"""Bounded app routing for the reviewed BG3/RDR2 native Vulkan package."""
import contextlib
import copy
import hashlib
import json
import os
import tempfile
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
# The shared install record (.rtxforge-install.json) for the other OS: the loader proxy,
# everything under NativeMods, and the Proton override that makes the proxy load.
RECORD_NAMES = ('bink2w64.dll', 'NativeMods')
PROXY = 'bink2w64.dll'
PROTON_OVERRIDES = ('bink2w64',)
SHARED_RECOVERY = '.rtxforge/vulkan/baseline.json'


def recovery_export(target, state, baseline, marker):
    """Plan a portable copy of the verified Vulkan restore record and its objects."""
    import cross_os
    checks, writes = {}, {}
    data = copy.deepcopy(baseline)
    data['cross_os_revision'] = marker['revision']
    objects = {(item or {}).get('sha256') for item in data['originals'].values()}
    objects.add(data.get('prior_record_sha256'))
    for digest in objects - {None}:
        source = t.safe(state/'objects'/digest)
        t.need(source.is_file() and source.stat().st_size <= 512*1024**2 and t.digest(source)==digest,
               'A Vulkan original backup is missing or changed.')
        destination = t.safe(target/'.rtxforge/vulkan/objects'/digest)
        actual = t.digest(destination) if destination.exists() else None
        t.need(actual in (None, digest), 'A shared Vulkan original backup changed.')
        checks[str(source)] = digest; checks[str(destination)] = actual
        if actual is None: writes[str(destination)] = source.read_bytes()
    portable = cross_os.portable(data, state, target)
    raw = (json.dumps(portable, sort_keys=True, indent=1)+'\n').encode()
    destination = t.safe(target/SHARED_RECOVERY)
    checks[str(destination)] = t.digest(destination) if destination.exists() else None
    writes[str(destination)] = raw
    marker['shared_recovery'] = {'schema':1, 'sha256':t.sha(raw), 'readable':True}
    return data, checks, writes


def import_shared_recovery(target, key, config=None):
    """Adopt another OS's exact restore record into private storage, without game writes."""
    import cross_os
    marker = cross_os.read(target)
    if not marker or marker.get('provider', {}).get('id') != ID or not marker.get('shared_recovery'): return
    state = provider.state_path(target, state_root(config))
    with provider._lock(state.parent/'adoption-locks'/state.name):
        return _import_shared_recovery(target, key, config)


def _import_shared_recovery(target, key, config=None):
    import cross_os
    marker = cross_os.read(target)
    if not marker or marker.get('provider', {}).get('id') != ID or not marker.get('shared_recovery'):
        return
    state = provider.state_path(target, state_root(config))
    local = t.read_json(state/'baseline.json') if (state/'baseline.json').is_file() else None
    if local and local.get('cross_os_revision') == marker.get('revision'): return
    source = t.safe(target/SHARED_RECOVERY)
    t.need(source.is_file() and source.stat().st_size < 1024**2 and t.digest(source)==marker['shared_recovery'].get('sha256'),
           'The shared Vulkan recovery record changed. Nothing was replaced.')
    raw = source.read_bytes(); shared = json.loads(raw)
    t.need(shared.get('cross_os_revision') == marker.get('revision') and shared.get('status')=='active',
           'Shared Vulkan revision differs from its installation record.')
    folder, manifest, archive, spec = bundled()
    state.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cross-os-import-', dir=state.parent) as temporary:
        staging = Path(temporary).resolve()
        local_prefix_checks={}
        local_prefix=t.safe(state/'proton-prefix')
        if local_prefix.is_dir():
            files=list(local_prefix.rglob('*'))
            t.need(len(files)<=256,'Too many local Proton recovery files.')
            for item in files:
                item=t.safe(item)
                if not item.is_file():continue
                t.need(item.stat().st_size<=128*1024**2,'Local Proton recovery file exceeds its size limit.')
                payload=item.read_bytes();local_prefix_checks[str(item)]=t.sha(payload)
                t.atomic_file(staging/'proton-prefix'/item.relative_to(local_prefix),payload,0o600)
        data = cross_os.localize(shared, staging, target)
        refs = {(item or {}).get('sha256') for item in data.get('originals', {}).values()}
        refs.add(data.get('prior_record_sha256'))
        for digest in refs - {None}:
            t.need(isinstance(digest,str) and len(digest)==64 and all(c in '0123456789abcdef' for c in digest), 'Invalid shared backup identity.')
            original = t.safe(target/'.rtxforge/vulkan/objects'/digest)
            t.need(original.is_file() and original.stat().st_size <= 512*1024**2 and t.digest(original)==digest, 'Shared Vulkan backup is missing or changed.')
            t.atomic_file(staging/'objects'/digest, original.read_bytes(), 0o600)
        t.atomic_file(staging/'baseline.json', (json.dumps(data)+'\n').encode(), 0o600)
        with provider.profile(key, manifest):
            provider._record(target, staging)
            for name, expected in data['installed'].items():
                if name not in provider._mutable():
                    t.need(t.digest(t.safe(target/t.relative(name))) == expected, 'Shared Vulkan package files changed: '+name)
        t.need(source.read_bytes()==raw and cross_os.read(target)==marker, 'Shared Vulkan state changed during adoption.')
        t.need(all(t.digest(Path(path))==digest for path,digest in local_prefix_checks.items()),'Local Proton recovery changed during adoption.')
        # Keep the former OS-local record for rollback; never overwrite it.
        retired = None
        if state.exists():
            retired = t.safe(state.parent/('retired-'+state.name+'-'+cross_os.new_revision()))
            os.replace(state, retired)
        try: os.replace(staging, state)
        except BaseException:
            if retired is not None: os.replace(retired, state)
            raise


