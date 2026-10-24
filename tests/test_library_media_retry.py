"""A cached lookup that found no artwork is retried within hours; one that found artwork keeps its cache."""
from pathlib import Path
import json
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import library_media


class ArtworkRetryTest(unittest.TestCase):
    def media(self, root, data, age):
        media = library_media.LibraryMedia.__new__(library_media.LibraryMedia)
        media.root = Path(root);media.config = {};media.shortcut_cache = {}
        media.settings = {'online_art': True, 'steam_metadata': False, 'cache_days': 7, 'network_timeout': 5}
        row = {'name': 'Example', 'appid': '10', 'source': 'Steam', 'game': '/x', 'exe': ''}
        import hashlib
        ident = hashlib.sha256(('10Example').encode()).hexdigest()[:24]
        (Path(root) / (ident + '.json')).write_text(json.dumps({'time': time.time() - age, 'data': data}))
        return media, row

    def lookups(self, data, age):
        with tempfile.TemporaryDirectory() as root:
            media, row = self.media(root, data, age)
            with mock.patch.object(media, 'steam_art', return_value={}), \
                 mock.patch.object(library_media, 'json_request', side_effect=OSError('offline')) as search, \
                 mock.patch.object(library_media, 'request', side_effect=OSError('offline')):
                media._enrich(row)
            return search.call_count

    def test_missing_artwork_is_retried_after_six_hours(self):
        self.assertGreater(self.lookups({'description': 'x'}, 7 * 3600), 0)

    def test_recent_missing_artwork_is_not_refetched(self):
        self.assertEqual(self.lookups({'description': 'x'}, 3600), 0)

    def test_found_artwork_keeps_the_full_cache_period(self):
        self.assertEqual(self.lookups({'poster': '/cached.image'}, 3 * 86400), 0)


if __name__ == '__main__':
    unittest.main()
