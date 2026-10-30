"""Windows DX9/DX10 and x86 Feeder recipes using upstream's split helper.

The x86 game never receives an x64 hook. DX9 translates to DX11 with a
separately verified local dgVoodoo import; DX10 uses the helper directly.
Every changed file belongs to the existing Feeder transaction and restore.
"""
import copy
import json
from pathlib import Path
import re
import struct
import zipfile
import urllib.request

import transactions as t

RECIPES = {'x86-d3d9', 'x64-d3d9', 'x86-d3d10', 'x64-d3d10', 'x86-d3d11'}


def lock():
    return t.read_json(Path(__file__).resolve().parents[1] / 'providers/feeder-legacy.json')


def machine(path):
    with Path(path).open('rb') as stream:
        header = stream.read(64)
        t.need(len(header) == 64 and header[:2] == b'MZ', 'Choose a Windows game executable')
        offset = struct.unpack_from('<I', header, 60)[0]
        t.need(64 <= offset <= 1024**2, 'Invalid PE header offset')
        stream.seek(offset)
        pe = stream.read(6)
        t.need(pe[:4] == b'PE\0\0', 'Invalid PE signature')
        value = int.from_bytes(pe[4:], 'little')
        t.need(value in (0x14c, 0x8664), 'Feeder requires an x86 or x64 Windows game')
        return value


def route(e, row):
    import feeder_provider as f
    _, exe, directory = f.target(row)
    state_path = f.state_dir(e, directory) / 'baseline.json'
    if state_path.is_file() and state_path.stat().st_size <= 1024**2:
        saved = t.read_json(state_path)
        if saved.get('status') != 'restored' and saved.get('legacy_recipe') in RECIPES:
            return saved['legacy_recipe']
    bits = 'x86' if machine(exe) == 0x14c else 'x64'
    apis = f.graphics_apis(e, exe)
    # Prefer a native DX11/12 route when an executable includes alternatives.
    api = next((api for api in ('d3d11', 'd3d12', 'd3d10', 'd3d10_1', 'd3d9') if api in apis), None)
    if api == 'd3d10_1':
        api = 'd3d10'
    selected = f'{bits}-{api}'
    return selected if selected in RECIPES else None


def helper(recipe):
    return recipe != 'x64-d3d9'


def runtime(directory, recipe):
    return directory / 'host64' if helper(recipe) else directory


def layout(recipe):
    """Destination -> verified import name. Base assets use a base: prefix."""
    import feeder_provider as f
    t.need(recipe in RECIPES, 'Unknown Feeder recipe')
    base = f.lock()
    shaders = {name: 'base:' + name for name in base['assets'] if name.startswith('reshade-shaders/')}
    if helper(recipe):
        files = {'dxgi.dll': 'reshade32.dll' if recipe.startswith('x86-') else 'reshade64.dll',
                 'dlss5-feed.addon32' if recipe.startswith('x86-') else 'dlss5-feed-helper.addon64':
                     'dlss5-feed.addon32' if recipe.startswith('x86-') else 'dlss5-feed-helper.addon64',
                 'host64/dlss5-feed-host64.exe': 'dlss5-feed-host64.exe',
                 'host64/dxgi.dll': 'base:dxgi.dll',
                 'host64/renodx-dlss5.addon64': 'base:renodx-dlss5.addon64',
                 'host64/nvngx_dlss.dll': 'base:nvngx_dlss.dll', **shaders}
    else:
        files = {name: 'base:' + name for name in base['assets']}
    if recipe.endswith('d3d9'):
        files['d3d9.dll'] = 'd3d9-x86.dll' if recipe.startswith('x86-') else 'd3d9-x64.dll'
    return files


def config_names(recipe):
    names = {'ReShade.ini', 'ReShadePreset.ini', 'dlss5-feed.cfg'}
    if helper(recipe):
        names |= {'host64/ReShade.ini', 'host64/ReShadePreset.ini'}
    if recipe.endswith('d3d9'):
        names.add('dgVoodoo.conf')
    return names


def model_name(recipe):
    return ('host64/' if helper(recipe) else '') + 'nvngx_dlssnr.dll'


def names(recipe):
    return set(layout(recipe)) | config_names(recipe) | {model_name(recipe)} | set(panel_names(recipe))


def panel_names(recipe):
    import feeder_provider as f
    prefix = 'host64/' if helper(recipe) else ''
    return {prefix + name: name for name in f.PANELS + f.OPTIONAL_PANELS}


