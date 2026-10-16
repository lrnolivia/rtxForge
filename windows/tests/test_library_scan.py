"""Fresh discovery and pinned-build metadata on temporary library folders."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'windows/engine-host')]
import discovery
import library_scan


class Service:
    def __init__(self, libraries):
        self.roots = libraries

    def libraries(self):
        return self.roots

    def scan(self, library, extra=()):
        games = discovery.discover_games(library, [], include_unavailable=True) if library else []
        for path in extra:
            root = Path(path)
            game = discovery.inspect_game(discovery.Game('', root.name, str(root), 'Folder'))
            if game.exe:
                games.append(game)
        return [{'name': game.name, 'game': str(Path(game.root).resolve()), 'appid': game.appid,
                 'source': game.type, 'exe': game.exe} for game in games]


class LibraryScanTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.steam = self.root / 'SteamLibrary'
        (self.steam / 'steamapps/common').mkdir(parents=True)
        self.service = Service([self.steam])

    def game(self, root):
        root.mkdir(parents=True, exist_ok=True)
        (root / 'Game.exe').write_bytes(b'fixture')
        return root

    def manifest(self, folder='PRAGMATA', name='PRAGMATA', appid='3357650'):
        path = self.steam / 'steamapps' / f'appmanifest_{appid}.acf'
        path.write_text(f'"AppState" {{ "appid" "{appid}" "name" "{name}" "installdir" "{folder}" }}')

    def test_rescan_reads_new_and_moved_steam_installs(self):
        self.assertEqual(library_scan.scan(self.service), [])
        first = self.game(self.steam / 'steamapps/common/Original')
        self.manifest('Original')
        self.assertEqual(library_scan.scan(self.service)[0]['game'], str(first))
        moved = self.steam / 'steamapps/common/NewFolder'
        first.rename(moved)
        self.manifest('NewFolder')
        self.assertEqual(library_scan.scan(self.service)[0]['game'], str(moved))

    def test_collection_discovers_new_children_without_one_combined_game(self):
        collection = self.root / 'MyCollection'
        collection.mkdir()
        self.assertEqual(library_scan.scan(self.service, library_folders=[collection]), [])
        first = self.game(collection / 'One')
        self.assertEqual(len(library_scan.scan(self.service, library_folders=[collection])), 1)
        second = self.game(collection / 'Two')
        rows = library_scan.scan(self.service, [first], [collection])
        self.assertEqual({row['game'] for row in rows}, {str(first), str(second)})
        (collection / 'Empty').mkdir()
        self.assertEqual(len(library_scan.scan(self.service, library_folders=[collection])), 2)

    def test_old_parent_plus_child_registration_does_not_duplicate_entries(self):
        parent = self.root / 'PinnedBuilds'
        first = self.game(parent / 'PRAGMATA-22357085')
        second = self.game(parent / 'Valhalla-Test')
        rows = library_scan.scan(self.service, [parent, first])
        self.assertEqual({row['game'] for row in rows}, {str(first), str(second)})

    def test_pinned_build_inherits_art_metadata_but_keeps_independent_identity(self):
        live = self.game(self.steam / 'steamapps/common/PRAGMATA')
        pinned = self.game(self.steam / 'PinnedBuilds/PRAGMATA-22357085')
        self.manifest()
        rows = library_scan.scan(self.service, [pinned])
        self.assertEqual(len(rows), 2)
        copy = next(row for row in rows if row['game'] == str(pinned))
        self.assertEqual(copy['name'], 'PRAGMATA (Build 22357085)')
        self.assertEqual(copy['metadata_appid'], '3357650')
        self.assertIsNone(copy['appid'])
        self.assertEqual(copy['source'], 'Folder')
        self.assertIn(str(live), [row['game'] for row in rows])

    def test_unmatched_build_does_not_guess_an_app_identity(self):
        self.manifest('DifferentGame')
        pinned = self.game(self.steam / 'PinnedBuilds/PRAGMATA-22357085')
        self.assertNotIn('metadata_appid', library_scan.scan(self.service)[0])

    def test_missing_manual_folder_is_removed_on_rescan(self):
        root = self.game(self.root / 'Manual')
        self.assertEqual(len(library_scan.scan(self.service, [root])), 1)
        (root / 'Game.exe').unlink()
        self.assertEqual(library_scan.scan(self.service, [root]), [])


if __name__ == '__main__':
    unittest.main()
