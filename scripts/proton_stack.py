"""What a game's Proton setup provides for native NR and Ada MFG (read-only).

Skynizz NR and the Universal MFG Unlocker run inside the game process. Under
Proton they need the same pieces a Windows install gets from the NVIDIA
driver: D3D12 through vkd3d-proton, NVAPI through dxvk-nvapi, and NGX through
the driver's Wine DLLs (nvngx.dll / _nvngx.dll) that Proton copies into the
prefix. This module only looks. It never starts Proton, never writes to a
prefix and never changes the environment.

A passing report means the pieces are present. It is not runtime evidence:
only a real Proton session on the target GPU can show NR or MFG working, and
`runtime_verified` stays False until such evidence is recorded for that
game, Proton build and GPU (see evidence()).

Every refusal has a stable reason code (REASONS) so the GTK app can show the
user text and the review can keep the technical detail behind Details.
"""
from pathlib import Path
import json
import re
import shlex

# Stable reason codes -> user text. The UI may show the text as-is.
REASONS = {
    'not-linux': 'Proton checks only apply on Linux.',
    'nvidia-driver-missing': 'The NVIDIA driver is not loaded. NR and MFG need an NVIDIA RTX GPU.',
    'nvidia-driver-old': 'Update the NVIDIA driver to the 570 series or newer for DLSS Frame Generation under Proton.',
    'gpu-not-rtx': 'No NVIDIA RTX GPU was found.',
    'mfg-gpu-unverified-linux': 'MFG under Proton is offered on RTX 40 and RTX 50 GPUs. RTX 20 and 30 are not offered on Linux yet.',
    'mfg-native-unverified-linux': ("RTX 50 uses the game's own DLSS Multi-Frame Generation, with no unlock installed. "
                                    'It has not been verified under Proton yet.'),
    'driver-ngx-missing': "The NVIDIA driver's Wine NGX files (nvngx.dll) were not found, so Proton cannot provide DLSS.",
    'prefix-missing': 'This game has not been started with Proton yet. Play it once, quit, then check again.',
    'tool-unknown': "The Proton version this game last used could not be read. Play it once with Proton, quit, then check again.",
    'vkd3d-missing': 'This Proton build has no vkd3d-proton, so DirectX 12 games cannot use DLSS.',
    'vkd3d-disabled': 'The launch options turn off DirectX 12 (PROTON_NO_D3D12 or PROTON_USE_WINED3D). Remove that to use DLSS.',
    'nvapi-missing': 'This Proton build has no dxvk-nvapi, so DLSS cannot start.',
    'nvapi-disabled': 'NVAPI is turned off for this game (PROTON_DISABLE_NVAPI, or Proton disables it for this title). DLSS cannot start.',
    'nvapi-not-in-prefix': "NVAPI was not set up in this game's prefix on its last run. Play it once with Proton, quit, then check again.",
    'ngx-not-in-prefix': "Proton did not copy the NVIDIA NGX files into this game's prefix on its last run. Play it once, quit, then check again.",
    'cuda-missing': ("This game's Proton build has no CUDA library (nvidia-libs nvcuda), which frame generation needs to identify "
                     "the GPU. In Steam, set the game to Proton-GE (Properties › Compatibility), then try again."),
    'cuda-stale-run': ("Steam is set to run this game with a Proton build that has CUDA, but the game last ran with one "
                       "that doesn't (nvidia-libs nvcuda), which frame generation needs. Play it once, quit, then try again."),
    'cuda-off': ("Proton gave this game its placeholder CUDA library on the last run, so the MFG Unlocker cannot "
                 "identify the GPU and MFG stays off. Set PROTON_NVIDIA_NVCUDA=1 for this game (in its launch "
                 "options or the Proton build's user_settings.py), play it once, quit, then check again."),
    'native-dlssg-missing': "MFG needs the game's own DLSS Frame Generation; this game does not ship it.",
    'dxvk-missing': 'This Proton build has no DXVK, so DirectX 11 games cannot use ReShade and the Feeder.',
    'feeder-linux-unverified': 'The Feeder route (ReShade + RenoDX) is Windows-only until it is shown working in a moving scene under Proton.',
}

