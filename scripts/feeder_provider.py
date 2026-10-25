"""Windows Feeder NR: reviewed local recipes, adoption, model updates and restore.

Third-party runtime binaries and the NR model are supplied locally. This adapter
does not run their installer scripts or manufacture native OptiScaler ownership.
"""
from __future__ import annotations

import copy
import configparser
import hashlib
import json
import math
import os
from pathlib import Path
import re

import transactions as t
import ui
import operation_session
from operation_session import Session, Cancelled

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ('ReShade.ini', 'ReShadePreset.ini')
MODEL = 'nvngx_dlssnr.dll'
INSTALL_DEFAULTS = {'NRFollowInputRes': '0', 'NRResolutionScale': '0.65',
                    'NRLocalStructure': '1.0', 'NRSkinStructure': '1.0'}
# Files only a Feeder install adds. When none remain, a game update or Steam
# verification replaced the folder and the old install record is obsolete.
FEEDER_ONLY = ('dlss5-feed.addon64', 'renodx-dlss5.addon64', 'ReShade.ini')
# EA's activation wrapper hides these executables' imports until it decrypts
# them at launch. Each was reviewed as an x64 DirectX 11 game.
REVIEWED_DX11 = {'ts4_x64.exe'}
# rtxForge's in-game panel and banner hider (windows/feeder-panel), bundled by Build-FeederPanel.ps1.
PANELS = ('rtxforge-panel.addon64', 'rtxforge-quiet.addon64')
# Added by hand before rtxforge-quiet existed.
RETIRED = {'quiet-startup.addon64': 'a33e97b437a6410d01d4dafc1ae770afa9c1e37a84bdbbe87926e24b5735f0a4'}
OWNED = (*PANELS, *RETIRED)
# rtxForge preset controls and the RenoDX keys they set. RenoDX reads these
# once, when the game starts; the in-game panel writes the same keys.
TUNING = {'intensity': ('NRIntensity', 0.0, 2.0), 'passes': ('NRPasses', 1, 4),
          'work_scale': ('NRResolutionScale', 0.25, 1.0), 'preset': ('NRPreset', 0, 3),
          'style': ('NRStyle', 0, 2), 'structure': ('NRLocalStructure', 0.0, 2.0)}
_hashes = {}


def lock():
    return json.loads((ROOT / 'providers/feeder.json').read_text(encoding='utf-8'))


