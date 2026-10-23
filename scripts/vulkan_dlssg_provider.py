"""Experimental BG3 Vulkan FG adapter with external, hash-guarded recovery.

This standalone adapter deliberately has no generic OptiScaler routing side effects.
Only pinned payloads and a recognized game-owned Bink original can be installed.
"""
from __future__ import annotations

import argparse
import contextlib
import contextvars
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import uuid
import zipfile

import transactions as t

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / 'providers/bg3fgvk/source.json'
ID = 'bg3fgvk-vulkan-dlssg'
PROXY = 'bink2w64.dll'
ORIGINAL = 'bink2w64_rtxforge_original.dll'
CONFIG = 'NativeMods/fgvk.ini'
NOTICES = 'NativeMods/rtxForge-bg3/'
LOGS = ('fgvk.log', 'sl.log', 'NativeMods/rtxforge-bg3-loader.log')
MAX_BACKUP = 128 * 1024**2
_selection = contextvars.ContextVar('vulkan_provider_selection', default=None)
_process_guard = contextvars.ContextVar('vulkan_process_guard', default=None)


@contextlib.contextmanager
def process_guard(check):
    token = _process_guard.set(check)
    try:
        yield
    finally:
        _process_guard.reset(token)


@contextlib.contextmanager
def profile(name, manifest):
    """Bind one exact shared-provider recipe without altering the legacy route."""
    t.need(name in ('bg3', 'rdr2'), 'Unknown Vulkan game profile')
    path = t.safe(manifest)
    token = _selection.set((name, path))
    try:
        pin()
        yield
    finally:
        _selection.reset(token)


def _pin_path():
    return _selection.get()[1] if _selection.get() else PIN


def _provider_id():
    return 'rtxforge-vulkan-native:' + _selection.get()[0] if _selection.get() else ID


def _executables():
    return ('RDR2.exe', 'PlayRDR2.exe') if _selection.get() and _selection.get()[0] == 'rdr2' else ('bg3.exe', 'bg3_dx11.exe')


def _game_name():
    return 'RDR2' if _selection.get() and _selection.get()[0] == 'rdr2' else 'BG3'


def _notices():
    return 'NativeMods/rtxForge-vulkan/' if _selection.get() else NOTICES


def _logs():
    return ('fgvk.log', 'sl.log', 'NativeMods/rtxforge-vulkan-loader.log',
            'NativeMods/MFG/RTXMFG-Universal.status.json') if _selection.get() else LOGS


def _mutable():
    return {CONFIG, 'RTX40MFG-UI.ini', 'NativeMods/MFG/RTXMFG-Universal.json'} if _selection.get() else {CONFIG}


def _destination(name):
    if name.startswith('NativeMods/') or (_selection.get() and name == 'RTX40MFG-UI.ini'):
        return name
    notices = {'LICENSE.txt': 'bg3fgvk-LICENSE.txt', 'README.md': 'UPSTREAM-README.md',
               'INSTALL.txt': 'UPSTREAM-INSTALL.txt'}
    t.need(name in notices, 'Unsupported provider destination: ' + name)
    return _notices() + notices[name]


def _identity():
    return {'id': _provider_id(), 'manifest': str(_pin_path()), 'profile': _selection.get()[0] if _selection.get() else 'legacy-bg3'}


class Cancelled(t.Refusal):
    pass


def pin():
    data = t.read_json(_pin_path())
    if _selection.get():
        name = _selection.get()[0]
        t.need(data.get('id') == 'rtxforge-vulkan-native' and data.get('experimental') is True
               and data.get('deployable') is True, 'Shared Vulkan candidate is not deployable')
        selected = data.get('profiles', {}).get(name)
        t.need(isinstance(selected, dict) and selected.get('executable') == _executables()[0],
               'Shared provider profile identity differs')
        t.need(data.get('runtime_verified') is False and data.get('default_promoted') is False,
               'Standalone candidate must retain Experimental provenance')
        data['loader'] = selected['loader']
        return data
    t.need(data.get('id') == ID and data.get('upstream', {}).get('tag') == 'v1.2.0',
           'Unsupported Vulkan provider identity')
    return data


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _digest(path):
    path = t.safe(path)
    if not path.exists():
        return None
    t.need(path.is_file(), 'Expected a regular file: ' + str(path))
    return t.digest(path)


