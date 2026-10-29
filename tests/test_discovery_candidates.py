"""Prerequisites and editors must not become a game's install target."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import discovery


class ExecutableDiscoveryTest(unittest.TestCase):
    def test_small_game_stub_beats_prerequisite_and_editor(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'FarCry5'
            files = {'bin/FarCry5.exe': 200, 'bin/ArcadeEditor64.exe': 2000000,
                     'Support/Software/MicrosoftNetFramework 4.6.1/NDP461-KB3102436-x86-x64-AllOS-ENU.exe': 8000000}
            for name, size in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('wb') as stream:
                    stream.truncate(size)
            upscalers, exes, _ = discovery.scan_files(root)
            self.assertEqual({p.name for p in exes}, {'FarCry5.exe', 'ArcadeEditor64.exe'})
            self.assertEqual(discovery.choose_exe(root, 'Far Cry 5', upscalers, exes), root / 'bin/FarCry5.exe')

    def test_shipping_binary_keeps_precedence_over_title_launcher(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'Game'
            launcher = root / 'Game.exe'
            shipping = root / 'Game/Binaries/Win64/Game-Win64-Shipping.exe'
            shipping.parent.mkdir(parents=True)
            launcher.touch()
            shipping.touch()
            self.assertEqual(discovery.choose_exe(root, 'Game', [], [launcher, shipping]), shipping)


if __name__ == '__main__':
    unittest.main()
