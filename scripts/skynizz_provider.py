"""Verified Skynizz releases and the single-loader Ada MFG bridge."""
from pathlib import Path
import hashlib
import configparser
import json
import math
from functools import lru_cache
import re
import stat
import struct
import urllib.request
import zipfile

import transactions as t
import package_catalog

ROOT = Path(__file__).resolve().parents[1]
REPO = 'Skynizz/optiscaler-dlss5'
API = 'https://api.github.com/repos/' + REPO
MAX_ARCHIVE = 128 * 1024**2
MAX_EXPANDED = 256 * 1024**2
PRODUCTION_RUNTIMES = {
    'sr_runtime': ('nvngx_dlss.dll', 'SR'),
    'rr_runtime': ('nvngx_dlssd.dll', 'RR'),
    'fg_runtime': ('nvngx_dlssg.dll', 'FG'),
}
FILES = {'OptiScaler.dll': 'dxgi.dll', 'OptiScaler.ini': 'OptiScaler.ini',
         'nvngx.dll_dlssnr.dll': 'nvngx.dll_dlssnr.dll'}
DEFAULTS = {
    'Upscalers': {'Dx12Upscaler': 'dlss'},
    'Log': {'LogToFile': 'true', 'LogLevel': '2'},
    'DlssNr': {'Enabled': 'true', 'CacheEnabled': 'true', 'CacheInterval': '1',
               'PreSr': 'true', 'WorkingScale': '0.65', 'JbuUpsample': 'true',
               'LocalStructure': '1.0', 'SkinStructure': '1.0',
               'CacheRefreshBlend': '1.0', 'WhitePointSource': '3'},
}


def require_mode(system, mode, fallback=False, bridge=False, proton=None):
    # Linux is allowed only per game, with the experimental opt-in and a passing
    # proton_mfg.gate report (every Proton prerequisite present). That is not
    # runtime verification; the review labels it experimental and unverified.
    t.need(system == 'windows' or (system == 'linux' and isinstance(proton, dict) and proton.get('opt_in') is True
                                   and proton.get('prerequisites_met') is True),
           'Skynizz is Windows-only in this release; Proton support is not verified.')
    t.need((mode == 'nr-only' or (mode in ('nr-mfg', 'mfg-only') and bridge)) and not fallback,
           'NR + MFG requires the combined Skynizz/Ada bridge build. Stock Skynizz supports NR Only; use the existing MFG package for MFG Only.')


def get_json(url):
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'rtxForge'})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(2 * 1024**2 + 1)
    t.need(len(raw) <= 2 * 1024**2, 'Release metadata exceeds the limit')
    return json.loads(raw)


def validate_production_runtime(record, component='sr_runtime'):
    filename, label = PRODUCTION_RUNTIMES[component]
    t.need(isinstance(record, dict), f'Production {label} runtime provenance is missing')
    commit = record.get('commit', '')
    t.need(record.get('repository') == 'NVIDIA/DLSS' and re.fullmatch(r'[0-9a-f]{40}', commit)
           and record.get('url') == f'https://raw.githubusercontent.com/NVIDIA/DLSS/{commit}/lib/Windows_x86_64/rel/{filename}'
           and re.fullmatch(r'[0-9a-f]{64}', record.get('sha256', ''))
           and re.fullmatch(r'\d+\.\d+\.\d+\.\d+', record.get('version', ''))
           and type(record.get('release_size')) is int and 64 < record['release_size'] <= MAX_ARCHIVE,
           f'Untrusted production {label} runtime identity')
    return dict(record)


def load_production_runtime(path, record, component='sr_runtime'):
    record = validate_production_runtime(record, component)
    label = PRODUCTION_RUNTIMES[component][1]
    path = Path(path)
    t.need(path.is_file() and not path.is_symlink() and path.absolute() == path.resolve()
           and path.stat().st_size == record['release_size'] and t.digest(path) == record['sha256'],
           f'Production {label} runtime size/type/hash mismatch')
    data = path.read_bytes()
    t.need(amd64(data) and hashlib.sha256(data).hexdigest() == record['sha256'],
           f'Production {label} runtime architecture/hash mismatch')
    return data


