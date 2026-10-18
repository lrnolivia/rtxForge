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
import importlib.util,json,sys,hashlib,zipfile
from pathlib import Path
from unittest.mock import patch
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
settings={'runtime_provider':'skynizz','skynizz_version':'latest','nr_runtime':str(model),'manage_dlss_files':False,'nr_on_launch':True}
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
def run(review,allow_blocked=False):
    assert review['rows'] and (allow_blocked or not review['blocked']),review.get('blocked')
    service.execute(review)
def baseline(folder):
    e=module(service.config)
    return e.load_baseline(folder)['current']
def files(folder):
    return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
checks=[]
control=game('Control')
(control/'Control_DX12.exe').write_bytes(fixtures.pe())
(control/'Control_DX11.exe').write_bytes(fixtures.pe()+b'larger alternate renderer')
control_row=scan(control)
assert control_row['exe']=='Control_DX12.exe',control_row
assert engine_bridge.game(module(service.config),control_row).exe==control/'Control_DX12.exe'
checks.append('Control Ultimate Edition keeps the same DX12 executable in discovery and review')
bg3=game('Baldurs Gate 3')
(bg3/'Game.exe').rename(bg3/'bg3.exe')
bg3_before=files(bg3);bg3_row=scan(bg3)
assert 'DirectX 11 or Vulkan' in bg3_row['blocked'],bg3_row
bg3_row['blocked']=''
bg3_review=service.prepare([bg3_row],'nr-only','install',visual_settings=settings)
assert not bg3_review['rows'] and 'DirectX 11 or Vulkan' in bg3_review['blocked'][0]['reason'],bg3_review
assert files(bg3)==bg3_before
checks.append('DX11/Vulkan-only BG3 cannot enter native NR through scan or a stale review row')
fresh=game('Fresh');before=files(fresh)
assert scan(fresh)['blocked']=='' and 'DLSS-G' in scan(fresh,'y4my')['blocked']
review=prepare(fresh);assert files(fresh)==before
assert release['sha256'] in review['rows'][0]['detail'] and str(model) in review['rows'][0]['detail']
run(review)
record=baseline(fresh);ini=(fresh/'OptiScaler.ini').read_text()
for value in ('Enabled=true','CacheInterval=1','WorkingScale=0.65','LocalStructure=1.0','SkinStructure=1.0','WhitePointSource=3','PreSr=true'):
    assert value in ini,value
import companion_controls
with patch.object(companion_controls.Controls,'_start_watcher',lambda self:None):
    controls=companion_controls.Controls(host.STATE)
    values=controls.status({'row':scan(fresh)})['values']
assert values['work_scale']==.65 and values['structure']==1.0 and values['skin']==1.0,values
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
ini=ini.replace('CacheInterval=1','CacheInterval=8').replace('WorkingScale=0.65','WorkingScale=0.5').replace('LocalStructure=1.0','LocalStructure=0.43').replace('SkinStructure=1.0','SkinStructure=0.71')
(fresh/'OptiScaler.ini').write_text(ini)
count=len(resolutions);repair=prepare(fresh,'repair',{'skynizz_version':'v9.9.9'})
assert len(resolutions)==count,'repair resolved a different release'
run(repair)
assert (fresh/'OptiScaler.ini').read_text()==ini,'repair replaced the user cache preset'
assert baseline(fresh)['archive']['release']['tag']=='v1.2.1'
reset=prepare(fresh,'reset');run(reset)
reset_ini=(fresh/'OptiScaler.ini').read_text()
assert 'CacheInterval=1' in reset_ini and 'WorkingScale=0.65' in reset_ini and 'LocalStructure=1.0' in reset_ini and 'SkinStructure=1.0' in reset_ini and 'DualFeature=' not in reset_ini
checks.append('repair pins exact release and preserves full preset; reset retains Skynizz policy')
run(prepare(fresh,'uninstall'));assert files(fresh)==before,files(fresh)
checks.append('restore reproduces the original file hashes')
import game_display as display
from types import SimpleNamespace
display_game=game('DisplayReview');display_before=files(display_game)
original_target=display.target
display.target=lambda *a,**kw:original_target(SimpleNamespace(appid='2456740',exe='inZOI-Win64-Shipping.exe'))
display_path,display_section,_=display.target(None)
display_path.parent.mkdir(parents=True,exist_ok=True)
display_original=('['+display_section+']\nFullscreenMode=0\nResolutionSizeX=1920\nResolutionSizeY=1080\nDLSSG_Mode=4\n').encode()
display_path.write_bytes(display_original)
def display_review(operation='install',enabled=True):
    checked=host.prepare({'rows':[scan(display_game)],'mode':'nr-only','operation':operation,
                          'settings':settings|{'borderless_4k':enabled}})
    return host.reviews.pop(checked['token'])