def _pe(data):
    if len(data) < 64 or data[:2] != b'MZ':
        return False
    off = struct.unpack_from('<I', data, 60)[0]
    return 64 <= off <= len(data) - 6 and data[off:off + 6] == b'PE\0\0d\x86'


def payload(archive, loader):
    spec = pin()
    archive, loader = t.safe(archive), t.safe(loader)
    for path, expected in ((archive, spec['archive']), (loader, spec['loader']['binary'])):
        t.need(path.is_file() and path.stat().st_size == expected['size']
               and _digest(path) == expected['sha256'], 'Pinned payload size/hash mismatch: ' + str(path))
    result, seen = {}, set()
    with zipfile.ZipFile(archive) as source:
        t.need(len(source.infolist()) == len(spec['files']), 'Unexpected archive member count')
        for member in source.infolist():
            name = member.filename.replace('\\', '/')
            t.relative(name)
            t.need(name.casefold() not in seen, 'Duplicate/case-colliding archive member')
            seen.add(name.casefold())
            mode = stat.S_IFMT(member.external_attr >> 16)
            t.need(not member.is_dir() and mode in (0, stat.S_IFREG) and not member.flag_bits & 1,
                   'Archive links, directories, special or encrypted files refused')
            expected = spec['files'].get(name)
            t.need(expected and member.file_size == expected['size'], 'Unexpected archive path/size: ' + name)
            data = source.read(member)
            t.need(_hash(data) == expected['sha256'], 'Archive member hash mismatch: ' + name)
            if name.lower().endswith('.dll'):
                t.need(_pe(data), 'Payload is not an x64 Windows DLL: ' + name)
            dest = _destination(name)
            result[dest] = data
    t.need(seen == {name.casefold() for name in spec['files']}, 'Incomplete archive')
    result[PROXY] = loader.read_bytes()
    t.need(_pe(result[PROXY]), 'Loader is not an x64 DLL')
    license_path = _pin_path().parent / 'loader/LICENSE.exports.txt'
    result[_notices() + 'loader-exports-LICENSE.txt'] = license_path.read_bytes()
    t.need(_hash(result[_notices() + 'loader-exports-LICENSE.txt']) == spec['loader']['exports_notice_sha256'],
           'Loader export notice changed')
    return result


def target(game):
    root = t.safe(game)
    if (root / 'bin/bg3.exe').is_file():
        root = t.safe(root / 'bin')
    executable = _executables()[0]
    t.need(root.is_dir() and (root / executable).is_file(), 'Select the reviewed Vulkan game directory: ' + executable)
    t.executable_check(t.safe(root / executable))
    t.need(t.safe(root / 'nvngx_dlss.dll').is_file(), 'Native Vulkan DLSS-SR runtime is missing')
    return root


def running(root):
    """Refuse either BG3 renderer; fail closed for an unreadable BG3 process."""
    if _process_guard.get() is not None:
        return bool(_process_guard.get()())
    if os.name != 'nt':
        return False  # Non-Windows hosts exercise synthetic fixture directories only.
    from ctypes import wintypes as w
    class Process(ctypes.Structure):
        _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('pid', w.DWORD),
                    ('heap', ctypes.c_size_t), ('module', w.DWORD), ('threads', w.DWORD),
                    ('parent', w.DWORD), ('priority', w.LONG), ('flags', w.DWORD),
                    ('exe', w.WCHAR * 260)]
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateToolhelp32Snapshot.restype = w.HANDLE
    k.OpenProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    k.Process32FirstW.argtypes = [w.HANDLE, ctypes.POINTER(Process)]
    k.Process32NextW.argtypes = [w.HANDLE, ctypes.POINTER(Process)]
    k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    snapshot = k.CreateToolhelp32Snapshot(2, 0)
    t.need(snapshot != ctypes.c_void_p(-1).value, 'Cannot inspect running game processes')
    item = Process(); item.dwSize = ctypes.sizeof(item)
    try:
        ok = k.Process32FirstW(snapshot, ctypes.byref(item))
        while ok:
            if item.exe.casefold() in tuple(name.casefold() for name in _executables()):
                handle = k.OpenProcess(0x1000, False, item.pid)
                if not handle:
                    return True
                try:
                    path = ctypes.create_unicode_buffer(32768); size = w.DWORD(len(path))
                    if not k.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                        return True
                    if Path(path.value).parent.resolve() == root:
                        return True
                finally:
                    k.CloseHandle(handle)
            ok = k.Process32NextW(snapshot, ctypes.byref(item))
    finally:
        k.CloseHandle(snapshot)
    return False