def validate_sr_runtime(record):
    return validate_production_runtime(record)


def load_sr_runtime(path, record):
    return load_production_runtime(path, record)


def mfg_component_module(record):
    """The module owning a recorded MFG component: Universal (OptiScaler plugin) or MFG Unlock (ReShade addon)."""
    import ada_mfg_provider
    import universal_mfg_provider
    return universal_mfg_provider if (record or {}).get('id') == universal_mfg_provider.ID else ada_mfg_provider


def validate_release(record):
    """Also validate saved releases before repair; never turn state into arbitrary URLs."""
    tag = record.get('tag', '')
    t.need(bool(re.fullmatch(r'v\d+\.\d+\.\d+', tag)), 'Choose latest or a stable Skynizz version such as v1.2.1.')
    if record.get('variant') == 'nr-mfg-bridge':
        if record.get('mfg_component'):
            mfg_component_module(record['mfg_component']).validate(record['mfg_component'])
        t.need(record.get('nr_preset') in (None, 0, 1, 2), 'Unsupported NR model preset')
        for component in PRODUCTION_RUNTIMES:
            if component in record:
                validate_production_runtime(record[component], component)
        name = 'rtxForge-Skynizz-' + tag + '-MFG.zip'
        t.need(record.get('repo') == 'lrnolivia/rtxForge' and record.get('archive') == name
               and record.get('url') == 'bundled:providers/skynizz-bridge/' + name,
               'Untrusted combined bridge identity')
        upstream = record.get('upstream') or {}
        t.need(upstream.get('repository') == REPO and upstream.get('tag') == tag
               and re.fullmatch(r'[0-9a-f]{40}', upstream.get('commit', ''))
               and re.fullmatch(r'[0-9a-f]{64}', record.get('patch_sha256', '')),
               'Combined bridge source provenance is incomplete')
        t.need(re.fullmatch(r'[0-9a-f]{64}', record.get('sha256', ''))
               and re.fullmatch(r'[0-9a-f]{40}', record.get('commit', ''))
               and type(record.get('release_size')) is int and 0 < record['release_size'] <= MAX_ARCHIVE,
               'Combined bridge archive provenance is incomplete')
        return dict(record, id='skynizz', family='skynizz', name='Skynizz NR + Ada MFG bridge', runtime_verified=False)
    name = 'OptiScaler-DLSS5-' + tag[1:] + '-win-x64.zip'
    t.need(record.get('repo') == REPO and record.get('archive') == name
           and record.get('url') == f'https://github.com/{REPO}/releases/download/{tag}/{name}',
           'Untrusted Skynizz release identity')
    t.need(bool(re.fullmatch(r'[0-9a-f]{64}', record.get('sha256', ''))), 'Skynizz release has no verified SHA-256 digest')
    t.need(type(record.get('release_size')) is int and 0 < record['release_size'] <= MAX_ARCHIVE,
           'Skynizz archive size is invalid')
    t.need(bool(re.fullmatch(r'[0-9a-f]{40}', record.get('commit', ''))), 'Skynizz release commit is missing')
    return dict(record, id='skynizz', family='skynizz', name='Skynizz DLSS 5 NR', runtime_verified=False)