def spec_for(name):
    import feeder_provider as f
    return f.lock()['assets'][name[5:]] if name.startswith('base:') else lock()['assets'][name]


def store_path(e):
    return e.STATE_ROOT / 'feeder-legacy-stack/stack.json'


def owned_assets(e):
    import feeder_provider as f
    path = store_path(e)
    if not path.is_file():
        return None
    t.need(path.stat().st_size <= 1024**2, 'Legacy Feeder record is too large')
    record = t.read_json(t.safe(path))
    spec = lock()
    t.need(record.get('schema') == 1 and record.get('recipe') == spec['id'] and isinstance(record.get('files'), dict)
           and set(record['files']) <= set(spec['assets']), 'The stored legacy Feeder recipe is invalid')
    for name, item in record['files'].items():
        cached = f.cached_input(e, item)
        expected = spec['assets'][name]
        t.need(f.digest(cached, cached=True) == expected['sha256'] and cached.stat().st_size == expected['size'],
               'Stored legacy Feeder component changed: ' + name)
    return record


def download_assets(e):
    """Fetch pinned public archives into app storage, without running an installer."""
    import feeder_provider as f
    import packages
    import ui
    spec = lock()
    files = {}
    for source in spec['sources']:
        if not source.get('members'):
            continue
        ui.progress('Getting ' + source['name'], phase='legacy-download')
        destination = e.STATE_ROOT / 'packages' / source['archive_sha256'] / source['archive_name']
        request = urllib.request.Request(source['download_url'], headers={'User-Agent': 'rtxForge/1.0 (+https://github.com/lrnolivia/rtxForge)'})
        archive = packages.download(request, destination,
                                    expected=source['archive_sha256'], size=source['archive_size'])
        with zipfile.ZipFile(archive) as zipped:
            for member, name in source['members'].items():
                entries = [entry for entry in zipped.infolist() if entry.filename == member]
                expected = spec['assets'][name]
                t.need(len(entries) == 1 and not entries[0].is_dir() and entries[0].file_size == expected['size'],
                       'The support archive has an unexpected file: ' + member)
                data = zipped.read(entries[0])
                t.need(t.sha(data) == expected['sha256'], 'The support file changed: ' + name)
                path = t.safe(e.STATE_ROOT / 'feeder-cache' / expected['sha256'])
                if not path.exists():
                    t.atomic_file(path, data, 0o600)
                if expected.get('machine'):
                    t.need(machine(path) == expected['machine'], 'Wrong support-file architecture: ' + name)
                files[name] = f.cache(e, path)
    t.need(set(files) == set(spec['assets']), 'The legacy support download is incomplete')
    record = {'schema': 1, 'recipe': spec['id'], 'files': files}
    t.atomic_file(store_path(e), (json.dumps(record, indent=2) + '\n').encode(), 0o600)
    return owned_assets(e)


def import_assets(e, source):
    """An optional legacy/ directory beside the existing local stack."""
    import feeder_provider as f
    source = t.safe(source) / 'legacy'
    if not source.is_dir():
        return None
    files = dict((owned_assets(e) or {}).get('files', {}))
    for name, spec in lock()['assets'].items():
        path = t.safe(source / name)
        if not path.exists():
            continue
        t.need(path.is_file() and path.stat().st_size == spec['size'] and f.digest(path) == spec['sha256'],
               'Legacy Feeder import is missing or changed: ' + name)
        if spec.get('machine'):
            t.need(machine(path) == spec['machine'], 'Wrong architecture: ' + name)
        files[name] = f.cache(e, path)
    t.need(files, 'No verified legacy Feeder files were found')
    record = {'schema': 1, 'recipe': lock()['id'], 'files': files}
    t.atomic_file(store_path(e), (json.dumps(record, indent=2) + '\n').encode(), 0o600)
    return record


