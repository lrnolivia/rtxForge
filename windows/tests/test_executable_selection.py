"""Read-only EXE selection stays inside the game and preserves restore ownership."""
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'windows/engine-host')]
import discovery
import executable_selection as selection
import transactions as t


def pe(path, machine=0x8664):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = bytearray(256)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64)
    data[64:68] = b'PE\0\0'
    struct.pack_into('<H', data, 68, machine)
    path.write_bytes(data)
    return path


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'game'
        self.old = pe(self.root / 'launcher.exe')
        self.exe = pe(self.root / 'bin/game.exe', 0x14c)
        self.row = {'game': str(self.root), 'exe': 'launcher.exe', 'name': 'game'}
        self.e = SimpleNamespace(STATE_ROOT=self.root.parent / 'state', load_baseline=lambda *a, **k: None)

    def test_selection_and_reset_are_read_only(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(selection.review(self.e, self.row, str(self.exe)), {'exe': 'bin/game.exe'})
        with selection.choices({str(self.root): 'bin/game.exe'}):
            self.assertEqual(discovery.choose_exe(self.root, 'game', [], [self.old]), self.exe)
            self.assertTrue(selection.decorate(dict(self.row))['executable_selected'])
        self.assertEqual(selection.review(self.e, self.row, None)['exe'], 'bin/game.exe')
        self.assertEqual({str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)

    def test_outside_traversal_and_non_pe_refused(self):
        outside = pe(self.root.parent / 'other.exe')
        invalid = self.root / 'invalid.exe'
        invalid.write_text('not an executable')
        for path in (outside, '../other.exe', invalid):
            with self.subTest(path=path), self.assertRaises(t.Refusal):
                selection.review(self.e, self.row, str(path))

    def test_stale_selection_retains_blocked_row(self):
        with selection.choices({str(self.root): 'missing.exe'}):
            row = selection.decorate(dict(self.row))
            self.assertIn('Choose another EXE', row['executable_error'])
            self.assertEqual(discovery.choose_exe(self.root, 'game', [], [self.old]), self.old)

    def test_active_ownership_cannot_be_orphaned(self):
        (self.root / '.rtxforge-install.json').write_text('{}')
        with self.assertRaisesRegex(t.Refusal, 'Restore'):
            selection.review(self.e, self.row, str(self.exe))

    def test_install_engine_reinspection_uses_the_chosen_exe_and_refuses_stale_choices(self):
        saved = {str(self.root): 'bin/game.exe'}
        engine = SimpleNamespace(choose_game_exe=lambda *args: self.old)
        selection.adapt_engine(engine, lambda: saved)
        self.assertEqual(engine.choose_game_exe(self.root, 'game', [self.old], []), self.exe)
        with selection.choices({str(self.root): 'launcher.exe'}):
            self.assertEqual(engine.choose_game_exe(self.root, 'game', [self.exe], []), self.old)
        saved[str(self.root)] = 'missing.exe'
        with self.assertRaises(t.Refusal):
            engine.choose_game_exe(self.root, 'game', [self.old], [])

    def test_automatic_review_uses_the_same_fresh_discovery_as_library(self):
        actual = pe(self.root / 'bin/FarCry5.exe')
        prerequisite = pe(self.root / 'Support/MicrosoftNetFramework4/dotNetFx.exe')
        with prerequisite.open('r+b') as stream:
            stream.truncate(67 * 1024**2)
        helper = pe(self.root / 'host64/dlss5-feed-host64.exe')
        engine = SimpleNamespace(choose_game_exe=lambda *args: prerequisite)
        selection.adapt_engine(engine, lambda: {})
        upscalers, exes, _ = discovery.scan_files(self.root)
        expected = discovery.choose_exe(self.root, 'Far Cry 5', upscalers, exes)
        self.assertEqual(expected, actual)
        self.assertEqual(engine.choose_game_exe(self.root, 'Far Cry 5', [prerequisite, helper], []), actual)
        actual.unlink()
        # A disappeared choice is freshly re-detected, rather than accepted
        # from the row or the original engine's stale candidate list.
        self.assertNotEqual(engine.choose_game_exe(self.root, 'Far Cry 5', [actual], []), actual)


if __name__ == '__main__':
    unittest.main()
