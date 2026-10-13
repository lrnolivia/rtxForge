#!/usr/bin/env python3
"""Wrap the exact built AppImage with verified setup and installation instructions."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', '.'], cwd=ROOT, check=True)
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True)
    if untracked.strip():
        raise RuntimeError('Commit or move untracked source before building a distributable bundle')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    version = (ROOT / 'VERSION').read_text().strip()
    app = ROOT / 'dist' / f'RTXForge-{version}-Bazzite-x86_64.AppImage'
    info = json.loads((ROOT / 'dist/AppImage-build/RTXForge.AppDir/usr/share/rtxforge/BUILD_INFO.json').read_text())
    if info['commit'] != commit:
        raise RuntimeError('Rebuild the AppImage from the current commit before bundling')
    name = f'rtxForge-Bazzite-RTX4070-{commit[:8]}'
    stage = ROOT / 'dist' / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    shutil.copyfile(app, stage / app.name)
    (stage / app.name).chmod(0o755)
    shutil.copyfile(ROOT / 'packaging/install_bundle.py', stage / 'install.py')
    shutil.copyfile(ROOT / 'docs/INSTALLATION.md', stage / 'INSTALLATION.md')
    shutil.copyfile(ROOT / 'providers/lock.json', stage / 'providers-lock.json')
    with app.open('rb') as handle:
        app_hash = hashlib.file_digest(handle, 'sha256').hexdigest()
    manifest = {'schema': 1, 'commit': commit, 'version': version, 'appimage': app.name,
                'sha256': app_hash,
                'size': app.stat().st_size, 'target': 'Bazzite GNOME x86_64 / RTX 4070',
                'runtime_delivery': 'verified on-demand download', 'game_runtime_verified': False}
    (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    archive = ROOT / 'dist' / (name + '.tar.gz')
    with tarfile.open(archive, 'w:gz') as bundle:
        bundle.add(stage, arcname=name)
    with archive.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    archive.with_name(archive.name + '.sha256').write_text(digest + '  ' + archive.name + '\n')
    print(archive)


if __name__ == '__main__':
    main()
