"""Host process checks for the Flatpak build.

Inside a Flatpak, /proc lists only the sandbox's own processes, so a scan for a
running game, Steam or anti-cheat would find nothing and quietly pass. The GTK
window stays sandboxed; every check that reads processes runs the same code on
the host instead, through ``flatpak-spawn --host`` with the host's python3 and
this app's own installed payload (host_probe.py). When the host cannot be
reached the check refuses; it never falls back to the sandbox's /proc.

Outside a Flatpak (AppImage, checkout, the host-side helper) nothing here runs.
"""
from pathlib import Path
import configparser
import json
import os
import shutil
import subprocess

import transactions as t

APP_ID = 'io.github.lrnolivia.RTXForge'
INFO = Path('/.flatpak-info')
HOST_PYTHON = '/usr/bin/python3'
TIMEOUT = 60
UNAVAILABLE = ('rtxForge cannot see the games and apps running on this computer from the Flatpak, '
               'so it will not change anything. ')
FIX = ('Allow host access with: flatpak override --user --talk-name=org.freedesktop.Flatpak ' + APP_ID +
       ', then open rtxForge again. Python 3 must be installed on the system (SteamOS, Bazzite and CachyOS include it).')


class HostUnavailable(t.Refusal):
    """A process check could not run on the host; the operation must stop."""


def sandboxed(info=None):
    return (info or INFO).is_file()


def instance(info=None):
    """The [Instance] section of /.flatpak-info."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string((info or INFO).read_text(encoding='utf-8'))
    except (OSError, configparser.Error):
        return {}
    return dict(parser['Instance']) if parser.has_section('Instance') else {}


def host_files(info=None):
    """This exact deployment's files directory as the host sees it (/app inside the sandbox)."""
    path = instance(info).get('app-path', '')
    if not path or not Path(path).is_absolute():
        raise HostUnavailable(UNAVAILABLE + 'The Flatpak did not report where it is installed.')
    return Path(path)


def stable_files(files):
    """The update-proof path: <installation>/app/<id>/current/active/files.

    app-path names one deployed commit (<arch>/<branch>/<commit>/files), which
    Flatpak deletes after an update. A login service must survive updates.
    """
    files = Path(files)
    parts = files.parts
    try:
        index = len(parts) - 1 - parts[::-1].index(APP_ID)
    except ValueError:
        return files
    return Path(*parts[:index + 1]) / 'current' / 'active' / 'files'


def spawn_argv(argv):
    # The sandbox's working directory (often under /app) does not exist on the host.
    return ['flatpak-spawn', '--host', '--watch-bus', '--directory=/', *argv]


def _run(argv, **kwargs):
    return subprocess.run(argv, **kwargs)


def run_host(argv, timeout=TIMEOUT, run=None):
    """Run argv on the host. Raises HostUnavailable when host spawning is not possible."""
    if not shutil.which('flatpak-spawn'):
        raise HostUnavailable(UNAVAILABLE + FIX)
    try:
        return (run or _run)(spawn_argv(argv), capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise HostUnavailable(UNAVAILABLE + FIX) from error


def probe(command, *args, info=None, run=None):
    """Run one host_probe.py query on the host and return its result."""
    script = host_files(info) / 'share/rtxforge/scripts/host_probe.py'
    result = run_host([HOST_PYTHON, '-I', '-B', str(script), command, *map(str, args)], run=run)
    answer = None
    for line in reversed((result.stdout or '').splitlines()):
        try:
            answer = json.loads(line)
            break
        except ValueError:
            continue
    if result.returncode != 0 or not isinstance(answer, dict) or answer.get('ok') is not True or 'result' not in answer:
        detail = (answer or {}).get('error') if isinstance(answer, dict) else None
        detail = detail or (result.stderr or '').strip().splitlines()[-1:] or ['no answer']
        raise HostUnavailable(UNAVAILABLE + FIX + f' ({detail if isinstance(detail, str) else detail[0]})')
    return answer['result']


# Sandbox replacements for the engine's process checks (engine_bridge.module).
def running_processes_under_root(root):
    return list(probe('processes-under-root', Path(root).resolve()))


def steam_process_names():
    return list(probe('steam-processes'))


def nvidia_smi(args, timeout=10, run=None):
    """nvidia-smi from the host driver; the GNOME runtime has none."""
    result = run_host(['nvidia-smi', *args], timeout=timeout, run=run)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, 'nvidia-smi', result.stdout, result.stderr)
    return result.stdout


def adopt(engine):
    """Route an engine module's process checks to the host when sandboxed."""
    if not sandboxed():
        return engine
    engine._running_processes_under_root = running_processes_under_root
    engine._steam_process_names = steam_process_names

    def gpu_name():
        try:
            out = nvidia_smi(['--query-gpu=name', '--format=csv,noheader'], timeout=5)
            return out.strip().splitlines()[0].strip() or None
        except Exception:
            return None
    engine.nvidia_gpu_name = gpu_name

    def launch_steam_verify(appid):
        # Steam is not in the sandbox; the URI opens on the host through the portal.
        subprocess.Popen(['xdg-open', f'steam://validate/{int(str(appid))}'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    engine.launch_steam_verify = launch_steam_verify
    return engine


# The in-game panel helper runs on the host as a systemd user service.
def helper_unit(files):
    """A user unit that runs the helper with the host's Python from this app's installed files."""
    import linux_overlay_helper as helper
    payload = stable_files(files) / 'share/rtxforge'
    script = payload / 'scripts/desktop_frontend.py'
    return ('[Unit]\n'
            'Description=rtxForge in-game panel helper (Flatpak)\n'
            'Documentation=https://github.com/lrnolivia/rtxForge\n'
            # Gone after the Flatpak is uninstalled: stay inactive instead of failing.
            f'ConditionPathExists={str(script).replace("%", "%%")}\n\n'
            '[Service]\n'
            'Type=simple\n'
            f'ExecStart={HOST_PYTHON} -B {helper._quote(script)} --overlay-helper\n'
            'Restart=on-failure\n'
            'RestartSec=5\n\n'
            '[Install]\n'
            'WantedBy=default.target\n')


def install_helper(unit_dir, info=None, run=None):
    """Write, enable and start the host helper. Returns the unit path.

    The app window does not run the panel host inside the sandbox, so the
    service is started now rather than at the next login.
    """
    import linux_overlay_helper as helper
    text = helper_unit(host_files(info))
    unit = Path(unit_dir) / helper.SERVICE
    unit.parent.mkdir(parents=True, exist_ok=True)
    changed = not unit.is_file() or unit.read_text() != text
    if changed:
        stage = unit.with_name('.' + helper.SERVICE + '.tmp')
        stage.write_text(text)
        os.replace(stage, unit)
    steps = [['systemctl', '--user', 'daemon-reload'], ['systemctl', '--user', 'enable', '--now', helper.SERVICE]]
    if changed:
        steps.append(['systemctl', '--user', 'try-restart', helper.SERVICE])
    for argv in steps:
        result = run_host(argv, timeout=30, run=run)
        if result.returncode != 0:
            raise HostUnavailable('The in-game panel helper could not be started on the system: ' +
                                  ((result.stderr or '').strip() or ' '.join(argv)))
    return unit
