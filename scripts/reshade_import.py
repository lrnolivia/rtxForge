"""Reviewed per-game ReShade packages. Archives are inspected, never executed."""
from pathlib import Path, PurePosixPath
import json
import os
import shutil
import stat
import uuid
import urllib.request
import zipfile

import discovery
import engine_bridge
import packages
import proton_prefix
import renodx_hdr as hdr
import transactions as t
from storage import storage

MAX_FILE = 128 * 1024**2
MAX_TOTAL = 512 * 1024**2
MAX_FILES = 4096
WINDOWS = os.name == 'nt'
TEXTURES = {'.png', '.jpg', '.jpeg', '.bmp', '.dds', '.tga', '.webp', '.cube', '.lut'}


def location(config, game):
    root, exe, _ = hdr._location(game)
    found = discovery.inspect_game(discovery.Game('', game['name'], str(root), game.get('source', 'Folder')))
    t.need(not found.anti_cheat and not game.get('anti_cheat'), 'ReShade is unavailable for games with detected anti-cheat.')
    engine = engine_bridge.module(config)
    t.need(not engine._running_processes_under_root(root), 'Close this game before changing ReShade.')
    return root, exe, engine


def _archive(source):
    """Bound every entry before decompressing; preserve case and include paths."""
    t.need(source.stat().st_size <= MAX_TOTAL, 'This package exceeds 512 MiB.')
    if not zipfile.is_zipfile(source):
        t.need(source.stat().st_size <= MAX_FILE, 'This file exceeds 128 MiB.')
        return {source.name: source.read_bytes()}
    result, seen, total = {}, set(), 0
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        t.need(len(entries) <= MAX_FILES, 'This package has too many files.')
        for entry in entries:
            name = entry.filename.rstrip('/')
            t.relative(name)
            t.need(not stat.S_ISLNK(entry.external_attr >> 16), 'Package links are not supported.')
            key = name.casefold()
            t.need(key not in seen, 'The package contains duplicate paths: ' + name)
            seen.add(key)
            t.need(not entry.flag_bits & 1, 'Extract this password-protected package before importing.')
            total += entry.file_size
            t.need(entry.file_size <= MAX_FILE and total <= MAX_TOTAL, 'The expanded package is too large.')
            if not entry.is_dir():
                result[name] = archive.read(entry)
    t.need(result, 'This package contains no files.')
    # Common publisher wrapper folders are not part of the game installation.
    known = {'reshade-shaders', 'shaders', 'textures', 'presets'}
    for _ in range(8):
        first = {name.split('/')[0] for name in result}
        if len(first) != 1 or any('/' not in name for name in result) or next(iter(first)).casefold() in known:
            break
        result = {name.split('/', 1)[1]: data for name, data in result.items()}
    return result


def _binary(data, arch):
    import struct
    t.need(len(data) >= 70 and data[:2] == b'MZ', 'The selected runtime or add-on is not a Windows DLL.')
    offset = struct.unpack_from('<I', data, 60)[0]
    t.need(64 <= offset <= 1024**2 and offset + 6 <= len(data) and data[offset:offset+4] == b'PE\0\0', 'Invalid Windows DLL header.')
    machine = data[offset+4:offset+6]
    return machine == (b'd\x86' if arch == 'x64' else b'L\x01')


def _is_reshade(data):
    return b'ReShade' in data or 'ReShade'.encode('utf-16le') in data


def _validate_ini(data, preset):
    text = data.decode('utf-8-sig')
    first = next((line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith((';', '#'))), '')
    # Preset globals such as Techniques and PreprocessorDefinitions precede
    # the shader sections in ordinary ReShade preset files.
    t.ini(('[__ReShadePresetGlobals__]\n' if preset and first and not first.startswith('[') else '') + text)


def _preset_ini(data):
    import re
    text = data.decode('utf-8-sig')
    return bool(re.search(r'(?im)^\s*(?:Techniques|TechniqueSorting|PreprocessorDefinitions)\s*=|^\s*\[[^\]\r\n]+\.fx\]\s*$', text))