def bundled_bridge(selection='latest'):
    """The app ships its exact compiled bridge, independently of mutable upstream releases."""
    t.need(selection == 'latest' or re.fullmatch(r'v\d+\.\d+\.\d+', selection or ''), 'Invalid bridge release selection')
    roots = [ROOT / 'providers/skynizz-bridge', ROOT / 'windows/out/skynizz-bridge']
    folder = next((path for path in roots if (path / 'package.json').is_file()), None)
    t.need(folder is not None, 'This app build does not contain the combined NR + MFG bridge. Use a build with the compiled bridge package.')
    record = json.loads((folder / 'package.json').read_text(encoding='utf-8-sig'))
    # The loader and each production runtime form one recorded recipe. Repair
    # retains those exact identities instead of resolving a newer runtime.
    lock = json.loads((ROOT / 'providers/lock.json').read_text(encoding='utf-8'))['skynizz']
    for component in PRODUCTION_RUNTIMES:
        record[component] = lock[component]
    record = validate_release(record)
    t.need(record.get('variant')=='nr-mfg-bridge','The bundled package is not the combined bridge')
    spec = json.loads((ROOT / 'providers/skynizz-bridge/source.json').read_text(encoding='utf-8'))
    matches = record['patch_sha256'] == spec['patch_sha256'] and record.get('bridge_id') == spec['id']
    if record.get('panel_candidate'):
        panel = json.loads((ROOT / 'providers/skynizz-bridge/panel-candidate.json').read_text(encoding='utf-8'))
        placement = json.loads((ROOT / 'providers/skynizz-bridge/placement-candidate.json').read_text(encoding='utf-8'))
        matches = (record.get('bridge_id') == panel['id'] and record.get('base_bridge_id') == spec['id']
                   and record.get('base_patch_sha256') == spec['patch_sha256']
                   and panel['base_bridge_id'] == placement['id']
                   and record['patch_sha256'] == placement['patch_sha256']
                   and record.get('route_header_sha256') == placement['header_sha256']
                   and record.get('panel_sources') == panel['sources'] and record.get('panel_renderer') == 'in-game')
    t.need(matches and record['upstream'] == spec['upstream'] and record.get('mfg_source') == spec['mfg_source'],
           'Bundled bridge does not match the admitted source patch')
    t.need(selection in ('latest', record['tag']), 'This Skynizz version has no compiled NR + MFG bridge in the app; keep the recorded version or update the app.')
    return dict(record, selected_source=selection), folder / record['archive']


def resolve(selection='latest'):
    t.need(isinstance(selection, str) and (selection == 'latest' or re.fullmatch(r'v\d+\.\d+\.\d+', selection)),
           'Choose latest or a stable Skynizz version such as v1.2.1.')
    release = get_json(API + ('/releases/latest' if selection == 'latest' else '/releases/tags/' + selection))
    tag = release.get('tag_name', '')
    t.need(not release.get('draft') and not release.get('prerelease')
           and re.fullmatch(r'v\d+\.\d+\.\d+', tag), 'A stable Skynizz release is required')
    t.need(selection == 'latest' or tag == selection, 'Release tag changed')
    name = f'OptiScaler-DLSS5-{tag[1:]}-win-x64.zip'
    assets = [asset for asset in release.get('assets', []) if asset.get('name') == name]
    t.need(len(assets) == 1, 'No unique supported Windows x64 Skynizz asset in this release')
    asset = assets[0]
    digest = asset.get('digest') or ''
    t.need(re.fullmatch(r'sha256:[0-9a-f]{64}', digest), 'GitHub did not publish a SHA-256 digest for this asset')
    ref = get_json(API + '/git/ref/tags/' + tag).get('object', {})
    if ref.get('type') == 'tag':
        ref = get_json(API + '/git/tags/' + ref['sha']).get('object', {})
    t.need(ref.get('type') == 'commit', 'Release tag does not resolve to a commit')
    return validate_release({'repo': REPO, 'tag': tag, 'archive': name, 'url': asset.get('browser_download_url'),
                             'sha256': digest[7:], 'release_size': asset.get('size'), 'asset_id': asset.get('id'),
                             'commit': ref.get('sha'), 'selected_source': selection})


def amd64(data):
    if len(data) < 64 or data[:2] != b'MZ':
        return False
    offset = struct.unpack_from('<I', data, 60)[0]
    return offset <= len(data) - 6 and data[offset:offset+4] == b'PE\0\0' and data[offset+4:offset+6] == b'\x64\x86'


