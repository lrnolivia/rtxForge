"""Adapt to Linux over a library of Windows installs: each game keeps its own route."""
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


def row(name, provider='skynizz'):
    return {'name': name, 'game': '/games/' + name, 'installed_on': 'windows', 'runtime_provider': provider}


class AdaptMixedLibraryTest(unittest.TestCase):
    def setUp(self):
        self.service = desktop_service.DesktopService.__new__(desktop_service.DesktopService)
        self.service.config = {}
        self.service.hardware = lambda: {'ready': True}
        self.calls = []
        check_scope = engine_bridge.check_scope
        def engine_prepare(config, rows, mode, operation, settings):
            # The real engine checks its rows against the scope it is given.
            check_scope(rows, settings.get('operation_scope'))
            self.calls.append(('engine', [r['name'] for r in rows], mode))
            return {'kind': 'engine', 'operation': operation, 'rows': [{'name': r['name']} for r in rows], 'blocked': [], 'plans': []}
        def feeder_prepare(config, rows, mode, operation, settings, e):
            check_scope(rows, settings.get('operation_scope'))
            self.calls.append(('feeder', [r['name'] for r in rows], mode))
            return {'kind': 'feeder', 'operation': operation, 'rows': [{'name': r['name']} for r in rows], 'blocked': [], 'plans': []}
        patches = [patch.object(cross_os, 'THIS_OS', 'linux'), patch.object(engine_bridge, 'prepare', engine_prepare),
                   patch.object(feeder_provider, 'prepare', feeder_prepare), patch.object(engine_bridge, 'module', lambda config: None),
                   patch.object(library_media, 'load_settings', lambda config: {'runtime_provider': 'dlss-unlocked'})]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_mixed_library_is_one_review_with_each_games_own_route(self):
        review = self.service.prepare([row('007'), row('Mass Effect', 'feeder'), row('Hogwarts')], 'mfg-only', 'install')
        # Feeder always gets NR Only; the engine part keeps adopting with each install's own mode.
        self.assertEqual(sorted(self.calls), [('engine', ['007', 'Hogwarts'], 'mfg-only'), ('feeder', ['Mass Effect'], 'nr-only')])
        self.assertEqual(review['kind'], 'engine')
        self.assertEqual([r['name'] for r in review['rows']], ['007', 'Hogwarts', 'Mass Effect'])
        self.assertEqual(review['companions'][0]['kind'], 'feeder')

    def test_each_part_checks_only_its_own_games_against_the_selection(self):
        rows = [row('007'), row('Mass Effect', 'feeder'), row('Hogwarts')]
        scope = {'kind': 'filtered', 'games': [r['game'] for r in rows]}
        review = self.service.prepare(rows, 'mfg-only', 'install', scope=scope)
        self.assertEqual(len(review['rows']), 3)
        # A selection that drifted from the reviewed games still refuses up front.
        with self.assertRaisesRegex(Exception, 'no longer match'):
            self.service.prepare(rows, 'mfg-only', 'install', scope=dict(scope, games=scope['games'][:2]))

    def test_feeder_only_adapt_ignores_the_toolbar_mode(self):
        review = self.service.prepare([row('Mass Effect', 'feeder')], 'mfg-only', 'install')
        self.assertEqual(self.calls, [('feeder', ['Mass Effect'], 'nr-only')])
        self.assertEqual(review['kind'], 'feeder')

    def test_a_game_installed_here_keeps_the_normal_route(self):
        mixed = [row('007'), dict(row('Fresh'), installed_on=None)]
        self.service.prepare(mixed, 'mfg-only', 'install')
        self.assertEqual(self.calls, [('engine', ['007', 'Fresh'], 'mfg-only')])

    def test_execute_runs_the_feeder_companion_after_the_engine_part(self):
        order = []
        companion = {'kind': 'feeder', 'rows': [{'name': 'Mass Effect'}]}
        review = {'kind': 'engine', 'rows': [], 'companions': [companion], 'cancel_event': threading.Event()}
        with patch.object(engine_bridge, 'execute', lambda r: order.append('engine') or 'engine-path'), \
             patch.object(feeder_provider, 'execute', lambda r: order.append('feeder') or 'feeder-path'):
            self.assertEqual(self.service.execute(review), 'feeder-path')
        self.assertEqual(order, ['engine', 'feeder'])
        review['cancel_event'].set();order.clear()
        with patch.object(engine_bridge, 'execute', lambda r: order.append('engine')), \
             patch.object(feeder_provider, 'execute', lambda r: order.append('feeder')):
            self.service.execute(review)
        self.assertEqual(order, ['engine'], 'a cancelled review stops before the Feeder part')


if __name__ == '__main__':
    unittest.main()