# Component name -> folder under Proton's lib/wine and the 64-bit DLLs it must hold.
COMPONENTS = {
    'dxvk': ('dxvk', ('dxgi.dll', 'd3d11.dll')),
    'vkd3d-proton': ('vkd3d-proton', ('d3d12.dll', 'd3d12core.dll')),
    'dxvk-nvapi': ('nvapi', ('nvapi64.dll',)),
}
# Proton's default nvcuda.dll is an empty placeholder. The working one wraps
# libcuda and is installed only when PROTON_NVIDIA_NVCUDA or PROTON_NVIDIA_LIBS
# is on. The MFG Unlocker picks the GPU through cuDeviceGetLuid and
# cuDeviceComputeCapability, so without it gpuSelectionFailure stays 200.
NVCUDA = Path('wine') / 'nvidia-libs' / 'nvcuda' / 'x86_64-windows' / 'nvcuda.dll.so'
NVCUDA_SWITCHES = ('PROTON_NVIDIA_NVCUDA', 'PROTON_NVIDIA_LIBS', 'PROTON_NVIDIA_NVENC', 'PROTON_NVIDIA_NVOPTIX')
DRIVER_WINE_DIRS = ('/usr/lib64/nvidia/wine', '/usr/lib/nvidia/wine', '/usr/lib/x86_64-linux-gnu/nvidia/wine')
DRIVER_ROOT = Path('/proc/driver/nvidia')
STEAM_ROOTS = tuple(Path.home() / p for p in ('.local/share/Steam', '.steam/steam',
                                               '.var/app/com.valvesoftware.Steam/.local/share/Steam'))
MIN_DRIVER = 570
_ASSIGNMENT = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$')


def _read(path, limit=1024 * 1024):
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            return None
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None


def gpu(driver_root=None):
    """The NVIDIA driver version and the first GPU's model and architecture."""
    driver_root = Path(driver_root or DRIVER_ROOT)
    version_text = _read(driver_root / 'version') or ''
    match = re.search(r'Kernel Module(?: for \S+)?\s+(\d+)\.(\d+)(?:\.(\d+))?', version_text)
    models = []
    try:
        for info in sorted((driver_root / 'gpus').iterdir()):
            text = _read(info / 'information') or ''
            found = re.search(r'^Model:\s*(.+)$', text, re.M)
            if found:
                models.append(found.group(1).strip())
    except OSError:
        pass
    model = models[0] if models else ''
    return {'driver': '.'.join(g for g in match.groups() if g) if match else None,
            'driver_major': int(match.group(1)) if match else None,
            'model': model, 'models': models, 'architecture': architecture(model)}


def architecture(model):
    """RTX generation from the marketing name: ada, blackwell, ampere, turing or unknown."""
    found = re.search(r'RTX\s*(?:A\d+\s*)?(\d)(\d)\d{1,2}', model or '', re.I)
    if not found:
        return 'unknown'
    return {'2': 'turing', '3': 'ampere', '4': 'ada', '5': 'blackwell'}.get(found.group(1), 'unknown')


def driver_wine_dir(candidates=None):
    """Where the driver keeps the Wine NGX DLLs Proton copies into each prefix."""
    for folder in candidates if candidates is not None else DRIVER_WINE_DIRS:
        if (Path(folder) / 'nvngx.dll').is_file():
            return Path(folder)
    return None


def compat_tool(compatdata):
    """The Proton build a game last ran with, from compatdata/<appid>/{version,config_info}.

    config_info's third line is the tool's lib directory (".../files/lib/").
    """
    compatdata = Path(compatdata)
    version = (_read(compatdata / 'version') or '').strip() or None
    lines = (_read(compatdata / 'config_info') or '').splitlines()
    lib = Path(lines[2].strip()) if len(lines) > 2 and lines[2].strip().startswith('/') else None
    return {'version': version, 'lib_dir': lib if lib and lib.is_dir() else None}