def host_bytes(config, arch):
    """The same pinned, verified host used by automatic RenoDX installation."""
    name, digest, size = hdr.HOSTS[arch]
    cache = storage(config) / 'reshade-cache'
    request = urllib.request.Request(hdr.HOST_URL, headers={'User-Agent': 'rtxForge/1.0'})
    setup = packages.download(request, cache / hdr.HOST_ARCHIVE[0] / 'ReShade_Addon.exe',
                              expected=hdr.HOST_ARCHIVE[0], size=hdr.HOST_ARCHIVE[1])
    with zipfile.ZipFile(setup) as archive:
        entries = [entry for entry in archive.infolist() if entry.filename == name]
        t.need(len(entries) == 1 and entries[0].file_size == size, 'Unexpected runtime in the verified ReShade archive.')
        data = archive.read(entries[0])
    t.need(t.sha(data) == digest, 'ReShade runtime failed verification.')
    return data


def bridge_files(arch):
    if arch != 'x64': return {}
    folder = hdr.ROOT / 'providers/feeder-panel'
    receipt = folder / 'package.json'
    if not receipt.is_file(): return {}
    pins = t.read_json(t.safe(receipt)).get('files', {})
    if 'rtxforge-effects.addon64' not in pins: return {}
    result = {}
    for name in ('rtxforge-effects.addon64', 'rtxforge-glass.dll'):
        pin = pins.get(name, {}); path = t.safe(folder / name)
        t.need(path.is_file() and path.stat().st_size == pin.get('size') and t.digest(path) == pin.get('sha256'), 'The bundled ReShade controls changed. Repair rtxForge before importing.')
        result[name] = path.read_bytes()
    return result


def _route(engine, exe, arch):
    # Recognize custom builds too: importing shaders must preserve a paid host.
    hosts = []
    for name in (*hdr.PROXIES, hdr.HOSTS[arch][0]):
        path = t.safe(exe.parent / name)
        if path.is_file() and path.stat().st_size <= MAX_FILE:
            data = path.read_bytes()
            if _is_reshade(data) and _binary(data, arch): hosts.append(path)
    t.need(len(hosts) <= 1, 'Several ReShade runtimes are installed. Choose one loader before importing.')
    if hosts:
        host = hosts[0]
        if host.name not in hdr.PROXIES:
            managed = hdr._managed(engine, exe.parent)
            t.need(managed and arch == 'x64' and managed['current'].get('provider_id') in ('skynizz', 'y4my', 'dlss-unlocked'),
                   'This ReShade DLL has no recognized loader. Import a runtime into a supported game first.')
            return 'optiscaler', host.name, exe.parent / 'OptiScaler.ini'
        return 'existing-reshade', host.name, None
    return hdr._route(engine, exe, arch)


