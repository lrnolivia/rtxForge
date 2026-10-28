"""Host side of the in-game panel (ForgePanel) for games running under Proton.

The panel draws inside the game through the Skynizz bridge's OptiScaler ImGui
hook, so the game-side code is the Windows build unchanged. Two things differ
on Linux:

1. Preferences. On Windows the helper writes HKCU\\Software\\rtxForge\\Overlay
   (InGamePanel, PanelKey, PanelModifiers, Advanced, UseOptiScaler,
   ShortcutKey) and Overlay\\Games\\<exe> = "#RRGGBB|Title". Under Proton the
   bridge's RegGetValueW reads the *prefix's* HKCU, i.e. pfx/user.reg. This
   module writes exactly those values into one game's prefix, records what was
   there before, and restores only its own values. Wine's server owns
   user.reg while anything runs in the prefix, so every write refuses a busy
   prefix (wineserver would overwrite the edit on exit).

2. Control channel. The panel creates the named mapping
   Local\\rtxForge.panel.<pid> (protocol in providers/skynizz-bridge/
   ForgePanelChannel.h). A native Linux process cannot open a Wine named
   section. PanelChannelFile below implements the exact same 64-byte header and
   seqlock over a *file-backed* mapping, which both a Wine process (mapping a
   prefix file) and this host can open coherently. The candidate bridge detects
   Wine and creates this file; Windows retains its named pagefile mapping.
   linux_overlay_host binds the mapping to a managed executable and its exact
   live prefix, handles save/reset, and replays recipe-bound presets through
   the controls mailbox. Synthetic tests establish protocol compatibility,
   not real Proton execution. See docs/linux/overlay-channel.md.

The panel shortcut is read in-process by OptiScaler's input hook (OptiInput).
The Linux host never registers a global grab for it, so opening the panel
cannot move focus away from the game. A Wayland/Gamescope shortcut is only
needed for the standalone companion, never for this panel.
"""
from pathlib import Path
import hashlib
import json
import mmap
import os
import re
import struct
import time

import proton_prefix

OVERLAY_KEY = 'Software\\rtxForge\\Overlay'
GAMES_KEY = 'Software\\rtxForge\\Overlay\\Games'
RECORD_NAME = 'prefix-overlay.json'
PANEL_VALUES = ('InGamePanel', 'PanelKey', 'PanelModifiers', 'Advanced', 'UseOptiScaler', 'ShortcutKey',
                'LightTheme', 'ShowLiveStats', 'ShowWelcome', 'WelcomePosition')
# overlay_settings.POSITIONS / ForgeSettings.WelcomePositions; the bridge stores the index.
WELCOME_POSITIONS = ('top-center', 'top-left', 'top-right', 'bottom-left', 'bottom-right')


def light_theme(settings, app_theme=None):
    """OverlayHelper.LightTheme: Dark, Light, or Follow app (rtxForge's own theme on Linux)."""
    theme = settings.get('overlay_theme', 'dark')
    if theme not in ('dark', 'light', 'app'):
        raise OverlayError('Choose Dark, Light or Follow app for the overlay.')
    if theme != 'app':
        return theme == 'light'
    return (app_theme if app_theme is not None else settings.get('theme')) == 'light'

# Windows virtual-key names accepted for the panel shortcut (OverlayShortcut.cs).
_KEYS = {'End': 0x23, 'Home': 0x24, 'PageUp': 0x21, 'PageDown': 0x22, 'Left': 0x25, 'Up': 0x26,
         'Right': 0x27, 'Down': 0x28, 'Pause': 0x13, 'ScrollLock': 0x91, 'Delete': 0x2E,
         'Backspace': 8, 'Enter': 13, 'Space': 0x20, 'NumMultiply': 0x6A, 'NumAdd': 0x6B,
         'NumSubtract': 0x6D, 'NumDecimal': 0x6E, 'NumDivide': 0x6F, 'Semicolon': 0xBA, 'Equals': 0xBB,
         'Comma': 0xBC, 'Minus': 0xBD, 'Period': 0xBE, 'Slash': 0xBF, 'Backtick': 0xC0,
         'LeftBracket': 0xDB, 'Backslash': 0xDC, 'RightBracket': 0xDD, 'Quote': 0xDE}
_KEYS.update({chr(code): code for code in range(0x30, 0x3A)})
_KEYS.update({chr(code): code for code in range(0x41, 0x5B)})
_KEYS.update({'Num%d' % n: 0x60 + n for n in range(10)})
_KEYS.update({'F%d' % n: 0x6F + n for n in range(1, 25) if n != 12})
_MODIFIERS = {'ctrl': 2, 'alt': 1, 'shift': 4}
DEFAULT_SHORTCUT = 'Delete'


