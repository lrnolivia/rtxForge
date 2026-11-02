"""Presentation changes never merge installs or change their launch identity."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import library_identity as identity


class LibraryIdentityTests(unittest.TestCase):
    def row(self, number):
        return {'game': str(Path('/Games/Legendary/Game') / f'ME{number}/Binaries/Win64'),
                'exe': f'MassEffect{number}.exe', 'name': 'Collection title', 'appid': '1328670',
                'source': 'Steam', 'collection_game': '/Games/Legendary'}

    def test_trilogy_gets_distinct_names_without_changing_launch_or_install_keys(self):
        rows = [self.row(n) for n in (1, 2, 3)]
        originals = copy.deepcopy(rows)
        identity.decorate(rows, {})
        self.assertEqual([r['name'] for r in rows], [f'Mass Effect {n} (LE)' for n in (1, 2, 3)])
        for before, after in zip(originals, rows):
            for field in ('game', 'exe', 'appid', 'source', 'collection_game'):
                self.assertEqual(before[field], after[field])

    def test_rename_survives_fresh_scan_and_reset_returns_automatic_name(self):
        row = self.row(2)
        settings = {'game_names': {row['game'].upper(): '  My Shepard  '}}
        identity.decorate([row], settings)
        self.assertEqual(row['name'], 'My Shepard')
        fresh = self.row(2)
        identity.decorate([fresh], settings)
        self.assertEqual(fresh['name'], 'My Shepard')
        identity.decorate([fresh], {})
        self.assertEqual(fresh['name'], 'Mass Effect 2 (LE)')

    def test_arbitrary_install_can_be_renamed_without_affecting_another_copy(self):
        rows = [{'game': '/Games/One', 'exe': 'Game.exe', 'name': 'Detected'},
                {'game': '/Games/Two', 'exe': 'Game.exe', 'name': 'Detected'}]
        identity.decorate(rows, {'game_names': {'/Games/One': 'My title'}})
        self.assertEqual([r['name'] for r in rows], ['My title', 'Detected'])
        identity.decorate(rows, {})
        self.assertEqual(rows[0]['name'], 'Detected')

    def test_original_game_and_mismatched_exe_are_not_mistaken_for_le(self):
        row = {'game': '/Games/Mass Effect', 'exe': 'MassEffect1.exe', 'name': 'Mass Effect'}
        identity.decorate([row], {})
        self.assertEqual(row['name'], 'Mass Effect')
        row = self.row(2); row['exe'] = 'MassEffect3.exe'
        self.assertIsNone(identity.legendary_name(row))

    def test_invalid_preferences_are_ignored(self):
        for name in ('', '  ', 'a\nb', 'a\x00b', 'a' * 201, None, 1):
            row = self.row(1)
            identity.decorate([row], {'game_names': {row['game']: name}})
            self.assertEqual(row['name'], 'Mass Effect 1 (LE)')
        identity.decorate([self.row(1)], {'game_names': []})


if __name__ == '__main__':
    unittest.main()
