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
import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]);repo=Path(sys.argv[2])
sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
saved_stdout=sys.stdout
import rtxforge_win_host as host
sys.stdout=saved_stdout
import engine_bridge,feeder_provider,runtime_updates
spec=importlib.util.spec_from_file_location('feeder_fixtures',repo/'tests/test_feeder_provider.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
case=fixtures.FeederTest();case.setUp()
try:
    original=engine_bridge.module
    def module(*args,**kwargs):
        e=original(*args,**kwargs);e._running_processes_under_root=lambda root:[]
        return e
    engine_bridge.module=module
    case.e=module(host.service.config)
    host.service.hardware=lambda:{'ready':True,'system':'Windows','architecture':'AMD64','reason':'fixture'}
    row=case.game(installed=True);before=case.files(row)
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
    assert {name for name in before if before[name]!=after[name]}=={feeder_provider.MODEL}
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
    print(json.dumps({'checks':7,'result':'host scan, exact-token model-only adoption, separate ownership, native updater exclusion, installed refresh, honest diagnosis and original restore passed'}))
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
            self.assertEqual(receipt['checks'],7)
            print('PASS: '+receipt['result'])


if __name__=='__main__':
    unittest.main()