def digest(path, cached=False):
    path = t.safe(path)
    if not path.exists():
        return None
    t.need(path.is_file(), 'Expected a regular file: ' + str(path))
    info = path.stat()
    key = (str(path), info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if not cached or key not in _hashes:
        _hashes[key] = t.digest(path)
    return _hashes[key]


def state_dir(e, target):
    target = t.safe(target)
    return t.safe(e.STATE_ROOT / 'feeder-targets' / hashlib.sha256(str(target).casefold().encode()).hexdigest())


def state(e, target):
    path = state_dir(e, target) / 'baseline.json'
    if not path.exists():
        return None
    t.need(path.stat().st_size <= 1024 * 1024, 'Feeder install record is too large')
    record = t.read_json(t.safe(path))
    t.need(isinstance(record, dict) and record.get('schema') == 1 and record.get('provider_id') == 'feeder'
           and isinstance(record.get('target'), str) and Path(record['target']).resolve() == t.safe(target),
           'Feeder install record identity differs')
    names = {*lock()['assets'], *CONFIGS, MODEL}
    # Records made before the panel shipped do not own it yet.
    t.need(isinstance(record.get('originals'), dict) and names <= set(record['originals']) <= names | set(OWNED)
           and isinstance(record.get('installed_hashes'), dict), 'Feeder ownership record is incomplete')
    for item in record['originals'].values():
        if item is not None:
            cached_input(e, item)
    return record


def cached_input(e, item):
    t.need(isinstance(item, dict) and isinstance(item.get('sha256'), str)
           and re.fullmatch(r'[0-9a-f]{64}', item['sha256']) and isinstance(item.get('path'), str),
           'Feeder cache identity is invalid')
    expected = t.safe(e.STATE_ROOT / 'feeder-cache' / item['sha256'])
    t.need(t.safe(item['path']) == expected, 'Feeder cache path is outside its owned storage')
    return expected


def target(row):
    root = t.safe(row['game'])
    exe = t.safe(root / t.relative(row['exe']))
    t.need(exe.is_relative_to(root) and exe.is_file(), 'The selected game executable is unavailable')
    t.executable_check(exe)
    return root, exe, exe.parent


def model(path):
    path = t.safe(path)
    value = digest(path)
    spec = lock()['models'].get(value)
    t.need(spec is not None and path.stat().st_size == spec['size'],
           'Choose a verified NR model for your GPU in Settings')
    t.executable_check(path)
    return {'path': str(path), 'sha256': value, **spec}


def accepted(spec, name, installed):
    """(sha256, size) pairs a file may have. Games installed with an earlier
    recipe keep repairing and restoring; imports and new installs use the pin."""
    pairs = {(spec['assets'][name]['sha256'], spec['assets'][name]['size'])}
    if installed:
        pairs |= {(item['sha256'], item['size']) for item in spec.get('previous_assets', {}).get(name, [])}
    return pairs


def stack(directory, cached=False, installed=False):
    directory = t.safe(directory)
    spec = lock()
    for name in spec['assets']:
        path = t.safe(directory / t.relative(name))
        t.need(path.is_file() and (digest(path, cached), path.stat().st_size) in accepted(spec, name, installed),
               'Feeder files are missing or changed: ' + name)
    for name in CONFIGS:
        path = t.safe(directory / name)
        t.need(path.is_file() and path.stat().st_size <= 256 * 1024, 'Feeder settings are missing: ' + name)
        _read_ini(path)
    return spec


def configured(directory):
    values = _read_ini(directory / 'ReShade.ini')
    nr = values['RenoDX.DLSS5'] if values.has_section('RenoDX.DLSS5') else {}
    preset = _read_ini(directory / 'ReShadePreset.ini')
    techniques = preset.get('DEFAULT', 'Techniques', fallback='')
    # ReShade preset globals precede sections; ConfigParser needs a header.
    if not techniques:
        text = (directory / 'ReShadePreset.ini').read_text(encoding='utf-8-sig')
        found = re.search(r'(?m)^Techniques=(.*)$', text)
        techniques = found[1] if found else ''
    return {'nr_enabled': nr.get('NeuralUplift', '0') == '1' and 'DLSS5_Feed' in techniques,
            'passes': nr.get('NRPasses'), 'scale': nr.get('NRResolutionScale'), 'preset': nr.get('NRPreset')}


def configure_new_install(text, nr_on_launch=False):
    """Apply fresh-install tuning without changing other ReShade or depth settings."""
    for key, value in INSTALL_DEFAULTS.items():
        text = t.setvalue(text, 'RenoDX.DLSS5', key, value)
    return t.setvalue(text, 'RenoDX.DLSS5', 'NeuralUplift', '1' if nr_on_launch else '0')


def tuning(settings):
    """rtxForge preset values as [RenoDX.DLSS5] keys, clamped to RenoDX's ranges."""
    controls = settings.get('feature_controls') or {}
    t.need(isinstance(controls, dict), 'Preset controls are invalid')
    values = {}
    if type(settings.get('nr_on_launch')) is bool:
        values['NeuralUplift'] = '1' if settings['nr_on_launch'] else '0'
    for key, (ini, low, high) in TUNING.items():
        value = controls.get(key, settings.get('nr_strength') if key == 'intensity' else None)
        if type(value) not in (int, float) or not math.isfinite(value):
            continue
        value = min(max(value, low), high)
        values[ini] = str(round(value)) if type(low) is int else f'{value:.2f}'
    return values


def tuning_changes(text, settings):
    """Preset keys whose saved value differs; 1 and 1.00 are the same setting."""
    parsed, changes = t.ini(text), {}
    for key, value in tuning(settings).items():
        saved = parsed.get('RenoDX.DLSS5', key, fallback=None)
        try:
            same = saved is not None and math.isclose(float(saved), float(value), abs_tol=0.005)
        except ValueError:
            same = False
        if not same:
            changes[key] = (saved, value)
    return changes


def apply_tuning(text, settings):
    for key, (_, value) in tuning_changes(text, settings).items():
        text = t.setvalue(text, 'RenoDX.DLSS5', key, value)
    return text


def panel(e):
    """The bundled in-game panel add-ons, verified against their build receipt; empty in builds without them."""
    folder = ROOT / 'providers/feeder-panel'
    receipt = folder / 'package.json'
    if not receipt.is_file():
        return {}
    spec = t.read_json(t.safe(receipt))
    files = spec.get('files') if isinstance(spec, dict) else None
    t.need(isinstance(files, dict) and set(files) == set(PANELS)
           and all(digest(folder / name) == files[name].get('sha256') for name in PANELS),
           'The bundled rtxForge panel changed. Reinstall rtxForge')
    return {name: cache(e, folder / name) for name in PANELS}


def _read_ini(path):
    text = path.read_text(encoding='utf-8-sig')
    # ReShade presets also support unsectioned global keys.
    return t.ini(text if text.lstrip().startswith('[') else '[DEFAULT]\n' + text)


def inspect(e, row, cached=True):
    _, _, directory = target(row)
    record = state(e, directory)
    if record and record.get('adopted') and record.get('installed_hashes'):
        # An adopted setup may be any Feeder version: its record, checked below,
        # is the recipe. Installing over it replaces it with the pinned stack.
        for name in CONFIGS:
            _read_ini(t.safe(directory / name))
        try:
            nr = model(directory / MODEL)
        except t.Refusal:
            nr = record.get('nr_runtime') or {}
            t.need(nr.get('sha256') and digest(directory / MODEL, cached) == nr['sha256'], 'The adopted NR model changed')
    else:
        stack(directory, cached, installed=True)
        nr = model(directory / MODEL)
    if record:
        t.need(record.get('status') == 'active', 'The Feeder installation needs recovery')
        for name, expected in record['installed_hashes'].items():
            if name not in CONFIGS:
                t.need(digest(directory / name, cached) == expected, 'An installed Feeder file changed: ' + name)
    return {'managed': record is not None, 'nr_runtime': nr, **configured(directory)}


def eligible(e, row, existing=False, check_running=True):
    root, exe, directory = target(row)
    t.need(getattr(e, 'DESKTOP_PLATFORM', 'windows' if os.name == 'nt' else 'linux') == 'windows',
           'Feeder installation is available on Windows only in this release')
    t.need(not row.get('anti_cheat'), 'Anti-cheat detected; Feeder is unavailable for this game')
    t.need(not check_running or not e._running_processes_under_root(root), 'Close this game before changing Feeder files')
    t.need(not e.load_baseline(directory, readonly=True) and not (directory / 'OptiScaler.ini').exists(),
           'Restore the existing OptiScaler package before installing Feeder NR')
    t.need(not any((directory / name).exists() for name in ('nvngx.dll_dlssnr.dll', 'dlss5-feed-helper.addon64',
                                                         'dlss5-bridge.addon64', 'renodx-mfgunlock.addon64')),
           'Another NR or frame-generation hook is present. Restore it before using this Feeder recipe')
    if not existing:
        apis = graphics_apis(e, exe)
        t.need(apis, 'This Feeder recipe requires an x64 DirectX 11 or DirectX 12 executable')
        # Feeder's DirectX 12 session shares the game's device and refuses a second DLSS
        # runtime there; a DirectX 12 game with its own DLSS uses that DLSS route instead.
        t.need(apis != {'d3d12'} or not row.get('native_dlss'),
               'This DirectX 12 game ships DLSS; use its DLSS route instead of Feeder NR')
    return root, exe, directory


def graphics_apis(e, exe):
    """The Direct3D versions an x64 executable loads: {'d3d11'}, {'d3d12'}, both, or none.

    Normal and delay-load imports first (EA-wrapped Mass Effect LE delay-loads d3d11).
    Packed executables hide their imports until launch, so fall back to the DLL names
    the file mentions.
    """
    if exe.name.lower() in REVIEWED_DX11:
        return {'d3d11'}
    def probe():
        names = {name.lower() for name in (*e.pe_imported_dlls(exe), *delay_imported_dlls(exe))}
        found = {api for api in ('d3d11', 'd3d12') if api + '.dll' in names}
        return found or mentioned_apis(exe)
    return cached_probe('direct3d', exe, probe)


_PROBES: dict | None = None


def _probe_path():
    if os.environ.get('RTXFORGE_PROBE_CACHE') is not None:
        return Path(os.environ['RTXFORGE_PROBE_CACHE']) if os.environ['RTXFORGE_PROBE_CACHE'] else None
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or str(Path.home() / '.cache')
    return Path(base) / 'rtxForge' / 'exe-probes.json'


def cached_probe(kind, exe, compute):
    """A per-executable answer that changes only when the file does (path, size, modified time).

    Every library scan otherwise re-reads multi-gigabyte game executables to detect their
    renderer; an empty RTXFORGE_PROBE_CACHE keeps the answers in memory only."""
    global _PROBES
    exe = Path(exe)
    try:
        stat = exe.stat()
    except OSError:
        return compute()
    path = _probe_path()
    if _PROBES is None:
        _PROBES = {}
        if path and path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding='utf-8'))
                _PROBES = loaded if isinstance(loaded, dict) else {}
            except (OSError, ValueError):
                _PROBES = {}
    key = f'{kind}|{os.path.normcase(str(exe))}'
    stamp = [stat.st_size, stat.st_mtime_ns]
    hit = _PROBES.get(key)
    if isinstance(hit, dict) and hit.get('stamp') == stamp and isinstance(hit.get('value'), list):
        return set(hit['value'])
    value = set(compute())
    _PROBES[key] = {'stamp': stamp, 'value': sorted(value)}
    if path:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + '.tmp')
            temp.write_text(json.dumps(_PROBES), encoding='utf-8')
            os.replace(temp, path)
        except OSError:
            pass  # a cache miss next time, never a failed scan
    return value


