"""Per-game Proton prefix DLL overrides, so installs work while Steam runs.

Steam keeps localconfig.vdf (where LaunchOptions live) in memory and writes it
back on exit, so LaunchOptions can only change while Steam is closed. Wine also
reads DLL overrides from each prefix's registry (pfx/user.reg,
Software\\Wine\\DllOverrides). Steam never rewrites that file; Wine's server
does while the game runs, so the prefix must be idle.

Records name exactly which values rtxForge set and what was there before, so a
restore removes only rtxForge's change and keeps anything the person edited.
"""
from pathlib import Path
import hashlib, json, os, re, tempfile, time

SECTION = '[Software\\\\Wine\\\\DllOverrides]'
NATIVE_BUILTIN = 'native,builtin'
RECORD_NAME = 'prefix-overrides.json'
_OVERRIDE = re.compile(r'(?:^|;)\s*([A-Za-z0-9_.\-]+(?:,[A-Za-z0-9_.\-]+)*)\s*=\s*n\s*,\s*b\s*(?=;|$)')
_VALUE = re.compile(r'^"((?:[^"\\]|\\.)*)"="((?:[^"\\]|\\.)*)"\s*$')


class PrefixError(ValueError):
    """A per-game reason the prefix route cannot be used, phrased as a next step."""


def override_names(launch_options):
    """DLL names from rtxForge's WINEDLLOVERRIDES launch string ("dxgi=n,b;winmm=n,b")."""
    match = re.search(r'WINEDLLOVERRIDES="([^"]*)"', launch_options or '')
    if not match:
        return []
    names = []
    for group in _OVERRIDE.findall(match.group(1)):
        for name in group.split(','):
            name = name.strip().lower()
            if name.endswith('.dll'):
                name = name[:-4]
            if name and name not in names:
                names.append(name)
    return names


def find_prefix(game_root, appid):
    """The game's Proton prefix: <library>/steamapps/compatdata/<appid>/pfx."""
    if not appid:
        raise PrefixError('Non-Steam games need Steam closed for this change. Close Steam, then try again.')
    root = Path(game_root).resolve()
    candidates = []
    for parent in root.parents:
        if parent.name == 'steamapps':
            candidates.append(parent / 'compatdata' / str(appid) / 'pfx')
            break
    home = Path.home()
    for steam in (home / '.local/share/Steam', home / '.steam/steam',
                  home / '.var/app/com.valvesoftware.Steam/.local/share/Steam'):
        candidates.append(steam / 'steamapps' / 'compatdata' / str(appid) / 'pfx')
    for prefix in candidates:
        if (prefix / 'user.reg').is_file():
            return prefix
    raise PrefixError('This game has not been started with Proton yet. Play it once, quit, then try again '
                      '(or close Steam to save the setting in Steam instead).')


def prefix_in_use(prefix, proc=Path('/proc')):
    """True while any process runs in this prefix (the game, its launcher or wineserver)."""
    if proc == Path('/proc'):
        import flatpak_host
        if flatpak_host.sandboxed():
            return bool(flatpak_host.probe('prefix-in-use', Path(prefix).resolve()))
    prefix = str(Path(prefix).resolve())
    compat = str(Path(prefix).parent)
    for entry in proc.iterdir() if proc.is_dir() else ():
        if not entry.name.isdigit():
            continue
        try:
            environ = (entry / 'environ').read_bytes().split(b'\0')
        except OSError:
            continue
        for item in environ:
            if item.startswith(b'WINEPREFIX=') or item.startswith(b'STEAM_COMPAT_DATA_PATH='):
                value = item.split(b'=', 1)[1].decode(errors='replace').rstrip('/')
                if value in (prefix, compat):
                    return True
    return False


def _section_bounds(lines):
    """(header index, end index) of the DllOverrides section, or None."""
    for index, line in enumerate(lines):
        if line.split(' ', 1)[0].rstrip('\n') == SECTION:
            end = index + 1
            while end < len(lines) and not lines[end].startswith('['):
                end += 1
            return index, end
    return None