def write_record(target):
    import cross_os
    previous = cross_os.read(target)
    record = cross_os.write(target, cross_os.THIS_OS, RECORD_NAMES, {'id': ID, 'name': TITLE, 'version': ''},
                            'nr-mfg', PROXY, PROTON_OVERRIDES)
    oses = {cross_os.THIS_OS}
    if previous and previous.get('provider', {}).get('id') == ID and previous.get('proxy') == PROXY:
        oses.add(previous['os'])
        oses.update(name for name in previous.get('installed_oses', []) if name in cross_os.OPERATING_SYSTEMS)
    record['installed_oses'] = [name for name in ('windows','linux') if name in oses]
    state = provider.state_path(target, state_root())
    if (state/'baseline.json').is_file():
        baseline, checks, writes = recovery_export(target, state, t.read_json(state/'baseline.json'), record)
        for path, data in writes.items():
            t.atomic_file(Path(path), data, 0o644)
            cross_os.readable_parents(Path(path),target)
        t.atomic_file(state/'baseline.json', (json.dumps(baseline)+'\n').encode(), 0o600)
    t.atomic_file(Path(target) / cross_os.MARKER, (json.dumps(record, indent=1) + '\n').encode(), 0o600)
    return record


def windows_record(target):
    """On Linux, a Windows install of this package: its shared record, or for installs made
    before Vulkan wrote one, the package's own layout (receipt plus the loader's backup)."""
    import cross_os
    target = Path(target)
    record = cross_os.read(target)
    if record:
        return record if record['os'] == 'windows' and (record.get('provider') or {}).get('id') == ID else None
    if cross_os.THIS_OS != 'linux':
        return None
    if ((target / 'NativeMods/rtxForge-vulkan/source-receipt.json').is_file()
            and (target / 'bink2w64_rtxforge_original.dll').is_file() and (target / PROXY).is_file()):
        return {'schema': 1, 'os': 'windows', 'provider': {'id': ID, 'name': TITLE, 'version': ''},
                'feature_mode': 'nr-mfg', 'proxy': PROXY, 'proton_overrides': list(PROTON_OVERRIDES),
                'files': {}, 'legacy': True}
    return None


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
    import_shared_recovery(target, key, config)
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
            import cross_os
            shared = cross_os.read(target)
            shared = shared if shared and shared.get('provider', {}).get('id') == ID else None
            oses = set(row.get('installed_oses') or [])
            if shared:
                oses.add(shared['os'])
                oses.update(name for name in shared.get('installed_oses', []) if name in cross_os.OPERATING_SYSTEMS)
            if record:
                if cross_os.THIS_OS=='windows':oses.add('windows')
                else:
                    import proton_prefix
                    ready=proton_prefix.load_record(provider.state_path(target,state_root(config))/'proton-prefix') is not None
                    if ready:oses.add('linux')
                    elif shared and 'windows' in oses:row['vulkan_windows']=True
            if record or shared:
                row['installed_on'] = shared['os'] if shared else cross_os.THIS_OS
                row['installed_oses'] = [name for name in ('windows','linux') if name in oses]
            windows = None if record else (shared or windows_record(target))
            if windows:
                # Installed with rtxForge on Windows: Adapt to Linux sets it up for Proton.
                row.update(installed=True, installed_on=windows['os'], runtime_provider=ID, install_provider=ID,
                           feature_mode='nr-mfg', profile='NR + MFG', graphics_apis=['Vulkan'], blocked='',
                           mfg_route='Native Vulkan DLSS-G · Universal Experimental', dynamic_mfg_available=False)
                row['installed_oses'] = [name for name in ('windows','linux') if name in oses | {windows['os']}]
                row['exe'] = (target / PROFILES[key][0]).relative_to(Path(row['game'])).as_posix()
                row['vulkan_windows'] = windows['os'] == 'windows' and cross_os.THIS_OS == 'linux'
                continue
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
            import_shared_recovery(target, key, config)
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
            # Shared record so the other OS recognises this install (removed with the originals).
            import cross_os
            if review['operation'] == 'uninstall':
                target = Path(item['plan']['target']); marker = cross_os.read(target)
                if marker and marker.get('provider', {}).get('id') == ID:
                    cross_os.remove(target, marker['os'])
            else:write_record(Path(item['plan']['target']))
            if item['prefix']:
                import proton_prefix
                state = Path(item['plan']['state']) / 'proton-prefix'
                if review['operation'] == 'uninstall': proton_prefix.restore(state)
                else: proton_prefix.apply(Path(item['prefix']), ['bink2w64'], state)
            completed.append(item['row']['name'])
    return f"Updated {len(completed)} Vulkan game(s). Original backups are retained. Restart the game to use these settings."
