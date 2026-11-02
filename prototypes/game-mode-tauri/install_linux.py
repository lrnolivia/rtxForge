"""Versioned per-user Linux installation, preserving the previous launcher."""
import json
import os
from pathlib import Path
import shutil
import uuid
from package_bundle import verify, smoke, digest


def main():
    source = Path(__file__).resolve().parent
    receipt = verify(source)
    if receipt.get('dirty') or receipt.get('platform') != 'linux-x64':
        raise ValueError('Install a complete Linux build from committed source.')
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    root = data / 'rtxforge-game-mode'
    identity = receipt['version'] + '-' + receipt['source'][:8] + '-' + digest(source / 'build.json')[:8]
    target = root / 'versions' / identity
    staging = root / 'versions' / ('.staging-' + uuid.uuid4().hex)
    if not target.exists():
        shutil.copytree(source, staging, symlinks=True)
        verify(staging)
        smoke(staging)
        staging.rename(target)
    else:
        verify(target)
    executable = target / 'rtxforge-game-mode'
    launcher = Path.home() / '.local/bin/rtxforge-game-mode'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    temporary = launcher.with_name('.rtxforge-game-mode-' + uuid.uuid4().hex)
    temporary.symlink_to(executable)
    temporary.replace(launcher)
    desktop = data / 'applications/fi.loew.rtxforge.gamemode.desktop'
    desktop.parent.mkdir(parents=True, exist_ok=True)
    escaped = str(executable).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
    desktop.write_text('[Desktop Entry]\nType=Application\nName=rtxForge Game Mode\n'
                       f'Exec="{escaped}"\nTerminal=false\nCategories=Game;Utility;\n', encoding='utf-8')
    previous = root / 'installed.json'
    if previous.exists(): shutil.copy2(previous, root / 'previous.json')
    previous.write_text(json.dumps({'source': receipt['source'], 'path': str(target)}, indent=2), encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
