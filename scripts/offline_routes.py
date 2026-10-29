"""Reviewed, per-title offline launch profiles. Anti-cheat evidence stays visible.

Profiles describe a verified vendor-supported offline route, never a general
anti-cheat bypass. Consent is bound to the actual executable and EAC settings.
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
import transactions as t

PROFILES = {
    'gears-eday-offline': {
        'version': 1, 'appid': '3010850',
        'exe': 'FairlightConcept/Binaries/Win64/GoWEDay-Steam.exe',
        'markers': ['EasyAntiCheat/Settings.json', 'start_protected_game.exe'],
        'environment': {'EOS_USE_ANTICHEATCLIENTNULL': '1', 'SteamAppId': '3010850', 'SteamGameId': '3010850'},
    },
}


def profile(row):
    for key, spec in PROFILES.items():
        if str(row.get('appid')) == spec['appid'] and str(row.get('exe', '')).replace('\\', '/').casefold() == spec['exe'].casefold():
            return key
    return None


def receipt(row, cache=None):
    key = profile(row)
    t.need(key is not None, 'No verified offline launch route is available for this title.')
    spec, root = PROFILES[key], t.safe(row['game'])
    files = [spec['exe'], *spec['markers']]
    hashes = {}
    for name in files:
        path = t.safe(root / name)
        t.need(path.is_file(), 'The verified offline route is missing: ' + name)
        signature = (str(path), path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ctime_ns)
        if cache is None:
            hashes[name] = t.digest(path)
        else:
            if signature not in cache:
                cache[signature] = t.digest(path)
            hashes[name] = cache[signature]
    return {'id': key, 'version': spec['version'], 'root': str(root), 'appid': spec['appid'], 'files': hashes}


def verify(route, cache=None):
    t.need(isinstance(route, dict) and route.get('id') in PROFILES, 'Review the offline-only exception again.')
    spec = PROFILES[route['id']]
    row = {'game': route.get('root'), 'exe': spec['exe'], 'appid': route.get('appid')}
    t.need(receipt(row, cache) == route, 'The offline route changed. Review this game again before managing its features.')
    return spec


PROTECTED_NAMES = ('easyanticheat', 'start_protected_game')


def protected_running(proc=Path('/proc')):
    if os.name != 'nt':
        if proc == Path('/proc'):
            import flatpak_host
            if flatpak_host.sandboxed():
                return bool(flatpak_host.probe('protected-running'))
        # Proton runs Windows processes as ordinary host processes; their command lines name the executable.
        for entry in proc.iterdir() if proc.is_dir() else ():
            if not entry.name.isdigit():
                continue
            try:
                args = (entry / 'cmdline').read_bytes().split(b'\0')
            except OSError:
                continue
            for arg in args:
                name = arg.decode('utf-8', 'replace').replace('\\', '/').rsplit('/', 1)[-1].casefold()
                if name and (name.startswith(PROTECTED_NAMES[1]) or PROTECTED_NAMES[0] in name):
                    return True
        return False
    import win_processes
    return any('easyanticheat' in name.casefold() or name.casefold().startswith('start_protected_game')
               for _, name, _, _ in win_processes._inventory())


def allowed(e, game):
    if not game.anti_cheat:
        return True
    try:
        baseline = e.load_baseline(game.target_dir, readonly=True) or {}
        route = baseline.get('offline_route')
        spec = verify(route)
        return (baseline.get('status') == 'active' and str(game.appid) == spec['appid']
                and t.safe(game.root) == t.safe(route['root'])
                and t.safe(game.exe) == t.safe(Path(route['root']) / spec['exe'])
                and not protected_running())
    except (t.Refusal, getattr(e, 'Stop', RuntimeError), OSError, ValueError, TypeError, KeyError):
        return False


def allowed_target(e, target, root):
    try:
        record = e.load_baseline(target, readonly=True) or {}
        if not record.get('offline_route'):
            return False
        return allowed(e, SimpleNamespace(target_dir=target, root=root, appid=record.get('appid'),
                                         exe=Path(record.get('exe') or ''), anti_cheat=True))
    except (t.Refusal, getattr(e, 'Stop', RuntimeError), OSError, ValueError, TypeError, KeyError):
        return False


def launch(e, row):
    import engine_bridge
    game = engine_bridge.game(e, row)
    t.need(game.anti_cheat and allowed(e, game), 'Adopt this game with its verified offline-only exception first.')
    t.need(not e._running_processes_under_root(game.root), 'This game is already running.')
    record = e.load_baseline(game.target_dir, readonly=True)
    for name, digest in record['current']['installed_hashes'].items():
        if not name.lower().endswith(('.ini', '.log')):
            t.need(t.digest(t.safe(game.target_dir / t.relative(name))) == digest, 'Package files changed; repair before launching offline.')
    spec = verify(record['offline_route'])
    child_env = dict(os.environ, **spec['environment'])
    child = subprocess.Popen([str(game.exe)], cwd=str(game.target_dir), env=child_env,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return {'pid': child.pid, 'offline_only': True}
