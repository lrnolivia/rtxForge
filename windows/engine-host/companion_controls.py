"""Bounded live controls for an owned Skynizz installation and local saved presets.

No game files are written. Presets belong to rtxForge and are reapplied while
its host is running, only to the same installed loader and game executable.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import threading
import time
import uuid
import configparser

import transactions as t

MAGIC, SIZE = 0x46585452, 256
OFFSETS = {'enabled': 64, 'intensity': 68, 'multiplier': 72, 'pre_sr': 76,
           'cache': 80, 'interval': 84, 'style': 88, 'structure': 92,
           'tone': 96, 'preset': 132}
DEFAULTS = {'enabled': 1, 'intensity': 1.0, 'multiplier': -1, 'pre_sr': 1,
            'cache': 0, 'interval': 1, 'style': 0, 'structure': 1.0, 'tone': 1.0, 'preset': 0}
INI_KEYS = {'enabled': 'Enabled', 'intensity': 'Intensity', 'pre_sr': 'PreSr',
            'cache': 'CacheEnabled', 'interval': 'CacheInterval', 'style': 'Style',
            'structure': 'LocalStructure', 'tone': 'LocalTone', 'preset': 'Preset'}
_FLOATS = {'intensity', 'structure', 'tone'}
EXTRA = {'work_scale': (288, 'WorkingScale', 1.0), 'passes': (292, 'Passes', 1),
         'skin': (296, 'SkinStructure', -1.0), 'auto_mask': (300, 'AutoMask', 1),
         'detail': (304, 'TransferStrength', 1.0), 'colour': (308, 'ColourStrength', 1.0),
         'reduced': (312, 'PreSrReduced', 0), 'edge_aware': (316, 'JbuUpsample', 0)}
LEGACY_KEYS = set(DEFAULTS)
OFFSETS.update({key: spec[0] for key, spec in EXTRA.items()})
DEFAULTS.update({key: spec[2] for key, spec in EXTRA.items()})
INI_KEYS.update({key: spec[1] for key, spec in EXTRA.items()})
_FLOATS.update({'work_scale', 'skin', 'detail', 'colour'})
_BOOLS = {'enabled', 'pre_sr', 'cache', 'auto_mask', 'reduced', 'edge_aware'}


def validate_changes(changes):
    t.need(isinstance(changes, dict) and changes and set(changes) <= set(DEFAULTS), 'Choose a supported control.')
    result = {}
    for key, value in changes.items():
        if key in _FLOATS:
            low = -1 if key == 'skin' else .25 if key == 'work_scale' else 0
            t.need(type(value) in (int, float) and math.isfinite(value) and low <= value <= 2,
                   'An image control is outside its supported range.')
            result[key] = float(value)
        else:
            t.need(type(value) is int, 'A control value is invalid.')
            valid = (value in (0, 1) if key in _BOOLS else
                     value in (-1, 0, 2, 3, 4, 5, 6) if key == 'multiplier' else
                     1 <= value <= 16 if key == 'interval' else
                     1 <= value <= 3 if key == 'passes' else
                     0 <= value <= 2 if key == 'style' else 0 <= value <= 3)
            t.need(valid, 'A control value is outside the supported range.')
            result[key] = value
    return result


def decode(raw, pid):
    t.need(len(raw) in (SIZE, 512), 'The game returned an incomplete control snapshot.')
    magic, version, found = struct.unpack_from('<III', raw)
    t.need(magic == MAGIC and version in (1, 2, 3) and found == pid
           and len(raw) == (512 if version == 3 else SIZE), 'This game uses an unsupported control protocol.')
    values = {key: struct.unpack_from('<f' if key in _FLOATS else '<i', raw, offset)[0]
              for key, offset in OFFSETS.items() if version == 3 or key in LEGACY_KEYS}
    validate_changes(values)
    failure = raw[160:256] if version >= 2 else raw[136:256]
    failure = failure.split(b'\0', 1)[0].decode('utf-8', errors='replace')
    result = {'values': values, 'sequence': struct.unpack_from('<i', raw, 12)[0],
              'command': struct.unpack_from('<i', raw, 16)[0], 'ack': struct.unpack_from('<i', raw, 20)[0],
              'result': struct.unpack_from('<i', raw, 24)[0], 'nr_running': bool(struct.unpack_from('<i', raw, 100)[0]),
              'nr_ms': struct.unpack_from('<f', raw, 104)[0], 'rendered_fps': struct.unpack_from('<f', raw, 108)[0],
              'backend_max': struct.unpack_from('<i', raw, 112)[0], 'fg_successes': struct.unpack_from('<i', raw, 124)[0],
              'version': version, 'failure': failure}
    if version >= 2:
        for key, offset in {'native_status': 136, 'native_presented': 140, 'native_samples': 144,
                            'native_tick': 148, 'native_mode': 152, 'native_generated': 156}.items():
            result[key] = struct.unpack_from('<i', raw, offset)[0]
    return result


def _api():
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    for name, arguments, result in [
        ('OpenProcess', [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32], ctypes.c_void_p),
        ('QueryFullProcessImageNameW', [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)], ctypes.c_bool),
        ('OpenFileMappingW', [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p], ctypes.c_void_p),
        ('MapViewOfFile', [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t], ctypes.c_void_p),
        ('UnmapViewOfFile', [ctypes.c_void_p], ctypes.c_bool),
        ('CloseHandle', [ctypes.c_void_p], ctypes.c_bool),
        ('WaitForSingleObject', [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_uint32),
        ('GetTickCount', [], ctypes.c_uint32),
    ]:
        function = getattr(k, name)
        function.argtypes, function.restype = arguments, result
    return k


class Mailbox:
    def __init__(self, pid, exe, write=False):
        self.pid, self.k, self.process, self.mapping, self.view = pid, _api(), None, None, None
        try:
            self.process = self.k.OpenProcess(0x101000, False, pid)
            if not self.process: raise OSError('The game process is unavailable.')
            buffer, size = ctypes.create_unicode_buffer(32768), ctypes.c_uint32(32768)
            if not self.k.QueryFullProcessImageNameW(self.process, 0, buffer, ctypes.byref(size)):
                raise OSError('The game executable could not be verified.')
            if Path(buffer.value).resolve() != exe:
                raise OSError('The running process does not match the selected game.')
            access = 6 if write else 4
            self.mapping = self.k.OpenFileMappingW(access, False, f'Local\\rtxForge.controls.{pid}')
            if not self.mapping: raise OSError('Waiting for the game controls to start.')
            self.view = self.k.MapViewOfFile(self.mapping, access, 0, 0, 0)
            if not self.view: raise OSError('The game control snapshot could not be opened.')
            header = ctypes.string_at(self.view, 12)
            magic, version, found = struct.unpack('<III', header)
            t.need(magic == MAGIC and version in (1, 2, 3) and found == pid, 'Unsupported game control protocol.')
            self.size = 512 if version == 3 else SIZE
            self.read()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.view: self.k.UnmapViewOfFile(self.view)
        if self.mapping: self.k.CloseHandle(self.mapping)
        if self.process: self.k.CloseHandle(self.process)
        self.view = self.mapping = self.process = None

    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def read(self):
        t.need(self.k.WaitForSingleObject(self.process, 0) == 258, 'The game has stopped.')
        for _ in range(12):
            raw = ctypes.string_at(self.view, self.size)
            sequence = struct.unpack_from('<i', raw, 12)[0]
            if not sequence & 1 and ctypes.c_long.from_address(self.view + 12).value == sequence:
                return decode(raw, self.pid)
            time.sleep(.001)
        raise t.Refusal('The game is busy. Try the control again.')

    def apply(self, changes):
        changes = validate_changes(changes)
        before = self.read()
        t.need(before['version'] >= 3 or not (set(changes) - LEGACY_KEYS),
               'Update this game package to use the additional NR controls.')
        values = before['values'] | changes
        if 'multiplier' in changes and changes['multiplier'] > 0:
            t.need(before['backend_max'] >= changes['multiplier'] - 1, 'This game does not support that multiplier.')
        sequence = max(before['command'], before['ack']) + 2
        sequence += sequence & 1
        ctypes.c_long.from_address(self.view + 16).value = sequence - 1
        packed = struct.pack('<ifiiiiiff', values['enabled'], values['intensity'], values['multiplier'],
                             values['pre_sr'], values['cache'], values['interval'], values['style'], values['structure'], values['tone'])
        ctypes.memmove(self.view + 28, packed, len(packed))
        ctypes.c_long.from_address(self.view + 128).value = values['preset']
        if before['version'] >= 3:
            for key, (offset, _, _) in EXTRA.items():
                raw = struct.pack('<f' if key in _FLOATS else '<i', values[key])
                ctypes.memmove(self.view + offset - 32, raw, 4)
        ctypes.c_long.from_address(self.view + 16).value = sequence
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            found = self.read()
            if found['ack'] == sequence:
                t.need(found['result'] == 1, 'The game refused that control value.')
                return found
            time.sleep(.025)
        raise t.Refusal('The game has not applied the change yet. Check its status before trying again.')


class Controls:
    def __init__(self, state):
        self.state = Path(state) / 'runtime-presets'
        self.lock = threading.RLock()
        self.verified, self.previous, self.last_pid, self.preset_errors = {}, {}, {}, {}
        self.process_cache, self.process_time = {}, 0
        self.presets = {}
        self.watcher = None
        if self.state.is_dir():
            for path in list(self.state.glob('*.json'))[:1000]:
                try:
                    t.need(not path.is_symlink() and path.stat().st_size < 65536, 'Unsafe preset')
                    data = json.loads(path.read_text(encoding='utf-8'))
                    t.need(isinstance(data, dict) and data.get('schema') == 1, 'Unsupported preset')
                    row = data.get('row')
                    t.need(isinstance(row, dict) and all(isinstance(row.get(key), str) for key in ('game', 'exe')), 'Invalid preset game')
                    t.need(isinstance(data.get('recipe'), str) and len(data['recipe']) == 64, 'Invalid preset recipe')
                    validate_changes(data['changes'])
                    self.presets[path.stem] = data
                except (OSError, ValueError, KeyError, TypeError, t.Refusal): pass
        self._start_watcher()

    def _game(self, params):
        row = params.get('row') or {}
        t.need(isinstance(row, dict) and isinstance(row.get('game'), str) and row['game'].strip(), 'Choose an installed game.')
        root = Path(row.get('game') or '').resolve()
        relative = Path(row.get('exe') or '')
        t.need(root.is_dir() and str(relative) not in ('', '.') and not relative.is_absolute(), 'Choose an installed game.')
        exe = (root / relative).resolve()
        t.need(exe.is_file() and exe.suffix.casefold() == '.exe' and exe.is_relative_to(root), 'The game executable is missing or outside its folder.')
        target = exe.parent
        metadata = target / '.rtxforge-install.json'
        t.need(metadata.is_file() and not metadata.is_symlink() and metadata.stat().st_size < 2 * 1024**2,
               'Install the current Skynizz package for this game first.')
        record = json.loads(metadata.read_text(encoding='utf-8-sig'))
        t.need(isinstance(record, dict) and isinstance(record.get('provider'), dict)
               and record['provider'].get('id') == 'skynizz', 'Live controls require a Skynizz installation.')
        t.need(isinstance(record.get('files'), dict), 'The installed file record is invalid; repair this game.')
        proxy = record.get('proxy') or ''
        t.need(Path(proxy).name == proxy and proxy.casefold().endswith('.dll'), 'The installed loader could not be verified.')
        loader = target / proxy
        expected = (record.get('files') or {}).get(proxy)
        t.need(loader.is_file() and not loader.is_symlink() and isinstance(expected, str), 'The installed loader is missing; repair this game.')
        signature = (loader.stat().st_size, loader.stat().st_mtime_ns, expected)
        if self.verified.get(str(loader)) != signature:
            with loader.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            t.need(digest == expected, 'The game loader changed; repair before using live controls.')
            self.verified[str(loader)] = signature
        key = hashlib.sha256(os.path.normcase(str(exe)).encode()).hexdigest()
        files = {name.casefold() for name in record.get('files', {})}
        immutable = {name.casefold(): digest for name, digest in record['files'].items()
                     if not name.casefold().endswith(('.ini', '.log'))}
        t.need(all(isinstance(value, str) and len(value) == 64 for value in immutable.values()), 'The installed recipe is invalid; repair this game.')
        recipe = hashlib.sha256(json.dumps({'files': immutable, 'mode': record.get('feature_mode')}, sort_keys=True).encode()).hexdigest()
        mfg = record.get('feature_mode') == 'nr-mfg' and 'renodx-mfgunlock.addon64' not in files
        return {'row': {k: row.get(k) for k in ('game', 'exe', 'appid', 'name')}, 'root': root,
                'exe': exe, 'target': target, 'key': key, 'recipe': recipe, 'can_mfg': mfg}

    def _configured(self, game):
        path = game['target'] / 'OptiScaler.ini'
        t.need(path.is_file() and not path.is_symlink() and path.stat().st_size < 2 * 1024**2, 'Repair the missing or unsafe game configuration.')
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(path.read_text(encoding='utf-8-sig'))
        values = dict(DEFAULTS)
        for key, ini in INI_KEYS.items():
            raw = parser.get('DlssNr', ini, fallback='auto').strip().casefold()
            if raw != 'auto':
                if key in _BOOLS:
                    t.need(raw in ('true', 'false', '0', '1'), 'A game configuration value is invalid; repair this game.')
                values[key] = (int(raw in ('true', '1')) if key in _BOOLS else
                               float(raw) if key in _FLOATS else int(raw))
        count = parser.get('DLSSG', 'OverrideInterpolationCount', fallback='auto').strip().casefold()
        if count != 'auto':
            t.need(0 <= int(count) <= 5, 'The saved MFG count is invalid; repair this game.')
            values['multiplier'] = 0 if int(count) == 0 else int(count) + 1
        return validate_changes(values)

    def _open(self, game, write=False):
        for pid in self._processes().get(game['exe'].name.casefold(), []):
            try:
                return Mailbox(pid, game['exe'], write)
            except OSError: continue
        return None

    def _processes(self):
        # One lightweight inventory per interval, rather than spawning a query
        # per saved game. Mailbox verifies each candidate's complete image path.
        if time.monotonic() - self.process_time < 2: return self.process_cache
        class Entry(ctypes.Structure):
            _fields_ = [('size', ctypes.c_uint32), ('usage', ctypes.c_uint32), ('pid', ctypes.c_uint32),
                        ('heap', ctypes.c_void_p), ('module', ctypes.c_uint32), ('threads', ctypes.c_uint32),
                        ('parent', ctypes.c_uint32), ('priority', ctypes.c_long), ('flags', ctypes.c_uint32),
                        ('exe', ctypes.c_wchar * 260)]
        k = _api()
        k.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        for name in ('Process32FirstW', 'Process32NextW'):
            getattr(k, name).argtypes = [ctypes.c_void_p, ctypes.POINTER(Entry)]
            getattr(k, name).restype = ctypes.c_bool
        handle = k.CreateToolhelp32Snapshot(2, 0)
        t.need(handle not in (None, ctypes.c_void_p(-1).value), 'Windows could not read running games.')
        found, entry = {}, Entry()
        entry.size = ctypes.sizeof(Entry)
        try:
            t.need(k.Process32FirstW(handle, ctypes.byref(entry)), 'Windows could not read running games.')
            while True:
                found.setdefault(entry.exe.casefold(), []).append(entry.pid)
                if not k.Process32NextW(handle, ctypes.byref(entry)): break
            t.need(ctypes.get_last_error() in (0, 18), 'Windows could not finish checking running games.')
        finally: k.CloseHandle(handle)
        self.process_cache, self.process_time = found, time.monotonic()
        return found

    def _present(self, game, box, found):
        now = time.monotonic()
        old_sequence, last_change = self.previous.get(box.pid, (None, now))
        if old_sequence != found['sequence']: last_change = now
        self.previous[box.pid] = (found['sequence'], last_change)
        stalled = now - last_change > 4
        native_age = (box.k.GetTickCount() - (found.get('native_tick', 0) & 0xffffffff)) & 0xffffffff
        native_fresh = found.get('native_samples', 0) > 0 and native_age < 2000
        # Missing GPU timing is not a zero-cost NR pass.
        found['nr_ms'] = found['nr_ms'] if found['nr_ms'] > 0 and math.isfinite(found['nr_ms']) else None
        fps = found['rendered_fps']
        found['rendered_fps'] = fps if found['nr_running'] and 0 < fps < 10000 and math.isfinite(fps) else None
        return {'state': 'stalled' if stalled else 'running', 'detail': 'Waiting for the game to respond.' if stalled else 'Connected',
                'pid': box.pid, 'can_edit': not stalled, 'can_save': True, 'can_mfg': game['can_mfg'],
                'native_fresh': bool(native_fresh) and not stalled, **found}

    def status(self, params):
        with self.lock:
            try:
                game = self._game(params)
                configured = self._configured(game)
                saved = self.presets.get(game['key'])
                result = {'state': 'waiting', 'detail': 'Start this game to use live controls.', 'can_edit': False,
                          'can_save': True, 'can_mfg': game['can_mfg'], 'values': configured, 'native_fresh': False}
                box = self._open(game)
                if box:
                    with box: result = self._present(game, box, box.read())
                result['saved'] = bool(saved)
                result['saved_values'] = (saved or {}).get('changes') or {}
                result['preset_compatible'] = not saved or saved.get('recipe') == game['recipe']
                result['preset_error'] = self.preset_errors.get(game['key'], '')
                return result
            except (t.Refusal, OSError, ValueError, KeyError, configparser.Error) as error:
                return {'state': 'unavailable', 'detail': str(error), 'can_edit': False, 'can_save': False,
                        'can_mfg': False, 'native_fresh': False, 'values': dict(DEFAULTS)}

    def active(self, params):
        """Resolve only verified, connected game processes; never choose a library default."""
        with self.lock:
            rows = params.get('rows')
            t.need(isinstance(rows, list) and len(rows) <= 500, 'Refresh the game library.')
            foreground = params.get('foreground_pid', 0)
            retained = params.get('retained_pid', 0)
            t.need(type(foreground) is int and type(retained) is int, 'Invalid process selection.')
            processes = self._processes()
            candidates, seen = [], set()
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get('exe'), str): continue
                if Path(row['exe']).name.casefold() not in processes: continue
                try:
                    game = self._game({'row': row})
                    if game['key'] in seen: continue
                    seen.add(game['key'])
                    box = self._open(game)
                    if box is None: continue
                    with box:
                        found = self._present(game, box, box.read())
                        candidates.append({'row': game['row'], **found})
                except (t.Refusal, OSError, ValueError, KeyError, configparser.Error): continue
            for pid in (foreground, retained):
                if pid > 0:
                    match = next((item for item in candidates if item['pid'] == pid), None)
                    if match is not None: return match
            if len(candidates) == 1: return candidates[0]
            return {'state': 'idle', 'detail': 'Focus your game, then open the overlay.' if candidates
                    else 'Start a game with the NR + MFG package.', 'can_edit': False, 'can_save': False,
                    'can_mfg': False, 'values': {}, 'row': None}

    def apply(self, params):
        with self.lock:
            game = self._game(params)
            changes = validate_changes(params.get('changes'))
            t.need(game['can_mfg'] or 'multiplier' not in changes, 'This MFG package does not support live edits. NR controls remain available.')
            box = self._open(game, True)
            t.need(box is not None, 'Start this game with the current bridge before applying live changes.')
            with box:
                t.need(not params.get('pid') or params['pid'] == box.pid,
                       'The game session changed. Open the overlay again.')
                current = self._present(game, box, box.read())
                t.need(current['can_edit'], current['detail'])
                found = box.apply(changes)
                return self._present(game, box, found)

    def save(self, params):
        with self.lock:
            game = self._game(params)
            changes = validate_changes(params.get('changes'))
            if params.get('pid'):
                box = self._open(game)
                t.need(box is not None, 'The game session ended. Open the overlay again.')
                with box:
                    t.need(box.pid == params['pid'], 'The game session changed. Open the overlay again.')
                    found = box.read()
                    t.need(found['version'] >= 3 or not (set(changes) - LEGACY_KEYS),
                           'Update this game package to save the additional NR controls.')
            old = self.presets.get(game['key']) or {}
            if old.get('recipe') == game['recipe']:
                changes = validate_changes((old.get('changes') or {}) | changes)
            t.need(game['can_mfg'] or 'multiplier' not in changes, 'This MFG package does not support saved live edits.')
            record = {'schema': 1, 'row': game['row'], 'recipe': game['recipe'], 'changes': changes, 'saved_at': time.time()}
            self.state.mkdir(parents=True, exist_ok=True)
            path = self.state / (game['key'] + '.json')
            t.need(not path.is_symlink(), 'Unsafe preset path.')
            temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
            try:
                with temporary.open('x', encoding='utf-8') as output: json.dump(record, output, indent=2)
                os.replace(temporary, path)
            finally:
                if temporary.exists(): temporary.unlink()
            self.presets[game['key']] = record
            self.last_pid.pop(game['key'], None)
            self.preset_errors.pop(game['key'], None)
            self._start_watcher()
            return {'saved': True, 'detail': 'Saved in rtxForge. Applies when connected, including the current session, while rtxForge is running.'}

    def forget(self, params):
        with self.lock:
            game = self._game(params)
            path = self.state / (game['key'] + '.json')
            t.need(not path.is_symlink(), 'Unsafe preset path.')
            if path.exists(): path.unlink()
            self.presets.pop(game['key'], None)
            self.last_pid.pop(game['key'], None)
            self.preset_errors.pop(game['key'], None)
            return {'saved': False, 'detail': 'Saved preset cleared. Current live settings are unchanged.'}

    def _start_watcher(self):
        if self.presets and self.watcher is None:
            self.watcher = threading.Thread(target=self._watch, daemon=True, name='runtime-presets')
            self.watcher.start()

    def _watch(self):
        while True:
            time.sleep(2)
            with self.lock:
                records = list(self.presets.items())
                try: processes = self._processes()
                except (OSError, t.Refusal): continue
            for key, record in records:
                # Do not hash or inspect every saved game's payload at startup.
                # Only a process with its executable name can be a candidate.
                if Path((record.get('row') or {}).get('exe') or '').name.casefold() not in processes: continue
                with self.lock:
                    try:
                        game = self._game({'row': record['row']})
                        if record.get('recipe') != game['recipe']: continue
                        box = self._open(game, True)
                        if box is None: continue
                        with box:
                            if self.last_pid.get(key) == box.pid: continue
                            current = self._present(game, box, box.read())
                            if not current['can_edit']: continue
                            if record['changes'].get('multiplier', 0) > 0 and current['backend_max'] == 0: continue
                            # One attempt per process and saved revision. A new
                            # preset or game process is required after refusal.
                            self.last_pid[key] = box.pid
                            t.need(game['can_mfg'] or 'multiplier' not in record['changes'], 'MFG ownership changed')
                            box.apply(record['changes'])
                            self.preset_errors.pop(key, None)
                    except (OSError, ValueError, KeyError, t.Refusal) as error:
                        self.preset_errors[key] = str(error)


def methods(state):
    controls = Controls(state)
    return {'companion_active': controls.active, 'companion_status': controls.status, 'companion_apply': controls.apply,
            'companion_save': controls.save, 'companion_forget': controls.forget}
