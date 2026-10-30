"""Native-overlay update ownership, drift guards and exact-file rollback."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKER = r'''
import copy,importlib.util,json,sys,os
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
        'originals':{name:{'existed':False} for name in owned},'managed_paths':list(owned),'cross_os_revision':'old',
        'current':{'provider_id':'skynizz','feature_mode':'nr-mfg','proxy':'winhttp.dll','installed_hashes':owned,
                   'archive':{'release':release|{'sha256':'f'*64}}}}
baseline=e.baseline_path(root);t.atomic_file(baseline,json.dumps(record).encode(),0o600)
marker=root/cross_os.MARKER
marker.write_text(json.dumps({'provider':{'id':'skynizz'},'proxy':'winhttp.dll','files':owned,'revision':'old','feature_mode':'nr-mfg'}))
def files():return {str(p):p.read_bytes() for base in [root,e.STATE_ROOT/'targets'] for p in base.rglob('*') if p.is_file()}
before=files()
# A prior cross-OS writer mislabeled a valid Skynizz recipe with the engine's
# default package. Shared and local recovery boundaries still agree exactly.
shared=cross_os.shared_state(root)/'baseline.json'
shared.parent.mkdir(parents=True)
portable=cross_os.portable(record,baseline.parent,root)
portable.update(cross_os_revision='other-os',cross_os_extras={'linux':{'launch_options':'preserve'}})
shared.write_text(json.dumps(portable))
stale=t.read_json(marker);stale.update(provider={'id':'dlss-unlocked'},schema=2,os='linux',shared_state=True,
                                     revision='other-os')
marker.write_text(json.dumps(stale))
drifted=files()
review=overlays.prepare(e,h.LOCAL/'state')
assert len(review['plans'])==1 and not review['blocked'],review['blocked']
assert files()==drifted,'ownership reconciliation mutated during review'
bulk.execute(review)
updated=t.read_json(baseline);published=t.read_json(shared);identity=t.read_json(marker)
assert identity['provider']['id']=='skynizz'
assert identity['revision']==updated['cross_os_revision']==published['cross_os_revision']
assert updated['cross_os_extras']==published['cross_os_extras']==portable['cross_os_extras']
assert updated['originals']==record['originals']
# Different restore ownership, recipe or shared inventory cannot be reconciled.
for field,value in [('originals',{}),('current',dict(portable['current'],provider_id='y4my'))]:
    for name,data in drifted.items():t.atomic_file(Path(name),data,0o600)
    changed=copy.deepcopy(portable);changed[field]=value;shared.write_text(json.dumps(changed))
    refused=overlays.prepare(e,h.LOCAL/'state')
    assert not refused['plans'] and refused['blocked'],field
# Do not classify stale locations as another installed MFG package, or include
# unselected package records in a scoped review.
absent=h.LOCAL/'old-game';absent_exe=absent/'Game.exe'
old_record=copy.deepcopy(record);old_record.update(target_dir=str(absent),exe=str(absent_exe),name='Old location')
old_record['current']['provider_id']='dlss-unlocked'
t.atomic_file(e.baseline_path(absent),json.dumps(old_record).encode(),0o600)
skipped=overlays.prepare(e,h.LOCAL/'state')['skipped']
assert all(x['title']!='Old location' for x in skipped),'ghost location leaked into review'
scoped=overlays.prepare(e,h.LOCAL/'state',{'target_games':[str(root)]})
assert all(x['title']!='Old location' for x in scoped['skipped'])
e.baseline_path(absent).unlink()
# Return to the ordinary update scenario.
shared.unlink()
for name,data in before.items():t.atomic_file(Path(name),data,0o600)
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
from types import SimpleNamespace
with patch.object(e,'Y4MY_PROVIDER',{'id':'dlss-unlocked','name':'DLSS-Unlocked'}), \
     patch.object(e,'_launch_record_for_game',return_value=None):
    engine_bridge.share_install(e,SimpleNamespace(target_dir=root),{'mode':'nr-mfg'})
identity=t.read_json(marker);published=t.read_json(shared);updated=t.read_json(baseline)
assert identity['provider']['id']=='skynizz' and identity['provider']['version']==release['tag']
assert identity['revision']==published['cross_os_revision']==updated['cross_os_revision']
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
    # The retired welcome addon was deliberately removed by the original install.
    # A recorded absence is a valid ownership check, not a missing-file failure.
    feeder_record=feeder.state(e,game);feeder_record['installed_hashes']['quiet-startup.addon64']=None
    t.atomic_file(feeder.state_dir(e,game)/'baseline.json',json.dumps(feeder_record).encode(),0o600)
    model=(game/'nvngx_dlssnr.dll').read_bytes();ini=t.ini((game/'ReShade.ini').read_text())
    tuning=ini['RenoDX.DLSS5']['NRResolutionScale'];native_before=files()
    params=overlay_settings.options({})|{'reshade_ui':False,'target_games':[str(game)],
        'game_overlay_settings':{str(game):{'overlay_welcome':False,'panel_hotkey':'F8'}}}
    with patch.object(feeder,'panel',return_value=new):
        review=overlays.prepare(e,h.LOCAL/'state',params)
        assert len(review['plans'])==1 and not review['blocked'],review
        intruder=game/'quiet-startup.addon64';intruder.write_bytes(b'foreign')
        try:bulk.execute(review);raise AssertionError('foreign file filled reviewed absence')
        except t.Refusal:pass
        intruder.unlink()
        assert 'Welcome message: Off' in review['plans'][0]['note'] and 'shortcut: F8' in review['plans'][0]['note']
        assert (game/feeder.PANELS[0]).read_bytes()==Path(old[feeder.PANELS[0]]['path']).read_bytes(),'review wrote a panel'
        bulk.execute(review)
    assert (game/feeder.PANELS[0]).read_bytes()==Path(new[feeder.PANELS[0]]['path']).read_bytes()
    assert (game/'nvngx_dlssnr.dll').read_bytes()==model and feeder.state(e,game)['originals']==original
    updated=t.ini((game/'ReShade.ini').read_text());assert updated['INPUT']['KeyOverlay']=='0,0,0,0'
    assert updated['RenoDX.DLSS5']['NRResolutionScale']==tuning
    assert files()==native_before,'scoped Feeder update changed another game'
    glass=ff.pe(b'glass feeder');glass_cache=e.STATE_ROOT/'feeder-cache'/t.sha(glass);t.atomic_file(glass_cache,glass,0o600)
    with_glass=new|{'rtxforge-glass.dll':{'path':str(glass_cache),'sha256':t.sha(glass)}}
    foreign=game/'rtxforge-glass.dll';foreign.write_bytes(b'foreign')
    with patch.object(feeder,'panel',return_value=with_glass):
        refused=overlays.prepare(e,h.LOCAL/'state',params);assert not refused['plans'] and refused['blocked']
        foreign.unlink();review=overlays.prepare(e,h.LOCAL/'state',params)
        assert len(review['plans'])==1 and not review['blocked'],review
        bulk.execute(review)
    migrated=feeder.state(e,game)
    assert migrated['originals']['rtxforge-glass.dll'] is None
    assert {k:v for k,v in migrated['originals'].items() if k!='rtxforge-glass.dll'}==original
    assert foreign.read_bytes()==glass and (game/'nvngx_dlssnr.dll').read_bytes()==model
    assert t.ini((game/'ReShade.ini').read_text())['RenoDX.DLSS5']['NRResolutionScale']==tuning
    try:overlays.prepare(e,h.LOCAL/'state',params|{'target_games':[]});raise AssertionError('empty scope widened')
    except t.Refusal:pass
finally:case.doCleanups()
# Required glass addition preserves originals, named presets and tuning. A
# foreign file cannot be adopted, and interruption restores its prior absence.
for name,data in before.items():t.atomic_file(Path(name),data,0o600)
shared.unlink(missing_ok=True)  # Start this addition case with the original local-only recipe.
glass_archive=h.LOCAL/'glass-candidate.zip';glass_release=fixtures.glass_bridge_fixture(glass_archive)|{'panel_renderer':'in-game','panel_candidate':True}
from hashlib import sha256
preset_path=h.LOCAL/'state/runtime-presets'/(sha256(os.path.normcase(str(root/'Game.exe')).encode()).hexdigest()+'.json')
preset_path.parent.mkdir(parents=True,exist_ok=True)
preset_doc={'schema':2,'presets':[{'name':'My tuning','recipe':overlays.recipe(owned,'nr-mfg'),'values':{'intensity':.8}}]}
preset_path.write_text(json.dumps(preset_doc));preset_before=preset_path.read_bytes()
scoped=None  # Required refresh does not reapply app/menu defaults.
with patch.object(overlays.provider,'bundled_bridge',return_value=(glass_release,glass_archive)):
    destination=root/'rtxforge-glass.dll';destination.write_bytes(b'foreign')
    rejected=overlays.prepare(e,h.LOCAL/'state',scoped)
    assert not rejected['plans'] and rejected['blocked'],'foreign glass renderer was adopted'
    destination.unlink()
    review=overlays.prepare(e,h.LOCAL/'state',scoped)
    assert len(review['plans'])==1 and not review['blocked'],review
    assert not destination.exists() and preset_path.read_bytes()==preset_before,'review mutated glass or presets'
    base_state=files();atomic=t.atomic_file;interrupted=[False]
    def interrupt_glass(path,data,*args,**kwargs):
        if Path(path)==destination and not interrupted[0]:interrupted[0]=True;raise OSError('fixture interruption')
        return atomic(path,data,*args,**kwargs)
    with patch.object(t,'atomic_file',side_effect=interrupt_glass):
        try:bulk.execute(review);raise AssertionError('interruption not reported')
        except t.Refusal:pass
    assert files()==base_state and not destination.exists() and preset_path.read_bytes()==preset_before,'glass rollback changed original ownership'
    bulk.execute(overlays.prepare(e,h.LOCAL/'state',scoped))
updated=t.read_json(baseline)
assert updated['originals']['rtxforge-glass.dll']=={'kind':'file','existed':False}
assert {k:v for k,v in updated['originals'].items() if k!='rtxforge-glass.dll'}==record['originals']
assert (root/'OptiScaler.ini').read_bytes()==before[str(root/'OptiScaler.ini')]
assert t.digest(destination)==glass_release['glass_sha256']
saved=t.read_json(preset_path)['presets'][0]
assert saved['name']=='My tuning' and saved['values']==preset_doc['presets'][0]['values']
assert saved['recipe']==overlays.recipe(updated['current']['installed_hashes'],'nr-mfg')
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
