"""Read-only host checks for this package's native NVIDIA NR/MFG route."""
import platform,subprocess,shutil,re
from pathlib import Path

def detect():
    info={'system':platform.system(),'architecture':platform.machine(),'gpu':'Not detected','driver':'Unknown','vram':'Unknown','cpu':platform.processor() or 'Unknown','ready':False,'reason':''}
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith('model name'):info['cpu']=line.split(':',1)[1].strip();break
    except OSError:pass
    if info['system']!='Linux' or info['architecture'].lower() not in ('x86_64','amd64'):
        info['reason']='This package requires 64-bit x86 Linux.';return info
    try:
        result=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader,nounits'],text=True,capture_output=True,timeout=10,check=True)
        rows=[line.split(',') for line in result.stdout.strip().splitlines() if line.count(',')>=2]
        supported=[r for r in rows if family(r[0])]
        chosen=(sorted(supported,key=lambda r:FAMILIES.index(family(r[0])))[-1:] or rows)[0]
        info.update({'gpu':chosen[0].strip(),'driver':chosen[1].strip(),'vram':chosen[2].strip()+' MiB','family':family(chosen[0])})
        if not supported:info['reason']=f"{info['gpu']} isn't an RTX GPU these packages can run on.";return info
    except (OSError,subprocess.SubprocessError,IndexError):
        info['reason']='Cannot verify an NVIDIA GPU and working NVIDIA driver. Install/repair is unavailable; uninstall remains available.';return info
    # Extraction is provider-specific. DLSS-Unlocked uses Python's ZIP reader;
    # the y4my engine can use libarchive even without a 7-Zip executable.
    return ready(info)


# RTX generations by GeForce model number. Only Ada (RTX 40) has been checked in game.
FAMILIES=('turing','ampere','ada','blackwell')
VERIFIED=('ada',)


def family(name):
    match=re.search(r'RTX\s+([2-5])0\d{1,2}\b',str(name))
    return FAMILIES[int(match[1])-2] if match else None


def ready(info):
    """Any RTX 20 to 50 GPU may install; only verified families skip the not-verified note."""
    info['ready']=True;info['verified']=info.get('family') in VERIFIED
    if info['verified']:
        info['reason']='Basic hardware and dependencies passed. Per-game compatibility still requires verification.'
    else:
        info['reason']=f"{info['gpu']} hasn't been verified with these packages yet. Installs are reviewed and restorable; share your result."
    if info.get('family')=='blackwell':
        info['reason']+=" Frame generation uses your GPU's own MFG, so no unlock package is installed."
    return info
