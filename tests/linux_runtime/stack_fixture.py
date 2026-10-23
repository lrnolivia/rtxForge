"""Disposable stand-ins for the NVIDIA driver, a Proton build and a game's prefix.

Nothing here touches a real Steam library, prefix or driver; every path lives
under the caller's temporary directory.
"""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

USER_REG = ('WINE REGISTRY Version 2\n;; All keys relative to REGISTRY\\\\User\\\\S-1-5-21-0-0-0-1000\n\n'
            '#arch=win64\n\n'
            '[Software\\\\Wine\\\\DllOverrides] 1788804309\n#time=1dc0000000000000\n"atiadlxx"="disabled"\n\n')


def driver(root, model='NVIDIA GeForce RTX 4070', version='615.71.09'):
    """A /proc/driver/nvidia look-alike plus the driver's Wine NGX folder."""
    proc = Path(root) / 'proc-driver-nvidia'
    (proc / 'gpus' / '0000:01:00.0').mkdir(parents=True)
    (proc / 'version').write_text(f'NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  {version}  Release Build\n')
    (proc / 'gpus' / '0000:01:00.0' / 'information').write_text(f'Model: \t\t {model}\nIRQ:   \t\t 117\n')
    wine = Path(root) / 'nvidia-wine'
    wine.mkdir()
    for name in ('nvngx.dll', '_nvngx.dll'):
        (wine / name).write_bytes(b'driver ' + name.encode())
    return proc, wine


def proton(root, name='Proton 10.0', components=('dxvk', 'vkd3d-proton', 'nvapi')):
    """A Proton build's files/lib/wine layout with component version files."""
    lib = Path(root) / 'common' / name / 'files' / 'lib'
    layouts = {'dxvk': ('dxgi.dll', 'd3d11.dll'), 'vkd3d-proton': ('d3d12.dll', 'd3d12core.dll'),
               'nvapi': ('nvapi64.dll', 'nvofapi64.dll')}
    versions = {'dxvk': 'dxvk (v2.6.2)', 'vkd3d-proton': 'vkd3d-proton (vkd3d-1.1-4904)', 'nvapi': 'dxvk-nvapi (v0.9.0)'}
    for component in components:
        folder = lib / 'wine' / component
        (folder / 'x86_64-windows').mkdir(parents=True)
        for dll in layouts[component]:
            (folder / 'x86_64-windows' / dll).write_bytes(b'PE')
        (folder / 'version').write_text('0' * 40 + ' ' + versions[component] + '\n')
    return lib


def prefix(library, appid, lib, version='10.0-200', nvapi=True, ngx=True):
    """<library>/steamapps/compatdata/<appid>/pfx as Proton leaves it after one run."""
    compat = Path(library) / 'steamapps' / 'compatdata' / str(appid)
    pfx = compat / 'pfx'
    system32 = pfx / 'drive_c' / 'windows' / 'system32'
    system32.mkdir(parents=True)
    (pfx / 'user.reg').write_text(USER_REG)
    (compat / 'version').write_text(version + '\n')
    (compat / 'config_info').write_text(f'{version}\n{lib.parent}/share/fonts/\n{lib}/\n')
    if nvapi:
        (system32 / 'nvapi64.dll').write_bytes(b'nvapi')
    if ngx:
        for name in ('nvngx.dll', '_nvngx.dll'):
            (system32 / name).write_bytes(b'ngx')
    devices = pfx / 'dosdevices'
    devices.mkdir()
    os.symlink('../drive_c', devices / 'c:')
    os.symlink('/', devices / 'z:')
    return pfx


def busy_proc(root, prefix):
    """A fake /proc with one process running inside the prefix."""
    proc = Path(root) / 'proc-busy'
    (proc / '4242').mkdir(parents=True)
    (proc / '4242' / 'environ').write_bytes(b'HOME=/x\0WINEPREFIX=' + str(Path(prefix).resolve()).encode() + b'\0')
    return proc


def idle_proc(root):
    proc = Path(root) / 'proc-idle'
    proc.mkdir(parents=True, exist_ok=True)
    return proc
