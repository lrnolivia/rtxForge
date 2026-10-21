import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('sample_export', Path(__file__).with_name('export_sample.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExportTests(unittest.TestCase):
    def test_display_allowlist_duplicate_install_and_extensionless_art(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            png = root / 'cached.hero'
            png.write_bytes(b'\x89PNG\r\n\x1a\n' + b'fixture')
            settings = root / 'settings.json'
            settings.write_text(json.dumps({'secret': 'must-not-copy', 'game_artwork': {}}))
            rows = [{'game': 'G:/Games/' + str(index), 'name': 'Same title', 'source': 'Folder',
                     'art': {'hero': str(png)}, 'installed': True, 'managed': True,
                     'operation_token': 'must-not-copy', 'test_record': {'notes': 'private notes'}} for index in range(2)]
            snapshot = root / 'snapshot.json'
            snapshot.write_text(json.dumps({'schema': 1, 'rows': rows}))
            before = settings.read_bytes()
            saved = os.environ.get('LOCALAPPDATA')
            try:
                os.environ['LOCALAPPDATA'] = str(root)
                target = root / 'rtxForge-samples' / 'fixture'
                receipt = module.export(snapshot, settings, target)
                text = (target / 'library.json').read_text()
                games = json.loads(text)['games']
                self.assertEqual(receipt['catalog_count'], 2)
                self.assertNotEqual(games[0]['id'], games[1]['id'])
                self.assertTrue(games[0]['hero'].endswith('.png'))
                for forbidden in ('must-not-copy', 'private notes', 'G:/Games', 'operation_token', 'managed'):
                    self.assertNotIn(forbidden, text)
                self.assertEqual(settings.read_bytes(), before)
                with self.assertRaises(ValueError):
                    module.export(snapshot, settings, target)
                with self.assertRaises(ValueError):
                    module.export(snapshot, settings, root / 'outside-sample')
                snapshot.write_text('{invalid')
                with self.assertRaises(ValueError):
                    module.export(snapshot, settings, root / 'rtxForge-samples' / 'bad')
            finally:
                if saved is None:
                    os.environ.pop('LOCALAPPDATA', None)
                else:
                    os.environ['LOCALAPPDATA'] = saved


if __name__ == '__main__':
    unittest.main()
