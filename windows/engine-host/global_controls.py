"""Reviewed, one-time NR/MFG changes to existing managed packages only."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import transactions as t
from operation_session import Session
import feeder_provider as feeder


def changes(params):
    t.need(isinstance(params, dict) and set(params) <= {'nr', 'mfg'}, 'Choose NR or MFG controls.')
    nr, mfg = params.get('nr'), params.get('mfg')
    t.need(nr is None or type(nr) is bool, 'Choose an NR setting.')
    t.need(mfg is None or type(mfg) is int and mfg in (-1, 0, 2, 3, 4, 5, 6), 'Choose an MFG setting.')
    t.need(nr is not None or mfg is not None, 'Choose at least one change.')
    return nr, mfg


def _read(path):
    path = t.safe(path)
    t.need(path.is_file() and path.stat().st_size < 2 * 1024**2, 'A settings or ownership file is missing or too large.')
    return path.read_bytes()


def _json(data):
    return (json.dumps(data, indent=2) + '\n').encode()


def prepare(e, state, params):
    nr, mfg = changes(params)
    plans, blocked, seen = [], [], set()
    candidates = [(p, False) for p in sorted((e.STATE_ROOT / 'targets').glob('*/baseline.json'))]
    candidates += [(p, True) for p in sorted((e.STATE_ROOT / 'feeder-targets').glob('*/baseline.json'))]
    t.need(len(candidates) <= 1000, 'Too many installation records. Refresh your library first.')
    for path, is_feeder in candidates:
        name = path.parent.name
        try:
            record = json.loads(_read(path))
            if record.get('status') != 'active': continue
            name = record.get('name') or name
            target = t.safe(record['target'] if is_feeder else record['target_dir'])
            expected = feeder.state_dir(e, target) if is_feeder else e.state_dir_for(target)
            t.need(t.safe(path.parent) == t.safe(expected), 'Installation record identity differs.')
            t.need(str(target).casefold() not in seen, 'Duplicate installation record.')
            seen.add(str(target).casefold())
            root = t.safe(record.get('game') or target)
            # Use the full Steam installation when the baseline's target is a
            # nested Binaries folder, so anti-cheat markers cannot be missed.
            for parent in (target, *target.parents):
                if parent.parent.name.casefold() in ('common', 'pinnedbuilds'):
                    root = parent; break
            t.need(not e._running_processes_under_root(root), 'Close this game, then review the bulk change again.')
            t.need(e.scan_game_files(root)[2] is None, 'Anti-cheat detected; this game is excluded.')
            checks, writes, notes = {str(path): t.sha(_read(path))}, {}, []
            baseline = copy.deepcopy(record)
            actual = {}
            if is_feeder:
                row = {'game': record['game'], 'exe': record['exe'], 'name': name}
                found = feeder.inspect(e, row, cached=False)
                t.need(found['managed'], 'Recognize this Feeder installation first.')
                if mfg is not None: notes.append('MFG unavailable in Feeder; NR can still change.')
                if nr is None:
                    blocked.append({'title': name, 'detail': 'Feeder provides NR only; MFG is unavailable.'}); continue
                config = target / 'ReShade.ini'
                original = _read(config)
                if nr:
                    # Do not enable a disabled or unrelated ReShade technique.
                    preset = _read(target / 'ReShadePreset.ini')
                    techniques = feeder._read_ini(target / 'ReShadePreset.ini').get('DEFAULT', 'Techniques', fallback='')
                    t.need(any(name.strip().split('@', 1)[0] == 'DLSS5_Feed' for name in techniques.split(',')),
                           'Enable the Feeder technique in ReShade first.')
                    checks[str(target / 'ReShadePreset.ini')] = t.sha(preset)
                text = e.set_ini_value(original.decode('utf-8-sig'), 'RenoDX.DLSS5', 'NeuralUplift', '1' if nr else '0')
                baseline['installed_hashes']['ReShade.ini'] = t.sha(text.encode('utf-8'))
                actual['enabled'] = int(nr)
            else:
                current = record.get('current') or {}
                family = (current.get('archive') or {}).get('family') or current.get('provider_id')
                t.need(family in ('skynizz', 'y4my'), 'This package does not expose these NR/MFG settings.')
                t.need(e.load_baseline(target, readonly=True) is not None, 'Installation ownership is missing.')
                meta_path = target / '.rtxforge-install.json'
                meta_bytes = _read(meta_path); metadata = json.loads(meta_bytes)
                t.need(metadata.get('provider', {}).get('id') == family, 'Installed provider identity changed.')
                files = metadata.get('files') or {}
                proxy = current.get('proxy')
                t.need(proxy in files and files[proxy] == (current.get('installed_hashes') or {}).get(proxy), 'Loader ownership changed.')
                # These are explicit bulk reviews, never a panel polling path.
                for filename, digest in files.items():
                    if filename.casefold().endswith(('.ini', '.log')): continue
                    owned = t.safe(target / t.relative(filename))
                    t.need(owned.is_relative_to(target) and t.digest(owned) == digest, 'Package files changed; repair this game first.')
                    checks[str(owned)] = digest
                config = target / 'OptiScaler.ini'; original = _read(config)
                text = original.decode('utf-8-sig')
                mode = current.get('feature_mode')
                if nr is not None:
                    if mode in ('nr-only', 'nr-mfg'):
                        text = e.set_ini_value(text, 'DlssNr', 'Enabled', 'true' if nr else 'false')
                        actual['enabled'] = int(nr)
                        if isinstance(baseline['current'].get('nr_profile'), dict): baseline['current']['nr_profile']['enabled'] = nr
                        if isinstance(metadata.get('nr_profile'), dict): metadata['nr_profile']['enabled'] = nr
                    else: notes.append('NR is not installed; NR setting skipped.')
                if mfg is not None:
                    external = 'renodx-mfgunlock.addon64' in {n.casefold() for n in files}
                    if mode in ('nr-mfg', 'mfg-only') and not external:
                        value = 'auto' if mfg == -1 else str(max(0, mfg - 1))
                        text = e.set_ini_value(text, 'DLSSG', 'OverrideInterpolationCount', value)
                        actual['multiplier'] = mfg
                    else: notes.append('This package does not provide this MFG control; MFG setting skipped.')
                t.need(actual, 'None of the chosen features is installed in this package.')
                digest = t.sha(text.encode('utf-8'))
                metadata['files']['OptiScaler.ini'] = digest
                baseline['current']['installed_hashes']['OptiScaler.ini'] = digest
                checks[str(meta_path)] = t.sha(meta_bytes); writes[str(meta_path)] = _json(metadata)
                # A previously saved sidebar preset must not undo this one-time
                # choice at the next game launch. Preserve every other field.
                exe = t.safe(record['exe'])
                key = hashlib.sha256(os.path.normcase(str(exe)).encode()).hexdigest()
                saved_path = Path(state) / 'runtime-presets' / (key + '.json')
                if saved_path.exists():
                    saved_bytes = _read(saved_path); saved = json.loads(saved_bytes)
                    t.need(saved.get('schema') == 1 and isinstance(saved.get('changes'), dict), 'Saved preset needs review first.')
                    t.need(len(saved_bytes) < 65536, 'Saved preset is too large.')
                    import companion_controls
                    companion_controls.validate_changes(saved['changes'])
                    saved['changes'].update(actual)
                    checks[str(saved_path)] = t.sha(saved_bytes); writes[str(saved_path)] = _json(saved)
            checks[str(config)] = t.sha(original)
            writes[str(config)] = text.encode('utf-8'); writes[str(path)] = _json(baseline)
            writes = {p: data for p, data in writes.items() if t.sha(data) != checks.get(p)}
            if not writes: continue
            label = ' · '.join([*(('NR on' if nr else 'NR off',) if 'enabled' in actual else ()),
                                *(('MFG follows game' if mfg == -1 else 'MFG off' if mfg == 0 else f'MFG {mfg}×',) if 'multiplier' in actual else ())])
            plans.append({'name': name, 'root': str(root), 'checks': checks, 'writes': writes,
                          'summary': label, 'note': ' '.join(notes)})
        except (t.Refusal, e.Stop, OSError, ValueError, KeyError, TypeError) as error:
            blocked.append({'title': name, 'detail': str(error)})
    return {'engine': e, 'plans': plans, 'blocked': blocked}


def _check(e, plan):
    t.need(not e._running_processes_under_root(Path(plan['root'])), 'A reviewed game started. Close it and review again.')
    t.need(e.scan_game_files(Path(plan['root']))[2] is None, 'Anti-cheat appeared after review; nothing further was changed.')
    for filename, digest in plan['checks'].items():
        t.need(t.digest(t.safe(filename)) == digest, 'Files changed since review. Review the bulk change again.')


def execute(review):
    e, plans = review['engine'], review['plans']
    t.need(plans, 'No bulk changes were reviewed.')
    with e.mutation_lock():
        for plan in plans: _check(e, plan)
        session = Session(e.STATE_ROOT / 'desktop-operations')
        completed = []
        try:
            for plan in plans:
                _check(e, plan)
                checkpoint = session.capture([Path(p) for p in plan['writes']], label=plan['name'])
                try:
                    for filename, data in plan['writes'].items(): t.atomic_file(Path(filename), data, 0o600)
                    for filename, data in plan['writes'].items():
                        t.need(t.digest(Path(filename)) == t.sha(data), 'A bulk change could not be verified.')
                    session.seal(checkpoint)
                    completed.append(plan['name'])
                except BaseException:
                    session.seal(checkpoint)
                    session.checkpoints[-1]['sealed'] = False; session.save()
                    t.need(not e._running_processes_under_root(Path(plan['root'])), 'Close the game before recovery. Backups: ' + str(session.root))
                    session.undo(checkpoint); session.seal(checkpoint)
                    raise
        except Exception as error:
            if all(c['sealed'] for c in session.checkpoints):
                session.status = 'failed'; session.save()
            import operation_session
            operation_session.LIVE.discard(str(session.root))
            raise t.Refusal(f"Updated {len(completed)} games before the operation stopped. "
                            f"Other games were not changed. Backups: {session.root}. {error}") from error
        # Retain the normal recovery session and original settings. Do not
        # remove backups or make a persistent override for future games.
        session.status = 'complete'; session.save()
        import operation_session
        operation_session.LIVE.discard(str(session.root))
    return {'message': f'Updated {len(plans)} games. Other settings were preserved.', 'errors': []}
