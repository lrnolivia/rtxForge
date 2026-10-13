"""Native runtime lifecycle checks on temporary game folders only."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import runtime_updates as runtime
import transactions as t


def pe(v):
    data = bytearray(256)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64)
    data[64:70] = b'PE\0\0\x64\x86'
    struct.pack_into('<IIII', data, 128, 0xFEEF04BD, 0x10000, (v << 16), 0)
    return bytes(data)


class Engine:
    def load_baseline(self, path, readonly=False):
        return None
    def _running_processes_under_root(self, root):
        return []


class RuntimeUpdatesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.game = self.root / 'Game'
        self.game.mkdir()
        (self.game / 'Game.exe').write_bytes(pe(1))
        (self.game / 'save.dat').write_bytes(b'save data')
        self.dll = self.game / 'nvngx_dlss.dll'
        self.dll.write_bytes(pe(1))
        self.source = self.root / 'source.dll'
        self.source.write_bytes(pe(2))
        self.config = {'storage': {'root': str(self.root / 'state'), 'reserve_bytes': 0}}
        self.snapshot = {'repository': 'fixture/source', 'commit': 'a'*40, 'entries': {
            'nvngx_dlss.dll': {'name': 'nvngx_dlss.dll', 'version': '2.0.0.0'}}}
        self.games = [{'name': 'Game', 'game': str(self.game), 'source': 'Folder'}]
        patcher = patch.object(runtime.engine_bridge, 'module', return_value=Engine())
        self.engine = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch.object(runtime, 'download', return_value=self.source)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_same_version_replacement_is_explicit_and_hash_guarded(self):
        self.dll.write_bytes(pe(2) + b'different build')
        with patch.object(runtime, 'catalog', return_value=self.snapshot):
            self.assertEqual(runtime.manage(self.config, self.games)['updated_games'], 0)
            self.assertEqual(runtime.manage(self.config, self.games, replace_same=True)['updated_games'], 1)
            self.assertEqual(self.dll.read_bytes(), pe(2))
            self.assertEqual(runtime.manage(self.config, self.games, replace_same=True)['updated_games'], 0)

    def test_backup_is_evidence_not_shipping_proof(self):
        self.assertEqual(runtime.backup_comparison(self.dll), 'Shipping version unknown')
        backup = self.dll.with_suffix('.dlsss')
        backup.write_bytes(pe(1))
        self.assertEqual(runtime.backup_comparison(self.dll), 'Matches updater backup · 1.0.0.0')
        self.dll.write_bytes(pe(2))
        self.assertEqual(runtime.backup_comparison(self.dll), 'Differs from updater backup · 1.0.0.0')

    def plans(self):
        rows = runtime.inspect(self.config, self.games, self.snapshot)
        return runtime.prepare(self.config, self.snapshot, rows)

    def test_review_apply_restore_and_save_preservation(self):
        plans = self.plans()
        self.assertEqual(self.dll.read_bytes(), pe(1))
        records = runtime.apply(self.config, plans)
        self.assertEqual(self.dll.read_bytes(), pe(2))
        self.assertEqual(len(runtime.recoveries(self.config)), 1)
        self.assertEqual(runtime.restore(self.config, records[0])['files'], ['nvngx_dlss.dll'])
        runtime.restore(self.config, records[0], True)
        self.assertEqual(self.dll.read_bytes(), pe(1))
        self.assertEqual((self.game / 'save.dat').read_bytes(), b'save data')
        self.assertFalse(runtime.recoveries(self.config))

    def test_target_drift_refuses_apply_and_restore(self):
        plans = self.plans()
        self.dll.write_bytes(pe(3))
        with self.assertRaisesRegex(t.Refusal, 'Target drift'):
            runtime.apply(self.config, plans)
        self.dll.write_bytes(pe(1))
        record = runtime.apply(self.config, self.plans())[0]
        self.dll.write_bytes(pe(3))
        with self.assertRaisesRegex(t.Refusal, 'Rollback drift'):
            runtime.restore(self.config, record, True)
        self.assertEqual(self.dll.read_bytes(), pe(3))

    def test_private_and_owned_runtimes_excluded(self):
        private = self.game / 'OptiScaler'
        private.mkdir()
        (private / 'nvngx_dlss.dll').write_bytes(pe(1))
        rows = runtime.inspect(self.config, self.games, self.snapshot)
        self.assertEqual([x['path'] for x in rows[0]['files']], ['nvngx_dlss.dll'])
        self.engine.load_baseline = lambda *args, **kwargs: {'status': 'active', 'managed_paths': ['nvngx_dlss.dll']}
        self.assertFalse(runtime.inspect(self.config, self.games, self.snapshot)[0]['files'])

    def test_links_and_anticheat_refused(self):
        self.dll.unlink()
        self.dll.symlink_to(self.source)
        self.assertTrue(runtime.inspect(self.config, self.games, self.snapshot)[0]['blocked'])
        self.dll.unlink()
        self.dll.write_bytes(pe(1))
        (self.game / 'EasyAntiCheat').mkdir()
        (self.game / 'EasyAntiCheat' / 'EasyAntiCheat.exe').write_bytes(pe(1))
        self.assertIn('Anti-cheat', runtime.inspect(self.config, self.games, self.snapshot)[0]['blocked'])

    def test_running_game_and_ownership_change_refused(self):
        plans = self.plans()
        self.engine._running_processes_under_root = lambda _: ['running.exe']
        with self.assertRaisesRegex(t.Refusal, 'Close'):
            runtime.apply(self.config, plans)
        self.engine._running_processes_under_root = lambda _: []
        self.engine.load_baseline = lambda *args, **kwargs: {'managed_paths': ['nvngx_dlss.dll']}
        with self.assertRaisesRegex(t.Refusal, 'ownership'):
            runtime.apply(self.config, plans)

    def test_partial_write_is_restored(self):
        plans = self.plans()
        original = t.atomic_file
        def fail_after_write(path, data, mode):
            original(path, data, mode)
            if Path(path)==self.dll and data==pe(2):
                raise OSError('simulated write failure')
        with patch.object(t, 'atomic_file', side_effect=fail_after_write):
            with self.assertRaisesRegex(t.Refusal, 'simulated write failure'):
                runtime.apply(self.config, plans)
        self.assertEqual(self.dll.read_bytes(), pe(1))

    def test_source_drift_refused(self):
        plans = self.plans()
        self.source.write_bytes(pe(3))
        with self.assertRaisesRegex(t.Refusal, 'Input drift'):
            runtime.apply(self.config, plans)

    def test_offline_inventory_is_read_only(self):
        with patch.object(runtime, 'catalog', side_effect=AssertionError('Unexpected network lookup')):
            found = runtime.inspect(self.config, self.games)[0]
        self.assertEqual(found['files'][0]['current'], '1.0.0.0')
        self.assertIsNone(found['files'][0]['target'])
        self.assertEqual(found['files'][0]['status'], 'Installed')
        self.assertEqual(self.dll.read_bytes(), pe(1))
        self.assertFalse(runtime.game_recoveries(self.config, self.game))

    def test_automatic_management_only_updates_older_known_versions(self):
        with patch.object(runtime, 'catalog', return_value=self.snapshot):
            for contents in (pe(2), pe(3), pe(1)[:128]):
                self.dll.write_bytes(contents)
                self.assertEqual(runtime.manage(self.config, self.games)['updated_games'], 0)
                self.assertEqual(self.dll.read_bytes(), contents)
            self.dll.write_bytes(pe(1))
            result = runtime.manage(self.config, self.games)
            self.assertEqual(result['updated_games'], 1)
            self.assertEqual(self.dll.read_bytes(), pe(2))
            runtime.restore_game(self.config, str(self.game))
            self.assertEqual(self.dll.read_bytes(), pe(1))

    def test_newer_and_same_versions_are_identified(self):
        self.dll.write_bytes(pe(3))
        self.assertEqual(runtime.inspect(self.config, self.games, self.snapshot)[0]['files'][0]['status'], 'Newer installed')
        self.dll.write_bytes(pe(2))
        self.assertEqual(runtime.inspect(self.config, self.games, self.snapshot)[0]['files'][0]['status'], 'Same version')
        self.assertFalse(self.plans())


if __name__ == '__main__':
    unittest.main()
