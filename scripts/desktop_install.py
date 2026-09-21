"""Persistent AppImage installation and atomic replacement."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

APP_ID = 'io.github.lrnolivia.RTXForge'
APP_NAME = 'RTXForge.AppImage'


def data_root():
    data = Path(
        os.environ.get(
            'XDG_DATA_HOME',
            str(Path.home() / '.local/share'),
        )
    )
    if not data.is_absolute():
        raise ValueError('XDG_DATA_HOME must be absolute')
    return data


def installed_path():
    return data_root() / 'rtxforge/application' / APP_NAME


def _fsync_file(path):
    with Path(path).open('rb') as handle:
        os.fsync(handle.fileno())


def _fsync_dir(path):
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def register(target=None):
    data = data_root()
    target = Path(target or installed_path()).resolve()

    assets = Path(__file__).resolve().parents[1] / 'gui/icons/hicolor'

    # The launcher needs a square canvas, not the wide dashboard artwork.
    # The scalable asset preserves the embedded artwork's aspect ratio.
    icon = data / f'icons/hicolor/scalable/apps/{APP_ID}.svg'
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(assets / f'scalable/apps/{APP_ID}.svg', icon)

    apps = data / 'applications'
    apps.mkdir(parents=True, exist_ok=True)

    quoted = (
        str(target)
        .replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace('`', '\\`')
        .replace('$', '\\$')
        .replace('%', '%%')
    )

    desktop = apps / f'{APP_ID}.desktop'
    desktop.write_text(
        '[Desktop Entry]\n'
        'Type=Application\n'
        'Name=rtxForge\n'
        'Comment=GeForce tools for Linux\n'
        f'Exec="{quoted}"\n'
        f'Icon={icon}\n'
        'Terminal=false\n'
        'Categories=Game;Utility;\n'
        f'StartupWMClass={APP_ID}\n'
    )

    if shutil.which('update-desktop-database'):
        subprocess.run(
            ['update-desktop-database', str(apps)],
            check=False,
            capture_output=True,
        )

    if shutil.which('gtk-update-icon-cache'):
        subprocess.run(
            [
                'gtk-update-icon-cache',
                '-f',
                '-t',
                str(data / 'icons/hicolor'),
            ],
            check=False,
            capture_output=True,
        )

    return str(target)


def install_from(source):
    source = Path(source).resolve(strict=True)

    target = installed_path()
    root = target.parent
    root.mkdir(parents=True, exist_ok=True)

    if source != target:
        fd, temporary = tempfile.mkstemp(
            prefix='.rtxforge-update-',
            dir=root,
        )
        os.close(fd)
        stage = Path(temporary)

        try:
            shutil.copyfile(source, stage)
            stage.chmod(0o755)
            _fsync_file(stage)

            if target.exists():
                previous = root / 'RTXForge.previous.AppImage'

                fd, previous_temp = tempfile.mkstemp(
                    prefix='.rtxforge-previous-',
                    dir=root,
                )
                os.close(fd)
                previous_stage = Path(previous_temp)

                try:
                    shutil.copyfile(target, previous_stage)
                    previous_stage.chmod(0o755)
                    _fsync_file(previous_stage)
                    os.replace(previous_stage, previous)
                finally:
                    previous_stage.unlink(missing_ok=True)

            os.replace(stage, target)
            _fsync_dir(root)

        finally:
            stage.unlink(missing_ok=True)

    register(target)
    return str(target)


def install():
    source = os.environ.get('APPIMAGE')
    if not source:
        raise RuntimeError('This action requires the AppImage build.')

    return install_from(source)


if __name__ == '__main__':
    print(install())