def prepare(config, game, source=None):
    root, exe, engine = location(config, game)
    arch = hdr.architecture(exe)
    entries = _archive(t.safe(source)) if source else {}
    route, host, opti = _route(engine, exe, arch)
    writes, runtime, presets, skipped = {}, [], [], []
    for name, data in entries.items():
        path = PurePosixPath(name); suffix = path.suffix.lower(); parts = path.parts
        low = [part.casefold() for part in parts]
        if suffix == '.dll':
            t.need(_is_reshade(data), 'The package includes a DLL that is not a ReShade runtime: ' + name)
            if _binary(data, arch): runtime.append(data)
            else: skipped.append(name + ' (other architecture)')
            continue
        if suffix in ('.addon64', '.addon32'):
            if not _binary(data, arch):
                skipped.append(name + ' (other architecture)'); continue
            target = path.name
        elif 'reshade-shaders' in low:
            index = low.index('reshade-shaders')
            target = 'reshade-shaders/' + '/'.join(parts[index+1:])
            t.need(len(parts) > index + 2 and low[index+1] in ('shaders', 'textures'), 'Unrecognized shader directory: ' + name)
            t.need(suffix in ({'.fx', '.fxh'} if low[index+1] == 'shaders' else TEXTURES), 'Unsupported shader asset: ' + name)
        elif low[0] in ('shaders', 'textures'):
            t.need(suffix in ({'.fx', '.fxh'} if low[0] == 'shaders' else TEXTURES), 'Unsupported shader asset: ' + name)
            target = 'reshade-shaders/' + name
        elif suffix in ('.fx', '.fxh'):
            target = 'reshade-shaders/Shaders/' + name
        elif suffix == '.ini':
            t.need(len(data) <= 2*1024**2, 'The preset/settings INI is too large.')
            _validate_ini(data, path.name.casefold() != 'reshade.ini')
            target = name
            if path.name.casefold() != 'reshade.ini' and _preset_ini(data): presets.append(target)
        elif suffix in ('.txt', '.md', '.pdf', '.url', '.json') or not suffix:
            # Keep supplied licenses and publisher documentation with the import.
            target = 'rtxForge-ReShade-Notices/' + name
        else:
            raise t.Refusal('Unrecognized package file: ' + name + '. Choose the ReShade files directly.')
        t.relative(target)
        t.need(target.casefold() not in {n.casefold() for n in writes}, 'Package paths collide: ' + target)
        writes[target] = data
    t.need(len(runtime) <= 1, 'This package contains several matching runtimes. Choose one DLL directly.')
    t.need(not source or runtime or any(not name.startswith('rtxForge-ReShade-Notices/') for name in writes), 'No matching ReShade files were found in this package.')
    existing_host = t.safe(exe.parent / host)
    if runtime:
        if existing_host.exists():
            t.need(t.digest(existing_host) == t.sha(runtime[0]), 'A different ReShade runtime is already installed. Restore its owning tool before replacing it.')
        else: writes[host] = runtime[0]
    elif not existing_host.exists(): writes[host] = host_bytes(config, arch)
    writes.update(bridge_files(arch))
    if not source or not runtime and not existing_host.exists():
        writes['rtxForge-ReShade-Notices/ReShade-LICENSE.txt'] = (hdr.ROOT / 'providers/renodx-hdr/ReShade-LICENSE.txt').read_bytes()
    # Preserve an installed host and its owner when only importing shaders/presets.
    config_name = next((n for n in writes if n.casefold() == 'reshade.ini'), 'ReShade.ini')
    config_path = t.safe(exe.parent / config_name)
    original = config_path.read_bytes() if config_path.exists() else b''
    text = writes.get(config_name, original).decode('utf-8-sig')
    values = t.ini(text)
    for key, value in [('EffectSearchPaths', '.\\reshade-shaders\\Shaders\\**'), ('TextureSearchPaths', '.\\reshade-shaders\\Textures\\**')]:
        current = values.get('GENERAL', key, fallback='')
        if value.casefold() not in {v.strip().casefold() for v in current.split(',')}:
            text = t.setvalue(text, 'GENERAL', key, ','.join(v for v in (current, value) if v))
    if len(presets) == 1: text = t.setvalue(text, 'GENERAL', 'PresetPath', '.\\' + presets[0].replace('/', '\\'))
    writes[config_name] = text.encode('utf-8')
    checks = {str(exe): t.digest(exe)}
    if existing_host.exists(): checks[str(existing_host)] = t.digest(existing_host)
    if opti:
        opti = t.safe(opti)
        t.need(opti.is_file() and opti.stat().st_size <= 2*1024**2, 'OptiScaler settings need repair.')
        writes[opti.name] = t.setvalue(opti.read_text(encoding='utf-8-sig'), 'Plugins', 'LoadReShade', 'true').encode()
    changes = []
    cache = storage(config) / 'extras-cache'
    listing = t.files(root)
    for name, data in writes.items():
        target = t.safe(exe.parent / t.relative(name)); rel = target.relative_to(root).as_posix()
        t.need(rel.casefold() not in listing or listing[rel.casefold()] == rel, 'Installed filename case differs: ' + rel)
        before = t.digest(target) if target.exists() else None
        after = t.sha(data)
        if before == after: continue
        settings = name in (config_name, opti.name if opti else '')
        t.need(not hdr._owned(engine, root, target) or opti and target == opti, 'A feature package owns ' + rel + '. Its file has been kept.')
        t.need(not target.exists() or settings, 'This file already exists. Restore its owning import before replacing it: ' + rel)
        cached = cache / after / 'payload'
        if not cached.exists(): t.atomic_file(cached, data, 0o600)
        checks[str(cached)] = after
        changes.append({'path': rel, 'before': before, 'after': after, 'source': str(cached)})
    t.need(changes, 'These ReShade files are already installed.')
    plan = {'game': str(root), 'name': game['name'], 'exe': game['exe'], 'kind': 'reshade-import',
            'route': route, 'host': host, 'listing': listing, 'inputs': checks, 'conflicts': [], 'changes': changes,
            'source_name': Path(source).name if source else 'Official ReShade', 'skipped': skipped,
            'notes': ['Existing ReShade builds are preserved. Preset and shader settings remain game-specific.']}
    if not WINDOWS and route == 'reshade':
        prefix = t.safe(proton_prefix.find_prefix(root, game.get('appid')))
        t.need(not proton_prefix.prefix_in_use(prefix), 'Close the Proton session before importing ReShade.')
        registry = t.safe(prefix / 'user.reg')
        plan['prefix'] = str(prefix)
        plan['inputs'][str(registry)] = t.digest(registry)
    plan['plan_sha256'] = t.sha(json.dumps(plan, sort_keys=True).encode())
    return plan


