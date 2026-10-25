"""Bounded app routing for the reviewed BG3/RDR2 native Vulkan package."""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import zipfile

import overlay_settings
import transactions as t
import ui
import vulkan_dlssg_provider as provider

ROOT = Path(__file__).resolve().parents[1]
ID = 'vulkan-native'
TITLE = 'Vulkan NR + Universal MFG'
PROFILES = {'bg3': ('bg3.exe', "Baldur’s Gate 3"), 'rdr2': ('RDR2.exe', 'Red Dead Redemption 2')}


def state_root(config=None):
    if os.environ.get('RTXFORGE_VULKAN_STATE'):
        return t.safe(os.environ['RTXFORGE_VULKAN_STATE'])
    if os.name == 'nt':
        return t.safe(Path(os.environ['LOCALAPPDATA']) / 'rtxForge/vulkan-native')
    from storage import storage
    return storage(config or {}) / 'vulkan-native'


def bundled():
    pin = t.read_json(ROOT / 'providers/vulkan-dlssg/bundle.json')
    folders = (ROOT / 'providers/vulkan-dlssg/runtime', ROOT / 'windows/out/vulkan-provider')
    for folder in folders:
        manifest = folder / 'candidate.json'
        if not manifest.is_file():
            continue
        expected = pin['files']['candidate.json']
        t.need(manifest.stat().st_size == expected['size'] and t.digest(manifest) == expected['sha256'], 'Vulkan package receipt changed. Reinstall rtxForge.')
        data = t.read_json(manifest)
        archive = t.safe(folder / t.relative(data['archive']['name']))
        t.need(archive.is_file() and archive.stat().st_size == data['archive']['size']
               and t.digest(archive) == data['archive']['sha256'], 'Vulkan package changed. Reinstall rtxForge.')
        return folder, manifest, archive, data
    raise t.Refusal('The Vulkan package is missing from this build. Reinstall the full x64 build.')


def profile_for(row):
    root = t.safe(row['game'])
    # Identify by the profiled executable and known stock Bink at review time,
    # never by a title substring or generic Vulkan import.
    for key, (exe, _) in PROFILES.items():
        target = root / 'bin' if key == 'bg3' and (root / 'bin' / exe).is_file() else root
        if (target / exe).is_file():
            return key, t.safe(target)
    return None, None


def owned(row, config=None):
    key, target = profile_for(row)
    if key is None:
        return None
    path = provider.state_path(target, state_root(config)) / 'baseline.json'
    if not path.is_file():
        return None
    data = t.read_json(path)
    t.need(data.get('provider_id') == 'rtxforge-vulkan-native:' + key and data.get('target') == str(target), 'Vulkan recovery identity differs.')
    return data if data.get('status') != 'restored' else None


def confirmed():
    """The games this package has a reviewed profile for, by name."""
    return [name for _, name in PROFILES.values()]


def decorate(rows, config=None, selected=False):
    # Like Feeder NR, profiled Vulkan games take this package automatically whenever the
    # build bundles it, beside whichever package is chosen for other DLSS games.
    try:
        bundled()
        available = True
    except (t.Refusal, OSError, ValueError, KeyError):
        available = False
    for row in rows:
        try:
            key, target = profile_for(row)
            if key is None:
                if selected and not row.get('installed'):
                    row['blocked']='The Vulkan package supports only its confirmed games.'
                continue
            row['vulkan_profile'] = key
            record = owned(row, config)
            if (available or selected) and not record and not row.get('installed'):
                row.update(install_provider=ID,vulkan_available=available,graphics_apis=['Vulkan'],
                           blocked='Anti-cheat detected; this game is excluded.' if row.get('anti_cheat') else '')
            if record:
                row.update(installed=True, runtime_provider=ID, install_provider=ID,
                           feature_mode='nr-mfg', profile='NR + MFG', graphics_apis=['Vulkan'],
                           mfg_route='Native Vulkan DLSS-G · Universal Experimental', dynamic_mfg_available=False)
                row['exe'] = (target / PROFILES[key][0]).relative_to(Path(row['game'])).as_posix()
                row['blocked'] = '' if record.get('status') == 'active' else 'Vulkan installation needs recovery. Review Restore Original Files.'
        except (t.Refusal, OSError, ValueError, KeyError) as error:
            row['vulkan_detail'] = str(error)
    return rows


