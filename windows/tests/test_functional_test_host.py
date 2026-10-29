"""Start/Finish through the real Windows host, with deterministic mailbox telemetry."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOST_TEST = r'''
import sys,time
from pathlib import Path
repo,base=map(Path,sys.argv[1:]);sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
saved=sys.stdout
import rtxforge_win_host as host
sys.stdout=saved
import cross_os,functional_test as ft,game_notes,win_features
game=base/'game';game.mkdir();(game/'Game.exe').write_bytes(b'MZ')
(game/'dxgi.dll').write_bytes(b'owned');(game/'OptiScaler.ini').write_text('[DlssNr]\nEnabled=true\nIntensity=1\n[DLSSG]\nOverrideInterpolationCount=3\n')
cross_os.write(game,'windows',['dxgi.dll'],{'id':'skynizz'},'nr-mfg','dxgi.dll')
row={'game':str(game),'exe':'Game.exe','name':'Host Test'}
sequence=0
def live(params):
    global sequence
    sequence+=2
    return dict(state='running',telemetry_source='skynizz-mailbox',pid=42,version=7,sequence=sequence,
                can_nr=True,can_mfg=True,nr_running=True,nr_ms=1.2,rendered_fps=60,
                nr_placement_verified=True,nr_placement=3,native_fresh=True,native_status=0,
                native_presented=4,native_generated=3,native_mode=1,fg_successes=sequence,
                values={'enabled':1,'intensity':1,'multiplier':4,'dynamic_mfg':0})
win_features.live_status=live
params={'row':row,'helper':{'running':True,'channel_valid':True,'pid':42},'shortcut_ok':True,'shortcut':'Delete'}
started=host.METHODS['test_start'](params)
assert started['active']['checks']['files_ok'] is True,started
assert started['active']['checks']['route']=='skynizz',started
try:host.METHODS['test_start'](params)
except Exception as error:assert 'Finish the current test' in str(error)
else:raise AssertionError('Duplicate start was accepted')
time.sleep(1.1)
closed=host.METHODS['test_finish'](params)
assert 'active' not in closed and closed['status']=='Untested',closed
test=game_notes.latest_test(closed);results={r['part']:r for r in test['results']}
assert all(results[p]['state']=='working' for p in ('files','settings','shortcut','hook','nr','mfg','panel','helper')),results
assert test['suggestion']=='Working',test
draft=host.METHODS['report_draft']({'rows':[row]})['reports'][0]
assert draft['fields']['nr-result']=='Working in-game' and draft['fields']['mfg-result']=='Working in-game',draft
assert draft['fields']['observations']=='',draft
again=host.METHODS['test_start'](params)
assert again['active']['id']!=started['active']['id']
ft.stop(win_features._config(),row,again['active'])
decorated=win_features.decorate([dict(row)])
assert decorated[0]['test_record']['active']['id']==again['active']['id']
closed=host.METHODS['test_finish'](params)
assert len(closed['sessions'])==2
assert ft.read_samples(win_features._config(),row,{'id':'different'})==[]
assert (game/'dxgi.dll').read_bytes()==b'owned'
print('Windows functional host: sampling, report prefill, duplicate refusal and restart recovery passed')
'''


@unittest.skipUnless(os.name == 'nt', 'Windows host adapters')
class FunctionalHostTests(unittest.TestCase):
    def test_host_session(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve(); local = base / 'local'
            env = dict(os.environ, LOCALAPPDATA=str(local), RTXFORGE_ROOT=str(ROOT),
                       RTXFORGE_STATE_ROOT=str(local / 'rtxForge/state'),
                       RTXFORGE_DLSS_UNLOCKED_STATE=str(local / 'rtxForge/engine-state'), PYTHONUTF8='1')
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', HOST_TEST, str(ROOT), str(base)],
                                    env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr[-6000:] + result.stdout[-1500:])


if __name__ == '__main__': unittest.main()
