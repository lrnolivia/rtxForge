"""Common overlay-review options and the owned Feeder update route."""
import copy
import cross_os
import json
import os
from pathlib import Path

import feeder_provider as feeder
import global_controls as bulk
import overlay_policy
import overlay_settings
import transactions as t


def share_inventory(target, provider, owned, checks, writes, legacy_recipe=None):
    """Publish the same ownership inventory for the next OS in a shared library."""
    path = t.safe(target / cross_os.MARKER)
    raw = bulk._read(path) if path.exists() else None
    marker = json.loads(raw) if raw is not None else {}
    t.need(not marker or marker.get('provider', {}).get('id') == provider,
           'Another package owns this shared installation record.')
    oses = {cross_os.THIS_OS, *marker.get('installed_oses', [])}
    if marker.get('os') in cross_os.OPERATING_SYSTEMS: oses.add(marker['os'])
    marker.update(schema=cross_os.SCHEMA, os=cross_os.THIS_OS,
                  provider={'id':provider, 'name':'Feeder NR' if provider=='feeder' else 'Vulkan NR + Universal MFG'},
                  revision=cross_os.new_revision(), shared_state=False,
                  feature_mode='nr-only' if provider=='feeder' else 'nr-mfg',
                  proxy='dxgi.dll' if provider=='feeder' else 'bink2w64.dll',
                  proton_overrides=['dxgi'] if provider=='feeder' else ['bink2w64'],
                  installed_oses=[os for os in ('windows','linux') if os in oses],
                  files=dict(marker.get('files', {}), **owned))
    if legacy_recipe:
        marker['legacy_recipe']=legacy_recipe
        marker['proxy']='d3d9.dll' if legacy_recipe.endswith('d3d9') else 'dxgi.dll'
        marker['proton_overrides']=[Path(marker['proxy']).stem]
    checks[str(path)] = t.sha(raw) if raw is not None else None
    writes[str(path)] = bulk._json(marker)


def selected(params, *identities):
    if params is None or 'target_games' not in params:
        return True
    games = params['target_games']
    t.need(isinstance(games, list) and 0 < len(games) <= 1000
           and all(isinstance(g, str) and g for g in games), 'Choose games to update.')
    normalize = lambda p: os.path.normcase(str(Path(p).resolve()))
    return bool({normalize(g) for g in games} & {normalize(g) for g in identities if g})


def preferences(params, record, target):
    if params is None:
        return None
    return overlay_settings.effective(params, record.get('game') or record.get('game_dir') or target)


def menus(e, target, values, owned, checks, writes):
    """Change only requested INI keys; preserve all unrelated tuning."""
    if values is None:
        return
    for name in ('OptiScaler.ini', 'ReShade.ini'):
        if name not in owned:
            continue
        path = t.safe(target / name)
        original = bulk._read(path)
        checks[str(path)] = t.sha(original)
        text = original.decode('utf-8-sig')
        changed = (overlay_policy.optiscaler(text, values, e.set_ini_value) if name == 'OptiScaler.ini'
                   else overlay_policy.reshade(text, values)).encode('utf-8')
        if changed != original:
            writes[str(path)] = changed
            owned[name] = t.sha(changed)


def feeder_plan(e, path, params, running):
    raw = bulk._read(path)
    record = json.loads(raw)
    if record.get('status') != 'active' or record.get('provider_id') != 'feeder':
        return None, None
    target = t.safe(record['target']); root = t.safe(record['game'])
    if not selected(params, root, target):
        return None, None
    exe = root / record['exe']
    if not root.is_dir() or not exe.is_file():
        return None, None
    t.need(path.parent == feeder.state_dir(e, target), 'Feeder record location differs.')
    if record.get('legacy_recipe'):
        return legacy_feeder_plan(e, path, raw, record, params, running)
    t.need(not running(root), 'Close this game, then review again.')
    values = preferences(params, record, target)
    baseline = copy.deepcopy(record)
    owned = baseline['installed_hashes']
    checks = {str(path): t.sha(raw)}; writes = {}
    # New managed overlay files may be added only to empty destinations. A
    # foreign add-on is never adopted or replaced by the required refresh.
    available = feeder.panel(e)
    missing = []
    for name, expected in record['installed_hashes'].items():
        destination = t.safe(target / t.relative(name))
        if name in feeder.CONFIGS:
            continue
        t.need(feeder.digest(destination, cached=False) == expected, 'Feeder files changed; repair this game first: ' + name)
        checks[str(destination)] = expected
    for name, item in available.items():
        if name not in owned:
            destination=t.safe(target / name)
            actual = feeder.digest(destination, cached=False) if destination.exists() else None
            adoption = (params or {}).get('adopt_overlay_files', {}).get(str(destination))
            t.need(actual is None or actual == adoption, 'An unowned overlay file is present: ' + name)
            checks[str(destination)]=actual
            original = feeder.cache(e, destination) if actual is not None else None
            if original: checks[original['path']] = original['sha256']
            baseline.setdefault('originals', {}).setdefault(name, original)
        data = t.safe(item['path']).read_bytes()
        t.need(t.sha(data) == item['sha256'], 'Bundled Feeder panel changed.')
        checks[item['path']] = item['sha256']
        if t.sha(data) != owned.get(name):
            writes[str(target / name)] = data
            owned[name] = t.sha(data)
    menus(e, target, values, owned, checks, writes)
    name = record.get('name') or root.name
    note = 'Feeder NR · DirectX 11/12. Model, tuning and original restore backups are preserved.'
    if values is not None:
        note += '\n\n' + overlay_settings.describe(values)
    if missing:
        note += '\nUse Repair Features to add the overlay to this older installation.'
    if not writes:
        return None, {'title': name, 'detail': 'Overlay packages and menus are up to date.', 'details': note}
    share_inventory(target, 'feeder', owned, checks, writes)
    writes[str(path)] = bulk._json(baseline)
    plan = {'name': name, 'game': str(root), 'root': str(root), 'target': str(target),
            'checks': checks, 'writes': writes, 'summary': 'Update Feeder overlay and menu settings', 'note': note}
    bulk._check(e, plan)
    return plan, None


