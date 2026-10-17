"""Real Windows DesktopService/engine transactions against disposable game files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKER = r'''
import importlib.util,json,sys,hashlib
from pathlib import Path
root=Path(sys.argv[1]);repo=Path(sys.argv[2])
sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
spec=importlib.util.spec_from_file_location('nr_fixture',repo/'tests/test_skynizz_provider.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
archive=root/'release.zip';release=fixtures.fixture(archive)
saved_stdout=sys.stdout
import rtxforge_win_host as host
sys.stdout=saved_stdout
import skynizz_provider as provider,engine_bridge,packages,library_media,cross_os
service=host.service;service.config['storage']['reserve_bytes']=0
service.hardware=lambda:{'ready':True,'system':'Windows','architecture':'AMD64','reason':'fixture'}
resolutions=[]
def resolve(selection='latest'):
    resolutions.append(selection)
    return dict(release,selected_source=selection)
provider.resolve=resolve
original_download=packages.download
def download(url,*args,**kwargs):
    if url.startswith('https://raw.githubusercontent.com/NVIDIA/DLSS/'):
        name=Path(url).name
        return root/('production-sr.dll' if name=='nvngx_dlss.dll' else 'production-'+name)
    return original_download(url,*args,**kwargs) if url.startswith('file:') else archive
packages.download=download
original_module=engine_bridge.module
inject_failure=False
def module(*a,**kw):
    e=original_module(*a,**kw)
    e._running_processes_under_root=lambda root:[]
    e._nr_runtime_candidates=lambda explicit=None:[Path(explicit)] if explicit else []
    e.original_archive_loader=lambda source:({'OptiScaler/streamline/sl.interposer.dll':fixtures.pe(),
                                            'OptiScaler/streamline/sl.dlss_g.dll':fixtures.pe(),
                                            'OptiScaler/nvngx_dlssg.dll':fixtures.pe(),
                                            'dxgi.dll':b'never replace Skynizz loader'}, {})
    if inject_failure:
        original_write=e.atomic_write
        failed=[False]
        def write(path,*args,**kwargs):
            if Path(path).name=='OptiScaler.ini' and not failed[0]:
                failed[0]=True
                raise OSError('injected fixture write failure')
            return original_write(path,*args,**kwargs)
        e.atomic_write=write
    return e
engine_bridge.module=module
model=root/'model.dll';model.write_bytes(fixtures.pe()+b'0'*(32*1024**2))
settings={'runtime_provider':'skynizz','skynizz_version':'latest','nr_runtime':str(model),'manage_dlss_files':False}
def game(name):
    folder=root/name;folder.mkdir()
    (folder/'Game.exe').write_bytes(fixtures.pe())
    (folder/'nvngx_dlss.dll').write_bytes(fixtures.pe())
    (folder/'save.dat').write_bytes(b'untouched')
    return folder
def scan(folder,selected='skynizz'):
    return host.scan({'folders':[str(folder)],'runtime_provider':selected})[0]
def prepare(folder,operation='install',values=None):
    return service.prepare([scan(folder)],'nr-only',operation,visual_settings=settings | (values or {}))
def run(review):
    assert review['rows'] and not review['blocked'],review.get('blocked')
    service.execute(review)
def baseline(folder):
    e=module(service.config)
    return e.load_baseline(folder)['current']
def files(folder):
    return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
checks=[]
fresh=game('Fresh');before=files(fresh)
assert scan(fresh)['blocked']=='' and 'DLSS-G' in scan(fresh,'y4my')['blocked']
review=prepare(fresh);assert files(fresh)==before
assert release['sha256'] in review['rows'][0]['detail'] and str(model) in review['rows'][0]['detail']
run(review)
record=baseline(fresh);ini=(fresh/'OptiScaler.ini').read_text()
for value in ('Enabled=true','CacheInterval=1','WorkingScale=0.67','WhitePointSource=3','PreSr=true'):
    assert value in ini,value
assert 'DualFeature=' not in ini and 'AdaMfgUnlock=true' not in ini
assert record['provider_id']=='skynizz' and record['mfg_provider'] is None
assert record['compatibility_policy']['mfg_route']=='unmanaged-skynizz-nr-only'
assert not record['nr_profile']['runtime_verified']
assert record['nr_runtime']['sha256']==hashlib.sha256(model.read_bytes()).hexdigest()
assert not (fresh/'INSTALL.bat').exists() and (fresh/'nvngx.dll_dlssnr.dll').is_file()
checks.append('active install, read-only review, SR-only eligibility, source/model provenance and honest route')
# Exercise the existing y4my MFG policy through the same lifecycle, using only
# synthetic payload bytes. This establishes config/ownership regression, not GPU MFG.
original_payload=engine_bridge.payload
def payload(e,config,mode,archive=None):
    if e.Y4MY_PROVIDER['id']=='y4my':
        data={'dxgi.dll':fixtures.pe(),'OptiScaler.ini':fixtures.TEMPLATE,
              'OptiScaler/streamline/sl.interposer.dll':fixtures.pe(),
              'OptiScaler/streamline/sl.dlss_g.dll':fixtures.pe()}
        return data,{'sha256':'a'*64,'name':'synthetic-mfg','provider':'fixture'}
    return original_payload(e,config,mode,archive)
engine_bridge.payload=payload
switch=service.prepare([scan(fresh)],'nr-only','install',visual_settings=settings | {'runtime_provider':'y4my'})
assert not switch['rows'] and 'switching providers' in switch['blocked'][0]['reason']
ini=ini.replace('CacheInterval=1','CacheInterval=8').replace('WorkingScale=0.67','WorkingScale=0.5')
(fresh/'OptiScaler.ini').write_text(ini)
count=len(resolutions);repair=prepare(fresh,'repair',{'skynizz_version':'v9.9.9'})
assert len(resolutions)==count,'repair resolved a different release'
run(repair)
assert (fresh/'OptiScaler.ini').read_text()==ini,'repair replaced the user cache preset'
assert baseline(fresh)['archive']['release']['tag']=='v1.2.1'
reset=prepare(fresh,'reset');run(reset)
reset_ini=(fresh/'OptiScaler.ini').read_text()
assert 'CacheInterval=1' in reset_ini and 'WorkingScale=0.67' in reset_ini and 'DualFeature=' not in reset_ini
checks.append('repair pins exact release and preserves full preset; reset retains Skynizz policy')
run(prepare(fresh,'uninstall'));assert files(fresh)==before,files(fresh)
checks.append('restore reproduces the original file hashes')
mfg=game('ExistingMfg');(mfg/'nvngx_dlssg.dll').write_bytes(fixtures.pe());mfg_before=files(mfg)
mfg_settings=settings | {'runtime_provider':'y4my'}
run(service.prepare([scan(mfg,'y4my')],'mfg-only','install',visual_settings=mfg_settings))
mfg_record=baseline(mfg)
assert mfg_record['compatibility_policy']['mfg_route']=='native-ada-y4my-v4-armed'
assert mfg_record['mfg_provider']['enabled'] and mfg_record['provider_id']=='y4my'
assert 'AdaMfgUnlock=true' in (mfg/'OptiScaler.ini').read_text()
assert (mfg/'nvngx_dlssg.dll').read_bytes()==fixtures.pe()
run(service.prepare([scan(mfg,'y4my')],'mfg-only','uninstall',visual_settings=mfg_settings))
assert files(mfg)==mfg_before
checks.append('existing y4my MFG config/ownership and provider-switch restoration boundary')
missing=game('Missing');missing_before=files(missing)
review=prepare(missing,values={'nr_runtime':''})
assert not review['rows'] and 'required' in review['blocked'][0]['reason']
assert files(missing)==missing_before
for mode in ('mfg-only',):
    try:service.prepare([scan(missing)],mode,'install',visual_settings=settings)
    except Exception as error:assert 'NR Only' in str(error)
    else:raise AssertionError('unsupported MFG composition accepted')
assert files(missing)==missing_before
checks.append('missing model and unsupported modes refuse before game writes')
combined_archive=root/'combined.zip';combined_release=fixtures.bridge_fixture(combined_archive,root/'production-sr.dll')
provider.bundled_bridge=lambda selection='latest':(dict(combined_release,selected_source=selection),combined_archive)
combined=game('Combined');(combined/'nvngx_dlssg.dll').write_bytes(fixtures.pe());combined_before=files(combined)
combined_review=service.prepare([scan(combined)],'nr-mfg','install',visual_settings=settings | {'mfg_multiplier':6})
for component in provider.PRODUCTION_RUNTIMES:
    assert combined_release[component]['sha256'] in combined_review['rows'][0]['detail']
run(combined_review);combined_record=baseline(combined);combined_ini=(combined/'OptiScaler.ini').read_text()
assert combined_record['mfg_provider']['enabled'] and combined_record['compatibility_policy']['mfg_route']=='native-ada-skynizz-bridge-armed'
assert combined_record['archive']['release']['variant']=='nr-mfg-bridge' and combined_record['archive']['mfg_runtime']['sha256']
assert combined_record['nr_profile']['enabled'] and not combined_record['nr_profile']['runtime_verified']
for value in ('AdaMfgUnlock=true','AdaBlackwellKernels=true','OverrideInterpolationCount=5','CacheEnabled=false','PreSr=true'):
    assert value in combined_ini,value
assert (combined/'OptiScaler/streamline/sl.dlss_g.dll').is_file()
for component,(filename,_) in provider.PRODUCTION_RUNTIMES.items():
    source=root/('production-sr.dll' if component=='sr_runtime' else 'production-'+filename)
    assert (combined/'OptiScaler'/filename).read_bytes()==source.read_bytes()
    assert combined_record['archive']['release'][component]==combined_release[component]
assert (combined/'dxgi.dll').read_bytes()==fixtures.pe(),'MFG donor replaced the NR loader'
assert (combined/'nvngx_dlssg.dll').read_bytes()==fixtures.pe(),'game native runtime replaced'
run(service.prepare([scan(combined)],'nr-mfg','repair',visual_settings=settings | {'skynizz_version':'v9.9.9'}))
assert baseline(combined)['archive']['release']['sha256']==combined_release['sha256']
for component in provider.PRODUCTION_RUNTIMES:
    assert baseline(combined)['archive']['release'][component]==combined_release[component]
run(service.prepare([scan(combined)],'nr-mfg','uninstall',visual_settings=settings));assert files(combined)==combined_before
checks.append('combined NR+MFG uses one loader, production SR/RR/FG and private Streamline; pinned repair/restore preserve ownership')
failed_combined=game('CombinedFailure');(failed_combined/'nvngx_dlssg.dll').write_bytes(fixtures.pe());combined_before=files(failed_combined)
review=service.prepare([scan(failed_combined)],'nr-mfg','install',visual_settings=settings)
e=review['engine'];write=e.atomic_write
def fail_private(path,*args,**kwargs):
    if Path(path).name=='sl.dlss_g.dll':raise OSError('injected combined runtime failure')
    return write(path,*args,**kwargs)
e.atomic_write=fail_private
try:service.execute(review)
except Exception:pass
else:raise AssertionError('combined write failure was ignored')
assert files(failed_combined)==combined_before
sr_only=host.scan({'folders':[str(missing)],'runtime_provider':'skynizz','feature_mode':'nr-mfg'})[0]
assert 'game-native DLSS Frame Generation' in sr_only['blocked']
checks.append('combined runtime failure restores NR/MFG changes; combined scan requires native FG')
local=game('LocalModel');(local/'nvngx_dlssnr.dll').write_bytes(fixtures.pe()+b'1'*(32*1024**2))
local_before=files(local);run(prepare(local))
assert baseline(local)['nr_runtime']['path']==str(local/'nvngx_dlssnr.dll')
assert baseline(local)['nr_runtime']['sha256']==local_before['nvngx_dlssnr.dll']
run(prepare(local,'uninstall'));assert files(local)==local_before
checks.append('existing game-local model wins and survives restore')
conflict=game('Conflict');(conflict/'renodx-dlss5.addon64').write_bytes(b'another NR consumer')
conflict_before=files(conflict);review=prepare(conflict)
assert not review['rows'] and 'NR consumer' in review['blocked'][0]['reason']
assert files(conflict)==conflict_before
(conflict/'renodx-dlss5.addon64').unlink();(conflict/'OptiScaler.ini').write_text('[Other]\nkeep=true\n')
conflict_before=files(conflict);review=prepare(conflict)
assert not review['rows'] and 'unmanaged' in review['blocked'][0]['reason']
assert files(conflict)==conflict_before
checks.append('other NR consumer and unmanaged OptiScaler collisions preserve unrelated files')
failure=game('Failure');failure_before=files(failure);review=prepare(failure)
e=review['engine'];original_write=e.atomic_write;failed=[False]
def fail_write(path,*args,**kwargs):
    if Path(path).name=='OptiScaler.ini' and not failed[0]:
        failed[0]=True
        raise OSError('injected fixture write failure')
    return original_write(path,*args,**kwargs)
e.atomic_write=fail_write
try:service.execute(review)
except Exception:
    reports=sorted(e.STATE_ROOT.glob('desktop-*.json'),key=lambda path:path.stat().st_mtime_ns)
    failure_report=json.loads(reports[-1].read_text())['results'][-1]
    assert 'injected fixture' in failure_report['error'] and failure_report['undone']
else:raise AssertionError('injected write failure was ignored')
assert files(failure)==failure_before,files(failure)
checks.append('injected failure rolls back every game change')
saved=library_media.load_settings(service.config);saved['skynizz_version']='v1.2.1';saved['runtime_provider']='skynizz'
library_media.save_settings(service.config,saved)
assert library_media.load_settings(service.config)['skynizz_version']=='v1.2.1'
cross_os.THIS_OS='linux'
try:service.prepare([scan(missing)],'nr-only','install',visual_settings=settings)
except Exception as error:assert 'Windows-only' in str(error)
else:raise AssertionError('Linux installed Windows-only provider')
checks.append('settings persistence and Linux direct-install refusal')
print(json.dumps({'checks':checks,'count':len(checks)}))
'''


@unittest.skipUnless(os.name == 'nt', 'Requires the real Windows host adapters')
class WindowsSkynizzTest(unittest.TestCase):
    def test_active_provider_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'Steam').mkdir()
            env = dict(os.environ, RTXFORGE_ROOT=str(ROOT), RTXFORGE_STATE_ROOT=str(root / 'state'),
                       RTXFORGE_DLSS_UNLOCKED_STATE=str(root / 'engine-state'), LOCALAPPDATA=str(root / 'appdata'),
                       RTXFORGE_STEAM_ROOTS=str(root / 'Steam'), PYTHONUTF8='1')
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', WORKER, str(root), str(ROOT)],
                                    env=env, capture_output=True, text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr[-12000:] + result.stdout[-3000:])
            receipt = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(receipt['count'], 11)
            print('PASS: ' + '; '.join(receipt['checks']))


if __name__ == '__main__':
    unittest.main()
