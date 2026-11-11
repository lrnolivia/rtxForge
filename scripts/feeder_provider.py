"""Windows Feeder NR: reviewed local recipes, adoption, model updates and restore.

Pinned runtime inputs are downloaded into app-owned storage automatically. This
adapter never runs upstream installers or manufactures OptiScaler ownership.
"""
from __future__ import annotations

import atexit
import contextlib
import copy
import configparser
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time

import file_stamps
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
FEEDER_HOOKS = ('dlss5-feed.addon64', 'dlss5-feed.addon32', 'dlss5-feed-helper.addon64')
FEEDER_ONLY = (*FEEDER_HOOKS, 'renodx-dlss5.addon64', 'ReShade.ini')
# EA's activation wrapper hides these executables' imports until it decrypts
# them at launch. Each was reviewed as an x64 DirectX 11 game.
REVIEWED_DX11 = {'ts4_x64.exe'}
# rtxForge's in-game panel and banner hider (windows/feeder-panel), bundled by Build-FeederPanel.ps1.
PANELS = ('rtxforge-panel.addon64', 'rtxforge-quiet.addon64')
OPTIONAL_PANELS = ('rtxforge-glass.dll', 'rtxforge-effects.addon64')
# Added by hand before rtxforge-quiet existed.
RETIRED = {'quiet-startup.addon64': 'a33e97b437a6410d01d4dafc1ae770afa9c1e37a84bdbbe87926e24b5735f0a4'}
OWNED = (*PANELS, *OPTIONAL_PANELS, *RETIRED)
# The DLSS Super Resolution DLL earlier manual Feeder installs shipped, later
# upgraded to the pinned production SR.
MANUAL_SR = '378262f4ba429e6199ce25d6f9275734f354c3b017f3f096d8cea1af468312ff'
# Verified Microsoft Windows Image Helper shipped with games. DbgHelp can
# also be a proxy name, so only these exact stock bytes are exempted.
STOCK_LIBRARIES = {'dbghelp.dll': {'abd6a38e9d73b0ed73372e80819eca9134534c17722ced453e5e1cbffef03ec2'}}
# rtxForge preset controls and the RenoDX keys they set. RenoDX reads these
# once, when the game starts; the in-game panel writes the same keys.
TUNING = {'intensity': ('NRIntensity', 0.0, 2.0), 'passes': ('NRPasses', 1, 4),
          # RenoDX clamps NRResolutionScale to 0.33-1.0 when it loads.
          'work_scale': ('NRResolutionScale', 0.33, 1.0), 'preset': ('NRPreset', 0, 3),
          'style': ('NRStyle', 0, 2), 'structure': ('NRLocalStructure', 0.0, 2.0)}
# Per-pass tuning that presets carry (passes 2-3; pass 4 is set in game).
for _pass in (2, 3):
    TUNING |= {f'pass{_pass}_inherit': (f'NRPass{_pass}FollowPass1', 0, 1),
               f'pass{_pass}_style': (f'NRPass{_pass}Style', 0, 2),
               f'pass{_pass}_strength': (f'NRPass{_pass}Intensity', 0.0, 2.0),
               f'pass{_pass}_structure': (f'NRPass{_pass}Structure', 0.0, 2.0),
               f'pass{_pass}_tone': (f'NRPass{_pass}LocalTone', 0.0, 2.0),
               f'pass{_pass}_skin': (f'NRPass{_pass}Skin', -1.0, 1.0)}
# Reviews share work, on the reviewing thread only: each file stamp (size, mtime, ctime) is hashed
# once across reviews, so games checked one at a time cost no more than one batch, and one process
# inventory serves every game in a review. Execution never runs inside a review, so it always checks afresh.
_review = threading.local()
_review_hashes = {}
# Reviews checked one game after another share a process inventory for a few seconds; executing
# always takes its own.
_review_inventory = [0.0, None]


def _inventory(e):
    shared = getattr(e._running_processes_under_root, 'snapshot', None)
    if shared is None:
        return None
    taken, running = _review_inventory
    if running is None or time.monotonic() - taken > 5:
        _review_inventory[:] = [time.monotonic(), shared()]
    return _review_inventory[1]


@contextlib.contextmanager
def review_session(e):
    if len(_review_hashes) > 50000:
        _review_hashes.clear()
    _review.hashes, _review.running = _review_hashes, _inventory(e)
    try:
        yield
    finally:
        _review.hashes = _review.running = None


def running_under(e, root):
    running = getattr(_review, 'running', None)
    return (running or e._running_processes_under_root)(root)


def lock():
    return json.loads((ROOT / 'providers/feeder.json').read_text(encoding='utf-8'))


