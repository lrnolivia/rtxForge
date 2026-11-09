"""Bundle the verified Linux Game Mode runtime for the Desktop distributions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from package_bundle import download_verified_asset

APP = Path(__file__).resolve().parent
GITHUB = 'https://github.com'
GITHUB_API = 'https://api.github.com/repos'
# Match the x64 tools expected by the locked Tauri CLI. The output plugin and
# type-2 runtime otherwise come from mutable upstream continuous releases.
APPIMAGE_TOOLS = (
    ('AppRun-x86_64', 'tauri-apps/binary-releases', 'apprun-old', 'AppRun-x86_64',
     274691722, 'f30140a43a0a59e46db21bdefdf749b9e9f2c6946e92afabbacf98b8ae73fb4f'),
    ('linuxdeploy-07333c6-x86_64.AppImage', 'tauri-apps/binary-releases', 'linuxdeploy-07333c6', 'linuxdeploy-x86_64.AppImage',
     576945544, '36a2d7e274d12e1050d0e9ecfe11d339ed54720b2bec464c286d53f8b07f5c62'),
    ('linuxdeploy-plugin-appimage.AppImage', 'linuxdeploy/linuxdeploy-plugin-appimage', 'continuous', 'linuxdeploy-plugin-appimage-x86_64.AppImage',
     602435573, '49d6a17160675a6bd1781699aae6bdf7692d98552e02a3671d2183d10547842e'),
    ('runtime-x86_64', 'AppImage/type2-runtime', 'continuous', 'runtime-x86_64',
     657374641, '617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46'),
)


def stage_x64_tools(cache):
    tools = cache / 'tauri'
    tools.mkdir(parents=True)
    for name, repository, tag, asset, asset_id, sha in APPIMAGE_TOOLS:
        target = tools / name
        download_verified_asset(f'{GITHUB}/{repository}/releases/download/{tag}/{asset}',
                                f'{GITHUB_API}/{repository}/releases/assets/{asset_id}', sha, target)
        target.chmod(0o755)
    return tools / 'runtime-x86_64'


def bundle(payload, output):
    payload, output = payload.resolve(), output.resolve()
    receipt = json.loads((payload / 'build.json').read_text())
    if receipt.get('dirty') or receipt.get('desktopIntegration') != 1:
        raise ValueError('Only a clean integrated payload can be bundled.')
    subprocess.run(['python3', str(APP / 'package_bundle.py'), '--verify', str(payload)], check=True)
    config = {'bundle': {'active': True, 'targets': ['appimage'],
                         'resources': {str(payload) + '/': 'payload/'}}}
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'bundle.json'
        path.write_text(json.dumps(config))
        # The linuxdeploy AppImage ships its own strip, which can fail on newer
        # system libraries. The Rust release binary is already built and verified.
        env = os.environ | {'NO_STRIP': 'true'}
        if platform.machine() == 'x86_64':
            cache = Path(temporary) / 'cache'
            runtime = stage_x64_tools(cache)
            env.update(XDG_CACHE_HOME=str(cache), LDAI_RUNTIME_FILE=str(runtime))
        env.pop('GH_TOKEN', None)
        subprocess.run(['node', 'node_modules/@tauri-apps/cli/tauri.js', 'bundle',
                        '--ci', '--verbose', '--bundles', 'appimage', '--config', str(path)],
                       cwd=APP, env=env, check=True)
    candidates = list((APP / 'src-tauri/target/release/bundle/appimage').glob('*.AppImage'))
    if len(candidates) != 1:
        raise ValueError('Expected one native Game Mode AppImage.')
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'rtxforge-game-mode.AppImage'
    shutil.copy2(candidates[0], target)
    with tempfile.TemporaryDirectory() as home:
        env = os.environ | {'HOME': home, 'RTXFORGE_PREVIEW_READ_ONLY': '1', 'APPIMAGE_EXTRACT_AND_RUN': '1',
                            'WEBKIT_DISABLE_DMABUF_RENDERER': '1'}
        env.pop('GH_TOKEN', None)
        result = subprocess.run(['dbus-run-session', '--', 'xvfb-run', '-a', str(target), '--appimage-extract-and-run', '--verify-runtime'],
                                env=env, text=True, capture_output=True, timeout=90)
        if result.returncode or '"runtimeVerified":true' not in result.stdout:
            raise RuntimeError(f'The bundled private runtime failed (exit {result.returncode}): '
                               + result.stdout[-1500:] + result.stderr[-2000:])
    with target.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    (output / 'game-mode.json').write_text(json.dumps({'schema': 1, 'desktopIntegration': 1,
        'source': receipt['source'], 'sha256': sha, 'size': target.stat().st_size}, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    bundle(args.payload, args.output)
