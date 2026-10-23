"""Native-overlay update ownership, drift guards and exact-file rollback."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKER = r'''
import copy,importlib.util,json,sys
from pathlib import Path
from unittest.mock import patch
repo=Path(sys.argv[1]);sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
out=sys.stdout
import companion_controls
companion_controls.Controls._start_watcher=lambda self:None
import rtxforge_win_host as h
sys.stdout=out
import engine_bridge,transactions as t,overlay_packages as overlays,global_controls as bulk,cross_os
spec=importlib.util.spec_from_file_location('fixtures',repo/'tests/test_skynizz_provider.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
e=engine_bridge.module(h.service.config)
e._running_processes_under_root=lambda root:[]
root=h.LOCAL/'game';root.mkdir(parents=True)
(root/'Game.exe').write_bytes(fixtures.pe())
(root/'winhttp.dll').write_bytes(fixtures.pe()+b'old')
(root/'nvngx.dll_dlssnr.dll').write_bytes(fixtures.pe())
(root/'OptiScaler.ini').write_bytes(b'[DlssNr]\nEnabled=false\nWorkingScale=0.5\n[DLSSG]\nOverrideInterpolationCount=3\n')
archive=h.LOCAL/'candidate.zip'
release=fixtures.bridge_fixture(archive)|{'panel_renderer':'in-game','panel_candidate':True}
overlays.provider.bundled_bridge=lambda:(release,archive)
owned={p.name:t.digest(p) for p in root.iterdir() if p.name!='Game.exe'}
record={'schema':e.ENGINE_SCHEMA,'status':'active','target_dir':str(root),'exe':str(root/'Game.exe'),'name':'Owned',
        'originals':{'restore-boundary':'keep'},'cross_os_revision':'old',
        'current':{'provider_id':'skynizz','feature_mode':'nr-mfg','proxy':'winhttp.dll','installed_hashes':owned,
                   'archive':{'release':release|{'sha256':'f'*64}}}}
baseline=e.baseline_path(root);t.atomic_file(baseline,json.dumps(record).encode(),0o600)
marker=root/cross_os.MARKER
marker.write_text(json.dumps({'provider':{'id':'skynizz'},'proxy':'winhttp.dll','files':owned,'revision':'old','feature_mode':'nr-mfg'}))
def files():return {str(p):p.read_bytes() for base in [root,e.STATE_ROOT/'targets'] for p in base.rglob('*') if p.is_file()}
before=files()
review=overlays.prepare(e,h.LOCAL/'state')
assert len(review['plans'])==1 and not review['blocked'],review['blocked']
assert files()==before,'review wrote game/state'
bulk.execute(review)
after=files();assert (root/'winhttp.dll').read_bytes()==fixtures.pe()
assert (root/'OptiScaler.ini').read_bytes()==before[str(root/'OptiScaler.ini')]
updated=t.read_json(baseline);assert updated['originals']==record['originals']
assert updated['current']['feature_mode']=='nr-mfg'
assert t.read_json(marker)['files']==updated['current']['installed_hashes']
assert not overlays.prepare(e,h.LOCAL/'state')['plans'],'duplicate update'
# Ownership drift is refused before writes.
(root/'winhttp.dll').write_bytes(fixtures.pe()+b'foreign')
review=overlays.prepare(e,h.LOCAL/'state');assert not review['plans'] and review['blocked']
for name,data in before.items():t.atomic_file(Path(name),data,0o600)
review=overlays.prepare(e,h.LOCAL/'state')
e._running_processes_under_root=lambda root:[1]
try:bulk.execute(review);raise AssertionError('running game accepted')
except t.Refusal:pass
assert files()==before
e._running_processes_under_root=lambda root:[]
review=overlays.prepare(e,h.LOCAL/'state');write=t.atomic_file;failed=[False]
def broken(path,data,*a,**kw):
    if Path(path)==marker and not failed[0]:failed[0]=True;raise OSError('injected write failure')
    return write(path,data,*a,**kw)
with patch.object(t,'atomic_file',broken):
    try:bulk.execute(review);raise AssertionError('write failure ignored')
    except t.Refusal:pass
assert failed[0] and files()==before,'rollback did not restore exact pre-update files'
import feeder_provider as feeder,overlay_settings
spec=importlib.util.spec_from_file_location('feeder_fixtures',repo/'tests/test_feeder_provider.py')
ff=importlib.util.module_from_spec(spec);spec.loader.exec_module(ff)
case=ff.FeederTest();case.setUp();case.e=e
try:
    row=case.game('Feeder',installed=True)
    def panel(revision):
        result={}
        for name in feeder.PANELS:
            raw=ff.pe(name.encode()+revision);cache=e.STATE_ROOT/'feeder-cache'/t.sha(raw)
            t.atomic_file(cache,raw,0o600);result[name]={'path':str(cache),'sha256':t.sha(raw)}
        return result
    old=panel(b'old');new=panel(b'new')
    with patch.object(feeder,'panel',return_value=old):
        feeder.execute(feeder.prepare(h.service.config,[row],'nr-only','install',case.settings,e))
    game=Path(row['game']);original=feeder.state(e,game)['originals']
    model=(game/'nvngx_dlssnr.dll').read_bytes();ini=t.ini((game/'ReShade.ini').read_text())
    tuning=ini['RenoDX.DLSS5']['NRResolutionScale'];native_before=files()
    params=overlay_settings.options({})|{'reshade_ui':False,'target_games':[str(game)],
        'game_overlay_settings':{str(game):{'overlay_welcome':False,'panel_hotkey':'F8'}}}
    with patch.object(feeder,'panel',return_value=new):
        review=overlays.prepare(e,h.LOCAL/'state',params)
        assert len(review['plans'])==1 and not review['blocked'],review
        assert 'Welcome message: Off' in review['plans'][0]['note'] and 'shortcut: F8' in review['plans'][0]['note']
        assert (game/feeder.PANELS[0]).read_bytes()==Path(old[feeder.PANELS[0]]['path']).read_bytes(),'review wrote a panel'
        bulk.execute(review)
    assert (game/feeder.PANELS[0]).read_bytes()==Path(new[feeder.PANELS[0]]['path']).read_bytes()
    assert (game/'nvngx_dlssnr.dll').read_bytes()==model and feeder.state(e,game)['originals']==original
    updated=t.ini((game/'ReShade.ini').read_text());assert updated['INPUT']['KeyOverlay']=='0,0,0,0'
    assert updated['RenoDX.DLSS5']['NRResolutionScale']==tuning
    assert files()==native_before,'scoped Feeder update changed another game'
    try:overlays.prepare(e,h.LOCAL/'state',params|{'target_games':[]});raise AssertionError('empty scope widened')
    except t.Refusal:pass
finally:case.doCleanups()
print('PASS: native-overlay review is read-only; loader, state and marker update atomically; tuning/originals preserved; idempotence, drift/running guards and exact rollback.')
'''


@unittest.skipUnless(os.name == 'nt', 'Windows host adapters')
class OverlayPackageTest(unittest.TestCase):
    def test_review_apply_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'Steam').mkdir()
            env=dict(os.environ,RTXFORGE_ROOT=str(ROOT),RTXFORGE_STATE_ROOT=str(root/'state'),
                     RTXFORGE_DLSS_UNLOCKED_STATE=str(root/'engine-state'),LOCALAPPDATA=str(root/'appdata'),
                     RTXFORGE_STEAM_ROOTS=str(root/'Steam'),PYTHONUTF8='1')
            result=subprocess.run([sys.executable,'-X','utf8','-c',WORKER,str(ROOT)],env=env,capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stderr[-6000:]+result.stdout[-2000:])
            print(result.stdout.strip().splitlines()[-1])


if __name__ == '__main__':unittest.main()
