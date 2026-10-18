"""Bulk changes through the real Windows review token and file adapters."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKER = r'''
import contextlib,hashlib,importlib.util,json,os,sys
from pathlib import Path
repo=Path(sys.argv[1]);sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
out=sys.stdout
import rtxforge_win_host as host
sys.stdout=out
import engine_bridge,feeder_provider as feeder,transactions as t,win_features,global_controls
spec=importlib.util.spec_from_file_location('feeder_fixtures',repo/'tests/test_feeder_provider.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
case=fixtures.FeederTest();case.setUp();case.settings['nr_on_launch']=True
try:
    e=engine_bridge.module(host.service.config)
    engine_bridge.module=lambda *args,**kwargs:e
    e._running_processes_under_root=lambda root:[]
    case.e=e
    row=case.game(installed=True)
    adoption=feeder.prepare(host.service.config,[row],'nr-only','install',case.settings,e)
    assert adoption['plans'] and not adoption['blocked'],adoption['blocked']
    feeder.execute(adoption)
    native=case.root/'Native';native.mkdir()
    (native/'Game.exe').write_bytes(fixtures.pe(b'game'))
    (native/'winhttp.dll').write_bytes(fixtures.pe(b'loader'))
    (native/'nvngx_dlssnr.dll').write_bytes(fixtures.pe(b'NR'))
    ini=b'[DlssNr]\nEnabled=true\nIntensity=1.25\nLocalTone=0.75\n[DLSSG]\nOverrideInterpolationCount=3\n[Keep]\nCustom=untouched\n'
    (native/'OptiScaler.ini').write_bytes(ini)
    files={p.name:t.digest(p) for p in native.iterdir() if p.name!='Game.exe'}
    current={'archive':{'family':'skynizz'},'provider_id':'skynizz','proxy':'winhttp.dll','feature_mode':'nr-mfg','installed_hashes':files}
    baseline={'schema':e.ENGINE_SCHEMA,'status':'active','name':'Native','target_dir':str(native),'exe':str(native/'Game.exe'),'current':current,'originals':{'untouched':True}}
    baseline_path=e.state_dir_for(native)/'baseline.json'
    t.atomic_file(baseline_path,json.dumps(baseline).encode(),0o600)
    metadata={'provider':{'id':'skynizz'},'feature_mode':'nr-mfg','proxy':'winhttp.dll','files':files}
    (native/'.rtxforge-install.json').write_text(json.dumps(metadata),encoding='utf-8')
    key=hashlib.sha256(os.path.normcase(str(native/'Game.exe')).encode()).hexdigest()
    preset=host.STATE/'runtime-presets'/(key+'.json')
    saved={'schema':1,'row':{'game':str(native),'exe':'Game.exe','name':'Native'},'recipe':'a'*64,'changes':{'enabled':1,'multiplier':4,'intensity':1.25,'tone':.75}}
    t.atomic_file(preset,json.dumps(saved).encode(),0o600)
    def before():
        return {str(p):p.read_bytes() for base in [native,Path(row['game']),e.STATE_ROOT/'targets',e.STATE_ROOT/'feeder-targets',host.STATE/'runtime-presets'] for p in base.rglob('*') if p.is_file()}
    original=before()
    checked=host.METHODS['global_review']({'nr':False,'mfg':0})
    assert len(checked['items'])==2 and not checked['blocked'],checked
    assert before()==original,'review changed files'
    result=host.METHODS['run']({'token':checked['token']})
    assert '2 games' in result['message'],result
    assert 'Enabled=false' in (native/'OptiScaler.ini').read_text()
    assert 'OverrideInterpolationCount=0' in (native/'OptiScaler.ini').read_text()
    assert 'Intensity=1.25' in (native/'OptiScaler.ini').read_text() and 'Custom=untouched' in (native/'OptiScaler.ini').read_text()
    assert not feeder.configured(Path(row['game']))['nr_enabled']
    assert 'NRLocalTone=2' in (Path(row['game'])/'ReShade.ini').read_text()
    assert json.loads(preset.read_text())['changes']=={'enabled':0,'multiplier':0,'intensity':1.25,'tone':.75}
    assert json.loads(baseline_path.read_text())['originals']==baseline['originals']
    receipt=list((e.STATE_ROOT/'desktop-operations').glob('*/session.json'))[-1]
    backups=json.loads(receipt.read_text());assert backups['status']=='complete'
    assert any(Path(item['backup']).read_bytes()==ini for item in backups['entries'])
    try:host.METHODS['run']({'token':checked['token']});raise AssertionError('token replay succeeded')
    except t.Refusal:pass
    checked=host.METHODS['global_review']({'nr':True,'mfg':4})
    stable=before();(native/'OptiScaler.ini').write_bytes((native/'OptiScaler.ini').read_bytes()+b'\n; external edit\n')
    drift=before()
    try:host.METHODS['run']({'token':checked['token']});raise AssertionError('drift accepted')
    except t.Refusal:pass
    assert before()==drift,'drift refusal made partial writes'
    checked=host.METHODS['global_review']({'nr':True})
    e._running_processes_under_root=lambda root:[123]
    current=before()
    try:host.METHODS['run']({'token':checked['token']});raise AssertionError('running game accepted')
    except t.Refusal:pass
    assert before()==current
    blocked=host.METHODS['global_review']({'nr':True})
    assert len(blocked['blocked'])==2 and not blocked['items']
    e._running_processes_under_root=lambda root:[]
    checked=host.METHODS['global_review']({'nr':True})
    marker=native/'EasyAntiCheat';marker.mkdir()
    current=before()
    try:host.METHODS['run']({'token':checked['token']});raise AssertionError('new anti-cheat accepted')
    except t.Refusal:pass
    assert before()==current;marker.rmdir()
    assert global_controls.anti_cheat(e,native) is None
    hidden=native/'Data';hidden.mkdir();(hidden/'Start_Protected_Game.exe').write_bytes(b'marker')
    assert global_controls.anti_cheat(e,native)==hidden/'Start_Protected_Game.exe'
    (hidden/'Start_Protected_Game.exe').unlink();hidden.rmdir()
    ignored=native/'_optiscaler_backups';ignored.mkdir();(ignored/'start_protected_game.exe').write_bytes(b'backup')
    assert global_controls.anti_cheat(e,native) is None
    (ignored/'start_protected_game.exe').unlink();ignored.rmdir()
    checked=host.METHODS['global_review']({'nr':True})
    previous=before();write=t.atomic_file;failed=[False]
    def injected(path,*args,**kwargs):
        if Path(path)==native/'OptiScaler.ini' and not failed[0]:
            failed[0]=True;raise OSError('injected bulk write failure')
        return write(path,*args,**kwargs)
    t.atomic_file=injected
    try:
        try:host.METHODS['run']({'token':checked['token']});raise AssertionError('write failure ignored')
        except t.Refusal as error:assert 'Updated 0 games' in str(error),str(error)
    finally:t.atomic_file=write
    assert failed[0] and before()==previous,'failed game was not restored exactly'
    from unittest.mock import patch
    # Already-applied controls need no expensive process, evidence or DLL scan.
    with patch.object(global_controls,'anti_cheat',side_effect=AssertionError('no-op scanned game')), patch.object(t,'digest',side_effect=AssertionError('no-op hashed runtime')):
        noop=host.METHODS['global_review']({'nr':False,'mfg':0})
    assert not noop['items'] and not noop['blocked'] and len(noop['skipped'])==2,noop
    assert all('Already set' in item['detail'] for item in noop['skipped'])
    host.METHODS['discard']({'token':noop['token']})
    for label,exists in [('Old MFG',True),('Missing Game',False)]:
        folder=case.root/label
        if exists:folder.mkdir();(folder/'Game.exe').write_bytes(fixtures.pe(b'old game'))
        old={'schema':e.ENGINE_SCHEMA,'status':'active','name':label,'target_dir':str(folder),'exe':str(folder/'Game.exe'),
             'current':{'provider_id':'dlss-unlocked','feature_mode':'mfg-only'}}
        t.atomic_file(e.state_dir_for(folder)/'baseline.json',json.dumps(old).encode(),0o600)
    skipped=host.METHODS['global_review']({'nr':False})
    assert not skipped['items'] and not skipped['blocked'],skipped
    reasons={item['title']:item['detail'] for item in skipped['skipped']}
    assert reasons['Old MFG']=='NR is not installed in this package.'
    assert reasons['Missing Game']=='Game no longer found at this location.'
    host.METHODS['discard']({'token':skipped['token']})
    # Both native and Feeder payloads stay bound to review-time file hashes.
    checked=host.METHODS['global_review']({'nr':True})
    model=Path(row['game'])/'nvngx_dlssnr.dll';original_model=model.read_bytes()
    model.write_bytes(original_model+b'drift');drift=before()
    try:host.METHODS['run']({'token':checked['token']});raise AssertionError('Feeder model drift accepted')
    except t.Refusal:pass
    assert before()==drift
    model.write_bytes(original_model)
    for params in ({},{'nr':1},{'mfg':True},{'mfg':1},{'nr':False,'unknown':1}):
        try:global_controls.changes(params);raise AssertionError('invalid controls accepted')
        except t.Refusal:pass
    print('PASS: real host NR/MFG bulk review/execute, Feeder NR-only, field preservation, backups, one-shot tokens, drift/running/anti-cheat refusals.')
finally:case.doCleanups()
'''


@unittest.skipUnless(os.name == 'nt', 'Windows host adapters')
class GlobalControlsTest(unittest.TestCase):
    def test_bulk_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root/'Steam').mkdir()
            env = dict(os.environ, RTXFORGE_ROOT=str(ROOT), RTXFORGE_STATE_ROOT=str(root/'state'),
                       RTXFORGE_DLSS_UNLOCKED_STATE=str(root/'engine-state'), LOCALAPPDATA=str(root/'appdata'),
                       RTXFORGE_STEAM_ROOTS=str(root/'Steam'), PYTHONUTF8='1')
            result = subprocess.run([sys.executable,'-X','utf8','-c',WORKER,str(ROOT)],env=env,
                                    capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stderr[-8000:]+result.stdout[-2000:])
            print(result.stdout.strip().splitlines()[-1])


if __name__ == '__main__': unittest.main()