def mentioned_apis(exe, limit=2 * 1024**3):
    import mmap
    try:
        with open(exe, 'rb') as file:
            if not 0 < os.fstat(file.fileno()).st_size <= limit:
                return set()
            with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
                return {api for api in ('d3d11', 'd3d12')
                        if re.search(rb'(?i)' + api.encode() + rb'\.dll', data)}
    except (OSError, ValueError):
        return set()


def directx11(e, exe):
    return 'd3d11' in graphics_apis(e, exe)


def route_note(e, row):
    """The Feeder route a fresh game gets. DirectX 12 has not been checked in game yet."""
    try:
        apis = graphics_apis(e, target(row)[1])
    except (t.Refusal, OSError, ValueError):
        apis = set()
    if apis == {'d3d12'}:
        return 'Feeder NR · DirectX 12 · not verified · NR only'
    return 'Feeder NR · DirectX 11 · NR only'


def delay_imported_dlls(exe):
    """Names in a PE32+ delay-load import directory; empty when absent or unreadable."""
    import struct
    try:
        data = Path(exe).read_bytes()
        pe = struct.unpack_from('<I', data, 0x3C)[0]
        if data[:2] != b'MZ' or data[pe:pe + 4] != b'PE\0\0':
            return set()
        sections, optional = struct.unpack_from('<H', data, pe + 6)[0], struct.unpack_from('<H', data, pe + 20)[0]
        opt = pe + 24
        if struct.unpack_from('<H', data, opt)[0] != 0x20B or optional < 112 + 14 * 8:
            return set()
        rva = struct.unpack_from('<I', data, opt + 112 + 13 * 8)[0]
        table = [struct.unpack_from('<IIII', data, opt + optional + i * 40 + 8) for i in range(sections)]

        def offset(value):
            for size, address, raw_size, raw in table:
                if address <= value < address + max(size, raw_size):
                    return value - address + raw
            raise ValueError('RVA outside sections')

        names, cursor = set(), offset(rva) if rva else None
        while cursor is not None and len(names) < 256:
            entry = data[cursor:cursor + 32]
            if len(entry) < 32 or not any(entry):
                break
            start = offset(struct.unpack_from('<I', entry, 4)[0])
            names.add(data[start:data.index(b'\0', start)].decode('ascii'))
            cursor += 32
        return names
    except (OSError, ValueError, struct.error, UnicodeDecodeError):
        return set()


