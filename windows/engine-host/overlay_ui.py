"""Review independent native menu/intro changes without touching NR or MFG."""
import copy
import json
import os
from pathlib import Path
import transactions as t
import cross_os
import feeder_provider as feeder
import overlay_policy as policy
import global_controls as bulk
import ui


def prepare(e, params):
    t.need(isinstance(params, dict) and set(params) <= {*policy.DEFAULTS, 'optiscaler_hotkey'}, 'Choose game-menu settings.')
    settings = policy.options(params) | {'optiscaler_hotkey': params.get('optiscaler_hotkey', 'Insert')}
    candidates = [(p, False) for p in sorted((e.STATE_ROOT / 'targets').glob('*/baseline.json'))]
    candidates += [(p, True) for p in sorted((e.STATE_ROOT / 'feeder-targets').glob('*/baseline.json'))]
    t.need(len(candidates) <= 1000, 'Too many package records. Rescan your library.')
    plans, blocked, skipped, seen = [], [], [], set()
    running = bulk._process_check(e)
    for index, (path, is_feeder) in enumerate(candidates, 1):
        name, root = path.parent.name, None
        try:
            raw = bulk._read(path); record = json.loads(raw)
            if record.get('status') != 'active': continue
            name = record.get('name') or name
            target = t.safe(record['target'] if is_feeder else record['target_dir'])
            t.need(target not in seen, 'Duplicate package record.'); seen.add(target)
            expected = feeder.state_dir(e, target) if is_feeder else e.state_dir_for(target)
            t.need(path.parent == expected, 'Package record location differs.')
            root = t.safe(record.get('game') or target)
            for parent in (target, *target.parents):
                if parent.parent.name.casefold() in ('common', 'pinnedbuilds'):
                    root = parent; break
            t.need(not running(root), 'Close this game, then review again.')
            ui.progress('Reviewing game menus', game=name, current=index, total=len(candidates))
            checks = {str(path): t.sha(raw)}; writes = {}; baseline = copy.deepcopy(record)
            native = record.get('current') or {}
            if not is_feeder and native.get('provider_id') not in ('skynizz', 'y4my'): continue
            owned = record['installed_hashes'] if is_feeder else native['installed_hashes']
            config = target / ('ReShade.ini' if is_feeder else 'OptiScaler.ini')
            original = bulk._read(config); checks[str(config)] = t.sha(original)
            text = original.decode('utf-8-sig')
            note = ''
            if is_feeder:
                text = policy.reshade(text, settings)
                if text.encode() == original:
                    skipped.append({'title': name, 'detail': 'Already set.', 'details': ''}); continue
                baseline['installed_hashes']['ReShade.ini'] = t.sha(text.encode())
                summary = f"ReShade menu {'on' if settings['reshade_ui'] else 'off'} · intro {'on' if settings['reshade_intro'] else 'off'}"
                note = 'Welcome guide and RenoDX welcome dialog. ReShade loading notices are separate.'
            else:
                text = policy.optiscaler(text, settings, e.set_ini_value)
                reshade_changed = False
                if 'ReShade.ini' in owned:
                    reshade = target / 'ReShade.ini'; old_reshade = bulk._read(reshade)
                    updated_reshade = policy.reshade(old_reshade.decode('utf-8-sig'), settings).encode()
                    reshade_changed = updated_reshade != old_reshade
                    checks[str(reshade)] = t.sha(old_reshade)
                    if reshade_changed: writes[str(reshade)] = updated_reshade
                if text.encode() == original and not reshade_changed:
                    skipped.append({'title': name, 'detail': 'Already set.', 'details': ''}); continue
                digest = t.sha(text.encode())
                baseline['current']['installed_hashes']['OptiScaler.ini'] = digest
                meta = target / cross_os.MARKER
                meta_raw = bulk._read(meta); marker = json.loads(meta_raw)
                t.need(marker['provider']['id'] == native['provider_id'] and marker['proxy'] == native['proxy'], 'Package ownership differs.')
                t.need(marker.get('files') == owned and marker.get('revision') == baseline.get('cross_os_revision'), 'Package ownership changed; repair this game first.')
                marker['files']['OptiScaler.ini'] = digest
                if reshade_changed:
                    marker['files']['ReShade.ini'] = baseline['current']['installed_hashes']['ReShade.ini'] = t.sha(updated_reshade)
                shared = cross_os.shared_state(target) / 'baseline.json'
                if shared.is_file():
                    shared_raw = bulk._read(shared)
                    t.need(json.loads(shared_raw).get('cross_os_revision') == baseline.get('cross_os_revision'), 'Shared package state changed; refresh this game first.')
                    revision = cross_os.new_revision()
                    baseline['cross_os_revision'] = marker['revision'] = revision
                    portable = cross_os.portable(baseline, e.state_dir_for(target), target)
                    portable.pop('steam_launch', None)
                    checks[str(shared)] = t.sha(shared_raw); writes[str(shared)] = bulk._json(portable)
                checks[str(meta)] = t.sha(meta_raw); writes[str(meta)] = bulk._json(marker)
                summary = f"OptiScaler menu {'on' if settings['optiscaler_ui'] else 'off'} · intro {'on' if settings['optiscaler_intro'] else 'off'}"
            writes[str(config)] = text.encode(); writes[str(path)] = bulk._json(baseline)
            writes = {p: data for p, data in writes.items() if t.sha(data) != checks.get(p)}
            if not writes:
                skipped.append({'title': name, 'detail': 'Already set.', 'details': ''}); continue
            for filename, digest in owned.items():
                owned_path = t.safe(target / t.relative(filename))
                if filename.casefold().endswith(('.ini', '.log')): continue
                t.need(t.digest(owned_path) == digest, 'Package files changed; repair this game first.')
                checks[str(owned_path)] = digest
            settings_file = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'rtxForge/settings.json'
            if settings_file.is_file(): checks[str(settings_file)] = t.sha(bulk._read(settings_file))
            plan = {'name': name, 'root': str(root), 'target': str(target), 'checks': checks, 'writes': writes,
                    'summary': summary, 'note': note}
            bulk._check(e, plan)
            plans.append(plan)
        except (t.Refusal, e.Stop, OSError, ValueError, KeyError, TypeError) as error:
            blocked.append({'title': name, 'detail': str(error), 'details': str(root) if root else ''})
    return {'engine': e, 'plans': plans, 'blocked': blocked, 'skipped': skipped}
