"""Toolkit-independent motion contract and theme persistence regressions."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'gui'))
sys.path.insert(0, str(ROOT / 'scripts'))
import game_mode_contract as contract
import library_media


class MotionContractTests(unittest.TestCase):
    def test_scroll_fade_boundaries_and_smoothness(self):
        for unit in (.7, 1, 1.3):
            for offset, extent, ends in ((0, 0, (1, 1)), (0, 1000, (1, 0)),
                                         (1000, 1000, (0, 1)), (500, 1000, (0, 0))):
                profile = contract.scroll_fade(700, offset, extent, unit)
                self.assertEqual(contract.scroll_fade_alpha(0, 700, *profile), ends[0])
                self.assertEqual(contract.scroll_fade_alpha(700, 700, *profile), ends[1])
                self.assertEqual(contract.scroll_fade_alpha(350, 700, *profile), 1)
            depth, top, bottom = contract.scroll_fade(700, 500, 1000, unit)
            values = [contract.scroll_fade_alpha(depth * i / 100, 700, depth, top, bottom) for i in range(101)]
            self.assertEqual(values, sorted(values))

    def test_profiles_are_bounded_and_regions_never_zoom(self):
        motion = contract.MOTION
        self.assertEqual(motion['schema'], 1)
        self.assertLessEqual(motion['press_ms'], 140)
        self.assertLessEqual(motion['focus_ms'], 220)
        self.assertLessEqual(motion['surface_ms'], 350)
        self.assertGreaterEqual(motion['focus_damping'], .9)
        self.assertLessEqual(motion['card_scale'], .03)
        self.assertTrue(all(0 < p['travel'] <= 16 and p['period_ms'] <= 220 for p in motion['page_regions']))
        self.assertNotIn('scale', motion['page_regions'][0])

    def test_existing_preferences_remain_linked(self):
        settings = {'theme': 'dark'}
        self.assertEqual(contract.theme_name(settings), 'dark')
        contract.set_theme(settings, 'light')
        self.assertEqual(settings['theme'], 'light')

    def test_unlink_preserves_appearance_and_isolates_both_directions(self):
        settings = {'theme': 'dark'}
        contract.link_themes(settings, False)
        self.assertEqual(contract.theme_name(settings), 'dark')
        contract.set_theme(settings, 'night')
        self.assertEqual(settings['theme'], 'dark')
        settings['theme'] = 'light'
        self.assertEqual(contract.theme_name(settings), 'night')
        contract.link_themes(settings, True)
        self.assertEqual(contract.theme_name(settings), 'light')

    def test_theme_and_accessibility_keys_survive_real_serializer(self):
        settings = dict(library_media.DEFAULTS, theme='light', game_mode_theme='night', game_mode_theme_linked=False, reduce_motion=True)
        with tempfile.TemporaryDirectory() as temporary:
            prior = library_media.settings_path
            try:
                library_media.settings_path = lambda _config: Path(temporary) / 'settings.json'
                library_media.save_settings({}, settings)
                restored = library_media.load_settings({})
            finally:
                library_media.settings_path = prior
        self.assertFalse(restored['game_mode_theme_linked'])
        self.assertTrue(restored['reduce_motion'])
        self.assertEqual(contract.theme_name(restored), 'night')

    def test_contract_data_round_trips_without_toolkit(self):
        self.assertEqual(json.loads(json.dumps(contract.MOTION)), contract.MOTION)
        with self.assertRaises(ValueError):
            contract.set_theme({}, 'unknown')


if __name__ == '__main__':
    unittest.main()