def state_path(root, state_root):
    state_root = t.safe(state_root)
    t.need(not state_root.is_relative_to(root) and not root.is_relative_to(state_root),
           'Recovery storage must be outside the game')
    return t.safe(state_root / 'targets' / _hash(str(root).casefold().encode()))


def _names(spec):
    names = {_destination(p) for p in spec['files']}
    return names | {PROXY, ORIGINAL, CONFIG, _notices() + 'loader-exports-LICENSE.txt', *_logs()}


def _record(root, state):
    path = t.safe(state / 'baseline.json')
    if not path.exists():
        return None
    t.need(path.stat().st_size < 1024**2, 'Invalid recovery record size')
    record = t.read_json(path)
    t.need(record.get('schema') == 1 and record.get('provider_id') == _provider_id()
           and record.get('target') == str(root),
           'Recovery identity/path inventory differs')
    t.need(record.get('status') in ('applying', 'active', 'interrupted', 'restoring', 'restored'),
           'Unknown recovery state')
    recorded_names = set(record.get('originals', {}))
    changed_inventory = recorded_names != _names(pin())
    t.need(not changed_inventory or record['status'] == 'restored', 'Recovery identity/path inventory differs')
    t.need(set(record.get('installed', {})) == recorded_names - set(_logs()), 'Incomplete installed inventory')
    for name in record['originals']:
        t.relative(name)
        item = record['originals'][name]
        if item:
            t.need(isinstance(item, dict) and re.fullmatch('[0-9a-f]{64}', item.get('sha256', ''))
                   and type(item.get('mode')) is int, 'Invalid backup identity')
            blob = t.safe(state / 'objects' / item['sha256'])
            t.need(blob.is_file() and _digest(blob) == item['sha256'], 'Backup is missing or damaged: ' + name)
    t.need(all(isinstance(h, str) and re.fullmatch('[0-9a-f]{64}', h)
               for h in record['installed'].values()), 'Invalid installed digest')
    prior = record.get('prior_record_sha256')
    if prior is not None:
        t.need(isinstance(prior, str) and re.fullmatch('[0-9a-f]{64}', prior), 'Invalid prior recovery record')
        blob = t.safe(state / 'objects' / prior)
        t.need(blob.is_file() and _digest(blob) == prior, 'Prior recovery record is missing or damaged')
    if changed_inventory:
        expected = {name: (value or {}).get('sha256') for name, value in record['originals'].items()}
        t.need(_snapshot(root, recorded_names) == expected, 'Restored inventory changed before candidate replacement')
    return record


def _snapshot(root, names):
    return {name: _digest(root / name) for name in sorted(names)}


def _seal(plan):
    plan['plan_sha256'] = _hash(json.dumps(plan, sort_keys=True).encode())
    return plan


def _default_config():
    shared = _selection.get()
    sleep = 0 if shared and shared[0] == 'rdr2' else 1
    data = ('[fgvk]\nConfigVersion=2\nDLSSGFrames=1\nReflexMode=2\nReflexSleep=%d\n'
            'TagHUDLess=0\nTagUI=0\nPresentPacing=1\nMvecScaleNormalized=1\n'
            'OnAfterEvalFrames=60\nOffAfterIdleFrames=30\nKeyToggleFG=0x6A\nKeyCycleFrames=0x23\n') % sleep
    if shared:
        data += '[nr]\nEnabled=1\nWorkingScale=0.5\nWhitePoint=1\nDetailStrength=1\nColourStrength=1\n'
    return data.encode()


