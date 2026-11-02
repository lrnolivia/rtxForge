"""Native Game Mode handoff shared by Linux Desktop and package validation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def native_instances(proc=Path('/proc'), pids=None):
    """Identify this user's native UI processes, including extracted AppImages."""
    if not hasattr(os, 'getuid'):
        return {}
    found = {}
    entries = (proc / str(pid) for pid in pids) if pids is not None else proc.iterdir()
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            executable = (entry / 'exe').readlink()
            if executable.name != 'rtxforge-game-mode':
                continue
            # Linux start ticks distinguish a living instance from a reused PID.
            fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            found[int(entry.name)] = fields[19]
        except (OSError, IndexError):
            continue
    return found


class NativeSession:
    def __init__(self, child):
        self.child = child

    def wait(self):
        code = self.child.wait()
        if code:
            return code
        # The single-instance launcher exits immediately after focusing an
        # existing window. Keep Desktop hidden until that actual UI exits.
        instances = native_instances()
        while instances:
            time.sleep(.5)
            current = native_instances(pids=instances)
            instances = {pid: start for pid, start in instances.items()
                         if current.get(pid) == start}
        return code


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_image(folder, expected_source=None):
    folder = Path(folder)
    record = json.loads((folder / 'game-mode.json').read_text())
    image = folder / 'rtxforge-game-mode.AppImage'
    if (record.get('schema') != 1 or record.get('desktopIntegration') != 1
            or (expected_source and record.get('source') != expected_source)
            or not image.is_file() or image.is_symlink()
            or image.stat().st_size != record.get('size')
            or digest(image) != record.get('sha256')):
        raise ValueError('The bundled Game Mode package is incomplete or has changed. Reinstall rtxForge.')
    return image


def resolve(root, data_home=None):
    bundled = Path(root) / 'game-mode'
    if bundled.exists():
        return validate_image(bundled), True
    home = Path(data_home or os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'rtxforge-game-mode'
    installed = json.loads((home / 'installed.json').read_text())
    folder = Path(installed['path']).resolve()
    if not folder.is_relative_to((home / 'versions').resolve()):
        raise ValueError('The Game Mode installation record is invalid.')
    receipt = json.loads((folder / 'build.json').read_text())
    if receipt.get('schema') != 2 or receipt.get('dirty') or receipt.get('desktopIntegration') != 1:
        raise ValueError('Install the current complete Game Mode package before switching interfaces.')
    for name in ('rtxforge-game-mode', 'python/bin/python3', 'bridge/engine_host.py',
                 'engine/scripts/desktop_service.py', 'screening/rtxforge-screenshot-screen'):
        if not (folder / name).is_file():
            raise ValueError('The Game Mode installation is incomplete: ' + name)
    executable = folder / 'rtxforge-game-mode'
    if digest(executable) != receipt.get('native', {}).get('sha256'):
        raise ValueError('The Game Mode executable has changed. Reinstall rtxForge.')
    return executable, False


def desktop_command(root):
    if os.environ.get('APPIMAGE'):
        return [os.path.abspath(os.environ['APPIMAGE']), '--desktop-mode']
    if os.environ.get('FLATPAK_ID'):
        return ['/usr/bin/flatpak-spawn', '--host', 'flatpak', 'run', os.environ['FLATPAK_ID'], '--desktop-mode']
    return [sys.executable, str(Path(root) / 'scripts/desktop_frontend.py'), '--desktop-mode']


def start(root, read_only=False, appearance=False):
    executable, image = resolve(root)
    env = os.environ.copy()
    command = desktop_command(root)
    for key in ('RTXFORGE_ROOT', 'RTXFORGE_PYTHON', 'PYTHONPATH', 'APPDIR', 'APPIMAGE',
                'LD_LIBRARY_PATH', 'LD_PRELOAD', 'GDK_PIXBUF_MODULE_FILE', 'GIO_EXTRA_MODULES',
                'GTK_PATH', 'GTK_DATA_PREFIX', 'GI_TYPELIB_PATH', 'GSETTINGS_SCHEMA_DIR',
                'SteamAppId', 'SteamGameId'):
        env.pop(key, None)
    env['RTXFORGE_DESKTOP_COMMAND'] = json.dumps(command)
    if os.environ.get('APPIMAGE'):env['RTXFORGE_APP_EXE']=os.path.abspath(os.environ['APPIMAGE'])
    else:env['RTXFORGE_APP_EXE']=str(Path(root)/'rtxforge')
    if read_only:
        env['RTXFORGE_PREVIEW_READ_ONLY'] = '1'
    args = [str(executable)] + (['--appimage-extract-and-run'] if image else [])
    if appearance:args.append('--appearance')
    child = subprocess.Popen([*args, '--desktop-parent', str(os.getpid())], env=env,
                             cwd=executable.parent, stdin=subprocess.DEVNULL)
    return NativeSession(child)