def digest(path, cached=False):
    path = t.safe(path)
    if not path.exists():
        return None
    t.need(path.is_file(), 'Expected a regular file: ' + str(path))
    info = path.stat()
    key = (str(path), info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    session = getattr(_review, 'hashes', None)
    if session is not None and key in session:
        return session[key]
    # cached: status and inspection trust an unchanged stamp, even from an earlier run.
    # Otherwise the bytes are read now (and the result serves later cached reads).
    value = file_stamps.digest(path) if cached else file_stamps.Operation().digest(path)
    if session is not None:
        session[key] = value
    return value


def has_feeder_hook(directory):
    """Recognize the Feeder hook files without treating RenoDX alone as Feeder."""
    return any((directory / name).is_file() for name in FEEDER_HOOKS)


def state_dir(e, target):
    target = t.safe(target)
    return t.safe(e.STATE_ROOT / 'feeder-targets' / hashlib.sha256(str(target).casefold().encode()).hexdigest())


def state(e, target):
    path = state_dir(e, target) / 'baseline.json'
    if not path.exists():
        return None
    t.need(path.stat().st_size <= 1024 * 1024, 'Feeder install record is too large')
    record = t.read_json(t.safe(path))
    if isinstance(record, dict) and record.get('legacy_recipe'):
        import feeder_legacy
        return feeder_legacy.validate_state(e, target, record)
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
    import feeder_legacy
    feeder_legacy.machine(exe)
    return root, exe, exe.parent


def model(path, cached=False):
    path = t.safe(path)
    value = digest(path, cached)
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


def stack(directory, cached=False, installed=False, drift=None):
    """The recipe when every asset is a published build. With a drift list, an
    owned install's changed assets are listed there for Repair instead of refused."""
    directory = t.safe(directory)
    spec = lock()
    for name in spec['assets']:
        path = t.safe(directory / t.relative(name))
        ok = path.is_file() and (digest(path, cached), path.stat().st_size) in accepted(spec, name, installed)
        if not ok and drift is not None:
            drift.append({'name': name, 'fix': 'restore'})
            continue
        t.need(ok, 'Feeder files are missing or changed: ' + name)
    for name in CONFIGS:
        path = t.safe(directory / name)
        t.need(path.is_file() and path.stat().st_size <= 256 * 1024, 'Feeder settings are missing: ' + name)
        _read_ini(path)
    return spec


def configured(directory, preset_directory=None):
    preset_directory = preset_directory or directory
    values = _read_ini(directory / 'ReShade.ini')
    nr = values['RenoDX.DLSS5'] if values.has_section('RenoDX.DLSS5') else {}
    preset = _read_ini(preset_directory / 'ReShadePreset.ini')
    techniques = preset.get('DEFAULT', 'Techniques', fallback='')
    # ReShade preset globals precede sections; ConfigParser needs a header.
    if not techniques:
        text = (preset_directory / 'ReShadePreset.ini').read_text(encoding='utf-8-sig')
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
    t.need(isinstance(files, dict) and set(PANELS) <= set(files) <= set(PANELS + OPTIONAL_PANELS)
           and all(isinstance(item, dict) and digest(folder / name) == item.get('sha256') for name, item in files.items()),
           'The bundled rtxForge panel changed. Reinstall rtxForge')
    t.need(('rtxforge-glass.dll' in files) == bool(spec.get('glass_revision')), 'Glass overlay receipt is incomplete')
    return {name: cache(e, folder / name) for name in files}


def _read_ini(path):
    text = path.read_text(encoding='utf-8-sig')
    # ReShade presets also support unsectioned global keys.
    return t.ini(text if text.lstrip().startswith('[') else '[DEFAULT]\n' + text)


class Drift(t.Refusal):
    """Files of an owned Feeder install differ from its record; Repair fixes each one.

    files: [{'name', 'fix'}], fix 'record' when the file on disk is a published
    rtxForge build the record has not caught up with, 'restore' otherwise."""

    def __init__(self, files):
        self.files = files
        super().__init__('An installed Feeder file changed: ' + ', '.join(item['name'] for item in files))


def drift_summary(files):
    """A calm one-line status for changed files, naming what Repair will do."""
    names = ', '.join(item['name'] for item in files)
    if all(item['fix'] == 'record' for item in files):
        return f'{names} {"is" if len(files) == 1 else "are"} a newer rtxForge build than this install records. Repair records it; nothing is replaced.'
    count = f'{len(files)} Feeder files' if len(files) > 1 else 'A Feeder file'
    return f'{count} changed ({names}). Repair puts back rtxForge\'s copy; your tuning is kept.'


def _published(e, spec, name, path, actual):
    """True when the bytes at path are one of rtxForge's own published builds of name."""
    if actual is None:
        return False
    if name in spec['assets']:
        return (actual, path.stat().st_size) in accepted(spec, name, True)
    item = panel(e).get(name)
    return bool(item) and item['sha256'] == actual


def inspect(e, row, cached=True, tolerate=False):
    """The installed Feeder setup. A changed owned file raises Drift, or with
    tolerate is reported in 'drift' so the library stays calm and Repair can fix it."""
    _, _, directory = target(row)
    record = state(e, directory)
    if record and record.get('legacy_recipe'):
        import feeder_legacy
        return feeder_legacy.inspect(e, row, record, cached)
    drift = []
    if record and record.get('adopted') and record.get('installed_hashes'):
        # An adopted setup may be any Feeder version: its record, checked below,
        # is the recipe. Installing over it replaces it with the pinned stack.
        for name in CONFIGS:
            _read_ini(t.safe(directory / name))
        try:
            nr = model(directory / MODEL, cached)
        except t.Refusal:
            nr = record.get('nr_runtime') or {}
            t.need(nr.get('sha256') and digest(directory / MODEL, cached) == nr['sha256'], 'The adopted NR model changed')
    else:
        # Only an install rtxForge owns can be repaired file by file; an
        # unrecognized setup must still match a published recipe exactly.
        stack(directory, cached, installed=True, drift=drift if record else None)
        nr = model(directory / MODEL, cached)
    if record:
        t.need(record.get('status') == 'active', 'The Feeder installation needs recovery')
        spec, listed = lock(), {item['name'] for item in drift}
        for name, expected in record['installed_hashes'].items():
            if name in CONFIGS or name in listed:
                continue
            path = t.safe(directory / t.relative(name))
            actual = digest(path, cached)
            if actual != expected:
                drift.append({'name': name, 'fix': 'record' if _published(e, spec, name, path, actual) else 'restore'})
    if drift and not tolerate:
        raise Drift(drift)
    return {'managed': record is not None, 'nr_runtime': nr, 'drift': drift, **configured(directory)}


def _windows(e):
    return getattr(e, 'DESKTOP_PLATFORM', 'windows' if os.name == 'nt' else 'linux') == 'windows'


def eligible(e, row, existing=False, check_running=True):
    root, exe, directory = target(row)
    t.need(_windows(e) or not existing or row.get('installed_on') != 'windows',
           'Installed with rtxForge on Windows. Use Adapt to Linux for this game; it still works on Windows. '
           'Nothing was changed.')
    t.need(_windows(e), 'Feeder installation is available on Windows only in this release')
    import offline_routes
    if row.get('anti_cheat'):
        # Scan can expose the otherwise-compatible route; mutation needs the
        # hash-bound offline review held by the host, never a row's boolean.
        if not check_running:
            offline_routes.receipt(row, manual=True)
        else:
            t.need(offline_routes.reviewed_route(row) is not None,
                   'Review and acknowledge offline-only use before changing this anti-cheat game.')
    t.need(not check_running or not running_under(e, root), 'Close this game before changing Feeder files')
    t.need(not e.load_baseline(directory, readonly=True) and not (directory / 'OptiScaler.ini').exists(),
           'Restore the existing OptiScaler package before installing Feeder NR')
    if not existing:
        conflicts = foreign_graphics_files(directory)
        t.need(not conflicts, 'Other graphics hooks/settings are present: ' + ', '.join(conflicts)
               + '. Restore them before installing Feeder NR')
    owned = state(e, directory)
    t.need(not any((directory / name).exists() for name in ('nvngx.dll_dlssnr.dll', 'dlss5-feed-helper.addon64',
                                                         'dlss5-bridge.addon64', 'renodx-mfgunlock.addon64')
                   if not (name == 'dlss5-feed-helper.addon64' and owned and owned.get('legacy_recipe'))),
           'Another NR or frame-generation hook is present. Restore it before using this Feeder recipe')
    if not existing:
        apis = graphics_apis(e, exe)
        import feeder_legacy
        legacy = feeder_legacy.route(e, row)
        t.need(apis and (legacy or feeder_legacy.machine(exe) == 0x8664 and apis & {'d3d11', 'd3d12'}),
               'This Feeder recipe requires DirectX 9, 10, 11 or 12 with a supported x86/x64 route')
        # Feeder's DirectX 12 session shares the game's device and refuses a second DLSS
        # runtime there; a DirectX 12 game with its own DLSS uses that DLSS route instead.
        t.need(apis != {'d3d12'} or not row.get('native_dlss'),
               'This DirectX 12 game ships DLSS; use its DLSS route instead of Feeder NR')
    return root, exe, directory


def foreign_graphics_files(directory):
    conflicts = []
    for name in sorted({*t.PROXIES, 'ReShade.ini', 'renodx-dlss5.addon64'}):
        path = directory / name
        if not path.exists():
            continue
        if name in STOCK_LIBRARIES and digest(path) in STOCK_LIBRARIES[name]:
            continue
        conflicts.append(name)
    return conflicts


def graphics_apis(e, exe):
    """Direct3D versions loaded by an x86/x64 game or its adjacent engine DLLs.

    Normal and delay-load imports first (EA-wrapped Mass Effect LE delay-loads d3d11).
    Packed executables hide their imports until launch, so fall back to the DLL names
    the file mentions.
    """
    if exe.name.lower() in REVIEWED_DX11:
        return {'d3d11'}
    apis, visited, pending = set(), set(), [(exe, 0)]
    while pending and len(visited) < 24:
        binary, depth = pending.pop(0)
        if binary in visited:
            continue
        visited.add(binary)
        # Reading the import table opens the executable, which costs up to
        # 20 ms per file on a scan; the cached list changes only with the file.
        names = cached_probe('pe-imports-v1', binary, lambda: {name.lower() for name in e.pe_imported_dlls(binary)})
        def probe():
            imported = names | {name.lower() for name in delay_imported_dlls(binary)}
            found = {api for api in ('d3d9', 'd3d10', 'd3d10_1', 'd3d11', 'd3d12') if api + '.dll' in imported}
            return found or mentioned_apis(binary)
        apis |= cached_probe('direct3d-local-v2', binary, probe)
        # Some games have a tiny EXE and keep their renderer in an imported
        # adjacent engine DLL (Far Cry 5: FC_m64.dll). Never load the DLL or
        # inspect unrelated files elsewhere in the game tree.
        if depth < 2 and not apis:
            for name in sorted(names):
                dependency = binary.parent / name
                if Path(name).name == name and name.endswith('.dll') and dependency.is_file() and not dependency.is_symlink():
                    pending.append((dependency, depth + 1))
    return apis


_PROBES: dict | None = None


def _probe_path():
    if os.environ.get('RTXFORGE_PROBE_CACHE') is not None:
        return Path(os.environ['RTXFORGE_PROBE_CACHE']) if os.environ['RTXFORGE_PROBE_CACHE'] else None
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or str(Path.home() / '.cache')
    return Path(base) / 'rtxForge' / 'exe-probes.json'


_PROBES_DIRTY = False
_PROBES_LOAD = threading.Lock()


def cached_value(kind, exe, compute, valid=lambda value: isinstance(value, list)):
    """A per-executable answer that changes only when the file does (path, size, modified time).

    Every library scan otherwise re-reads multi-gigabyte game executables to detect their
    renderer; an empty RTXFORGE_PROBE_CACHE keeps the answers in memory only. New answers
    reach the file through save_probes(), once per scan and at exit."""
    global _PROBES, _PROBES_DIRTY
    exe = Path(exe)
    try:
        stat = exe.stat()
    except OSError:
        return compute()
    with _PROBES_LOAD:
        if _PROBES is None:
            loaded = {}
            path = _probe_path()
            if path and path.is_file():
                try:
                    loaded = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    loaded = {}
            _PROBES = loaded if isinstance(loaded, dict) else {}
    key = f'{kind}|{os.path.normcase(str(exe))}'
    stamp = [stat.st_size, stat.st_mtime_ns]
    hit = _PROBES.get(key)
    if isinstance(hit, dict) and hit.get('stamp') == stamp and valid(hit.get('value')):
        return hit['value']
    value = compute()
    _PROBES[key] = {'stamp': stamp, 'value': value}
    _PROBES_DIRTY = True
    return value


def cached_probe(kind, exe, compute):
    """cached_value for a set of names."""
    return set(cached_value(kind, exe, lambda: sorted(set(compute()))))


def save_probes():
    """Write new probe answers. A failure only costs a cache miss next time, never a failed scan."""
    global _PROBES_DIRTY
    path = _probe_path()
    if not _PROBES_DIRTY or path is None or _PROBES is None:
        return
    _PROBES_DIRTY = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + f'.{os.getpid()}.tmp')
        temp.write_text(json.dumps(_PROBES), encoding='utf-8')
        os.replace(temp, path)
    except (OSError, RuntimeError):  # RuntimeError: a probe landed while writing
        _PROBES_DIRTY = True


