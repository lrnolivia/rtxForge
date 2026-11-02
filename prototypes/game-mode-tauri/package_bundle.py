"""Record native build identity, assemble payloads, and verify complete manifests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request

APP = Path(__file__).resolve().parent
REPO = APP.parents[1]
LINUX_PYTHON = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.14.10%2B20261026-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz'
LINUX_PYTHON_SHA = '4d3c16c59ed0802a3d1d34d8bce504b15ceeaff39d62dadecc6a9fa803412aed'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def revision():
    return subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()


def fingerprint():
    value = hashlib.sha256()
    files = [p for folder in ('src', 'public', 'src-tauri/src', 'src-tauri/icons', 'src-tauri/capabilities')
             for p in (APP / folder).rglob('*') if p.is_file()]
    files += [APP / p for p in ('package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.mjs',
                              'index.html', 'src-tauri/Cargo.toml', 'src-tauri/Cargo.lock',
                              'src-tauri/build.rs', 'src-tauri/tauri.conf.json')]
    for path in sorted(set(files)):
        if path.is_file():
            value.update(path.relative_to(APP).as_posix().encode())
            value.update(bytes.fromhex(digest(path)))
    return value.hexdigest()


def executable():
    return APP / 'src-tauri/target/release' / ('rtxforge-game-mode.exe' if os.name == 'nt' else 'rtxforge-game-mode')


def record_native():
    value = {'source': revision(), 'inputs': fingerprint(), 'sha256': digest(executable())}
    (executable().parent / 'native-build.json').write_text(json.dumps(value, indent=2), encoding='utf-8')


def verify(folder):
    folder = Path(folder).resolve()
    receipt = json.loads((folder / 'build.json').read_text(encoding='utf-8-sig'))
    for relative, expected in receipt['files'].items():
        path = folder / relative
        if path.is_symlink() or not path.resolve().is_relative_to(folder) or digest(path) != expected:
            raise ValueError('Incomplete or changed application payload: ' + relative)
    for relative, target in receipt.get('links', {}).items():
        path = folder / relative
        if not path.is_symlink() or os.readlink(path) != target or not path.resolve().is_relative_to(folder):
            raise ValueError('Changed runtime link: ' + relative)
    return receipt


def smoke(folder):
    folder = Path(folder).resolve()
    python = folder / ('python/python.exe' if os.name == 'nt' else 'python/bin/python3')
    env = dict(os.environ, RTXFORGE_ROOT=str(folder / 'engine'), RTXFORGE_ENGINE_BRIDGE='1',
               RTXFORGE_APP_EXE=str(folder / ('rtxforge-game-mode.exe' if os.name == 'nt' else 'rtxforge-game-mode')))
    for key in ('PYTHONPATH', 'RTXFORGE_PREVIEW_READ_ONLY', 'RTXFORGE_PYTHON', 'RTXFORGE_READ_ONLY'):
        env.pop(key, None)
    child = subprocess.Popen([str(python), '-u', '-B', str(folder / 'bridge/engine_host.py')],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=env, cwd=folder)
    try:
        for method in ('hello', 'settings_get'):
            child.stdin.write(json.dumps({'id': method, 'method': method, 'params': {}}) + '\n')
            child.stdin.flush()
            while True:
                line = child.stdout.readline()
                if not line:
                    raise RuntimeError('Installed host stopped: ' + child.stderr.read()[-3000:])
                result = json.loads(line)
                if result.get('id') == method:
                    if 'error' in result: raise RuntimeError(result['error'])
                    break
        child.stdin.close()
        if child.wait(timeout=20) != 0: raise RuntimeError('Installed host failed to drain.')
    finally:
        if child.poll() is None:
            child.stdin.close()
            child.wait(timeout=30)
        child.stdout.close()
        child.stderr.close()


def bundle(output, screening):
    output, screening = output.resolve(), screening.resolve()
    native = json.loads((executable().parent / 'native-build.json').read_text(encoding='utf-8'))
    if native != {'source': revision(), 'inputs': fingerprint(), 'sha256': digest(executable())}:
        raise ValueError('Native build identity differs. Build the current source before packaging.')
    if output == APP or output == REPO or output in APP.parents:
        raise ValueError('Choose a distinct package output directory.')
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(executable(), output / executable().name)
    shutil.copytree(APP / 'bridge', output / 'bridge', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(screening, output / 'screening', dirs_exist_ok=True)
    if os.name != 'nt':
        archive = output.parent / 'python-linux-x64.tar.gz'
        if not archive.is_file() or digest(archive) != LINUX_PYTHON_SHA:
            urllib.request.urlretrieve(LINUX_PYTHON, archive)
        if digest(archive) != LINUX_PYTHON_SHA: raise ValueError('Private Python archive hash mismatch.')
        with tarfile.open(archive) as source: source.extractall(output, filter='data')
        for relative in ('engine', 'scripts', 'providers', 'windows/engine-host', 'gui/icons', 'packaging/steam-artwork'):
            shutil.copytree(REPO / relative, output / 'engine' / relative, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ('provider.json', 'VERSION'):
            shutil.copy2(REPO / name, output / 'engine' / name)
    for name in ('README.md', 'FEATURE_PARITY.md', 'VALIDATION.md', 'ASSETS.md', 'SCREENSHOT_SCREENING.md', 'Install.ps1', 'install_linux.py', 'package_bundle.py'):
        shutil.copy2(APP / name, output / name)
    shutil.copy2(REPO / 'LICENSE', output / 'LICENSE')
    notices = output / 'notices'
    shutil.copytree(APP / 'public/fonts', notices / 'fonts', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('*.woff', '*.woff2', '*.ttf'))
    for path in (APP / 'node_modules/@tauri-apps/api').glob('LICENSE*'):
        shutil.copy2(path, notices / path.name)
    cargo_home = Path(os.environ.get('CARGO_HOME') or Path.home() / '.cargo')
    for package in tomllib.loads((APP / 'src-tauri/Cargo.lock').read_text())['package']:
        crate = package['name'] + '-' + package['version']
        for path in (cargo_home / 'registry/src').glob('*/' + crate + '/*'):
            if path.is_file() and path.name.upper().startswith(('LICENSE','COPYING','NOTICE')):
                destination = notices / 'rust' / crate
                destination.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,destination/path.name)
    dirty = bool(subprocess.check_output(['git', '-C', str(REPO), 'diff', '--name-only'], text=True).strip())
    files = {path.relative_to(output).as_posix(): digest(path) for path in sorted(output.rglob('*'))
             if path.is_file() and path.name != 'build.json' and not path.is_symlink()}
    receipt = {'schema': 2, 'version': '1.0.0', 'source': revision(), 'dirty': dirty,
               'native': native, 'platform': 'win-x64' if os.name == 'nt' else 'linux-x64',
               'readOnlyDefault': False, 'desktopIntegration': 1, 'files': files,
               'links': {p.relative_to(output).as_posix(): os.readlink(p) for p in output.rglob('*') if p.is_symlink()}}
    (output / 'build.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    verify(output)
    smoke(output)
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--record-native', action='store_true')
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--smoke', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--screening', type=Path)
    args = parser.parse_args()
    if args.record_native: record_native()
    elif args.verify: verify(args.verify)
    elif args.smoke: smoke(args.smoke)
    else: bundle(args.output, args.screening)
