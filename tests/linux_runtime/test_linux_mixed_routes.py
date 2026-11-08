"""The Linux desktop splits a selection by each game's route, as Windows and Game Mode do."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
sys.path[:0] = [str(Path(__file__).resolve().parents[2] / 'scripts')]
import cross_os  # noqa: E402
import desktop_service  # noqa: E402
import engine_bridge  # noqa: E402
import feeder_provider  # noqa: E402
import library_media  # noqa: E402
import vulkan_app  # noqa: E402


def game(name, **values):
    return {'name': name, 'game': '/games/' + name, 'exe': name + '.exe', **values}


ROWS = [game('Alan'), game('Bright', native_dlss=True), game('Fable', install_provider='feeder', feeder_available=True),
        game('Valley', install_provider='vulkan-native', vulkan_available=True)]


class MixedRoutesTest(unittest.TestCase):
    def setUp(self):
        self.service = desktop_service.DesktopService.__new__(desktop_service.DesktopService)
        self.service.config = {}
        self.service.hardware = lambda: {'ready': True}
        self.calls, self.ran = [], []
        check_scope = engine_bridge.check_scope

        def review(kind, rows, settings):
            check_scope(rows, settings.get('operation_scope'))
            return {'kind': kind, 'rows': [{'name': r['name']} for r in rows], 'blocked': [],
                    'plans': [{'row': r} for r in rows], 'names': [r['name'] for r in rows]}

        def engine_prepare(config, rows, mode, operation, settings):
            self.calls.append(('engine', settings['runtime_provider'], [r['name'] for r in rows], mode))
            return review('engine', rows, settings)

        def feeder_prepare(config, rows, mode, operation, settings, e):
            self.calls.append(('feeder', settings['runtime_provider'], [r['name'] for r in rows], mode))
            return review('feeder', rows, settings)

        def vulkan_prepare(config, rows, mode, operation, settings, e):
            self.calls.append(('vulkan', settings['runtime_provider'], [r['name'] for r in rows], mode))
            return review('vulkan-native', rows, settings)

        def ran(kind):
            return lambda review: self.ran.append((kind, review['names'])) or kind

        patches = [patch.object(cross_os, 'THIS_OS', 'linux'), patch.object(engine_bridge, 'module', lambda config: None),
                   patch.object(engine_bridge, 'prepare', engine_prepare), patch.object(feeder_provider, 'prepare', feeder_prepare),
                   patch.object(vulkan_app, 'prepare', vulkan_prepare), patch.object(engine_bridge, 'execute', ran('engine')),
                   patch.object(feeder_provider, 'execute', ran('feeder')), patch.object(vulkan_app, 'execute', ran('vulkan')),
                   patch.object(library_media, 'load_settings',
                                lambda config: {'runtime_provider': 'skynizz', 'game_packages': {'/games/Bright': 'dlss-unlocked'}})]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_each_game_takes_its_own_route_in_one_review(self):
        review = self.service.prepare(ROWS, 'nr-only', 'install')
        self.assertEqual(sorted(self.calls), [('engine', 'dlss-unlocked', ['Bright'], 'nr-only'),
                                              ('engine', 'skynizz', ['Alan', 'Valley'], 'nr-only'),
                                              ('feeder', 'skynizz', ['Fable'], 'nr-only')])
        self.assertEqual(review['kind'], 'engine')
        self.assertEqual(sorted(r['name'] for r in review['rows']), ['Alan', 'Bright', 'Fable', 'Valley'])
        self.assertEqual(len(review['companions']), 2)

    def test_feeder_games_in_an_nr_mfg_install_are_an_opt_in_offer(self):
        review = self.service.prepare_supported(ROWS, 'nr-mfg', 'install')
        self.assertEqual(sorted(call for call in self.calls if call[0] != 'feeder'),
                         [('engine', 'dlss-unlocked', ['Bright'], 'nr-mfg'), ('engine', 'skynizz', ['Alan'], 'nr-mfg'),
                          ('vulkan', 'vulkan-native', ['Valley'], 'nr-mfg')])
        self.assertEqual(sorted(r['name'] for r in review['rows']), ['Alan', 'Bright', 'Valley'])
        self.assertEqual([(o['reason_code'], o['games'], o['mfg']) for o in review['supported']],
                         [('feeder-nr-only', ['/games/Fable'], False)])
        self.service.execute(review)
        self.assertNotIn('feeder', [kind for kind, _ in self.ran], 'the offer runs only when chosen')

    def test_one_other_route_beside_feeder_is_one_ordinary_review(self):
        review = self.service.prepare([ROWS[0], ROWS[2]], 'nr-mfg', 'install')
        self.assertEqual(self.calls, [('engine', 'skynizz', ['Alan'], 'nr-mfg')])
        self.assertNotIn('companions', review)

    def test_one_route_is_one_ordinary_review(self):
        review = self.service.prepare(ROWS[:1] + [game('Cedar')], 'nr-mfg', 'install')
        self.assertEqual(self.calls, [('engine', 'skynizz', ['Alan', 'Cedar'], 'nr-mfg')])
        self.assertNotIn('companions', review)

    def test_each_part_checks_only_its_own_games_and_a_drifted_selection_still_refuses(self):
        scope = {'kind': 'filtered', 'games': [r['game'] for r in ROWS]}
        self.assertEqual(len(self.service.prepare(ROWS, 'nr-only', 'install', scope=scope)['rows']), 4)
        with self.assertRaisesRegex(Exception, 'no longer match'):
            self.service.prepare(ROWS, 'nr-only', 'install', scope=dict(scope, games=scope['games'][:3]))

    def test_every_part_runs_and_cancelling_stops_the_rest(self):
        review = self.service.prepare(ROWS, 'nr-mfg', 'install')
        self.service.execute(review)
        self.assertEqual(sorted(kind for kind, _ in self.ran), ['engine', 'engine', 'vulkan'])
        self.ran.clear()
        review = self.service.prepare(ROWS, 'nr-mfg', 'install')
        review['cancel_event'] = threading.Event()
        review['cancel_event'].set()
        self.service.execute(review)
        self.assertEqual(len(self.ran), 1, 'only the part already running finishes')

    def test_a_game_on_another_route_is_not_offered_again(self):
        review = self.service.prepare_supported(ROWS, 'nr-only', 'install')
        self.assertEqual(review['supported'], [])


if __name__ == '__main__':
    unittest.main()