def load_payload(archive, record):
    record = validate_release(record)
    archive = Path(archive)
    t.need(archive.is_file() and not archive.is_symlink() and archive.absolute() == archive.resolve()
           and archive.stat().st_size == record['release_size'],
           'Skynizz archive size/type mismatch')
    t.need(t.digest(archive) == record['sha256'], 'Skynizz archive SHA-256 mismatch')
    found, seen, total = {}, set(), 0
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        t.need(len(members) <= 1024, 'Skynizz archive has too many members')
        for member in members:
            package_catalog.relative(member.orig_filename.rstrip('/') if member.is_dir() else member.orig_filename)
            name = member.filename.rstrip('/')
            package_catalog.relative(name)
            t.need(name.casefold() not in seen, 'Case-colliding Skynizz archive member')
            seen.add(name.casefold())
            mode = member.external_attr >> 16
            t.need(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR) and not member.flag_bits & 1,
                   'Linked, special or encrypted Skynizz archive member')
            total += member.file_size
            t.need(total <= MAX_EXPANDED and member.file_size <= 64 * 1024**2, 'Expanded Skynizz archive exceeds the limit')
            parts = name.split('/')
            if not member.is_dir() and len(parts) == 2 and parts[0] == 'DLSS5-Optimised' and parts[1] in FILES:
                found[parts[1]] = source.read(member)
        if record.get('variant') == 'nr-mfg-bridge':
            t.need('DLSS5-Optimised/rtxforge-bridge.json' in source.namelist(),'Combined bridge source receipt is missing')
            marker = source.read('DLSS5-Optimised/rtxforge-bridge.json')
            t.need(len(marker) < 128 * 1024, 'Bridge receipt exceeds the limit')
            receipt = json.loads(marker.decode('utf-8-sig'))
            t.need(all(receipt.get(key) == record.get(key) for key in ('commit','patch_sha256','upstream','mfg_source','bridge_id')),
                   'Combined bridge payload/source receipt mismatch')
    t.need(set(found) == set(FILES), 'Unrecognized Skynizz payload layout; required loader, INI and NR forwarder must be present')
    t.need(amd64(found['OptiScaler.dll']) and amd64(found['nvngx.dll_dlssnr.dll']), 'Skynizz requires AMD64 PE payloads')
    ini = found['OptiScaler.ini'].decode('utf-8-sig')
    t.need('[DlssNr]' in ini and 'CacheEnabled=' in ini and 'PreSr=' in ini, 'Unsupported Skynizz configuration schema')
    t.need(t.digest(archive) == record['sha256'], 'Skynizz archive changed during extraction')
    return {FILES[name]: data for name, data in found.items()}, {
        **record, 'path': str(archive), 'provider': record['name'], 'release': record,
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in found.items()},
    }


def startup_overlay_disabled(game):
    return game is not None and (str(game.appid) == '2456740'
                                 or Path(game.exe or '').name.casefold() == 'inzoi-win64-shipping.exe')


# DLSS render presets: OptiScaler applies RenderPresetForAll only with RenderPresetOverride on.
RENDER_PRESETS = {'dlss_preset', 'rr_preset'}


@lru_cache(maxsize=1)
def control_schema():
    controls = json.loads((ROOT / 'providers/skynizz-bridge/controls.json').read_text(encoding='utf-8'))['controls']
    extension = json.loads((ROOT / 'providers/mfg-unlocker/preset-controls.json').read_text(encoding='utf-8'))['controls']
    keys = {control['key'] for control in controls}
    return controls + [item for item in extension if item['key'] not in keys]


def validate_controls(values):
    t.need(isinstance(values, dict), 'Feature presets must contain supported numeric controls.')
    definitions = {item['key']: item for item in control_schema()}
    t.need(set(values) <= set(definitions), 'An unsupported feature preset was requested.')
    for key, value in values.items():
        item = definitions[key]
        t.need(type(value) in (int, float) and math.isfinite(value) and item['min'] <= value <= item['max']
               and (item['kind'] == 'slider' or value == int(value))
               and ('values' not in item or value in item['values']), 'Choose a supported value for ' + item['label'] + '.')
    return dict(values)


