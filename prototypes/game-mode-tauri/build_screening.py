"""Build the same offline screenshot worker on Windows and Linux."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    source = Path(__file__).resolve().parent
    import rapidocr
    runtime = Path(rapidocr.__file__).resolve().parent
    sys.path.insert(0, str(source / 'bridge'))
    from screenshot_screen import MODEL_SHA256, VERSION
    model = runtime / 'models/PP-OCRv6_det_small.onnx'
    if hashlib.sha256(model.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError('Pinned screenshot model differs from the distribution.')
    output.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--name',
               'rtxforge-screenshot-screen', '--distpath', str(output / 'dist'),
               '--workpath', str(output / 'work'), '--specpath', str(output),
               '--collect-submodules', 'rapidocr', '--collect-all', 'onnxruntime']
    for data in ('config.yaml', 'default_models.yaml', 'models/PP-OCRv6_det_small.onnx'):
        command += ['--add-data', f'{runtime / data}:rapidocr/{Path(data).parent.as_posix()}']
    subprocess.run(command + [str(source / 'bridge/screenshot_screen.py')], check=True)
    package = output / 'dist/rtxforge-screenshot-screen'
    notices = package / 'notices'
    notices.mkdir(exist_ok=True)
    packages = []
    # Retain dependency license texts, including native runtime third-party notices.
    for dist in importlib.metadata.distributions():
        name = dist.metadata['Name']
        packages.append({'name': name, 'version': dist.version})
        for file in dist.files or []:
            if any(word in file.name.upper() for word in ('LICENSE', 'COPYING', 'NOTICE')):
                path = Path(dist.locate_file(file))
                if path.is_file():
                    target = notices / name / str(file).replace('..', '_')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
    shutil.copy2(source / 'SCREENSHOT_SCREENING.md', notices / 'SCREENSHOT_SCREENING.md')
    (package / 'screening.json').write_text(json.dumps({'version': VERSION, 'modelSha256': MODEL_SHA256,
        'python': sys.version.split()[0], 'packages': packages}, indent=2), encoding='utf-8')
    print(package)


if __name__ == '__main__':
    main()