def _block(text, key):
    """The body of a VDF block "key" { ... }, braces balanced; '' when absent."""
    match = re.search(r'"%s"\s*\{' % re.escape(key), text, re.I)
    if not match:
        return ''
    depth, start = 1, match.end()
    for i in range(start, len(text)):
        depth += {'{': 1, '}': -1}.get(text[i], 0)
        if not depth:
            return text[start:i]
    return ''


def _custom_tool_lib(roots, name):
    """files/lib of a compatibilitytools.d tool by its Steam name, or None (Valve's own builds)."""
    for root in roots:
        try:
            tools = sorted((root / 'compatibilitytools.d').iterdir())
        except OSError:
            continue
        for folder in tools:
            vdf = _read(folder / 'compatibilitytool.vdf') or ''
            if folder.name == name or _block(_block(vdf, 'compat_tools'), name):
                lib = folder / 'files' / 'lib'
                if lib.is_dir():
                    return lib
    return None


def mapped_tool(appid):
    """The compatibility tool Steam is set to run a game with (config.vdf CompatToolMapping).

    This is what the next launch uses, which can differ from compat_tool(), the last run.
    lib_dir is set only for tools in compatibilitytools.d (Proton-GE and other custom builds).
    """
    roots = [Path(root) for root in STEAM_ROOTS]
    for root in roots:
        entry = _block(_block(_read(root / 'config' / 'config.vdf') or '', 'CompatToolMapping'), str(appid))
        match = re.search(r'"name"\s+"([^"]+)"', entry)
        if match:
            return {'name': match.group(1), 'lib_dir': _custom_tool_lib(roots, match.group(1))}
    return {'name': None, 'lib_dir': None}


def cuda_missing_reason(compatdata):
    """Why the last-run Proton build has no CUDA: 'cuda-stale-run' when Steam is already set to one that has it."""
    lib = mapped_tool(Path(compatdata).name)['lib_dir']
    return 'cuda-stale-run' if lib and (lib / NVCUDA).is_file() else 'cuda-missing'


def component_versions(lib_dir):
    """{component: {'present': bool, 'version': str|None}} inside a Proton build."""
    report = {}
    for name, (folder, dlls) in COMPONENTS.items():
        root = Path(lib_dir) / 'wine' / folder if lib_dir else None
        present = bool(root) and all((root / 'x86_64-windows' / dll).is_file() for dll in dlls)
        text = (_read(root / 'version') or '').strip() if root else ''
        described = re.search(r'\(([^)]+)\)', text)
        report[name] = {'present': present, 'version': described.group(1) if described else (text or None)}
    return report


def launch_environment(launch_options):
    """Environment assignments before %command% in Steam launch options."""
    text = (launch_options or '').split('%command%', 1)[0]
    try:
        words = shlex.split(text)
    except ValueError:
        words = text.split()
    values = {}
    for word in words:
        match = _ASSIGNMENT.match(word)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def _truthy(value):
    return value is not None and value.strip() not in ('', '0')


def cuda_requested(lib_dir, env):
    """Whether Proton will install its working nvcuda: launch options or the build's user_settings.py."""
    if any(_truthy(env.get(name)) for name in NVCUDA_SWITCHES):
        return True
    settings = _read(Path(lib_dir).parent.parent / 'user_settings.py') if lib_dir else None
    return bool(settings) and re.search(r'''['"](%s)['"]\s*:\s*['"]?[1-9]''' % '|'.join(NVCUDA_SWITCHES),
                                        settings) is not None


def prefix_cuda(prefix):
    """Whether the prefix's nvcuda.dll from the last run exports the CUDA driver API."""
    path = Path(prefix) / 'drive_c' / 'windows' / 'system32' / 'nvcuda.dll'
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 ** 2:
            return False
        return b'cuDeviceGetLuid' in path.read_bytes()
    except OSError:
        return False


def prefix_files(prefix):
    system32 = Path(prefix) / 'drive_c' / 'windows' / 'system32'
    return {name: (system32 / name).is_file() for name in ('nvapi64.dll', 'nvngx.dll', '_nvngx.dll')}


