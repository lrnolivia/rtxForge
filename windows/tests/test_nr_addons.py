"""NR add-on choice through the real Windows host methods, in a disposable app-data folder."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOST_TEST = r'''
import sys
from pathlib import Path
repo,base=map(Path,sys.argv[1:]);sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
saved=sys.stdout
import rtxforge_win_host as host
sys.stdout=saved
M=host.METHODS
catalog=M['nr_catalog']({})
assert {a['id'] for a in catalog['addons']}=={'lecram','shortfuse','gitc'},catalog
assert {m['id'] for m in catalog['models']}=={'old','new'}
assert catalog['combos']['characters-and-world']['builtin'] is True
row={'name':'Game','game':str(base),'exe':'Game.exe','native_dlss':True}
combo=catalog['combos']['characters-and-world']
ok=M['nr_check']({'row':row,'setup':{'environment':combo['environment'],'character':combo['character']}})
assert ok['ok'] and not ok['feeder'] and ok['verified'] and not ok['optiscaler_nr'],ok
opti=dict(row,installed=True,runtime_provider='skynizz',feature_mode='nr-mfg')
lecram=M['nr_check']({'row':opti,'setup':{'environment':combo['environment']}})
assert not lecram['ok'] and 'OptiScaler is installed' in lecram['reason'],lecram
sf=catalog['combos']['characters-with-optiscaler']
beside=M['nr_check']({'row':opti,'setup':{'character':sf['character']}})
assert beside['ok'] and beside['optiscaler_nr'] and beside['model'] is None,beside
assert M['nr_status']({'row':opti})['default']=={'character':{'addon':'shortfuse'}}
no=M['nr_check']({'row':dict(row,native_dlss=False),'setup':{'environment':combo['environment'],'character':combo['character']}})
assert not no['ok'] and 'own DLSS' in no['reason'],no
gitc=M['nr_check']({'row':row,'setup':{'environment':{'addon':'gitc'},'character':{'addon':'lecram'}}})
assert not gitc['ok'] and 'runs alone' in gitc['reason'],gitc
saved=M['nr_combo_save']({'name':'Soft world','combo':{'environment':{'addon':'lecram','model':'old','values':{'intensity':0.6}}}})
assert saved['combos'][saved['id']]['name']=='Soft world' and saved['combos'][saved['id']]['builtin'] is False
assert M['nr_catalog']({})['combos'][saved['id']]['environment']['values']=={'intensity':0.6},'not persisted'
try:M['nr_combo_save']({'name':'Bad','combo':{'environment':{'addon':'lecram','values':{'intensity':9}}}})
except Exception as error:assert 'between' in str(error),error
else:raise AssertionError('an out-of-range combo was saved')
try:M['nr_combo_delete']({'id':'characters-and-world'})
except Exception as error:assert 'Built-in' in str(error),error
else:raise AssertionError('a built-in combo was deleted')
left=M['nr_combo_delete']({'id':saved['id']})
assert saved['id'] not in left['combos']
assert M['nr_status']({'row':row})=={'installed':False,'default':{'environment':{'addon':'lecram'}}}
print('NR add-on host methods passed')
'''


@unittest.skipUnless(os.name == 'nt', 'Windows host adapters')
class NrAddonHostTests(unittest.TestCase):
    def test_host_methods(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve(); local = base / 'local'
            env = dict(os.environ, LOCALAPPDATA=str(local), RTXFORGE_ROOT=str(ROOT),
                       RTXFORGE_STATE_ROOT=str(local / 'rtxForge/state'),
                       RTXFORGE_DLSS_UNLOCKED_STATE=str(local / 'rtxForge/engine-state'), PYTHONUTF8='1')
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', HOST_TEST, str(ROOT), str(base)],
                                    env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr[-6000:] + result.stdout[-1500:])


if __name__ == '__main__': unittest.main()
