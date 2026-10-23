from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import overlay_settings as overlay
import transactions as t


class OverlaySettingsTest(unittest.TestCase):
    def test_per_game_choices_do_not_leak_to_another_game(self):
        game = str(Path('game-a').resolve())
        settings = {'overlay_welcome': True, 'game_overlay_settings': {game: {
            'overlay_welcome': False, 'overlay_welcome_position': 'bottom-right', 'panel_hotkey': 'End'}}}
        self.assertFalse(overlay.effective(settings, game)['overlay_welcome'])
        self.assertEqual(overlay.effective(settings, game)['panel_hotkey'], 'End')
        self.assertTrue(overlay.effective(settings, str(Path('game-b').resolve()))['overlay_welcome'])
        self.assertEqual(settings['overlay_welcome'], True)

    def test_invalid_choices_refuse(self):
        for changes in ({'overlay_welcome': 1}, {'overlay_renderer': 'unknown'},
                        {'overlay_welcome_position': 'outside'}, {'panel_hotkey': 'Ctrl+Alt+Delete'}):
            with self.subTest(changes=changes), self.assertRaises((t.Refusal, ValueError)):
                overlay.options(changes)

    def test_review_includes_menu_and_startup_choices(self):
        text = overlay.describe(overlay.DEFAULTS)
        for label in ('Overlay:', 'Welcome message:', 'Welcome position:', 'rtxForge shortcut:',
                      'OptiScaler menu:', 'ReShade welcome:', 'Native Vulkan MFG menu:'):
            self.assertIn(label, text)


if __name__ == '__main__':
    unittest.main()
