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


if __name__ == '__main__':
    unittest.main()
