import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'gui'))
import overview_facts as o  # noqa: E402


class OverviewFactsTest(unittest.TestCase):
    def test_installed_game_shows_package_and_state_not_hero_facts(self):
        game = {'installed': True, 'runtime_provider': 'skynizz', 'profile': 'NR + MFG', 'native_dlss': True,
                'nr_enabled': False, 'installed_on': 'windows', 'source': 'Steam', 'library': 'Games drive',
                'developers': 'Remedy', 'release': '2019', 'game': '/g/Control'}
        titles = dict(o.compact_facts(game))
        self.assertEqual(titles['Package'], 'Skynizz NR + Universal MFG')
        self.assertEqual(titles['NR at launch'], 'Off')
        self.assertEqual(titles['Installed on'], 'Windows')
        for hero_fact in ('Developer', 'Release', 'Library', 'Compatibility'):
            self.assertNotIn(hero_fact, titles)
        self.assertEqual(o.folder(game), '/g/Control')

    def test_non_steam_library_is_shown_and_uninstalled_hides_package(self):
        titles = dict(o.compact_facts({'source': 'Heroic', 'library': '/mnt/games', 'runtime_provider': 'y4my'}))
        self.assertEqual(titles, {'Library': '/mnt/games'})


if __name__ == '__main__':
    unittest.main()