def plan_install(game, archive, loader, state_root, *, experimental=False, nr_on_launch=None):
    t.need(experimental, 'The BG3 Vulkan route requires explicit Experimental opt-in')
    root = target(game)
    t.need(not running(root), 'Close ' + _game_name() + ' before changing its provider')
    state = state_path(root, state_root)
    spec, data = pin(), payload(archive, loader)
    current = _record(root, state)
    active = current and current['status'] != 'restored'
    names = _names(spec)
    checks = _snapshot(root, names)
    if active:
        original = current['originals'][PROXY]
        t.need(original is not None, 'Bink backup is missing')
        bink = (state / 'objects' / original['sha256']).read_bytes()
        for name, installed in current['installed'].items():
            if name in _mutable():
                continue
            before = (current['originals'][name] or {}).get('sha256')
            t.need(checks[name] in (installed, before, None), 'Managed file changed; refusing repair: ' + name)
    else:
        bink = t.safe(root / PROXY).read_bytes()
        stock = spec['loader']['game_original']
        t.need(len(bink) == stock['size'] and _hash(bink) == stock['sha256'],
               'Unknown Bink/loader: ownership must be reviewed before replacement')
        for name in names - {PROXY, *_logs()}:
            t.need(checks[name] is None, 'Unmanaged provider file already exists: ' + name)
    for name in ('sl.interposer.dll', 'OptiScaler.ini'):
        t.need(not t.safe(root / name).exists(), 'A separate runtime requires coexistence review: ' + name)
    runtime_dir = t.safe(root / 'NativeMods/Streamline')
    if runtime_dir.exists():
        allowed = {Path(p).name.casefold() for p in spec['files'] if p.startswith('NativeMods/Streamline/')}
        t.need(runtime_dir.is_dir() and all(p.is_file() and p.name.casefold() in allowed
                                          for p in runtime_dir.iterdir()), 'Mixed private Streamline directory')
    data[ORIGINAL] = bink
    data[CONFIG] = (t.safe(root / CONFIG).read_bytes() if active and checks[CONFIG] else
                   _default_config())
    if nr_on_launch is not None and not active:
        t.need(type(nr_on_launch) is bool and _selection.get() is not None, 'Invalid Vulkan NR startup choice')
        data[CONFIG] = t.setvalue(data[CONFIG].decode(), 'nr', 'Enabled', '1' if nr_on_launch else '0').encode()
    if active:
        for name in _mutable() - {CONFIG}:
            if name in data and checks.get(name):
                data[name] = t.safe(root / name).read_bytes()
    return _seal({'schema': 1, 'recipe': _identity(), 'operation': 'repair' if active else 'install', 'target': str(root),
                  'state': str(state), 'state_root': str(t.safe(state_root)), 'checks': checks,
                  'record_before': _digest(state / 'baseline.json'),
                  'inputs': {str(t.safe(p)): _digest(p) for p in (archive, loader, _pin_path(),
                             _pin_path().parent / 'loader/LICENSE.exports.txt', root / _executables()[0], root / 'nvngx_dlss.dll')},
                  'archive': str(t.safe(archive)), 'loader': str(t.safe(loader)), 'nr_on_launch': nr_on_launch,
                  'after': {name: _hash(value) for name, value in data.items()}})


def plan_restore(game, state_root):
    root = target(game)
    t.need(not running(root), 'Close ' + _game_name() + ' before restoring its provider')
    state = state_path(root, state_root)
    record = _record(root, state)
    t.need(record is not None and record['status'] != 'restored', 'No active BG3 Vulkan install to restore')
    checks = _snapshot(root, record['originals'])
    for name, installed in record['installed'].items():
        if name in _mutable():
            continue
        before = (record['originals'][name] or {}).get('sha256')
        t.need(checks[name] in (installed, before, None), 'Restore refuses changed managed file: ' + name)
    return _seal({'schema': 1, 'recipe': _identity(), 'operation': 'restore', 'target': str(root), 'state': str(state),
                  'state_root': str(t.safe(state_root)), 'checks': checks,
                  'record_before': _digest(state / 'baseline.json'),
                  'after': {name: (value or {}).get('sha256') for name, value in record['originals'].items()}})


@contextlib.contextmanager
def _lock(state):
    state.mkdir(parents=True, exist_ok=True)
    path = t.safe(state / 'operation.lock')
    with path.open('a+b') as handle:
        if path.stat().st_size == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise t.Refusal('Another BG3 provider operation is running')
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _save(state, record):
    t.atomic_file(state / 'baseline.json', (json.dumps(record, indent=2) + '\n').encode(), 0o600)


def _cache(state, data):
    digest = _hash(data)
    path = t.safe(state / 'objects' / digest)
    if path.exists():
        t.need(_digest(path) == digest, 'Recovery object changed')
    else:
        t.atomic_file(path, data, 0o600)
    return digest