atexit.register(save_probes)


def mentioned_apis(exe, limit=2 * 1024**3, chunk=32 * 1024**2):
    return mentioned(exe, _MENTIONED, limit, chunk)


def mentioned(exe, names, limit=2 * 1024**3, chunk=32 * 1024**2):
    """The keys of (key, lowercase DLL name) pairs whose name the file contains in any case."""
    import mmap
    try:
        with open(exe, 'rb') as file:
            if not 0 < os.fstat(file.fileno()).st_size <= limit:
                return set()
            with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
                # Any-case DLL names, chunk by chunk, stopping once every name is
                # seen: a lowercased chunk and literal searches are 2-3x faster
                # than a case-insensitive pattern over packed executables.
                # Chunks overlap by one name, so a name across a boundary is found.
                found, start, overlap = set(), 0, max(len(name) for _, name in names) - 1
                while start < len(data) and len(found) < len(names):
                    block = data[start:start + chunk + overlap].lower()
                    found.update(key for key, name in names if key not in found and name in block)
                    start += chunk
                return found
    except (OSError, ValueError):
        return set()


_MENTIONED = tuple((api, (api + '.dll').encode()) for api in ('d3d9', 'd3d10', 'd3d10_1', 'd3d11', 'd3d12'))


def route_note(e, row):
    """The Feeder route a fresh game gets, including experimental legacy recipes."""
    try:
        import feeder_legacy
        legacy = feeder_legacy.route(e, row)
        if legacy:
            bits, api = legacy.split('-', 1)
            return f'Feeder NR · {api.replace("d3d", "DirectX ")} · {bits} · experimental · NR only'
        apis = graphics_apis(e, target(row)[1])
    except (t.Refusal, OSError, ValueError):
        apis = set()
    if apis == {'d3d12'}:
        return 'Feeder NR · DirectX 12 · not verified · NR only'
    return 'Feeder NR · DirectX 11 · NR only'