review=display_review()
assert display_path.read_bytes()==display_original,'display review wrote settings'
assert '3840' in review['rows'][0]['detail']
run(review)
assert b'ResolutionSizeX=3840' in display_path.read_bytes()
assert b'DLSSG_Mode=4' in display_path.read_bytes()
run(display_review('uninstall',False))
assert display_path.read_bytes()==display_original and files(display_game)==display_before
checks.append('Windows host review installs and restores backed-up borderless preferences')
review=display_review()
display_current=display_original+b'; changed after review\n'
display_path.write_bytes(display_current)
try:service.execute(review)
except Exception:pass
else:raise AssertionError('display review drift was ignored')
assert files(display_game)==display_before,'display failure left a partial feature install'
assert display_path.read_bytes()==display_current,'rollback overwrote a concurrent display preference'
display.target=original_target
checks.append('display drift rolls back feature writes and preserves newer display settings')
local_model=game('ExplicitModel')
old_model=fixtures.pe()+b'old'*(12*1024**2)
(local_model/'nvngx_dlssnr.dll').write_bytes(old_model)
local_before=files(local_model)
run(prepare(local_model,values={'nr_runtime':''}))
assert (local_model/'nvngx_dlssnr.dll').read_bytes()==old_model
run(prepare(local_model,'uninstall'))
assert files(local_model)==local_before
explicit=prepare(local_model)
assert str(model) in explicit['rows'][0]['detail']
run(explicit)
assert (local_model/'nvngx_dlssnr.dll').read_bytes()==model.read_bytes()
assert baseline(local_model)['nr_runtime']['explicit_override']
run(prepare(local_model,'uninstall'))
assert files(local_model)==local_before
checks.append('explicit model replaces a game-local copy after review and restores it; automatic selection preserves it')
mfg=game('ExistingMfg');(mfg/'nvngx_dlssg.dll').write_bytes(fixtures.pe())
(mfg/'OptiScaler').mkdir();(mfg/'OptiScaler/old-support.dll').write_bytes(b'original support bytes')
mfg_before=files(mfg)
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
# A restore returns an original support tree, but removes its former loader/INI.
# A subsequent install may back up these exact recorded bytes without treating
# an unknown live OptiScaler install as ours.
old_proxy=mfg/mfg_record['proxy'];old_proxy.write_bytes(b'external active loader')
review=prepare(mfg)
assert not review['rows'] and 'unmanaged' in review['blocked'][0]['reason']
old_proxy.unlink()
review=prepare(mfg)
assert review['plans'][0]['preview']['restored_support_tree']
assert 'previous restore' in review['rows'][0]['detail'] and files(mfg)==mfg_before
(mfg/'OptiScaler/old-support.dll').write_bytes(b'changed since review')
drift_before=files(mfg)
try:service.execute(review)
except Exception:pass
else:raise AssertionError('restored support drift was ignored')
assert files(mfg)==drift_before
review=prepare(mfg)
assert not review['rows'] and 'unmanaged' in review['blocked'][0]['reason']
(mfg/'OptiScaler/old-support.dll').write_bytes(b'original support bytes')
run(prepare(mfg));run(prepare(mfg,'uninstall'))
assert files(mfg)==mfg_before,'support tree was not restored exactly'
unknown=game('UnknownSupport');(unknown/'OptiScaler').mkdir()
(unknown/'OptiScaler/old-support.dll').write_bytes(b'original support bytes')
unknown_before=files(unknown);review=prepare(unknown)
assert not review['rows'] and 'unmanaged' in review['blocked'][0]['reason']
assert files(unknown)==unknown_before
checks.append('exact inactive restored support tree can be backed up and restored; active loaders, unknown folders and review drift still refuse')
missing=game('Missing');missing_before=files(missing)
review=prepare(missing,values={'nr_runtime':''})
assert not review['rows'] and 'required' in review['blocked'][0]['reason']
assert files(missing)==missing_before
try:provider.require_mode('windows','mfg-only')
except Exception as error:assert 'NR Only' in str(error)
else:raise AssertionError('stock package accepted MFG')
assert files(missing)==missing_before
checks.append('missing model and unsupported modes refuse before game writes')
combined_archive=root/'combined.zip';combined_release=fixtures.bridge_fixture(combined_archive,root/'production-sr.dll')
provider.bundled_bridge=lambda selection='latest':(dict(combined_release,selected_source=selection),combined_archive)
combined=game('Combined');(combined/'nvngx_dlssg.dll').write_bytes(fixtures.pe());combined_before=files(combined)
combined_review=service.prepare([scan(combined)],'nr-mfg','install',visual_settings=settings | {'mfg_multiplier':6})
for component in provider.PRODUCTION_RUNTIMES:
    assert combined_release[component]['sha256'] in combined_review['rows'][0]['detail']