def legacy_feeder_plan(e, path, raw, record, params, running):
    import feeder_legacy as legacy
    target = t.safe(record['target']); root = t.safe(record['game'])
    legacy.validate_state(e, target, record)
    t.need(not running(root), 'Close this game, then review again.')
    baseline = copy.deepcopy(record); owned = baseline['installed_hashes']
    checks = {str(path): t.sha(raw)}; writes = {}
    for name, expected in owned.items():
        if name in legacy.config_names(record['legacy_recipe']): continue
        destination = t.safe(target / t.relative(name))
        t.need(feeder.digest(destination, cached=False) == expected, 'Feeder files changed; repair first: ' + name)
        checks[str(destination)] = expected
    available = feeder.panel(e)
    for name, source in legacy.panel_names(record['legacy_recipe']).items():
        if source not in available: continue
        destination = t.safe(target / name); actual = feeder.digest(destination, cached=False)
        if name not in baseline['originals']:
            t.need(actual is None, 'An unowned panel is present: ' + name)
            baseline['originals'][name] = None
        item = available[source]; data = t.safe(item['path']).read_bytes()
        t.need(t.sha(data) == item['sha256'], 'Bundled Feeder panel changed.')
        checks[str(destination)] = actual; checks[item['path']] = item['sha256']
        if actual != item['sha256']: writes[str(destination)] = data
        owned[name] = item['sha256']
    values = preferences(params, record, root)
    if values is not None:
        for name in legacy.config_names(record['legacy_recipe']):
            if not name.endswith('/ReShade.ini') and name != 'ReShade.ini': continue
            destination = t.safe(target / name); original = bulk._read(destination)
            changed = overlay_policy.reshade(original.decode('utf-8-sig'), values).encode('utf-8')
            checks[str(destination)] = t.sha(original)
            if changed != original: writes[str(destination)] = changed
            owned[name] = t.sha(changed)
    name = record.get('name') or root.name
    note = ('Feeder NR · ' + record['legacy_recipe'] + ' · experimental. '
            'Translation layer, helper, NR model, tuning and original restore backups are preserved.')
    if values is not None: note += '\n\n' + overlay_settings.describe(values)
    if not writes: return None, {'title': name, 'detail': 'Overlay packages and menus are up to date.', 'details': note}
    share_inventory(target, 'feeder', owned, checks, writes, record['legacy_recipe'])
    writes[str(path)] = bulk._json(baseline)
    plan = {'name': name, 'game': str(root), 'root': str(root), 'target': str(target),
            'checks': checks, 'writes': writes, 'summary': 'Update legacy Feeder overlay and menu settings', 'note': note}
    bulk._check(e, plan)
    return plan, None