def expand_rows(e, rows, selected=False):
    import skynizz_provider
    result = []
    for original in rows:
        root = Path(original['game'])
        candidates = []
        # ME Legendary Edition has one Steam entry and three actual targets.
        for index in (1, 2, 3):
            exe = root / f'Game/ME{index}/Binaries/Win64/MassEffect{index}.exe'
            if exe.is_file():
                candidates.append((exe, f"{original['name']} · Mass Effect {index}"))
        if not candidates and original.get('exe'):
            exe = root / original['exe']
            # Some collections pick a launcher. Prefer its adjacent DX11 game.
            if exe.name.lower() in ('ts4_launcher_x64.exe', 'ts4_dx9_x64.exe') and (exe.parent / 'TS4_x64.exe').is_file():
                exe = exe.parent / 'TS4_x64.exe'
            candidates = [(exe, original['name'])]
        for exe, name in candidates:
            child = copy.deepcopy(original)
            if len(candidates) > 1:
                child.update(game=str(exe.parent), exe=exe.name, collection_game=str(root), name=name)
            else:
                child['exe'] = exe.relative_to(root).as_posix()
            if (exe.parent / 'dlss5-feed.addon64').is_file():
                try:
                    found = inspect(e, child)
                    child.update(installed=True, runtime_provider='feeder', feature_mode='nr-only', profile='NR Only',
                                 feeder_managed=found['managed'], nr_enabled=found['nr_enabled'], nr_runtime=found['nr_runtime'],
                                 mfg_enabled=False, mfg_multiplier=0, installed_on='windows' if found['managed'] else None,
                                 feeder_settings={k: found[k] for k in ('passes', 'scale', 'preset')},
                                 blocked='')
                except (t.Refusal, OSError, ValueError, configparser.Error) as error:
                    child.update(blocked=str(error), feeder_detected=True)
                    try:
                        unmanaged = state(e, exe.parent) is None
                    except (t.Refusal, OSError, ValueError):
                        unmanaged = False
                    if unmanaged:
                        # Another Feeder version: Adoption takes it as found or
                        # replaces it with the pinned stack.
                        child.update(blocked='', installed=True, runtime_provider='feeder', feature_mode='nr-only',
                                     profile='NR Only', feeder_managed=False, installed_on=None, mfg_enabled=False, mfg_multiplier=0)
            elif selected or not child.get('native_dlss') or skynizz_provider.native_nr_refusal(child.get('exe'), child.get('appid')):
                try:
                    # Capability is independent of the package selected for native
                    # DLSS games. Mutation checks still run again during review.
                    eligible(e, child, check_running=False)
                    child.update(blocked='', feeder_available=True, install_provider='feeder',
                                 nr_route_note=route_note(e, child))
                except (t.Refusal, e.Stop, OSError, ValueError) as error:
                    child.pop('feeder_available', None)
                    if child.get('install_provider') == 'feeder':
                        child.pop('install_provider')
                    if selected:
                        child['blocked'] = str(error)
            result.append(child)
        if not candidates:
            result.append(original)
    return result


def cache(e, source):
    source = t.safe(source)
    value = digest(source)
    dest = t.safe(e.STATE_ROOT / 'feeder-cache' / value)
    if not dest.exists():
        t.atomic_file(dest, source.read_bytes(), 0o600)
    t.need(digest(dest) == value, 'Feeder cached file differs')
    return {'path': str(dest), 'sha256': value}


def stack_record_path(e):
    return t.safe(e.STATE_ROOT / 'feeder-stack' / 'stack.json')


def owned_stack(e):
    """The app-owned reusable stack, verified against the current recipe; None when absent.

    Its files live content-addressed in feeder-cache, so new installs never
    depend on another game's folder or on the folder they were imported from."""
    path = stack_record_path(e)
    if not path.is_file():
        return None
    t.need(path.stat().st_size <= 1024 * 1024, 'The stored Feeder stack record is too large')
    record = t.read_json(path)
    spec = lock()
    t.need(isinstance(record, dict) and record.get('schema') == 1 and record.get('provider_id') == 'feeder'
           and isinstance(record.get('files'), dict), 'The stored Feeder stack record is invalid')
    if record.get('recipe') != spec['version']:
        return None
    for name in [*spec['assets'], *CONFIGS, *([MODEL] if MODEL in record['files'] else [])]:
        item = record['files'].get(name)
        t.need(item is not None, 'The stored Feeder stack is incomplete: ' + name)
        cached = cached_input(e, item)
        t.need(digest(cached, cached=True) == item['sha256'], 'The stored Feeder stack changed: ' + name)
        if name in spec['assets']:
            t.need(item['sha256'] == spec['assets'][name]['sha256'], 'The stored Feeder stack is another recipe: ' + name)
        elif name in CONFIGS:
            t.need(cached.stat().st_size <= 256 * 1024, 'Stored Feeder settings are too large: ' + name)
            _read_ini(cached)
    return record


def import_stack(e, source):
    """Copy a verified reusable stack (and its NR model, when verified) into app-owned storage."""
    source = t.safe(source)
    spec = stack(source)
    files = {name: cache(e, source / t.relative(name)) for name in [*spec['assets'], *CONFIGS]}
    nr = None
    try:
        nr = model(source / MODEL)
        files[MODEL] = cache(e, source / MODEL)
    except (t.Refusal, OSError):
        pass
    current = owned_stack(e)
    if current is None or current['files'] != files:
        record = dict(schema=1, provider_id='feeder', recipe=spec['version'], imported_from=str(source),
                      imported_utc=t.now(), files=files, nr_version=nr['version'] if nr else None)
        t.atomic_file(stack_record_path(e), (json.dumps(record, indent=2) + '\n').encode(), 0o600)
    return owned_stack(e)


