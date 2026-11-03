import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import overlay_status


class OverlayStatusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / 'app'; self.state = self.root / 'state'; self.game = self.root / 'game'
        self.game.mkdir(); self.app.mkdir(); self.state.mkdir()
        (self.app / 'VERSION').write_text('1.5.0-beta.1')
        folder = self.app / 'providers/glass-overlay'; folder.mkdir(parents=True)
        self.new = b'new glass'; self.old = b'old glass'
        self.hash = lambda data: hashlib.sha256(data).hexdigest()
        (folder / 'rtxforge-glass.dll').write_bytes(self.new)
        (folder / 'package.json').write_text(json.dumps({'revision':7, 'files':{'rtxforge-glass.dll':{'sha256':self.hash(self.new)}}}))
        self.path = self.state / 'targets/game/baseline.json'; self.path.parent.mkdir(parents=True)

    def record(self, installed, observed=None, **extra):
        (self.game / 'rtxforge-glass.dll').write_bytes(installed if observed is None else observed)
        value = {'status':'active', 'target_dir':str(self.game), 'name':'A game', 'current':{
            'provider_id':'skynizz', 'installed_hashes':{'rtxforge-glass.dll':self.hash(installed)},
            'archive':{'release':{'glass_revision':6, 'glass_source':'a'*40}}}}
        value.update(extra); self.path.write_text(json.dumps(value))

    def test_current_update_needed_and_drift_are_distinct(self):
        for installed, observed, status in [(self.new,self.new,'current'), (self.old,self.old,'update-available'),
                                            (self.new,b'foreign','needs-attention')]:
            with self.subTest(status=status):
                self.record(installed, observed)
                result = overlay_status.collect(self.app,self.state)['games'][0]
                self.assertEqual(result['status'],status)
                self.assertEqual(result['currentVersion'],'1.5.0-beta.1')
                self.assertIsNone(result['lastUpdated'])

    def test_read_does_not_mutate_records_or_invent_dates(self):
        self.record(self.new)
        before = self.path.read_bytes()
        overlay_status.collect(self.app,self.state)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse((self.state/'overlay-update-dates.json').exists())

    def test_completed_update_has_a_recorded_timestamp(self):
        self.record(self.new)
        overlay_status.record_updates(self.state,[{'target':str(self.game)}])
        result = overlay_status.collect(self.app,self.state)['games'][0]
        self.assertRegex(result['lastUpdated'],r'^\d{4}-\d{2}-\d{2}T')

    def test_unrecorded_old_overlay_is_explicitly_unknown(self):
        self.record(self.new,current={'provider_id':'skynizz','installed_hashes':{}})
        result = overlay_status.collect(self.app,self.state)['games'][0]
        self.assertEqual(result['status'],'unknown')
        self.assertIsNone(result['installedVersion'])

    def test_restored_record_is_absent_and_missing_target_is_unavailable(self):
        self.record(self.new,status='restored')
        self.assertEqual(overlay_status.collect(self.app,self.state)['games'],[])
        self.record(self.new); (self.game/'rtxforge-glass.dll').unlink(); self.game.rmdir()
        self.assertEqual(overlay_status.collect(self.app,self.state)['games'][0]['status'],'unavailable')

    def test_unsafe_owned_member_is_not_read(self):
        self.record(self.new,current={'provider_id':'skynizz','installed_hashes':{'../rtxforge-glass.dll':'a'*64}})
        result = overlay_status.collect(self.app,self.state)
        self.assertEqual(result['games'],[])
        self.assertIn('Invalid owned overlay file path',result['warnings'][0])


if __name__ == '__main__':
    unittest.main()
