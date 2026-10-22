"""The background helper's side of the in-game panel for Feeder NR games.

RenoDX keeps its live state in memory and reads [RenoDX.DLSS5] from the game's
ReShade.ini when it loads, so the helper never edits a running game. It saves
the panel's preset to that section, the same keys rtxForge Presets writes, for
the next launch. Neural rendering itself switches live inside the game.
"""
from __future__ import annotations

import ctypes
import hashlib
from pathlib import Path

import transactions as t
import feeder_provider as feeder

SECTION = 'RenoDX.DLSS5'
# Panel defaults; resolution follows the Feeder install default.
DEFAULTS = {'intensity': 1.0, 'passes': 1, 'work_scale': float(feeder.INSTALL_DEFAULTS['NRResolutionScale']),
            'preset': 0, 'style': 0, 'structure': 1.0}


def record(installations, directory):
    """The active Feeder install record for a game folder, or None."""
    path = installations / hashlib.sha256(str(directory).casefold().encode()).hexdigest() / 'baseline.json'
    if not path.is_file():
        return None
    t.need(path.stat().st_size < 1024 ** 2, 'Feeder install record is too large')
    found = t.read_json(t.safe(path))
    if not (isinstance(found, dict) and found.get('provider_id') == 'feeder' and found.get('status') == 'active'):
        return None
    t.need(Path(found.get('target') or '').resolve() == directory, 'Feeder install record identity differs')
    return found


def targets(installations):
    rows = []
    for path in sorted(installations.glob('*/baseline.json'))[:500]:
        try:
            t.need(path.stat().st_size < 1024 ** 2, 'Feeder install record is too large')
            found = t.read_json(t.safe(path))
            installed = game(installations, {'game': found.get('game'), 'exe': found.get('exe'),
                                             'name': found.get('name'), 'appid': found.get('appid')})
            if installed:
                rows.append({**installed['row'], 'name': found.get('name') or installed['exe'].stem})
        except (OSError, ValueError, KeyError, TypeError, AttributeError, t.Refusal):
            continue
    return rows


def _image(pid):
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
    k.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = k.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        size = ctypes.c_uint32(32768)
        text = ctypes.create_unicode_buffer(size.value)
        return Path(text.value).resolve() if k.QueryFullProcessImageNameW(handle, 0, text, ctypes.byref(size)) else None
    finally:
        k.CloseHandle(handle)


def running(game, processes):
    """The game's process id, checked by its full image path."""
    for pid in processes.get(game['exe'].name.casefold(), []):
        try:
            if _image(pid) == game['exe']:
                return pid
        except OSError:
            continue
    return 0


def _ini(game):
    path = t.safe(game['target'] / 'ReShade.ini')
    t.need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 256 * 1024,
           'Repair this Feeder installation; its ReShade.ini is missing.')
    return path, path.read_bytes().decode('utf-8-sig')


def values(game):
    _, text = _ini(game)
    parsed, found = t.ini(text), {}
    found['enabled'] = int(parsed.get(SECTION, 'NeuralUplift', fallback='0').strip() == '1')
    for key, (name, low, high) in feeder.TUNING.items():
        try:
            value = float(parsed.get(SECTION, name, fallback=str(DEFAULTS[key])))
        except ValueError:
            value = DEFAULTS[key]
        value = min(max(value, low), high)
        found[key] = round(value) if type(low) is int else value
    return found


def write(game, changes):
    """Save panel values to [RenoDX.DLSS5]; RenoDX loads them at its next launch."""
    path, text = _ini(game)
    settings = {'feature_controls': {key: value for key, value in changes.items() if key in feeder.TUNING}}
    if 'enabled' in changes:
        settings['nr_on_launch'] = bool(changes['enabled'])
    changed = feeder.apply_tuning(text, settings)
    if changed != text:
        t.atomic_file(path, changed.encode('utf-8'), 0o644)


def reset(game):
    write(game, DEFAULTS)


def game(installations, row):
    """A library row resolved to its Feeder install, or None for other games."""
    if not (isinstance(row, dict) and isinstance(row.get('game'), str) and isinstance(row.get('exe'), str)):
        return None
    root = Path(row['game']).resolve()
    relative = Path(row['exe'])
    if not root.is_dir() or relative.is_absolute() or str(relative) in ('', '.'):
        return None
    exe = (root / relative).resolve()
    if not (exe.is_file() and exe.is_relative_to(root)):
        return None
    found = record(installations, exe.parent)
    return found and {'row': {k: row.get(k) for k in ('game', 'exe', 'appid', 'name')}, 'exe': exe,
                      'target': exe.parent, 'model': (exe.parent / feeder.MODEL).is_file()}


def status(game, pid):
    nr = ({'state': 'managed', 'detail': 'RenoDX DLSS 5 neural rendering installed by rtxForge.'} if game['model']
          else {'state': 'changed', 'detail': 'The NR model is missing. Repair this game.'})
    nr['detail'] += ' File status does not establish live activity.'
    return {'state': 'running' if pid else 'waiting',
            'detail': 'Connected · tuning applies the next time the game starts' if pid else 'Start this game to use its panel.',
            'pid': pid, 'can_edit': False, 'can_save': True, 'can_mfg': False, 'can_nr': True, 'native_fresh': False,
            'values': values(game), 'saved': False, 'saved_values': {}, 'preset_compatible': True, 'preset_error': '',
            'pipelines': {'NR': nr}}
