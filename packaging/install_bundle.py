#!/usr/bin/env python3
"""Verify the adjacent rtxForge package and run setup without requiring FUSE."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'manifest.json').read_text())
    name = manifest['appimage']
    if Path(name).name != name:
        raise RuntimeError('Invalid AppImage filename in package manifest')
    app = root / name
    if app.is_symlink() or app.stat().st_size != manifest['size']:
        raise RuntimeError('AppImage size or path differs from the package manifest')
    with app.open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != manifest['sha256']:
            raise RuntimeError('AppImage checksum mismatch; download the package again')
    args = sys.argv[1:] or ['install']
    app.chmod(app.stat().st_mode | 0o100)
    env = {**os.environ, 'APPIMAGE_EXTRACT_AND_RUN': '1'}
    return subprocess.call([str(app), '--setup', *args], env=env)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f'Package verification failed: {exc}', file=sys.stderr)
        sys.exit(1)