def apply_controls(e, text, values, mode='nr-mfg', external_mfg=False):
    values = validate_controls(values)
    t.need(not (external_mfg and mode != 'nr-only' and values.get('dynamic_mfg')),
           'Dynamic Multi-Frame Generation requires the integrated MFG route. Choose Auto or Custom for this package.')
    for item in control_schema():
        key = item['key']
        if key not in values: continue
        if item['section'] == 'DlssNr' and mode == 'mfg-only': continue
        if item['group'] == 'Frame generation' and mode == 'nr-only': continue
        if item['section'] == 'DLSSG' and external_mfg: continue
        value = values[key]
        if key in RENDER_PRESETS:
            # Game default hands the choice back to the game; any preset needs the override on.
            text = e.set_ini_value(text, item['section'], 'RenderPresetOverride', 'true' if value else 'false')
            text = e.set_ini_value(text, item['section'], item['ini'], str(int(value)) if value else 'auto')
            continue
        if key == 'multiplier': value = 'auto' if value == -1 else str(max(0, int(value) - 1))
        elif key == 'sharpen_shader': value = ('rcas', 'da', 'lcda')[int(value)]
        elif item['kind'] == 'toggle': value = 'true' if value else 'false'
        elif item['kind'] != 'slider': value = str(int(value))
        else: value = format(value, '.8g')
        text = e.set_ini_value(text, item['section'], item['ini'], value)
    return text


def read_controls(path):
    path = Path(path)
    t.need(path.is_file() and not path.is_symlink() and path.stat().st_size < 2 * 1024**2, 'Game settings need repair.')
    parser = configparser.ConfigParser(interpolation=None, strict=True, inline_comment_prefixes=(';', '#'))
    parser.read_string(path.read_text(encoding='utf-8-sig'))
    values = {}
    for item in control_schema():
        raw = parser.get(item['section'], item['ini'], fallback='auto').casefold()
        if item['key'] in RENDER_PRESETS:
            override = parser.get(item['section'], 'RenderPresetOverride', fallback='auto').casefold()
            preset = int(raw) if override in ('true', '1') and raw.isdigit() else 0
            # A preset picked in OptiScaler's own menu that rtxForge does not list stays untouched.
            if preset in item['values']: values[item['key']] = preset
            continue
        if raw == 'auto' and item['key'] != 'multiplier': continue
        if item['key'] == 'multiplier': value = -1 if raw == 'auto' else 0 if int(raw) == 0 else int(raw) + 1
        elif item['key'] == 'sharpen_shader': value = ('rcas', 'da', 'lcda').index(raw)
        elif item['kind'] == 'toggle':
            t.need(raw in ('true', 'false', '0', '1'), 'An installed feature preset is invalid.')
            value = int(raw in ('true', '1'))
        else: value = float(raw) if item['kind'] == 'slider' else int(raw)
        values[item['key']] = value
    return validate_controls(values)


