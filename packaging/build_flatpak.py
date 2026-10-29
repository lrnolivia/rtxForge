#!/usr/bin/env python3
"""Build the rtxForge Flatpak bundle (dist/rtxForge-<version>-x86_64.flatpak).

Needs flatpak-builder and the org.gnome.Sdk//51 and org.gnome.Platform//51
runtimes from Flathub. Stages the AppImage's payload (build_appimage.stage_payload),
builds the app into a local repository and exports a single-file bundle.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import importlib.util
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APP_ID = 'io.github.lrnolivia.RTXForge'
FLATPAK = ROOT / 'packaging/flatpak'
MANIFEST = FLATPAK / f'{APP_ID}.yml'
BRANCH = 'beta'


def _appimage_builder():
    spec = importlib.util.spec_from_file_location('build_appimage', ROOT / 'packaging/build_appimage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metainfo(text, version, date):
    """The shipped release entry names this build's version."""
    release = f'<release version="{version}" date="{date}" type="development"/>'
    updated, count = re.subn(r'<release version="[^"]*" date="[^"]*" type="development"/>', release, text)
    if count != 1:
        raise RuntimeError('metainfo must have exactly one release entry')
    return updated


def stage(build):
    """dist/flatpak-build/source: what the manifest's one module installs."""
    source = build / 'source'
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True)
    version = _appimage_builder().stage_payload(ROOT, source / 'payload')
    shutil.copyfile(FLATPAK / 'rtxforge', source / 'rtxforge')
    shutil.copyfile(FLATPAK / f'{APP_ID}.desktop', source / f'{APP_ID}.desktop')
    today = datetime.date.today().isoformat()
    (source / f'{APP_ID}.metainfo.xml').write_text(
        metainfo((FLATPAK / f'{APP_ID}.metainfo.xml').read_text(encoding='utf-8'), version, today), encoding='utf-8')
    # Exported icons must be named after the app id (the -light variant is too).
    for icon in (ROOT / 'gui/icons/hicolor').glob('*/apps/*'):
        target = source / 'icons/hicolor' / icon.relative_to(ROOT / 'gui/icons/hicolor')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(icon, target)
    return version


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-only', action='store_true', help='Stage the sources without running flatpak-builder')
    args = parser.parse_args(argv)
    dist = ROOT / 'dist'
    build = dist / 'flatpak-build'
    version = stage(build)
    if args.stage_only:
        print(build / 'source')
        return 0
    repo, app = build / 'repo', build / 'app'
    subprocess.run(['flatpak-builder', '--force-clean', '--disable-rofiles-fuse', f'--default-branch={BRANCH}',
                    f'--state-dir={build / "state"}', f'--repo={repo}', str(app), str(MANIFEST)], check=True)
    out = dist / f'rtxForge-{version}-x86_64.flatpak'
    subprocess.run(['flatpak', 'build-bundle', '--runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo',
                    str(repo), str(out), APP_ID, BRANCH], check=True)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    out.with_name(out.name + '.sha256').write_text(f'{digest}  {out.name}\n')
    print(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