def delay_imported_dlls(exe):
    """Names in a PE32+ delay-load import directory; empty when absent or unreadable."""
    import mmap
    import struct
    try:
        # Mapped, not read: only the header and import pages of a large executable are touched.
        with open(exe, 'rb') as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
            return _delay_imports(data, struct)
    except (OSError, ValueError, struct.error, UnicodeDecodeError):
        return set()


def _delay_imports(data, struct):
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
        end = data.find(b'\0', start)
        if end < 0:
            raise ValueError('Unterminated delay-import name')
        names.add(data[start:end].decode('ascii'))
        cursor += 32
    return names


def leftover_sr(e, directory):
    """True when the folder's DLSS SR DLL is Feeder's, left after a restore.

    Feeder ships its own SR. An adopted manual install brought one in, so the
    restore puts that back, and the scan would then read it as the game's
    DLSS (The Sims 4 has none). Only a restored record that adopted a Feeder
    SR, with a Feeder SR still in place, qualifies: a game's own DLSS stays.
    """
    try:
        record = state(e, directory)
    except (t.Refusal, OSError, ValueError):
        return False
    if not record or record.get('legacy_recipe') or record.get('status') != 'restored' or not record.get('adopted'):
        return False
    spec = lock()
    known = {MANUAL_SR} | {sha for sha, _ in accepted(spec, 'nvngx_dlss.dll', installed=True)}
    before = record['originals'].get('nvngx_dlss.dll')
    path = Path(directory) / 'nvngx_dlss.dll'
    try:
        return bool(before and before.get('sha256') in known and path.is_file() and digest(path, True) in known)
    except (t.Refusal, OSError, ValueError):
        return False


def _prefetch(rows):
    """Open, side by side, the files the loop below reads from each game first.

    A first scan otherwise waits on one cold executable or DLL open at a time.
    Every answer is still computed by the same cached call, so none changes:
    an executable's PE machine type, and the digests of a Feeder stack."""
    exes, files, names = [], [], None
    for row in rows:
        if row.get('executable_error') or not row.get('game'):
            continue
        root = Path(row['game'])
        paths = [] if row.get('executable_selected') else [
            root / f'Game/ME{index}/Binaries/Win64/MassEffect{index}.exe' for index in (1, 2, 3)]
        if row.get('exe'):
            paths.append(root / row['exe'])
        for exe in paths:
            if not exe.is_file():
                continue
            exes.append(exe)
            if any((exe.parent / name).is_file() for name in ('dlss5-feed.addon64', 'dlss5-feed.addon32')):
                names = names or [*lock()['assets'], MODEL]
                files += [exe.parent / name for name in names]
    import feeder_legacy

    def machine(exe):
        try:
            feeder_legacy.machine(exe)
        except (t.Refusal, OSError, ValueError):
            pass
    if len(exes) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(min(file_stamps.WORKERS, len(exes)), thread_name_prefix='exe-probe') as pool:
            list(pool.map(machine, exes))
    file_stamps.prefetch(files)


