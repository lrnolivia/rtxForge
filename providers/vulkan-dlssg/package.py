"""Prepare a hash-pinned local NR + Universal MFG gameplay candidate."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(data):
    return {'size': len(data), 'sha256': digest(data)}


def checked(path, expected):
    raw = Path(path).read_bytes()
    if identity(raw) != {k: expected[k] for k in ('size', 'sha256')}:
        raise ValueError('Pinned input size/hash mismatch: ' + str(path))
    return raw


def package(args):
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT.parents[1]):
        raise ValueError('Choose a new candidate directory outside the product checkout')
    source = json.loads((ROOT / 'source.json').read_text())
    bg3 = json.loads((ROOT.parent / 'bg3fgvk/source.json').read_text())
    mfg = source['mfg_component']
    runtime_archive = checked(args.runtime_archive, bg3['archive'])
    mfg_archive = checked(args.mfg_archive, {'size': mfg['release_size'], 'sha256': mfg['sha256']})
    data = {}
    for filename in ('fgvk.dll', 'nvngx.dll_dlssnr.dll'):
        raw = (args.build / filename).read_bytes()
        if not raw.startswith(b'MZ'):
            raise ValueError('Provider build did not emit a PE DLL: ' + filename)
        data['NativeMods/' + filename] = raw
    data['NativeMods/nvngx_dlssnr.dll'] = args.model.read_bytes()
    if not data['NativeMods/nvngx_dlssnr.dll'].startswith(b'MZ'):
        raise ValueError('The local NR model is not a PE DLL')
    with zipfile.ZipFile(args.runtime_archive) as archive:
        members = {entry.filename.replace('\\', '/'): entry for entry in archive.infolist()}
        if len(members) != len(archive.infolist()):
            raise ValueError('Duplicate Streamline archive member')
        for name, expected in bg3['files'].items():
            if name.startswith('NativeMods/Streamline/'):
                raw = archive.read(members[name])
                if identity(raw) != expected:
                    raise ValueError('Streamline runtime member differs: ' + name)
                data[name] = raw
    with zipfile.ZipFile(args.mfg_archive) as archive:
        matches = [item for item in archive.infolist() if item.filename == 'MFGUnlocker.dll']
        if len(matches) != 1:
            raise ValueError('Universal MFG release member identity differs')
        raw = archive.read(matches[0])
        if identity(raw) != {key: mfg['files']['MFGUnlocker.dll'][key] for key in ('size', 'sha256')}:
            raise ValueError('Universal MFG release DLL differs')
        data['NativeMods/MFG/MFGUnlocker.dll'] = raw
    # Follow the shared provider's requested count; its panel owns the ordinary
    # multiplier control. Its pinned standalone menu/input is gated off by our
    # runtime by default; the MFG backend and original vendor file stay intact.
    data['NativeMods/MFG/RTXMFG-Universal.json'] = (
        b'{"followGame":true,"multiplier":2,"dynamic":false,"dlssgPreset":0}\n')
    data['RTX40MFG-UI.ini'] = b'[Overlay]\nFirstLaunchMenuShown=1\n'
    notices = 'NativeMods/rtxForge-vulkan/'
    data[notices + 'COPYING.txt'] = (ROOT / 'LICENSE').read_bytes()
    for path in sorted((ROOT / 'licenses').iterdir()):
        if path.is_file():
            data[notices + path.name] = path.read_bytes()
    for path in ('LICENSE', 'NOTICE.md'):
        raw = subprocess.check_output(['git', '-C', str(args.mfg_source), 'show', mfg['commit'] + ':' + path])
        if identity(raw) != mfg['notices'][path]:
            raise ValueError('Universal MFG legal notice differs: ' + path)
        data[notices + 'MFG-Unlocker-' + path] = raw
    # The ImGui renderer and backend come from the pinned RDR source tree.
    data[notices + 'ImGui-MIT.txt'] = (args.build / 'source/rdr/vendor/imgui/LICENSE.txt').read_bytes()
    data[notices + 'Inter-OFL.txt'] = (ROOT.parents[1] / 'windows/RtxForge.Windows/Assets/Fonts/OFL-Inter.txt').read_bytes()
    data[notices + 'Inter-OFL.txt'] += b'\n\nBakbak One (rtxForge wordmark and game headings)\n\n' + (ROOT.parents[1] / 'gui/fonts/OFL-BakbakOne.txt').read_bytes()
    data[notices + 'Detours-MIT.txt'] = (args.build / 'source/Detours/LICENSE.md').read_bytes()
    receipt = (args.build / 'source-receipt.json').read_bytes()
    data[notices + 'source-receipt.json'] = receipt
    output.mkdir(parents=True)
    fixture = output / 'mfg-ui-fixture'
    fixture.mkdir()
    (fixture / 'MFGUnlocker.dll').write_bytes(data['NativeMods/MFG/MFGUnlocker.dll'])
    (fixture / 'RTXMFG-Universal.json').write_bytes(data['NativeMods/MFG/RTXMFG-Universal.json'])
    subprocess.run([str((args.build / 'test-mfg-ui.exe').resolve()), str((fixture / 'MFGUnlocker.dll').resolve())], cwd=fixture, check=True)
    archive_path = output / 'rtxForge-Vulkan-NR-UniversalMFG-local.zip'
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, raw in sorted(data.items()):
            archive.writestr(name, raw)
    notice = (ROOT / 'loader/LICENSE.exports.txt').read_bytes()
    (output / 'loader').mkdir()
    (output / 'loader/LICENSE.exports.txt').write_bytes(notice)
    profiles = {}
    for name, executable, loader in (('bg3', 'bg3.exe', args.bg3_loader), ('rdr2', 'RDR2.exe', args.rdr2_loader)):
        loader_spec = json.loads((ROOT / 'loader' / (name + '.json')).read_text())
        profiles[name] = {'executable': executable, 'loader': {
            'binary': identity(loader.read_bytes()), 'game_original': loader_spec['game_original'],
            'exports_notice_sha256': digest(notice)}}
        (output / ('loader-' + name)).mkdir()
        shutil.copyfile(loader, output / ('loader-' + name) / 'bink2w64.dll')
    candidate = {
        **source, 'deployable': True, 'profiles': profiles,
        'archive': {'name': archive_path.name, **identity(archive_path.read_bytes())},
        'files': {name: identity(raw) for name, raw in sorted(data.items())},
        'source_receipt_sha256': digest(receipt),
        'distribution': 'Local gameplay candidate includes a copy of the user-supplied NR model; excluded from distributable builds',
    }
    path = output / 'candidate.json'
    path.write_text(json.dumps(candidate, indent=2) + '\n')
    print(json.dumps({'manifest': str(path), 'archive': str(archive_path), 'files': len(data),
                      'runtime_sha256': candidate['files']['NativeMods/fgvk.dll']['sha256'],
                      'runtime_verified': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'bg3-loader', 'rdr2-loader', 'model', 'runtime-archive', 'mfg-archive', 'mfg-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    package(parser.parse_args())
