"""Actual Windows host review/execute/scan with disposable Feeder files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKER = r'''
import configparser,importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]);repo=Path(sys.argv[2])
sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
saved_stdout=sys.stdout
import rtxforge_win_host as host
sys.stdout=saved_stdout
import engine_bridge,feeder_provider,runtime_updates
spec=importlib.util.spec_from_file_location('feeder_fixtures',repo/'tests/test_feeder_provider.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
case=fixtures.FeederTest();case.setUp();case.settings['nr_on_launch']=True
try:
    original=engine_bridge.module
    def module(*args,**kwargs):
        e=original(*args,**kwargs);e._running_processes_under_root=lambda root:[]
        e.pe_imported_dlls=lambda exe:{'d3d11.dll'}
        return e
    engine_bridge.module=module
    case.e=module(host.service.config)
    host.service.hardware=lambda:{'ready':True,'system':'Windows','architecture':'AMD64','reason':'fixture'}
    row=case.game(installed=True);before=case.files(row)
    original_ini=configparser.ConfigParser()
    original_ini.read(Path(row['game'])/'ReShade.ini',encoding='utf-8-sig')
    def scan():
        return next(r for r in host.scan({'folders':[row['game']],'runtime_provider':'skynizz'}) if r['game']==row['game'])
    selected=scan()
    assert selected['installed'] and selected['runtime_provider']=='feeder' and not selected['blocked']
    settings=case.settings|{'runtime_provider':'skynizz','manage_dlss_files':True,'borderless_4k':True}
    checked=host.prepare({'rows':[selected],'mode':'nr-mfg','operation':'install','settings':settings})
    assert len(checked['rows'])==1 and not checked['blocked'],checked
    assert host.reviews[checked['token']]['kind']=='feeder'
    assert case.files(row)==before,'review changed game files'
    host.execute({'token':checked['token']})
    after=case.files(row)
    # The host includes reviewed overlay preferences with the model update.
    # Existing NR/depth tuning must survive that UI configuration change.
    assert {name for name in before if before[name]!=after[name]}=={feeder_provider.MODEL,'ReShade.ini'}
    updated_ini=configparser.ConfigParser()
    updated_ini.read(Path(row['game'])/'ReShade.ini',encoding='utf-8-sig')
    for section in original_ini.sections():
        for name,value in original_ini.items(section):
            assert updated_ini.get(section,name)==value,(section,name,value)
    assert feeder_provider.state(case.e,Path(row['game']))['provider_id']=='feeder'
    assert case.e.load_baseline(Path(row['game'])) is None,'forged native provider baseline'
    assert runtime_updates._owned(case.e,Path(row['game']),Path(row['game'])/'nvngx_dlss.dll')
    refreshed=scan()
    assert refreshed['installed'] and refreshed['feeder_managed'] and refreshed['nr_enabled']
    assert refreshed['profile']=='NR Only' and refreshed['installed_on']=='windows'
    assert refreshed['nr_runtime']['version']=='310.9.16.0'
    report=host.METHODS['diagnose']({'row':refreshed})
    assert report['provider']=='feeder' and 'No matching NR evaluation' in ' '.join(report['observations'])
    checked=host.prepare({'rows':[refreshed],'mode':'nr-mfg','operation':'uninstall','settings':settings})
    assert checked['rows'] and not checked['blocked'],checked
    host.execute({'token':checked['token']})
    assert case.files(row)=={'game.exe':before['game.exe'],'save.dat':before['save.dat']}
    fresh=case.game('fresh-dx11');clean=case.files(fresh)
    selected=next(r for r in host.scan({'folders':[fresh['game']],'runtime_provider':'skynizz'}) if r['game']==fresh['game'])
    assert selected['feeder_available'] and selected['install_provider']=='feeder' and not selected['blocked']
    assert not selected.get('installed') and selected.get('runtime_provider')!='feeder','capability forged ownership'
    checked=host.prepare({'rows':[selected],'mode':'nr-mfg','operation':'install','settings':settings|{'nr_on_launch':False}})
    assert checked['rows'] and not checked['blocked'],checked
    assert host.reviews[checked['token']]['kind']=='feeder','fresh route used native package'
    assert case.files(fresh)==clean,'fresh review changed game files'
    host.execute({'token':checked['token']})
    target=Path(fresh['game'])
    for name,data in case.assets.items():
        assert (target/name).read_bytes()==data,'missing local-stack asset: '+name
    assert (target/feeder_provider.MODEL).read_bytes()==case.new
    assert not feeder_provider.configured(target)['nr_enabled'],'fresh NR did not default off'
    refreshed=next(r for r in host.scan({'folders':[fresh['game']],'runtime_provider':'skynizz'}) if r['game']==fresh['game'])
    assert refreshed['installed'] and refreshed['feeder_managed'] and refreshed['runtime_provider']=='feeder'
    checked=host.prepare({'rows':[refreshed],'mode':'nr-mfg','operation':'uninstall','settings':settings})
    assert checked['rows'] and not checked['blocked'],checked
    host.execute({'token':checked['token']})
    assert case.files(fresh)==clean,'fresh restore left package files behind'
    try:host.prepare({'rows':[selected],'mode':'mfg-only','operation':'install','settings':settings})
    except Exception as error:assert 'Feeder provides NR Only' in str(error),error
    else:raise AssertionError('MFG-only request silently installed NR')
    print(json.dumps({'checks':12,'result':'existing adoption plus fresh Skynizz-selected DX11 detection, exact-token full ReShade/Feeder/RenoDX/shader/model deployment, NR-off default, managed refresh, MFG-only refusal and original restore passed'}))
finally:case.doCleanups()
'''


@unittest.skipUnless(os.name == 'nt', 'Requires real Windows host adapters')
class WindowsFeederTest(unittest.TestCase):
    def test_adoption_and_normal_host_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'Steam').mkdir()
            env = dict(os.environ, RTXFORGE_ROOT=str(ROOT), RTXFORGE_STATE_ROOT=str(root/'state'),
                       RTXFORGE_DLSS_UNLOCKED_STATE=str(root/'engine-state'), LOCALAPPDATA=str(root/'appdata'),
                       RTXFORGE_STEAM_ROOTS=str(root/'Steam'), PYTHONUTF8='1')
            result = subprocess.run([sys.executable,'-X','utf8','-c',WORKER,str(root),str(ROOT)],
                                    env=env,capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stderr[-10000:]+result.stdout[-3000:])
            receipt=json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(receipt['checks'],12)
            print('PASS: '+receipt['result'])


if __name__=='__main__':
    unittest.main()
