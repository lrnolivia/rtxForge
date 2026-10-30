"""Verified application updates for AppImage and Flatpak installations."""
from pathlib import Path
import json
import os
import re
import subprocess
import urllib.request

import desktop_install
import auto_update
import flatpak_host

ROOT = Path(__file__).resolve().parents[1]

RELEASE_API = (
    'https://api.github.com/repos/lrnolivia/rtxForge/'
    'releases/tags/continuous'
)

MANIFEST_NAME = 'rtxforge-update.json'

# Each channel is one GitHub release with its own manifest (same schema).
CHANNELS = {
    'continuous': (RELEASE_API, MANIFEST_NAME),
    'beta': (
        'https://api.github.com/repos/lrnolivia/rtxForge/releases/tags/beta',
        'rtxforge-beta-linux.json',
    ),
}
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
    match = re.fullmatch(r'(\d+(?:\.\d+)*)(?:-(beta|rc)\.(\d+))?', text)
    if not match:
        raise ValueError(f'Invalid application version: {value}')
    core = tuple(int(part) for part in match[1].split('.'))
    core += (0,) * max(0, 3 - len(core))
    return core, ((-1 if match[2] == 'beta' else 0), int(match[3])) if match[2] is not None else (1, 0)


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


def channel():
    """The channel this install follows: an explicit override, the Beta
    download being run, then what the install recorded; continuous otherwise."""
    override = os.environ.get('RTXFORGE_UPDATE_CHANNEL', '').strip().lower()
    if override:
        if override not in CHANNELS:
            raise RuntimeError(f'Unknown update channel: {override}')
        return override
    if flatpak_host.sandboxed():
        return 'beta'
    if desktop_install.BETA_APPIMAGE.fullmatch(Path(os.environ.get('APPIMAGE', '')).name):
        return 'beta'
    return desktop_install.installed_channel() or 'continuous'


def check():
    selected = channel()
    release_api, manifest_name = CHANNELS[selected]
    release = _json(release_api)

    assets = {
        asset['name']: asset
        for asset in release.get('assets', [])
    }

    manifest_asset = assets.get(manifest_name)
    if not manifest_asset:
        raise RuntimeError(
            'The rtxForge Beta release has no Linux build yet.'
            if selected == 'beta'
            else 'The rtxForge update release has no update manifest.'
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

    package_format = 'appimage'
    if flatpak_host.sandboxed():
        package_format = 'flatpak'
        name = f"rtxForge-{manifest['version']}-x86_64.flatpak"
        app_asset = assets.get(name)
        checksum = assets.get(name + '.sha256')
        if not app_asset or not checksum:
            raise RuntimeError('This release has no verified Flatpak update yet.')
        if not checksum['browser_download_url'].startswith(auto_update.PREFIX):
            raise RuntimeError('Refusing unexpected update checksum address.')
        sha = re.search(r'\b[0-9a-fA-F]{64}\b', _bytes(checksum['browser_download_url']).decode('ascii'))
        if not sha:
            raise RuntimeError('Invalid Flatpak checksum.')
        manifest.update(appimage=name, sha256=sha[0].lower(), size=int(app_asset['size']))

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
        'update_channel': selected,
        'published_at': release.get('published_at'),
        'format': package_format,
    }


def supported():
    return bool(os.environ.get('APPIMAGE')) or flatpak_host.sandboxed()


def stage(info, progress=None):
    if not supported():
        raise RuntimeError('Use the packaged app to install application updates.')
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache')))
    return auto_update.download({**info, 'name': info['appimage'], 'url': info['download_url']},
                                cache / 'rtxforge/updates', progress)


def apply(info, path):
    payload = {**info, 'name': info['appimage']}
    if not auto_update.verified(path, payload):
        raise RuntimeError('The staged update changed. Check for updates again.')
    if info.get('format') == 'flatpak':
        # Update the installation this sandbox actually came from. Never create
        # a second user copy of a system app, or guess a custom installation.
        files = flatpak_host.host_files()
        if files.as_posix().startswith('/var/lib/flatpak/'):
            scope = '--system'
        elif files.as_posix().startswith((Path.home() / '.local/share/flatpak').as_posix() + '/'):
            scope = '--user'
        else:
            raise RuntimeError('Update this custom Flatpak installation in your software manager.')
        result = flatpak_host.run_host(['flatpak', 'install', scope, '--noninteractive', '--assumeyes',
                                       '--no-deps', str(path)], timeout=300)
        if result.returncode:
            raise RuntimeError('Flatpak update failed. ' + (result.stderr or 'Try your software manager.').strip()[-500:])
        return str(path)
    if not os.environ.get('APPIMAGE'):
        raise RuntimeError('Application updates require the AppImage build.')
    Path(path).chmod(0o755)
    installed = desktop_install.install_from(path)
    if info.get('update_channel') in CHANNELS:
        desktop_install.record_channel(info['update_channel'])
    return installed


def install(info, progress=None):
    return apply(info, stage(info, progress))


def restart(game_mode=False):
    if flatpak_host.sandboxed():
        subprocess.Popen(['flatpak-spawn', '--host', '--directory=/', 'flatpak', 'run', flatpak_host.APP_ID,
                          *(['--game-mode'] if game_mode else [])],
                         start_new_session=True)
        return flatpak_host.APP_ID
    target = desktop_install.installed_path().resolve(strict=True)

    env = os.environ.copy()

    for key in ('APPDIR', 'APPIMAGE', 'ARGV0', 'OWD'):
        env.pop(key, None)

    subprocess.Popen(
        [str(target), *(['--game-mode'] if game_mode else [])],
        cwd=str(Path.home()),
        env=env,
        start_new_session=True,
    )

    return str(target)