mfg_only=game('Bridge MFG Only');(mfg_only/'nvngx_dlssg.dll').write_bytes(fixtures.pe());mfg_original=files(mfg_only)
mfg_review=service.prepare([scan(mfg_only)],'mfg-only','install',visual_settings=settings | {'nr_runtime':''})
assert mfg_review['rows'] and not mfg_review['blocked'],mfg_review
run(mfg_review)
assert not (mfg_only/'nvngx_dlssnr.dll').exists()
import configparser
mfg_ini=configparser.ConfigParser();mfg_ini.read(mfg_only/'OptiScaler.ini')
assert mfg_ini['DlssNr'].getboolean('Enabled') is False
assert 'AdaMfgUnlock=true' in (mfg_only/'OptiScaler.ini').read_text()
assert baseline(mfg_only)['feature_mode']=='mfg-only'
run(service.prepare([scan(mfg_only)],'mfg-only','uninstall',visual_settings=settings))
assert files(mfg_only)==mfg_original
checks.append('combined bridge MFG-only install needs no NR model, disables NR, and restores exactly')
nr_subset=game('Supported NR Subset');nr_subset_before=files(nr_subset)
subset_settings=settings | {'prefer_bundled_nr_only':True}
run(service.prepare([scan(nr_subset)],'nr-only','install',visual_settings=subset_settings))
subset_ini=configparser.ConfigParser();subset_ini.read(nr_subset/'OptiScaler.ini')
assert baseline(nr_subset)['feature_mode']=='nr-only'
assert baseline(nr_subset)['archive']['release']['variant']=='nr-mfg-bridge'
assert subset_ini['DlssNr'].getboolean('Enabled') is True
assert subset_ini['DLSSG'].getboolean('AdaMfgUnlock') is False
assert subset_ini['DLSSG'].getboolean('AdaBlackwellKernels') is False
assert not baseline(nr_subset)['mfg_provider']['enabled']
assert baseline(nr_subset)['compatibility_policy']['mfg_route']=='disabled-nr-only'
run(service.prepare([scan(nr_subset)],'nr-only','uninstall',visual_settings=subset_settings))
assert files(nr_subset)==nr_subset_before
checks.append('supported NR-only subset gets the helper-compatible bridge with MFG unlock disabled and exact restore')
discarded=game('Discarded Review');discarded_before=files(discarded)
prepared=host.prepare({'rows':[scan(discarded)],'mode':'nr-only','operation':'install','settings':subset_settings,'save_defaults':False})
token=prepared['token'];assert token in host.reviews
active={'cancel_event':__import__('threading').Event()};host.running['active-write']=active
host.discard_operation({'tokens':[token,'active-write','missing-token']})
assert token not in host.reviews and host.running['active-write'] is active
assert not active['cancel_event'].is_set() and files(discarded)==discarded_before
host.running.pop('active-write')
checks.append('dismissing a review releases its payload without touching games or active operations')
from unittest.mock import patch as measure_calls
batch_a=game('Batch A');batch_b=game('Batch B');batch_blocked=game('Batch Blocked')
for folder in (batch_a,batch_b):(folder/'nvngx_dlssg.dll').write_bytes(fixtures.pe())
factory=engine_bridge.module;model_reads=[]
def observed_factory(*a,**kw):
    e=factory(*a,**kw);load=e.load_user_nr_runtime
    def measured(*a,**kw):
        model_reads.append(1);return load(*a,**kw)
    e.load_user_nr_runtime=measured;return e
