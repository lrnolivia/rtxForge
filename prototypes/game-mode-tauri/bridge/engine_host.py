"""Opt-in adapter to the existing Windows host without its startup refresh worker.

Default development never starts this process. Importing the existing host binds
its reviewed methods, but its main() is deliberately not called: main() starts
an automatic overlay refresh which is outside this isolated prototype's scope.
"""
import json
import os
from pathlib import Path
import runpy
import sys
import threading

ALLOWED = frozenset(('hello', 'hardware', 'scan', 'prepare', 'execute', 'cancel', 'discard_operation',
                     'prepare_routes', 'execute_routes', 'cancel_routes', 'discard_routes',
                     'prepare_dlss', 'update_dlss', 'packages', 'extras_list', 'extra_review',
                     'extra_restore_review', 'run', 'discard', 'steam_status', 'steam_review',
                     'steam_install', 'steam_remove', 'recoveries', 'recovery_review', 'cleanup_review', 'open_game_folder',
                     'diagnose', 'dlss_inventory', 'dlss_restore_review', 'launch_game', 'settings_get', 'settings_review', 'notes_get', 'notes_save', 'package_inspect', 'package_use', 'scan_game', 'test_start', 'test_finish', 'hdr_status', 'hdr_review', 'report_draft', 'report_preview', 'global_review', 'overlay_ui_review', 'overlay_package_review', 'storage_inventory', 'storage_review', 'update_check', 'executable_review', 'sgdb_status', 'sgdb_connect', 'sgdb_disconnect', 'sgdb_search', 'sgdb_artwork', 'sgdb_download', 'art_store', 'art_reset', 'art_sync_review', 'art_profiles', 'art_set_profile', 'media', 'feeder_storage'))


