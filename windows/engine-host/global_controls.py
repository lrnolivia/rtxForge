"""Reviewed, one-time NR/MFG changes to existing managed packages only."""
from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import stat

import transactions as t
from operation_session import Session
import feeder_provider as feeder
import ui


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


def anti_cheat(e, root):
    """Check names without stat-ing every texture, archive and save in a game."""
    pattern = re.compile('|'.join(fnmatch.translate(p) for p in e.ANTI_CHEAT_PATTERNS))
    count = 0
    def fail(error): raise error
    for parent, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        safe_dirs = []
        for name in dirs:
            low = name.casefold()
            if low in e.IGNORE_DIRS or low.startswith(('_optiscaler', '_true_uninstall')): continue
            child = Path(parent) / name
            if child.is_symlink() or e._path_is_mount(child): continue
            if low in e.ANTI_CHEAT_DIRS: return child
            safe_dirs.append(name)
        dirs[:] = safe_dirs
        count += len(files)
        t.need(count <= 250000, 'Too many files to safely check this game. No settings were changed.')
        for name in files:
            if pattern.fullmatch(name.casefold()): return Path(parent) / name
    return None


def _process_check(e):
    check = e._running_processes_under_root
    return check.snapshot() if hasattr(check, 'snapshot') else check


def prepare(e, state, params):
    nr, mfg = changes(params)
    plans, blocked, skipped, seen = [], [], [], set()
    candidates = [(p, False) for p in sorted((e.STATE_ROOT / 'targets').glob('*/baseline.json'))]
    candidates += [(p, True) for p in sorted((e.STATE_ROOT / 'feeder-targets').glob('*/baseline.json'))]
    t.need(len(candidates) <= 1000, 'Too many installation records. Refresh your library first.')
    check_running = None
    for index, (path, is_feeder) in enumerate(candidates, 1):
        name = path.parent.name
        root = None
        try:
            record = json.loads(_read(path))
            if record.get('status') != 'active': continue
            name = record.get('name') or name
            ui.progress('Checking installed games', game=name, current=index, total=len(candidates))
            target = t.safe(record['target'] if is_feeder else record['target_dir'])
            expected = feeder.state_dir(e, target) if is_feeder else e.state_dir_for(target)
            t.need(t.safe(path.parent) == t.safe(expected), 'Installation record identity differs.')
            t.need(str(target).casefold() not in seen, 'Duplicate installation record.')
            seen.add(str(target).casefold())
            exe = t.safe(Path(record['game']) / record['exe'] if is_feeder else record['exe'])
            if not target.is_dir() or not exe.is_file():
                skipped.append({'title': name, 'detail': 'Game no longer found at this location.', 'details': str(target)})
                continue
            root = t.safe(record.get('game') or target)
            # Use the full Steam installation when the baseline's target is a
            # nested Binaries folder, so anti-cheat markers cannot be missed.
            for parent in (target, *target.parents):
                if parent.parent.name.casefold() in ('common', 'pinnedbuilds'):
                    root = parent; break
            checks, writes, notes = {str(path): t.sha(_read(path))}, {}, []
            baseline = copy.deepcopy(record)
            actual = {}
            owned_files = {}
            if is_feeder:
                row = {'game': record['game'], 'exe': record['exe'], 'name': name}
                if mfg is not None: notes.append('MFG unavailable in Feeder; NR can still change.')
                if nr is None:
                    skipped.append({'title': name, 'detail': 'Feeder provides NR only; MFG is unavailable.', 'details': str(root)}); continue
                runtime = target
                if record.get('legacy_recipe'):
                    import feeder_legacy
                    runtime = feeder_legacy.runtime(target, record['legacy_recipe'])
                config = runtime / 'ReShade.ini'
                original = _read(config)
                if nr:
                    # Do not enable a disabled or unrelated ReShade technique.
                    preset = _read(target / 'ReShadePreset.ini')
                    techniques = feeder._read_ini(target / 'ReShadePreset.ini').get('DEFAULT', 'Techniques', fallback='')
                    t.need(any(name.strip().split('@', 1)[0] == 'DLSS5_Feed' for name in techniques.split(',')),
                           'Enable the Feeder technique in ReShade first.')
                    checks[str(target / 'ReShadePreset.ini')] = t.sha(preset)
                text = e.set_ini_value(original.decode('utf-8-sig'), 'RenoDX.DLSS5', 'NeuralUplift', '1' if nr else '0')
                baseline['installed_hashes'][config.relative_to(target).as_posix()] = t.sha(text.encode('utf-8'))
                actual['enabled'] = int(nr)
            else:
                current = record.get('current') or {}
                family = (current.get('archive') or {}).get('family') or current.get('provider_id')
                mode = current.get('feature_mode')
                if family not in ('skynizz', 'y4my') or (nr is not None and mfg is None and mode not in ('nr-only', 'nr-mfg')):
                    skipped.append({'title': name, 'detail': 'NR is not installed in this package.' if nr is not None and mfg is None
                                    else 'This package has no compatible Global controls.', 'details': str(root)}); continue
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
                    t.need(owned.is_relative_to(target), 'Package path is outside this game.')
                    owned_files[str(owned)] = digest
                config = target / 'OptiScaler.ini'; original = _read(config)
                text = original.decode('utf-8-sig')
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
                if not actual:
                    skipped.append({'title': name, 'detail': 'None of the selected features is installed in this package.', 'details': str(root)}); continue
                digest = t.sha(text.encode('utf-8'))
                if digest != t.sha(original):
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
            label = ' · '.join([*(('NR on' if nr else 'NR off',) if 'enabled' in actual else ()),
                                *(('MFG follows game' if mfg == -1 else 'MFG off' if mfg == 0 else f'MFG {mfg}×',) if 'multiplier' in actual else ())])
            if not writes:
                skipped.append({'title': name, 'detail': 'Already set: ' + label + '.', 'details': str(root)})
                continue
            if check_running is None: check_running = _process_check(e)
            t.need(not check_running(root), 'Close this game, then review the bulk change again.')
            import offline_routes
            t.need(anti_cheat(e, root) is None or (not is_feeder and offline_routes.allowed_target(e, target, root)), 'Anti-cheat detected; this game is excluded.')
            ui.progress('Verifying package files', game=name, current=index, total=len(candidates))
            if is_feeder:
                found = feeder.inspect(e, row, cached=False)
                t.need(found['managed'], 'Recognize this Feeder installation first.')
                configs = set(feeder.CONFIGS)
                if record.get('legacy_recipe'):
                    import feeder_legacy
                    configs |= feeder_legacy.config_names(record['legacy_recipe'])
                owned_files = {str(t.safe(target / t.relative(n))): h for n, h in record['installed_hashes'].items() if n not in configs}
            for filename, digest in owned_files.items():
                t.need(t.digest(filename) == digest, 'Package files changed; repair this game first.')
                checks[filename] = digest
            plans.append({'name': name, 'root': str(root), 'target': str(target), 'checks': checks, 'writes': writes,
                          'summary': label, 'note': ' '.join(notes)})
        except (t.Refusal, e.Stop, OSError, ValueError, KeyError, TypeError) as error:
            blocked.append({'title': name, 'detail': str(error), 'details': str(root) if root else ''})
    ui.progress('Review ready', current=len(candidates), total=len(candidates))
    return {'engine': e, 'plans': plans, 'blocked': blocked, 'skipped': skipped}