def configure(e, source, saved=None, mode='nr-only', mfg_multiplier='auto', game=None, controls=None):
    """Repair retains the complete user preset, including cache/placement choices."""
    text = (saved if saved is not None else source).decode('utf-8-sig')
    component = getattr(e, 'Y4MY_PROVIDER', {}).get('mfg_component')
    universal = bool(component) and mfg_component_module(component).ID == 'universal'
    # A ReShade-hosted addon owns the count; the Universal plugin leaves it to OptiScaler.
    external_mfg = bool(component) and not universal
    if saved is None:
        for section, values in DEFAULTS.items():
            for key, value in values.items():
                text = e.set_ini_value(text, section, key, value)
        if mode == 'nr-mfg':
            # Upstream issue #2 reports MFG pacing trouble with edit reuse.
            # Keep the pre-SR path, with cache reuse opt-in until runtime QA.
            text = e.set_ini_value(text, 'DlssNr', 'CacheEnabled', 'false')
        if (preset := getattr(e, 'Y4MY_PROVIDER', {}).get('nr_preset')) is not None:
            text = e.set_ini_value(text, 'DlssNr', 'Preset', str(preset))
    if mode in ('nr-mfg', 'mfg-only'):
        unlock = 'false' if component else 'true'
        for section, values in {'DLSSG':{'AdaMfgUnlock':unlock,'AdaBlackwellKernels':unlock,'AmpereMfgUnlock':'false'},
                                'FrameGen':{'Enabled':'false','FGInput':'nofg','FGOutput':'nofg','FGNvngxReplacement':'None'}}.items():
            for key, value in values.items():
                text = e.set_ini_value(text, section, key, value)
        if saved is None:
            for key, value in e.visual_defaults(2, mfg_multiplier, .5)['DLSSG'].items():
                text = e.set_ini_value(text, 'DLSSG', key, value)
        if external_mfg:
            # Only the addon owns the count, kernels and capability patches.
            for key, value in {'OverrideInterpolationCount': 'auto', 'OverrideForceDMFG': 'false'}.items():
                text = e.set_ini_value(text, 'DLSSG', key, value)
            text = e.set_ini_value(text, 'Plugins', 'LoadReShade', 'true')
            text = e.set_ini_value(text, 'Menu', 'OverlayMenu', 'false')
        if universal:
            import universal_mfg_provider
            text = universal_mfg_provider.configure(e, text)
            # Dynamic is offered only after this game's plugin confirms support.
            t.need(not (controls and controls.get('dynamic_mfg')
                        and (game is None or universal_mfg_provider.dynamic_support(game.target_dir) is not True)),
                   "This game hasn't confirmed Dynamic Multi-Frame Generation support. Choose Auto or Custom, then launch it to check.")
    if mode == 'nr-only' and getattr(e, 'Y4MY_PROVIDER', {}).get('variant') == 'nr-mfg-bridge':
        for key in ('AdaMfgUnlock', 'AdaBlackwellKernels', 'AmpereMfgUnlock'):
            text = e.set_ini_value(text, 'DLSSG', key, 'false')
    if mode == 'mfg-only':
        text = e.set_ini_value(text, 'DlssNr', 'Enabled', 'false')
    if controls is not None:
        text = apply_controls(e, text, controls, mode, external_mfg)
    # Skynizz bypasses the generic OptiScaler INI policy. Suppress its startup
    # splash on fresh installs and repairs without disabling the manual menu.
    text = e.set_ini_value(text, 'Menu', 'DisableSplash', 'true')
    if getattr(e, 'OVERLAY_UI', None) is not None:
        import overlay_policy
        text = overlay_policy.optiscaler(text, e.OVERLAY_UI, e.set_ini_value)
    if startup_overlay_disabled(game):
        # The swapchain overlay hangs inZOI before NR evaluation. The classic
        # menu path allows startup and leaves the native FG and NR routes on.
        text = e.set_ini_value(text, 'Menu', 'OverlayMenu', 'false')
    parser = configparser.ConfigParser(interpolation=None, strict=True, inline_comment_prefixes=(';', '#'))
    parser.optionxform = str
    try:
        parser.read_string(text)
    except configparser.Error as error:
        raise t.Refusal('Skynizz configuration could not be parsed: ' + str(error)) from error
    return text, dict(parser['DlssNr']) if parser.has_section('DlssNr') else {}


