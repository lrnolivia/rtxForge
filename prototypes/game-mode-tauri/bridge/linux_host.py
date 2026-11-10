"""JSON adapter over the existing Linux DesktopService and reviewed tool plans.

No install logic lives here. The normal DesktopService constructor refreshes
installed overlays; bind only its configuration so startup stays read-only.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid


def app_entry():
    value = os.environ.get('RTXFORGE_APP_EXE')
    if not value:
        raise ValueError('Open the installed Game Mode application before adding it to Steam.')
    entry = Path(value).resolve(strict=True)
    if not entry.is_file() or not os.access(entry, os.X_OK):
        raise ValueError('The installed Game Mode executable is unavailable.')
    return entry


def bind(root, send):
    sys.path.insert(0, str(root / 'scripts'))
    sys.path.insert(1, str(root / 'windows/engine-host'))
    import desktop_service
    import rtxforge
    import library_media
    import package_catalog
    import extra_tools
    import engine_bridge
    import runtime_updates
    import runtime_diagnostics
    import game_notes
    import steam_self_install
    import dlss_updates
    import renodx_hdr
    import functional_test
    import beta_report
    import compat_list
    import global_controls
    import overlay_ui
    import overlay_packages
    import artwork_overrides
    import steamgrid_client
    import steamgrid_credentials
    import feeder_provider
    from storage import storage
    import ui

    service = desktop_service.DesktopService.__new__(desktop_service.DesktopService)
    service.config = rtxforge.load_provider()
    library_media.DEFAULTS.setdefault('library_folders', [])
    library_media.DEFAULTS.setdefault('game_hero_focus', {})
    reviews = {}
    running = {}

    def reviewed(title, rows, payload, runner, **extra):
        token = uuid.uuid4().hex
        reviews[token] = (payload, runner)
        return dict(token=token, title=title, rows=rows, **extra)

    def prepare(params):
        review = service.prepare(params['rows'], params['mode'], params['operation'], visual_settings=params.get('settings'), save_defaults=params.get('save_defaults', False))
        review['cancel_event'] = threading.Event()
        return reviewed(review.get('title', 'Review changes'), review.get('rows', []), review, service.execute, blocked=review.get('blocked', []))

    def execute(params):
        record = reviews.pop(params['token'], None)
        if record is None:
            raise ValueError('This review expired. Review the exact changes again.')
        payload, runner = record
        running[params['token']] = record
        try:
            return runner(payload)
        finally:
            running.pop(params['token'], None)

    def discard(params):
        for token in params.get('tokens', [params.get('token')]):
            reviews.pop(token, None)
            inspections.pop(token, None)
        return {}

    def cancel(params):
        record = reviews.get(params.get('token')) or running.get(params.get('token'))
        if record and isinstance(record[0], dict) and record[0].get('cancel_event'):
            record[0]['cancel_event'].set()
        return {'message': 'Cancellation requested at the next safe engine boundary.'}

    def settings_review(params):
        changes = params.get('changes')
        if not isinstance(changes, dict) or not changes or set(changes) - set(library_media.DEFAULTS):
            raise ValueError('Choose supported changed preferences.')
        import overlay_settings
        if set(changes) & set(overlay_settings.DEFAULTS):
            overlay_settings.options(library_media.load_settings(service.config) | changes)
        if 'game_overlay_settings' in changes:
            combined = library_media.load_settings(service.config) | changes
            for game in changes['game_overlay_settings']:
                overlay_settings.effective(combined, game)
        def save(values):
            library_media.save_settings(service.config, library_media.load_settings(service.config) | values)
            return {'message': 'Shared preferences saved.'}
        return reviewed('Review preferences', [{'name': key.replace('_', ' ').capitalize(), 'detail': json.dumps(value)} for key, value in changes.items()], changes, save, action='Save preferences', note='Game files are unchanged.')

    def scan(params):
        settings = library_media.load_settings(service.config)
        folders = settings.get('extra_folders', []) + params.get('folders', [])
        for raw in settings.get('library_folders', []) + params.get('library_folders', []):
            try:
                folders += [str(child) for child in sorted(Path(raw).iterdir())[:1000]
                            if child.is_dir() and not child.is_symlink() and not child.name.startswith('.')]
            except OSError:
                continue
        return compat_list.apply(service.config, service.scan_all(list(dict.fromkeys(folders))), engine_bridge.module(service.config))

    def extra_review(params):
        plan = extra_tools.prepare(service.config, params['row'], params['path'], params['kind'])
        rows = [{'name': plan['name'], 'detail': '\n'.join(('Update ' if change.get('before') else 'Add ') + change['path'] for change in plan['changes'])}]
        return reviewed('Review ' + extra_tools.KINDS[plan['kind']], rows, plan, lambda value: extra_tools.apply(service.config, value),
                        trust='I trust the source of this exact file', action='Install tool', note='Native code will run inside the game. The hash identifies the exact input; it does not establish publisher safety.')

    def extra_restore(params):
        records = [record for record in extra_tools.recoveries(service.config) if record['path'] == params.get('path')]
        if len(records) != 1:
            raise ValueError('This tool recovery is no longer available.')
        return reviewed('Restore tool', [{'name': records[0]['name'], 'detail': 'Restore recorded original files. Changed files are refused.'}], records[0]['path'], lambda value: extra_tools.restore(service.config, value), action='Restore tool')

    def prepare_dlss(params):
        review = dlss_updates.prepare(service.config, params['rows'])
        return reviewed('Review DLSS update', review['rows'], review, lambda value: dlss_updates.execute(service.config, value), blocked=review['blocked'])

    def restore_dlss(params):
        records = runtime_updates.game_recoveries(service.config, params['row']['game'])
        if not records:
            raise ValueError('No DLSS backups for this game.')
        state = records[0]['path']
        review = runtime_updates.restore(service.config, state, False)
        return reviewed('Restore original DLSS files', [{'name': path, 'detail': 'Restore the recorded previous file'} for path in review['files']], state, lambda value: runtime_updates.restore(service.config, value, True), action='Restore')

    def recover(params):
        review = service.review_recovery(params['row'])
        return reviewed(review['title'], review['rows'], review, service.execute, action='Restore')

    def cleanup_review(_params):
        review = service.review_cleanup()
        return reviewed('Remove old NR files', review['rows'], review, service.execute, action='Back up and remove')

    def launch(params):
        appid = str(params.get('appid', ''))
        if not appid.isdecimal():
            raise ValueError('A verified Steam app ID is required.')
        subprocess.Popen(['xdg-open', 'steam://rungameid/' + appid], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {'message': 'Launch request sent to Steam. Runtime activity is not yet reported.'}

    def open_game_folder(params):
        folder = Path(params['row']['game']).resolve(strict=True)
        if not folder.is_dir():
            raise ValueError('This game folder is unavailable.')
        subprocess.Popen(['xdg-open', str(folder)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {'message': 'Game folder opened.'}

    def steam_review(params):
        settings = library_media.load_settings(service.config)
        entry = app_entry()
        plan = steam_self_install.review(service.config, settings, entry=entry)
        result = reviewed('Review Steam shortcut', [{'name': 'rtxForge shortcut', 'detail': str(plan.get('roles', []))}], plan,
                          lambda value: steam_self_install.install(service.config, settings, reviewed=value, entry=entry), action='Add to Steam')
        return result | {key: plan.get(key) for key in ('created', 'profile', 'roles')}

    def steam_status(params):
        settings = library_media.load_settings(service.config)
        entry = app_entry()
        status = steam_self_install.shortcut_status(service.config, settings, entry=entry)
        result = reviewed('Remove rtxForge from Steam', [{'name': 'rtxForge shortcut', 'detail': 'Remove the exact recorded shortcut'}], status,
                          lambda value: steam_self_install.remove(service.config, settings, reviewed=value, entry=entry), action='Remove shortcut')
        return result | {'added': status['added']}

    def notes(params):
        record = game_notes.load(service.config, params['game'])
        record.update(status=params.get('status') or record.get('status', 'Untested'), notes=str(params.get('notes', '')))
        game_notes.save(service.config, params['game'], record)
        return record
    inspections = {}
    def inspect_package(params):
        result = package_catalog.inspect_archive(params['path'])
        token = uuid.uuid4().hex
        inspections[token] = result
        return {key: result.get(key) for key in ('name', 'family', 'confidence', 'sha256', 'parameters', 'warnings')} | {'token': token, 'deployable': result['family'] == 'dlss-unlocked'}
    def use_package(params):
        inspection = inspections.get(params['token'])
        if inspection is None:
            raise ValueError('Inspect the exact package again.')
        record = package_catalog.custom_record(inspection, params.get('values') or {}, trusted=params.get('trusted') is True, review_notes=params.get('notes') or '')
        settings = library_media.load_settings(service.config) | {'custom_package': record, 'runtime_provider': 'custom'}
        library_media.save_settings(service.config, settings)
        inspections.pop(params['token'], None)
        return {'name': record['name'], 'message': 'Package selected for future reviewed operations.'}
    def hdr_review(params):
        plan = renodx_hdr.prepare_remove(service.config, params['row']) if params.get('remove') else renodx_hdr.prepare(service.config, params['row'], params.get('custom_path'))
        return reviewed('Review RenoDX HDR', [{'name': plan['name'], 'detail': '\n'.join(change['path'] for change in plan['changes'])}], plan,
                        lambda value: renodx_hdr.apply(service.config, value), action='Remove HDR' if params.get('remove') else 'Install HDR',
                        trust='I trust this exact add-on' if plan.get('custom') else None, note=renodx_hdr.NOTICE)
    drafts = {}
    def report_draft(params):
        facts = beta_report.context(service.hardware(), compat_list.version(), '', compat_list.package_label(library_media.load_settings(service.config).get('runtime_provider', '')), system='Linux')
        reports = []
        drafts.clear()
        for row in params['rows']:
            report = beta_report.draft(row, facts, game_notes.load(service.config, row['game']))
            drafts[report['id']] = (report, row)
            reports.append({'id': report['id'], 'name': report['name'], 'fields': report['fields'], 'problems': beta_report.problems(report)})
        return {'reports': reports, 'fields': [{'id': key, 'label': label, 'choices': list(beta_report.CHOICES.get(key, ())), 'required': key in beta_report.REQUIRED, 'max': beta_report.LENGTHS.get(key, 0)} for key, label in beta_report.FIELDS]}
    def report_preview(params):
        reports = []
        logs, notes = {}, {}
        for identity in params['ids']:
            if identity not in drafts:
                raise ValueError('This report draft expired.')
            report, row = drafts[identity]
            for key, value in (params.get('edits') or {}).get(identity, {}).items():
                beta_report.correct(report, key, value)
            missing = beta_report.problems(report)
            if missing:
                raise ValueError(' '.join(missing))
            reports.append(report)
            if params.get('logs'):
                logs[identity] = beta_report.collect(row, game_notes.load(service.config, row['game']))
            if params.get('notes'):
                notes[identity] = game_notes.load(service.config, row['game']).get('notes', '')
        preview = beta_report.bundle(reports, logs or None, notes or None, None)
        items = [{'name': name, 'detail': 'Review exact redacted contents', 'details': text} for name, text in preview['files'].items()]
        return reviewed('Review bug report', items, preview, lambda value: beta_report.export(value, beta_report.folder(service.config, params.get('documents'))), action='Save report', note='Saved on this PC. Nothing is uploaded. Check the redacted text for personal information.')
    def global_review(params):
        plan = global_controls.prepare(engine_bridge.module(service.config), storage(service.config), params)
        return reviewed('Review bulk graphics changes', [{'name': value['name'], 'detail': value['summary']} for value in plan['plans']], plan, global_controls.execute, blocked=plan['blocked'], action='Apply to games')
    def overlay_review(params, packages=False):
        e = engine_bridge.module(service.config)
        plan = overlay_packages.prepare(e, storage(service.config), params) if packages else overlay_ui.prepare(e, params)
        return reviewed('Review overlay update' if packages else 'Review game menus', [{'name': value['name'], 'detail': value['summary']} for value in plan['plans']], plan, global_controls.execute, blocked=plan['blocked'], action='Update overlays' if packages else 'Apply menus')
    def art_store(params):
        import transactions as t
        source = t.safe(Path(params['path']))
        t.need(source.is_file(), 'Choose a regular image file.')
        with source.open('rb') as stream:
            data = stream.read(artwork_overrides.MAX_BYTES + 1)
        settings = library_media.load_settings(service.config)
        return {'path': artwork_overrides.store(service.config, settings, params['row'], params['role'], data, credit=params.get('credit') or 'Your artwork', link=params.get('link') or '')}
    def art_reset(params):
        artwork_overrides.reset(service.config, library_media.load_settings(service.config), params['row'], params['role'])
        return {}
    def sgdb_connect(params):
        key = steamgrid_credentials.normalize_key(params.get('key'))
        steamgrid_client.Client(key).validate()
        steamgrid_credentials.save_key(key)
        return {}
    def sgdb_artwork(params):
        assets = steamgrid_client.Client().artwork(params['game_id'], params['role'], page=int(params.get('page', 0)), mime=params.get('mime') or '')
        return [{key: asset.get(key) for key in ('id', 'url', 'thumb', 'width', 'height', 'mime')} | {'author': (asset.get('author') or {}).get('name') or 'Community artist'} for asset in assets]
    def sgdb_download(params):
        import hashlib
        import transactions as t
        data = steamgrid_client.Client.download(params['asset'])
        extension = '.png' if data.startswith(b'\x89PNG') else '.jpg' if data.startswith(b'\xff\xd8') else '.webp'
        path = storage(service.config) / 'desktop/steamgrid-preview' / (hashlib.sha256(data).hexdigest() + extension)
        t.atomic_file(path, data, 0o600)
        return {'path': str(path)}
    def feeder_storage(params):
        if params:
            raise ValueError('Managed Feeder acquisition uses the normal reviewed package installation route on Linux.')
        e = engine_bridge.module(service.config)
        owned = feeder_provider.owned_stack(e)
        return {'stack': None if owned is None else {key: owned.get(key) for key in ('recipe', 'nr_version')}, 'message': 'Managed acquisition runs through installation review; no user-provided stack is required.'}
    def media(params):
        library = library_media.LibraryMedia(service.config, library_media.load_settings(service.config))
        return [dict(game=row['game'], **library.enrich(row, bool(params.get('refresh')))) for row in params['rows']]

    def overlay_status(params):
        import overlay_status as status_inventory
        return status_inventory.snapshot(service.config)

    import overview_summary
    import nr_addons
    import nr_install
    import feeder_character

    def split_render_review(params):
        try:
            children = [reviews[token][0] for token in params['tokens']]
        except KeyError as error:
            raise ValueError('The installation review expired. Review the games again.') from error
        return nr_install.revise_package_reviews(service.config, children, params, service.hardware().get('family') or 'ada')

    def nr_review(params):
        gpu = service.hardware().get('family') or 'ada'
        if 'rows' in params:
            plan = nr_install.prepare_batch(service.config, params['rows'], params['choice'], gpu)
            rows = [{'name': item['name'], 'game': item['game'], 'summary': item['selection'],
                     'details': nr_install.describe_changes(item)} for item in plan['plans']]
            def apply_batch(review):
                return nr_install.apply_batch(service.config, review, lambda name, index, total:
                                              ui.progress('Installing Split Render', game=name, checked=index, total=total))
            return reviewed('Review Split Render', rows, plan, apply_batch, blocked=plan['blocked'], action='Install Split Render')

        remove = params.get('remove', False)
        if type(remove) is not bool:
            raise ValueError('Choose a Split Render action.')
        if remove:
            plan = nr_install.prepare_remove(service.config, params['row'])
        else:
            plan = nr_install.prepare(service.config, params['row'], params['setup'], gpu)
        action = 'Remove Split Render' if remove else 'Install Split Render'
        rows = [{'name': plan['name'], 'game': plan['game'], 'summary': plan.get('selection') or action,
                 'details': nr_install.describe_changes(plan)}]
        return reviewed(action, rows, plan, lambda review: nr_install.apply(service.config, review), action=action)

    def nr_combo_save(params):
        key = nr_addons.save_combo(service.config, params.get('name'), params.get('combo'))
        return {'id': key, 'combos': nr_addons.combos(service.config)}

    methods = dict(overview_inspect=lambda p: overview_summary.inspect(p["row"], engine_bridge.module(service.config)), overlay_status=overlay_status, hello=lambda _p: {'root': str(root), 'platform': 'Linux'}, hardware=lambda _p: service.hardware(), scan=scan,
                   prepare=prepare, execute=execute, cancel=cancel, discard_operation=discard, discard=discard, run=execute,
                   settings_get=lambda _p: library_media.load_settings(service.config), settings_review=settings_review,
                   packages=lambda _p: {'catalog': package_catalog.catalog(service.hardware())},
                   nr_catalog=lambda p: nr_install.catalog_view(service.config, p.get('row')), nr_review=nr_review,
                   feeder_character_apply=lambda p: feeder_character.apply(
                       service.config, p['row'], p.get('stamp'), p.get('skin'),
                       p.get('pass_number', 2), p.get('character', True)),
                   nr_match=lambda p: nr_install.match_batch(service.config, p['rows'], p['choice'], service.hardware().get('family') or 'ada'),
                   nr_check=lambda p: nr_addons.check(p['row'], p['setup']), nr_status=lambda p: nr_install.status(p['row']),
                   nr_combo_save=nr_combo_save,
                   extras_list=lambda p: extra_tools.recoveries(service.config, p['row']), extra_review=extra_review,
                   extra_restore_review=extra_restore, prepare_dlss=prepare_dlss, update_dlss=execute, dlss_restore_review=restore_dlss,
                   dlss_inventory=lambda p: runtime_updates.display_inventory(service.config, p['row']), diagnose=lambda p: runtime_diagnostics.inspect(p['row']),
                   recoveries=lambda _p: service.recoveries(), recovery_review=recover, cleanup_review=cleanup_review, launch_game=launch, open_game_folder=open_game_folder, notes_save=notes,
                   steam_review=steam_review, steam_status=steam_status, steam_install=execute, steam_remove=execute,
                   scan_game=lambda p: compat_list.apply(service.config, service.scan(None, [p['folder']]), engine_bridge.module(service.config)), package_inspect=inspect_package, package_use=use_package,
                   notes_get=lambda p: game_notes.load(service.config, p['game']),
                   hdr_status=lambda p: renodx_hdr.status(service.config, p['row']), hdr_review=hdr_review,
                   test_start=lambda p: game_notes.start(service.config, p['row'], functional_test.preflight(p['row'], library_media.load_settings(service.config))),
                   test_finish=lambda p: game_notes.finish(service.config, p['row'], helper=p.get('helper')),
                   report_draft=report_draft, report_preview=report_preview, global_review=global_review,
                   overlay_ui_review=lambda p: overlay_review(p), overlay_package_review=lambda p: overlay_review(p, True),
                   art_store=art_store, art_reset=art_reset, sgdb_status=lambda _p: {'connected': bool(steamgrid_credentials.load_key())},
                   sgdb_connect=sgdb_connect, sgdb_disconnect=lambda _p: {'external': steamgrid_credentials.clear_key()},
                   sgdb_search=lambda p: [{'id': item['id'], 'name': item['name']} for item in steamgrid_client.Client().search(p['term'])],
                   sgdb_artwork=sgdb_artwork, sgdb_download=sgdb_download, media=media, feeder_storage=feeder_storage)
    from review_plan import ReviewedRoutes
    routes = ReviewedRoutes(prepare, execute, cancel, discard, lambda: library_media.load_settings(service.config),
                            defaults=(settings_review, execute), split_render=split_render_review)
    methods.update(prepare_routes=routes.prepare, execute_routes=routes.execute, cancel_routes=routes.cancel, discard_routes=routes.discard,
                   split_render_routes_review=routes.split_render)

    import activity
    activity_line = activity.Tracker(send)

    def handle(request):
        rid = request.get('id')
        # The same background-activity line as Windows (scripts/activity.py).
        work = ('request', rid if rid is not None else id(request))
        activity_line.begin(work, request.get('method'))
        def report(event):
            if event.get('kind') == 'progress':
                send({'event': 'progress', 'id': rid, **{key: value for key, value in event.items() if key != 'kind'}})
                activity_line.progress(work, event.get('label'), event.get('checked'), event.get('total'))
        try:
            if request['method'] not in methods:
                raise ValueError('This action is Windows-specific in the current engine adapter; the Linux equivalent is not qualified yet.')
            with ui.report_to(report):
                result = methods[request['method']](request.get('params') or {})
            send({'id': rid, 'result': result})
        except Exception as error:
            send({'id': rid, 'error': desktop_service.friendly(str(error))})
        finally:
            activity_line.end(work)
    def shutdown():
        routes.shutdown()
        for token in list(running) + list(reviews):
            cancel({'token': token})
        discard({'tokens': list(reviews)})
    return {'handle': handle, 'send': send, 'shutdown': shutdown}
