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
from storage import storage


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


def _loader(e, target):
    """The setup's OptiScaler loader, under any name OptiScaler loads as. ReShade
    or another tool may own a second proxy name beside it."""
    present = [name for name in e.PROXY_NAMES if (target / name).is_file()]
    # OptiScaler names itself in its loader; ReShade and other proxies don't.
    found = [name for name in present if b'OptiScaler' in t.safe(target / name).read_bytes()] or present
    t.need(found, 'No OptiScaler loader was found beside the game.')
    t.need(len(found) == 1, 'Several OptiScaler loaders were found: ' + ', '.join(found) + '. Remove the extra one first.')
    return found[0]


def _release(config, provider, settings):
    """The newest pin of a package family."""
    if provider == 'skynizz':
        # A bundled bridge is a distinct recipe, including its private NVIDIA
        # runtimes. Never identify it solely by a filename or version string.
        return skynizz_provider.bundled_bridge()[0]
    if provider == 'custom':
        custom = settings.get('custom_package')
        t.need(isinstance(custom, dict), 'Choose and review a custom package before adopting it.')
        return custom
    return bridge.providers()[provider]


def _older_releases(config, pin):
    """Earlier releases of a family still in the package cache, so a setup an
    older pin installed is recognized. Each is re-verified by hash when loaded."""
    tag, archive = pin.get('tag'), pin.get('archive', '')
    if not tag or tag not in archive or tag not in pin.get('url', ''):
        return []
    prefix, suffix = archive.split(tag, 1)
    found = []
    root = storage(config) / 'packages'
    for path in sorted(root.glob('*/' + prefix + '*' + suffix)) if root.is_dir() else []:
        older = path.name[len(prefix):len(path.name) - len(suffix)]
        if older == tag or path.parent.name == pin['sha256'] or len(path.parent.name) != 64:
            continue
        found.append({**pin, 'tag': older, 'archive': path.name, 'sha256': path.parent.name, 'release_size': path.stat().st_size,
                      'url': pin['url'].replace(tag, older), 'asset_id': None, 'verified_at': None})
    return found


def _payload(e, config, release, mode, cache):
    key = (release.get('sha256'), mode)
    if cache is not None and key in cache:
        return cache[key]
    e.Y4MY_PROVIDER = release
    result = bridge.payload(e, config, mode)
    if cache is not None:
        cache[key] = result
    return result


def _recognize(config, settings, row, loader_sha, mode, cache):
    """The package and release that installed this setup: the selected package
    first, then the other families, newest pin first, then older cached releases.
    Only releases available without a download are compared."""
    selected = settings.get('runtime_provider', 'skynizz')
    families = [selected] + [p for p in ('skynizz', 'dlss-unlocked', 'y4my') if p != selected]
    for provider in families:
        if provider in ('feeder', 'custom') and provider != selected:
            continue
        try:
            pin = _release(config, provider, settings)
        except (t.Refusal, KeyError, OSError, ValueError):
            continue
        for release in [pin, *_older_releases(config, pin)]:
            local = provider in ('skynizz', 'custom') or (storage(config) / 'packages' / release['sha256'] / release['archive']).is_file()
            if not local:
                continue
            e = bridge.module(config, 'y4my' if provider == 'custom' else provider)
            bridge.desktop_mode(e)
            try:
                payload, meta = _payload(e, config, release, mode, cache)
            except (t.Refusal, OSError, ValueError, KeyError, RuntimeError):
                continue
            if payload.get('dxgi.dll') is not None and t.sha(payload['dxgi.dll']) == loader_sha:
                e.Y4MY_PROVIDER = release
                e.Y4MY_CACHE_DIR = storage(config) / 'packages' / release['sha256']
                return e, release, payload, meta
    return None


def _native(config, row, settings, cache=None, clean=False):
    selected = settings.get('runtime_provider', 'skynizz')
    t.need(selected != 'feeder', 'Select a package for games with DLSS in Packages before adopting this setup.')
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
    proxy = _loader(e, target)
    loader_sha = t.digest(t.safe(target / proxy))
    t.need(not any((target / name).exists() for name in ('renodx-dlss5.addon64', 'dlss5-feed.addon64', 'renodx-mfgunlock.addon64')),
           'Another NR/MFG hook is present. Resolve it before Adoption.')
    known = None if clean else _recognize(config, settings, row, loader_sha, mode, cache)
    if clean:
        # Back up whatever is here, then install the selected package's newest pin.
        # The setup found today needs no recipe: Restore returns to its backup.
        release = _release(config, selected, settings)
        payload, meta = _payload(e, config, release, mode, cache)
        e.Y4MY_PROVIDER = release
        hashes = {proxy: loader_sha, 'OptiScaler.ini': t.digest(ini)}
        # Record the whole found tree so the fresh install may replace it.
        if (target / 'OptiScaler').is_dir():
            for name in t.files(target / 'OptiScaler').values():
                hashes['OptiScaler/' + name] = t.digest(t.safe(target / 'OptiScaler' / t.relative(name)))
    else:
        t.need(known is not None, 'rtxForge doesn\'t recognize this OptiScaler build, so it can\'t keep it as is. '
                                  'Back up and clean install replaces it with the newest package; Restore brings this setup back.')
        e, release, payload, meta = known
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
    nr, nrmeta = (None, None)
    if has_nr:
        nr, nrmeta = e.load_user_nr_runtime(str(t.safe(target / 'nvngx_dlssnr.dll')), family=None)
        t.need(nr is not None, 'The existing NR model could not be verified.')
        hashes['nvngx_dlssnr.dll'] = t.sha(nr)
    return dict(engine=e, game=game, row=dict(row), target=target, mode=mode, proxy=proxy,
                hashes=hashes, payload=payload, meta=meta, nr=nr, nrmeta=nrmeta, provider=dict(release))


