"""Exercise the real atomic settings writer only inside a temporary local app tree."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
HOST = Path(__file__).resolve().parents[1] / 'bridge/engine_host.py'


@unittest.skipUnless(os.name == 'nt', 'Windows native preference contract')
class NativeSettingsTests(unittest.TestCase):
    def test_native_path_unknown_keys_and_exact_review(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            local = folder / 'rtxForge'
            local.mkdir()
            native = local / 'settings.json'
            native.write_text(json.dumps({'online_art': True, 'native_only_fixture': {'keep': True}, 'game_executables': {}}))
            legacy = local / 'state/desktop/settings.json'
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"legacy_marker":true}')
            environment = os.environ | {'RTXFORGE_ENGINE_BRIDGE': '1', 'RTXFORGE_ROOT': str(ROOT), 'LOCALAPPDATA': str(folder), 'RTXFORGE_STATE_ROOT': str(local / 'state')}
            process = subprocess.Popen([sys.executable, '-u', '-B', str(HOST)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding='utf-8', env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                ready = json.loads(process.stdout.readline())
                self.assertFalse(ready['automaticRefresh'])
                process.stdin.write(json.dumps({'id': 'review', 'method': 'settings_review', 'params': {'changes': {'online_art': False,
                    'borderless_4k': True, 'overlay_appearance': {'Layout':'bar','TextSize':26}}}}) + '\n')
                process.stdin.flush()
                response = json.loads(process.stdout.readline())
                self.assertNotIn('error', response)
                token = response['result']['token']
                self.assertTrue(json.loads(native.read_text())['online_art'], 'Review must not save preferences')
                process.stdin.write(json.dumps({'id': 'confirm', 'method': 'run', 'params': {'token': token}}) + '\n')
                process.stdin.flush()
                confirmed = json.loads(process.stdout.readline())
                self.assertNotIn('error', confirmed)
                result = json.loads(native.read_text())
                self.assertFalse(result['online_art'])
                self.assertTrue(result['borderless_4k'])
                self.assertEqual({'Layout':'bar','TextSize':26}, result['overlay_appearance'])
                self.assertEqual({'keep': True}, result['native_only_fixture'])
                self.assertEqual({'legacy_marker': True}, json.loads(legacy.read_text()))
                process.stdin.close()
                process.wait(timeout=10)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()


if __name__ == '__main__':
    unittest.main()