def expand_rows(e, rows, selected=False):
    import skynizz_provider
    _prefetch(rows)
    result = []
    for original in rows:
        if original.get('executable_error'):
            result.append(original)
            continue
        root = Path(original['game'])
        candidates = []
        # ME Legendary Edition has one Steam entry and three actual targets.
        for index in (1, 2, 3):
            if original.get('executable_selected'):
                break
            exe = root / f'Game/ME{index}/Binaries/Win64/MassEffect{index}.exe'
            if exe.is_file():
                candidates.append((exe, f"{original['name']} · Mass Effect {index}"))
        if not candidates and original.get('exe'):
            exe = root / original['exe']
            # Some collections pick a launcher. Prefer its adjacent DX11 game.
            if (not original.get('executable_selected') and exe.name.lower() in ('ts4_launcher_x64.exe', 'ts4_dx9_x64.exe')
                    and (exe.parent / 'TS4_x64.exe').is_file()):
                exe = exe.parent / 'TS4_x64.exe'
            candidates = [(exe, original['name'])]
        for exe, name in candidates:
            child = copy.deepcopy(original)
            if len(candidates) > 1:
                child.update(game=str(exe.parent), exe=exe.name, collection_game=str(root), name=name)
            else:
                child['exe'] = exe.relative_to(root).as_posix()
            if child.get('native_dlss') and leftover_sr(e, exe.parent):
                child['native_dlss'] = False
            if has_feeder_hook(exe.parent):
                try:
                    import cross_os
                    shared = cross_os.read(exe.parent)
                    if not _windows(e) and shared and shared.get('provider',{}).get('id')=='feeder' and shared.get('legacy_recipe'):
                        child.update(installed=True, runtime_provider='feeder', feature_mode='nr-only', profile='NR Only',
                                     installed_on='windows', installed_oses=['windows'], linux_ready=False,
                                     feeder_available=False, mfg_enabled=False, mfg_multiplier=0,
                                     blocked='This experimental Feeder route is available on Windows. Its shared installation is preserved.')
                        result.append(child);continue
                    found = inspect(e, child, tolerate=True)
                    if found.get('drift'):  # legacy recipes report no drift
                        # One changed file is a repair, not a broken game: it stays
                        # installed and usable, with Repair named as the fix.
                        child['feeder_drift'] = {'files': found['drift'], 'summary': drift_summary(found['drift'])}
                    child.update(installed=True, runtime_provider='feeder', feature_mode='nr-only', profile='NR Only',
                                 feeder_managed=found['managed'], nr_enabled=found['nr_enabled'], nr_runtime=found['nr_runtime'],
                                 # Feeder installs only on Windows, so on Linux a verified stack is a dual-boot install.
                                 mfg_enabled=False, mfg_multiplier=0,
                                 installed_on='windows' if found['managed'] or not _windows(e) else None,
                                 linux_ready=not _windows(e) and linux_ready(e, child),
                                 feeder_settings={k: found[k] for k in ('passes', 'scale', 'preset')},
                                 blocked='')
                    import cross_os
                    marker = cross_os.read(exe.parent)
                    oses = set(child.get('installed_oses') or [])
                    if child.get('installed_on') == 'windows': oses.add('windows')
                    if child.get('linux_ready'): oses.add('linux')
                    if marker and marker.get('provider', {}).get('id') == 'feeder':
                        oses.add(marker['os'])
                        oses.update(name for name in marker.get('installed_oses', []) if name in cross_os.OPERATING_SYSTEMS)
                    child['installed_oses'] = [name for name in ('windows','linux') if name in oses]
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
            elif (selected or original.get('executable_selected') or not child.get('native_dlss')
                  or skynizz_provider.native_nr_refusal(child.get('exe'), child.get('appid'))):
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


def publish_installation(row, baseline):
    """Share verified ownership with the other OS without rehashing large models."""
    import cross_os
    directory = Path(baseline['target']); previous = cross_os.read(directory) or {}
    t.need(not previous or previous.get('provider',{}).get('id')=='feeder', 'Another package owns the shared install record.')
    oses = {cross_os.THIS_OS, *previous.get('installed_oses',[])}
    if previous.get('os') in cross_os.OPERATING_SYSTEMS: oses.add(previous['os'])
    recipe = baseline.get('legacy_recipe'); proxy = 'd3d9.dll' if recipe and recipe.endswith('d3d9') else 'dxgi.dll'
    marker = dict(schema=cross_os.SCHEMA, os=cross_os.THIS_OS, revision=cross_os.new_revision(), shared_state=False,
                  provider={'id':'feeder','name':'Feeder NR','version':lock()['version']}, feature_mode='nr-only',
                  proxy=proxy, proton_overrides=[Path(proxy).stem], files=dict(baseline['installed_hashes']),
                  installed_oses=[name for name in ('windows','linux') if name in oses])
    if recipe: marker['legacy_recipe']=recipe
    t.atomic_file(directory/cross_os.MARKER,(json.dumps(marker,indent=1)+'\n').encode(),0o644)


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
    import feeder_legacy
    feeder_legacy.import_assets(e, source)
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
    owned = None
    if source and Path(source).is_dir():
        try:
            owned = import_stack(e, source)
        except (t.Refusal, OSError, ValueError, configparser.Error):
            owned = owned_stack(e)
            if owned is None:
                spec = stack(source, cached=True, installed=True)
                # A verified older import can stay in Settings while the new
                # package is fetched. Unknown local files still refuse.
                if all(digest(Path(source) / name, cached=True) == spec['assets'][name]['sha256']
                       for name in spec.get('previous_assets', {})):
                    raise
    owned = owned or owned_stack(e)
    if owned is None:
        owned = download_stack(e)
    if MODEL not in owned['files'] and not settings.get('nr_runtime'):
        import vulkan_app
        nr = model(vulkan_app.bundled_model(e.STATE_ROOT))
        owned = copy.deepcopy(owned); owned['files'][MODEL] = cache(e, Path(nr['path'])); owned['nr_version'] = nr['version']
        t.atomic_file(stack_record_path(e), (json.dumps(owned,indent=2)+'\n').encode(), 0o600)
    return owned['files']