def read_overrides(text):
    """{name: value} from the prefix's DllOverrides section."""
    lines = text.splitlines(keepends=True)
    bounds = _section_bounds(lines)
    values = {}
    if bounds:
        for line in lines[bounds[0] + 1:bounds[1]]:
            match = _VALUE.match(line.strip())
            if match:
                values[match.group(1).lower()] = match.group(2)
    return values


def edit_overrides(text, changes):
    """Set (value) or remove (None) DllOverrides entries; everything else is kept byte for byte."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
    bounds = _section_bounds(lines)
    if bounds is None:
        if not any(value is not None for value in changes.values()):
            return text
        if lines and lines[-1].strip():
            lines.append('\n')
        lines.append(f'{SECTION} {int(time.time())}\n')
        bounds = (len(lines) - 1, len(lines))
    start, end = bounds
    body = lines[start + 1:end]
    pending = {name.lower(): value for name, value in changes.items()}
    kept = []
    for line in body:
        match = _VALUE.match(line.strip())
        name = match.group(1).lower() if match else None
        if name in pending:
            value = pending.pop(name)
            if value is not None:
                kept.append(f'"{name}"="{value}"\n')
            continue
        kept.append(line)
    # New values go after the last existing value, before the section's blank line.
    insert_at = len(kept)
    while insert_at and not kept[insert_at - 1].strip():
        insert_at -= 1
    additions = [f'"{name}"="{value}"\n' for name, value in sorted(pending.items()) if value is not None]
    kept[insert_at:insert_at] = additions
    if end == len(lines) and (not kept or kept[-1].strip()):
        kept.append('\n')
    return ''.join(lines[:start + 1] + kept + lines[end:])


def _write_atomic(path, text):
    path = Path(path)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix='.rtxforge-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def apply(prefix, names, state_dir, proc=Path('/proc')):
    """Set each DLL to native,builtin in the prefix and record what was there before."""
    prefix = Path(prefix)
    if prefix_in_use(prefix, proc):
        raise PrefixError('This game is running. Quit it, then try again.')
    registry = prefix / 'user.reg'
    text = registry.read_text(encoding='utf-8', errors='surrogateescape')
    before = read_overrides(text)
    record_path = Path(state_dir) / RECORD_NAME
    previous = json.loads(record_path.read_text()) if record_path.is_file() else {}
    # Keep the very first "before" values across repairs, so restore returns to the original.
    original = dict(previous.get('original', {})) if previous.get('prefix') == str(prefix) else {}
    for name in names:
        original.setdefault(name, before.get(name))
    changes = {name: NATIVE_BUILTIN for name in names}
    after = edit_overrides(text, changes)
    if after != text:
        _write_atomic(registry, after)
    record = {'prefix': str(prefix), 'registry': str(registry), 'applied': changes, 'original': original,
              'after_sha256': _digest(after)}
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    _write_atomic(record_path, json.dumps(record, indent=1, sort_keys=True) + '\n')
    return record


def load_record(state_dir):
    path = Path(state_dir) / RECORD_NAME
    return json.loads(path.read_text()) if path.is_file() else None


def restore(state_dir, proc=Path('/proc')):
    """Undo rtxForge's overrides; values the person changed since are left alone."""
    record = load_record(state_dir)
    if not record:
        return {'status': 'none'}
    prefix = Path(record['prefix'])
    registry = Path(record['registry'])
    if not registry.is_file():
        (Path(state_dir) / RECORD_NAME).unlink(missing_ok=True)
        return {'status': 'prefix-gone'}
    if prefix_in_use(prefix, proc):
        raise PrefixError('This game is running. Quit it, then try again.')
    text = registry.read_text(encoding='utf-8', errors='surrogateescape')
    current = read_overrides(text)
    changes, kept = {}, []
    for name, value in record['applied'].items():
        if current.get(name) == value:
            changes[name] = record['original'].get(name)
        else:
            kept.append(name)
    after = edit_overrides(text, changes)
    if after != text:
        _write_atomic(registry, after)
    (Path(state_dir) / RECORD_NAME).unlink(missing_ok=True)
    return {'status': 'restored', 'kept': kept}