def _check(plan):
    value = dict(plan); seal = value.pop('plan_sha256', None)
    t.need(seal == _hash(json.dumps(value, sort_keys=True).encode()), 'Review integrity mismatch')
    t.need(plan.get('recipe') == _identity(), 'Reviewed provider/game profile differs')
    root = target(plan['target'])
    state = state_path(root, plan['state_root'])
    t.need(str(state) == plan['state'] and set(plan['checks']) == _names(pin()), 'Review scope differs')
    t.need(plan['operation'] in ('install', 'repair', 'restore'), 'Unknown operation')
    t.need(not running(root), 'Close ' + _game_name() + ' before changing its provider')
    t.need(_digest(state / 'baseline.json') == plan['record_before'], 'Recovery state changed after review')
    t.need(_snapshot(root, plan['checks']) == plan['checks'], 'Game files changed after review')
    for path, digest in plan.get('inputs', {}).items():
        t.need(_digest(path) == digest, 'Payload changed after review')
    return root, state


def execute(plan, *, cancelled=lambda: False):
    root, state = _check(plan)
    with _lock(state):
        root, state = _check(plan)
        record = _record(root, state)
        if plan['operation'] != 'restore':
            data = payload(plan['archive'], plan['loader'])
            if not record or record['status'] == 'restored':
                # Retain old manifests, settings and runtime-evidence references
                # when a restored candidate is replaced by another inventory.
                prior_record = _cache(state, (state / 'baseline.json').read_bytes()) if record else None
                total = sum((root / name).stat().st_size for name, digest in plan['checks'].items() if digest)
                t.need(total <= MAX_BACKUP, 'Original files exceed the recovery size bound')
                originals = {}
                for name, digest in plan['checks'].items():
                    if digest:
                        raw = t.safe(root / name).read_bytes()
                        t.need(_hash(raw) == digest, 'Original changed while backing up')
                        originals[name] = {'sha256': _cache(state, raw), 'mode': stat.S_IMODE((root / name).stat().st_mode)}
                    else:
                        originals[name] = None
                directories = {parent.relative_to(root).as_posix() for name in originals
                               for parent in (root / name).parents if parent != root and parent.is_relative_to(root)}
                record = {'schema': 1, 'provider_id': _provider_id(), 'target': str(root), 'status': 'applying',
                          'created_utc': t.now(), 'originals': originals,
                          'directories_before': sorted(d for d in directories if (root / d).exists()),
                          'directories': sorted(directories), 'observed_runtime': [], 'installed': plan['after']}
                if prior_record is not None:
                    record['prior_record_sha256'] = prior_record
            data[ORIGINAL] = (state / 'objects' / record['originals'][PROXY]['sha256']).read_bytes()
            data[CONFIG] = ((root / CONFIG).read_bytes() if plan['checks'][CONFIG] else
                            _default_config())
            if plan.get('nr_on_launch') is not None and not plan['checks'][CONFIG]:
                data[CONFIG] = t.setvalue(data[CONFIG].decode(), 'nr', 'Enabled', '1' if plan['nr_on_launch'] else '0').encode()
            for name in _mutable() - {CONFIG}:
                if name in data and plan['checks'].get(name):
                    data[name] = t.safe(root / name).read_bytes()
            t.need({name: _hash(raw) for name, raw in data.items()} == plan['after'], 'Prepared payload differs')
            record['installed'] = plan['after']
            order = [ORIGINAL, *sorted(set(data) - {ORIGINAL, PROXY}), PROXY]
        else:
            t.need(record is not None, 'Missing restore journal')
            t.need({name: (value or {}).get('sha256') for name, value in record['originals'].items()} == plan['after'],
                   'Restore destinations differ from original backups')
            data = {name: ((state / 'objects' / original['sha256']).read_bytes() if original else None)
                    for name, original in record['originals'].items()}
            for name in set(_logs()) | _mutable():
                if plan['checks'][name]:
                    raw = (root / name).read_bytes()
                    t.need(len(raw) <= MAX_BACKUP, 'Runtime diagnostics exceed the recovery bound')
                    record['observed_runtime'].append({'path': name, 'sha256': _cache(state, raw)})
            order = [PROXY, *sorted(set(data) - {PROXY, ORIGINAL}, reverse=True), ORIGINAL]
        _check(plan)
        record['status'] = 'restoring' if plan['operation'] == 'restore' else 'applying'
        _save(state, record)  # Complete verified backups and journal precede every game write.
        try:
            for name in order:
                if cancelled():
                    raise Cancelled('Operation cancelled; use restore to recover the recorded originals')
                t.need(not running(root), 'BG3 started during the operation; recovery journal retained')
                path = t.safe(root / t.relative(name))
                t.need(_digest(path) == plan['checks'][name], 'Concurrent file change: ' + name)
                raw = data[name]
                if raw is None:
                    if path.exists():
                        path.unlink()
                elif _digest(path) != _hash(raw):
                    mode = ((record['originals'][name] or {}).get('mode', 0o644)
                            if plan['operation'] == 'restore' else 0o644)
                    t.atomic_file(path, raw, mode)
                t.need(_digest(path) == plan['after'][name], 'Write verification failed: ' + name)
            record['status'] = 'restored' if plan['operation'] == 'restore' else 'active'
            record['updated_utc'] = t.now()
            _save(state, record)
        except BaseException:
            record['status'] = 'interrupted'
            _save(state, record)
            raise
        if record['status'] == 'restored':
            for name in sorted(set(record['directories']) - set(record['directories_before']), key=len, reverse=True):
                path = t.safe(root / t.relative(name))
                if path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
        return {'provider_id': _provider_id(), 'operation': plan['operation'], 'status': record['status'],
                'target': str(root), 'journal': str(state / 'baseline.json'), 'runtime_verified': False}


