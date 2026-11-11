import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import game_mode_appearance as appearance


class SharedAppearanceTests(unittest.TestCase):
    def test_missing_storage_does_not_replace_native_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'game-mode-appearance.json'
            self.assertIsNone(appearance.load(path=path))
            self.assertFalse(path.exists())

    def test_round_trip_preserves_all_native_options_and_background(self):
        value = dict(appearance.DEFAULTS, theme='dark', accentMode='adaptive', tintStrength=23,
                     text='large', navigation='bottom', detailsNavigation='tabs', scale=150,
                     libraryScale=115, background='data:image/png;base64,aGVsbG8=')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'game-mode-appearance.json'
            self.assertEqual(appearance.save(value, path=path), value)
            self.assertEqual(appearance.load(path=path), value)
            self.assertEqual(list(path.parent.glob('.game-mode-appearance-*')), [])

    def test_invalid_edit_keeps_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'game-mode-appearance.json'
            appearance.save(appearance.DEFAULTS, path=path)
            before = path.read_bytes()
            for change in ({'scale': True}, {'tintStrength': float('nan')}, {'libraryScale': 999},
                           {'background': 'https://example.test/image.png'}, {'accent': '#bad'},
                           {'theme': 'night'}, {'motion': 'false'}, {'unknown': 'value'}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    appearance.save(appearance.DEFAULTS | change, path=path)
                self.assertEqual(path.read_bytes(), before)

    def test_accent_source_preserves_custom_color_and_details_tint(self):
        saved = {'accent': '#3266A1', 'accentMode': 'adaptive'}
        self.assertEqual(appearance.normalize(saved)['accentSource'], 'custom')
        for source, _ in appearance.ACCENT_CHOICES:
            current = appearance.normalize(saved | {'accentSource': source})
            self.assertEqual(current['accentSource'], source)
            self.assertEqual(current['accent'], '#3266a1')
            self.assertEqual(current['accentMode'], 'adaptive')
        with self.assertRaises(ValueError):
            appearance.normalize(saved | {'accentSource': 'artwork'})

    def test_none_or_zero_tint_is_normalized(self):
        self.assertFalse(appearance.normalize(dict(appearance.DEFAULTS, accentMode='theme'))['tint'])
        self.assertFalse(appearance.normalize(dict(appearance.DEFAULTS, tintStrength=0))['tint'])

    def test_corrupt_or_large_storage_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'game-mode-appearance.json'
            for data in ('{', '[]', 'x' * (appearance.MAX_BYTES + 1)):
                path.write_text(data)
                with self.assertRaises(ValueError):
                    appearance.load(path=path)


if __name__ == '__main__':
    unittest.main()
