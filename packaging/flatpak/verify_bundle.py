#!/usr/bin/env python3
"""Check an installed rtxForge Flatpak the way a user's system runs it (CI: build-flatpak).

Run on the host inside a D-Bus session after ``flatpak install --user`` of the
bundle. Proves the sandbox's own /proc is blind to a fake game, that the app's
process checks still see it through flatpak-spawn --host, that the panel helper
refuses inside the sandbox and runs on the host from the update-proof path, and
that the GTK window opens.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time

APP_ID = 'io.github.lrnolivia.RTXForge'

SANDBOX_CHECKS = r'''
import json, os, sys
sys.path.insert(0, '/app/share/rtxforge/scripts')
import flatpak_host, proton_prefix, engine_bridge
game, prefix, idle, pid = sys.argv[1:]
engine = engine_bridge.module({})
print(json.dumps({
    'sandboxed': flatpak_host.sandboxed(),
    'sandbox_sees_game': os.path.isdir(f'/proc/{pid}'),
    'prefix_in_use': proton_prefix.prefix_in_use(prefix),
    'idle_prefix_in_use': proton_prefix.prefix_in_use(idle),
    'under_root': engine._running_processes_under_root(game),
    'host_files': str(flatpak_host.host_files()),
}))
'''


def flatpak_run(*args, **kwargs):
    return subprocess.run(['flatpak', 'run', *args], text=True, capture_output=True, timeout=180, **kwargs)


def check(condition, message, detail=''):
    if not condition:
        raise SystemExit(f'FAILED: {message}\n{detail}')
    print('ok:', message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--screenshot', type=Path)
    args = parser.parse_args()

    doctor = flatpak_run(APP_ID, '--frontend-doctor')
    check(doctor.returncode == 0, 'frontend doctor runs', doctor.stderr[-2000:])
    check(json.loads(doctor.stdout)['gtk_missing'] is None, 'the runtime provides GTK4 and libadwaita 1.7+')

    # A fake game on the host, in a folder the sandbox shares (--filesystem=host).
    with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
        root = Path(directory)
        game, prefix = root / 'game', root / 'compatdata/1/pfx'
        game.mkdir()
        prefix.mkdir(parents=True)
        child = subprocess.Popen(['sleep', '120'], cwd=game, env={**os.environ, 'WINEPREFIX': f'{prefix}/'})
        try:
            result = flatpak_run('--command=python3', APP_ID, '-B', '-c', SANDBOX_CHECKS,
                                 str(game), str(prefix), str(root / 'idle/pfx'), str(child.pid))
            check(result.returncode == 0, 'process checks run inside the sandbox', result.stderr[-2000:])
            seen = json.loads(result.stdout.splitlines()[-1])
            check(seen['sandboxed'], 'the app knows it is sandboxed')
            check(not seen['sandbox_sees_game'], "the sandbox's own /proc cannot see the game")
            check(seen['prefix_in_use'], 'a running game blocks prefix changes (checked on the host)')
            check(not seen['idle_prefix_in_use'], 'an idle prefix is free')
            check(any(item.startswith(f'{child.pid}:') for item in seen['under_root']),
                  'the engine finds the game process under its folder (checked on the host)')
        finally:
            child.kill()
            child.wait()

    refused = flatpak_run(APP_ID, '--overlay-helper')
    check(refused.returncode == 1 and 'runs on the host' in refused.stderr, 'the panel helper refuses inside the sandbox')

    files = Path(seen['host_files'])
    stable = files.parents[3] / 'current/active/files'
    helper = stable / 'share/rtxforge/scripts/desktop_frontend.py'
    check(helper.is_file(), f'the update-proof payload path exists: {helper}')
    with tempfile.TemporaryDirectory() as state:
        env = {**os.environ, 'XDG_STATE_HOME': state, 'XDG_RUNTIME_DIR': state}
        try:
            run = subprocess.run(['/usr/bin/python3', '-B', str(helper), '--overlay-helper'], env=env, cwd='/',
                                 text=True, capture_output=True, timeout=8)
            check(False, 'the host helper keeps running', run.stderr[-2000:])
        except subprocess.TimeoutExpired:
            check(True, "the panel helper runs on the host's Python from the Flatpak's files")

    if args.screenshot and shutil.which('xvfb-run'):
        window = subprocess.Popen(['xvfb-run', '-a', '-s', '-screen 0 1600x1000x24', 'sh', '-c',
                                   f'flatpak run --env=GSK_RENDERER=cairo {APP_ID} & app=$!; sleep 25; '
                                   f'import -window root {args.screenshot}; kill -0 $app; status=$?; kill $app; exit $status'],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = window.communicate(timeout=120)[0]
        check(window.returncode == 0 and args.screenshot.is_file() and args.screenshot.stat().st_size > 10000,
              'the window opens and stays open', output[-3000:])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
