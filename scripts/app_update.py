"""Public GitHub AppImage updater for rtxForge."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request

import desktop_install

ROOT = Path(__file__).resolve().parents[1]

RELEASE_API = (
    'https://api.github.com/repos/lrnolivia/rtxForge/'
    'releases/tags/continuous'
)

MANIFEST_NAME = 'rtxforge-update.json'
USER_AGENT = 'rtxForge-AppUpdater/1'


def _request(url, timeout=30):
    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': USER_AGENT,
            'Accept': 'application/vnd.github+json',
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


def _bytes(url, timeout=30):
    with _request(url, timeout) as response:
        return response.read()


def _json(url):
    return json.loads(_bytes(url).decode('utf-8'))


def _version_key(value):
    text = str(value).strip().lstrip('v')
    if not re.fullmatch(r'\d+(?:\.\d+)*', text):
        raise ValueError(f'Invalid application version: {value}')
    return tuple(int(part) for part in text.split('.'))


def current_build():
    version_file = ROOT / 'VERSION'
    version = (
        version_file.read_text(encoding='utf-8').strip()
        if version_file.exists()
        else '0.0.0'
    )

    commit = 'unknown'
    info_file = ROOT / 'BUILD_INFO.json'

    if info_file.exists():
        try:
            commit = (
                json.loads(info_file.read_text(encoding='utf-8'))
                .get('commit')
                or 'unknown'
            )
        except Exception:
            pass

    return {
        'version': version,
        'commit': commit,
    }


def check():
    release = _json(RELEASE_API)

    assets = {
        asset['name']: asset
        for asset in release.get('assets', [])
    }

    manifest_asset = assets.get(MANIFEST_NAME)
    if not manifest_asset:
        raise RuntimeError(
            'The rtxForge update release has no update manifest.'
        )

    manifest = _json(manifest_asset['browser_download_url'])

    for key in ('version', 'commit', 'appimage', 'sha256', 'size'):
        if not manifest.get(key):
            raise RuntimeError(
                f'Update manifest is missing {key}.'
            )

    if not re.fullmatch(r'[0-9a-fA-F]{64}', manifest['sha256']):
        raise RuntimeError('Update manifest contains an invalid SHA256.')

    app_asset = assets.get(manifest['appimage'])
    if not app_asset:
        raise RuntimeError(
            'The AppImage named by the update manifest is missing.'
        )

    download_url = app_asset['browser_download_url']

    expected_prefix = (
        'https://github.com/lrnolivia/rtxForge/releases/download/'
    )
    if not download_url.startswith(expected_prefix):
        raise RuntimeError('Refusing unexpected update download URL.')

    current = current_build()

    local_version = _version_key(current['version'])
    remote_version = _version_key(manifest['version'])

    if remote_version > local_version:
        available = True
    elif remote_version < local_version:
        available = False
    else:
        available = (
            current['commit'] == 'unknown'
            or manifest['commit'] != current['commit']
        )

    return {
        **manifest,
        'available': available,
        'current_version': current['version'],
        'current_commit': current['commit'],
        'download_url': download_url,
        'published_at': release.get('published_at'),
    }


def install(info, progress=None):
    if not os.environ.get('APPIMAGE'):
        raise RuntimeError(
            'Application updates require the AppImage build.'
        )

    root = desktop_install.installed_path().parent
    root.mkdir(parents=True, exist_ok=True)

    fd, name = tempfile.mkstemp(
        prefix='.rtxforge-download-',
        suffix='.AppImage',
        dir=root,
    )
    os.close(fd)

    stage = Path(name)
    digest = hashlib.sha256()
    received = 0
    expected_size = int(info['size'])

    try:
        request = urllib.request.Request(
            info['download_url'],
            headers={'User-Agent': USER_AGENT},
        )

        with urllib.request.urlopen(
            request,
            timeout=60,
        ) as response, stage.open('wb') as output:

            total = (
                int(response.headers.get('Content-Length') or 0)
                or expected_size
            )

            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break

                output.write(chunk)
                digest.update(chunk)
                received += len(chunk)

                if progress and total:
                    progress(
                        min(received / total, 1.0),
                        received,
                        total,
                    )

            output.flush()
            os.fsync(output.fileno())

        if received != expected_size:
            raise RuntimeError(
                'Update download size mismatch: '
                f'expected {expected_size}, received {received}.'
            )

        actual = digest.hexdigest().lower()
        expected = info['sha256'].lower()

        if actual != expected:
            raise RuntimeError(
                'Update checksum verification failed: '
                f'expected {expected}, got {actual}.'
            )

        stage.chmod(0o755)

        if progress:
            progress(1.0, received, expected_size)

        return desktop_install.install_from(stage)

    finally:
        stage.unlink(missing_ok=True)


def restart():
    target = desktop_install.installed_path().resolve(strict=True)

    env = os.environ.copy()

    for key in ('APPDIR', 'APPIMAGE', 'ARGV0', 'OWD'):
        env.pop(key, None)

    subprocess.Popen(
        [str(target)],
        cwd=str(Path.home()),
        env=env,
        start_new_session=True,
    )

    return str(target)
