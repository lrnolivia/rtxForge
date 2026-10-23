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


def prepare(e, state, params=None):
    if params is not None:
        overlay_settings.options(params)
        routes.selected(params)  # Validate an explicitly scoped, nonempty selection.
    bundled = None
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
            current = record.get('current') or {}
            if current.get('provider_id') != 'skynizz':
                skipped.append({'title': name, 'detail': 'Uses Feeder/ReShade.' if record.get('provider_id') == 'feeder'
                                else 'Uses a different MFG package.', 'details': 'The native overlay requires the Skynizz bridge; this loader is preserved.'})
                continue
            target = t.safe(record['target_dir']); exe = t.safe(record['exe'])
            t.need(path.parent == e.state_dir_for(target) and exe.parent == target and exe.is_file(), 'Installation identity differs.')
            t.need(target not in seen, 'Duplicate game record.'); seen.add(target)
            root = target
            for parent in (target, *target.parents):
                if parent.parent.name.casefold() in ('common', 'pinnedbuilds'): root = parent; break
            if not routes.selected(params, root, target): continue
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
            marker_path = target / cross_os.MARKER
            marker_raw = bulk._read(marker_path); marker = json.loads(marker_raw)
            t.need(marker.get('provider', {}).get('id') == 'skynizz' and marker.get('proxy') == proxy
                   and marker.get('files') == owned and marker.get('revision') == record.get('cross_os_revision'),
                   'Installation ownership changed; repair this game first.')
            checks = {str(path): t.sha(original), str(marker_path): t.sha(marker_raw), str(cached): release['sha256']}
            writes = {}; baseline = copy.deepcopy(record)
            values = routes.preferences(params, record, root)
            details = ('\n\n' + overlay_settings.describe(values)) if values is not None else ''
            for filename, data in ((proxy, payload['dxgi.dll']), ('nvngx.dll_dlssnr.dll', payload['nvngx.dll_dlssnr.dll'])):
                destination = t.safe(target / filename)
                expected = owned.get(filename)
                t.need(expected and t.digest(destination) == expected, 'The installed bridge changed: ' + filename)
                checks[str(destination)] = expected
                if t.sha(data) != expected: writes[str(destination)] = data
                baseline['current']['installed_hashes'][filename] = marker['files'][filename] = t.sha(data)
            routes.menus(e, target, values, baseline['current']['installed_hashes'], checks, writes)
            marker['files'] = dict(baseline['current']['installed_hashes'])
            if not writes and old_release.get('sha256') == release['sha256']:
                skipped.append({'title': name, 'detail': 'Overlay packages and menus are up to date.', 'details': details}); continue
            for filename, expected in owned.items():
                if filename.casefold().endswith(('.ini', '.log')): continue
                destination = t.safe(target / t.relative(filename))
                t.need(t.digest(destination) == expected, 'Package files changed; repair this game first: ' + filename)
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
                if saved.get('recipe') == recipe(owned, mode):
                    saved['recipe'] = recipe(marker['files'], mode)
                    checks[str(preset_path)] = t.sha(raw); writes[str(preset_path)] = bulk._json(saved)
            revision = cross_os.new_revision()
            baseline['cross_os_revision'] = marker['revision'] = revision
            shared = cross_os.shared_state(target) / 'baseline.json'
            if shared.is_file():
                raw = bulk._read(shared)
                t.need(json.loads(raw).get('cross_os_revision') == record.get('cross_os_revision'), 'Shared installation state changed.')
                portable = cross_os.portable(baseline, path.parent, target); portable.pop('steam_launch', None)
                checks[str(shared)] = t.sha(raw); writes[str(shared)] = bulk._json(portable)
            writes[str(path)] = bulk._json(baseline); writes[str(marker_path)] = bulk._json(marker)
            plan = {'name': name, 'game': str(root), 'root': str(root), 'target': str(target), 'checks': checks, 'writes': writes,
                    'summary': 'Update overlay packages and menu settings',
                    'note': 'OptiScaler · DirectX 12. NR, MFG, tuning and original restore backups are preserved.' + details}
            bulk._check(e, plan)
            plans.append(plan)
        except (t.Refusal, e.Stop, OSError, ValueError, KeyError, TypeError) as error:
            blocked.append({'title': name, 'detail': str(error), 'details': ''})
    more, failures, unchanged = routes.vulkan_plans(e, params, running)
    return {'engine': e, 'plans': plans + more, 'blocked': blocked + failures, 'skipped': skipped + unchanged}
