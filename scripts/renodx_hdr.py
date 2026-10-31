"""Automatic, pinned RenoDX HDR packages, kept separate from NR and MFG ownership."""
from pathlib import Path
import copy
import json
import os
import re
import struct
import unicodedata
import urllib.error
import urllib.request
import uuid
import zipfile

import discovery
import cross_os
import engine_bridge
import packages
import library_media
import overlay_policy
import overlay_settings
import proton_prefix
import runtime_updates
import storage as state_storage
import transactions as t

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == 'nt'
API = 'https://api.github.com/repos/clshortfuse/renodx/releases/assets/'
HOST_URL = 'https://reshade.me/downloads/ReShade_Setup_6.8.0_Addon.exe'
HOST_ARCHIVE = ('afe4c8f13048306307983b8b3d41d5bf00a86820440b0e57dea10950e1176445', 4318424)
HOSTS = {
    'x64': ('ReShade64.dll', '0cee63f9c9f13f3ac909c5b4903f4dbb4b719a7ab3b4f13b0deaf83c814b94f7', 5592064),
    'x86': ('ReShade32.dll', 'da430e0a9c6eecefa0d1b27d05e16c426fb5d04e808b194d914eaac4b31bc0f8', 4398080),
}
PROXIES = ('dxgi.dll', 'd3d9.dll', 'd3d10.dll', 'd3d11.dll', 'd3d12.dll', 'opengl32.dll')
NOTICE = 'Requires an HDR display and Windows HDR or a compatible HDR-enabled Proton session. Disable Auto HDR and RTX HDR to avoid double tone mapping.'


def catalog():
    data = t.read_json(ROOT / 'providers/renodx-hdr.json')
    t.need(data.get('schema') == 1 and isinstance(data.get('games'), list)
           and isinstance(data.get('assets'), dict), 'RenoDX catalog is invalid; update rtxForge.')
    return data


def _title(value):
    value = re.sub('[™®©]', '', str(value))
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower())


def architecture(path):
    with t.safe(path).open('rb') as f:
        header = f.read(64)
        t.need(len(header) == 64 and header[:2] == b'MZ', 'No Windows game executable found.')
        offset = struct.unpack_from('<I', header, 60)[0]
        t.need(64 <= offset <= 1024**2, 'Invalid Windows executable header.')
        f.seek(offset)
        signature = f.read(6)
    t.need(signature[:4] == b'PE\0\0' and signature[4:] in (b'd\x86', b'L\x01'), 'RenoDX requires an x64 or x86 Windows game.')
    return 'x64' if signature[4:] == b'd\x86' else 'x86'


def _steam_identity(row):
    """Resolve nested subgames from their exact containing Steam installation."""
    if not row.get('game'): return None
    root = Path(row['game']).resolve()
    for folder in (root, *root.parents):
        common = folder.parent
        if common.name.casefold() != 'common' or common.parent.name.casefold() != 'steamapps': continue
        manifests = list(common.parent.glob('appmanifest_*.acf'))
        t.need(len(manifests) <= 10000, 'Too many Steam installation records; rescan this library.')
        matches = []
        for path in manifests:
            if path.stat().st_size > 1024**2: continue
            raw = path.read_bytes(); text = raw.decode('utf-8-sig', errors='replace')
            def value(key):
                found = re.search(r'"' + key + r'"\s+"([^"]*)"', text, re.I)
                return found.group(1) if found else ''
            appid, install = value('appid'), value('installdir')
            if (not appid.isdecimal() or path.name != 'appmanifest_' + appid + '.acf'
                    or not install or install in ('.', '..') or '/' in install or '\\' in install): continue
            if (common / install).resolve() == folder:
                matches.append({'appid': appid, 'manifest': str(path.resolve()), 'sha256': t.sha(raw)})
        t.need(len(matches) <= 1, 'Several Steam records own this installation; rescan before choosing HDR.')
        return matches[0] if matches else None
    return None