def detect(prefix, mode='nr-mfg', launch_options='', native_dlssg=None, system='linux',
           driver_root=None, driver_dirs=None, cuda_planned=False):
    """Read-only prerequisite report for native NR/MFG in one game's Proton prefix.

    prefix        -- <library>/steamapps/compatdata/<appid>/pfx, or None if never run
    mode          -- 'nr-only', 'nr-mfg' or 'mfg-only'
    native_dlssg  -- the library scan's game-native DLSS-G flag (None = unknown)
    cuda_planned  -- the same review writes the build's user_settings.py (proton_cuda)
    """
    checks = []

    def check(check_id, ok, reason=None, detail='', required=True):
        checks.append({'id': check_id, 'state': 'ok' if ok else ('missing' if required else 'note'),
                       'required': required, 'reason': None if ok else reason,
                       'detail': detail or (REASONS.get(reason, '') if not ok else '')})
        return ok

    if system != 'linux':
        check('platform', False, 'not-linux')
        return _finish(checks, None, {}, None)
    card = gpu(driver_root)
    check('nvidia-driver', card['driver_major'] is not None, 'nvidia-driver-missing',
          'NVIDIA ' + card['driver'] if card['driver'] else '')
    if card['driver_major'] is not None:
        check('driver-version', card['driver_major'] >= MIN_DRIVER, 'nvidia-driver-old', 'NVIDIA ' + str(card['driver']))
    check('gpu', card['architecture'] != 'unknown', 'gpu-not-rtx', card['model'])
    # RTX 50 needs no unlock: MFG is the game's own, so the Universal plugin's CUDA needs don't apply.
    native_mfg = card['architecture'] == 'blackwell'
    if mode in ('nr-mfg', 'mfg-only'):
        check('mfg-gpu', card['architecture'] in ('ada', 'blackwell'), 'mfg-gpu-unverified-linux', card['model'])
        if native_mfg:
            check('mfg-native', False, 'mfg-native-unverified-linux', card['model'], required=False)
        if native_dlssg is not None:
            check('native-dlssg', bool(native_dlssg), 'native-dlssg-missing')
    wine_dir = driver_wine_dir(driver_dirs)
    check('driver-ngx', wine_dir is not None, 'driver-ngx-missing', str(wine_dir or ''))
    env = launch_environment(launch_options)
    tool = {'version': None, 'lib_dir': None}
    components = {}
    if not prefix or not (Path(prefix) / 'user.reg').is_file():
        check('prefix', False, 'prefix-missing')
    else:
        prefix = Path(prefix)
        check('prefix', True, detail=str(prefix))
        tool = compat_tool(prefix.parent)
        if check('proton', tool['lib_dir'] is not None, 'tool-unknown', 'Proton ' + str(tool['version'] or '')):
            components = component_versions(tool['lib_dir'])
            check('vkd3d-proton', components['vkd3d-proton']['present'], 'vkd3d-missing',
                  components['vkd3d-proton']['version'] or '')
            check('dxvk-nvapi', components['dxvk-nvapi']['present'], 'nvapi-missing',
                  components['dxvk-nvapi']['version'] or '')
        check('d3d12-enabled', not (_truthy(env.get('PROTON_NO_D3D12')) or _truthy(env.get('PROTON_USE_WINED3D'))),
              'vkd3d-disabled')
        disabled = _truthy(env.get('PROTON_DISABLE_NVAPI')) and not _truthy(env.get('PROTON_FORCE_NVAPI'))
        check('nvapi-enabled', not disabled, 'nvapi-disabled')
        files = prefix_files(prefix)
        # Proton copies nvapi64.dll on every run where NVAPI is enabled and
        # deletes it where it is disabled, so its presence reflects the last run.
        check('nvapi-prefix', files['nvapi64.dll'], 'nvapi-not-in-prefix')
        check('ngx-prefix', files['nvngx.dll'] and files['_nvngx.dll'], 'ngx-not-in-prefix')
        if mode in ('nr-mfg', 'mfg-only') and not native_mfg and tool['lib_dir'] is not None:
            has_cuda = (Path(tool['lib_dir']) / NVCUDA).is_file()
            if check('nvcuda', has_cuda, None if has_cuda else cuda_missing_reason(prefix.parent)):
                check('cuda-enabled', cuda_planned or prefix_cuda(prefix) or cuda_requested(tool['lib_dir'], env),
                      'cuda-off')
    return _finish(checks, tool, components, card)


