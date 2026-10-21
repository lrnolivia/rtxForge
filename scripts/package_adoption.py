"""Package Adoption: identify, review, back up and register existing installs.

Detection is not ownership. Provider adapters verify complete known recipes at
review time; registration never treats modded bytes as vanilla game originals.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import transactions as t
import engine_bridge as bridge
import skynizz_provider
import feeder_provider as feeder
import offline_routes
import cross_os
import ui
from operation_session import Session, Cancelled


def decorate(e, rows):
    for row in rows:
        if not row.get('exe'):
            continue
        try:
            target = t.safe(Path(row['game']) / t.relative(row['exe'])).parent
            baseline = e.load_baseline(target, readonly=True)
            fstate = feeder.state(e, target) if (target / 'dlss5-feed.addon64').is_file() else None
            managed = bool(baseline and baseline.get('status') == 'active' or fstate and fstate.get('status') == 'active'
                           or row.get('adaptable'))
            detected = (target / 'OptiScaler.ini').is_file() or (target / 'dlss5-feed.addon64').is_file()
            row.update(package_detected=detected, managed=managed, adoption_available=detected and not managed)
            if detected:
                row['installed'] = True
                if not managed:
                    row['installed_on'] = None
            if baseline and baseline.get('offline_route'):
                # Do not hide the anti-cheat flag. A separate scoped policy
                # admits management only while the reviewed route still matches.
                game = bridge.game(e, row)
                row['offline_only'] = bool(game.anti_cheat and offline_routes.allowed(e, game))
                if row['offline_only'] and row.get('blocked') == 'Anti-cheat detected':
                    row['blocked'] = ''
            row['offline_available'] = offline_routes.profile(row) is not None
        except (t.Refusal, e.Stop, OSError, ValueError, KeyError):
            row['adoption_available'] = False
    return rows


def _native(config, row, settings, cache=None):
    selected = settings.get('runtime_provider', 'y4my')
    t.need(selected != 'feeder', 'Select this installation’s OptiScaler package in Graphics before adopting it.')
    e = bridge.module(config, 'y4my' if selected == 'custom' else selected)
    bridge.desktop_mode(e)
    game = bridge.game(e, row)
    target = t.safe(game.target_dir)
    t.need(e.load_baseline(target, readonly=True) is None, 'This installation already has a recovery record. Restore or finish recovery first.')
    ini = t.safe(target / 'OptiScaler.ini')
    t.need(ini.is_file() and ini.stat().st_size <= 256 * 1024, 'No supported OptiScaler settings were found.')
    text = ini.read_text(encoding='utf-8-sig')
    t.ini(text)
    has_nr = (target / 'nvngx_dlssnr.dll').is_file()
    mode = 'nr-mfg' if has_nr and game.dlssg else 'nr-only' if has_nr else 'mfg-only'
    if selected == 'skynizz':
        # A bundled bridge is a distinct recipe, including its private NVIDIA
        # runtimes. Never identify it solely by a filename or version string.
        release, _ = skynizz_provider.bundled_bridge()
        e.Y4MY_PROVIDER = release
    elif selected == 'custom':
        custom = settings.get('custom_package')
        t.need(isinstance(custom, dict), 'Choose and review a custom package before adopting it.')
        e.Y4MY_PROVIDER = custom
    key = (e.Y4MY_PROVIDER.get('sha256'), mode)
    if cache is not None and key in cache:
        payload, meta = cache[key]
    else:
        payload, meta = bridge.payload(e, config, mode)
        if cache is not None:
            cache[key] = payload, meta
    loader = payload.get('dxgi.dll')
    t.need(loader is not None, 'This package does not support Adoption yet.')
    proxies = [name for name in t.SUPPORTED_PROXIES if (target / name).is_file() and t.digest(t.safe(target / name)) == t.sha(loader)]
    t.need(len(proxies) == 1, 'The detected loader does not match the selected package. Choose its package in Graphics, or restore the existing setup first.')
    proxy = proxies[0]
    expected = {proxy if name == 'dxgi.dll' else name: data for name, data in payload.items()}
    hashes = {}
    for name, data in expected.items():
        path = t.safe(target / t.relative(name))
        t.need(path.is_file(), 'The detected package is incomplete: ' + name)
        actual = t.digest(path)
        t.need(name.lower().endswith('.ini') or actual == t.sha(data), 'An existing package file is unrecognized or changed: ' + name)
        hashes[name] = actual
    # No claiming an unknown companion DLL/addon by recursively owning a tree.
    if (target / 'OptiScaler').exists():
        for name in t.files(target / 'OptiScaler').values():
            t.need('OptiScaler/' + name in expected or not name.lower().endswith(('.dll', '.addon64', '.exe')),
                   'Another graphics runtime is present: OptiScaler/' + name)
    t.need(not any((target / name).exists() for name in ('renodx-dlss5.addon64', 'dlss5-feed.addon64', 'renodx-mfgunlock.addon64')),
           'Another NR/MFG hook is present. Resolve it before Adoption.')
    nr, nrmeta = (None, None)
    if has_nr:
        nr, nrmeta = e.load_user_nr_runtime(str(t.safe(target / 'nvngx_dlssnr.dll')), family=None)
        t.need(nr is not None, 'The existing NR model could not be verified.')
        hashes['nvngx_dlssnr.dll'] = t.sha(nr)
    return dict(engine=e, game=game, row=dict(row), target=target, mode=mode, proxy=proxy,
                hashes=hashes, payload=payload, meta=meta, nr=nr, nrmeta=nrmeta, provider=dict(e.Y4MY_PROVIDER))


def _feeder(config, row, settings):
    e = bridge.module(config)
    root, exe, target = feeder.eligible(e, row, existing=True)
    t.need(e.scan_game_files(root)[2] is None, 'Anti-cheat detected; no Feeder offline profile is available.')
    t.need(feeder.state(e, target) is None, 'This Feeder setup already has a management record.')
    found = feeder.inspect(e, row, cached=False)
    names = [*feeder.lock()['assets'], *feeder.CONFIGS, feeder.MODEL]
    hashes = {name: t.digest(t.safe(target / t.relative(name))) for name in names}
    return dict(engine=e, row=dict(row), target=target, root=root, exe=exe, mode='nr-only',
                hashes=hashes, found=found, feeder=True, provider={'id': 'feeder', 'name': 'Feeder NR'})


def _checks(plan):
    e, target = plan['engine'], plan['target']
    hashes = {name: t.digest(t.safe(target / t.relative(name))) for name in plan['hashes']}
    root = t.safe(plan['row']['game'])
    exe = t.safe(root / t.relative(plan['row']['exe']))
    return {'hashes': hashes, 'exe': t.digest(exe), 'baseline': bridge.fingerprint(e, plan['game']) if not plan.get('feeder')
            else feeder.digest(feeder.state_dir(e, target) / 'baseline.json'),
            'offline': offline_routes.receipt(plan['row']) if plan.get('offline') else None}


def prepare(config, rows, operation, settings):
    t.need(operation in ('adopt', 'adopt-clean'), 'Invalid Adoption action.')
    plans, blocked, ready, seen, cache = [], [], [], set(), {}
    for index, row in enumerate(rows, 1):
        ui.progress('Reviewing Adoption', game=row['name'], checked=index-1, total=len(rows))
        try:
            plan = (_feeder(config, row, settings) if row.get('runtime_provider') == 'feeder'
                    else _native(config, row, settings, cache))
            e, target = plan['engine'], plan['target']
            t.need(str(target).casefold() not in seen, 'The same installation was selected twice.')
            seen.add(str(target).casefold())
            t.need(not e._running_processes_under_root(Path(row['game'])), 'Close this game before Adoption.')
            if not plan.get('feeder') and plan['game'].anti_cheat:
                plan['offline'] = offline_routes.receipt(row)
                t.need(not offline_routes.protected_running(), 'Close protected games before reviewing the offline-only exception.')
            if operation == 'adopt-clean':
                t.need(settings.get('runtime_provider') == plan['provider']['id'] or (settings.get('runtime_provider') == 'custom' and plan['provider'].get('custom')),
                       'Clean install requires the matching package. Adopt first, then restore before switching package families.')
                if plan.get('feeder'):
                    files = feeder.stack_files(plan['engine'], settings)
                    plan['clean_payload'] = {}
                    for name in [*feeder.lock()['assets'], *feeder.CONFIGS]:
                        data = feeder.cached_input(plan['engine'], files[name]).read_bytes()
                        t.need(t.sha(data) == files[name]['sha256'], 'The stored Feeder stack changed: ' + name)
                        plan['clean_payload'][name] = data
                    t.need(settings.get('nr_runtime') or feeder.MODEL in files, 'Choose a verified RTX 40 compatible NR model in Settings')
                    model = t.safe(settings.get('nr_runtime') or files[feeder.MODEL]['path'])
                    feeder.model(model)
                    plan['clean_payload'][feeder.MODEL] = model.read_bytes()
                else:
                    # The package/version shown is the app-selected, verified
                    # recipe. Other families need their own restore boundary.
                    if settings.get('nr_runtime') and plan['mode'] != 'mfg-only':
                        plan['nr'], plan['nrmeta'] = e.load_user_nr_runtime(settings['nr_runtime'], family=None)
            plan['checks'] = _checks(plan)
            plan['settings'] = dict(settings)
            plans.append(plan)
            summary = ('Back up this setup and install a fresh ' + plan['provider']['name'] + ' package.' if operation == 'adopt-clean'
                       else 'Keep the current files and settings. Let rtxForge manage this setup.')
            summary += ' Restore returns to the setup found today.'
            if plan.get('offline'):
                summary += ' Offline only · launch from rtxForge. Online play is unavailable with this package.'
            if operation == 'adopt-clean':
                summary += ' NR starts ' + ('on.' if settings.get('nr_on_launch', False) else 'off; enable it from the overlay.')
            provider = plan['provider']
            ready.append({'name': row['name'], 'game': row['game'], 'summary': summary,
                          # Chooser data: what was found, both choices and where Restore returns to.
                          'adoption': {'detected': ' '.join(str(v) for v in (provider.get('name'), provider.get('version')) if v),
                                       'choices': ['adopt', 'adopt-clean'], 'chosen': operation,
                                       'restore_boundary': 'before-adoption'},
                          'detail': json.dumps({'provider': plan['provider'], 'files': plan['hashes'], 'offline': plan.get('offline')}, indent=2)})
        except (t.Refusal, OSError, ValueError, KeyError, RuntimeError) as error:
            blocked.append({'name': row['name'], 'game': row['game'], 'reason': str(error)})
        ui.progress('Game checked', game=row['name'], checked=index, total=len(rows))
    return {'kind': 'adoption', 'operation': operation, 'title': 'Review Adoption', 'plans': plans, 'rows': ready, 'blocked': blocked}


def _check(plan):
    t.need(not plan['engine']._running_processes_under_root(Path(plan['row']['game'])), 'A reviewed game started. Close it and review Adoption again.')
    t.need(_checks(plan) == plan['checks'], 'Files changed since review. Review Adoption again.')
    if plan.get('offline'):
        t.need(not offline_routes.protected_running(), 'A protected game started. Close it before Adoption.')


def _register_native(plan):
    e, game, target = plan['engine'], plan['game'], plan['target']
    baseline = e.create_baseline(game, set(plan['hashes']), plan['proxy'], [])
    baseline['game_root'] = str(game.root)
    baseline['adoption'] = {'created_utc': t.now(), 'restore_boundary': 'before-adoption', 'files': dict(plan['hashes'])}
    if plan.get('offline'):
        baseline['offline_route'] = plan['offline']
    baseline.update(status='active', managed_paths=sorted(plan['hashes']))
    values = t.ini((target / 'OptiScaler.ini').read_text(encoding='utf-8-sig'))
    enabled = values.get('DlssNr', 'Enabled', fallback='false').split(';', 1)[0].strip().lower() == 'true'
    baseline['current'] = {'installed_utc': t.now(), 'archive': plan['meta'], 'provider_id': plan['provider']['id'],
                           'feature_mode': plan['mode'], 'proxy': plan['proxy'], 'installed_hashes': dict(plan['hashes']),
                           'nr_runtime': plan['nrmeta'], 'nr_profile': {'enabled': enabled, 'runtime_verified': False},
                           'compatibility_policy': {'mfg_route': 'adopted-native-route', 'offline_only': bool(plan.get('offline'))}}
    e.save_json_atomic(e.baseline_path(target), baseline)
    e.verify_baseline_integrity(target, baseline, adopt_legacy=False)
    if plan['clean']:
        settings = plan['settings']
        e.install_target(game, plan['payload'], plan['meta'], 'ada', nr_runtime_payload=plan['nr'], nr_runtime_meta=plan['nrmeta'],
                         feature_mode=plan['mode'], enable_effects=True, nr_strength=settings.get('nr_strength', 2.0),
                         mfg_multiplier=settings.get('mfg_multiplier', 'auto'), sharpening_strength=settings.get('sharpening_strength', .5),
                         preserve_visual_settings=False, clean_config=True, nr_on_launch=settings.get('nr_on_launch', False))
    bridge.share_install(e, game, {'mode': plan['mode']})


def _register_feeder(plan):
    e, target, row = plan['engine'], plan['target'], plan['row']
    originals = {name: feeder.cache(e, target / name) for name in plan['hashes']}
    nr = feeder.model(target / feeder.MODEL)
    record = dict(schema=1, provider_id='feeder', status='active', target=str(target), game=row['game'], exe=row['exe'],
                  name=row['name'], originals=originals, adopted=True, created_utc=t.now(),
                  restore_boundary='before-adoption', nr_runtime={**nr, 'cache': originals[feeder.MODEL]}, installed_hashes=plan['hashes'])
    if plan['clean']:
        data = dict(plan['clean_payload'])
        text = data['ReShade.ini'].decode('utf-8-sig')
        text = feeder.configure_new_install(text, plan['settings'].get('nr_on_launch', False))
        import overlay_policy
        if overlay_policy.explicit(plan['settings']): text = overlay_policy.reshade(text, plan['settings'])
        data['ReShade.ini'] = text.encode()
        for name, value in data.items():
            t.atomic_file(t.safe(target / t.relative(name)), value, 0o644)
        record['installed_hashes'] = {name: t.digest(target / name) for name in plan['hashes']}
        nr = feeder.model(target / feeder.MODEL)
        record['nr_runtime'] = {**nr, 'cache': feeder.cache(e, target / feeder.MODEL)}
    t.atomic_file(feeder.state_dir(e, target) / 'baseline.json', (json.dumps(record, indent=2) + '\n').encode(), 0o600)


def execute(review):
    plans = review['plans']
    t.need(plans, 'No Adoption was reviewed.')
    e = plans[0]['engine']
    cancel = review.get('cancel_event')
    with e.mutation_lock():
        for plan in plans:
            _check(plan)
        session = Session(e.STATE_ROOT / 'desktop-operations')
        try:
            for index, plan in enumerate(plans, 1):
                if cancel is not None and cancel.is_set():
                    raise Cancelled('Adoption cancelled. Changes undone.')
                _check(plan)
                plan['clean'] = review['operation'] == 'adopt-clean'
                pe, target = plan['engine'], plan['target']
                paths = [feeder.state_dir(pe, target) if plan.get('feeder') else pe.state_dir_for(target)]
                paths += [target / cross_os.MARKER, target / cross_os.SHARED]
                if plan['clean']:
                    paths += [target / name for name in plan['hashes']]
                    paths += [target / 'OptiScaler']
                checkpoint = session.capture(paths, label=plan['row']['name'])
                ui.progress('Adopting package', game=plan['row']['name'], current=index, total=len(plans))
                try:
                    (_register_feeder if plan.get('feeder') else _register_native)(plan)
                    if not plan['clean']:
                        t.need({name: t.digest(target / name) for name in plan['hashes']} == plan['hashes'], 'Package changed during Adoption.')
                    session.seal(checkpoint)
                except BaseException:
                    session.seal(checkpoint)
                    session.checkpoints[-1]['sealed'] = False
                    session.save()
                    t.need(not pe._running_processes_under_root(Path(plan['row']['game'])), 'Close this game before recovery. Backups retained at ' + str(session.root))
                    session.undo(checkpoint)
                    session.seal(checkpoint)
                    raise
            if cancel is not None and cancel.is_set():
                raise Cancelled('Adoption cancelled. Changes undone.')
            session.complete()
        except Cancelled:
            t.need(not any(p['engine']._running_processes_under_root(Path(p['row']['game'])) for p in plans), 'Close games before recovery. Backups retained at ' + str(session.root))
            session.rollback()
            raise
        except BaseException:
            if session.interrupted() is None:
                session.close('failed')
            raise
    return str(session.root)