def match(row, arch, data=None):
    """Store ID first; exact normalized aliases only when no store ID is known."""
    data = data or catalog()
    appid = str(row.get('appid') or '')
    identity = _steam_identity(row) if not appid else None
    if identity: appid = identity['appid']
    title = _title(row.get('name', ''))
    games = [g for g in data['games'] if (str(g.get('steam_appid') or '') == appid if appid
             else title and title in {_title(g['title']), *(_title(a) for a in g.get('aliases', []))})]
    t.need(games, 'No matching RenoDX HDR package is available in this catalog yet.')
    candidates = []
    for game in games:
        for mod in game['mods']:
            if mod.get('category') != 'game' or mod.get('compatibility') in ('unsupported', 'in-progress'):
                continue
            if mod.get('compatibility') != 'working' and mod.get('status') != 'stable':
                continue
            if str(mod.get('variant') or '').casefold() in ('sdr', 'alternate'):
                continue
            # These packages have extra setup, a replacement or unresolved prerequisites.
            notes = ' '.join(mod.get('notes', [])).lower()
            if any(word in notes for word in ('requires ', 'superseded', 'unmaintained', 'bypass', 'broken')):
                continue
            deploy = mod.get('deploy') or {}
            executable = Path(str(row.get('exe', '')).replace('\\', '/')).name.casefold()
            names = deploy.get('game_exe') or deploy.get('process_name')
            if names:
                names = names if isinstance(names, list) else [names]
                if executable not in {str(n).casefold() for n in names}: continue
            for artifact in mod.get('artifacts', []):
                if artifact.get('arch') != arch: continue
                name = artifact['name']
                pin = data['assets'].get(name)
                if not pin: continue
                t.need(re.fullmatch(r'renodx-[a-zA-Z0-9_-]+\.addon(?:32|64)', name)
                       and type(pin.get('id')) is int and pin['id'] > 0
                       and type(pin.get('size')) is int and 0 < pin['size'] <= 128*1024**2
                       and re.fullmatch('[a-f0-9]{64}', pin.get('sha256', '')), 'Invalid pinned RenoDX asset.')
                candidates.append({'name': name, 'pin': pin, 'mod': mod, 'title': game['title'],
                                   'source_commit': data['source_commit'], 'steam_identity': identity,
                                   'appid': appid})
    unique = {item['name']: item for item in candidates}
    t.need(unique, 'This game has no automatic HDR download for its architecture and supported configuration yet.')
    t.need(len(unique) == 1, 'Several RenoDX HDR variants match this game; automatic installation needs a specific profile.')
    return next(iter(unique.values()))


def _location(row):
    root = t.safe(row['game'])
    exe = t.safe(root / t.relative(row['exe']))
    t.need(exe.is_file(), 'The selected game executable is unavailable.')
    receipt = root / '.rtxforge' / ('hdr-' + t.sha(row['exe'].encode())[:16] + '.json')
    return root, exe, t.safe(receipt)


def _eligible(config, row):
    root, exe, receipt = _location(row)
    found = discovery.inspect_game(discovery.Game('', row['name'], str(root), row.get('source', 'Folder')))
    t.need(not found.anti_cheat and not row.get('anti_cheat'), 'RenoDX HDR is unavailable for games with detected anti-cheat.')
    e = engine_bridge.module(config)
    t.need(not e._running_processes_under_root(root), 'Close this game before changing HDR.')
    return root, exe, receipt, e


def _managed(e, directory):
    baseline = e.load_baseline(directory, readonly=True)
    if baseline and baseline.get('status') == 'active': return baseline
    # Borrow a verified shared loader without taking ownership of its files or
    # requiring the other OS's private state to exist on this OS.
    shared = cross_os.read(directory)
    if shared and cross_os.intact(directory, shared):
        return {'status': 'active', 'current': {'provider_id': shared['provider']['id'],
                'proxy': shared['proxy'], 'installed_hashes': shared['files']}}
    return None


def _owned(e, root, path):
    if runtime_updates._owned(e, root, path): return True
    for directory in (path.parent, *path.parent.parents):
        if not directory.is_relative_to(root): break
        shared = cross_os.read(directory)
        if shared and path.relative_to(directory).as_posix().casefold() in {n.casefold() for n in shared['files']}:
            return True
    return False