def inputs(e, settings, recipe):
    import feeder_provider as f
    base = f.stack_files(e, settings)
    source = settings.get('feeder_source')
    if source and Path(source).is_dir():
        import_assets(e, source)
    path = store_path(e)
    t.need(path.is_file() and path.stat().st_size <= 1024**2,
           'Import the DX9/DX10 Feeder files in the local stack\'s legacy folder in Packages first')
    record = t.read_json(path)
    t.need(record.get('schema') == 1 and record.get('recipe') == lock()['id'] and isinstance(record.get('files'), dict),
           'The stored legacy Feeder recipe is invalid')
    result = {}
    for dest, name in layout(recipe).items():
        item = base.get(name[5:]) if name.startswith('base:') else record['files'].get(name)
        t.need(item is not None, 'Import the legacy Feeder component: ' + name)
        cached = f.cached_input(e, item)
        spec = spec_for(name)
        t.need(f.digest(cached) == spec['sha256'] and cached.stat().st_size == spec['size'],
               'Stored Feeder component changed: ' + name)
        result[dest] = item
    result.update({dest: item for dest, name in panel_names(recipe).items()
                   if (item := f.panel(e).get(name)) is not None})
    if recipe.endswith('d3d9'):
        item = record['files'].get('dgVoodoo.conf')
        t.need(item is not None and f.digest(f.cached_input(e, item)) == lock()['assets']['dgVoodoo.conf']['sha256'],
               'Import the verified dgVoodoo configuration')
        result['dgVoodoo.conf'] = item
    return result


def validate_state(e, directory, record):
    import feeder_provider as f
    recipe = record.get('legacy_recipe')
    t.need(recipe in RECIPES and record.get('schema') == 1 and record.get('provider_id') == 'feeder'
           and Path(record.get('target') or '').resolve() == directory, 'Legacy Feeder record identity differs')
    allowed = names(recipe)
    parents = {p.as_posix() for name in allowed for p in Path(name).parents if p.as_posix() != '.'}
    t.need(isinstance(record.get('created_directories', []), list)
           and set(record.get('created_directories', [])) <= parents, 'Legacy Feeder directory ownership is invalid')
    t.need(isinstance(record.get('originals'), dict)
           and allowed - set(panel_names(recipe)) <= set(record['originals']) <= allowed
           and isinstance(record.get('installed_hashes'), dict)
           and set(record['installed_hashes']) <= set(record['originals']), 'Legacy Feeder ownership record is incomplete')
    for item in record['originals'].values():
        if item is not None:
            f.cached_input(e, item)
    return record


def inspect(e, row, record, cached=True):
    import feeder_provider as f
    _, _, directory = f.target(row)
    recipe = record['legacy_recipe']
    validate_state(e, directory, record)
    t.need(record.get('status') == 'active', 'The Feeder installation needs recovery')
    for name, expected in record['installed_hashes'].items():
        if name not in config_names(recipe):
            t.need(f.digest(directory / name, cached) == expected, 'An installed Feeder file changed: ' + name)
    nr = f.model(directory / model_name(recipe))
    return {'managed': True, 'nr_runtime': nr, **f.configured(runtime(directory, recipe), directory)}


def verify_written(directory, recipe):
    import feeder_provider as f
    for dest, source in layout(recipe).items():
        spec = spec_for(source)
        path = directory / dest
        t.need(f.digest(path) == spec['sha256'] and path.stat().st_size == spec['size'], 'Legacy Feeder write changed: ' + dest)
    f.model(directory / model_name(recipe))
    for name in config_names(recipe) - {'dgVoodoo.conf', 'dlss5-feed.cfg'}:
        f._read_ini(directory / name)


def cleanup_directories(directory, baseline):
    """Remove only recorded, empty recipe directories; runtime logs are kept."""
    for name in sorted(baseline.get('created_directories', []), key=lambda name: len(Path(name).parts), reverse=True):
        path = t.safe(directory / t.relative(name))
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


def _cached_text(e, text):
    import feeder_provider as f
    path = t.safe(e.STATE_ROOT / 'feeder-cache' / t.sha(text.encode()))
    if not path.exists():
        t.atomic_file(path, text.encode(), 0o600)
    return f.cache(e, path)


