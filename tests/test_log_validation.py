"""Validate reads a game's own logs for proof that NR or MFG ran, and never more."""
import json
import os
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import game_notes  # noqa: E402
import log_validation  # noqa: E402

NR_LOG = 'OptiScaler v0.9 loaded\nCreateFeature(18) result=0x00000001 handle=1\nDLSS-NR GPU window: 256 samples, 2.1 ms\n'
MFG_LOG = ('DLSS-G state sample: frames presented since prior query=1 (maximum generated per real frame=5, status=0)\n'
           'DLSS-G state sample: frames presented since prior query=4 (maximum generated per real frame=5, status=0)\n')


class LogValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.game = root / 'Game'; self.game.mkdir()
        (self.game / 'Game.exe').write_bytes(b'MZ')
        self.row = {'name': 'Game', 'game': str(self.game), 'exe': 'Game.exe', 'runtime_provider': 'universal-mfg'}
        self.config = {'storage': {'root': str(root / 'state'), 'reserve_bytes': 0}}
        # Test records live in the app's storage; keep them in this test's folder on every OS.
        patcher = unittest.mock.patch.object(game_notes, 'root', lambda config: root / 'state' / 'reports')
        patcher.start(); self.addCleanup(patcher.stop)
        self.install(time.time() - 3600)

    def install(self, when):
        stamp = time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime(when))
        (self.game / '.rtxforge-install.json').write_text(json.dumps({
            'schema': 2, 'os': 'windows', 'installed_at': stamp, 'provider': {'id': 'universal-mfg'},
            'files': {'dxgi.dll': '0' * 64}}))

    def test_nothing_logged_is_no_proof(self):
        self.assertEqual(log_validation.scan(self.row)['found'], [])

    def test_nr_and_mfg_from_their_own_logs(self):
        (self.game / 'OptiScaler.log').write_text(NR_LOG)
        (self.game / 'RTXMFG-game-0123456789ABCDEF.log').write_text(MFG_LOG)
        result = log_validation.scan(self.row)
        self.assertEqual(result['found'], ['NR', 'MFG'])
        self.assertIn('4 frames', ' '.join(result['details']))

    def test_one_frame_per_query_or_an_error_status_is_not_frame_generation(self):
        (self.game / 'RTXMFG-game-0123456789ABCDEF.log').write_text(
            'DLSS-G state sample: frames presented since prior query=1 (maximum generated per real frame=5, status=0)\n'
            'DLSS-G state sample: frames presented since prior query=4 (maximum generated per real frame=5, status=2)\n')
        self.assertEqual(log_validation.scan(self.row)['found'], [])

    def test_logs_from_before_this_install_say_nothing(self):
        (self.game / 'RTXMFG-game-0123456789ABCDEF.log').write_text(MFG_LOG)
        old = time.time() - 7200
        os.utime(self.game / 'RTXMFG-game-0123456789ABCDEF.log', (old, old))
        self.assertEqual(log_validation.scan(self.row)['found'], [])

    def test_the_chosen_result_is_kept_and_a_running_test_is_left_alone(self):
        (self.game / 'OptiScaler.log').write_text(NR_LOG)
        record = log_validation.validate(self.config, self.row)
        self.assertEqual(record['status'], 'Untested')
        self.assertEqual(record['validation']['found'], ['NR'])
        record['active'] = {'id': 'session'}; record.pop('validation')
        game_notes.save(self.config, self.row['game'], record)
        self.assertNotIn('validation', log_validation.validate(self.config, self.row))


if __name__ == '__main__':
    unittest.main()