def _route(e, exe, arch, selected=None):
    directory = exe.parent
    imports = e.pe_imported_dlls(exe)
    t.need(not ((selected or {}).get('mod', {}).get('deploy', {}).get('api') == 'vulkan'
               or ('vulkan-1.dll' in imports and not imports.intersection({'d3d9.dll', 'd3d10.dll', 'd3d11.dll', 'd3d12.dll'}))),
           'This game needs the RenoDX Vulkan layer route, which is not available yet.')
    known_host = HOSTS[arch][1]
    hosts = []
    for name in (*PROXIES, HOSTS[arch][0]):
        path = t.safe(directory / name)
        if path.is_file() and t.digest(path) == known_host: hosts.append(name)
    baseline = _managed(e, directory)
    managed = baseline and baseline.get('status') == 'active'
    if managed:
        current = baseline.get('current') or {}
        family = current.get('provider_id') or (current.get('archive') or {}).get('family')
        proxy = current.get('proxy')
        hashes = current.get('installed_hashes') or {}
        if family in ('skynizz', 'y4my', 'dlss-unlocked') and proxy:
            path = t.safe(directory / t.relative(proxy))
            t.need(path.is_file() and t.digest(path) == hashes.get(proxy), 'Repair the managed OptiScaler loader before adding HDR.')
            t.need(arch == 'x64', 'This OptiScaler HDR route requires an x64 game.')
            # An already hooked ReShade must not also be loaded by OptiScaler.
            proxied = [n for n in hosts if n in PROXIES]
            if proxied:
                t.need(len(proxied) == 1, 'Multiple ReShade hooks are present; review the graphics tools first.')
                return 'existing-reshade', proxied[0], None
            return 'optiscaler', 'ReShade64.dll', directory / 'OptiScaler.ini'
    proxied = [n for n in hosts if n in PROXIES]
    if proxied:
        t.need(len(proxied) == 1, 'Multiple ReShade hooks are present; review the graphics tools first.')
        return 'existing-reshade', proxied[0], None
    t.need(not (directory / 'OptiScaler.ini').exists(), 'An unrecognized OptiScaler installation is present. Recognize or repair it before adding HDR.')
    if 'd3d9.dll' in imports: proxy = 'd3d9.dll'
    elif 'opengl32.dll' in imports: proxy = 'opengl32.dll'
    elif imports.intersection({'dxgi.dll', 'd3d10.dll', 'd3d11.dll', 'd3d12.dll'}): proxy = 'dxgi.dll'
    else: raise t.Refusal('The graphics API could not be identified safely for automatic ReShade setup.')
    t.need(not (directory / proxy).exists(), 'Another graphics tool uses ' + proxy + '. Its files have been kept.')
    return 'reshade', proxy, None


def _prefix_review(config, row, route, host, *, remove=False):
    if WINDOWS or route != 'reshade': return None
    key = t.sha((str(t.safe(row['game'])) + '\n' + row['exe']).encode())
    state = t.safe(state_storage.storage(config) / 'hdr-prefixes' / key)
    if remove:
        prior = proton_prefix.load_record(state)
        if not prior: return None
        prefix = t.safe(prior['prefix'])
    else: prefix = t.safe(proton_prefix.find_prefix(row['game'], row.get('appid')))
    t.need(not proton_prefix.prefix_in_use(prefix), 'Close this game and its Proton session before changing HDR.')
    registry = t.safe(prefix / 'user.reg')
    t.need(registry.is_file() and registry.stat().st_size <= 32*1024**2, 'The Proton registry is unavailable or too large.')
    record = state / proton_prefix.RECORD_NAME
    return {'prefix': str(prefix), 'registry': str(registry), 'before': t.digest(registry), 'state': str(state),
            'record_before': t.digest(t.safe(record)) if record.exists() else None,
            'names': [host.removesuffix('.dll')]}


def status(config, row):
    try:
        root, exe, receipt = _location(row)
        if receipt.exists():
            record = _record(root, receipt, exe.parent)
            intact = all((root / n).is_file() and t.digest(t.safe(root / n)) == h for n, h in record['files'].items())
            try: selected = match(row, architecture(exe))
            except t.Refusal: selected = None
            return {'available': True, 'installed': True, 'title': record['title'],
                    'message': 'RenoDX HDR installed.' if intact else 'HDR files changed; review HDR before repairing.',
                    'update': bool(selected and record.get('addon_sha256') != selected['pin']['sha256']), 'notes': NOTICE}
        selected = match(row, architecture(exe))
        _, _, _, e = _eligible(config, row)
        route, host, _ = _route(e, exe, architecture(exe), selected)
        _prefix_review(config, row, route, host)
        return {'available': True, 'installed': False, 'title': selected['title'],
                'message': 'Downloads the matching HDR mod and required ReShade runtime automatically.', 'route': route, 'notes': NOTICE}
    except (t.Refusal, OSError, ValueError) as error:
        return {'available': False, 'installed': False, 'message': str(error), 'notes': NOTICE}


