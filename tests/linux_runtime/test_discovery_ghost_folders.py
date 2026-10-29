"""Leftover Non-Steam folders without a game are not listed as games."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import discovery  # noqa: E402


class GhostFolderTest(unittest.TestCase):
    def test_empty_non_steam_folders_are_not_games(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            library, nonsteam = root / 'SteamLibrary', root / 'Non-Steam Games'
            (library / 'steamapps/common/Broken').mkdir(parents=True)
            (library / 'steamapps/appmanifest_42.acf').write_text(
                '"AppState"\n{\n\t"appid"\t\t"42"\n\t"name"\t\t"Broken Steam Game"\n\t"installdir"\t\t"Broken"\n}\n')
            ghost = nonsteam / 'The Outer Worlds 2'
            ghost.mkdir(parents=True)
            (ghost / 'leftover').write_bytes(b'')
            real = nonsteam / 'Sonic Unleashed'
            real.mkdir()
            (real / 'UnleashedRecomp.exe').write_bytes(b'MZ' + b'\0' * 64)
            games = discovery.discover_games(library, [nonsteam], include_unavailable=True)
            names = {g.name for g in games}
            self.assertNotIn('The Outer Worlds 2', names)
            self.assertIn('Sonic Unleashed', names)
            # A Steam game without an executable is genuinely broken and still shows.
            self.assertIn('Broken Steam Game', names)


if __name__ == '__main__':
    unittest.main()
