"""Linux starts on DLSS-Unlocked; Windows keeps y4my; saved choices are kept."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import library_media


class DefaultProviderTest(unittest.TestCase):
    def load(self, stored=None):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'settings.json'
            if stored is not None:
                path.write_text(json.dumps(stored))
            with mock.patch.object(library_media, 'settings_path', return_value=path):
                return library_media.load_settings({})

    def test_os_defaults(self):
        self.assertEqual(library_media.default_provider('posix'), 'dlss-unlocked')
        self.assertEqual(library_media.default_provider('nt'), 'y4my')

    @unittest.skipIf(os.name == 'nt', 'Linux default')
    def test_fresh_linux_settings_use_dlss_unlocked(self):
        self.assertEqual(library_media.DEFAULTS['runtime_provider'], 'dlss-unlocked')
        self.assertEqual(self.load()['runtime_provider'], 'dlss-unlocked')
        self.assertEqual(self.load({'theme': 'dark'})['runtime_provider'], 'dlss-unlocked')

    @unittest.skipUnless(os.name == 'nt', 'Windows default')
    def test_fresh_windows_settings_use_y4my(self):
        self.assertEqual(self.load()['runtime_provider'], 'y4my')

    def test_saved_choice_is_kept(self):
        for provider in ('y4my', 'skynizz', 'dlss-unlocked'):
            self.assertEqual(self.load({'runtime_provider': provider})['runtime_provider'], provider)


if __name__ == '__main__':
    unittest.main()
