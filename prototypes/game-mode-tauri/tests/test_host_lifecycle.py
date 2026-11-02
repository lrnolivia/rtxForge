"""Real child-process EOF tests; all writes stay in temporary fixtures."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BRIDGE = Path(__file__).resolve().parents[1] / 'bridge'
FIXTURE = r'''
import json, sys, threading, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from host_lifecycle import serve
cancel = threading.Event()
def send(value):
    print(json.dumps(value), flush=True)
def handle(request):
    if request['method'] == 'execute':
        send({'event': 'writing'})
        time.sleep(.2)
        Path(sys.argv[2]).write_text('transaction-complete')
        send({'id': request['id'], 'result': {'cancelled': cancel.is_set()}})
    else:
        send({'id': request['id'], 'result': 'ready'})
serve(sys.stdin.buffer, handle, send, {'hello', 'execute'}, cancel.set)
'''


class LifecycleTests(unittest.TestCase):
    def test_eof_cancels_and_drains_transaction_before_reaping(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'transaction.txt'
            child = subprocess.Popen([sys.executable, '-u', '-c', FIXTURE, str(BRIDGE), str(target)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            child.stdin.write(json.dumps({'id': 'write', 'method': 'execute'}) + '\n')
            child.stdin.flush()
            self.assertEqual('writing', json.loads(child.stdout.readline())['event'])
            child.stdin.close()
            self.assertTrue(json.loads(child.stdout.readline())['result']['cancelled'])
            self.assertEqual(0, child.wait(timeout=5))
            self.assertEqual('transaction-complete', target.read_text())
            child.stdout.close()
            child.stderr.close()

    def test_idle_host_exits_and_new_process_starts_cleanly(self):
        for _ in range(2):
            result = subprocess.run([sys.executable, '-u', '-c', FIXTURE, str(BRIDGE), 'unused'],
                                    input='{"id":"hello","method":"hello"}\n', text=True,
                                    capture_output=True, timeout=5)
            self.assertEqual(0, result.returncode)
            # EOF may reject work not yet admitted, but never leaves a pending request.
            response = json.loads(result.stdout)
            self.assertEqual('hello', response['id'])
            self.assertTrue('result' in response or 'error' in response)