def vulkan_plans(e, params, running):
    """Update only the known immutable overlay/runtime inventory, preserving NR models and all mutable files."""
    import vulkan_app
    import vulkan_dlssg_provider as native
    plans, blocked, skipped = [], [], []
    candidates = sorted((vulkan_app.state_root() / 'targets').glob('*/baseline.json'))
    t.need(len(candidates) <= 1000, 'Too many Vulkan installation records.')
    if not candidates:
        return plans, blocked, skipped
    folder, manifest, archive, spec = vulkan_app.bundled()
    for path in candidates:
        name = path.parent.name
        try:
            raw = bulk._read(path); record = json.loads(raw)
            if record.get('status') != 'active': continue
            profile = record.get('provider_id', '').removeprefix('rtxforge-vulkan-native:')
            t.need(profile in vulkan_app.PROFILES, 'Unknown Vulkan recovery profile.')
            target = t.safe(record['target']); root = target.parent if profile == 'bg3' and target.name.casefold() == 'bin' else target
            if not selected(params, root, target): continue
            name = vulkan_app.PROFILES[profile][1]
            t.need(path.parent == native.state_path(target, vulkan_app.state_root()), 'Vulkan record path differs.')
            t.need(not running(root), 'Close this game, then review again.')
            with native.profile(profile, manifest):
                # Checks original recovery objects, inventory, profile and all immutable ownership.
                native._record(target, path.parent)
                payload = native.payload(archive, folder / ('loader-'+profile) / 'bink2w64.dll')
                mutable = native._mutable()
            baseline = copy.deepcopy(record)
            checks = {str(path): t.sha(raw)}; writes = {}
            checks[str(manifest)] = t.digest(manifest); checks[str(archive)] = spec['archive']['sha256']
            loader = folder / ('loader-'+profile) / 'bink2w64.dll'
            checks[str(loader)] = spec['profiles'][profile]['loader']['binary']['sha256']
            retained_runtimes = set()
            production = t.read_json(vulkan_app.ROOT / 'providers/lock.json')['skynizz']
            for filename, expected in record['installed'].items():
                destination = t.safe(target / t.relative(filename))
                if filename in mutable: continue
                actual = t.digest(destination)
                runtime = {'NativeMods/Streamline/nvngx_dlssg.dll': 'fg_runtime',
                           'NativeMods/Streamline/nvngx_dlss.dll': 'sr_runtime',
                           'NativeMods/Streamline/nvngx_dlssd.dll': 'rr_runtime'}.get(filename)
                pin = production.get(runtime, {})
                verified_runtime = actual != expected and actual == pin.get('sha256') and destination.stat().st_size == pin.get('release_size')
                t.need(actual == expected or verified_runtime, 'Vulkan package files changed; repair first: '+filename)
                checks[str(destination)] = actual
                if verified_runtime:
                    retained_runtimes.add(filename)
                    baseline['installed'][filename] = actual
                    baseline.setdefault('runtime_overrides', {})[filename] = {key: pin[key] for key in ('sha256', 'version', 'commit', 'repository')}
                override = record.get('runtime_overrides', {}).get(filename)
                if override and all(override.get(key) == pin.get(key) for key in ('sha256', 'version', 'commit', 'repository')):
                    # Keep a deliberately selected production runtime through
                    # future package repairs, including an older app's rewrite.
                    retained_runtimes.add(filename)
                    if actual != pin['sha256']:
                        import packages
                        source = packages.download(pin['url'], e.STATE_ROOT/'packages'/pin['sha256']/Path(filename).name,
                                                   expected=pin['sha256'], size=pin['release_size'])
                        checks[str(source)] = pin['sha256']
                        writes[str(destination)] = source.read_bytes()
                        baseline['installed'][filename] = pin['sha256']
            # The selected user's model is an independent owned input. An
            # overlay update never replaces it with the bundled model.
            for filename, data in payload.items():
                if filename in mutable or filename == 'NativeMods/nvngx_dlssnr.dll' or filename in retained_runtimes or filename in baseline.get('runtime_overrides', {}): continue
                t.need(filename in baseline['installed'], 'Vulkan inventory upgrade needs the full Repair Features review.')
                if t.sha(data) != baseline['installed'][filename]:
                    writes[str(target / filename)] = data
                    baseline['installed'][filename] = t.sha(data)
            values = preferences(params, {'game':str(root)}, target)
            note = 'Vulkan · Universal Experimental. NR model, tuning and original restore backups are preserved.'
            if values is not None: note += '\n\n'+overlay_settings.describe(values)
            shared = cross_os.read(target)
            if not writes and baseline == record and shared and shared.get('shared_recovery',{}).get('readable') is True and record.get('cross_os_revision') == shared.get('revision'):
                skipped.append({'title':name,'detail':'Vulkan overlay package is up to date.','details':note}); continue
            share_inventory(target, vulkan_app.ID, baseline['installed'], checks, writes)
            marker_path = str(target/cross_os.MARKER)
            marker = json.loads(writes[marker_path])
            with native.profile(profile, manifest): native._record(target, path.parent)
            baseline, recovery_checks, recovery_writes = vulkan_app.recovery_export(target, path.parent, baseline, marker)
            checks.update(recovery_checks); writes.update(recovery_writes)
            writes[marker_path] = bulk._json(marker)
            writes[str(path)] = bulk._json(baseline)
            plan = {'name':name,'game':str(root),'root':str(root),'target':str(target),
                    'checks':checks,'writes':writes,'summary':'Update Vulkan overlay package','note':note}
            bulk._check(e,plan); plans.append(plan)
        except (t.Refusal,e.Stop,OSError,ValueError,KeyError,TypeError) as error:
            blocked.append({'title':name,'detail':str(error),'details':''})
    return plans, blocked, skipped
