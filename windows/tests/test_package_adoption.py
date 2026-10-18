"""Real Windows adoption transactions against disposable provider/game fixtures."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKER = r'''
import importlib.util,sys,json,hashlib,copy
from pathlib import Path
repo=Path(sys.argv[1]).resolve();root=Path(sys.argv[2]).resolve()
sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
spec=importlib.util.spec_from_file_location('adopt_fixture',repo/'tests/test_skynizz_provider.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
saved=sys.stdout
import rtxforge_win_host as host
sys.stdout=saved
import package_adoption as a,engine_bridge as b,skynizz_provider as s,offline_routes as off,transactions as t
host.service.config['storage']['reserve_bytes']=0
archive=root/'package.zip';release=fixture.bridge_fixture(archive,root/'production-sr.dll')
s.bundled_bridge=lambda *args:(copy.deepcopy(release),archive)
payload,meta=s.load_payload(archive,release)
for key,(name,_) in s.PRODUCTION_RUNTIMES.items():
    p=root/('production-sr.dll' if name=='nvngx_dlss.dll' else 'production-'+name)
    payload['OptiScaler/'+name]=p.read_bytes()
    meta[key]=release[key]
payload['OptiScaler/streamline/sl.interposer.dll']=fixture.pe()+b'interposer'
payload['OptiScaler/streamline/sl.dlss_g.dll']=fixture.pe()+b'fg'
original=b.module
running=[]
def module(*args,**kwargs):
    e=original(*args,**kwargs);e._running_processes_under_root=lambda root:list(running)
    e.NR_RUNTIME_MIN_BYTES=16
    return e
b.module=module
b.payload=lambda *args,**kwargs:(copy.deepcopy(payload),copy.deepcopy(meta))
off.protected_running=lambda:False
settings={'runtime_provider':'skynizz','nr_on_launch':False,'nr_strength':1.5,'mfg_multiplier':4}
def game(name='Example',offline=False):
    base=root/name;base.mkdir()
    directory=base/'FairlightConcept/Binaries/Win64' if offline else base
    directory.mkdir(parents=True,exist_ok=True)
    exe=directory/('GoWEDay-Steam.exe' if offline else 'Game.exe');exe.write_bytes(fixture.pe()+b'game'*10000)
    (base/'nvngx_dlss.dll').write_bytes(fixture.pe()+b'native')
    (base/'nvngx_dlssg.dll').write_bytes(fixture.pe()+b'nativefg')
    for n,v in payload.items():
        p=directory/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v)
    ini=directory/'OptiScaler.ini'
    text=ini.read_text(encoding='utf-8-sig')
    text=t.setvalue(text,'DlssNr','Enabled','true')
    text=t.setvalue(text,'DlssNr','Intensity','1.37')
    ini.write_text(text,encoding='utf-8')
    (directory/'nvngx_dlssnr.dll').write_bytes(fixture.pe()+b'model')
    (base/'save.dat').write_bytes(b'save')
    row={'game':str(base),'exe':exe.relative_to(base).as_posix(),'name':name,'source':'Folder','native_dlss':True,'native_dlssg':True}
    if offline:
        row['appid']='3010850';row['anti_cheat']=True
        (base/'EasyAntiCheat').mkdir();(base/'EasyAntiCheat/Settings.json').write_text('{}')
        (base/'start_protected_game.exe').write_bytes(fixture.pe()+b'eac')
    return row,directory
def files(root):return {str(p.relative_to(root)):t.digest(p) for p in root.rglob('*') if p.is_file() and not any(part.startswith('.rtxforge') for part in p.relative_to(root).parts)}
def review(row,clean=False):
    r=a.prepare(host.service.config,[row],'adopt-clean' if clean else 'adopt',settings)
    assert len(r['plans'])==1,r['blocked']
    return r
row,target=game();before=files(target);row['installed_on']='windows'
a.decorate(module(host.service.config),[row]);assert row['adoption_available'] and row['installed'] and not row['managed']
assert row['installed_on'] is None,'unmanaged files must not claim installation by rtxForge'
foreign=dict(row,adaptable=True,installed_on='linux')
a.decorate(module(host.service.config),[foreign])
assert foreign['managed'] and not foreign['adoption_available'] and foreign['installed_on']=='linux'
r=review(row);a.execute(r)
assert files(target)==before
e=module(host.service.config);g=b.game(e,row);baseline=e.load_baseline(target)
assert baseline['adoption']['restore_boundary']=='before-adoption'
assert baseline['current']['nr_profile']['enabled']
e.verify_baseline_integrity(target,baseline,adopt_legacy=False)
a.decorate(e,[row]);assert row['managed'] and not row['adoption_available']
e.restore_target(g);assert files(target)==before
# Drift/running-game rejection happens before any management record is written.
row,target=game('Drift');r=review(row);(target/'dxgi.dll').write_bytes(b'changed')
try:a.execute(r);raise AssertionError('drift admitted')
except t.Refusal:pass
assert module(host.service.config).load_baseline(target) is None
row,target=game('Running');r=review(row);running.append('test.exe')
try:a.execute(r);raise AssertionError('running game admitted')
except t.Refusal:pass
running.clear()
# Unknown companion binaries are not silently claimed.
row,target=game('Mixed');(target/'OptiScaler/unknown.dll').write_bytes(b'other')
assert not a.prepare(host.service.config,[row],'adopt',settings)['plans']
# A clean install resets config, starts NR off, and restores the exact adopted setup.
row,target=game('Clean');before=files(target);r=review(row,True);a.execute(r)
assert t.ini((target/'OptiScaler.ini').read_text()).get('DlssNr','Enabled')=='false'
e=module(host.service.config);e.restore_target(b.game(e,row));assert files(target)==before
# New install default and explicit opt-in are independent of MFG.
row,target=game('NewInstall');e=module(host.service.config);g=b.game(e,row)
# Remove the manually staged package, retaining the native game DLLs and saves.
for name in [*payload,'nvngx_dlssnr.dll']:
    (target/name).unlink()
for directory in sorted((target/'OptiScaler').rglob('*'),key=lambda p:len(p.parts),reverse=True):
    if directory.is_dir():directory.rmdir()
(target/'OptiScaler').rmdir()
e.Y4MY_PROVIDER=copy.deepcopy(release)
e.install_target(g,payload,meta,'ada',nr_runtime_payload=fixture.pe()+b'model',nr_runtime_meta={'sha256':t.sha(fixture.pe()+b'model')},feature_mode='nr-mfg',enable_effects=True)
assert not t.ini((target/'OptiScaler.ini').read_text()).getboolean('DlssNr','Enabled')
assert t.ini((target/'OptiScaler.ini').read_text()).getboolean('DLSSG','AdaMfgUnlock')
# Gears requires explicit reviewed consent; all other EAC games remain blocked.
row,target=game('Gears',True);e=module(host.service.config);g=b.game(e,row)
assert g.anti_cheat and not g.eligible
before=files(Path(row['game']));a.execute(review(row));assert files(Path(row['game']))==before
g=b.game(e,row);assert g.anti_cheat and g.eligible
off.protected_running=lambda:True
assert not g.eligible
off.protected_running=lambda:False
(Path(row['game'])/'EasyAntiCheat/Settings.json').write_text('{"changed":true}')
assert not g.eligible
row,target=game('OtherEAC');(target/'EasyAntiCheat').mkdir();(target/'EasyAntiCheat/Settings.json').write_text('{}')
row['anti_cheat']=True
assert not a.prepare(host.service.config,[row],'adopt',settings)['plans']
# Launch uses the exact reviewed executable and child-only environment.
row,target=game('LaunchOffline',True);a.execute(review(row));e=module(host.service.config)
from unittest.mock import patch
import os
original_environment=dict(os.environ)
with patch.object(off.subprocess,'Popen') as start:
    start.return_value.pid=1234
    assert off.launch(e,row)['offline_only']
    args,kwargs=start.call_args
    assert args[0]==[str(target/'GoWEDay-Steam.exe')]
    assert kwargs['env']['EOS_USE_ANTICHEATCLIENTNULL']=='1'
    assert os.environ==original_environment
# Failure after baseline capture rolls ownership/markers back.
row,target=game('FailedRegistration');r=review(row);before=files(target)
with patch.object(a,'_register_native',side_effect=OSError('injected failure')):
    try:a.execute(r);raise AssertionError('failure ignored')
    except OSError:pass
assert module(host.service.config).load_baseline(target) is None and files(target)==before
# Separate Feeder adapter, same Adoption semantics, with no original manual receipt required.
spec=importlib.util.spec_from_file_location('feed_adopt_fixture',repo/'tests/test_feeder_provider.py')
ff=importlib.util.module_from_spec(spec);spec.loader.exec_module(ff)
case=ff.FeederTest();case.setUp()
try:
    row=case.game('FeedAdopt',installed=True);row['runtime_provider']='feeder'
    target=Path(row['game']);before=files(target)
    r=a.prepare(host.service.config,[row],'adopt',case.settings)
    assert r['plans'],r['blocked']
    a.execute(r);assert files(target)==before
    assert a.feeder.state(module(host.service.config),target)['restore_boundary']=='before-adoption'
finally:case.doCleanups()
print('adoption, clean install, restore, drift, running, unknown files and scoped offline consent passed')
'''


@unittest.skipUnless(os.name == 'nt', 'Windows native transaction adapter')
class AdoptionTransactions(unittest.TestCase):
    def test_transactions(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = str(Path(temp).resolve())
            env = dict(os.environ, LOCALAPPDATA=str(Path(temp)/'local'), RTXFORGE_STATE_ROOT=str(Path(temp)/'state'),
                       RTXFORGE_DLSS_UNLOCKED_STATE=str(Path(temp)/'engine'), RTXFORGE_ROOT=str(ROOT), PYTHONIOENCODING='utf-8')
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', WORKER, str(ROOT), temp],
                                    env=env, text=True, capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-6000:])


if __name__ == '__main__': unittest.main()