def _fetch(config, selected, arch):
    pin = selected['pin']
    cache = state_storage.storage(config, 32*1024**2) / 'hdr-cache'
    request = urllib.request.Request(API + str(pin['id']), headers={'Accept': 'application/octet-stream', 'User-Agent': 'rtxForge/1.0'})
    try:
        addon = packages.download(request, cache / pin['sha256'] / selected['name'], expected=pin['sha256'], size=pin['size'])
        request = urllib.request.Request(HOST_URL, headers={'User-Agent': 'rtxForge/1.0'})
        setup = packages.download(request, cache / HOST_ARCHIVE[0] / 'ReShade_Addon.exe', expected=HOST_ARCHIVE[0], size=HOST_ARCHIVE[1])
    except urllib.error.HTTPError as error:
        if error.code in (404, 410):
            raise t.Refusal('This HDR build is no longer published. Update rtxForge, then retry.') from error
        raise t.Refusal('Could not download the HDR package. Try again later. ' + str(error)) from error
    except (OSError, urllib.error.URLError) as error:
        raise t.Refusal('Could not download the HDR package. Check your connection and retry. ' + str(error)) from error
    t.need(architecture(addon) == arch, 'The RenoDX add-on architecture does not match this game.')
    name, digest, size = HOSTS[arch]
    with zipfile.ZipFile(setup) as archive:
        entries = [m for m in archive.infolist() if m.filename == name]
        t.need(len(entries) == 1 and entries[0].file_size == size, 'Unexpected ReShade runtime in the verified archive.')
        data = archive.read(entries[0])
    t.need(t.sha(data) == digest, 'ReShade runtime failed verification.')
    return {selected['name']: addon.read_bytes(), name: data}


def _record(root, receipt, directory):
    t.need(receipt.stat().st_size < 1024**2, 'HDR recovery record is too large.')
    record = t.read_json(receipt)
    t.need(record.get('schema') == 1 and isinstance(record.get('files'), dict)
           and record.get('route') in ('reshade', 'existing-reshade', 'optiscaler')
           and record.get('host') in (*PROXIES, 'ReShade64.dll', 'ReShade32.dll')
           and isinstance(record.get('title'), str)
           and re.fullmatch(r'renodx-[a-zA-Z0-9_-]+\.addon(?:32|64)', record.get('addon', '')),
           'Invalid HDR recovery record.')
    for name, digest in record['files'].items():
        t.relative(name)
        path = t.safe(root / name)
        allowed = (path.parent == directory and path.name in (record['addon'], record['host'])
                   or path.parent == directory / 'rtxForge-HDR-Licenses' and path.name in ('RenoDX-LICENSE.txt', 'ReShade-LICENSE.txt'))
        t.need(isinstance(digest, str) and re.fullmatch('[a-f0-9]{64}', digest) and allowed, 'Invalid HDR recovery member.')
    if record.get('plugin'):
        value = record['plugin']['value']
        t.need(t.safe(root / t.relative(record['plugin']['path'])) == directory / 'OptiScaler.ini'
               and (value is None or isinstance(value, str) and len(value) <= 4096 and '\n' not in value and '\r' not in value),
               'Invalid HDR loader recovery setting.')
    if record.get('settings'):
        setting = record['settings']
        t.need(t.safe(root / t.relative(setting['path'])) == directory / 'ReShade.ini'
               and re.fullmatch('[a-f0-9]{64}', setting.get('created_sha256', '')), 'Invalid HDR settings recovery member.')
    return record


def _plan(row, root, writes, *, action, checks=None):
    changes = []
    for path, data in writes.items():
        path = t.safe(path)
        before = t.digest(path) if path.exists() else None
        after = t.sha(data) if data is not None else None
        if before == after: continue
        changes.append({'path': path.relative_to(root).as_posix(), 'before': before, 'after': after})
        if data is not None:
            # Binary payloads are frozen outside the game before displaying review.
            changes[-1]['_data'] = data
    return {'game': str(root), 'name': row['name'], 'exe': row['exe'], 'source': row.get('source', 'Folder'),
            'appid': row.get('appid'), 'kind': 'renodx-hdr', 'action': action, 'listing': t.files(root),
            'inputs': {}, 'conflicts': [], 'checks': checks or {}, 'changes': changes}


def _freeze(config, plan):
    for change in plan['changes']:
        data = change.pop('_data', None)
        if data is None: continue
        path = t.safe(state_storage.storage(config) / 'hdr-cache' / change['after'] / 'payload')
        if not path.exists(): t.atomic_file(path, data, 0o600)
        t.need(t.digest(path) == change['after'], 'HDR cache changed before review.')
        change['source'] = str(path)
        plan['inputs'][str(path)] = change['after']
    plan['plan_sha256'] = t.sha(json.dumps(plan, sort_keys=True).encode())
    return plan