def main():
    if os.environ.get('RTXFORGE_PREVIEW_READ_ONLY') == '1' or os.environ.get('RTXFORGE_ENGINE_BRIDGE') != '1':
        print(json.dumps({'event': 'unavailable', 'error': 'Reviewed operations require the opt-in adapter.'}), flush=True)
        return 1
    root = Path(os.environ.get('RTXFORGE_ROOT') or Path(__file__).resolve().parents[3])
    if os.name != 'nt':
        from linux_host import bind
        output = sys.stdout
        sys.stdout = sys.stderr
        lock = threading.Lock()
        def send(message):
            with lock:
                print(json.dumps(message, default=str), file=output, flush=True)
        host = bind(root, send)
        host['send']({'event': 'ready', 'adapter': 'existing Linux DesktopService', 'automaticRefresh': False})
        workers = []
        for line in sys.stdin.buffer:
            request = json.loads(line)
            if request.get('method') not in ALLOWED:
                send({'id': request.get('id'), 'error': 'Unsupported reviewed adapter method.'})
                continue
            workers = [worker for worker in workers if worker.is_alive()]
            worker = threading.Thread(target=host['handle'], args=(request,))
            worker.start()
            workers.append(worker)
        for worker in workers:
            worker.join()
        return 0
    host = runpy.run_path(str(root / 'windows/engine-host/rtxforge_win_host.py'), run_name='rtxforge_prototype_host')
    features = sys.modules['win_features']
    media = sys.modules['library_media']
    # WinUI owns this preferences file. Keep the Python path only as a legacy fallback.
    native_settings = host['LOCAL'] / 'settings.json'
    legacy_settings = media.settings_path(host['service'].config)
    selected_settings = native_settings if native_settings.is_file() else legacy_settings
    media.settings_path = lambda _config: selected_settings
    media.DEFAULTS.setdefault('borderless_4k', False)
    media.DEFAULTS.setdefault('game_folders', [])
    media.DEFAULTS.setdefault('library_folders', [])
    try:
        stored = json.loads(selected_settings.read_text(encoding='utf-8-sig')) if selected_settings.is_file() else {}
        if not isinstance(stored, dict):
            raise ValueError('The shared preferences file is not an object.')
        # Existing native-only keys survive calls through the shared atomic writer.
        for key, value in stored.items():
            media.DEFAULTS.setdefault(key, value)
        media.DEFAULTS.setdefault('game_executables', {})
    except (OSError, ValueError) as error:
        raise ValueError('Shared preferences could not be loaded safely: ' + str(error)) from error
    def launch_game(params):
        appid = str(params.get('appid', ''))
        if not appid.isdecimal():
            raise ValueError('A verified Steam application ID is required.')
        os.startfile('steam://rungameid/' + appid)
        return {'message': 'Launch request sent to Steam. Runtime activity is not yet reported.'}
    def save_settings(changes):
        settings = media.load_settings(host['service'].config)
        if selected_settings.is_file():
            current = json.loads(selected_settings.read_text(encoding='utf-8-sig'))
            if not isinstance(current, dict):
                raise ValueError('Shared preferences changed. Reload them before saving.')
            settings.update(current)
        for key, value in changes.items():
            if key not in media.DEFAULTS or type(value) not in (bool, int, float, str, list, dict, type(None)):
                raise ValueError('Unsupported preference: ' + key)
        media.save_settings(host['service'].config, settings | changes)
        return {'message': 'Preferences saved through the existing shared settings service.'}
    def open_game_folder(params):
        folder = Path(params['row']['game']).resolve(strict=True)
        if not folder.is_dir():
            raise ValueError('This game folder is unavailable.')
        os.startfile(str(folder))
        return {'message': 'Game folder opened.'}
    def settings_review(params):
        changes = params.get('changes')
        if not isinstance(changes, dict) or not changes:
            raise ValueError('Choose at least one changed preference.')
        for key in changes:
            if key not in media.DEFAULTS:
                raise ValueError('Unsupported preference: ' + key)
        import overlay_settings
        if set(changes) & set(overlay_settings.DEFAULTS):
            overlay_settings.options(media.load_settings(host['service'].config) | changes)
        if 'game_overlay_settings' in changes:
            combined = media.load_settings(host['service'].config) | changes
            for game in changes['game_overlay_settings']:
                overlay_settings.effective(combined, game)
        return features._review('prototype-settings', 'Review preferences',
            [features._item(key.replace('_', ' ').capitalize(), json.dumps(value), 'Save') for key, value in changes.items()],
            action='Save preferences', payload=changes, note='These preferences are shared with the existing application. Game files are unchanged.')
    def scan_game(params):
        import feeder_provider
        import package_adoption
        import skynizz_provider
        import vulkan_app
        import executable_selection
        service = host['service']
        engine = host['engine_bridge'].module(service.config)
        with executable_selection.choices(media.load_settings(service.config).get('game_executables')):
            rows = service.scan(None, [params['folder']])
        rows = feeder_provider.expand_rows(engine, rows, selected=params.get('runtime_provider') == 'feeder')
        package_adoption.decorate(engine, rows)
        vulkan_app.decorate(rows, service.config, selected=params.get('runtime_provider') == 'vulkan-native')
        checked = skynizz_provider.scan_rows([dict(row) for row in rows], params.get('feature_mode', 'mfg-only'))
        for row, verdict in zip(rows, checked):
            row['package_blocked'] = row.get('blocked', '')
            row['skynizz_blocked'] = verdict.get('blocked', '')
            if params.get('runtime_provider') == 'skynizz':
                row.update(verdict)
        features.decorate(rows)
        return rows
    import executable_selection
    def executable_review(params):
        row = params['row']
        value = executable_selection.review(host['engine_bridge'].module(host['service'].config), row, params.get('path'))
        def save_executable(payload):
            current = media.load_settings(host['service'].config)
            choices = dict(current.get('game_executables') or {})
            identity = executable_selection.key(payload['game'])
            if payload['reset']:
                choices.pop(identity, None)
                choices.pop(payload['game'], None)
            else:
                choices[identity] = payload['exe']
            return save_settings({'game_executables': choices})
        features.RUNNERS['prototype-executable'] = save_executable
        return features._review('prototype-executable', 'Review game executable', [features._item(row['name'], value['exe'], 'Use executable')], action='Use detected executable' if not params.get('path') else 'Save executable choice', payload={'game': row['game'], 'exe': value['exe'], 'reset': not bool(params.get('path'))}, note='The existing validator checks architecture, ownership and the selected installation before this choice is saved.')
    features.RUNNERS['prototype-settings'] = save_settings
    import game_notes
    host['METHODS'].update(launch_game=launch_game, open_game_folder=open_game_folder, settings_get=lambda _p: media.load_settings(host['service'].config), settings_review=settings_review, scan_game=scan_game,
                           notes_get=lambda p: game_notes.load(host['service'].config, p['game']), executable_review=executable_review)
    original_prepare = host['METHODS']['prepare']
    def prepare(params):
        return original_prepare(dict(params, settings=media.load_settings(host['service'].config) | (params.get('settings') or {})))
    host['METHODS']['prepare'] = prepare
    original_discard = host['METHODS']['discard_operation']
    def discard_reviews(params):
        tokens = params.get('tokens', [params.get('token')])
        original_discard({'tokens': tokens})
        for token in tokens:
            features.discard({'token': token})
            host['steam_reviews'].pop(token, None)
        return {}
    host['METHODS']['discard_operation'] = discard_reviews
    host['METHODS']['discard'] = discard_reviews
    original_update_check = host['METHODS']['update_check']
    def update_check(params):
        result = original_update_check(params)
        if result.get('token'):
            result.update(action='Download verified installer', note='The existing updater verifies and saves the installer. This prototype does not close or replace the installed application.')
        return result
    host['METHODS']['update_check'] = update_check
    original_feeder_storage = host['METHODS']['feeder_storage']
    def managed_feeder_storage(params):
        if set(params) - {'legacy'} or type(params.get('legacy', False)) is not bool:
            raise ValueError('Feeder acquisition is managed. User-provided stacks are not required.')
        return original_feeder_storage(params)
    host['METHODS']['feeder_storage'] = managed_feeder_storage
    from review_routes import ReviewedRoutes
    def execute_child(params):
        token = params['token']
        host['running'][token] = host['reviews'].get(token, {})
        try:
            return host['execute'](params)
        finally:
            host['running'].pop(token, None)
    routes = ReviewedRoutes(prepare, execute_child, host['cancel'], discard_reviews, lambda: media.load_settings(host['service'].config),
                            defaults=(settings_review, host['METHODS']['run']))
    host['METHODS'].update(prepare_routes=routes.prepare, execute_routes=routes.execute, cancel_routes=routes.cancel, discard_routes=routes.discard)
    host['_DOWNLOAD_METHODS'].update(('prepare_routes', 'execute_routes'))
    host['send']({'event': 'ready', 'adapter': 'existing Windows reviewed host', 'automaticRefresh': False})
    workers = []
    for line in sys.stdin.buffer:
        try:
            request = json.loads(line)
            method = request.get('method')
            if method not in ALLOWED:
                host['send']({'id': request.get('id'), 'error': 'Method is outside this prototype’s reviewed adapter.'})
                continue
            if method in ('update_dlss',) and 'token' not in (request.get('params') or {}):
                host['send']({'id': request.get('id'), 'error': 'A fresh exact review token is required.'})
                continue
            workers = [worker for worker in workers if worker.is_alive()]
            if method == 'cancel':
                host['handle'](request)
            else:
                worker = threading.Thread(target=host['handle'], args=(request,), daemon=False)
                worker.start()
                workers.append(worker)
        except (ValueError, TypeError) as error:
            host['send']({'error': str(error)})
    for worker in workers:
        worker.join()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
