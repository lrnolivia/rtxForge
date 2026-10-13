"""Feature composition independent of the pinned, shared MFG provider."""
from pathlib import Path
import transactions as t
NR_NAMES={'nvngx_dlssnr.dll','nvngx.dll_dlssnr.dll','sl.dlss_nr.dll'}
LEGACY_NAMES={'dlss-enabler-headless.dll','dlss-enabler.asi','nvngx.ini','dlssg_to_fsr3_amd_is_better.dll'}
PIPELINE='streamline-native-dlssg-nr-separate-v2'

def compose(sources,mode,config):
    t.need(mode in {'mfg-only','nr-mfg'},'Unsupported graphics pipeline')
    result={n:v for n,v in sources.items() if Path(n).name.lower() not in LEGACY_NAMES}
    if mode=='mfg-only':
        result={n:v for n,v in result.items() if Path(n).name.lower() not in NR_NAMES}
    else:
        for name in config['nr']['components']:
            t.need(name in result and result[name][1]==config['nr']['components'][name],'NR component missing or changed: '+name)
        expected=config['nr'].get('runtime_sha256')
        t.need(expected and result['nvngx_dlssnr.dll'][1]==expected,'NR model does not match the pinned patched runtime')
    for name in ('OptiScaler/streamline/sl.interposer.dll','OptiScaler/streamline/sl.dlss_g.dll','OptiScaler/nvngx_dlssg.dll'):
        t.need(name in result,'Native Streamline DLSS-G component missing: '+name)
    return result

def describe(sources,mode,config):
    return {'pipeline':PIPELINE,'mode':mode,'core_provider':config['repo'],
            'core_commit':config['commit'],'mfg_input_default':'dlssg',
            'mfg_output_default':'dlssg','mfg_nvngx_replacement_default':'none',
            'mfg_provider':'native-streamline-dlssg','mfg_fallback_provider':None,
            'nr_provider':config['nr']['repo'] if mode=='nr-mfg' else None,
            'nr_enabled_at_install':mode=='nr-mfg',
            'private_streamline_present':any('/streamline/' in n for n in sources),
            'headless_fallback_present':'OptiScaler/dlss-enabler-headless.dll' in sources,
            'runtime_verified':False,
            'files':{n:{'sha256':h,'feature':'nr' if Path(n).name.lower() in NR_NAMES else 'shared-mfg'} for n,(_,h) in sorted(sources.items())}}