def prepare(config, row):
    root, exe, receipt, e = _eligible(config, row)
    arch = architecture(exe)
    selected = match(row, arch)
    route, host, ini = _route(e, exe, arch, selected)
    prior = _record(root, receipt, exe.parent) if receipt.exists() else None
    record = copy.deepcopy(prior) if prior else {'schema': 1, 'files': {}, 'plugin': None}
    if prior:
        t.need(prior['addon'] == selected['name'], 'A different HDR package owns this game. Remove it before switching.')
        for name, digest in prior['files'].items():
            path = t.safe(root / name)
            t.need(path.is_file() and t.digest(path) == digest, 'HDR files changed: ' + name + '. Your files have been kept.')
        # Keep the recorded host route when its own installed proxy was detected.
        if prior['route'] == 'reshade' and host == prior['host']: route = 'reshade'
        t.need(route == prior['route'] and host == prior['host'], 'The HDR loader route changed. Remove HDR before switching routes.')
    prefix = _prefix_review(config, dict(row, appid=selected['appid'] or row.get('appid')), route, host)
    payload = _fetch(config, selected, arch)
    writes, checks = {}, {str(exe): t.digest(exe)}
    if prior: checks.update({str(root / name): digest for name, digest in prior['files'].items()})
    if route == 'optiscaler':
        baseline = _managed(e, exe.parent)
        proxy = exe.parent / t.relative(baseline['current']['proxy'])
        checks[str(proxy)] = t.digest(proxy)
    for name, data in {selected['name']: payload[selected['name']], host: payload[HOSTS[arch][0]]}.items():
        path = t.safe(exe.parent / name)
        rel = path.relative_to(root).as_posix()
        if path.exists() and rel not in record['files']:
            t.need(name != selected['name'], 'An existing HDR add-on is already installed; its files were kept. Restore its owning tool before automatic setup.')
            t.need(t.digest(path) == t.sha(data), 'Another tool owns ' + name + '; its file was kept.')
            checks[str(path)] = t.digest(path)
            continue
        writes[path] = data
        record['files'][rel] = t.sha(data)
    if ini:
        t.need(ini.is_file() and ini.stat().st_size <= 2*1024**2, 'OptiScaler settings need repair.')
        original = t.safe(ini).read_bytes()
        text = original.decode('utf-8-sig'); values = t.ini(text)
        plugin = values.get('Plugins', 'LoadReShade', fallback=None)
        if not prior:
            record['plugin'] = {'path': ini.relative_to(root).as_posix(), 'value': plugin}
        text = t.setvalue(text, 'Plugins', 'LoadReShade', 'true')
        writes[ini] = text.encode('utf-8')
    settings_path = t.safe(exe.parent / 'ReShade.ini')
    if not settings_path.exists():
        settings = overlay_settings.effective(library_media.load_settings(config), str(root))
        data = overlay_policy.reshade('', settings).encode('utf-8')
        writes[settings_path] = data
        record['settings'] = {'path': settings_path.relative_to(root).as_posix(), 'created_sha256': t.sha(data)}
    for name in ('RenoDX-LICENSE.txt', 'ReShade-LICENSE.txt'):
        data = (ROOT / 'providers/renodx-hdr' / name).read_bytes()
        path = exe.parent / 'rtxForge-HDR-Licenses' / name
        rel = path.relative_to(root).as_posix()
        if not path.exists() or rel in record['files']:
            writes[path] = data; record['files'][rel] = t.sha(data)
        else: t.need(t.digest(t.safe(path)) == t.sha(data), 'HDR license file changed.')
    record.update(addon=selected['name'], addon_sha256=selected['pin']['sha256'], route=route, host=host,
                  title=selected['title'], source_commit=selected['source_commit'])
    writes[receipt] = (json.dumps(record, indent=2) + '\n').encode()
    plan = _plan(row, root, writes, action='install', checks=checks)
    plan.update(route=route, prefix=prefix, steam_identity=selected['steam_identity'],
                notes=[*selected['mod'].get('notes', []), NOTICE])
    return _freeze(config, plan)