def stack_files(e, settings):
    """Files for a fresh install: the chosen folder (imported again when it verifies), else the owned copy."""
    source = settings.get('feeder_source')
    if source and Path(source).is_dir():
        try:
            return import_stack(e, source)['files']
        except (t.Refusal, OSError, ValueError, configparser.Error):
            if owned_stack(e) is None:
                raise
    owned = owned_stack(e)
    t.need(owned is not None, 'Import a verified Feeder stack in Packages first')
    return owned['files']


def originals_root(e):
    return t.safe(e.STATE_ROOT / 'feeder-originals')


def _backup_manifest(path):
    if not (path.is_file() and path.stat().st_size <= 1024 * 1024):
        return None
    try:
        doc = t.read_json(t.safe(path))
    except (ValueError, OSError, t.Refusal):
        return None
    return doc if isinstance(doc, dict) and doc.get('schema') == 1 and isinstance(doc.get('target'), str) else None


def import_backups(e, folder):
    """Copy original Feeder manifests and their verified originals into app-owned storage.

    Copies are keyed by the manifest's content, so a later or different
    manifest for the same game never replaces one already kept."""
    folder = t.safe(folder)
    imported = 0
    for path in [folder / 'manifest.json', *sorted(folder.glob('*/manifest.json'))[:128]]:
        doc = _backup_manifest(path)
        entries = doc.get('files') if doc else None
        if not isinstance(entries, list) or len(entries) > 256:
            continue
        data = path.read_bytes()
        dest = t.safe(originals_root(e) / t.sha(data))
        for entry in entries:
            if not (isinstance(entry, dict) and isinstance(entry.get('path'), str) and isinstance(entry.get('before'), str)):
                continue
            try:
                name = t.relative(entry['path'])
                original = t.safe(path.parent / 'originals' / name)
                kept = t.safe(dest / 'originals' / name)
            except t.Refusal:
                continue
            if digest(kept) != entry['before'] and original.is_file() and digest(original) == entry['before']:
                t.atomic_file(kept, original.read_bytes(), 0o600)
        if digest(dest / 'manifest.json') != t.sha(data):
            t.atomic_file(dest / 'manifest.json', data, 0o600)
        imported += 1
    return imported


def original_manifest(settings, directory, e=None):
    folder = settings.get('feeder_backups', '')
    roots = []
    if e is not None:
        if folder and Path(folder).is_dir():
            import_backups(e, folder)
        if originals_root(e).is_dir():
            roots.append((originals_root(e), None))
    if folder and Path(folder).is_dir():
        roots.append((t.safe(folder), 128))
    t.need(roots, 'Choose the original Feeder backups folder in Packages to recognize this installation')
    # The owned copy comes first, so its originals are the ones used.
    found = {}
    for root, limit in roots:
        listed = sorted(root.glob('*/manifest.json'))
        for path in [root / 'manifest.json', *(listed[:limit] if limit else listed)]:
            doc = _backup_manifest(path)
            if doc and Path(doc['target']).resolve() == directory:
                found.setdefault(t.digest(path), (path, doc))
    found = list(found.values())
    t.need(len(found) == 1, 'A unique original Feeder backup for this executable is required')
    path, doc = found[0]
    t.need(doc.get('state') == 'installed-unverified', 'This manual Feeder backup is not an installed recipe')
    entries = doc.get('files', [])
    t.need(isinstance(entries, list) and len(entries) <= 256
           and all(isinstance(entry, dict) and isinstance(entry.get('path'), str) for entry in entries),
           'Original Feeder backup file list is invalid')
    t.need(len({entry['path'].casefold() for entry in entries}) == len(entries),
           'Original Feeder backup paths are duplicated or too numerous')
    for entry in entries:
        t.relative(entry['path'])
    return path, {entry['path']: entry for entry in entries}


def _checks(directory, names):
    return {name: digest(directory / t.relative(name)) for name in names}


def _check(e, plan):
    eligible(e, plan['row'], existing=plan['existing'])
    directory = Path(plan['target'])
    t.need(_checks(directory, plan['checks']) == plan['checks'], 'Feeder files changed since review; review again')
    t.need(digest(state_dir(e, directory) / 'baseline.json') == plan['baseline_before'],
           'Feeder install record changed since review')
    for item in plan['inputs'].values():
        t.need(digest(cached_input(e, item)) == item['sha256'], 'Feeder source or original backup changed since review')


