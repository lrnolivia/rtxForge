"""Fast inventory must retain executable, protected-game and ignore-directory behavior."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import discovery


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    def test_executables_and_native_upscalers_keep_original_paths(self):
        exe = self.file('Binaries/Win64/Game-Win64-Shipping.EXE')
        dlss = self.file('Binaries/Win64/NVNGX_DLSS.DLL')
        fg = self.file('Binaries/Win64/sl.dlss_g.extra.dll')
        self.file('setup.exe'); self.file('data/not-an-exe.exe.pak')
        self.file('data/Game.pak')
        upscalers, exes, anti = discovery.scan_files(self.root)
        self.assertEqual(set(upscalers), {dlss, fg})
        self.assertEqual(exes, [exe])
        self.assertIsNone(anti)

    def test_every_protected_filename_pattern_is_still_detected_case_insensitively(self):
        names = ['EasyAntiCheat_EOS.EXE', 'EAntiCheat.Game.EXE', 'BEService_x64.exe',
                 'BEDaisy_x64.SYS', 'Start_Protected_Game.EXE', 'ACE-Game.EXE']
        for name in names:
            with self.subTest(name=name):
                path = self.file(name)
                self.assertEqual(discovery.scan_files(self.root)[2], path)
                path.unlink()

    def test_protected_directory_evidence_and_non_matches(self):
        ordinary = self.file('data/EasyAntiCheat-readme.txt')
        self.assertIsNone(discovery.scan_files(self.root)[2])
        protected = self.file('BaTtLeYe/data.bin')
        self.assertEqual(discovery.scan_files(self.root)[2], protected)
        self.assertTrue(ordinary.is_file())

    def test_ignored_backups_and_digital_extras_stay_out_of_inventory(self):
        game = self.file('Game.exe')
        for folder in ('DigitalExtras', '_OptiScaler_MFG_Backup_123', '_TRUE_UNINSTALL_123', '.git'):
            self.file(folder + '/EasyAntiCheat.exe'); self.file(folder + '/Other.exe')
        self.assertEqual(discovery.scan_files(self.root), ([], [game], None))

    def test_public_walk_retains_its_file_limit(self):
        for number in range(5): self.file(f'{number}.dat')
        self.assertEqual(len(list(discovery.iter_walk(self.root, max_files=2))), 2)


if __name__ == '__main__':
    unittest.main()