def feeder_detect(prefix, launch_options='', driver_root=None, driver_dirs=None):
    """Read-only report for the Feeder route (ReShade + DLSS5 Feeder/RenoDX, DX11 through DXVK).

    The pieces it would need are reported, but the route is never offered on
    Linux yet: ReShade's depth/present behaviour and the Feeder's NGX path under
    DXVK have not been shown in a moving scene under Proton.
    """
    report = detect(prefix, 'nr-only', launch_options, driver_root=driver_root, driver_dirs=driver_dirs)
    present = (report.get('components') or {}).get('dxvk', {}).get('present')
    if prefix and (Path(prefix) / 'user.reg').is_file():
        report['checks'].append({'id': 'dxvk', 'state': 'ok' if present else 'missing', 'required': True,
                                 'reason': None if present else 'dxvk-missing',
                                 'detail': '' if present else REASONS['dxvk-missing']})
        if not present:
            report['reasons'].append('dxvk-missing')
    report['prerequisites_met'] = not report['reasons']
    report['offered'] = False
    report['offer_reason'] = REASONS['feeder-linux-unverified']
    report['label'] = 'Feeder under Proton is not offered yet'
    return report


def _finish(checks, tool, components, card):
    reasons = [c['reason'] for c in checks if c['required'] and c['state'] != 'ok']
    return {
        'schema': 1,
        'checks': checks,
        'reasons': reasons,
        # Shown beside the result; they never block (for example RTX 50 MFG not yet verified).
        'notes': [c['reason'] for c in checks if not c['required'] and c['state'] == 'note'],
        'prerequisites_met': not reasons,
        # Presence is not proof. Only a recorded real Proton session sets this.
        'runtime_verified': False,
        'tool': {'version': (tool or {}).get('version'), 'lib_dir': str((tool or {}).get('lib_dir') or '') or None},
        'components': components,
        'gpu': card,
        'label': 'Prerequisites found · Linux runtime not yet verified' if not reasons else 'Not ready under Proton',
    }


EVIDENCE_NAME = 'proton-runtime-evidence.json'


def evidence(state_dir, appid, tool_version, gpu_model, component_id):
    """A recorded real-session observation for this exact game/Proton/GPU/component, or None.

    Records are written only from a human-confirmed in-game session
    (record_evidence); file presence or this report alone never creates one.
    """
    text = _read(Path(state_dir) / EVIDENCE_NAME)
    try:
        records = json.loads(text) if text else []
    except ValueError:
        return None
    for record in records if isinstance(records, list) else []:
        if (isinstance(record, dict) and record.get('appid') == str(appid) and record.get('tool') == tool_version
                and record.get('gpu') == gpu_model and record.get('component') == component_id
                and record.get('confirmed_by') and record.get('observed')):
            return record
    return None


def record_evidence(state_dir, appid, tool_version, gpu_model, component_id, observed, confirmed_by):
    """Append a human-confirmed real Proton session. Refuses anonymous or empty observations."""
    if not (isinstance(observed, str) and observed.strip() and isinstance(confirmed_by, str) and confirmed_by.strip()):
        raise ValueError('Runtime evidence needs what was observed and who confirmed it.')
    path = Path(state_dir) / EVIDENCE_NAME
    text = _read(path)
    records = json.loads(text) if text else []
    record = {'appid': str(appid), 'tool': tool_version, 'gpu': gpu_model, 'component': component_id,
              'observed': observed.strip(), 'confirmed_by': confirmed_by.strip()}
    records.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(records, indent=1) + '\n', encoding='utf-8')
    temporary.replace(path)
    return record
