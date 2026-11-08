"""The Windows host's review_prepare: the shared review planner behind Windows Desktop."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKER = r'''
import json,sys
from pathlib import Path
repo=Path(sys.argv[1]);sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
out=sys.stdout
import rtxforge_win_host as host
sys.stdout=out
calls,discarded,downloads=[],[],[]
def prepare(params):
    calls.append((params['operation'],params['mode'],params['settings']['runtime_provider'],[row['name'] for row in params['rows']]))
    return {'token':str(len(calls)),'rows':[{'name':row['name'],'game':row['game']} for row in params['rows']],'blocked':[],'warnings':[]}
host.prepare=prepare
host.discard_operation=lambda params:discarded.extend(params['tokens'])
host.prefetch_install=lambda params:downloads.append([batch['settings']['runtime_provider'] for batch in params['batches']])
rows=[{'name':'B','game':'/games/B','exe':'B.exe','runtime_provider':'feeder','installed':True},
      {'name':'A','game':'/games/A','exe':'A.exe','installed':True,'runtime_provider':'skynizz'}]
settings={'runtime_provider':'skynizz','manage_dlss_files':True}
desktop={'apply':'reset'}
# Desktop Repair is the engine's file repair, as in Game Mode; routes, batches and downloads are the planner's.
result=host.review_prepare({'rows':rows,'operation':'repair','mode':'nr-mfg','settings':settings,'engine_operations':desktop})
assert calls==[('repair','nr-mfg','skynizz',['A']),('repair','nr-mfg','skynizz',['B'])],calls
assert downloads==[['skynizz','feeder']],downloads
assert [step['route'] for step in result['steps']]==['skynizz','feeder'],result
assert [step['operation'] for step in result['steps']]==['repair','repair'],result
assert result['supported']==[] and result['blocked']==[] and discarded==[],result
# Desktop Apply re-applies presets as a reset, with no downloads.
calls.clear();downloads.clear()
host.review_prepare({'rows':rows[1:],'operation':'apply','mode':'nr-mfg','settings':settings,'engine_operations':desktop})
assert calls==[('reset','nr-mfg','skynizz',['A'])] and downloads==[],(calls,downloads)
# Without a mapping (Game Mode) the planned operation is the engine's.
calls.clear()
host.review_prepare({'rows':rows[1:],'operation':'apply','mode':'nr-mfg','settings':settings})
assert calls==[('apply','nr-mfg','skynizz',['A'])],calls
# The background-activity line follows the request and clears when it ends.
import activity
lines,replies=[],[]
host.activity_line=activity.Tracker(lines.append,show_after=0)
host.send=replies.append
host.handle({'id':7,'method':'review_prepare','params':{'rows':rows,'operation':'repair','mode':'nr-mfg','settings':settings}})
texts=[line['text'] for line in lines]
assert texts[0]=='Checking games for the review' and 'Downloading packages/files' in texts and texts[-1]=='',texts
assert replies[-1]['id']==7 and 'result' in replies[-1],replies[-1]
print('PASS: review_prepare plans routes and runs each as the requested engine operation')
'''


class ReviewPrepareHostTest(unittest.TestCase):
    def test_desktop_operations_follow_the_shared_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root/'Steam').mkdir()
            env = dict(os.environ, RTXFORGE_ROOT=str(ROOT), RTXFORGE_STATE_ROOT=str(root/'state'),
                       RTXFORGE_DLSS_UNLOCKED_STATE=str(root/'engine-state'), LOCALAPPDATA=str(root/'appdata'),
                       RTXFORGE_STEAM_ROOTS=str(root/'Steam'), PYTHONUTF8='1')
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', WORKER, str(ROOT)], env=env,
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr[-8000:] + result.stdout[-2000:])
            print(result.stdout.strip().splitlines()[-1])


if __name__ == '__main__':
    unittest.main()
