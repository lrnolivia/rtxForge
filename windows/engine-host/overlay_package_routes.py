"""Common overlay-review options and the owned Feeder update route."""
import copy
import json
import os
from pathlib import Path

import feeder_provider as feeder
import global_controls as bulk
import overlay_policy
import overlay_settings
import transactions as t


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
    if record.get('legacy_recipe'):
        return None, {'title': record.get('name') or root.name,
                      'detail': 'Uses the experimental DX9/DX10 Feeder recipe. Update it from Game Details.',
                      'details': 'The helper and translation layer are kept with this game\'s reviewed Feeder installation.'}
    t.need(path.parent == feeder.state_dir(e, target), 'Feeder record location differs.')
    t.need(not running(root), 'Close this game, then review again.')
    values = preferences(params, record, target)
    baseline = copy.deepcopy(record)
    owned = baseline['installed_hashes']
    checks = {str(path): t.sha(raw)}; writes = {}
    # Never silently adopt or replace a foreign add-on. Older installs without
    # a panel enter the ordinary repair flow, which captures their originals.
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
            missing.append(name)
            continue
        data = t.safe(item['path']).read_bytes()
        t.need(t.sha(data) == item['sha256'], 'Bundled Feeder panel changed.')
        checks[item['path']] = item['sha256']
        if t.sha(data) != owned[name]:
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
    writes[str(path)] = bulk._json(baseline)
    plan = {'name': name, 'game': str(root), 'root': str(root), 'target': str(target),
            'checks': checks, 'writes': writes, 'summary': 'Update Feeder overlay and menu settings', 'note': note}
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
            for filename, expected in record['installed'].items():
                destination = t.safe(target / t.relative(filename))
                if filename in mutable: continue
                t.need(t.digest(destination) == expected, 'Vulkan package files changed; repair first: '+filename)
                checks[str(destination)] = expected
            # The selected user's model is an independent owned input. An
            # overlay update never replaces it with the bundled model.
            for filename, data in payload.items():
                if filename in mutable or filename == 'NativeMods/nvngx_dlssnr.dll': continue
                t.need(filename in baseline['installed'], 'Vulkan inventory upgrade needs the full Repair Features review.')
                if t.sha(data) != baseline['installed'][filename]:
                    writes[str(target / filename)] = data
                    baseline['installed'][filename] = t.sha(data)
            values = preferences(params, {'game':str(root)}, target)
            note = 'Vulkan · Universal Experimental. NR model, tuning and original restore backups are preserved.'
            if values is not None: note += '\n\n'+overlay_settings.describe(values)
            if not writes:
                skipped.append({'title':name,'detail':'Vulkan overlay package is up to date.','details':note}); continue
            writes[str(path)] = bulk._json(baseline)
            plan = {'name':name,'game':str(root),'root':str(root),'target':str(target),
                    'checks':checks,'writes':writes,'summary':'Update Vulkan overlay package','note':note}
            bulk._check(e,plan); plans.append(plan)
        except (t.Refusal,e.Stop,OSError,ValueError,KeyError,TypeError) as error:
            blocked.append({'title':name,'detail':str(error),'details':''})
    return plans, blocked, skipped
