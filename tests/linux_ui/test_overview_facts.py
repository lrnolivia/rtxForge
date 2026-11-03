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

    def test_overview_keeps_three_cards_when_results_are_missing(self):
        cards = o.overview_cards({})
        self.assertEqual([title for title, _, _ in cards], ['Feature package', 'Compatibility', 'Features'])
        self.assertEqual(cards[1][1], 'No compatibility result')
        game = {'installed': True, 'runtime_provider': 'feeder', 'nr_enabled': False}
        cards = o.overview_cards(game, {'verdict': 'Working', 'source': 'list'})
        self.assertEqual(cards[1][1], 'Working · rtxForge list')
        self.assertEqual(cards[2][:2], ('Neural rendering', 'Disabled in saved settings · NR only'))

    def test_repair_uses_the_installed_package_and_profile(self):
        from unittest.mock import patch
        from desktop_service import DesktopService

        service = DesktopService.__new__(DesktopService)
        service.config = {}
        service.hardware = lambda: {'ready': True}
        row = {'name': 'Game', 'game': '/games/game', 'installed': True, 'installed_on': 'linux',
               'runtime_provider': 'y4my', 'feature_mode': 'nr-only',
               'install_provider': 'vulkan-native', 'vulkan_available': True}
        with patch('engine_bridge.check_scope'), \
             patch('library_media.load_settings', return_value={'runtime_provider': 'feeder'}), \
             patch('engine_bridge.prepare', return_value={'plans': []}) as prepare:
            service.prepare([row], 'nr-mfg', 'repair')
            _, rows, mode, operation, settings = prepare.call_args.args
            self.assertEqual((rows, mode, operation), ([row], 'nr-only', 'repair'))
            self.assertEqual(settings['runtime_provider'], 'y4my')
            self.assertFalse(settings['apply_requested_presets'])
            review = service.prepare([dict(row, feature_mode=None)], 'nr-mfg', 'repair')
            self.assertTrue(review['blocked'])
            prepare.assert_called_once()

    def test_mfg_card_uses_active_setting_over_saved_choices(self):
        game = {'installed': True, 'feature_mode': 'nr-mfg', 'mfg_saved_mode': 2}
        for settings, expected in (({'mfg_multiplier': 0, 'dynamic_mfg': 1}, 'Off'),
                                   ({'mfg_multiplier': 4, 'dynamic_mfg': 1}, 'Dynamic'),
                                   ({'mfg_multiplier': 4}, '4×'), ({'mfg_multiplier': 'auto'}, 'Auto'),
                                   ({}, 'Saved setting unavailable')):
            self.assertEqual(o.overview_cards(dict(game, **settings))[-1][:2],
                             ('Multi-Frame Generation', expected))
        self.assertEqual(len(o.overview_cards(dict(game, feature_mode='nr-only'))), 3)

    def test_extras_need_files_next_to_the_selected_executable(self):
        import tempfile
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / 'bin'
            target.mkdir()
            (target / 'Game.exe').touch()
            game = {'game': str(root), 'exe': 'bin/Game.exe'}
            (root / 'RenoDX.addon64').touch()
            (target / 'rtxforge-panel.addon64').touch()
            (target / 'dxgi.dll').write_bytes(b'Unrelated proxy')
            self.assertEqual(o.installed_extras(game), [])
            (target / 'dxgi.dll').write_bytes(b'ReShade')
            (target / 'RenoDX.addon64').touch()
            (target / 'Another.addon64').touch()
            (target / 'Preset.ini').write_text('Techniques=Example')
            shaders = target / 'reshade-shaders' / 'Shaders'
            shaders.mkdir(parents=True)
            (shaders / 'Example.fx').touch()
            self.assertEqual(o.installed_extras(game), ['RenoDX', 'ReShade', 'Filters', 'Presets', 'Add-ons'])

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