blocked_row=scan(batch_blocked);blocked_row['blocked']='Anti-cheat detected'
with measure_calls.object(engine_bridge,'module',side_effect=observed_factory), measure_calls.object(engine_bridge,'payload',wraps=engine_bridge.payload) as verify:
    batch=service.prepare([scan(batch_a),scan(batch_b),blocked_row],'nr-mfg','install',visual_settings=settings)
    assert len(batch['rows'])==2 and len(batch['blocked'])==1,batch
    assert verify.call_count==1 and len(model_reads)==1,(verify.call_count,len(model_reads))
run(batch,allow_blocked=True)
for folder in (batch_a,batch_b):
    assert baseline(folder)['feature_mode']=='nr-mfg'
    assert (folder/'nvngx_dlssnr.dll').read_bytes()==model.read_bytes()
checks.append('batch extracts/verifies one exact package and reads one NR model for two targets; blocked target never reaches payload work')
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
# A newer bundled loader must remain opt-in for an already pinned recipe.
updated_archive=root/'updated-combined.zip'
with zipfile.ZipFile(combined_archive) as source,zipfile.ZipFile(updated_archive,'w') as target:
    for member in source.infolist():
        data=source.read(member)
        if member.filename.endswith('/OptiScaler.dll'):data+=b'updated bridge'
        target.writestr(member,data)
updated_release=combined_release | {'sha256':hashlib.sha256(updated_archive.read_bytes()).hexdigest(),
                                    'release_size':updated_archive.stat().st_size}
provider.bundled_bridge=lambda selection='latest':(dict(updated_release,selected_source=selection),updated_archive)
combined_ini=combined_ini.replace('WorkingScale=0.65','WorkingScale=0.5')+'\n; keep this game tuning\n'
(combined/'OptiScaler.ini').write_text(combined_ini)
run(service.prepare([scan(combined)],'nr-mfg','repair',visual_settings=settings | {'skynizz_version':'v9.9.9'}))
assert baseline(combined)['archive']['release']['sha256']==combined_release['sha256']
for component in provider.PRODUCTION_RUNTIMES:
    assert baseline(combined)['archive']['release'][component]==combined_release[component]
upgrade_settings=settings | {'upgrade_skynizz_bridge':True,'nr_runtime':str(root/'missing-global-model.dll'),
                            'mfg_multiplier':2,'nr_preset':0}
review=service.prepare([scan(combined)],'nr-mfg','repair',visual_settings=upgrade_settings)
assert review['title']=='Update NR + MFG bridge' and updated_release['sha256'] in review['rows'][0]['detail']
assert (combined/'dxgi.dll').read_bytes()==fixtures.pe(),'review changed the loader'
run(review)
assert baseline(combined)['archive']['release']['sha256']==updated_release['sha256']
assert (combined/'dxgi.dll').read_bytes()==fixtures.pe()+b'updated bridge'
assert (combined/'nvngx_dlssnr.dll').read_bytes()==model.read_bytes()
assert (combined/'OptiScaler.ini').read_text()==combined_ini,'bridge upgrade reset tuning or MFG count'
for component in provider.PRODUCTION_RUNTIMES:
    assert baseline(combined)['archive']['release'][component]==combined_release[component]
