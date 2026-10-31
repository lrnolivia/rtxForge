"""Reviewed native-overlay updates; keep tuning, runtimes and original backups."""
import copy
import hashlib
import json
import os
from pathlib import Path

import cross_os
import global_controls as bulk
import packages
import skynizz_provider as provider
import transactions as t
import ui
import overlay_package_routes as routes
import overlay_settings


def recipe(files, mode):
    immutable = {name.casefold(): digest for name, digest in files.items()
                 if not name.casefold().endswith(('.ini', '.log'))}
    return t.sha(json.dumps({'files': immutable, 'mode': mode}, sort_keys=True).encode())


def ownership(e, path, record):
    """Bind the local recipe to its shared inventory, allowing metadata-only drift."""
    target = t.safe(record['target_dir'])
    current = record['current']
    marker_path = target / cross_os.MARKER
    marker_raw = bulk._read(marker_path)
    marker = json.loads(marker_raw)
    shared = cross_os.shared_state(target) / 'baseline.json'
    shared_raw = bulk._read(shared) if shared.is_file() else None
    shared_record = json.loads(shared_raw) if shared_raw is not None else None
    t.need(marker.get('proxy') == current['proxy'] and marker.get('files') == current['installed_hashes'],
           'Installation ownership changed; repair this game first.')
    reconciled = (marker.get('provider', {}).get('id') != 'skynizz'
                  or marker.get('revision') != record.get('cross_os_revision'))
    if reconciled:
        portable = cross_os.portable(record, path.parent, target)
        t.need(marker.get('schema') == cross_os.SCHEMA and marker.get('shared_state') is True
               and marker.get('os') in cross_os.OPERATING_SYSTEMS
               and marker.get('provider', {}).get('id') in ('skynizz', 'dlss-unlocked')
               and marker.get('feature_mode') == current['feature_mode']
               and isinstance(shared_record, dict) and bool(marker.get('revision'))
               and shared_record.get('cross_os_revision') == marker['revision']
               and all(portable.get(key) == shared_record.get(key) for key in
                       ('schema', 'status', 'target_dir', 'exe', 'originals', 'managed_paths', 'appid'))
               and all(portable['current'].get(key) == (shared_record.get('current') or {}).get(key) for key in
                       ('provider_id', 'proxy', 'feature_mode', 'installed_hashes', 'mfg_provider'))
               and portable['current']['archive']['release'] == shared_record.get('current', {}).get('archive', {}).get('release'),
               'Shared installation differs from the local recipe; review Adapt or Repair first.')
        e.verify_baseline_integrity(target, record, adopt_legacy=False)
    elif shared_record is not None:
        t.need(shared_record.get('cross_os_revision') == record.get('cross_os_revision'),
               'Shared installation state changed; review again.')
    return marker_path, marker_raw, marker, shared, shared_raw, shared_record, reconciled


def shared_overlay_revision(e, path, record):
    """Read a compatible other-OS revision without mutating private restore state."""
    target = t.safe(record['target_dir'])
    marker = cross_os.adoptable(target, cross_os.THIS_OS, record.get('cross_os_revision'))
    if not marker or marker.get('provider', {}).get('id') != 'skynizz': return record, False
    shared = t.read_json(t.safe(cross_os.shared_state(target)/'baseline.json'))
    candidate = cross_os.localize(shared, path.parent, target)
    old, current = record.get('current') or {}, candidate.get('current') or {}
    portable = cross_os.portable(record, path.parent, target)
    t.need(candidate.get('status')=='active' and candidate.get('schema')==record.get('schema')
           and candidate.get('target_dir')==str(target) and candidate.get('exe')==record.get('exe')
           and candidate.get('cross_os_revision')==marker.get('revision')
           and current.get('provider_id')=='skynizz' and current.get('installed_hashes')==marker.get('files')
           and all(current.get(key)==old.get(key) for key in ('proxy','feature_mode')),
           'The other OS changed the package route. Review Adapt or Repair before updating it.')
    originals = shared.get('originals') or {}
    t.need(all(originals.get(key)==value for key,value in portable.get('originals',{}).items())
           and all(isinstance(value,dict) and value.get('existed') is False
                   for key,value in originals.items() if key not in portable.get('originals',{})),
           'The other OS changed restore ownership. Its verified backup adoption is required.')
    e.verify_baseline_integrity(target, record, adopt_legacy=False)
    e.verify_baseline_integrity(target, candidate, adopt_legacy=False)
    # Steam settings belong to this OS even when the DLL revision is shared.
    candidate.pop('steam_launch',None)
    if record.get('steam_launch'): candidate['steam_launch']=copy.deepcopy(record['steam_launch'])
    current['launch_options']=old.get('launch_options',current.get('launch_options'))
    return candidate, True