class OverlayError(ValueError):
    """A reason the panel preferences cannot be written, phrased as a next step."""


def parse_shortcut(value):
    """(normalized, modifiers, key) like OverlayShortcut.TryParse; key 0 means Disabled."""
    text = (value or '').strip()
    if text.casefold() == 'disabled':
        return 'Disabled', 0, 0
    if text.casefold() in ('', 'insert', 'end'):
        # Retired defaults move to Delete, as on Windows; other choices stay.
        text = DEFAULT_SHORTCUT
    parts = [part.strip() for part in text.split('+')]
    modifiers = 0
    for part in parts[:-1]:
        bit = _MODIFIERS.get(part.casefold())
        if not bit or modifiers & bit:
            raise OverlayError('Choose a key, with optional Ctrl, Alt or Shift.')
        modifiers |= bit
    name = next((known for known in _KEYS if known.casefold() == parts[-1].casefold()), None)
    if name is None:
        raise OverlayError('Choose a valid shortcut in Settings → Overlay.')
    key = _KEYS[name]
    if modifiers & 1 and key in (0x73, 0x20) or (modifiers & 3) == 3 and key == 0x2E:
        raise OverlayError('That shortcut belongs to the system. Choose another shortcut.')
    normalized = ('Ctrl+' if modifiers & 2 else '') + ('Alt+' if modifiers & 1 else '') + ('Shift+' if modifiers & 4 else '') + name
    return normalized, modifiers, key


def preferences(settings):
    """The DWORDs the bridge reads once at game start (OverlayHelper.ConfigureStartup/ConfigurePanel)."""
    def flag(name, default):
        value = settings.get(name, default)
        if type(value) is not bool:
            raise OverlayError('Choose on or off for ' + name.replace('_', ' ') + '.')
        return value
    renderer = settings.get('overlay_renderer', 'game')
    if renderer == 'rtxforge': renderer = 'game'  # shared Windows preference
    if renderer not in ('game', 'optiscaler', 'standalone'):
        raise OverlayError('Choose a supported overlay renderer.')
    controls = settings.get('overlay_controls', 'unified')
    if controls not in ('unified', 'classic'):
        raise OverlayError('Choose Unified or Advanced controls.')
    hotkey = settings.get('optiscaler_hotkey', 'Insert')
    if hotkey not in ('Insert', 'F8', 'Disabled'):
        raise OverlayError('Choose a supported OptiScaler shortcut.')
    position = settings.get('overlay_welcome_position', 'top-center')
    if position not in WELCOME_POSITIONS:
        raise OverlayError('Choose a supported welcome position.')
    _, modifiers, key = parse_shortcut(settings.get('panel_hotkey', DEFAULT_SHORTCUT))
    return {
        'InGamePanel': 1 if renderer == 'game' else 0,
        'PanelKey': key, 'PanelModifiers': modifiers,
        'Advanced': 1 if controls == 'classic' else 0,
        'UseOptiScaler': 1 if flag('optiscaler_ui', True) else 0,
        'ShortcutKey': 0x77 if hotkey == 'F8' else 0 if hotkey == 'Disabled' else 0x2D,
        # OverlayHelper.ConfigurePanel: read once at game start; the helper updates them live.
        'LightTheme': 1 if light_theme(settings) else 0,
        'ShowLiveStats': 1 if flag('overlay_live_stats', True) else 0,
        'ShowWelcome': 1 if flag('overlay_welcome', True) else 0,
        'WelcomePosition': WELCOME_POSITIONS.index(position),
    }


# --- Wine registry text (user.reg) -------------------------------------------------------

def _escape(text):
    out = []
    for index, char in enumerate(text):
        code = ord(char)
        if char in '\\"':
            out.append('\\' + char)
        elif 32 <= code < 127:
            out.append(char)
        else:
            # Wine reads up to four hex digits after \x; always writing four is unambiguous.
            out.append('\\x%04x' % code)
    return ''.join(out)


def _unescape(text):
    return re.sub(r'\\x([0-9a-fA-F]{1,4})|\\(.)', lambda m: chr(int(m.group(1), 16)) if m.group(1) else m.group(2), text)


def dword(value):
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise OverlayError('Invalid registry number.')
    return 'dword:%08x' % value


def string(value):
    return '"' + _escape(value) + '"'


def _header(key):
    return '[' + key.replace('\\', '\\\\') + ']'


_LINE = re.compile(r'^"((?:[^"\\]|\\.)*)"=(.*)$')