def configuration(e, settings, recipe, files):
    import feeder_provider as f
    import overlay_policy
    root_ini = '[GENERAL]\nEffectSearchPaths=.\\reshade-shaders\\Shaders\\**\nTextureSearchPaths=.\\reshade-shaders\\Textures\\**\nPresetPath=.\\ReShadePreset.ini\n[ADDON]\nAddonPath=.\\\n'
    host_ini = '[GENERAL]\nPresetPath=.\\ReShadePreset.ini\n[ADDON]\nAddonPath=.\\\n'
    root_ini = overlay_policy.reshade(root_ini, settings) if overlay_policy.explicit(settings) else root_ini
    control_ini = host_ini if helper(recipe) else root_ini
    control_ini = f.configure_new_install(control_ini, settings.get('nr_on_launch', False))
    if settings.get('apply_requested_presets'):
        control_ini = f.apply_tuning(control_ini, settings)
    if helper(recipe) and overlay_policy.explicit(settings):
        control_ini = overlay_policy.reshade(control_ini, settings)
    preset = 'Techniques=Lumenite_Kernel@lumenite_Kernel.fx,DLSS5_Feed@DLSS5_Feed.fx\n'
    texts = {'ReShade.ini': root_ini if helper(recipe) else control_ini,
             'ReShadePreset.ini': preset,
             'dlss5-feed.cfg': 'enabled=1\nhost_window=0\nhost_gpu_priority=0\n'}
    if helper(recipe):
        texts |= {'host64/ReShade.ini': control_ini, 'host64/ReShadePreset.ini': 'Techniques=\n'}
    if recipe.endswith('d3d9'):
        text = Path(files['dgVoodoo.conf']['path']).read_text(encoding='utf-8-sig')
        prefix = '[rtxForge.DgVoodooGlobals]\n'
        text = prefix + text
        # Upstream's config has an unsectioned Version key; preserve the full
        # supplied configuration and replace only the documented route keys.
        for section, values in {'General': {'OutputAPI': 'd3d11_fl11_0'}, 'DirectX': {
                'DisableAndPassThru': 'false', 'VRAM': '1024', 'VideoCard': 'internal3D', 'dgVoodooWatermark': 'true'}}.items():
            t.need(t.section(text, section) is not None, 'dgVoodoo configuration section is missing: ' + section)
            for name, value in values.items():
                text = t.setvalue(text, section, name, value)
        texts['dgVoodoo.conf'] = text.removeprefix(prefix)
    return {name: _cached_text(e, text) for name, text in texts.items()}


def check(e, plan):
    import feeder_provider as f
    f.eligible(e, plan['row'], existing=plan['existing'])
    scan = getattr(e, 'scan_game_files', None)
    if scan:
        import offline_routes
        t.need(scan(Path(plan['row']['game']))[2] is None or offline_routes.reviewed_route(plan['row']) is not None,
               'Review and acknowledge offline-only use before changing this anti-cheat game.')
    directory = Path(plan['target'])
    t.need(f.digest(Path(plan['row']['game']) / plan['row']['exe']) == plan['exe_hash'], 'Game executable changed since review')
    t.need(f._checks(directory, plan['checks']) == plan['checks'], 'Feeder files changed since review; review again')
    t.need(f.digest(f.state_dir(e, directory) / 'baseline.json') == plan['baseline_before'], 'Feeder install record changed since review')
    for item in plan['inputs'].values():
        t.need(f.digest(f.cached_input(e, item)) == item['sha256'], 'Feeder source or original backup changed since review')


