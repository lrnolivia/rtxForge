"""Independent menus/welcome, supported keys, and original tuning preservation."""
from pathlib import Path
import itertools
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import overlay_policy as policy
import transactions as t


class OverlayPolicyTest(unittest.TestCase):
    def test_all_menu_intro_combinations_keep_rendering_and_effects(self):
        text = ('[Menu]\nOverlayMenu=false\nShortcutKey=0x77\n[DlssNr]\nEnabled=false\nWorkingScale=0.65\n'
                '[DLSSG]\nOverrideInterpolationCount=3\n[INPUT]\nKeyOverlay=45,1,0,0\nGamepadNavigation=1\n'
                '[GENERAL]\nPerformanceMode=0\n[OVERLAY]\nTutorialProgress=4\n'
                '[RenoDX.DLSS5]\nUiWelcomed=1\nNeuralUplift=1\nNRResolutionScale=0.65\nNRLocalStructure=1.0\n')
        for choices in itertools.product((False, True), repeat=4):
            settings = dict(zip(policy.DEFAULTS, choices)) | {'optiscaler_hotkey': 'F8'}
            result = t.ini(policy.reshade(policy.optiscaler(text, settings), settings))
            self.assertEqual(result.getboolean('Menu', 'DisableSplash'), not settings['optiscaler_intro'])
            self.assertEqual(result.get('Menu', 'ShortcutKey'), '0x77' if settings['optiscaler_ui'] else '0')
            self.assertEqual(result.get('INPUT', 'KeyOverlay'), '45,1,0,0' if settings['reshade_ui'] else '0,0,0,0')
            self.assertEqual(result.get('INPUT', 'GamepadNavigation'), '1' if settings['reshade_ui'] else '0')
            self.assertEqual(result.get('OVERLAY', 'TutorialProgress'), '0' if settings['reshade_intro'] else '4')
            self.assertEqual(result.get('RenoDX.DLSS5', 'UiWelcomed'), '0' if settings['reshade_intro'] else '1')
            for section in ('DlssNr', 'DLSSG', 'GENERAL'):
                self.assertEqual(dict(result[section]), dict(t.ini(text)[section]))
            self.assertEqual(result.get('Menu', 'OverlayMenu'), 'false')
            self.assertEqual(result.get('RenoDX.DLSS5', 'NeuralUplift'), '1')

    def test_disable_enable_restores_custom_shortcut_and_gamepad_without_stale_override(self):
        text = '[INPUT]\nKeyOverlay=45,1,0,0\nGamepadNavigation=1\n'
        off = policy.reshade(text, {'reshade_ui': False})
        self.assertEqual(policy.reshade(off, {'reshade_ui': False}), off)
        on = policy.reshade(off, {'reshade_ui': True})
        self.assertEqual(t.ini(on).get('INPUT', 'KeyOverlay'), '45,1,0,0')
        self.assertEqual(t.ini(on).get('INPUT', 'GamepadNavigation'), '1')
        edited = on.replace('45,1,0,0', '36,0,1,0')
        self.assertEqual(t.ini(policy.reshade(edited, {'reshade_ui': True})).get('INPUT', 'KeyOverlay'), '36,0,1,0')
        self.assertFalse(t.ini(on).has_section('RenoDX.DLSS5'))

    def test_preferences_are_boolean_and_intros_default_off(self):
        self.assertEqual(policy.options({}), policy.DEFAULTS)
        for value in (0, 'false', None, [], {}):
            with self.assertRaises(t.Refusal): policy.options({'reshade_intro': value})
        with self.assertRaises(t.Refusal): policy.optiscaler('[Menu]\n', {'optiscaler_hotkey': 'arbitrary'})

    def test_unchanged_reshade_policy_keeps_windows_line_endings_and_spacing(self):
        text = ('[INPUT]\r\nKeyOverlay = 45,1,0,0\r\nGamepadNavigation = 1\r\n'
                '[OVERLAY]\r\nTutorialProgress = 4\r\n[RenoDX.DLSS5]\r\nUiWelcomed = 1\r\n'
                '[rtxForge.UI]\r\nReShadeDisabled = 0\r\n')
        self.assertEqual(policy.reshade(text, {}), text)


if __name__ == '__main__': unittest.main()