def local_model(explicit, e, cache):
    """An explicit override never falls back to the bundled model."""
    folder, manifest, archive, data = bundled()
    if not explicit:
        return folder, manifest, archive, data
    path = t.safe(explicit)
    t.need(path.is_file() and 32 * 1024**2 < path.stat().st_size <= 512 * 1024**2, 'Choose a compatible x64 NR model DLL larger than 32 MiB.')
    raw = path.read_bytes(); t.executable_check(path)
    t.need(provider._pe(raw), 'The NR model must be an x64 Windows DLL.')
    digest = t.sha(raw)
    output = t.safe(Path(cache) / 'vulkan-models' / data['archive']['sha256'] / digest)
    output.mkdir(parents=True, exist_ok=True)
    copy_manifest = copy.deepcopy(data)
    copy_manifest['files']['NativeMods/nvngx_dlssnr.dll'] = {'size': len(raw), 'sha256': digest}
    destination = output / 'local-model.zip'
    if not destination.is_file():
        temporary = output / 'local-model.zip.part'
        with zipfile.ZipFile(archive) as original, zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as changed:
            for item in original.infolist():
                payload = raw if item.filename == 'NativeMods/nvngx_dlssnr.dll' else original.read(item)
                changed.writestr(item.filename, payload)
        temporary.replace(destination)
    copy_manifest['archive'] = {'name': destination.name, 'size': destination.stat().st_size, 'sha256': t.digest(destination)}
    # The adapter resolves the matching export notice beside the selected receipt.
    notice = output / 'loader/LICENSE.exports.txt'; notice.parent.mkdir(exist_ok=True)
    t.atomic_file(notice, (folder / 'loader/LICENSE.exports.txt').read_bytes(), 0o600)
    selected = output / 'candidate.json'; t.atomic_file(selected, (json.dumps(copy_manifest, indent=2)+'\n').encode(), 0o600)
    return folder, selected, destination, copy_manifest


def bundled_model(cache):
    folder, manifest, archive, data = bundled()
    name = 'NativeMods/nvngx_dlssnr.dll'
    expected = data['files'][name]
    path = t.safe(Path(cache) / 'bundled-nr' / expected['sha256'] / 'nvngx_dlssnr.dll')
    if not path.is_file():
        with zipfile.ZipFile(archive) as source:
            raw = source.read(name)
        t.need(len(raw) == expected['size'] and t.sha(raw) == expected['sha256'], 'Bundled NR model changed.')
        t.atomic_file(path, raw, 0o600)
    t.need(path.stat().st_size == expected['size'] and t.digest(path) == expected['sha256'], 'Cached NR model changed.')
    return path


def prefix_for(row):
    if os.name == 'nt':
        return None
    import proton_prefix
    prefix = proton_prefix.find_prefix(row['game'], row.get('appid'))
    t.need(prefix is not None, 'Launch this game with Proton once, quit, then review again.')
    t.need(not proton_prefix.prefix_in_use(prefix), 'Close this game and its Proton prefix, then review again.')
    return prefix