def apply(config, plan):
    _, _, engine = location(config, plan)
    with engine.mutation_lock():
        return _apply_locked(config, plan)


def _apply_locked(config, plan):
    t.check_plan(plan)
    root, exe, engine = location(config, plan)
    t.need(plan['kind'] == 'reshade-import', 'Invalid ReShade import.')
    for change in plan['changes']:
        target = t.safe(root / t.relative(change['path']))
        t.need(target.is_relative_to(exe.parent), 'Invalid ReShade destination.')
        t.need(not hdr._owned(engine, root, target) or target == exe.parent / 'OptiScaler.ini' and plan['route'] == 'optiscaler', 'A feature package now owns ' + change['path'])
    t.need(shutil.disk_usage(root).free > sum(Path(c['source']).stat().st_size for c in plan['changes']) + 64*1024**2, 'Insufficient game disk space.')
    base = storage(config) / 'extras-transactions'; base.mkdir(parents=True, exist_ok=True)
    state = base / uuid.uuid4().hex
    try:
        t.apply_transaction(plan, state)
        if plan.get('prefix'): proton_prefix.apply(Path(plan['prefix']), [Path(plan['host']).stem], state / 'proton')
    except Exception:
        if (state / 'proton' / proton_prefix.RECORD_NAME).exists(): proton_prefix.restore(state / 'proton')
        if (state / 'transaction.json').exists(): t.rollback_transaction(state, True)
        raise
    return state


def restore(config, state):
    state = t.safe(state)
    t.need(state.parent == storage(config) / 'extras-transactions', 'Invalid ReShade recovery.')
    plan = t.read_json(state / 'transaction.json')['plan']
    _, _, engine = location(config, plan)
    with engine.mutation_lock():
        return _restore_locked(config, state)


def _restore_locked(config, state):
    state = t.safe(state)
    t.need(state.parent == storage(config) / 'extras-transactions', 'Invalid ReShade recovery.')
    doc = t.read_json(state / 'transaction.json'); plan = doc['plan']
    root, exe, engine = location(config, plan)
    _, _, hdr_receipt = hdr._location(plan)
    if hdr_receipt.exists():
        record = hdr._record(root, hdr_receipt, exe.parent)
        if (exe.parent / record['addon']).is_file():
            shared = {record['host'], 'rtxforge-effects.addon64', 'rtxforge-glass.dll'}
            t.need(not any(Path(change['path']).name in shared for change in plan['changes']), 'RenoDX HDR still uses this ReShade installation. Remove HDR first; its shared runtime will be kept until this import is restored.')
    for change in plan['changes']:
        target = t.safe(root / t.relative(change['path']))
        t.need(target.is_file() and t.digest(target) == change['after'], 'ReShade files changed since import: ' + change['path'] + '. Your edits have been kept.')
        t.need(not hdr._owned(engine, root, target) or target == exe.parent / 'OptiScaler.ini' and plan['route'] == 'optiscaler', 'A feature package now owns ' + change['path'])
    if plan.get('prefix'): proton_prefix.restore(state / 'proton')
    return t.rollback_transaction(state, True)
