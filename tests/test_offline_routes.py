"""Offline install consent binds exact files without adding a generic launcher."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import offline_routes as off
import transactions as t


class OfflineRoutesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / 'Game.exe').write_bytes(b'game executable')
        (self.root / 'EasyAntiCheat').mkdir()
        (self.root / 'EasyAntiCheat/Settings.json').write_text('{}')
        self.row = {'game': str(self.root), 'exe': 'Game.exe', 'appid': '123'}
        self.game = SimpleNamespace(root=self.root, exe=self.root/'Game.exe', target_dir=self.root,
                                    appid='123', anti_cheat=True)
        self.e = SimpleNamespace(load_baseline=lambda *a, **k: None)
        p = patch.object(off, 'protected_running', return_value=False)
        p.start(); self.addCleanup(p.stop)

    def test_review_is_scoped_read_only_and_not_persistent_consent(self):
        route = off.receipt(self.row, manual=True)
        self.assertFalse(off.allowed(self.e, self.game))
        with off.reviewed([route]):
            self.assertTrue(off.allowed(self.e, self.game))
            self.assertIsNone(off.reviewed_route(self.row | {'exe': 'Other.exe'}))
        self.assertFalse(off.allowed(self.e, self.game))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['EasyAntiCheat', 'Game.exe'])

    def test_executable_and_anti_cheat_drift_require_new_review(self):
        for name in ('Game.exe', 'EasyAntiCheat/Settings.json'):
            with self.subTest(name=name):
                route = off.receipt(self.row, manual=True)
                path = self.root/name
                original = path.read_bytes()
                path.write_bytes(original+b'changed')
                with self.assertRaises(t.Refusal):
                    with off.reviewed([route]): pass
                path.write_bytes(original)

    def test_protected_process_and_other_roots_are_not_admitted(self):
        route = off.receipt(self.row, manual=True)
        with patch.object(off, 'protected_running', return_value=True), self.assertRaises(t.Refusal):
            with off.reviewed([route]): pass
        with off.reviewed([route]), patch.object(off, 'protected_running', return_value=True):
            self.assertFalse(off.allowed(self.e, self.game))
        with off.reviewed([route]):
            self.assertIsNone(off.reviewed_route(self.row | {'game': str(self.root/'other')}))

    def test_manual_route_has_no_automatic_launcher_or_environment(self):
        route = off.receipt(self.row, manual=True)
        self.assertEqual(off.verify(route)['environment'], {})
        self.assertIsNone(off.profile(self.row))
        with self.assertRaises(t.Refusal): off.receipt(self.row)

    def test_persisted_receipt_keeps_existing_management_scoped(self):
        route = off.receipt(self.row, manual=True)
        self.e.load_baseline = lambda *a, **k: {'status': 'active', 'offline_route': route}
        self.assertTrue(off.allowed(self.e, self.game))
        (self.root/'Game.exe').write_bytes(b'update')
        self.assertFalse(off.allowed(self.e, self.game))


if __name__ == '__main__': unittest.main()