checks.append('explicit bridge upgrade adopts the new loader while preserving exact model, game tuning, MFG count and runtime pins')
run(service.prepare([scan(combined)],'nr-mfg','uninstall',visual_settings=settings));assert files(combined)==combined_before
checks.append('combined NR+MFG uses one loader, production SR/RR/FG and private Streamline; pinned repair/restore preserve ownership')
review=service.prepare([scan(combined)],'nr-mfg','repair',visual_settings=upgrade_settings)
assert not review['rows'] and 'before updating' in review['blocked'][0]['reason']
assert files(combined)==combined_before
for mode,operation,values in [('nr-only','repair',upgrade_settings),('nr-mfg','install',upgrade_settings)]:
    try:service.prepare([scan(combined)],mode,operation,visual_settings=values)
    except Exception:pass
    else:raise AssertionError('unsafe bridge update selection accepted')
try:engine_bridge.prepare(service.config,[scan(combined)],'nr-mfg','repair',upgrade_settings | {'apply_requested_presets':True})
except Exception:pass
else:raise AssertionError('bridge update accepted preset reset')
checks.append('bridge update refuses unowned installs, mode changes and preset resets before writes')
inzoi=game('inZOI');(inzoi/'Game.exe').rename(inzoi/'inZOI-Win64-Shipping.exe')
(inzoi/'nvngx_dlssg.dll').write_bytes(fixtures.pe());inzoi_before=files(inzoi)
review=service.prepare([scan(inzoi)],'nr-mfg','install',visual_settings=settings)
assert 'overlay disabled for inZOI startup' in review['rows'][0]['detail']
run(review)
ini=inzoi/'OptiScaler.ini'
assert 'OverlayMenu=false' in ini.read_text() and 'Enabled=true' in ini.read_text()
ini.write_text(ini.read_text().replace('OverlayMenu=false','OverlayMenu=true').replace('CacheInterval=1','CacheInterval=5'))
run(service.prepare([scan(inzoi)],'nr-mfg','repair',visual_settings=settings))
assert 'OverlayMenu=false' in ini.read_text() and 'CacheInterval=5' in ini.read_text()
assert 'AdaMfgUnlock=true' in ini.read_text() and 'PreSr=true' in ini.read_text()
run(service.prepare([scan(inzoi)],'nr-mfg','reset',visual_settings=settings))
assert 'OverlayMenu=false' in ini.read_text()
run(service.prepare([scan(inzoi)],'nr-mfg','uninstall',visual_settings=settings));assert files(inzoi)==inzoi_before
checks.append('inZOI disables the startup overlay through install/repair/reset while retaining NR/MFG and restoring original files')
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
# Exercise the external MFG recipe through the same review/execute/restore path.
# This verifies ownership and rollback; these fixture DLLs provide no GPU proof.
import ada_mfg_provider
external=game('ExternalMfg');(external/'nvngx_dlssg.dll').write_bytes(fixtures.pe())
(external/'ReShade.ini').write_text('[Other]\nKeep=1\n')
external_before=files(external)
external_payload={'ReShade64.dll':fixtures.pe(), 'renodx-mfgunlock.addon64':fixtures.pe(),
                  'OptiScaler/licenses/MFG-Unlock-LICENSE.txt':b'fixture license'}