def prepare_remove(config, row):
    root, exe, receipt, e = _eligible(config, row)
    t.need(receipt.is_file(), 'No managed RenoDX HDR installation was found.')
    record = _record(root, receipt, exe.parent)
    writes = {receipt: None}
    checks = {str(receipt): t.digest(receipt), str(exe): t.digest(exe)}
    for name, digest in record['files'].items():
        path = t.safe(root / name)
        t.need(path.is_file() and t.digest(path) == digest, 'HDR file changed; it has been kept: ' + name)
        t.need(not _owned(e, root, path), 'Another feature now uses this HDR runtime. Restore that feature before removing HDR.')
        writes[path] = None
    if record.get('plugin'):
        plugin = record['plugin']; ini = t.safe(root / t.relative(plugin['path']))
        if ini.exists():
            text = ini.read_text(encoding='utf-8-sig')
            if t.ini(text).get('Plugins', 'LoadReShade', fallback='').strip().lower() == 'true':
                # Restore our one key, preserving all subsequent NR/MFG tuning.
                if plugin['value'] is None:
                    block = t.section(text, 'Plugins')
                    replacement = re.sub(r'(?im)^[ \t]*LoadReShade[ \t]*=[^\r\n]*(?:\r?\n|$)', '', block)
                    text = text.replace(block, replacement, 1)
                else: text = t.setvalue(text, 'Plugins', 'LoadReShade', plugin['value'])
                writes[ini] = text.encode('utf-8')
    if record.get('settings'):
        setting = record['settings']; path = t.safe(root / t.relative(setting['path']))
        # ReShade writes tuning to this file while playing. Keep those edits.
        if path.is_file() and t.digest(path) == setting['created_sha256'] and not _owned(e, root, path):
            writes[path] = None
    plan = _plan(row, root, writes, action='remove', checks=checks)
    plan['prefix'] = _prefix_review(config, row, record['route'], record['host'], remove=True)
    return _freeze(config, plan)


def apply(config, plan):
    root, exe, receipt, e = _eligible(config, plan)
    t.need(plan.get('kind') == 'renodx-hdr' and plan.get('action') in ('install', 'remove'), 'Invalid HDR operation.')
    base = state_storage.storage(config) / 'hdr-transactions'; base.mkdir(parents=True, exist_ok=True)
    state = base / uuid.uuid4().hex
    with e.mutation_lock():
        _eligible(config, plan)
        t.check_plan(plan)
        if plan.get('steam_identity'):
            t.need(_steam_identity(plan) == plan['steam_identity'], 'Steam installation identity changed since review; review HDR again.')
        for path, digest in plan['checks'].items():
            t.need(t.safe(path).is_relative_to(root) and Path(path).is_file() and t.digest(path) == digest, 'HDR prerequisites changed since review; review again.')
        prefix = plan.get('prefix')
        session = checkpoint = None
        if prefix:
            t.need(not proton_prefix.prefix_in_use(Path(prefix['prefix'])), 'The Proton session started after review. Close it and review HDR again.')
            registry = t.safe(prefix['registry']); record = t.safe(Path(prefix['state']) / proton_prefix.RECORD_NAME)
            t.need(t.digest(registry) == prefix['before'] and (t.digest(record) if record.exists() else None) == prefix['record_before'],
                   'Proton settings changed after review; review HDR again.')
            from operation_session import Session
            session = Session(e.STATE_ROOT / 'desktop-operations')
            checkpoint = session.capture([registry, record], label='RenoDX HDR Proton override')
        try:
            result = t.apply_transaction(plan, state)
            if prefix:
                if plan['action'] == 'remove': proton_prefix.restore(Path(prefix['state']))
                else: proton_prefix.apply(Path(prefix['prefix']), prefix['names'], Path(prefix['state']))
                session.seal(checkpoint); session.status = 'complete'; session.save()
        except BaseException:
            if session:
                # Seal the actual partial output before restoring the captured inputs.
                session.seal(checkpoint); session.checkpoints[-1]['sealed'] = False; session.save()
                session.undo(checkpoint); session.seal(checkpoint); session.status = 'failed'; session.save()
            if (state / 'transaction.json').exists():
                doc = t.read_json(state / 'transaction.json')
                if doc['status'] in ('complete', 'applying', 'interrupted'): t.rollback_transaction(state, True)
            raise
        finally:
            if session:
                import operation_session
                operation_session.LIVE.discard(str(session.root))
    return {'status': result['status'], 'recovery': str(state), 'message': 'RenoDX HDR removed.' if plan['action'] == 'remove' else 'RenoDX HDR installed. Enable HDR in your display settings before starting the game.'}