def prepare(config, rows, mode, operation, settings, e):
    t.need(mode == 'nr-only' or operation == 'uninstall', 'Feeder provides NR Only. Frame generation is not available for this route')
    t.need(operation in ('install', 'repair', 'uninstall', 'reset', 'apply'), 'Unsupported Feeder operation')
    ready, blocked, plans, seen = [], [], [], set()
    base_settings = dict(settings)
    for index, row in enumerate(rows):
        ui.progress('Checking Feeder files', game=row['name'], checked=index, total=len(rows))
        try:
            import overlay_settings
            import overlay_policy
            settings = (base_settings | overlay_settings.effective(base_settings, row['game'])
                        if overlay_policy.explicit(base_settings) or row['game'] in base_settings.get('game_overlay_settings', {}) else base_settings)
            _, _, directory = target(row)
            t.need(str(directory).casefold() not in seen, 'The same Feeder executable was selected twice')
            seen.add(str(directory).casefold())
            current = state(e, directory)
            existing = (directory / 'dlss5-feed.addon64').is_file()
            if current and current.get('status') == 'restored':
                current = None
            elif current and operation == 'install' and not any((directory / name).exists() for name in FEEDER_ONLY):
                # The game folder was replaced; its pre-Feeder originals are now
                # the current files, so install again from a fresh record.
                current = None
            eligible(e, row, existing)
            spec = stack(directory, installed=True) if existing else lock()
            names = list(spec['assets']) + [*CONFIGS, MODEL]
            inputs, writes = {}, {}
            baseline = copy.deepcopy(current)
            if operation in ('uninstall', 'reset', 'repair', 'apply'):
                t.need(current is not None, 'Recognize this Feeder installation with its original backups first')
            if current or existing:
                found = inspect(e, row, cached=False)
            if operation == 'uninstall':
                for name, original in current['originals'].items():
                    if original is not None:
                        inputs['original:' + name] = original
                    writes[name] = original
                summary = 'Restore the original files recorded for this Feeder setup.'
            elif operation == 'reset':
                t.need(False, 'Edit Feeder NR settings in its ReShade panel. Your saved tuning has been kept')
            elif operation == 'apply':
                # The in-game panel saves to the same keys; RenoDX loads them at launch.
                t.need(existing, 'Repair this Feeder installation before applying presets')
                source_ini = (directory / 'ReShade.ini').read_bytes().decode('utf-8-sig')
                changes = tuning_changes(source_ini, settings)
                t.need(changes, 'This game already uses these settings')
                changed = apply_tuning(source_ini, settings)
                dest = t.safe(e.STATE_ROOT / 'feeder-cache' / t.sha(changed.encode()))
                if not dest.exists(): t.atomic_file(dest, changed.encode(), 0o600)
                inputs['preset-ini'] = writes['ReShade.ini'] = {'path': str(dest), 'sha256': t.sha(changed.encode())}
                summary = 'Save presets to ReShade.ini: ' + ', '.join(
                    f"{key} {saved or 'unset'} → {value}" for key, (saved, value) in changes.items()) + \
                    '. They apply the next time the game starts.'
            else:
                if not existing:
                    t.need(not any((directory / name).exists() for name in (*t.PROXIES, 'ReShade.ini', 'renodx-dlss5.addon64')),
                           'Other graphics mods are present. Restore them before installing Feeder NR')
                    files = stack_files(e, settings)
                    for name in [*spec['assets'], *CONFIGS]:
                        inputs[name] = writes[name] = files[name]
                if baseline is None:
                    originals = {}
                    manifest = None
                    if existing:
                        manifest, old = original_manifest(settings, directory, e)
                        inputs['manual-manifest'] = cache(e, manifest)
                    for name in names:
                        if existing:
                            t.need(name in old, 'The original backup does not cover: ' + name)
                            installed = old[name].get('after')
                            if name in spec['assets']:
                                expected = {sha for sha, _ in accepted(spec, name, installed=True)}
                                if name == 'nvngx_dlss.dll':
                                    # Earlier manual installs were subsequently
                                    # upgraded to the verified production SR.
                                    expected.add('378262f4ba429e6199ce25d6f9275734f354c3b017f3f096d8cea1af468312ff')
                                t.need(installed in expected, 'The manual backup describes another Feeder recipe: ' + name)
                            elif name == MODEL:
                                t.need(installed in spec['models'], 'The manual backup has an unrecognized NR model')
                            prior = old[name].get('before')
                            if prior is not None:
                                original = t.safe(manifest.parent / 'originals' / t.relative(name))
                                t.need(digest(original) == prior, 'An original Feeder backup is missing or changed: ' + name)
                                originals[name] = cache(e, original)
                                inputs['original:' + name] = originals[name]
                            else:
                                originals[name] = None
                        else:
                            originals[name] = cache(e, directory / name) if (directory / name).exists() else None
                            if originals[name]:
                                inputs['original:' + name] = originals[name]
                    baseline = dict(schema=1, provider_id='feeder', status='active', target=str(directory),
                                    game=row['game'], exe=row['exe'], name=row['name'], originals=originals,
                                    adopted=existing, original_manifest=str(manifest) if manifest else None,
                                    created_utc=t.now(), installed_hashes={})
                desired = settings.get('nr_runtime') if operation == 'install' else None
                if desired or current or existing:
                    source = (Path(desired) if desired else Path(current['nr_runtime']['cache']['path']) if current else
                              directory / MODEL)
                else:
                    t.need(MODEL in files, 'Choose a verified NR model for your GPU in Settings')
                    source = Path(files[MODEL]['path'])
                selected = model(source)
                inputs[MODEL] = cache(e, source)
                if digest(directory / MODEL) != selected['sha256']:
                    if existing:
                        prior_model = cache(e, directory / MODEL)
                        inputs['previous-model'] = prior_model
                        baseline.setdefault('previous_models', []).append(prior_model)
                    writes[MODEL] = inputs[MODEL]
                baseline['nr_runtime'] = {**selected, 'cache': inputs[MODEL]}
                baseline['updated_utc'] = t.now()
                old_version = found['nr_runtime']['version'] if existing else None
                summary = ('Recognize the existing Feeder NR setup.' if existing and current is None else
                           'Update Feeder NR.' if existing else 'Install Feeder NR.')
                if old_version != selected['version']:
                    summary += f" NR runtime: {old_version or 'not installed'} → {selected['version']}."
                summary += ' Keep your saved tuning. Frame generation is unavailable.' if existing else ' Frame generation is unavailable.'
            if operation == 'install':
                # NR startup is an explicit install choice, independent of MFG.
                source_ini = (Path(writes['ReShade.ini']['path']).read_bytes().decode('utf-8-sig')
                              if 'ReShade.ini' in writes else (directory / 'ReShade.ini').read_bytes().decode('utf-8-sig'))
                desired_startup = '1' if settings.get('nr_on_launch', False) else '0'
                if not existing:
                    changed = configure_new_install(source_ini, settings.get('nr_on_launch', False))
                else:
                    changed = source_ini if t.ini(source_ini).get('RenoDX.DLSS5', 'NeuralUplift', fallback='0') == desired_startup else t.setvalue(source_ini, 'RenoDX.DLSS5', 'NeuralUplift', desired_startup)
                if settings.get('apply_requested_presets') and not existing:
                    # Existing setups keep their tuning; Presets › Apply changes it.
                    changed = apply_tuning(changed, settings)
                dest =t.safe(e.STATE_ROOT / 'feeder-cache' / t.sha(changed.encode()))
                if not dest.exists(): t.atomic_file(dest, changed.encode(), 0o600)
                if changed != source_ini or 'ReShade.ini' in writes:
                    inputs['startup-ini'] = writes['ReShade.ini'] = {'path': str(dest), 'sha256': t.sha(changed.encode())}
                summary += ' NR starts ' + ('on.' if settings.get('nr_on_launch', False) else 'off; enable it from the overlay.')
            if operation in ('install', 'repair'):
                import overlay_policy
                if overlay_policy.explicit(settings):
                    source_ui = (Path(writes['ReShade.ini']['path']) if 'ReShade.ini' in writes else directory / 'ReShade.ini').read_text(encoding='utf-8-sig')
                    updated_ui = overlay_policy.reshade(source_ui, settings)
                    # The rtxForge panel hides ReShade's startup banner unless welcomes are on.
                    quiet = '0' if overlay_policy.options(settings)['reshade_intro'] else '1'
                    if t.ini(updated_ui).get('rtxForge.UI', 'QuietStartup', fallback='1') != quiet:
                        updated_ui = t.setvalue(updated_ui, 'rtxForge.UI', 'QuietStartup', quiet)
                    if updated_ui != source_ui:
                        ui_file = t.safe(e.STATE_ROOT / 'feeder-cache' / t.sha(updated_ui.encode()))
                        if not ui_file.exists(): t.atomic_file(ui_file, updated_ui.encode(), 0o600)
                        inputs['ui-ini'] = writes['ReShade.ini'] = {'path': str(ui_file), 'sha256': t.sha(updated_ui.encode())}
                    summary += ' Menu access and welcome messages follow Overlay settings.'
                bundled = {name: item for name, item in panel(e).items() if digest(directory / name) != item['sha256']}
                for name, item in bundled.items():
                    inputs[name] = writes[name] = item
                if bundled:
                    summary += ' Add the rtxForge in-game panel.'
                for name, retired in RETIRED.items():
                    if digest(directory / name) == retired:
                        writes[name] = None
                for name in OWNED:
                    # Restore puts back whatever was here before rtxForge first owned it.
                    if name in writes and name not in baseline['originals']:
                        original = cache(e, directory / name) if (directory / name).exists() else None
                        baseline['originals'][name] = original
                        if original:
                            inputs['original:' + name] = original
            checks = _checks(directory, [*names, *(name for name in writes if name not in names)])
            plan = dict(row=dict(row), target=str(directory), existing=existing, checks=checks,
                        baseline_before=digest(state_dir(e, directory) / 'baseline.json'), baseline=baseline,
                        inputs=inputs, writes=writes, operation=operation)
            _check(e, plan)
            plans.append(plan)
            detail = json.dumps({'target': str(directory), 'operation': operation,
                                 'recipe': spec['version'], 'model': (baseline or {}).get('nr_runtime'),
                                 'original_manifest': (baseline or {}).get('original_manifest'),
                                 'writes': {name: item['sha256'] if item else None for name, item in writes.items()},
                                 'preserved_settings': list(CONFIGS) if existing and operation != 'uninstall' else []}, indent=2)
            ready.append({'name': row['name'], 'game': row['game'], 'summary': summary, 'detail': detail})
        except (t.Refusal, e.Stop, OSError, ValueError, configparser.Error) as error:
            blocked.append({'name': row['name'], 'game': row['game'], 'reason': str(error)})
    return dict(kind='feeder', operation=operation, title='Feeder NR', rows=ready, blocked=blocked, plans=plans, engine=e)