def diagnose(game):
    root = target(game)
    path = t.safe(root / 'fgvk.log')
    text = path.read_text(errors='replace')[-1024 * 1024:] if path.is_file() else ''
    stats = re.findall(r'FG stats: (\d+) presents -> (\d+) frames displayed \(x([\d.]+)\) status=(\d+)', text)
    return {'target': str(root), 'inputs_submitted': 'FG inputs submitted ok' in text,
            'generation_gate_on': 'DLSS-G ON' in text,
            'stats': [{'presents': int(a), 'displayed': int(b), 'ratio': float(c), 'status': int(d)}
                      for a, b, c, d in stats], 'runtime_verified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('review-install', 'install', 'repair', 'review-restore', 'restore', 'status', 'diagnose'))
    parser.add_argument('--game', required=True)
    parser.add_argument('--state-root')
    parser.add_argument('--archive'); parser.add_argument('--loader')
    parser.add_argument('--profile', choices=('bg3', 'rdr2'))
    parser.add_argument('--manifest')
    parser.add_argument('--experimental', action='store_true')
    args = parser.parse_args(argv)
    if args.state_root is None:
        args.state_root = str(Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'rtxForge' /
                              ('vulkan-native' if args.profile else 'bg3-vulkan'))
    selection_token = None
    try:
        if args.profile:
            t.need(args.manifest, 'Provide the exact shared-provider --manifest')
            selection_token = _selection.set((args.profile, t.safe(args.manifest)))
            pin()
        if args.operation == 'diagnose':
            result = diagnose(args.game)
        elif args.operation == 'status':
            root = target(args.game); record = _record(root, state_path(root, args.state_root))
            result = {'provider_id': _provider_id(), 'status': record['status'] if record else 'absent', 'runtime_verified': False}
        else:
            if args.operation in ('restore', 'review-restore'):
                plan = plan_restore(args.game, args.state_root)
            else:
                t.need(args.archive and args.loader, 'Provide the pinned --archive and built --loader')
                plan = plan_install(args.game, args.archive, args.loader, args.state_root, experimental=args.experimental)
                t.need(args.operation != 'repair' or plan['operation'] == 'repair', 'No managed installation to repair')
            result = plan if args.operation.startswith('review-') else execute(plan)
        print(json.dumps(result, indent=2))
        return 0
    except (t.Refusal, OSError, ValueError, zipfile.BadZipFile) as error:
        print(json.dumps({'status': 'refused', 'reason': str(error)}), file=sys.stderr)
        return 2
    finally:
        if selection_token is not None:
            _selection.reset(selection_token)


if __name__ == '__main__':
    raise SystemExit(main())
