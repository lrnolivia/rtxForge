"""Real Windows process detection plus fail-closed query errors."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKER = r'''
import json,os,sys,subprocess
from pathlib import Path
from unittest.mock import patch
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'scripts'),str(root/'windows/engine-host')]
output=sys.stdout
import rtxforge_win_host as host
sys.stdout=output
from transactions import Refusal
folder=Path(sys.executable).parent
actual=host._running_under(folder)
assert any(line.startswith(str(os.getpid())+':') for line in actual),actual
assert not host._running_under(folder/'not-a-real-game')
for result in [subprocess.CompletedProcess([],1,stdout='',stderr='failure'),OSError('missing query'),subprocess.TimeoutExpired('query',20)]:
    options={'side_effect':result} if isinstance(result,Exception) else {'return_value':result}
    with patch.object(host.subprocess,'run',**options):
        try:host._running_under(folder)
        except Refusal:pass
        else:raise AssertionError('unknown process state allowed game writes')
print(json.dumps({'self_detected':True,'boundary_checked':True,'errors_refused':3}))
'''


@unittest.skipUnless(os.name == 'nt', 'Windows process query')
class ProcessTests(unittest.TestCase):
    def test_live_process_and_query_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, RTXFORGE_ROOT=str(ROOT), LOCALAPPDATA=str(Path(directory) / 'appdata'),
                       RTXFORGE_STATE_ROOT=str(Path(directory) / 'state'), RTXFORGE_DLSS_UNLOCKED_STATE=str(Path(directory) / 'engine'))
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', WORKER, str(ROOT)], env=env,
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:] + result.stdout[-1000:])
            self.assertTrue(json.loads(result.stdout.strip().splitlines()[-1])['self_detected'])


if __name__ == '__main__':
    unittest.main()
