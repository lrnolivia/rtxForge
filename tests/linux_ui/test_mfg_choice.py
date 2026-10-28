import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'gui'))
import mfg_choice as m  # noqa: E402


class MfgChoiceTest(unittest.TestCase):
    def test_auto_custom_dynamic_values(self):
        self.assertEqual(m.to_values(True, m.AUTO, 4)['mfg_multiplier'], 'auto')
        custom = m.to_values(True, m.CUSTOM, 3)
        self.assertEqual((custom['mfg_multiplier'], custom['dynamic_mfg']), (3, 0))
        dynamic = m.to_values(True, m.DYNAMIC, 6)
        self.assertEqual((dynamic['mfg_multiplier'], dynamic['dynamic_mfg']), (6, 1))

    def test_off_keeps_mode_and_ratio_dormant(self):
        off = m.to_values(False, m.DYNAMIC, 5)
        self.assertEqual((off['mfg_multiplier'], off['dynamic_mfg']), (0, 0))
        self.assertEqual(m.from_values(off), (False, m.DYNAMIC, 5))

    def test_round_trip(self):
        for enabled in (True, False):
            for mode in m.MODES:
                for ratio in m.RATIOS:
                    values = m.to_values(enabled, mode, ratio)
                    back = m.from_values(values)
                    self.assertEqual(back[0], enabled)
                    self.assertEqual(back[1], mode)
                    if mode != m.AUTO or not enabled:
                        self.assertEqual(back[2], ratio)

    def test_dynamic_falls_back_to_custom_when_unsupported(self):
        values = m.to_values(True, m.DYNAMIC, 4, dynamic_available=False)
        self.assertEqual((values['mfg_multiplier'], values['dynamic_mfg'], values['mfg_saved_mode']), (4, 0, m.CUSTOM))

    def test_legacy_presets_still_read(self):
        self.assertEqual(m.from_values({'mfg_multiplier': 'auto'})[:2], (True, m.AUTO))
        self.assertEqual(m.from_values({'mfg_multiplier': 0})[0], False)
        self.assertEqual(m.from_values({'mfg_multiplier': 4}), (True, m.CUSTOM, 4))
        self.assertEqual(m.from_values({'mfg_multiplier': 9})[2], 2)

    def test_summary(self):
        self.assertEqual(m.summary(m.to_values(True, m.DYNAMIC, 4)), 'Dynamic up to 4×')
        self.assertEqual(m.summary({'mfg_multiplier': 0}), 'Off')

    def test_dynamic_follows_windows_support(self):
        # Library defaults: Skynizz with the Universal or Integrated component (DynamicMfgSupported).
        self.assertTrue(m.dynamic_supported({'runtime_provider': 'skynizz'}))
        self.assertTrue(m.dynamic_supported({'runtime_provider': 'skynizz', 'mfg_provider': 'integrated'}))
        self.assertFalse(m.dynamic_supported({'runtime_provider': 'skynizz', 'mfg_provider': 'mfg-unlock'}))
        self.assertFalse(m.dynamic_supported({'runtime_provider': 'dlss-unlocked'}))
        # One game: the scan row decides, whatever the library defaults say.
        self.assertFalse(m.dynamic_supported({'runtime_provider': 'skynizz'}, {'dynamic_mfg_available': False}))
        self.assertTrue(m.dynamic_supported({}, {'dynamic_mfg_available': True}))

    def test_dynamic_reason_names_the_game_detail(self):
        game = {'dynamic_mfg_detail': 'Launch the game once to check Dynamic support'}
        self.assertEqual(m.dynamic_reason(False, game), 'Dynamic: Launch the game once to check Dynamic support')
        self.assertEqual(m.dynamic_reason(True, game), '')
        self.assertEqual(m.dynamic_reason(False), '')


if __name__ == '__main__':
    unittest.main()
