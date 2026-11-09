"""Bundle the verified Linux Game Mode runtime for the Desktop distributions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

APP = Path(__file__).resolve().parent


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