def execute(review):
    e, results = review['engine'], []
    t.need(review['plans'], 'No Feeder changes were reviewed')
    cancel = review.get('cancel_event')
    with e.mutation_lock():
        # Reject drift anywhere in the reviewed selection before the first write.
        for plan in review['plans']:
            _check(e, plan)
        session = Session(e.STATE_ROOT / 'desktop-operations')
        try:
            for index, plan in enumerate(review['plans'], 1):
                if cancel is not None and cancel.is_set():
                    raise Cancelled('Changes undone.')
                directory = Path(plan['target'])
                _check(e, plan)
                ui.progress('Backing up Feeder files', game=plan['row']['name'], current=index, total=len(review['plans']))
                checkpoint = session.capture([directory / name for name in plan['writes']] + [state_dir(e, directory)], label=plan['row']['name'])
                try:
                    # A durable baseline precedes any model replacement.
                    if plan['operation'] != 'uninstall':
                        baseline = copy.deepcopy(plan['baseline'])
                        baseline['status'] = 'preparing'
                        t.atomic_file(state_dir(e, directory) / 'baseline.json', (json.dumps(baseline, indent=2) + '\n').encode(), 0o600)
                    for name, item in plan['writes'].items():
                        if cancel is not None and cancel.is_set():
                            raise Cancelled('Changes undone.')
                        path = t.safe(directory / t.relative(name))
                        t.need(digest(path) == plan['checks'][name], 'Feeder target changed during installation')
                        if item is None:
                            if path.exists():
                                path.unlink()
                        else:
                            data = Path(item['path']).read_bytes()
                            t.need(t.sha(data) == item['sha256'], 'Feeder input changed during installation')
                            t.atomic_file(path, data, path.stat().st_mode & 0o777 if path.exists() else 0o644)
                        t.need(digest(path) == (item['sha256'] if item else None), 'Feeder write verification failed')
                    if plan['operation'] == 'uninstall':
                        baseline = copy.deepcopy(plan['baseline'])
                        baseline['status'] = 'restored'
                    else:
                        baseline = copy.deepcopy(plan['baseline'])
                        baseline['status'] = 'active'
                        baseline['installed_hashes'] = _checks(directory, plan['checks'])
                        stack(directory, installed=True)
                    t.atomic_file(state_dir(e, directory) / 'baseline.json', (json.dumps(baseline, indent=2) + '\n').encode(), 0o600)
                    session.seal(checkpoint)
                    results.append({'name': plan['row']['name'], 'game': plan['row']['game'], 'status': 'complete'})
                except BaseException:
                    session.seal(checkpoint)
                    # Keep this checkpoint recoverable until undo is verified.
                    # A failed restore must not disappear as a closed session.
                    session.checkpoints[-1]['sealed'] = False
                    session.save()
                    t.need(not e._running_processes_under_root(Path(plan['row']['game'])),
                           'Close this game before Feeder recovery. Backups are retained at ' + str(session.root))
                    session.undo(checkpoint)
                    session.seal(checkpoint)
                    raise
            if cancel is not None and cancel.is_set():
                raise Cancelled('Changes undone.')
            session.complete()
        except Cancelled:
            t.need(not any(e._running_processes_under_root(Path(p['row']['game'])) for p in review['plans']),
                   'Close running games before Feeder recovery. Backups are retained at ' + str(session.root))
            session.rollback()
            raise
        except BaseException as error:
            if session.interrupted() is None:
                session.close('failed')
            e.save_json_atomic(session.root / 'result.json', {'results': results, 'error': str(error),
                               'recovery_required': session.interrupted() is not None})
            if isinstance(error, Exception):
                raise t.Refusal(f'Feeder stopped after {len(results)} completed game(s). '
                                f'Completed games keep their changes. Recovery copies: {session.root}. {error}') from error
            raise
        finally:
            operation_session.LIVE.discard(str(session.root))
    path = e.STATE_ROOT / ('desktop-feeder-' + e.now_stamp() + '.json')
    e.save_json_atomic(path, {'results': results})
    return str(path)