def restored_support_tree(e, game):
    """Recognize only exact inactive bytes retained by a completed engine restore.

    This is permission to back up the tree as original data, never to delete it
    or adopt an unrecorded live mod. The normal install/restore owns that backup.
    """
    target = game.target_dir
    tree = target / 'OptiScaler'
    if not tree.is_dir() or tree.is_symlink() or (target / 'OptiScaler.ini').exists():
        return False
    receipts = sorted(e._validated_state_dir(target).glob('baseline-restored-*.json'), reverse=True)
    if not receipts:
        return False
    receipt = receipts[0]
    if receipt.is_symlink() or receipt.stat().st_size > 1024 * 1024:
        return False
    try:
        record = json.loads(receipt.read_text(encoding='utf-8'))
        if (record.get('schema') != e.ENGINE_SCHEMA or record.get('status') != 'restored'
                or record.get('baseline_payload_retained') is not False
                or Path(record.get('target_dir', '')).resolve() != target.resolve()
                or Path(record.get('exe', '')).resolve() != Path(game.exe).resolve()):
            return False
        original = (record.get('originals') or {}).get('OptiScaler/') or {}
        proxy = (record.get('current') or {}).get('proxy')
        if (original.get('kind') != 'tree' or original.get('existed') is not True
                or not isinstance(proxy, str) or not proxy or Path(proxy).name != proxy
                or '/' in proxy or '\\' in proxy or ':' in proxy
                or (target / proxy).exists() or (target / proxy).is_symlink()):
            return False
        actual = e._tree_manifest_data(tree)
        return all(actual.get(key) == original.get(key) for key in ('tree_sha256', 'file_count', 'bytes'))
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def check_target(e, game, baseline):
    target = game.target_dir
    if component := e.Y4MY_PROVIDER.get('mfg_component'):
        mfg_component_module(component).check_target(e, game, baseline)
    t.need(not (target / 'renodx-dlss5.addon64').exists(),
           'Another NR consumer (renodx-dlss5.addon64) is present. Disable it yourself before installing Skynizz.')
    # A second OptiScaler cannot share this INI or the existing MFG hook tree.
    restored_tree = False
    if not baseline:
        restored_tree = restored_support_tree(e, game) if (target / 'OptiScaler').exists() else False
        t.need(not (target / 'OptiScaler.ini').exists() and (not (target / 'OptiScaler').exists() or restored_tree),
               'Existing OptiScaler configuration/runtime is unmanaged. Restore or remove it before installing Skynizz.')
        t.need(not (target / 'nvngx.dll_dlssnr.dll').exists(),
               'An unmanaged NR forwarder is already present. Restore or remove that installation before using Skynizz.')
    else:
        current = baseline.get('current') or {}
        t.need(not current or current.get('provider_id') == 'skynizz', 'Restore the existing provider before switching to Skynizz.')
    return restored_tree


def native_nr_refusal(exe, appid=None):
    # Larian documents DX11/Vulkan only; neither reaches this D3D12 NR hook.
    # https://larian.com/support/faqs/graphical-issues_83
    if str(appid) == '1086940' or Path(exe or '').name.casefold() in {'bg3.exe', 'bg3_dx11.exe'}:
        return 'Native NR needs DirectX 12. Baldur’s Gate 3 uses DirectX 11 or Vulkan; this package cannot provide NR here.'
    return ''


def scan_rows(rows, mode='nr-only'):
    for row in rows:
        if row.get('runtime_provider') == 'feeder' or row.get('install_provider') == 'feeder' and row.get('feeder_available') is True:
            continue
        if not row.get('exe'):
            row['blocked'] = 'No Windows executable found'
        elif row.get('anti_cheat') and not row.get('offline_only'):
            row['blocked'] = 'Anti-cheat detected'
        elif mode != 'mfg-only' and native_nr_refusal(row.get('exe'), row.get('appid')):
            row['blocked'] = native_nr_refusal(row.get('exe'), row.get('appid'))
        elif not row.get('native_dlss'):
            row['blocked'] = 'Skynizz needs a native DLSS Super Resolution route; D3D12/DLSS must be used in game.'
        elif mode == 'nr-mfg' and not row.get('native_dlssg'):
            row['blocked'] = 'The combined NR + MFG bridge requires game-native DLSS Frame Generation.'
        else:
            row['blocked'] = ''
        row['nr_route_note'] = 'Requires D3D12 with DLSS enabled · combined-build runtime validation pending' if mode == 'nr-mfg' else 'NR Only · requires D3D12 with DLSS enabled'
    return rows