def prepare(e, row, mode, operation, settings, recipe):
    import feeder_provider as f
    t.need(mode == 'nr-only' or operation == 'uninstall', 'Feeder provides NR Only. Frame generation is not available for this route')
    t.need(f._windows(e), 'DX9/DX10 Feeder setup is available on Windows only in this release')
    _, exe, directory = f.target(row)
    record = f.state(e, directory)
    current = record if record and record.get('status') != 'restored' else None
    t.need(not current or current.get('legacy_recipe') == recipe, 'Restore the existing Feeder recipe before switching routes')
    existing = current is not None
    f.eligible(e, row, existing=existing)
    if existing:
        inspect(e, row, current, cached=False)
    t.need(operation in ('install', 'repair', 'uninstall', 'apply'), 'Unsupported legacy Feeder operation')
    t.need(existing or operation == 'install', 'Install this Feeder recipe first')
    allowed = names(recipe)
    writes, sources = {}, {}
    baseline = copy.deepcopy(current)
    if operation == 'uninstall':
        writes = dict(current['originals'])
        sources = {name: item for name, item in writes.items() if item}
        summary = 'Restore every original DX9/DX10 Feeder file, including the translation layer and helper.'
    elif operation == 'apply':
        name = ('host64/' if helper(recipe) else '') + 'ReShade.ini'
        text = (directory / name).read_text(encoding='utf-8-sig')
        changed = f.apply_tuning(text, settings)
        t.need(changed != text, 'This game already uses these settings')
        writes[name] = sources[name] = _cached_text(e, changed)
        summary = 'Save Feeder presets for the next launch.'
    else:
        payload = inputs(e, settings, recipe)
        model_path = settings.get('nr_runtime') or (current or {}).get('nr_runtime', {}).get('cache', {}).get('path')
        if not model_path:
            model_path = f.stack_files(e, settings).get(f.MODEL, {}).get('path')
        t.need(model_path, 'Choose a verified NR model for your GPU in Settings')
        nr = f.model(Path(model_path))
        payload[model_name(recipe)] = f.cache(e, Path(model_path))
        if not existing:
            # This route does not adopt unmanaged graphics hooks or commandeer
            # a pre-existing host64 folder.
            host = directory / 'host64'
            retained_logs = False
            if helper(recipe) and host.exists() and record and record.get('status') == 'restored' and record.get('legacy_recipe') == recipe:
                entries = list(host.iterdir())
                retained_logs = len(entries) <= 64 and all(t.safe(entry).is_file() and re.fullmatch(
                    r'(?i)(?:ReShade\.log\d*|dlss5-feed-host\.log(?:\.\d+)?|RenoDX-DLSS5-crash\.log)', entry.name) for entry in entries)
            t.need(not host.exists() or retained_logs if helper(recipe) else True,
                   'A host64 folder already exists. Restore its graphics mod before installing Feeder')
            t.need(not any((directory / name).exists() for name in (*t.PROXIES, 'ReShade.ini', 'dlss5-feed.addon32',
                       'dlss5-feed.addon64', 'dlss5-feed-helper.addon64', 'renodx-dlss5.addon64')),
                   'Other graphics mods are present. Restore them before installing this Feeder recipe')
            payload |= configuration(e, settings, recipe, payload)
            originals = {name: f.cache(e, directory / name) if (directory / name).exists() else None for name in allowed}
            missing_dirs = {p.as_posix() for name in allowed for p in Path(name).parents
                            if p.as_posix() != '.' and not (directory / p).exists()}
            baseline = dict(schema=1, provider_id='feeder', status='active', target=str(directory),
                            game=row['game'], exe=row['exe'], name=row['name'], appid=row.get('appid'),
                            legacy_recipe=recipe, originals=originals, installed_hashes={}, created_utc=t.now(),
                            created_directories=sorted(missing_dirs))
        else:
            payload.pop('dgVoodoo.conf', None)  # preserve the user's translation and depth tuning
            for name in panel_names(recipe):
                if name in payload and name not in baseline['originals']:
                    t.need(not (directory / name).exists(), 'An unowned panel is present: ' + name)
                    baseline['originals'][name] = None
            if operation == 'install' and type(settings.get('nr_on_launch')) is bool:
                control_name = ('host64/' if helper(recipe) else '') + 'ReShade.ini'
                text = (directory / control_name).read_text(encoding='utf-8-sig')
                changed = t.setvalue(text, 'RenoDX.DLSS5', 'NeuralUplift', '1' if settings['nr_on_launch'] else '0')
                if changed != text:
                    payload[control_name] = _cached_text(e, changed)
        writes = {name: item for name, item in payload.items() if f.digest(directory / name) != item['sha256']}
        sources = dict(writes)
        baseline['nr_runtime'] = {**nr, 'cache': payload[model_name(recipe)]}
        baseline['updated_utc'] = t.now()
        summary = f'Install Feeder NR · {recipe} · experimental.' if not existing else f'Update Feeder NR · {recipe}.'
        summary += f" NR model: {nr['version']}."
        if recipe.endswith('d3d9'):
            summary += ' Translate DirectX 9 to DirectX 11 with dgVoodoo2; its watermark confirms the wrapper is active.'
        if helper(recipe):
            summary += ' The game sends frames to a separate 64-bit helper. Use borderless mode for its panel.'
        summary += ' Frame generation is unavailable. A moving-scene NR test is still required.'
    checks = f._checks(directory, allowed)
    plan = dict(row=dict(row), target=str(directory), existing=existing, checks=checks,
                baseline_before=f.digest(f.state_dir(e, directory) / 'baseline.json'), baseline=baseline,
                inputs=sources, writes=writes, operation=operation, legacy_recipe=recipe, exe_hash=f.digest(exe))
    check(e, plan)
    detail = json.dumps({'target': str(directory), 'recipe': recipe, 'runtime_verified': False,
                         'writes': {name: item['sha256'] if item else None for name, item in writes.items()}}, indent=2)
    return plan, {'name': row['name'], 'game': row['game'], 'summary': summary, 'detail': detail}