def _bounds(lines, key):
    header = _header(key).casefold()
    for index, line in enumerate(lines):
        if line.split(' ', 1)[0].rstrip('\r\n').casefold() == header:
            end = index + 1
            while end < len(lines) and not lines[end].startswith('['):
                end += 1
            return index, end
    return None


def drop_empty(text, key):
    """Remove one key that holds no values (its header, #time line and blank tail); the rest stays byte for byte."""
    lines = text.splitlines(keepends=True)
    bounds = _bounds(lines, key)
    if bounds is None or any(_LINE.match(line.rstrip('\r\n')) for line in lines[bounds[0] + 1:bounds[1]]):
        return text
    return ''.join(lines[:bounds[0]] + lines[bounds[1]:])


def read_values(text, key):
    """{name (as written): raw encoded value} for one registry key."""
    lines = text.splitlines(keepends=True)
    bounds = _bounds(lines, key)
    values = {}
    if bounds:
        for line in lines[bounds[0] + 1:bounds[1]]:
            match = _LINE.match(line.rstrip('\r\n'))
            if match:
                values[_unescape(match.group(1))] = match.group(2)
    return values


def edit_values(text, key, changes):
    """Set ({name: encoded}) or remove ({name: None}) values in one key; the rest stays byte for byte."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
    bounds = _bounds(lines, key)
    if bounds is None:
        if not any(value is not None for value in changes.values()):
            return text
        if lines and lines[-1].strip():
            lines.append('\n')
        stamp = int(time.time())
        lines.append(f'{_header(key)} {stamp}\n')
        lines.append('#time=%x\n' % ((stamp + 11644473600) * 10000000))
        bounds = (len(lines) - 2, len(lines))
    start, end = bounds
    body = lines[start + 1:end]
    pending = {name.casefold(): (name, value) for name, value in changes.items()}
    kept = []
    for line in body:
        match = _LINE.match(line.rstrip('\r\n'))
        folded = _unescape(match.group(1)).casefold() if match else None
        if folded in pending:
            name, value = pending.pop(folded)
            if value is not None:
                kept.append(f'"{_escape(name)}"={value}\n')
            continue
        kept.append(line)
    insert_at = len(kept)
    while insert_at and not kept[insert_at - 1].strip():
        insert_at -= 1
    kept[insert_at:insert_at] = [f'"{_escape(name)}"={value}\n' for name, value in sorted(pending.values())
                                 if value is not None]
    if end == len(lines) and (not kept or kept[-1].strip()):
        kept.append('\n')
    return ''.join(lines[:start + 1] + kept + lines[end:])


# --- DOS paths for the identity value -------------------------------------------------------

def dos_paths(prefix, unix_path):
    """The Windows paths Wine may report for a Linux file (GetModuleFileNameW), most specific first.

    Wine maps a path through the prefix's dosdevices links. Steam may launch
    through a symlinked parent (Bazzite: /home -> /var/home), so both the
    given and the resolved spelling are returned.
    """
    candidates = []
    devices = Path(prefix) / 'dosdevices'
    links = []
    try:
        for entry in devices.iterdir():
            if re.fullmatch(r'[a-z]:', entry.name) and entry.is_symlink():
                target = os.readlink(entry)
                root = (devices / target).resolve() if not os.path.isabs(target) else Path(target)
                links.append((entry.name[0].upper(), Path(os.path.normpath(root))))
    except OSError:
        pass
    links.sort(key=lambda item: len(item[1].parts), reverse=True)
    for spelling in dict.fromkeys([Path(unix_path), Path(unix_path).resolve()]):
        for letter, root in links:
            try:
                relative = spelling.relative_to(root)
            except ValueError:
                continue
            path = letter + ':\\' + '\\'.join(relative.parts)
            if path not in candidates:
                candidates.append(path)
    return candidates


def identity(prefix, exe, title, accent):
    if not re.fullmatch(r'#[0-9A-Fa-f]{6}', accent or ''):
        raise OverlayError('Choose a game accent colour.')
    title = (title or 'Game').strip()[:200] or 'Game'
    return {path: string(accent.upper() + '|' + title) for path in dos_paths(prefix, exe)}


# --- Review / apply / restore ---------------------------------------------------------------

def _digest(text):
    return hashlib.sha256(text.encode('utf-8', 'surrogateescape')).hexdigest()


def plan(prefix, settings, exe=None, title=None, accent=None, proc=Path('/proc')):
    """Exactly which values a write would change in this prefix; nothing is written."""
    prefix = Path(prefix)
    registry = prefix / 'user.reg'
    if not registry.is_file() or registry.is_symlink():
        raise OverlayError('This game has not been started with Proton yet. Play it once, quit, then try again.')
    if proton_prefix.prefix_in_use(prefix, proc):
        raise OverlayError('This game is running. Quit it, then try again.')
    text = registry.read_text(encoding='utf-8', errors='surrogateescape')
    wanted = {OVERLAY_KEY: {name: dword(value) for name, value in preferences(settings).items()}}
    if exe and accent:
        wanted[GAMES_KEY] = identity(prefix, exe, title, accent)
    changes = {}
    for key, values in wanted.items():
        current = {name.casefold(): value for name, value in read_values(text, key).items()}
        delta = {name: value for name, value in values.items() if current.get(name.casefold()) != value}
        if delta:
            changes[key] = delta
    return {'prefix': str(prefix), 'registry': str(registry), 'before_sha256': _digest(text),
            'changes': changes, 'unchanged': not changes,
            'summary': 'Panel preferences already match' if not changes else
                       'Sets ' + ', '.join(sorted(n for values in changes.values() for n in values if n in PANEL_VALUES) or ['the game identity'])
                       + " in this game's Proton prefix · applies next launch"}


def apply(reviewed, state_dir, proc=Path('/proc')):
    """Write a reviewed plan. Refuses a busy prefix or a registry that changed since review."""
    prefix = Path(reviewed['prefix'])
    registry = Path(reviewed['registry'])
    if proton_prefix.prefix_in_use(prefix, proc):
        raise OverlayError('This game is running. Quit it, then try again.')
    text = registry.read_text(encoding='utf-8', errors='surrogateescape')
    if _digest(text) != reviewed['before_sha256']:
        raise OverlayError("The game's Proton settings changed since review. Review again.")
    record_path = Path(state_dir) / RECORD_NAME
    previous = json.loads(record_path.read_text()) if record_path.is_file() else {}
    same = previous.get('prefix') == str(prefix)
    original = {key: dict(values) for key, values in (previous.get('original') or {}).items()} if same else {}
    applied = {key: dict(values) for key, values in (previous.get('applied') or {}).items()} if same else {}
    after = text
    for key, values in reviewed['changes'].items():
        before = {name.casefold(): value for name, value in read_values(after, key).items()}
        for name, value in values.items():
            original.setdefault(key, {}).setdefault(name, before.get(name.casefold()))
            applied.setdefault(key, {})[name] = value
        after = edit_values(after, key, values)
    if after != text:
        proton_prefix._write_atomic(registry, after)
    record = {'prefix': str(prefix), 'registry': str(registry), 'original': original, 'applied': applied,
              'after_sha256': _digest(after)}
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    proton_prefix._write_atomic(record_path, json.dumps(record, indent=1, sort_keys=True) + '\n')
    return record


def restore(state_dir, proc=Path('/proc')):
    """Return each value rtxForge set to what was there before; values changed since are kept."""
    record_path = Path(state_dir) / RECORD_NAME
    if not record_path.is_file():
        return {'status': 'none'}
    record = json.loads(record_path.read_text())
    registry = Path(record['registry'])
    if not registry.is_file():
        record_path.unlink()
        return {'status': 'prefix-gone'}
    if proton_prefix.prefix_in_use(Path(record['prefix']), proc):
        raise OverlayError('This game is running. Quit it, then try again.')
    text = registry.read_text(encoding='utf-8', errors='surrogateescape')
    after, kept = text, []
    for key, values in record['applied'].items():
        current = {name.casefold(): value for name, value in read_values(after, key).items()}
        changes = {}
        for name, value in values.items():
            if current.get(name.casefold()) == value:
                changes[name] = record['original'].get(key, {}).get(name)
            else:
                kept.append(name)
        after = edit_values(after, key, changes)
        if not any(value is not None for value in record['original'].get(key, {}).values()):
            after = drop_empty(after, key)  # rtxForge created this key; leave none of it behind
    if after != text:
        proton_prefix._write_atomic(registry, after)
    record_path.unlink()
    return {'status': 'restored', 'kept': kept}


# --- File-backed control channel (host half, protocol header version 1) ---------------------

MAGIC = 0x50465852
CAPACITY = 32768
HEADER = struct.Struct('<10i24x')   # magic, version, pid, request, response, visible, requestLength, responseLength, revision, ownsShortcut
SIZE = HEADER.size + CAPACITY * 2
_FIELDS = ('magic', 'version', 'pid', 'request', 'response', 'visible', 'request_length', 'response_length',
           'revision', 'owns_shortcut')
assert HEADER.size == 64


def channel_path(prefix, pid):
    """Where an opted-in bridge would create its file-backed mapping inside the prefix (C:\\users\\steamuser\\AppData\\Local\\rtxForge)."""
    return Path(prefix) / 'drive_c' / 'users' / 'steamuser' / 'AppData' / 'Local' / 'rtxForge' / f'panel.{int(pid)}.map'


class PanelChannelFile:
    """Host side of ForgePanelChannel over a shared file. Mirrors NativePanelChannel.TryRead/Reply."""

    def __init__(self, path):
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size != SIZE:
            raise FileNotFoundError(str(path))
        fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            info=os.fstat(fd)
            if info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_size!=SIZE:
                raise OverlayError('Invalid panel channel file.')
            self._file=os.fdopen(fd,'r+b')
        except BaseException:
            os.close(fd);raise
        self._map = mmap.mmap(self._file.fileno(), SIZE)
        self.handled = 0

    def close(self):
        self._map.close()
        self._file.close()

    def header(self):
        return dict(zip(_FIELDS, HEADER.unpack_from(self._map, 0)))

    def _set(self, field, value):
        struct.pack_into('<i', self._map, _FIELDS.index(field) * 4, value)

    @property
    def valid(self):
        head = self.header()
        return head['magic'] == MAGIC and head['version'] == 1

    @property
    def visible(self):
        return self.valid and self.header()['visible'] == 1

    def try_read(self):
        """(request id, request dict) for a complete, unhandled request, else None."""
        head = self.header()
        request = head['request']
        if not self.valid or request <= 0 or request & 1 or request == self.handled or request == head['response']:
            return None
        length = head['request_length']
        if not 0 < length <= CAPACITY:
            return None
        body = bytes(self._map[64:64 + length])
        if self.header()['request'] != request:
            return None   # the panel started another write meanwhile
        self.handled = request
        try:
            message = json.loads(body.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            return request, None
        return request, message if isinstance(message, dict) else None

    def reply(self, request, response):
        body = json.dumps(response, separators=(',', ':')).encode('utf-8')
        if not body or len(body) > CAPACITY:
            raise OverlayError('Panel response is too large.')
        revision = self.header()['revision']
        writing = revision + 1 if revision % 2 == 0 else revision
        self._set('revision', writing)                       # odd: response being written
        self._map[64 + CAPACITY:64 + CAPACITY + len(body)] = body
        self._set('response_length', len(body))
        self._set('response', request)
        self._set('revision', writing + 1 if writing < 0x7ffffff0 else 2)
        self._map.flush()


def handle(message, settings):
    """Answers the panel can rely on today; anything that writes game files stays in the rtxForge app."""
    action = message.get('op', '') if isinstance(message, dict) else ''
    snapshot = settings_snapshot(settings)
    if action in ('hello', 'status'):
        return {'op': action, 'settings': snapshot, 'status': {}}
    if action == 'discard-review':
        return {'op': action, 'message': '', 'settings': snapshot}
    return {'op': action, 'error': True, 'settings': snapshot,
            'message': 'Use rtxForge on Linux for this. The Linux panel helper is not finished yet.'}


def settings_snapshot(settings, app_theme=None):
    _, modifiers, key = parse_shortcut(settings.get('panel_hotkey', DEFAULT_SHORTCUT))
    return {
        'overlay_controls': settings.get('overlay_controls', 'unified'),
        # NativePanelCoordinator.SettingsSnapshot: the choice plus its resolved light/dark.
        'overlay_theme': settings.get('overlay_theme', 'dark'),
        'overlay_light': light_theme(settings, app_theme),
        'overlay_renderer': settings.get('overlay_renderer', 'game'),
        'overlay_live_stats': bool(settings.get('overlay_live_stats', True)),
        'overlay_welcome': bool(settings.get('overlay_welcome', True)),
        'overlay_welcome_position': settings.get('overlay_welcome_position', 'top-center'),
        'vulkan_mfg_native_menu': bool(settings.get('vulkan_mfg_native_menu', False)),
        'panel_hotkey': settings.get('panel_hotkey', DEFAULT_SHORTCUT),
        'panel_key': key, 'panel_modifiers': modifiers,
        'overlay_helper': bool(settings.get('overlay_helper', True)),
        'overlay_start_with_windows': False,
        'optiscaler_ui': bool(settings.get('optiscaler_ui', True)),
        'optiscaler_intro': bool(settings.get('optiscaler_intro', False)),
        'optiscaler_hotkey': settings.get('optiscaler_hotkey', 'Insert'),
        'reshade_ui': bool(settings.get('reshade_ui', True)),
        'reshade_intro': bool(settings.get('reshade_intro', False)),
    }
