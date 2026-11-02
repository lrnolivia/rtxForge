"""Presentation changes never merge installs or change their launch identity."""
import copy
from pathlib import Path
import sys
import unittest
import hashlib
import json
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

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

    def test_campaign_metadata_uses_each_game_without_changing_the_launcher(self):
        import library_media
        with tempfile.TemporaryDirectory() as folder:
            media = library_media.LibraryMedia.__new__(library_media.LibraryMedia)
            media.root = Path(folder); media.config = {}; media.shortcut_cache = {}
            media.settings = {**library_media.DEFAULTS, 'online_art': False}
            looked_up = []
            def request(url):
                appid = parse_qs(urlparse(url).query)['appids'][0]
                looked_up.append(appid)
                return {appid: {'success': True, 'data': {
                    'short_description': 'Campaign ' + appid, 'developers': ['BioWare'],
                    'genres': [{'description': 'RPG'}], 'release_date': {'date': 'Steam port date'},
                }}}
            results = []
            with patch.object(media, 'steam_art', return_value={}), patch.object(library_media, 'json_request', side_effect=request):
                for number in (1, 2, 3):
                    row = self.row(number)
                    # A fresh collection record must not suppress the new campaign lookup.
                    old = hashlib.sha256(('1328670' + row['name']).encode()).hexdigest()[:24]
                    (media.root / (old + '.json')).write_text(json.dumps({'time': 9999999999, 'data': {'description': 'Collection'}}))
                    results.append(media._enrich(row))
                    self.assertEqual(row['appid'], '1328670')
            self.assertEqual(looked_up, ['17460', '24980', '1238020'])
            self.assertEqual([r['description'] for r in results], ['Campaign 17460', 'Campaign 24980', 'Campaign 1238020'])
            self.assertEqual([r['release'] for r in results], ['2007 · LE 2021', '2010 · LE 2021', '2012 · LE 2021'])

    def test_steam_art_reads_each_shortcut_including_its_logo(self):
        import library_media
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'Steam'; (root / 'config').mkdir(parents=True)
            (root / 'config/loginusers.vdf').write_text('"76561197960265770" { "Timestamp" "10" }')
            grid = root / 'userdata/42/config/grid'; grid.mkdir(parents=True)
            (grid.parent / 'shortcuts.vdf').write_bytes(b'fixture')
            shortcuts = [{'exe': str(root / 'steam.exe'), 'LaunchOptions': f'-applaunch 1328670 -game {n} -autoterminate',
                          'appid': 0x80000000 + n} for n in (1, 2, 3)]
            engine = SimpleNamespace(parse_shortcuts_spans=lambda data: shortcuts,
                _shortcut_string=lambda row, key: row.get(key, ''), _shortcut_int=lambda row, key: row.get(key))
            media = library_media.LibraryMedia.__new__(library_media.LibraryMedia)
            media.config = {}; media.settings = {}; media.shortcut_cache = {}; media.engine = engine
            for n in (1, 2, 3):
                for suffix in ('p', '', '_hero', '_logo'):
                    (grid / (str(0x80000000 + n) + suffix + '.png')).write_bytes(b'current Steam selection')
            (grid / '1328670p.png').write_bytes(b'collection')
            with patch('discovery.steam_roots', return_value=[root]):
                for n in (1, 2, 3):
                    art = media.steam_art(self.row(n))
                    self.assertEqual(Path(art['poster']).name, f'{0x80000000 + n}p.png')
                    self.assertEqual(Path(art['logo']).name, f'{0x80000000 + n}_logo.png')
                shortcuts.clear()
                self.assertEqual(media.steam_art(self.row(1)), {})


if __name__ == '__main__':
    unittest.main()