def download_stack(e):
    """Resolve a complete fresh-install recipe, independently of any game folder."""
    import package_downloads
    import vulkan_app
    spec = lock()
    sources = t.read_json(ROOT / 'providers/feeder-runtime.json')['sources']
    files = package_downloads.inputs(e, sources, spec['assets'])
    t.need(set(files) == set(spec['assets']), 'The downloaded Feeder package is incomplete. Retry the download.')
    defaults = {
        'ReShade.ini': '[GENERAL]\nEffectSearchPaths=.\\reshade-shaders\\Shaders\\**\nTextureSearchPaths=.\\reshade-shaders\\Textures\\**\nPresetPath=.\\ReShadePreset.ini\n[RenoDX.DLSS5]\nNeuralUplift=0\n',
        'ReShadePreset.ini': 'Techniques=Lumenite_Kernel@lumenite_Kernel.fx,DLSS5_Feed@DLSS5_Feed.fx\nTechniqueSorting=Lumenite_Kernel@lumenite_Kernel.fx,DLSS5_Feed@DLSS5_Feed.fx\n[DLSS5_Feed.fx]\nPreprocessorDefinitions=DLSS5_MV_PROVIDER=3\n',
    }
    for name, text in defaults.items():
        raw = text.encode('utf-8'); path = t.safe(e.STATE_ROOT / 'feeder-cache' / t.sha(raw))
        if not path.exists(): t.atomic_file(path, raw, 0o600)
        files[name] = cache(e, path)
    nr = model(vulkan_app.bundled_model(e.STATE_ROOT))
    files[MODEL] = cache(e, Path(nr['path']))
    record = dict(schema=1, provider_id='feeder', recipe=spec['version'],
                  imported_from='verified-download', imported_utc=t.now(), files=files, nr_version=nr['version'])
    t.atomic_file(stack_record_path(e), (json.dumps(record, indent=2) + '\n').encode(), 0o600)
    return owned_stack(e)


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


def _review_split_restore(config, plan, entry):
    if plan['operation'] != 'uninstall':
        return
    import nr_install
    directory = Path(plan['target'])
    restore = nr_install.prepare_package_restore(config, plan['row'], (directory / t.relative(name) for name in plan['writes']))
    plan['split_render_restore'] = restore
    if detail := nr_install.package_restore_detail(restore):
        entry['detail'] += '\n' + detail
        entry['summary'] += ' Also remove the recorded Split Render setup.'
        if notes := restore['review'].get('notes'):
            entry['summary'] += ' ' + ' '.join(notes)


def _check(e, plan):
    import offline_routes
    if plan.get('split_render_restore'):
        import nr_install
        nr_install.check_package_restore(plan['split_render_restore'])
    if hasattr(e, 'scan_game_files') and e.scan_game_files(Path(plan['row']['game']))[2] is not None:
        t.need(offline_routes.reviewed_route(plan['row']) is not None, 'Anti-cheat appeared after review; review offline-only use again.')
    if plan.get('legacy_recipe'):
        import feeder_legacy
        return feeder_legacy.check(e, plan)
    eligible(e, plan['row'], existing=plan['existing'])
    directory = Path(plan['target'])
    t.need(_checks(directory, plan['checks']) == plan['checks'], 'Feeder files changed since review; review again')
    t.need(digest(state_dir(e, directory) / 'baseline.json') == plan['baseline_before'],
           'Feeder install record changed since review')
    for item in plan['inputs'].values():
        t.need(digest(cached_input(e, item)) == item['sha256'], 'Feeder source or original backup changed since review')


# --- Adapt to Linux: a Feeder install made on Windows, run under Proton ----------------------
#
# ReShade loads as dxgi.dll beside the game. Under Proton that only needs the prefix to load
# the native dxgi.dll first, so this adds that one DLL override and nothing else: no game file,
# Feeder record or Windows backup changes, and Windows keeps working as it was. Remove Linux
# Setup puts the prefix back. Mass Effect LE's three games share one Steam prefix, so the
# record is kept per Steam game, not per executable.

LINUX_OVERRIDES = ('dxgi',)


def linux_setup_state(e, row):
    return e.STATE_ROOT / 'prefix-overrides' / e.target_key(Path(row.get('collection_game') or row['game']))


def linux_ready(e, row):
    import proton_prefix
    try:
        return bool(proton_prefix.load_record(linux_setup_state(e, row)))
    except (OSError, ValueError):
        return False


def publish_linux_history(row, ready):
    """Keep Feeder's per-OS setup history beside its shared game files."""
    import cross_os
    _, _, directory = target(row)
    previous = cross_os.read(directory)
    t.need(previous is None or previous.get('provider', {}).get('id') == 'feeder',
           'A different package owns this game\'s shared record.')
    names = [*lock()['assets'], *CONFIGS, MODEL, *PANELS]
    record = cross_os.write(directory, 'linux' if ready else 'windows', names,
                            {'id':'feeder','name':'Feeder NR','version':lock()['version']},
                            'nr-only','dxgi.dll',('dxgi',))
    record['installed_oses'] = ['windows','linux'] if ready else ['windows']
    t.atomic_file(directory / cross_os.MARKER, (json.dumps(record,indent=1)+'\n').encode(),0o600)
    return record


