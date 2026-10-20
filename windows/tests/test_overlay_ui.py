"""Native and Feeder UI settings through actual Windows review/execute tokens."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKER = r'''
import copy,hashlib,importlib.util,json,sys
from pathlib import Path
repo=Path(sys.argv[1]);sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
out=sys.stdout
import companion_controls
companion_controls.Controls._start_watcher=lambda self:None
import rtxforge_win_host as h
sys.stdout=out
import engine_bridge,feeder_provider as feeder,transactions as t,win_features,overlay_ui,global_controls,cross_os
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('fixtures',repo/'tests/test_feeder_provider.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
case=fixtures.FeederTest();case.setUp()
try:
    e=engine_bridge.module(h.service.config);engine_bridge.module=lambda *a,**k:e
    e._running_processes_under_root=lambda root:[];case.e=e
    row=case.game(installed=True)
    feeder.execute(feeder.prepare(h.service.config,[row],'nr-only','install',case.settings,e))
    f=Path(row['game']);fini=f/'ReShade.ini'
    fini.write_text(fini.read_text()+'\n[INPUT]\nKeyOverlay=45,1,0,0\nGamepadNavigation=1\n[OVERLAY]\nTutorialProgress=4\n')
    native=case.root/'Native';native.mkdir()
    (native/'Game.exe').write_bytes(fixtures.pe(b'game'))
    (native/'winhttp.dll').write_bytes(fixtures.pe(b'loader'))
    (native/'nvngx_dlssnr.dll').write_bytes(fixtures.pe(b'nr'))
    ini=b'[Menu]\nOverlayMenu=false\nShortcutKey=0x77\nDisableSplash=true\n[DlssNr]\nEnabled=false\nWorkingScale=0.65\n[DLSSG]\nOverrideInterpolationCount=3\n'
    (native/'OptiScaler.ini').write_bytes(ini)
    hashes={p.name:t.digest(p) for p in native.iterdir() if p.name!='Game.exe'}
    current={'archive':{'family':'skynizz'},'provider_id':'skynizz','proxy':'winhttp.dll','feature_mode':'nr-mfg','installed_hashes':hashes}
    baseline={'schema':e.ENGINE_SCHEMA,'status':'active','name':'Native','target_dir':str(native),'exe':str(native/'Game.exe'),'current':current,'originals':{'preserve':True},'cross_os_revision':'fixture-revision'}
    bp=e.baseline_path(native);t.atomic_file(bp,json.dumps(baseline).encode(),0o600)
    marker={'provider':{'id':'skynizz'},'proxy':'winhttp.dll','feature_mode':'nr-mfg','files':hashes,'revision':'fixture-revision'}
    (native/'.rtxforge-install.json').write_text(json.dumps(marker))
    shared=cross_os.shared_state(native)/'baseline.json'
    t.atomic_file(shared,json.dumps(cross_os.portable(baseline,e.state_dir_for(native),native)).encode(),0o600)
    def files():
        return {str(p):p.read_bytes() for folder in [native,f,e.STATE_ROOT/'targets',e.STATE_ROOT/'feeder-targets'] for p in folder.rglob('*') if p.is_file()}
    before=files()
    settings={'optiscaler_ui':False,'optiscaler_intro':True,'reshade_ui':False,'reshade_intro':False,'optiscaler_hotkey':'F8'}
    checked=h.METHODS['overlay_ui_review'](settings)
    assert len(checked['items'])==2 and not checked['blocked'],checked
    assert before==files(),'review changed files'
    result=h.METHODS['run']({'token':checked['token']});assert '2 games' in result['message']
    c=t.ini((native/'OptiScaler.ini').read_text());assert c['Menu']['ShortcutKey']=='0' and not c['Menu'].getboolean('DisableSplash')
    assert c['DlssNr']['Enabled']=='false' and c['DlssNr']['WorkingScale']=='0.65' and c['DLSSG']['OverrideInterpolationCount']=='3' and c['Menu']['OverlayMenu']=='false'
    c=t.ini(fini.read_text());assert c['INPUT']['KeyOverlay']=='0,0,0,0' and c['INPUT']['GamepadNavigation']=='0' and c['OVERLAY']['TutorialProgress']=='4' and c['RenoDX.DLSS5']['UiWelcomed']=='1'
    for path,old in before.items():
        if Path(path).suffix.casefold() in ('.dll','.addon64','.fx','.fxh'):assert Path(path).read_bytes()==old,path
    assert json.loads(bp.read_text())['originals']==baseline['originals']
    updated=json.loads(bp.read_text());portable=json.loads(shared.read_text());metadata=json.loads((native/'.rtxforge-install.json').read_text())
    assert updated['cross_os_revision']==portable['cross_os_revision']==metadata['revision']!='fixture-revision'
    assert portable['current']['installed_hashes']==metadata['files']==updated['current']['installed_hashes']
    stable=files()
    with patch.object(t,'digest',side_effect=AssertionError('unchanged review read large payloads')):
        noop=h.METHODS['overlay_ui_review'](settings)
    assert not noop['items'] and len(noop['skipped'])==2,noop
    assert stable==files(),'unchanged review wrote metadata'
    try:h.METHODS['run']({'token':checked['token']});raise AssertionError('token reused')
    except t.Refusal:pass
    settings.update(optiscaler_ui=True,optiscaler_intro=False,reshade_ui=True,reshade_intro=True)
    checked=h.METHODS['overlay_ui_review'](settings);h.METHODS['run']({'token':checked['token']})
    c=t.ini(fini.read_text());assert c['INPUT']['KeyOverlay']=='45,1,0,0' and c['INPUT']['GamepadNavigation']=='1' and c['OVERLAY']['TutorialProgress']=='0' and c['RenoDX.DLSS5']['UiWelcomed']=='0'
    assert 'ShortcutKey=0x77' in (native/'OptiScaler.ini').read_text()
    checked=h.METHODS['overlay_ui_review'](dict(settings,reshade_ui=False))
    fini.write_bytes(fini.read_bytes()+b'\n; outside edit\n');drift=files()
    try:h.METHODS['run']({'token':checked['token']});raise AssertionError('drift accepted')
    except t.Refusal:pass
    assert files()==drift
    e._running_processes_under_root=lambda root:[123]
    checked=h.METHODS['overlay_ui_review'](settings);assert not checked['items'] and len(checked['blocked'])==2
    e._running_processes_under_root=lambda root:[]
    checked=h.METHODS['overlay_ui_review'](dict(settings,optiscaler_ui=False))
    stable=files();write=t.atomic_file;failed=[False]
    def broken(path,data,*a,**kw):
        if Path(path).name=='OptiScaler.ini' and not failed[0]:failed[0]=True;raise OSError('injected UI failure')
        return write(path,data,*a,**kw)
    with patch.object(t,'atomic_file',broken):
        try:h.METHODS['run']({'token':checked['token']});raise AssertionError('failure ignored')
        except t.Refusal:pass
    assert failed[0] and files()==stable,'transaction failed to restore exact files'
    # Ordinary Feeder repair applies UI options but preserves model/tuning and
    # the original restoration boundary, with the same runtime bytes.
    checked=feeder.prepare(h.service.config,[row],'nr-only','repair',case.settings|settings,e)
    assert not checked['blocked'],checked['blocked'];feeder.execute(checked)
    c=t.ini(fini.read_text());assert c['OVERLAY']['TutorialProgress']=='0' and c['RenoDX.DLSS5']['UiWelcomed']=='0'
    print('PASS: native/Feeder menu and welcome independence; real read-only review, one-shot apply, tuning/DLL/original preservation, restored custom key/gamepad, drift/running guards and rollback.')
finally:case.doCleanups()
'''


@unittest.skipUnless(os.name == 'nt', 'Windows host adapters')
class OverlayUiTest(unittest.TestCase):
    def test_review_apply_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'Steam').mkdir()
            env=dict(os.environ,RTXFORGE_ROOT=str(ROOT),RTXFORGE_STATE_ROOT=str(root/'state'),
                     RTXFORGE_DLSS_UNLOCKED_STATE=str(root/'engine-state'),LOCALAPPDATA=str(root/'appdata'),
                     RTXFORGE_STEAM_ROOTS=str(root/'Steam'),PYTHONUTF8='1')
            result=subprocess.run([sys.executable,'-X','utf8','-c',WORKER,str(ROOT)],env=env,capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stderr[-7000:]+result.stdout[-2500:])
            print(result.stdout.strip().splitlines()[-1])


if __name__ == '__main__':unittest.main()
