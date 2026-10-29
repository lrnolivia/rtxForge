"""The in-game panel helper without the app window (Windows: --overlay-helper).

The Proton panel asks a host for live NR/MFG status, presets and reviewed
changes over a file-backed channel (linux_overlay_host). The app window runs
that host while it is open; this helper runs the same host headless so the
panel works with the window closed and in Game Mode. A systemd user service
starts it at login (unit_text / install_service). Only one host runs per user:
whichever starts second waits for the lock (linux_overlay_host.host_lock).
"""
from pathlib import Path
import os
import signal
import subprocess
import sys

SERVICE = 'io.github.lrnolivia.RTXForge.overlay-helper.service'


def _quote(path):
    """A path as one systemd ExecStart word."""
    text = str(path)
    for old, new in (('\\', '\\\\'), ('"', '\\"'), ('%', '%%'), ('$', '$$')):
        text = text.replace(old, new)
    return '"' + text + '"'


def unit_text(appimage):
    return ('[Unit]\n'
            'Description=rtxForge in-game panel helper\n'
            'Documentation=https://github.com/lrnolivia/rtxForge\n\n'
            '[Service]\n'
            'Type=simple\n'
            f'ExecStart={_quote(appimage)} --overlay-helper\n'
            'Restart=on-failure\n'
            'RestartSec=5\n\n'
            '[Install]\n'
            'WantedBy=default.target\n')


def install_service(appimage, unit_dir, systemctl, run=subprocess.run):
    """Write the user unit beside the launcher (<data>/systemd/user, on systemd's user search
    path) and start it now and at login. Returns the unit path, or None without systemctl."""
    unit = Path(unit_dir) / SERVICE
    text = unit_text(Path(appimage).resolve())
    unit.parent.mkdir(parents=True, exist_ok=True)
    changed = not unit.is_file() or unit.read_text() != text
    if changed:
        stage = unit.with_name('.' + SERVICE + '.tmp')
        stage.write_text(text)
        os.replace(stage, unit)
    if not systemctl:
        return None
    steps = [[systemctl, '--user', 'daemon-reload'],
             [systemctl, '--user', 'enable', '--now', SERVICE]]
    if changed:
        steps.append([systemctl, '--user', 'try-restart', SERVICE])
    for argv in steps:
        result = run(argv, check=False, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError('The in-game panel helper could not be started: ' +
                               ((result.stderr or '').strip() or ' '.join(argv)))
    return unit


def _settings(config):
    """Current app settings, reread when the app saves them."""
    import library_media
    path = library_media.settings_path(config)
    cache = {'stamp': None, 'value': {}}

    def current():
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            stamp = None
        if stamp != cache['stamp']:
            try:
                cache['value'] = library_media.load_settings(config)
                cache['stamp'] = stamp
            except (OSError, ValueError):
                pass
        return dict(cache['value'])
    return current


def main(argv=None):
    if sys.platform != 'linux':
        print('The panel helper runs on Linux; Windows has its own.', file=sys.stderr)
        return 1
    from desktop_service import DesktopService
    from linux_overlay_host import Host
    from storage import storage
    import engine_bridge
    config = DesktopService().config
    settings = _settings(config)
    if settings().get('overlay_helper', True) is not True:
        print('In-game panel helper is off in Settings.', file=sys.stderr)
        return 0
    engine = engine_bridge.module(config)
    host = Host(storage(config), settings, engine.STATE_ROOT, engine=engine)
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: host.stop.set())
    host.run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