def prepare(config, rows, mode, operation, settings, e):
    t.need(operation in ('install', 'repair', 'uninstall'), 'Use the Vulkan in-game overlay for presets; install, repair and restore are reviewed here.')
    if operation != 'uninstall':
        t.need(mode in ('nr-mfg', 'mfg-only'), 'This Vulkan package includes frame generation. Choose NR + MFG or MFG Only.')
    folder, manifest, archive, data = local_model(settings.get('nr_runtime') if operation != 'uninstall' else None, e, e.STATE_ROOT)
    ready, blocked, plans, seen = [], [], [], set()
    for index, row in enumerate(rows):
        try:
            key, target = profile_for(row)
            t.need(key is not None, 'The Vulkan package supports only its confirmed games.')
            t.need(target not in seen, 'Duplicate Vulkan game selection.'); seen.add(target)
            t.need(not row.get('anti_cheat'), 'Anti-cheat detected; this game is excluded.')
            t.need(not e._running_processes_under_root(Path(row['game'])), 'Close this game, then review again.')
            prefix = prefix_for(row)
            with provider.profile(key, manifest):
                plan = (provider.plan_restore(target, state_root(config)) if operation == 'uninstall'
                        else provider.plan_install(target, archive, folder / ('loader-'+key) / 'bink2w64.dll', state_root(config), experimental=True,
                                                   nr_on_launch=mode != 'mfg-only' and bool(settings.get('nr_on_launch', False))))
            values = overlay_settings.effective(settings, row['game'])
            plans.append({'row': dict(row), 'profile': key, 'manifest': str(manifest), 'plan': plan,
                          'prefix': str(prefix) if prefix else None,
                          'prefix_registry': t.digest(Path(prefix)/'user.reg') if prefix else None,
                          'settings': values})
            model = data['files']['NativeMods/nvngx_dlssnr.dll']
            detail = ('Restore recorded originals.' if operation == 'uninstall' else
                      f"Vulkan · Universal Experimental\nNR model: {'Local override' if settings.get('nr_runtime') else 'Bundled'} · SHA-256 {model['sha256']}\n"
                      f"Confirmed profile: {PROFILES[key][1]}. Frame generation uses native NVIDIA MFG where the GPU supports it.\n")
            ready.append({'name': row['name'], 'game': row['game'], 'summary': 'Restore Vulkan original files' if operation == 'uninstall' else TITLE,
                          'detail': detail + '\n' + overlay_settings.describe(values)})
            ui.progress('Game checked', phase='review-check', game=row['name'], checked=index+1, total=len(rows))
        except (t.Refusal, e.Stop, OSError, ValueError, KeyError) as error:
            blocked.append({'name': row['name'], 'game': row.get('game'), 'reason': str(error)})
    return {'kind': ID, 'operation': operation, 'title': TITLE, 'engine': e, 'plans': plans, 'rows': ready, 'blocked': blocked}


def execute(review):
    e = review['engine']
    t.need(review['plans'], 'No Vulkan games were reviewed.')
    # Whole-selection preflight before touching any game.
    for item in review['plans']:
        t.need(not e._running_processes_under_root(Path(item['row']['game'])), 'A reviewed game started. Close it and review again.')
        with provider.profile(item['profile'], item['manifest']): provider._check(item['plan'])
        if item['prefix']:
            import proton_prefix
            prefix=Path(item['prefix'])
            t.need(not proton_prefix.prefix_in_use(prefix), 'A reviewed Proton prefix is running. Close it and review again.')
            t.need(t.digest(prefix/'user.reg')==item['prefix_registry'], 'Proton settings changed after review. Review again.')
    completed = []
    with e.mutation_lock():
        for item in review['plans']:
            ui.progress('Updating Vulkan package', game=item['row']['name'], current=len(completed)+1, total=len(review['plans']))
            with provider.profile(item['profile'], item['manifest']), provider.process_guard(lambda: e._running_processes_under_root(Path(item['row']['game']))):
                provider.execute(item['plan'])
            if item['prefix']:
                import proton_prefix
                state = Path(item['plan']['state']) / 'proton-prefix'
                if review['operation'] == 'uninstall': proton_prefix.restore(state)
                else: proton_prefix.apply(Path(item['prefix']), ['bink2w64'], state)
            completed.append(item['row']['name'])
    return f"Updated {len(completed)} Vulkan game(s). Original backups are retained. Restart the game to use these settings."