def _feeder(config, row, settings):
    """Any Feeder NR setup, whatever its Feeder, RenoDX or model version. Keeping
    it records the files found; a clean install replaces them with the pinned stack."""
    e = bridge.module(config)
    root, exe, target = feeder.eligible(e, row, existing=True)
    t.need(e.scan_game_files(root)[2] is None, 'Anti-cheat detected; no Feeder offline profile is available.')
    t.need(feeder.state(e, target) is None, 'This Feeder setup already has a management record.')
    t.need((target / 'dlss5-feed.addon64').is_file() and (target / 'ReShade.ini').is_file(), 'No Feeder NR setup was found.')
    names = [*feeder.lock()['assets'], *feeder.CONFIGS, feeder.MODEL]
    hashes = {name: feeder.digest(target / t.relative(name)) for name in names}
    return dict(engine=e, row=dict(row), target=target, root=root, exe=exe, mode='nr-only',
                hashes=hashes, feeder=True, provider={'id': 'feeder', 'name': 'Feeder NR'})


def _checks(plan):
    e, target = plan['engine'], plan['target']
    # Absent files stay absent: an adopted Feeder setup may lack a recipe file.
    hashes = {name: feeder.digest(target / t.relative(name)) for name in plan['hashes']}
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
                    else _native(config, row, settings, cache, clean=operation == 'adopt-clean'))
            e, target = plan['engine'], plan['target']
            t.need(str(target).casefold() not in seen, 'The same installation was selected twice.')
            seen.add(str(target).casefold())
            t.need(not e._running_processes_under_root(Path(row['game'])), 'Close this game before Adoption.')
            if not plan.get('feeder') and plan['game'].anti_cheat:
                plan['offline'] = offline_routes.receipt(row)
                t.need(not offline_routes.protected_running(), 'Close protected games before reviewing the offline-only exception.')
            if operation == 'adopt-clean':
                if plan.get('feeder'):
                    files = feeder.stack_files(plan['engine'], settings)
                    plan['clean_payload'] = {}
                    for name in [*feeder.lock()['assets'], *feeder.CONFIGS]:
                        data = feeder.cached_input(plan['engine'], files[name]).read_bytes()
                        t.need(t.sha(data) == files[name]['sha256'], 'The stored Feeder stack changed: ' + name)
                        plan['clean_payload'][name] = data
                    t.need(settings.get('nr_runtime') or feeder.MODEL in files, 'Choose a verified NR model for your GPU in Settings')
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
            release = plan['provider'].get('tag') or plan['provider'].get('version') or ''
            package = (plan['provider']['name'] + ' ' + release).strip()
            summary = ('Back up this setup and install ' + package + '.' if operation == 'adopt-clean'
                       else 'Keep the current files and settings (' + package + '). Let rtxForge manage this setup.')
            summary += ' Restore returns to the setup found today.'
            if plan.get('offline'):
                summary += ' Offline only · launch from rtxForge. Online play is unavailable with this package.'
            if operation == 'adopt-clean':
                summary += ' NR starts ' + ('on.' if settings.get('nr_on_launch', False) else 'off; enable it from the overlay.')
            ready.append({'name': row['name'], 'game': row['game'], 'summary': summary,
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


def _feeder_model(target, cached):
    """The NR model found in an adopted Feeder setup; an unlisted model is kept as found."""
    if cached is None:
        return None
    try:
        nr = feeder.model(target / feeder.MODEL)
    except t.Refusal:
        nr = {'path': str(target / feeder.MODEL), 'sha256': cached['sha256'], 'version': None, 'verified': False}
    return {**nr, 'cache': cached}


def _register_feeder(plan):
    e, target, row = plan['engine'], plan['target'], plan['row']
    originals = {name: feeder.cache(e, target / name) if plan['hashes'][name] else None for name in plan['hashes']}
    record = dict(schema=1, provider_id='feeder', status='active', target=str(target), game=row['game'], exe=row['exe'],
                  name=row['name'], originals=originals, adopted=True, created_utc=t.now(),
                  restore_boundary='before-adoption', nr_runtime=_feeder_model(target, originals[feeder.MODEL]),
                  installed_hashes={name: value for name, value in plan['hashes'].items() if value})
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
                    # The fresh package may use another loader name and other root files.
                    roots = {*plan['hashes'], *getattr(pe, 'PROXY_NAMES', ())}
                    roots.update(name for name in plan.get('payload') or {} if '/' not in name and name != 'dxgi.dll')
                    paths += [target / name for name in sorted(roots, key=str.casefold)]
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
