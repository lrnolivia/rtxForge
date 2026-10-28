import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'gui'))
import action_labels  # noqa: E402


class ProviderNameTest(unittest.TestCase):
    def test_every_provider_reads_as_a_name(self):
        for provider, name in (('skynizz', 'Skynizz'), ('feeder', 'Feeder NR'), ('dlss-unlocked', 'DLSS-Unlocked'),
                               ('custom', 'Custom package'), ('vulkan-native', 'Vulkan NR + Universal MFG')):
            self.assertEqual(action_labels.provider_name(provider), name)

    def test_y4my_is_short_in_reviews_and_full_in_game_mode(self):
        self.assertEqual(action_labels.provider_name('y4my'), 'y4my')
        self.assertEqual(action_labels.provider_name(None, short=False), 'y4my Multipass')


class AdaptLabelTest(unittest.TestCase):
    def test_windows_installs_take_over_install_and_restore(self):
        self.assertEqual(action_labels.game(windows_install=True), ('Adapt to Linux', 'Remove Linux Setup'))
        self.assertEqual(action_labels.game(), (action_labels.INSTALL, action_labels.RESTORE))
        self.assertEqual(action_labels.library(adapt=True)[:2], ('Adapt to Linux', 'Remove Linux Setup'))
        self.assertEqual(action_labels.library(3, adapt=True)[:2], ('Adapt Selected (3)', 'Remove Linux Setup (3)'))
        self.assertEqual(action_labels.library(3)[:2], ('Install Selected (3)', 'Restore Selected (3)'))


if __name__ == '__main__':
    unittest.main()