def _check(e, plan):
    t.need(not e._running_processes_under_root(Path(plan['root'])), 'A reviewed game started. Close it and review again.')
    import offline_routes
    t.need(anti_cheat(e, Path(plan['root'])) is None or (plan.get('target') and offline_routes.allowed_target(e, Path(plan['target']), Path(plan['root']))), 'Anti-cheat appeared after review; nothing further was changed.')
    for filename, digest in plan['checks'].items():
        path = t.safe(filename)
        actual = t.digest(path) if path.exists() else None
        t.need(actual == digest, 'Files changed since review. Review the bulk change again.')


def execute(review):
    e, plans = review['engine'], review['plans']
    t.need(plans, 'No bulk changes were reviewed.')
    with e.mutation_lock():
        for index, plan in enumerate(plans, 1):
            ui.progress('Verifying reviewed games', game=plan['name'], current=index, total=len(plans))
            _check(e, plan)
        session = Session(e.STATE_ROOT / 'desktop-operations')
        completed = []
        try:
            for plan in plans:
                ui.progress('Applying settings', game=plan['name'], current=len(completed) + 1, total=len(plans))
                _check(e, plan)
                checkpoint = session.capture([Path(p) for p in plan['writes']], label=plan['name'])
                try:
                    for filename, data in plan['writes'].items():
                        path=Path(filename)
                        # Game payloads and shared restore records must remain
                        # readable from the other OS. Private app state stays private.
                        mode=((stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600)|0o044
                              if path.is_relative_to(Path(plan['root'])) else 0o600)
                        t.atomic_file(path, data, mode)
                        if path.is_relative_to(Path(plan['root'])):
                            import cross_os
                            cross_os.readable_parents(path,Path(plan['root']))
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
