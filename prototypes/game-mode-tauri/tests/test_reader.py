import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('read_snapshot', Path(__file__).resolve().parents[1] / 'bridge/read_snapshot.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        shutil.copyfile(ROOT / 'scripts/discovery.py', self.root / 'scripts/discovery.py')
        (self.root / 'providers').mkdir()
        (self.root / 'providers/lock.json').write_text(json.dumps({'test': {'name': 'Fixture provider', 'tag': 'fixture-v1', 'sha256': 'a' * 64}}))
        self.steam = self.root / 'steam'
        (self.steam / 'steamapps/common/Fixture Game').mkdir(parents=True)
        self.settings = self.root / 'settings.json'
        self.settings.write_text('{}')
        self.manifest('10', 'Fixture Game', 'Fixture Game')

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, appid, title, folder):
        (self.steam / f'steamapps/appmanifest_{appid}.acf').write_text(f'"AppState" {{ "appid" "{appid}" "name" "{title}" "installdir" "{folder}" }}')

    def collect(self):
        return reader.collect(self.root, settings_file=self.settings, roots=[self.steam])

    def hashes(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}

    def test_real_manifest_parser_and_read_only_snapshot(self):
        before = self.hashes()
        snapshot = self.collect()
        self.assertEqual(['Fixture Game'], [g['name'] for g in snapshot['games']])
        self.assertEqual('Not checked', snapshot['games'][0]['status'])
        self.assertFalse(snapshot['operations']['available'])
        self.assertEqual(before, self.hashes())

    def test_missing_game_and_traversal_manifest_are_excluded(self):
        self.manifest('11', 'Missing game', 'Not installed')
        self.manifest('12', 'Outside', '../outside')
        self.manifest('13', 'Windows traversal', '..\\outside')
        self.assertEqual(1, len(self.collect()['games']))

    def test_malformed_settings_does_not_erase_library(self):
        self.settings.write_text('[]')
        snapshot = self.collect()
        self.assertEqual(1, len(snapshot['games']))
        self.assertEqual(1, len(snapshot['warnings']))

    def test_removed_game_and_saved_folders(self):
        folder = self.root / 'Saved fixture'
        folder.mkdir()
        self.settings.write_text(json.dumps({'extra_folders': [str(folder)], 'removed_games': [str(self.steam / 'steamapps/common/Fixture Game')]}))
        snapshot = self.collect()
        self.assertEqual(['Saved fixture'], [g['name'] for g in snapshot['games']])
        self.assertEqual('Saved folder', snapshot['games'][0]['source'])

    def test_invalid_cached_art_is_not_sent_as_image(self):
        cache = self.steam / 'appcache/librarycache'
        cache.mkdir(parents=True)
        (cache / '10_library_600x900.jpg').write_text('<script>not an image</script>')
        self.assertIsNone(self.collect()['games'][0]['art'])

    def test_saved_settings_are_displayed_without_writes_or_private_keys(self):
        self.settings.write_text(json.dumps({'borderless_4k': True, 'recognize_previous': False,
            'overlay_appearance': {'Layout': 'bar', 'TextSize': 26}, 'private_fixture_key': 'not-for-display'}))
        before = self.hashes()
        snapshot = self.collect()
        self.assertTrue(snapshot['preferences']['borderless_4k'])
        self.assertFalse(snapshot['preferences']['recognize_previous'])
        self.assertEqual({'Layout': 'bar', 'TextSize': 26}, snapshot['preferences']['overlay_appearance'])
        self.assertNotIn('private_fixture_key', snapshot['preferences'])
        self.assertEqual(before, self.hashes())

    def test_native_folders_collections_and_cached_child_identity_stay_unverified(self):
        manual = self.root / 'Native game'
        manual.mkdir()
        collection = self.root / 'Collection'
        child = collection / 'Collection game'
        child.mkdir(parents=True)
        cached = self.root / 'Exact cached child'
        cached.mkdir()
        self.settings.write_text(json.dumps({'game_folders':[str(manual)], 'library_folders':[str(collection)]}))
        snapshot = self.root / 'state/library-snapshot.json'
        snapshot.parent.mkdir()
        snapshot.write_text(json.dumps({'schema':1,'rows':[{'game':str(cached),'name':'Saved child identity','installed':True}]}))
        before = self.hashes()
        result = self.collect()
        self.assertEqual(4,len(result['games']))
        saved = next(game for game in result['games'] if game['path']==str(cached))
        self.assertEqual('Saved child identity',saved['name'])
        self.assertEqual('Saved library check',saved['provenance'])
        self.assertEqual('Not checked',saved['status'])
        self.assertTrue(saved['savedRecord']['installed'])
        self.assertFalse(result['operations']['available'])
        self.assertEqual(before,self.hashes())

    def test_metadata_uses_the_existing_library_id_and_title_cache_key(self):
        folder = self.settings.parent / 'media'
        folder.mkdir()
        key = hashlib.sha256('10Fixture Game'.encode()).hexdigest()[:24]
        (folder / (key+'.json')).write_text(json.dumps({'data':{'developers':'Fixture studio','release':'Fixture date'}}))
        before = self.hashes()
        game = self.collect()['games'][0]
        self.assertEqual('Fixture studio',game['developers'])
        self.assertEqual('Fixture date',game['release'])
        self.assertEqual(before,self.hashes())

    def test_exact_game_accent_focus_and_saved_metadata_are_display_only(self):
        game = str(self.steam / 'steamapps/common/Fixture Game')
        self.settings.write_text(json.dumps({'game_accents': {game: '#37aadd'}, 'game_hero_focus': {game: [.7,.3]}}))
        snapshot = self.settings.parent / 'state/library-snapshot.json'
        snapshot.parent.mkdir()
        snapshot.write_text(json.dumps({'schema': 1, 'rows': [{'game': game, 'installed': True, 'runtime_provider': 'fixture',
                       'test_record': {'status': 'Working'}, 'art': {'developers': ['Fixture studio'], 'release': 'Fixture date'}}]}))
        saved = snapshot.read_bytes()
        result = self.collect()['games'][0]
        self.assertEqual('#37aadd', result['accent'])
        self.assertEqual([.7,.3], result['heroFocus'])
        self.assertEqual('Working', result['testStatus'])
        self.assertEqual(['Fixture studio'], result['developers'])
        self.assertTrue(result['savedRecord']['installed'])
        self.assertEqual('Not checked', result['status'])
        self.assertEqual(saved, snapshot.read_bytes())

    def test_saved_artwork_is_authoritative_and_large_images_load_by_opaque_id(self):
        game = str(self.steam / 'steamapps/common/Fixture Game')
        image = self.root / 'custom.png'
        image.write_bytes(b'\x89PNG\r\n\x1a\n' + b'x' * 1100000)
        saved = self.settings.parent / 'state/library-snapshot.json'
        saved.parent.mkdir()
        saved.write_text(json.dumps({'schema': 1, 'rows': [{'game': game, 'appid': '10', 'name': 'Fixture Game', 'art': {'poster': str(image)}}]}))
        before = self.hashes()
        item = self.collect()['games'][0]
        self.assertIn('poster', item['localArtwork'])
        self.assertTrue(reader.local_artwork(item['id'],'poster',settings_file=self.settings).startswith('data:image/png;base64,'))
        self.assertIsNone(reader.local_artwork(str(image),'poster',settings_file=self.settings))
        with self.assertRaises(ValueError):
            reader.local_artwork(item['id'],'../../settings.json',settings_file=self.settings)
        self.assertEqual(before,self.hashes())


if __name__ == '__main__':
    unittest.main()
