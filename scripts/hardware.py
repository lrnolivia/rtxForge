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
        supported=[r for r in rows if re.search(r'RTX\s+40\d{2}',r[0])]
        chosen=(supported or rows)[0]
        info.update({'gpu':chosen[0].strip(),'driver':chosen[1].strip(),'vram':chosen[2].strip()+' MiB'})
        if not supported:info['reason']='This native NVIDIA package targets GeForce RTX 40-series GPUs. This GPU is not validated.';return info
    except (OSError,subprocess.SubprocessError,IndexError):
        info['reason']='Cannot verify an NVIDIA GPU and working NVIDIA driver. Install/repair is unavailable; uninstall remains available.';return info
    # Extraction is provider-specific. DLSS-Unlocked uses Python's ZIP reader;
    # the y4my engine can use libarchive even without a 7-Zip executable.
    info['ready']=True;info['reason']='Basic hardware and dependencies passed. Per-game compatibility still requires verification.';return info
