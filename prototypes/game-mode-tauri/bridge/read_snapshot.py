"""Bounded, read-only presentation adapter. Never imports DesktopService or calls writes.

Uses the existing discovery manifest/VDF parsers. Presence in this snapshot is
library discovery, not engine eligibility, ownership verification or live status.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import subprocess

MAX_JSON = 4 * 1024 * 1024
MAX_GAMES = 1000
PREFERENCE_KEYS = ('default_profile', 'nr_on_launch', 'manage_dlss_files', 'borderless_4k', 'recognize_previous',
                   'vulkan_experimental', 'library_view', 'online_art', 'steam_metadata', 'extra_folders', 'game_folders', 'library_folders', 'removed_games',
                   'steam_artwork_profile', 'ui_scale', 'navigation_position', 'button_glyphs', 'controller_glyphs',
                   'controller_hints', 'auto_update', 'overlay_renderer', 'overlay_controls', 'overlay_theme',
                   'overlay_appearance', 'overlay_welcome', 'overlay_welcome_position', 'overlay_live_stats',
                   'panel_hotkey', 'overlay_helper', 'overlay_start_with_windows', 'optiscaler_ui', 'optiscaler_intro',
                   'optiscaler_hotkey', 'reshade_ui', 'reshade_intro', 'vulkan_mfg_native_menu')


def display_hardware(root):
    """Display labels only, using the native host's read-only GPU query.

    No host startup, service constructor, helper refresh or eligibility result.
    """
    if not (root / 'scripts/hardware.py').is_file():
        return {}
    import hardware
    if os.name != 'nt':
        info = hardware.detect()
        return {key: info.get(key) for key in ('gpu', 'driver', 'vram', 'cpu')}
    info = {'gpu': 'Unavailable', 'driver': 'Unavailable', 'vram': 'Unavailable', 'cpu': platform.processor()}
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader,nounits'],
                                text=True, capture_output=True, timeout=5, check=True, creationflags=0x08000000)
        rows = [line.split(',') for line in result.stdout.strip().splitlines() if line.count(',') >= 2]
        supported = [row for row in rows if hardware.family(row[0])]
        selected = (sorted(supported, key=lambda row: hardware.FAMILIES.index(hardware.family(row[0])))[-1:] or rows)[0]
        info.update(gpu=selected[0].strip(), driver=selected[1].strip(), vram=selected[2].strip() + ' MiB')
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    return info


def cached_image(raw, budget, limit=1000000):
    if not isinstance(raw, str) or not raw or budget[0] <= 0:
        return None
    path = Path(raw)
    try:
        size = path.stat().st_size
        if path.is_symlink() or size > min(limit, budget[0]):
            return None
        data = path.read_bytes()
        mime = 'image/jpeg' if data.startswith(b'\xff\xd8\xff') else 'image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'image/webp' if data[:4] == b'RIFF' and data[8:12] == b'WEBP' else None
        if not mime:
            return None
        budget[0] -= len(data)
        return 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')
    except (OSError, ValueError):
        return None


def read_json(path: Path, fallback=None):
    try:
        if path.stat().st_size > MAX_JSON:
            raise ValueError('JSON file exceeds reader limit')
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return fallback


def settings_path():
    override = os.environ.get('RTXFORGE_STATE_ROOT')
    if override:
        return Path(override) / 'desktop/settings.json'
    if os.name == 'nt':
        local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'rtxForge'
        native = local / 'settings.json'
        return native if native.is_file() else local / 'state/desktop/settings.json'
    return Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'rtxforge/desktop/settings.json'


def load_discovery(root):
    spec = importlib.util.spec_from_file_location('rtxforge_snapshot_discovery', root / 'scripts/discovery.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    prior = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = prior
    return module


def steam_roots(discovery):
    candidates = list(discovery.steam_roots()) if os.name != 'nt' else []
    if os.name == 'nt':
        import winreg
        for hive, key, field in [(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                                 (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')]:
            try:
                with winreg.OpenKey(hive, key) as registry:
                    candidates.append(Path(winreg.QueryValueEx(registry, field)[0]))
            except OSError:
                pass
        candidates += [Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Steam']
    candidates += [Path(value) for value in os.environ.get('RTXFORGE_STEAM_ROOTS', '').split(os.pathsep) if value]
    return list(dict.fromkeys(p.resolve() for p in candidates if p.is_dir()))


def art_for(appid, roots, budget, kind='poster'):
    if budget[0] <= 0:
        return None
    for root in roots:
        cache = root / 'appcache/librarycache'
        native = {'hero': 'library_hero', 'capsule': 'header'}.get(kind, 'library_600x900')
        candidates = []
        # Match the latest Steam account's user-picked grid before the cache.
        try:
            login = (root / 'config/loginusers.vdf').read_text(encoding='utf-8')
            accounts = []
            for uid, body in re.findall(r'"(7656119\d+)"\s*\{([^}]+)\}', login):
                stamp = re.search(r'"Timestamp"\s*"(\d+)"', body)
                accounts.append((int(stamp[1]) if stamp else 0, int(uid)-76561197960265728))
            if accounts:
                grid = root / 'userdata' / str(max(accounts)[1]) / 'config/grid'
                custom = {'hero': appid+'_hero', 'capsule': appid}.get(kind, appid+'p')
                candidates.extend(grid / (custom+ext) for ext in ('.png','.jpg','.jpeg','.webp'))
        except (OSError,ValueError):
            pass
        for extension in ('.jpg', '.png', '.webp'):
            candidates += [cache / f'{appid}_{native}{extension}', cache / appid / f'{native}{extension}']
            candidates += sorted((cache / appid).glob(f'*/{native}{extension}'))[:3]
        for path in candidates:
            try:
                size = path.stat().st_size
                if size > (1000000 if kind == 'hero' else 300000) or size > budget[0] or path.is_symlink():
                    continue
                data = path.read_bytes()
                mime = 'image/jpeg' if data.startswith(b'\xff\xd8\xff') else 'image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'image/webp' if data[:4] == b'RIFF' and data[8:12] == b'WEBP' else None
                if mime is None:
                    continue
                budget[0] -= len(data)
                return 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')
            except OSError:
                continue
    return None



def local_art_sources(settings_file, settings, row, appid, name):
    identity = hashlib.sha256((str(appid or '') + name).encode()).hexdigest()[:24]
    media_root = settings_file.parent / 'state/desktop/media' if os.name == 'nt' and settings_file.parent.name.casefold() == 'rtxforge' else settings_file.parent / 'media'
    media = (read_json(media_root / (identity+'.json'), {}) or {}).get('data', {})
    overrides = (settings.get('game_artwork') or {}).get(row.get('game'), {})
    saved = row.get('art') or {}
    return {role: (overrides.get(role) or {}).get('path') or saved.get(role) or media.get(role)
            for role in ('poster','hero','capsule')}


def local_artwork(game_id, role, *, settings_file=None):
    # The caller selects an existing opaque game ID and a fixed artwork role,
    # never an arbitrary filesystem path. Large art travels on demand.
    if role not in ('poster','hero','capsule'):
        raise ValueError('Unsupported artwork role')
    settings_file = settings_file or settings_path()
    settings = read_json(settings_file, {})
    saved = read_json(settings_file.parent / 'state/library-snapshot.json', {})
    for row in saved.get('rows', [])[:2000]:
        if not isinstance(row,dict) or not isinstance(row.get('game'),str):
            continue
        path = row['game']; identity = os.path.normcase(str(Path(path).resolve()))
        appid = str(row.get('metadata_appid') or row.get('appid') or '')
        accepted = {'saved:'+hashlib.sha256(identity.encode()).hexdigest()[:12],
                    'folder:'+hashlib.sha256(path.encode()).hexdigest()[:12]}
        if appid.isdecimal():
            accepted.add('steam:'+appid+':'+hashlib.sha256(path.encode()).hexdigest()[:12])
        if game_id not in accepted:
            continue
        sources = local_art_sources(settings_file,settings,row,appid,str(row.get('name') or Path(path).name))
        return cached_image(sources.get(role),[11*1024*1024],limit=11*1024*1024)
    return None


def collect(root, *, settings_file=None, roots=None):
    discovery = load_discovery(root)
    warnings = []
    settings_file = settings_file or settings_path()
    try:
        settings = read_json(settings_file, {})
        if not isinstance(settings, dict):
            raise ValueError('Expected settings object')
    except (OSError, ValueError) as error:
        settings = {}
        warnings.append(f'Saved settings could not be read: {error}')
    roots = roots if roots is not None else steam_roots(discovery)
    libraries = list(roots)
    for steam in roots:
        try:
            libraries += discovery.parse_vdf_paths(steam / 'steamapps/libraryfolders.vdf')
        except (OSError, ValueError):
            warnings.append('A Steam library list could not be read.')
    libraries = list(dict.fromkeys(Path(p).resolve() for p in libraries if Path(p).is_dir()))
    games, seen = [], set()
    removed = settings.get('removed_games', [])
    art_budget = [8 * 1024 * 1024]
    for library in libraries:
        try:
            manifests = sorted((library / 'steamapps').glob('appmanifest_*.acf'))[:MAX_GAMES]
            for manifest in manifests:
                if len(games) >= MAX_GAMES:
                    warnings.append('Library display is limited to 1,000 entries.')
                    break
                if manifest.stat().st_size > 256000:
                    continue
                record = discovery.parse_appmanifest(manifest)
                if not record or discovery.is_library_tool(record.get('name', ''), record.get('appid')):
                    continue
                name = record['installdir']
                # Never let a malformed manifest escape its Steam common folder.
                if Path(name).name != name or name in ('.', '..') or '\\' in name or '/' in name:
                    continue
                folder = library / 'steamapps/common' / name
                if not folder.is_dir() or str(folder) in removed or str(folder) in seen:
                    continue
                seen.add(str(folder))
                appid = record['appid']
                if not appid.isdecimal():
                    continue
                games.append(dict(id=f'steam:{appid}:' + hashlib.sha256(str(folder).encode()).hexdigest()[:12], name=record['name'], path=str(folder), appid=appid,
                                  source='Steam', status='Not checked', art=art_for(appid, roots, art_budget)))
        except OSError as error:
            warnings.append(f'A Steam library could not be read: {error}')
    extras = list(settings.get('extra_folders') or []) + list(settings.get('game_folders') or [])
    collections = list(settings.get('library_folders') or []) + [str(library / 'PinnedBuilds') for library in libraries]
    for raw in collections[:MAX_GAMES]:
        if not isinstance(raw, str):
            continue
        try:
            extras += [str(child) for child in sorted(Path(raw).iterdir())[:MAX_GAMES]
                       if child.is_dir() and not child.is_symlink() and not child.name.startswith('.')
                       and not discovery.is_library_tool(child.name)]
        except OSError:
            continue
    for raw in extras[:MAX_GAMES] if isinstance(extras, list) else []:
        if not isinstance(raw, str):
            continue
        folder = Path(raw)
        if folder.is_dir() and str(folder) not in seen and str(folder) not in removed:
            seen.add(str(folder))
            games.append(dict(id='folder:' + hashlib.sha256(str(folder).encode()).hexdigest()[:12], name=folder.name, path=str(folder), appid=None,
                              source='Saved folder', status='Not checked', art=None))
    snapshot_file = settings_file.parent / 'state/library-snapshot.json'
    cached_rows = {}
    try:
        saved = read_json(snapshot_file, {})
        if isinstance(saved, dict) and saved.get('schema') == 1:
            cached_rows = {os.path.normcase(str(Path(row['game']).resolve())): row for row in saved.get('rows', [])[:2000]
                           if isinstance(row, dict) and isinstance(row.get('game'), str)}
    except (OSError, ValueError, TypeError):
        pass
    # The native snapshot includes exact child installations (for example,
    # separate executables within a collection). It supplies display identity
    # only; the operation adapter still performs a fresh exact-game scan.
    visible = {os.path.normcase(str(Path(game['path']).resolve())) for game in games}
    hidden = {os.path.normcase(str(Path(path).resolve())) for path in removed if isinstance(path, str)}
    for identity, row in cached_rows.items():
        folder = Path(row['game'])
        name = str(row.get('name') or folder.name)
        if identity in visible or identity in hidden or not folder.is_dir() or discovery.is_library_tool(name, row.get('appid')):
            continue
        appid = str(row.get('metadata_appid') or row.get('appid') or '')
        appid = appid if appid.isdecimal() else None
        games.append(dict(id='saved:' + hashlib.sha256(identity.encode()).hexdigest()[:12], name=name, path=str(folder),
                          appid=appid, source='Steam' if row.get('source') == 'Steam' and appid else 'Saved folder',
                          provenance='Saved library check', status='Not checked', art=art_for(appid, roots, art_budget) if appid else None))
        visible.add(identity)
        if len(games) >= MAX_GAMES:
            break
    games.sort(key=lambda game: game['name'].casefold())
    for game in games:
        game['hero'] = art_for(game['appid'], roots, art_budget, 'hero') if game['appid'] else None
        game['capsule'] = art_for(game['appid'], roots, art_budget, 'capsule') if game['appid'] else None
        try:
            # LibraryMedia records are keyed by Steam ID + displayed name,
            # not installation path. Read the existing cache without fetching.
            identity = hashlib.sha256((str(game.get('appid') or '') + game['name']).encode()).hexdigest()[:24]
            media_root = settings_file.parent / 'state/desktop/media' if os.name == 'nt' and settings_file.parent.name.casefold() == 'rtxforge' else settings_file.parent / 'media'
            media = (read_json(media_root / f'{identity}.json', {}) or {}).get('data', {})
            saved_row = cached_rows.get(os.path.normcase(str(Path(game['path']).resolve())), {})
            art = saved_row.get('art') or {}
            metadata_id = str(saved_row.get('metadata_appid') or saved_row.get('appid') or '')
            if not game.get('appid') and metadata_id.isdecimal():
                game['appid'] = metadata_id
                game['art'] = art_for(metadata_id, roots, art_budget)
                game['hero'] = art_for(metadata_id, roots, art_budget, 'hero')
                game['capsule'] = art_for(metadata_id, roots, art_budget, 'capsule')
            game['savedRecord'] = {key: saved_row[key] for key in ('installed', 'profile', 'runtime_provider', 'installed_on', 'installed_oses', 'dlss_version', 'compat', 'exe', 'blocked', 'nr_on_launch', 'nr_enabled', 'nr_strength', 'sharpening_strength', 'mfg_multiplier', 'dynamic_mfg', 'mfg_saved_mode', 'mfg_saved_multiplier', 'feature_controls', 'feature_mode', 'dynamic_mfg_available') if key in saved_row}
            test = saved_row.get('test_record') or {}
            if isinstance(test, dict) and test.get('status') in ('Untested','Working','Problem','Bench'):
                game['testStatus'] = test['status']
            if isinstance(test, dict):
                game['notes'] = str(test.get('notes') or '')[:32768]
                game['testActive'] = bool(test.get('active'))
            for key in ('description','developers','release'):
                if art.get(key):
                    game[key] = art[key]
            for setting, field in (('game_accents','accent'), ('game_hero_focus','heroFocus')):
                choices = settings.get(setting) or {}
                value = next((value for path, value in choices.items() if os.path.normcase(str(Path(path).resolve())) == os.path.normcase(str(Path(game['path']).resolve()))), None)
                if field == 'accent' and isinstance(value, str) and len(value) == 7 and value.startswith('#') and all(c in '0123456789abcdefABCDEF' for c in value[1:]):
                    game[field] = value
                if field == 'heroFocus' and isinstance(value, list) and len(value) == 2 and all(isinstance(n, (int,float)) and 0 <= n <= 1 for n in value):
                    game[field] = value
            overrides = (settings.get('game_artwork') or {}).get(game['path'], {})
            for role, field in (('poster', 'art'), ('hero', 'hero'), ('capsule', 'capsule')):
                source = (overrides.get(role) or {}).get('path') or art.get(role) or media.get(role)
                image = cached_image(source, art_budget)
                if image:
                    game[field] = image
                elif isinstance(source,str) and Path(source).is_file():
                    game.setdefault('localArtwork', []).append(role)
            for field in ('description', 'developers', 'release'):
                if media.get(field):
                    game[field] = media[field]
        except (OSError, ValueError, TypeError, AttributeError):
            warnings.append('Some cached game metadata could not be read.')
    locks = read_json(root / 'providers/lock.json', {})
    packages = [dict(id=key, name=value.get('name', key), version=value.get('tag', value.get('version', 'Unspecified')),
                     repository=value.get('repo', ''), sha256=value.get('sha256', ''), status='Catalog record')
                for key, value in locks.items() if isinstance(value, dict) and value.get('name')]
    catalog = []
    try:
        if (root / 'scripts/package_catalog.py').is_file():
            sys.path.insert(0, str(root / 'scripts'))
            import package_catalog
            catalog = package_catalog.catalog({'system': platform.system(), 'architecture': platform.machine(), 'ready': False, 'reason': 'Not checked in preview'})
    except (OSError, ValueError, ImportError, RuntimeError):
        pass
    preference_defaults, overlay_defaults, overlay_themes = {}, {}, {}
    if (root / 'scripts/library_media.py').is_file():
        import library_media
        import glass_preferences
        preference_defaults = library_media.DEFAULTS
        overlay_defaults = glass_preferences.DEFAULTS
        for mode in ('clear', 'light', 'dark', 'accent'):
            values = {}
            glass_preferences.theme(values, mode)
            overlay_themes[mode] = values['overlay_appearance']
    overlay_report = None
    try:
        report_path = settings_file.parent / ('state/overlay-refresh.json' if os.name == 'nt' else '../overlay-refresh.json')
        overlay_report = read_json(report_path)
        if not isinstance(overlay_report, dict):
            overlay_report = None
    except (OSError, ValueError):
        pass
    return dict(schema=1, source='Local library reader', platform=platform.system(), readOnly=True,
                capturedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(), games=games[:MAX_GAMES], packages=packages, catalog=catalog,
                warnings=warnings, libraryCount=len(libraries), settingsFound=settings_file.is_file(),
                preferences={key: settings.get(key, preference_defaults.get(key)) for key in PREFERENCE_KEYS},
                preferenceDefaults={key: preference_defaults.get(key) for key in PREFERENCE_KEYS},
                overlayDefaults=overlay_defaults, overlayThemes=overlay_themes,
                overlayReport=overlay_report,
                hardware=display_hardware(root),
                defaults={key: settings.get(key) for key in ('runtime_provider', 'default_profile', 'mfg_provider', 'nr_on_launch', 'mfg_multiplier',
                          'nr_strength', 'sharpening_strength', 'reduce_motion', 'overlay_theme', 'feature_controls', 'dynamic_mfg', 'mfg_saved_mode', 'mfg_saved_multiplier', 'controller_glyphs', 'controller_hints')},
                controlSchema=read_json(root / 'providers/skynizz-bridge/controls.json', {'groups': [], 'controls': []}),
                operations=dict(available=False, reason='Installation and tuning require the existing reviewed operation bridge.'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--artwork')
    parser.add_argument('--role', choices=('poster','hero','capsule'))
    args = parser.parse_args()
    try:
        snapshot = {'image': local_artwork(args.artwork,args.role)} if args.artwork else collect(args.root.resolve())
        sys.stdout.reconfigure(encoding='utf-8')
        print(json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')))
    except (OSError, ValueError, ImportError) as error:
        print(f'Local library reader failed: {error}', file=sys.stderr)
        sys.exit(1)
