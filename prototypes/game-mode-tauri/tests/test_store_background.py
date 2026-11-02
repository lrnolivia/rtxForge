import base64
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('store_background', Path(__file__).resolve().parents[1] / 'bridge/store_background.py')
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


def jpeg_header(width, height):
    return b'\xff\xd8\xff\xc0\x00\x11\x08' + struct.pack('>HH', height, width) + b'\x03' + b'\x00' * 9 + b'\xff\xd9'


class StoreBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cache = Path(self.directory.name)
        self.urls = ['https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/10/ss_' + str(i) + '.jpg' for i in range(3)]
        self.calls = []

    def tearDown(self):
        self.directory.cleanup()

    def download(self, url, limit):
        self.calls.append(url)
        if url.startswith('https://store.steampowered.com/api/'):
            return json.dumps({'10': {'success': True, 'data': {'screenshots': [{'path_full': url} for url in self.urls]}}}).encode()
        return jpeg_header(*((3840, 2160) if url == self.urls[1] else (1920, 1080)))

    def test_prefers_4k_original_and_reuses_disk_cache(self):
        first = store.background('10', self.cache, download=self.download, now=100)
        self.assertEqual((first['width'], first['height']), (3840, 2160))
        self.assertEqual(base64.b64decode(first['image'].split(',')[1]), jpeg_header(3840, 2160))
        self.assertEqual(len(self.calls), 3, 'Stop once a 4K screenshot has been found')
        second = store.background('10', self.cache, download=lambda *_: self.fail('Fresh cache must avoid the network'), now=101)
        self.assertEqual(second, first)

    def test_offline_retains_last_good_screenshot(self):
        first = store.background('10', self.cache, download=self.download, now=100)
        def offline(*_):
            raise OSError('offline')
        self.assertEqual(store.background('10', self.cache, download=offline, now=store.TTL + 200), first)

    def test_store_derivative_uses_original_screenshot_first(self):
        self.urls = [self.urls[0].replace('.jpg', '.1920x1080.jpg')]
        def download(url, limit):
            if url.startswith('https://store.steampowered.com/api/'):
                return self.download(url, limit)
            self.assertNotIn('.1920x1080.', url)
            return jpeg_header(3840, 2160)
        result = store.background('10', self.cache, download=download, now=100)
        self.assertEqual((result['width'], result['height']), (3840, 2160))
        self.assertNotIn('.1920x1080.', result['source'])

    def test_missing_screenshots_are_briefly_cached(self):
        empty = lambda *_: b'{"10":{"success":true,"data":{}}}'
        self.assertEqual(store.background('10', self.cache, download=empty, now=100), {'image': None})
        self.assertEqual(store.background('10', self.cache, download=lambda *_: self.fail('Negative cache must avoid repeat requests'), now=101), {'image': None})

    def test_individual_screenshots_share_catalog_not_image_bytes(self):
        first = store.background('10', self.cache, screenshot='0', download=self.download, now=100)
        second = store.background('10', self.cache, screenshot='1', download=self.download, now=101)
        self.assertEqual((first['width'], first['height']), (1920, 1080))
        self.assertEqual((second['width'], second['height']), (3840, 2160))
        self.assertEqual(len([url for url in self.calls if '/api/' in url]), 1)
        self.assertTrue((self.cache / '10-0.image').is_file())
        self.assertTrue((self.cache / '10-1.image').is_file())
        self.assertEqual(store.background('10', self.cache, screenshot='99', download=self.download, now=102), {'image': None})

    def test_rejects_foreign_urls_invalid_ids_and_broken_images(self):
        for url in ['http://shared.akamai.steamstatic.com/steam/apps/10/ss_0.jpg', 'https://example.com/steam/apps/10/ss_0.jpg', self.urls[0].replace('/10/', '/11/')]:
            self.assertFalse(store.allowed(url, '10'))
        for appid in ['../10', '0', '10&x=1', '12345678901']:
            with self.assertRaises(ValueError):
                store.background(appid, self.cache)
        for data in [b'', b'not an image', b'\xff\xd8\xff\xc0\x00\x00']:
            with self.assertRaises(ValueError):
                store.dimensions(data)

    def test_changed_cache_is_not_displayed(self):
        store.background('10', self.cache, download=self.download, now=100)
        (self.cache / '10.image').write_bytes(b'changed')
        def offline(*_):
            raise OSError('offline')
        self.assertEqual(store.background('10', self.cache, download=offline, now=101), {'image': None})

    def test_reviewed_clean_gallery_filters_cached_hud_frames_and_reordered_ids(self):
        appid = '3159330'
        approved = next(iter(store.CLEAN_SCREENSHOTS[appid]))
        clean = f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/ss_{approved}.1920x1080.jpg'
        hud = clean.replace(approved, '0' * 40)
        (self.cache / (appid + '.gallery.json')).write_text(json.dumps({'checked': 100, 'screenshots': [
            {'id': '0', 'full': hud}, {'id': '8', 'full': clean}]}), encoding='utf-8')
        self.assertEqual(store.gallery(appid, self.cache, now=101), [{'id': '8', 'full': clean}])
        data = jpeg_header(3840, 2160)
        (self.cache / (appid + '-0.image')).write_bytes(data)
        import hashlib
        (self.cache / (appid + '-0.json')).write_text(json.dumps({'version': 2, 'checked': 100,
            'source': hud, 'sha256': hashlib.sha256(data).hexdigest()}), encoding='utf-8')
        self.assertEqual(store.background(appid, self.cache, screenshot='0', now=101), {'image': None})

    def test_first_light_excludes_promotional_panels_even_when_previously_cached(self):
        appid = '3768760'
        hashes = ['ef374e5e4ede8c71f32d455652bc00f2fa7c035e',
                  '18787f52adabf0e5248548ed83562e6aac88f94d',
                  '43c8cf3875cb6643ac7d8244e9fd39381609814a']
        shots = [{'id': str(i), 'full': f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/ss_{value}.1920x1080.jpg'}
                 for i, value in enumerate(hashes)]
        (self.cache / (appid + '.gallery.json')).write_text(
            json.dumps({'checked': 100, 'screenshots': shots}), encoding='utf-8')
        self.assertEqual(store.gallery(appid, self.cache, now=101), shots[2:])
        for shot in shots[:2]:
            self.assertFalse(store.clean_screenshot(shot['full'], appid))


if __name__ == '__main__':
    unittest.main()