ada_mfg_provider.load_payload=lambda config,record:dict(external_payload)
external_settings=settings | {'mfg_provider':'mfg-unlock','mfg_multiplier':4,'nr_preset':2}
review=service.prepare([scan(external)],'nr-mfg','install',visual_settings=external_settings)
assert files(external)==external_before
assert 'MFG Unlock 1.4.4' in review['rows'][0]['detail']
# Native DLL preparation loads another engine after the provider review. It
# must not replace the pending operation's provider/configuration context.
later_engine=module(service.config,'y4my')
run(review);record=baseline(external)
assert record['mfg_provider']['ownership']=='managed-addon'
assert scan(external)['mfg_multiplier']==4 and scan(external)['mfg_provider']=='mfg-unlock'
assert record['compatibility_policy']['mfg_route']=='native-ada-mfg-unlock-addon'
ini=(external/'OptiScaler.ini').read_text()
for value in ('AdaMfgUnlock=false','AdaBlackwellKernels=false','OverrideInterpolationCount=auto','LoadReShade=true','Preset=2'):
    assert value in ini,value
reshade=external/'ReShade.ini'
assert 'ForceMultiplier=4' in reshade.read_text() and 'DynamicMFG=0' in reshade.read_text()
tuned=reshade.read_text().replace('ForceMultiplier=4','ForceMultiplier=3')+'\n; user preset\n'
reshade.write_text(tuned)
run(service.prepare([scan(external)],'nr-mfg','repair',visual_settings=settings | {'mfg_provider':'integrated'}))
assert reshade.read_text()==tuned,'repair reset the addon preset or changed MFG owner'
assert scan(external)['mfg_multiplier']==3
assert baseline(external)['mfg_provider']['version']=='1.4.4'
external_ini=(external/'OptiScaler.ini').read_text()
run(service.prepare([scan(external)],'nr-mfg','repair',visual_settings=upgrade_settings | {'mfg_provider':'integrated'}))
assert baseline(external)['archive']['release']['mfg_component']==record['archive']['release']['mfg_component']
assert (external/'OptiScaler.ini').read_text()==external_ini and reshade.read_text()==tuned
assert scan(external)['mfg_provider']=='mfg-unlock' and scan(external)['mfg_multiplier']==3
run(service.prepare([scan(external)],'nr-mfg','reset',visual_settings=settings | {'mfg_multiplier':4}))
assert 'AdaMfgUnlock=false' in (external/'OptiScaler.ini').read_text()
assert 'ForceMultiplier=4' in reshade.read_text() and '; user preset' in reshade.read_text()
run(service.prepare([scan(external)],'nr-mfg','uninstall',visual_settings=settings))
assert files(external)==external_before
checks.append('external MFG recipe pins addon/host, disables internal unlock, preserves tuning on repair/reset and restores original files')
collision=game('ExternalCollision');(collision/'nvngx_dlssg.dll').write_bytes(fixtures.pe())
(collision/'ReShade64.dll').write_bytes(b'unmanaged host');collision_before=files(collision)
review=service.prepare([scan(collision)],'nr-mfg','install',visual_settings=external_settings)
assert not review['rows'] and 'Unmanaged MFG' in review['blocked'][0]['reason']
assert files(collision)==collision_before
checks.append('unmanaged addon host refuses before mutation')
external_fail=game('ExternalFailure');(external_fail/'nvngx_dlssg.dll').write_bytes(fixtures.pe())
fail_before=files(external_fail)
review=service.prepare([scan(external_fail)],'nr-mfg','install',visual_settings=external_settings)
e=review['engine'];original_write=e.atomic_write;failed=[False]
def fail_addon(path,*args,**kwargs):
    if Path(path).name=='renodx-mfgunlock.addon64' and not failed[0]:
        failed[0]=True;raise OSError('injected addon failure')
    return original_write(path,*args,**kwargs)
e.atomic_write=fail_addon
try:service.execute(review)
except Exception:pass
else:raise AssertionError('addon write failure was ignored')
assert files(external_fail)==fail_before
checks.append('external addon failure rolls back the complete recipe')
local=game('LocalModel');(local/'nvngx_dlssnr.dll').write_bytes(fixtures.pe()+b'1'*(32*1024**2))
local_before=files(local);run(prepare(local,values={'nr_runtime':''}))
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
            self.assertEqual(receipt['count'], 27)
            print('PASS: ' + '; '.join(receipt['checks']))


if __name__ == '__main__':
    unittest.main()
