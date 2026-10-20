"""Windows Feeder NR: reviewed local recipes, adoption, model updates and restore.

Third-party runtime binaries and the NR model are supplied locally. This adapter
does not run their installer scripts or manufacture native OptiScaler ownership.
"""
from __future__ import annotations

import copy
import configparser
import hashlib
import json
import os
from pathlib import Path
import re

import transactions as t
import ui
import operation_session
from operation_session import Session, Cancelled

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ('ReShade.ini', 'ReShadePreset.ini')
MODEL = 'nvngx_dlssnr.dll'
INSTALL_DEFAULTS = {'NRFollowInputRes': '0', 'NRResolutionScale': '0.65',
                    'NRLocalStructure': '1.0', 'NRSkinStructure': '1.0'}
_hashes = {}


def lock():
    return json.loads((ROOT / 'providers/feeder.json').read_text(encoding='utf-8'))


def digest(path, cached=False):
    path = t.safe(path)
    if not path.exists():
        return None
    t.need(path.is_file(), 'Expected a regular file: ' + str(path))
    info = path.stat()
    key = (str(path), info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if not cached or key not in _hashes:
        _hashes[key] = t.digest(path)
    return _hashes[key]


def state_dir(e, target):
    target = t.safe(target)
    return t.safe(e.STATE_ROOT / 'feeder-targets' / hashlib.sha256(str(target).casefold().encode()).hexdigest())


def state(e, target):
    path = state_dir(e, target) / 'baseline.json'
    if not path.exists():
        return None
    t.need(path.stat().st_size <= 1024 * 1024, 'Feeder install record is too large')
    record = t.read_json(t.safe(path))
    t.need(isinstance(record, dict) and record.get('schema') == 1 and record.get('provider_id') == 'feeder'
           and isinstance(record.get('target'), str) and Path(record['target']).resolve() == t.safe(target),
           'Feeder install record identity differs')
    names = {*lock()['assets'], *CONFIGS, MODEL}
    t.need(isinstance(record.get('originals'), dict) and set(record['originals']) == names
           and isinstance(record.get('installed_hashes'), dict), 'Feeder ownership record is incomplete')
    for item in record['originals'].values():
        if item is not None:
            cached_input(e, item)
    return record


def cached_input(e, item):
    t.need(isinstance(item, dict) and isinstance(item.get('sha256'), str)
           and re.fullmatch(r'[0-9a-f]{64}', item['sha256']) and isinstance(item.get('path'), str),
           'Feeder cache identity is invalid')
    expected = t.safe(e.STATE_ROOT / 'feeder-cache' / item['sha256'])
    t.need(t.safe(item['path']) == expected, 'Feeder cache path is outside its owned storage')
    return expected


def target(row):
    root = t.safe(row['game'])
    exe = t.safe(root / t.relative(row['exe']))
    t.need(exe.is_relative_to(root) and exe.is_file(), 'The selected game executable is unavailable')
    t.executable_check(exe)
    return root, exe, exe.parent


def model(path):
    path = t.safe(path)
    value = digest(path)
    spec = lock()['models'].get(value)
    t.need(spec is not None and path.stat().st_size == spec['size'],
           'Choose a verified RTX 40 compatible NR model in Settings')
    t.executable_check(path)
    return {'path': str(path), 'sha256': value, **spec}


def stack(directory, cached=False):
    directory = t.safe(directory)
    spec = lock()
    for name, expected in spec['assets'].items():
        path = t.safe(directory / t.relative(name))
        t.need(path.is_file() and path.stat().st_size == expected['size'] and digest(path, cached) == expected['sha256'],
               'Feeder files are missing or changed: ' + name)
    for name in CONFIGS:
        path = t.safe(directory / name)
        t.need(path.is_file() and path.stat().st_size <= 256 * 1024, 'Feeder settings are missing: ' + name)
        _read_ini(path)
    return spec


def configured(directory):
    values = _read_ini(directory / 'ReShade.ini')
    nr = values['RenoDX.DLSS5'] if values.has_section('RenoDX.DLSS5') else {}
    preset = _read_ini(directory / 'ReShadePreset.ini')
    techniques = preset.get('DEFAULT', 'Techniques', fallback='')
    # ReShade preset globals precede sections; ConfigParser needs a header.
    if not techniques:
        text = (directory / 'ReShadePreset.ini').read_text(encoding='utf-8-sig')
        found = re.search(r'(?m)^Techniques=(.*)$', text)
        techniques = found[1] if found else ''
    return {'nr_enabled': nr.get('NeuralUplift', '0') == '1' and 'DLSS5_Feed' in techniques,
            'passes': nr.get('NRPasses'), 'scale': nr.get('NRResolutionScale'), 'preset': nr.get('NRPreset')}


def configure_new_install(text, nr_on_launch=False):
    """Apply fresh-install tuning without changing other ReShade or depth settings."""
    for key, value in INSTALL_DEFAULTS.items():
        text = t.setvalue(text, 'RenoDX.DLSS5', key, value)
    return t.setvalue(text, 'RenoDX.DLSS5', 'NeuralUplift', '1' if nr_on_launch else '0')


def _read_ini(path):
    text = path.read_text(encoding='utf-8-sig')
    # ReShade presets also support unsectioned global keys.
    return t.ini(text if text.lstrip().startswith('[') else '[DEFAULT]\n' + text)


def inspect(e, row, cached=True):
    _, _, directory = target(row)
    stack(directory, cached)
    nr = model(directory / MODEL)
    record = state(e, directory)
    if record:
        t.need(record.get('status') == 'active', 'The Feeder installation needs recovery')
        for name, expected in record['installed_hashes'].items():
            if name not in CONFIGS:
                t.need(digest(directory / name, cached) == expected, 'An installed Feeder file changed: ' + name)
    return {'managed': record is not None, 'nr_runtime': nr, **configured(directory)}


def eligible(e, row, existing=False):
    root, exe, directory = target(row)
    t.need(getattr(e, 'DESKTOP_PLATFORM', 'windows' if os.name == 'nt' else 'linux') == 'windows',
           'Feeder installation is available on Windows only in this release')
    t.need(not row.get('anti_cheat'), 'Anti-cheat detected; Feeder is unavailable for this game')
    t.need(not e._running_processes_under_root(root), 'Close this game before changing Feeder files')
    t.need(not e.load_baseline(directory) and not (directory / 'OptiScaler.ini').exists(),
           'Restore the existing OptiScaler package before installing Feeder NR')
    t.need(not any((directory / name).exists() for name in ('nvngx.dll_dlssnr.dll', 'dlss5-feed-helper.addon64',
                                                         'dlss5-bridge.addon64', 'renodx-mfgunlock.addon64')),
           'Another NR or frame-generation hook is present. Restore it before using this Feeder recipe')
    t.need(existing or 'd3d11.dll' in {name.lower() for name in e.pe_imported_dlls(exe)},
           'This Feeder recipe requires an x64 DirectX 11 executable')
    return root, exe, directory


def expand_rows(e, rows, selected=False):
    result = []
    for original in rows:
        root = Path(original['game'])
        candidates = []
        # ME Legendary Edition has one Steam entry and three actual targets.
        for index in (1, 2, 3):
            exe = root / f'Game/ME{index}/Binaries/Win64/MassEffect{index}.exe'
            if exe.is_file() and (exe.parent / 'dlss5-feed.addon64').is_file():
                candidates.append((exe, f"{original['name']} · Mass Effect {index}"))
        if not candidates and original.get('exe'):
            exe = root / original['exe']
            # Some collections pick a launcher. Prefer its adjacent DX11 game.
            if exe.name.lower() in ('ts4_launcher_x64.exe', 'ts4_dx9_x64.exe') and (exe.parent / 'TS4_x64.exe').is_file():
                exe = exe.parent / 'TS4_x64.exe'
            candidates = [(exe, original['name'])]
        for exe, name in candidates:
            child = copy.deepcopy(original)
            if len(candidates) > 1:
                child.update(game=str(exe.parent), exe=exe.name, collection_game=str(root), name=name)
            else:
                child['exe'] = exe.relative_to(root).as_posix()
            if (exe.parent / 'dlss5-feed.addon64').is_file():
                try:
                    found = inspect(e, child)
                    child.update(installed=True, runtime_provider='feeder', feature_mode='nr-only', profile='NR Only',
                                 feeder_managed=found['managed'], nr_enabled=found['nr_enabled'], nr_runtime=found['nr_runtime'],
                                 mfg_enabled=False, mfg_multiplier=0, installed_on='windows' if found['managed'] else None,
                                 feeder_settings={k: found[k] for k in ('passes', 'scale', 'preset')},
                                 blocked='')
                except (t.Refusal, OSError, ValueError, configparser.Error) as error:
                    child.update(blocked=str(error), feeder_detected=True)
            elif selected:
                try:
                    eligible(e, child)
                    child['blocked'] = ''
                except (t.Refusal, OSError, ValueError) as error:
                    child['blocked'] = str(error)
            result.append(child)
        if not candidates:
            result.append(original)
    return result


def cache(e, source):
    source = t.safe(source)
    value = digest(source)
    dest = t.safe(e.STATE_ROOT / 'feeder-cache' / value)
    if not dest.exists():
        t.atomic_file(dest, source.read_bytes(), 0o600)
    t.need(digest(dest) == value, 'Feeder cached file differs')
    return {'path': str(dest), 'sha256': value}


def original_manifest(settings, directory):
    folder = settings.get('feeder_backups', '')
    t.need(folder, 'Choose the original Feeder backups folder in Packages to recognize this installation')
    folder = t.safe(folder)
    paths = [folder / 'manifest.json', *sorted(folder.glob('*/manifest.json'))[:128]]
    found = []
    for path in paths:
        if path.is_file() and path.stat().st_size <= 1024 * 1024:
            try:
                doc = t.read_json(t.safe(path))
            except (ValueError, OSError, t.Refusal):
                continue
            if isinstance(doc, dict) and doc.get('schema') == 1 and isinstance(doc.get('target'), str) and Path(doc['target']).resolve() == directory:
                found.append((path, doc))
    t.need(len(found) == 1, 'A unique original Feeder backup for this executable is required')
    path, doc = found[0]
    t.need(doc.get('state') == 'installed-unverified', 'This manual Feeder backup is not an installed recipe')
    entries = doc.get('files', [])
    t.need(isinstance(entries, list) and len(entries) <= 256
           and all(isinstance(entry, dict) and isinstance(entry.get('path'), str) for entry in entries),
           'Original Feeder backup file list is invalid')
    t.need(len({entry['path'].casefold() for entry in entries}) == len(entries),
           'Original Feeder backup paths are duplicated or too numerous')
    for entry in entries:
        t.relative(entry['path'])
    return path, {entry['path']: entry for entry in entries}


def _checks(directory, names):
    return {name: digest(directory / t.relative(name)) for name in names}


def _check(e, plan):
    eligible(e, plan['row'], existing=plan['existing'])
    directory = Path(plan['target'])
    t.need(_checks(directory, plan['checks']) == plan['checks'], 'Feeder files changed since review; review again')
    t.need(digest(state_dir(e, directory) / 'baseline.json') == plan['baseline_before'],
           'Feeder install record changed since review')
    for item in plan['inputs'].values():
        t.need(digest(cached_input(e, item)) == item['sha256'], 'Feeder source or original backup changed since review')


def prepare(config, rows, mode, operation, settings, e):
    t.need(mode == 'nr-only' or operation == 'uninstall', 'Feeder provides NR Only. Frame generation is not available for this route')
    t.need(operation in ('install', 'repair', 'uninstall', 'reset'), 'Unsupported Feeder operation')
    ready, blocked, plans, seen = [], [], [], set()
    for index, row in enumerate(rows):
        ui.progress('Checking Feeder files', game=row['name'], checked=index, total=len(rows))
        try:
            _, _, directory = target(row)
            t.need(str(directory).casefold() not in seen, 'The same Feeder executable was selected twice')
            seen.add(str(directory).casefold())
            current = state(e, directory)
            if current and current.get('status') == 'restored':
                current = None
            existing = (directory / 'dlss5-feed.addon64').is_file()
            eligible(e, row, existing)
            spec = stack(directory) if existing else lock()
            names = list(spec['assets']) + [*CONFIGS, MODEL]
            inputs, writes = {}, {}
            baseline = copy.deepcopy(current)
            if operation in ('uninstall', 'reset', 'repair'):
                t.need(current is not None, 'Recognize this Feeder installation with its original backups first')
            if current or existing:
                found = inspect(e, row, cached=False)
            if operation == 'uninstall':
                for name, original in current['originals'].items():
                    if original is not None:
                        inputs['original:' + name] = original
                    writes[name] = original
                summary = 'Restore the original files recorded for this Feeder setup.'
            elif operation == 'reset':
                t.need(False, 'Edit Feeder NR settings in its ReShade panel. Your saved tuning has been kept')
            else:
                if not existing:
                    t.need(not any((directory / name).exists() for name in (*t.PROXIES, 'ReShade.ini', 'renodx-dlss5.addon64')),
                           'Other graphics mods are present. Restore them before installing Feeder NR')
                    t.need(settings.get('feeder_source'), 'Choose a local Feeder stack folder in Packages first')
                    source = t.safe(settings['feeder_source'])
                    stack(source)
                    for name in [*spec['assets'], *CONFIGS]:
                        inputs[name] = writes[name] = cache(e, source / name)
                if baseline is None:
                    originals = {}
                    manifest = None
                    if existing:
                        manifest, old = original_manifest(settings, directory)
                        inputs['manual-manifest'] = cache(e, manifest)
                    for name in names:
                        if existing:
                            t.need(name in old, 'The original backup does not cover: ' + name)
                            installed = old[name].get('after')
                            if name in spec['assets']:
                                expected = {spec['assets'][name]['sha256']}
                                if name == 'nvngx_dlss.dll':
                                    # Earlier manual installs were subsequently
                                    # upgraded to the verified production SR.
                                    expected.add('378262f4ba429e6199ce25d6f9275734f354c3b017f3f096d8cea1af468312ff')
                                t.need(installed in expected, 'The manual backup describes another Feeder recipe: ' + name)
                            elif name == MODEL:
                                t.need(installed in spec['models'], 'The manual backup has an unrecognized NR model')
                            prior = old[name].get('before')
                            if prior is not None:
                                original = t.safe(manifest.parent / 'originals' / t.relative(name))
                                t.need(digest(original) == prior, 'An original Feeder backup is missing or changed: ' + name)
                                originals[name] = cache(e, original)
                                inputs['original:' + name] = originals[name]
                            else:
                                originals[name] = None
                        else:
                            originals[name] = cache(e, directory / name) if (directory / name).exists() else None
                            if originals[name]:
                                inputs['original:' + name] = originals[name]
                    baseline = dict(schema=1, provider_id='feeder', status='active', target=str(directory),
                                    game=row['game'], exe=row['exe'], name=row['name'], originals=originals,
                                    adopted=existing, original_manifest=str(manifest) if manifest else None,
                                    created_utc=t.now(), installed_hashes={})
                desired = settings.get('nr_runtime') if operation == 'install' else None
                source = (Path(desired) if desired else Path(current['nr_runtime']['cache']['path']) if current else
                          directory / MODEL if existing else Path(settings['feeder_source']) / MODEL)
                selected = model(source)
                inputs[MODEL] = cache(e, source)
                if digest(directory / MODEL) != selected['sha256']:
                    if existing:
                        prior_model = cache(e, directory / MODEL)
                        inputs['previous-model'] = prior_model
                        baseline.setdefault('previous_models', []).append(prior_model)
                    writes[MODEL] = inputs[MODEL]
                baseline['nr_runtime'] = {**selected, 'cache': inputs[MODEL]}
                baseline['updated_utc'] = t.now()
                old_version = found['nr_runtime']['version'] if existing else None
                summary = ('Recognize the existing Feeder NR setup.' if existing and current is None else
                           'Update Feeder NR.' if existing else 'Install Feeder NR.')
                if old_version != selected['version']:
                    summary += f" NR runtime: {old_version or 'not installed'} → {selected['version']}."
                summary += ' Keep your saved tuning. Frame generation is unavailable.' if existing else ' Frame generation is unavailable.'
            if operation == 'install':
                # NR startup is an explicit install choice, independent of MFG.
                source_ini = (Path(writes['ReShade.ini']['path']).read_bytes().decode('utf-8-sig')
                              if 'ReShade.ini' in writes else (directory / 'ReShade.ini').read_bytes().decode('utf-8-sig'))
                desired_startup = '1' if settings.get('nr_on_launch', False) else '0'
                if not existing:
                    changed = configure_new_install(source_ini, settings.get('nr_on_launch', False))
                else:
                    changed = source_ini if t.ini(source_ini).get('RenoDX.DLSS5', 'NeuralUplift', fallback='0') == desired_startup else t.setvalue(source_ini, 'RenoDX.DLSS5', 'NeuralUplift', desired_startup)
                dest = t.safe(e.STATE_ROOT / 'feeder-cache' / t.sha(changed.encode()))
                if not dest.exists(): t.atomic_file(dest, changed.encode(), 0o600)
                if changed != source_ini or 'ReShade.ini' in writes:
                    inputs['startup-ini'] = writes['ReShade.ini'] = {'path': str(dest), 'sha256': t.sha(changed.encode())}
                summary += ' NR starts ' + ('on.' if settings.get('nr_on_launch', False) else 'off; enable it from the overlay.')
            if operation in ('install', 'repair'):
                import overlay_policy
                if overlay_policy.explicit(settings):
                    source_ui = (Path(writes['ReShade.ini']['path']) if 'ReShade.ini' in writes else directory / 'ReShade.ini').read_text(encoding='utf-8-sig')
                    updated_ui = overlay_policy.reshade(source_ui, settings)
                    if updated_ui != source_ui:
                        ui_file = t.safe(e.STATE_ROOT / 'feeder-cache' / t.sha(updated_ui.encode()))
                        if not ui_file.exists(): t.atomic_file(ui_file, updated_ui.encode(), 0o600)
                        inputs['ui-ini'] = writes['ReShade.ini'] = {'path': str(ui_file), 'sha256': t.sha(updated_ui.encode())}
                    summary += ' Menu access and welcome messages follow Overlay settings.'
            checks = _checks(directory, names)
            plan = dict(row=dict(row), target=str(directory), existing=existing, checks=checks,
                        baseline_before=digest(state_dir(e, directory) / 'baseline.json'), baseline=baseline,
                        inputs=inputs, writes=writes, operation=operation)
            _check(e, plan)
            plans.append(plan)
            detail = json.dumps({'target': str(directory), 'operation': operation,
                                 'recipe': spec['version'], 'model': (baseline or {}).get('nr_runtime'),
                                 'original_manifest': (baseline or {}).get('original_manifest'),
                                 'writes': {name: item['sha256'] if item else None for name, item in writes.items()},
                                 'preserved_settings': list(CONFIGS) if existing and operation != 'uninstall' else []}, indent=2)
            ready.append({'name': row['name'], 'game': row['game'], 'summary': summary, 'detail': detail})
        except (t.Refusal, e.Stop, OSError, ValueError, configparser.Error) as error:
            blocked.append({'name': row['name'], 'game': row['game'], 'reason': str(error)})
    return dict(kind='feeder', operation=operation, title='Feeder NR', rows=ready, blocked=blocked, plans=plans, engine=e)


def execute(review):
    e, results = review['engine'], []
    t.need(review['plans'], 'No Feeder changes were reviewed')
    cancel = review.get('cancel_event')
    with e.mutation_lock():
        # Reject drift anywhere in the reviewed selection before the first write.
        for plan in review['plans']:
            _check(e, plan)
        session = Session(e.STATE_ROOT / 'desktop-operations')
        try:
            for index, plan in enumerate(review['plans'], 1):
                if cancel is not None and cancel.is_set():
                    raise Cancelled('Changes undone.')
                directory = Path(plan['target'])
                _check(e, plan)
                ui.progress('Backing up Feeder files', game=plan['row']['name'], current=index, total=len(review['plans']))
                checkpoint = session.capture([directory / name for name in plan['writes']] + [state_dir(e, directory)], label=plan['row']['name'])
                try:
                    # A durable baseline precedes any model replacement.
                    if plan['operation'] != 'uninstall':
                        baseline = copy.deepcopy(plan['baseline'])
                        baseline['status'] = 'preparing'
                        t.atomic_file(state_dir(e, directory) / 'baseline.json', (json.dumps(baseline, indent=2) + '\n').encode(), 0o600)
                    for name, item in plan['writes'].items():
                        if cancel is not None and cancel.is_set():
                            raise Cancelled('Changes undone.')
                        path = t.safe(directory / t.relative(name))
                        t.need(digest(path) == plan['checks'][name], 'Feeder target changed during installation')
                        if item is None:
                            if path.exists():
                                path.unlink()
                        else:
                            data = Path(item['path']).read_bytes()
                            t.need(t.sha(data) == item['sha256'], 'Feeder input changed during installation')
                            t.atomic_file(path, data, path.stat().st_mode & 0o777 if path.exists() else 0o644)
                        t.need(digest(path) == (item['sha256'] if item else None), 'Feeder write verification failed')
                    if plan['operation'] == 'uninstall':
                        baseline = copy.deepcopy(plan['baseline'])
                        baseline['status'] = 'restored'
                    else:
                        baseline = copy.deepcopy(plan['baseline'])
                        baseline['status'] = 'active'
                        baseline['installed_hashes'] = _checks(directory, plan['checks'])
                        stack(directory)
                    t.atomic_file(state_dir(e, directory) / 'baseline.json', (json.dumps(baseline, indent=2) + '\n').encode(), 0o600)
                    session.seal(checkpoint)
                    results.append({'name': plan['row']['name'], 'game': plan['row']['game'], 'status': 'complete'})
                except BaseException:
                    session.seal(checkpoint)
                    # Keep this checkpoint recoverable until undo is verified.
                    # A failed restore must not disappear as a closed session.
                    session.checkpoints[-1]['sealed'] = False
                    session.save()
                    t.need(not e._running_processes_under_root(Path(plan['row']['game'])),
                           'Close this game before Feeder recovery. Backups are retained at ' + str(session.root))
                    session.undo(checkpoint)
                    session.seal(checkpoint)
                    raise
            if cancel is not None and cancel.is_set():
                raise Cancelled('Changes undone.')
            session.complete()
        except Cancelled:
            t.need(not any(e._running_processes_under_root(Path(p['row']['game'])) for p in review['plans']),
                   'Close running games before Feeder recovery. Backups are retained at ' + str(session.root))
            session.rollback()
            raise
        except BaseException as error:
            if session.interrupted() is None:
                session.close('failed')
            e.save_json_atomic(session.root / 'result.json', {'results': results, 'error': str(error),
                               'recovery_required': session.interrupted() is not None})
            if isinstance(error, Exception):
                raise t.Refusal(f'Feeder stopped after {len(results)} completed game(s). '
                                f'Completed games keep their changes. Recovery copies: {session.root}. {error}') from error
            raise
        finally:
            operation_session.LIVE.discard(str(session.root))
    path = e.STATE_ROOT / ('desktop-feeder-' + e.now_stamp() + '.json')
    e.save_json_atomic(path, {'results': results})
    return str(path)


def parse_logs(feed, reshade):
    """Keep model/evaluation evidence distinct from a feed counter or NR request."""
    versions = re.findall(r'NGX runtime nvngx_dlssnr\.dll:\s*([\d.]+)', feed)
    verdicts = re.findall(r'NR-VERDICT\s+v\d+\s+state=(\w+)[^\n]*', reshade)
    evaluations = re.findall(r'feature 18 evaluation succeeded\s*\(count=(\d+)', reshade, re.I)
    depths = [float(value) for value in re.findall(r'Depth probe[^\n]*variance\s+([\d.eE+-]+)', feed)]
    motion = [float(value) for value in re.findall(r'MV probe[^\n]*max\s+([\d.eE+-]+)\s*px', feed)]
    return {'logged_nr_version': versions[-1] if versions else None,
            'feature18_created': bool(re.search(r'feature 18 created via the signed snippet', reshade, re.I)),
            'feature18_evaluated': bool(evaluations), 'last_evaluation_count': int(evaluations[-1]) if evaluations else 0,
            'last_verdict': verdicts[-1] if verdicts else None,
            'nonflat_depth_observed': any(value > 1e-8 for value in depths),
            'moving_vectors_observed': any(value > 0.01 for value in motion)}


def diagnose(row):
    from runtime_diagnostics import read_regular
    _, _, directory = target(row)
    nr = model(directory / MODEL)
    saved = configured(directory)
    report = {'name': row['name'], 'provider': 'feeder', 'settings': saved, 'files': {MODEL: nr},
              'observations': ['Feeder NR is installed. Saved NR is ' + ('enabled.' if saved['nr_enabled'] else 'disabled.'),
                               'NR runtime: ' + nr['version'] + '.', 'Frame generation is unavailable for this route.'],
              'warnings': [], 'visual_result': 'Not established by file or log inspection'}
    logs, times = {}, {}
    for name in ('dlss5-feed.log', 'ReShade.log'):
        try:
            data, info = read_regular(directory / name, tail=True)
            logs[name] = data.decode('utf-8', errors='replace')
            times[name] = info.st_mtime_ns
        except (OSError, ValueError):
            logs[name] = ''
            times[name] = 0
    evidence = parse_logs(logs['dlss5-feed.log'], logs['ReShade.log'])
    latest_change = max((directory / name).stat().st_mtime_ns for name in (*CONFIGS, MODEL))
    evidence['predates_current_files'] = any(value < latest_change for value in times.values())
    evidence['matches_current_model_version'] = evidence['logged_nr_version'] == nr['version']
    report['log'] = evidence
    current = not evidence['predates_current_files'] and evidence['matches_current_model_version']
    if current and evidence['feature18_created'] and evidence['feature18_evaluated']:
        report['observations'].append('The captured run created and evaluated the NR model. This does not establish visual correctness.')
        report['observations'].append('Last NR state in that run: ' + (evidence['last_verdict'] or 'Not reported') + '.')
    else:
        report['observations'].append('No matching NR evaluation is confirmed for the current files. Run the game, then refresh.')
    if current and evidence['nonflat_depth_observed'] and evidence['moving_vectors_observed']:
        report['observations'].append('The captured run includes nonflat depth and moving motion vectors.')
    else:
        report['observations'].append('Depth and motion-vector quality still need a moving-scene check.')
    return report
