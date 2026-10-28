import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'gui'))
import overview_facts as o  # noqa: E402


class OverviewFactsTest(unittest.TestCase):
    """Matches Windows GameOverview.Facts."""

    def test_package_is_always_first(self):
        self.assertEqual(o.facts({})[0][:2], ('Feature package', 'Not installed'))
        installed = o.facts({'installed': True, 'runtime_provider': 'skynizz'})
        self.assertEqual(installed[0][:2], ('Feature package', 'Skynizz'))
        self.assertEqual(o.facts({'adoption_available': True, 'runtime_provider': 'x'})[0][1], 'Installed features')

    def test_library_only_when_not_steam_or_folder(self):
        self.assertNotIn('Library', dict(o.compact_facts({'source': 'Steam', 'library': 'Games drive'})))
        self.assertNotIn('Library', dict(o.compact_facts({'library': 'Folder'})))
        self.assertEqual(dict(o.compact_facts({'source': 'Heroic', 'library': '/mnt/games'}))['Library'], '/mnt/games')

    def test_dlss_version_and_feeder(self):
        rows = dict(o.compact_facts({'dlss_version': '310.4.0'}))
        self.assertEqual(rows['DLSS file version'], '310.4.0')
        feeder = dict(o.compact_facts({'installed': True, 'runtime_provider': 'feeder', 'nr_enabled': False,
                                       'nr_runtime': {'version': '310.9.16'}}))
        self.assertEqual(feeder['Neural rendering'], 'Model 310.9.16\nDisabled in saved settings · NR only')
        offer = dict(o.compact_facts({'install_provider': 'feeder', 'feeder_available': True}))
        self.assertEqual(offer['Available features'], 'Feeder NR · NR only')

    def test_every_fact_has_a_glyph(self):
        for _title, _value, icon in o.facts({'installed': True, 'runtime_provider': 'feeder', 'library': '/x', 'dlss_version': '1'}):
            self.assertTrue(icon.endswith('-symbolic'))

    def test_folder(self):
        self.assertEqual(o.folder({'game': '/g/Control'}), '/g/Control')



class InstalledOsMarksTest(unittest.TestCase):
    def test_one_mark_per_os_the_install_is_set_up_for(self):
        self.assertEqual(o.installed_oses({'installed': True, 'installed_on': 'windows'}), ['windows'])
        # A Windows install adapted for Linux (adopted or set up here) carries both.
        self.assertEqual(o.installed_oses({'installed': True, 'installed_on': 'linux', 'installed_oses': ['windows', 'linux']}),
                         ['windows', 'linux'])
        self.assertEqual(o.installed_oses({'installed': False, 'installed_oses': ['windows']}), [])
        self.assertEqual(o.os_tooltip(['windows', 'linux']), 'Set up for Windows and Linux')
        self.assertEqual(o.os_tooltip(['linux']), 'Installed with rtxForge on Linux')

    def test_the_scan_reads_every_os_from_the_shared_state(self):
        import json, tempfile
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
        import cross_os, desktop_service
        with tempfile.TemporaryDirectory() as root:
            state = cross_os.shared_state(root)
            state.mkdir(parents=True)
            (state / 'baseline.json').write_text(json.dumps({'cross_os_extras': {'linux': {}, 'windows': {}}}))
            self.assertEqual(desktop_service.installed_oses_from_state(root), ['windows', 'linux'])
            (state / 'baseline.json').write_text('not json')
            self.assertEqual(desktop_service.installed_oses_from_state(root), [])


if __name__ == '__main__':
    unittest.main()