def _linux_setup(e, row, operation):
    """Review entry for Adapt to Linux / Remove Linux Setup of a Windows Feeder install."""
    import proton_prefix
    root, _, directory = target(row)
    t.need(not running_under(e, root), 'Close this game before changing its Linux setup')
    state = linux_setup_state(e, row)
    shared = ' Its prefix is shared by every Mass Effect game in this collection.' if row.get('collection_game') else ''
    if operation == 'uninstall':
        record = proton_prefix.load_record(state)
        t.need(record, 'Installed with rtxForge on Windows. Restore its original files in rtxForge on Windows, '
                       'where they are backed up.')
        prefix = record['prefix']
        summary = ('Remove Linux Setup · removes the Proton setting (dxgi) from this game\'s prefix.' + shared +
                   ' The Windows install is not touched; restore its original files in rtxForge on Windows.')
    else:
        inspect(e, row, cached=False)  # a verified Feeder stack, exactly as Windows left it
        try:
            prefix = proton_prefix.find_prefix(row.get('collection_game') or row['game'], row.get('appid'))
        except proton_prefix.PrefixError as error:
            raise t.Refusal(str(error)) from error
        t.need(not proton_prefix.prefix_in_use(prefix), 'This game is running. Quit it, then try again.')
        summary = ('Adapt to Linux · adds the Proton setting (dxgi) in this game\'s prefix so ReShade and Feeder NR '
                   'load under Proton.' + shared + ' Nothing in the game folder changes and the Windows install is not touched.')
    plan = dict(row=dict(row), target=str(directory), operation=operation, linux_setup=list(LINUX_OVERRIDES),
                prefix=str(prefix), state=str(state))
    detail = json.dumps({'target': str(directory), 'operation': operation, 'prefix': str(prefix),
                         'overrides': list(LINUX_OVERRIDES), 'writes': {}}, indent=2)
    return plan, {'name': row['name'], 'game': row['game'], 'summary': summary, 'detail': detail}


def _execute_linux(review):
    """Apply or remove reviewed Linux setups; each game's prefix change is undone if it fails."""
    import proton_prefix
    e, results = review['engine'], []
    with e.mutation_lock():
        session = Session(e.STATE_ROOT / 'desktop-operations')
        try:
            for index, plan in enumerate(review['plans'], 1):
                ui.progress('Saving the Proton setting', game=plan['row']['name'], current=index, total=len(review['plans']))
                t.need(not running_under(e, Path(plan['row']['game'])), 'Close this game before changing its Linux setup')
                record = proton_prefix.load_record(plan['state'])
                registry = Path(record['registry']) if record else Path(plan['prefix']) / 'user.reg'
                import cross_os
                marker_path = Path(plan['target']) / cross_os.MARKER
                checkpoint = session.capture([registry, Path(plan['state']), marker_path], label=plan['row']['name'])
                try:
                    if plan['operation'] == 'uninstall':
                        proton_prefix.restore(plan['state'])
                    else:
                        proton_prefix.apply(Path(plan['prefix']), plan['linux_setup'], plan['state'])
                    publish_linux_history(plan['row'], plan['operation'] != 'uninstall')
                    session.seal(checkpoint)
                except BaseException:
                    session.seal(checkpoint)
                    session.undo(checkpoint)
                    session.seal(checkpoint)
                    raise
                results.append({'name': plan['row']['name'], 'game': plan['row']['game'], 'status': 'complete'})
            session.complete()
        except BaseException as error:
            if session.interrupted() is None:
                session.close('failed')
            if isinstance(error, Exception):
                raise t.Refusal(f'Stopped after {len(results)} completed game(s). Completed games keep their Linux '
                                f'setup; the rest are as they were. {error}') from error
            raise
        finally:
            operation_session.LIVE.discard(str(session.root))
    path = e.STATE_ROOT / ('desktop-feeder-' + e.now_stamp() + '.json')
    e.save_json_atomic(path, {'results': results})
    return str(path)


def prepare(config, rows, mode, operation, settings, e):
    with review_session(e):
        import feeder_legacy
        def legacy_route(row):
            try:
                eligible(e, row, existing=any((Path(row['game']) / row['exe']).parent.joinpath(name).is_file()
                         for name in ('dlss5-feed.addon64', 'dlss5-feed.addon32', 'dlss5-feed-helper.addon64')))
                return feeder_legacy.route(e, row)
            except (t.Refusal, e.Stop, OSError, ValueError, KeyError):
                return None
        if _windows(e) and any(legacy_route(row) for row in rows):
            ready, blocked, plans, seen = [], [], [], set()
            for row in rows:
                try:
                    directory = target(row)[2]
                    t.need(str(directory).casefold() not in seen, 'The same Feeder executable was selected twice')
                    seen.add(str(directory).casefold())
                    recipe = feeder_legacy.route(e, row)
                    if recipe:
                        import overlay_settings
                        effective = settings | overlay_settings.effective(settings, row['game'])
                        plan, entry = feeder_legacy.prepare(e, row, mode, operation, effective, recipe)
                        _review_split_restore(config, plan, entry)
                        plans.append(plan); ready.append(entry)
                    else:
                        part = _prepare(config, [row], mode, operation, settings, e)
                        plans.extend(part['plans']); ready.extend(part['rows']); blocked.extend(part['blocked'])
                except (t.Refusal, e.Stop, OSError, ValueError, configparser.Error) as error:
                    blocked.append({'name': row['name'], 'game': row['game'], 'reason': str(error)})
            return dict(kind='feeder', operation=operation, title='Feeder NR', rows=ready, blocked=blocked, plans=plans, engine=e)
        return _prepare(config, rows, mode, operation, settings, e)


