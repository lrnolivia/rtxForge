"""Launch a Forge Lab copy of a game with the store authentication it needs.

Feature testing runs on copies (docs/DEVELOPMENT.md), never on the player's own
install. A copy outside the store's library still has to pass the store's
check, and how depends on the executable's protection:

- Steamworks: steam_appid.txt beside the executable keeps the game from
  restarting itself through Steam into the real install.
- SteamStub (a .bind section): Steam's launch variables (SteamAppId,
  SteamGameId) as well, so the stub authenticates this copy.
- EA online activation (.ooa): the licence belongs to the EA account; the EA
  app must be running and signed in.
- Ubisoft Connect: may insist on its registered install path; reported, not
  worked around.

Steam itself must be running and signed in for Steam titles. Nothing here
touches the real install, and the copy is changed only by steam_appid.txt.

    python scripts/forge_lab.py <copy folder> <exe relative to it> <Steam app id>
"""
import os
import struct
import subprocess
import sys
from pathlib import Path

STEAM_APIS = ('steam_api64.dll', 'steam_api.dll')
UBISOFT = ('uplay_r1_loader64.dll', 'upc_r2_loader64.dll', 'uplay_r2_loader64.dll')


def sections(exe):
    """PE section names, read from the header only."""
    data = Path(exe).read_bytes()[:4096]
    if data[:2] != b'MZ':
        raise ValueError('Not a Windows executable: ' + str(exe))
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[pe:pe + 4] != b'PE\0\0':
        raise ValueError('Not a Windows executable: ' + str(exe))
    count = struct.unpack_from('<H', data, pe + 6)[0]
    optional = struct.unpack_from('<H', data, pe + 20)[0]
    start = pe + 24 + optional
    return [data[start + 40 * i:start + 40 * i + 8].rstrip(b'\0').decode('ascii', 'replace') for i in range(count)]


def protection(copy, exe):
    """steamworks, steamstub, ea, ubisoft or none: what this copy must satisfy to start."""
    found = set(sections(copy / exe))
    folder = (copy / exe).parent
    near = {path.name.casefold() for path in folder.iterdir()} if folder.is_dir() else set()
    if '.bind' in found:
        return 'steamstub'
    if '.ooa' in found:
        return 'ea'
    if any(name in near for name in UBISOFT):
        return 'ubisoft'
    if any(name in near for name in STEAM_APIS) or any(copy.rglob('steam_api64.dll')):
        return 'steamworks'
    return 'none'


def running(name):
    """Whether a process with this image name is running (Windows tasklist)."""
    try:
        out = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}', '/NH'], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return name.casefold() in out.casefold()


def plan(copy, exe, appid):
    """The launch: command, working folder, environment additions, and what must be running."""
    copy, exe = Path(copy), Path(exe)
    if not (copy / exe).is_file():
        raise ValueError('The copy has no ' + str(exe))
    if 'steamapps' in (part.casefold() for part in copy.resolve().parts):
        raise ValueError('That folder is a store install, not a Forge Lab copy.')
    kind = protection(copy, exe)
    env, needs, notes = {}, [], []
    if kind in ('steamworks', 'steamstub'):
        if not str(appid).isdigit():
            raise ValueError('A Steam app id is needed for this game.')
        needs.append('steam.exe')
        if kind == 'steamstub':
            env = {'SteamAppId': str(appid), 'SteamGameId': str(appid), 'SteamOverlayGameId': str(appid)}
    elif kind == 'ea':
        needs.append('EADesktop.exe')
        notes.append('EA titles check the licence on your EA account; keep the EA app signed in.')
    elif kind == 'ubisoft':
        notes.append('Ubisoft Connect may start the registered install instead of this copy; check which one runs.')
    return {'command': [str(copy / exe)], 'cwd': str((copy / exe).parent), 'env': env, 'protection': kind,
            'appid': str(appid) if kind in ('steamworks', 'steamstub') else None, 'needs': needs, 'notes': notes}


def launch(copy, exe, appid):
    """Start the copy. Refuses when the store it needs is not running."""
    launch_plan = plan(copy, exe, appid)
    missing = [name for name in launch_plan['needs'] if not running(name)]
    if missing:
        raise RuntimeError('Start and sign in to ' + ', '.join(m.removesuffix('.exe') for m in missing) + ' first.')
    if launch_plan['appid']:
        marker = Path(launch_plan['cwd']) / 'steam_appid.txt'
        if not marker.exists() or marker.read_text(encoding='ascii', errors='replace').strip() != launch_plan['appid']:
            marker.write_text(launch_plan['appid'] + '\n', encoding='ascii')
    env = dict(os.environ, **launch_plan['env'])
    process = subprocess.Popen(launch_plan['command'], cwd=launch_plan['cwd'], env=env)
    return dict(launch_plan, pid=process.pid)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__.split('\n\n')[-1].strip())
    result = launch(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"Started {result['command'][0]} ({result['protection']}), pid {result['pid']}")
    for note in result['notes']:
        print(note)
