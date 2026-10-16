"""DLSS review, exact execution and recovery against temporary games only."""
import struct
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'windows/engine-host')]
import dlss_updates as updates
import runtime_updates as runtime
import transactions as t
import operation_session


def pe(major):
    data = bytearray(256)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64)
    data[64:70] = b'PE\0\0\x64\x86'
    struct.pack_into('<IIII', data, 128, 0xFEEF04BD, 0x10000, major << 16, 0)
    return bytes(data)


class Engine:
    def load_baseline(self, *args, **kwargs):
        return None

    def _running_processes_under_root(self, root):
        return []


class DlssUpdatesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.state = self.root / 'state'
        self.state.mkdir()
        self.engine = Engine()
        self.source = self.root / 'new.dll'
        self.source.write_bytes(pe(2))
        self.snapshot = {'repository': 'fixture/source', 'commit': 'a' * 40,
                         'entries': {name: {'name': name, 'version': '2.0.0.0'} for name in runtime.COMPONENTS}}
        for target, name, value in [(runtime, 'storage', lambda *args: self.state),
                                     (runtime, 'catalog', lambda config: self.snapshot),
                                     (runtime, 'download', lambda config, entry: self.source),
                                     (runtime.engine_bridge, 'module', lambda config: self.engine)]:
            mock = patch.object(target, name, value)
            mock.start()
            self.addCleanup(mock.stop)

    def game(self, folder, name=None, version=1):
        root = self.root / folder
        root.mkdir(parents=True)
        (root / 'Game.exe').write_bytes(pe(1))
        dll = root / 'Engine/Plugins/Halo.External/DLSS/Binaries/ThirdParty/Win64/nvngx_dlss.dll'
        dll.parent.mkdir(parents=True)
        dll.write_bytes(pe(version))
        return {'name': name or folder, 'game': str(root), 'blocked': 'No native DLSS-G detected'}, dll

    def test_exact_paths_versions_and_restoration(self):
        game, dll = self.game('Halo')
        save = dll.parent / 'save.dat'
        save.write_bytes(b'keep')
        review = updates.prepare({}, [game])
        self.assertIn('1.0.0.0 → 2.0.0.0', review['rows'][0]['detail'])
        self.assertIn('Engine/Plugins/Halo.External', review['rows'][0]['detail'])
        self.assertEqual(dll.read_bytes(), pe(1), 'Review must not write game files')
        result = updates.execute({}, review)
        self.assertEqual(result['updated_games'], 1)
        self.assertEqual(dll.read_bytes(), pe(2))
        runtime.restore({}, result['records'][0], True)
        self.assertEqual(dll.read_bytes(), pe(1))
        self.assertEqual(save.read_bytes(), b'keep')

    def test_current_newer_unknown_and_missing_explain_skips(self):
        for label, version, reason in [('Current', 2, 'match or exceed'), ('Newer', 3, 'match or exceed'),
                                       ('Unknown', 1, 'could not be verified'), ('Missing', 1, 'No eligible')]:
            with self.subTest(label=label):
                game, dll = self.game(label, version=version)
                if label == 'Unknown':
                    dll.write_bytes(pe(1)[:128])
                elif label == 'Missing':
                    dll.unlink()
                review = updates.prepare({}, [game])
                self.assertFalse(review['rows'])
                self.assertIn(reason, review['blocked'][0]['reason'])
                with self.assertRaisesRegex(t.Refusal, 'No newer'):
                    updates.execute({}, review)

    def test_same_names_and_duplicate_requests_preserve_installation_identity(self):
        steam, first = self.game('Steam/Halo', 'Halo')
        other, second = self.game('Other/Halo', 'Halo')
        unselected, untouched = self.game('Mafia')
        review = updates.prepare({}, [steam, other, steam])
        self.assertEqual({r['game'] for r in review['rows']}, {steam['game'], other['game']})
        self.assertEqual(updates.execute({}, review)['updated_games'], 2)
        self.assertEqual(first.read_bytes(), pe(2))
        self.assertEqual(second.read_bytes(), pe(2))
        self.assertEqual(untouched.read_bytes(), pe(1))

    def test_target_drift_fails_entire_selection_before_first_write(self):
        first, dll = self.game('Mafia')
        second, drift = self.game('Halo')
        review = updates.prepare({}, [first, second])
        drift.write_bytes(pe(3))
        with self.assertRaisesRegex(t.Refusal, 'Target drift'):
            updates.execute({}, review)
        self.assertEqual(dll.read_bytes(), pe(1))

    def test_source_drift_running_games_and_provider_ownership_still_refuse(self):
        game, dll = self.game('Halo')
        review = updates.prepare({}, [game])
        self.source.write_bytes(pe(3))
        with self.assertRaisesRegex(t.Refusal, 'Input drift'):
            updates.execute({}, review)
        self.source.write_bytes(pe(2))
        self.engine._running_processes_under_root = lambda root: ['game.exe']
        with self.assertRaisesRegex(t.Refusal, 'Close'):
            updates.execute({}, review)
        self.engine._running_processes_under_root = lambda root: []
        self.engine.load_baseline = lambda *args, **kwargs: {'managed_paths': ['nvngx_dlss.dll']}
        with self.assertRaisesRegex(t.Refusal, 'ownership'):
            updates.execute({}, review)
        self.assertEqual(dll.read_bytes(), pe(1))

    def test_anticheat_and_provider_files_are_not_updated(self):
        game, dll = self.game('Halo')
        anti = Path(game['game']) / 'EasyAntiCheat'
        anti.mkdir()
        (anti / 'EasyAntiCheat.exe').write_bytes(pe(1))
        review = updates.prepare({}, [game])
        self.assertIn('Anti-cheat', review['blocked'][0]['reason'])
        self.assertFalse(review['plans'])

    def install_review(self, games, operation='install'):
        return {'operation': operation, 'plans': [{'row': game} for game in games],
                'rows': [{'name': game['name'], 'detail': 'Feature installation'} for game in games]}

    def test_normal_install_and_repair_honor_the_native_update_setting(self):
        game, dll = self.game('Mafia')
        with patch.object(updates, 'prepare', side_effect=AssertionError('Unexpected update lookup')):
            updates.attach_install({}, self.install_review([game]), enabled=False)
            updates.attach_install({}, self.install_review([game], 'reset'))
            updates.attach_install({}, self.install_review([game], 'uninstall'))
            updates.attach_install({}, self.install_review([]))
        review = self.install_review([game], 'repair')
        updates.attach_install({}, review)
        self.assertIn('Native DLSS updates', review['rows'][0]['detail'])
        self.assertEqual(dll.read_bytes(), pe(1))
        review['plans'][0]['before_game']()
        self.assertEqual(dll.read_bytes(), pe(2))
        self.assertEqual(len(runtime.game_recoveries({}, game['game'])), 1)

    @staticmethod
    def copy_for_session(args, **kwargs):
        src, dst = map(Path, args[-2:])
        if src.is_dir():
            shutil.copytree(src, dst, copy_function=shutil.copy2)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return subprocess.CompletedProcess(args, 0)

    def test_install_failure_cancel_and_crash_restore_native_files_and_records(self):
        for action in ('failure', 'cancel', 'crash'):
            with self.subTest(action=action), patch.object(operation_session.subprocess, 'run', self.copy_for_session):
                game, dll = self.game(action)
                review = self.install_review([game])
                updates.attach_install({}, review)
                item = review['plans'][0]
                session = operation_session.Session(self.state / 'desktop-operations')
                checkpoint = session.capture(item['extra_checkpoint_paths'], label=game['name'])
                item['before_game']()
                self.assertEqual(dll.read_bytes(), pe(2))
                self.assertTrue(runtime.game_recoveries({}, game['game']))
                if action == 'crash':
                    operation_session.Session.load(session.root).recover()
                else:
                    session.seal(checkpoint)
                    if action == 'failure':
                        session.undo(checkpoint)
                    else:
                        session.rollback()
                self.assertEqual(dll.read_bytes(), pe(1))
                self.assertFalse(runtime.game_recoveries({}, game['game']))
                operation_session.LIVE.discard(str(session.root))

    def test_reserved_recovery_paths_are_scoped_and_each_game_has_its_own_record(self):
        first, dll = self.game('Mafia')
        second, other = self.game('Halo')
        plans = updates.prepare({}, [first, second])['plans']
        with self.assertRaisesRegex(t.Refusal, 'recovery path'):
            runtime.apply({}, plans, state_paths=[self.root / 'escape', self.state / 'runtime-transactions/valid'])
        self.assertEqual(dll.read_bytes(), pe(1))
        records = runtime.apply({}, plans)
        self.assertEqual(len(set(records)), 2)
        self.assertEqual(dll.read_bytes(), pe(2))
        self.assertEqual(other.read_bytes(), pe(2))


if __name__ == '__main__':
    unittest.main()
