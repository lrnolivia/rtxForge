"""Read adjacent NR evidence without loading DLLs or inferring visual success."""
from pathlib import Path
import configparser
import datetime
import hashlib
import os
import re
import stat

CROSS_GEN_SHA256='e67dee209320cdafe0e93e45675d7aa34323a53acc57a72b2e40a181581c989a'
BLACKWELL_SHA256='e16bcf15e16e13f527491cdf7845b2fe6521a738d8f7c9c721866a8496e1fc8e'


def read_regular(path, limit=4*1024*1024, tail=False):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):raise ValueError('Not a regular file')
        if tail:source.seek(max(0,info.st_size-limit))
        return source.read(limit),info


def parse_log(text):
    # Ignore generic NGX diagnostic callbacks: they also describe SR and RR.
    starts=list(re.finditer(r'^.*OptiScaler v[^\n]+loaded.*$',text,re.M))
    if starts:text=text[starts[-1].start():]
    created=bool(re.search(r'CreateFeature\(18\).*result=0x0*1\b',text,re.I))
    timings=re.findall(r'DLSS-NR GPU window:.*',text)
    errors=[line.strip() for line in text.splitlines() if re.search(r'(?:DLSS-NR|DlssNr|CreateFeature\(18\)).*(?:failed|failure|error)',line,re.I) and 'NgxDiagnostics' not in line]
    intensity=re.findall(r'DlssNr\.Intensity:\s*([\d.]+)',text)
    toggles=re.findall(r'Neural Rendering toggle key pressed, setting DlssNrEnabled to (true|false)',text,re.I)
    enabled=re.findall(r'DlssNr\.Enabled:\s*(true|false)',text,re.I)
    return {'model_created':created,'gpu_samples_observed':bool(timings),
            'warnings':errors[-8:],'last_gpu_sample':timings[-1] if timings else '',
            'logged_intensity':float(intensity[-1]) if intensity else None,
            'logged_enabled':enabled[-1].lower()=='true' if enabled else None,
            'run_header_observed':bool(starts),'hotkey_toggle_events':[value.lower()=='true' for value in toggles],
            'hotkey_evidence_note':'Toggle events require upstream debug logging; absence at Info level does not prove that the key failed.'}


def inspect(game, hashes=True):
    root=Path(game['game'])
    relative=Path(game.get('exe',''))
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe executable path')
    directory=root/relative.parent
    result={'name':game.get('name',root.name),'settings':{},'files':{},'observations':[],
            'visual_result':'Not established by file or log inspection'}
    try:
        data,info=read_regular(directory/'OptiScaler.ini',1024*1024)
        parser=configparser.ConfigParser(strict=False,interpolation=None)
        parser.read_string(data.decode('utf-8-sig',errors='replace'))
        nr=dict(parser['DlssNr']) if parser.has_section('DlssNr') else {}
        result['settings']={k:nr.get(k,'auto') for k in ('enabled','intensity','skinstructure','applymodel','runbeforesr','workingscale','passes','togglekey','processfilter')}
        result['config_modified_utc']=datetime.datetime.fromtimestamp(info.st_mtime,datetime.timezone.utc).isoformat()
        if nr.get('enabled','false').lower()!='true':result['observations'].append('NR is disabled in the saved configuration.')
        if nr.get('intensity','auto') in ('0','0.0','0.00'):result['observations'].append('NR intensity is zero; model execution alone may produce no visible change.')
        if nr.get('applymodel','true').lower()=='false':result['observations'].append('ApplyModel is disabled.')
    except (OSError,ValueError,configparser.Error) as exc:result['observations'].append('Configuration unavailable: '+type(exc).__name__)
    for name in ('nvngx_dlssnr.dll','nvngx.dll_dlssnr.dll'):
        path=directory/name
        try:
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as source:
                info=os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode):raise ValueError('Not a regular file')
                item={'present':True,'size':info.st_size}
                if hashes:
                    digest=hashlib.file_digest(source,'sha256').hexdigest();item['sha256']=digest
                    if name=='nvngx_dlssnr.dll':item['variant']='RTX 20–40 cross-generation' if digest==CROSS_GEN_SHA256 else 'RTX 50 original' if digest==BLACKWELL_SHA256 else 'Unrecognized build'
                result['files'][name]=item
        except (OSError,ValueError):result['files'][name]={'present':False}
    if not result['files']['nvngx_dlssnr.dll']['present']:result['observations'].append('No adjacent NR runtime. A provider-specific external path may still load one; verify the log.')
    try:
        text,log_info=read_regular(directory/'OptiScaler.log',tail=True)
        result['log']=parse_log(text.decode('utf-8',errors='replace'))
        result['log']['modified_utc']=datetime.datetime.fromtimestamp(log_info.st_mtime,datetime.timezone.utc).isoformat()
        result['log']['predates_config']=result.get('config_modified_utc','')>result['log']['modified_utc']
        if result['log']['predates_config']:result['observations'].append('The log predates the saved settings; it does not verify the current configuration.')
        if result['log']['gpu_samples_observed']:result['observations'].append('The captured run records NR GPU timing. This establishes execution evidence, not visible correctness.')
        elif result['log']['model_created']:result['observations'].append('NR model creation succeeded; evaluation is not established by this log.')
        else:result['observations'].append('No NR model/evaluation evidence in the captured log tail.')
    except (OSError,ValueError):result['observations'].append('No readable OptiScaler log.')
    return result