def _prepare(config, rows, mode, operation, settings, e):
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
            if not _windows(e) and existing and row.get('installed_on') == 'windows':
                t.need(operation in ('install', 'repair', 'uninstall'),
                       'Installed with rtxForge on Windows. Change its Feeder settings in rtxForge on Windows.')
                plan, entry = _linux_setup(e, row, operation)
                plans.append(plan)
                ready.append(entry)
                continue
            eligible(e, row, existing)
            # Repair and Restore are how a changed owned file gets fixed, so they
            # never refuse because of it (the session still backs up what is there).
            mend = operation in ('repair', 'uninstall') and current is not None
            spec = stack(directory, installed=True, drift=[] if mend else None) if existing else lock()
            names = list(spec['assets']) + [*CONFIGS, MODEL]
            inputs, writes = {}, {}
            baseline = copy.deepcopy(current)
            if operation in ('uninstall', 'reset', 'repair', 'apply'):
                t.need(current is not None, 'Recognize this Feeder installation with its original backups first')
            if current or existing:
                found = inspect(e, row, cached=False, tolerate=mend)
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
                                    expected.add(MANUAL_SR)
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
                drifted = found.get('drift') if operation == 'repair' and (current or existing) else None
                if drifted:
                    # Changed recipe files come back from the verified stack; panel files
                    # come back with the bundled panel below; published builds are recorded as they are.
                    restore = [item['name'] for item in drifted if item['fix'] == 'restore' and item['name'] in spec['assets']]
                    if restore:
                        files = stack_files(e, settings)
                        for name in restore:
                            inputs[name] = writes[name] = files[name]
                        summary += ' Put back: ' + ', '.join(restore) + '.'
                    kept = [item['name'] for item in drifted if item['fix'] == 'record']
                    if kept:
                        summary += ' Record the current rtxForge build of: ' + ', '.join(kept) + '.'
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
            if operation == 'repair':
                unfixed = [item['name'] for item in found.get('drift') or [] if item['fix'] == 'restore' and item['name'] not in writes]
                t.need(not unfixed, 'Repair has no verified copy of ' + ', '.join(unfixed) + '. Reinstall Feeder NR to replace it.')
            # Files the record already owns stay owned after a repair (the in-game panel included).
            owned = [name for name in (current or {}).get('installed_hashes', {})
                     if name not in names and name not in writes and operation != 'uninstall']
            checks = _checks(directory, [*names, *(name for name in writes if name not in names), *owned])
            plan = dict(row=dict(row), target=str(directory), existing=existing, checks=checks,
                        baseline_before=digest(state_dir(e, directory) / 'baseline.json'), baseline=baseline,
                        inputs=inputs, writes=writes, operation=operation)
            detail = json.dumps({'target': str(directory), 'operation': operation,
                                 'recipe': spec['version'], 'model': (baseline or {}).get('nr_runtime'),
                                 'original_manifest': (baseline or {}).get('original_manifest'),
                                 'writes': {name: item['sha256'] if item else None for name, item in writes.items()},
                                 'preserved_settings': list(CONFIGS) if existing and operation != 'uninstall' else []}, indent=2)
            entry = {'name': row['name'], 'game': row['game'], 'summary': summary, 'detail': detail}
            _review_split_restore(config, plan, entry)
            _check(e, plan)
            plans.append(plan); ready.append(entry)
        except (t.Refusal, e.Stop, OSError, ValueError, configparser.Error) as error:
            blocked.append({'name': row['name'], 'game': row['game'], 'reason': str(error)})
    return dict(kind='feeder', operation=operation, title='Feeder NR', rows=ready, blocked=blocked, plans=plans, engine=e)


def execute(review):
    e, results = review['engine'], []
    t.need(review['plans'], 'No Feeder changes were reviewed')
    if any(plan.get('linux_setup') for plan in review['plans']):
        t.need(all(plan.get('linux_setup') for plan in review['plans']), 'Review the Linux setup on its own')
        return _execute_linux(review)
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
                import cross_os
                shared_marker = directory / cross_os.MARKER
                writes = {directory / t.relative(name): (plan['checks'][name], item) for name, item in plan['writes'].items()}
                import nr_install
                split_render = plan.get('split_render_restore')
                checkpoint = session.capture([*writes, state_dir(e, directory), shared_marker,
                                              *nr_install.package_restore_paths(split_render)], label=plan['row']['name'])
                try:
                    if split_render:
                        nr_install.apply_package_restore(split_render, cancelled=cancel.is_set if cancel is not None else lambda: False)
                    # A durable baseline precedes any model replacement.
                    if plan['operation'] != 'uninstall':
                        baseline = copy.deepcopy(plan['baseline'])
                        baseline['status'] = 'preparing'
                        t.atomic_file(state_dir(e, directory) / 'baseline.json', (json.dumps(baseline, indent=2) + '\n').encode(), 0o600)
                    for destination, (expected, item) in writes.items():
                        if cancel is not None and cancel.is_set():
                            raise Cancelled('Changes undone.')
                        path = t.safe(destination)
                        t.need(digest(path) == expected, 'Feeder target changed during the operation')
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
                        if plan.get('legacy_recipe'):
                            import feeder_legacy
                            feeder_legacy.verify_written(directory, plan['legacy_recipe'])
                        else:
                            stack(directory, installed=True)
                    t.atomic_file(state_dir(e, directory) / 'baseline.json', (json.dumps(baseline, indent=2) + '\n').encode(), 0o600)
                    if plan['operation'] == 'uninstall':
                        shared = cross_os.read(directory)
                        if shared and shared.get('provider', {}).get('id') == 'feeder': shared_marker.unlink()
                    else: publish_installation(plan['row'], baseline)
                    if plan.get('legacy_recipe') and plan['operation'] == 'uninstall':
                        import feeder_legacy
                        feeder_legacy.cleanup_directories(directory, baseline)
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
    feed_directory = directory
    if any((directory / name).is_file() for name in ('dlss5-feed.addon32', 'dlss5-feed-helper.addon64')):
        directory = directory / 'host64'
    nr = model(directory / MODEL)
    saved = configured(directory, feed_directory)
    report = {'name': row['name'], 'provider': 'feeder', 'settings': saved, 'files': {MODEL: nr},
              'observations': ['Feeder NR is installed. Saved NR is ' + ('enabled.' if saved['nr_enabled'] else 'disabled.'),
                               'NR runtime: ' + nr['version'] + '.', 'Frame generation is unavailable for this route.'],
              'warnings': [], 'visual_result': 'Not established by file or log inspection'}
    logs, times = {}, {}
    for name in ('dlss5-feed.log', 'ReShade.log'):
        try:
            data, info = read_regular((feed_directory if name == 'dlss5-feed.log' else directory) / name, tail=True)
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
