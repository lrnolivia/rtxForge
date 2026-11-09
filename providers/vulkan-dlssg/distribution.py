"""Fetch and verify the exact reviewed Vulkan runtime/model bundle for builds."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request
import zipfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / 'scripts'))
import packages
import transactions as t


def download_bundle(spec, source):
    token = os.environ.get('GH_TOKEN')
    public_url = spec['url']
    for attempt in range(3):
        request = public_url
        if token and attempt != 1:
            request = Request('https://api.github.com/repos/lrnolivia/rtxForge/releases/assets/668303214'
                              + f'?fresh={time.time_ns()}', headers={'Accept': 'application/octet-stream'})
            request.add_unredirected_header('Authorization', f'Bearer {token}')
        try:
            packages.download(request, source, expected=spec['sha256'], size=spec['size'])
            return
        except (URLError, TimeoutError, ConnectionError) as error:
            if attempt == 2 or isinstance(error, HTTPError) and error.code not in (429, 500, 502, 503, 504):
                raise
            print(f'Vulkan bundle download failed ({error}); retrying.', flush=True)
            time.sleep(2 ** (attempt + 1))


def install(output, archive=None):
    spec = json.loads((ROOT / 'bundle.json').read_text(encoding='utf-8'))
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = Path(archive).resolve() if archive else output.parent / spec['archive']
    if archive is None:
        download_bundle(spec, source)
    t.need(source.stat().st_size == spec['size'] and t.digest(source) == spec['sha256'], 'Vulkan build bundle differs.')
    with zipfile.ZipFile(source) as bundle:
        t.need(len(bundle.infolist()) == len(spec['files']), 'Vulkan bundle inventory differs.')
        seen = set()
        for item in bundle.infolist():
            name = item.filename
            t.relative(name)
            t.need(name in spec['files'] and name not in seen and not item.is_dir(), 'Unexpected Vulkan bundle entry.')
            seen.add(name)
            expected = spec['files'][name]
            t.need(item.file_size == expected['size'], 'Vulkan bundle entry size differs.')
            destination = t.safe(output / name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + '.part')
            with bundle.open(item) as src, temporary.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            t.need(t.digest(temporary) == expected['sha256'], 'Vulkan bundle entry hash differs.')
            temporary.replace(destination)
    print(json.dumps({'bundle': spec['sha256'], 'output': str(output), 'runtime_verified': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    install(args.output, args.archive)