def prepare(e, state, params=None):
    if params is not None:
        overlay_settings.options(params)
        routes.selected(params)  # Validate an explicitly scoped, nonempty selection.
    bundled = None
    recovered = {}
    plans, blocked, skipped, seen = [], [], [], set()
    candidates = sorted((e.STATE_ROOT / 'targets').glob('*/baseline.json'))
    candidates += sorted((e.STATE_ROOT / 'feeder-targets').glob('*/baseline.json'))
    t.need(len(candidates) <= 1000, 'Too many installation records. Refresh your library.')
    running = bulk._process_check(e)
    for index, path in enumerate(candidates, 1):
        name = path.parent.name
        try:
            original = bulk._read(path); record = json.loads(original)
            if record.get('status') != 'active': continue
            name = record.get('name') or name
            if record.get('provider_id') == 'feeder':
                plan, unchanged = routes.feeder_plan(e, path, params, running)
                if plan: plans.append(plan)
                if unchanged: skipped.append(unchanged)
                continue
            record, adopted = shared_overlay_revision(e, path, record)
            current = record.get('current') or {}
            target = t.safe(record['target_dir']); exe = t.safe(record['exe'])
            t.need(path.parent == e.state_dir_for(target) and exe.parent == target, 'Installation identity differs.')
            root = target
            for parent in (target, *target.parents):
                if parent.parent.name.casefold() in ('common', 'pinnedbuilds'): root = parent; break
            if not routes.selected(params, root, target): continue
            if not target.is_dir() or not exe.is_file():
                continue
            if current.get('provider_id') != 'skynizz':
                skipped.append({'title': name, 'detail': 'Uses Feeder/ReShade.' if record.get('provider_id') == 'feeder'
                                else 'Uses a different MFG package.', 'details': 'The native overlay requires the Skynizz bridge; this loader is preserved.'})
                continue
            t.need(target not in seen, 'Duplicate game record.'); seen.add(target)
            if bundled is None:
                release, archive = provider.bundled_bridge()
                t.need(release.get('panel_renderer') == 'in-game', 'This build is missing the native overlay bridge.')
                payload, metadata = provider.load_payload(archive, release)
                cache = Path(state) / 'packages' / release['sha256'] / release['archive']
                cached = packages.download(archive.resolve().as_uri(), cache, expected=release['sha256'], size=release['release_size'])
                metadata['path'] = str(cached)
                bundled = release, payload, metadata, cached
            release, payload, metadata, cached = bundled
            t.need(not running(root), 'Close this game, then review again.')
            ui.progress('Checking overlay packages', game=name, current=index, total=len(candidates))
            old_release = provider.validate_release(current['archive']['release'])
            t.need(old_release.get('variant') == 'nr-mfg-bridge', 'This older NR package needs a reviewed package upgrade.')
            mode, proxy = current['feature_mode'], current['proxy']
            t.need(mode in ('nr-only', 'mfg-only', 'nr-mfg') and str(t.relative(proxy)) == proxy and '/' not in proxy,
                   'The installed loader identity is invalid.')
            owned = current['installed_hashes']
            marker_path, marker_raw, marker, shared, shared_raw, shared_record, reconciled = ownership(e, path, record)
            checks = {str(path): t.sha(original), str(marker_path): t.sha(marker_raw), str(cached): release['sha256']}
            writes = {}; baseline = copy.deepcopy(record)
            values = routes.preferences(params, record, root)
            details = ('\n\n' + overlay_settings.describe(values)) if values is not None else ''
            for filename, data in ((proxy, payload['dxgi.dll']), ('nvngx.dll_dlssnr.dll', payload['nvngx.dll_dlssnr.dll'])):
                destination = t.safe(target / filename)
                expected = owned.get(filename)
                actual = t.digest(destination) if destination.is_file() else None
                t.need(expected and actual in (None, expected),
                       'The installed bridge is missing or changed. Use Repair Features: ' + filename)
                checks[str(destination)] = actual
                if t.sha(data) != actual: writes[str(destination)] = data
                baseline['current']['installed_hashes'][filename] = marker['files'][filename] = t.sha(data)
            if 'rtxforge-glass.dll' in payload:
                filename='rtxforge-glass.dll'; destination=t.safe(target / filename)
                actual=t.digest(destination) if destination.exists() else None
                expected=owned.get(filename)
                t.need(actual == expected, 'An unowned or changed glass renderer is present. Repair this game first.')
                checks[str(destination)]=actual
                data=payload[filename]
                if actual != t.sha(data): writes[str(destination)]=data
                baseline.setdefault('originals', {}).setdefault(filename, {'kind':'file','existed':False})
                if filename not in baseline.setdefault('managed_paths', []): baseline['managed_paths'].append(filename)
                baseline['current']['installed_hashes'][filename]=marker['files'][filename]=t.sha(data)
            routes.menus(e, target, values, baseline['current']['installed_hashes'], checks, writes)
            marker['files'] = dict(baseline['current']['installed_hashes'])
            if not writes and old_release.get('sha256') == release['sha256'] and not reconciled and not adopted:
                skipped.append({'title': name, 'detail': 'Overlay packages and menus are up to date.', 'details': details}); continue
            for filename, expected in owned.items():
                if filename.casefold().endswith(('.ini', '.log')): continue
                destination = t.safe(target / t.relative(filename))
                if str(destination) in writes and str(destination) in checks:
                    continue  # Already bound to its observed bytes (or absence) above.
                if not destination.exists():
                    source = t.safe(e.STATE_ROOT / 'feeder-cache' / expected)
                    t.need(source.is_file() and source.stat().st_size <= 512 * 1024**2 and t.digest(source) == expected,
                           'The missing managed file needs a verified recovery download: ' + filename)
                    if expected not in recovered: recovered[expected] = source.read_bytes()
                    checks[str(destination)] = None; checks[str(source)] = expected
                    writes[str(destination)] = recovered[expected]
                    continue
                t.need(destination.is_file() and t.digest(destination) == expected, 'Package files changed; repair this game first: ' + filename)
                checks[str(destination)] = expected
            updated_release = dict(release)
            for key in ('mfg_component', 'nr_preset', *provider.PRODUCTION_RUNTIMES):
                if key in old_release: updated_release[key] = old_release[key]
            baseline['current']['archive'] = {**current['archive'], **metadata, 'release': updated_release}
            marker['provider'] = updated_release
            # Existing presets are tied to the exact recipe. Rebind only presets
            # that match the verified old recipe; do not revive stale presets.
            key = hashlib.sha256(os.path.normcase(str(exe)).encode()).hexdigest()
            preset_path = Path(state) / 'runtime-presets' / (key + '.json')
            if preset_path.is_file():
                raw = bulk._read(preset_path); saved = json.loads(raw)
                before_recipe,after_recipe=recipe(owned, mode),recipe(marker['files'], mode)
                changed=False
                if saved.get('recipe') == before_recipe:
                    saved['recipe'] = after_recipe;changed=True
                for entry in saved.get('presets', []) if isinstance(saved.get('presets'), list) else []:
                    if isinstance(entry, dict) and entry.get('recipe') == before_recipe:
                        entry['recipe']=after_recipe;changed=True
                if changed:
                    checks[str(preset_path)] = t.sha(raw); writes[str(preset_path)] = bulk._json(saved)
            revision = cross_os.new_revision()
            baseline['cross_os_revision'] = marker['revision'] = revision
            if shared_raw is not None:
                checks[str(shared)] = t.sha(shared_raw)
                if shared_record.get('cross_os_extras') is not None:
                    baseline['cross_os_extras'] = shared_record['cross_os_extras']
                portable = cross_os.portable(baseline, path.parent, target); portable.pop('steam_launch', None)
                writes[str(shared)] = bulk._json(portable)
            writes[str(path)] = bulk._json(baseline); writes[str(marker_path)] = bulk._json(marker)
            plan = {'name': name, 'game': str(root), 'root': str(root), 'target': str(target), 'checks': checks, 'writes': writes,
                    'summary': 'Update overlay packages and menu settings',
                    'note': 'OptiScaler · DirectX 12. NR, MFG, tuning and original restore backups are preserved.'
                    + (' Shared package identity will be synchronized.' if reconciled else '') + details}
            bulk._check(e, plan)
            plans.append(plan)
        except (t.Refusal, e.Stop, OSError, ValueError, KeyError, TypeError) as error:
            blocked.append({'title': name, 'detail': str(error), 'details': ''})
    more, failures, unchanged = routes.vulkan_plans(e, params, running)
    return {'engine': e, 'plans': plans + more, 'blocked': blocked + failures, 'skipped': skipped + unchanged}