def parse_logs(feed, reshade):
    """Keep model/evaluation evidence distinct from a feed counter or NR request."""
    versions = re.findall(r'NGX runtime nvngx_dlssnr\.dll:\s*([\d.]+)', feed)
    verdicts = re.findall(r'NR-VERDICT\s+v\d+\s+state=(\w+)[^\n]*', reshade)
    evaluations = re.findall(r'feature 18 evaluation succeeded\s*\(count=(\d+)', reshade, re.I)
    depths = [float(value) for value in re.findall(r'Depth probe[^\n]*variance\s+([\d.eE+-]+)', feed)]
    motion = [float(value) for value in re.findall(r'MV probe[^\n]*max\s+([\d.eE+-]+)\s*px', feed)]
    return {'logged_nr_version': versions[-1] if versions else None,
            'feature18_created': bool(re.search(r'feature 18 created via the signed snippet', reshade, re.I)),
            'feature18_evaluated': bool(evaluations), 'last_evaluation_count': int(evaluations[-1]) if evaluations else 0,
            'last_verdict': verdicts[-1] if verdicts else None,
            'nonflat_depth_observed': any(value > 1e-8 for value in depths),
            'moving_vectors_observed': any(value > 0.01 for value in motion)}


def diagnose(row):
    from runtime_diagnostics import read_regular
    _, _, directory = target(row)
    nr = model(directory / MODEL)
    saved = configured(directory)
    report = {'name': row['name'], 'provider': 'feeder', 'settings': saved, 'files': {MODEL: nr},
              'observations': ['Feeder NR is installed. Saved NR is ' + ('enabled.' if saved['nr_enabled'] else 'disabled.'),
                               'NR runtime: ' + nr['version'] + '.', 'Frame generation is unavailable for this route.'],
              'warnings': [], 'visual_result': 'Not established by file or log inspection'}
    logs, times = {}, {}
    for name in ('dlss5-feed.log', 'ReShade.log'):
        try:
            data, info = read_regular(directory / name, tail=True)
            logs[name] = data.decode('utf-8', errors='replace')
            times[name] = info.st_mtime_ns
        except (OSError, ValueError):
            logs[name] = ''
            times[name] = 0
    evidence = parse_logs(logs['dlss5-feed.log'], logs['ReShade.log'])
    latest_change = max((directory / name).stat().st_mtime_ns for name in (*CONFIGS, MODEL))
    evidence['predates_current_files'] = any(value < latest_change for value in times.values())
    evidence['matches_current_model_version'] = evidence['logged_nr_version'] == nr['version']
    report['log'] = evidence
    current = not evidence['predates_current_files'] and evidence['matches_current_model_version']
    if current and evidence['feature18_created'] and evidence['feature18_evaluated']:
        report['observations'].append('The captured run created and evaluated the NR model. This does not establish visual correctness.')
        report['observations'].append('Last NR state in that run: ' + (evidence['last_verdict'] or 'Not reported') + '.')
    else:
        report['observations'].append('No matching NR evaluation is confirmed for the current files. Run the game, then refresh.')
    if current and evidence['nonflat_depth_observed'] and evidence['moving_vectors_observed']:
        report['observations'].append('The captured run includes nonflat depth and moving motion vectors.')
    else:
        report['observations'].append('Depth and motion-vector quality still need a moving-scene check.')
    return report
