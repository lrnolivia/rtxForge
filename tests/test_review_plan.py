"""The one review plan: Windows Desktop rules (EngineForgeService), used by Game Mode and the hosts."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import review_plan as plan  # noqa: E402

SETTINGS = {'runtime_provider': 'skynizz'}


def game(name, **values):
    return {'name': name, 'game': f'/games/{name}', 'exe': f'{name}.exe', **values}


class RouteTest(unittest.TestCase):
    def test_routes_follow_the_desktop_rules(self):
        route = lambda row, operation='install', mode='nr-mfg', settings=SETTINGS: plan.route(row, operation, mode, settings)
        self.assertEqual(route(game('A', adoption_available=True)), 'adopt')
        self.assertEqual(route(game('A', adoption_available=True), 'repair'), 'skynizz')
        # A confirmed Vulkan game takes the Vulkan package, except NR Only on a fresh install.
        vulkan = game('V', install_provider='vulkan-native', vulkan_available=True)
        self.assertEqual(route(vulkan), 'vulkan-native')
        self.assertEqual(route(vulkan, mode='nr-only'), 'skynizz')
        self.assertEqual(route(dict(vulkan, vulkan_available=False)), 'skynizz', 'unconfirmed Vulkan stays on its package')
        self.assertEqual(route(game('V', runtime_provider='vulkan-native', installed=True), mode='nr-only'), 'vulkan-native')
        self.assertEqual(route(game('F', runtime_provider='feeder')), 'feeder')
        self.assertEqual(route(game('F', install_provider='feeder', feeder_available=True)), 'feeder')
        self.assertEqual(route(game('F', install_provider='feeder')), 'skynizz', 'Feeder only where the scan admitted it')

    def test_each_game_may_choose_its_package_and_a_repair_keeps_the_installed_one(self):
        settings = dict(SETTINGS, game_packages={'/games/B': 'dlss-unlocked', '/games/C': 'not-a-package'})
        self.assertEqual(plan.route(game('B'), 'install', 'nr-mfg', settings), 'dlss-unlocked')
        self.assertEqual(plan.route(game('C'), 'install', 'nr-mfg', settings), 'skynizz')
        installed = game('B', installed=True, runtime_provider='skynizz')
        self.assertEqual(plan.route(installed, 'repair', 'nr-mfg', settings), 'skynizz')
        self.assertEqual(plan.route(dict(installed, runtime_provider='y4my'), 'repair', 'nr-mfg', settings), 'dlss-unlocked')
        # Uninstall, reset and apply use the selected package; the engine restores from each game's record.
        self.assertEqual(plan.route(game('B'), 'uninstall', 'nr-mfg', settings), 'skynizz')

    def test_steps_keep_the_package_setting_for_feeder_and_adoption(self):
        self.assertEqual(plan.step('feeder', 'install', SETTINGS), ('install', 'skynizz'))
        self.assertEqual(plan.step('adopt', 'install', SETTINGS), ('adopt', 'skynizz'))
        self.assertEqual(plan.step('vulkan-native', 'repair', SETTINGS), ('repair', 'vulkan-native'))

    def test_applying_presets_never_reinstalls_a_package(self):
        # DLSS packages re-apply presets with the engine's preset reset; Feeder saves its ReShade.ini.
        self.assertEqual(plan.step('skynizz', 'apply', SETTINGS), ('reset', 'skynizz'))
        self.assertEqual(plan.step('feeder', 'apply', SETTINGS), ('apply', 'skynizz'))
        self.assertEqual(plan.step('skynizz', 'reset', SETTINGS), ('reset', 'skynizz'))


class BatchTest(unittest.TestCase):
    def test_consecutive_games_on_one_route_share_a_batch_in_name_order(self):
        rows = [game('d'), game('B', runtime_provider='feeder'), game('a'), game('C', runtime_provider='feeder')]
        groups = plan.batches(rows, 'install', 'nr-mfg', SETTINGS)
        self.assertEqual([(name, [row['name'] for row in group]) for name, group in groups],
                         [('skynizz', ['a']), ('feeder', ['B', 'C']), ('skynizz', ['d'])])

    def test_a_large_selection_on_one_route_is_checked_once_and_keeps_every_game(self):
        rows = [game(f'Game {index:02}') for index in range(48)]
        self.assertEqual([(name, len(group)) for name, group in plan.batches(rows, 'install', 'nr-mfg', SETTINGS)], [('skynizz', 48)])
        mixed = [dict(row, runtime_provider='feeder') if 10 <= index < 20 else row for index, row in enumerate(rows)]
        groups = plan.batches(mixed, 'install', 'nr-mfg', SETTINGS)
        self.assertEqual([name for name, _ in groups], ['skynizz', 'feeder', 'skynizz'])
        self.assertEqual([row['name'] for _, group in groups for row in group], [row['name'] for row in rows])
        self.assertEqual(plan.batches([], 'install', 'nr-mfg', SETTINGS), [])

    def test_downloads_cover_each_route_once_and_never_adoption(self):
        rows = [game('A'), game('B', runtime_provider='feeder'), game('C'), game('D', adoption_available=True)]
        groups = plan.batches(rows, 'install', 'nr-mfg', SETTINGS)
        self.assertEqual([item['settings']['runtime_provider'] for item in plan.prefetch(groups, 'install', 'nr-mfg', SETTINGS)],
                         ['skynizz', 'feeder'])
        self.assertEqual(plan.prefetch(groups, 'uninstall', 'nr-mfg', SETTINGS), [])


class OfferTest(unittest.TestCase):
    def test_offers_only_what_a_game_supports(self):
        rows = [game('Ready', native_dlssg=True), game('NoFG', native_dlss=True), game('NoNR', native_dlssg=True),
                game('Cheat', native_dlss=True, anti_cheat=True), game('NoExe', native_dlss=True, exe='')]
        ready = {plan.identity('/games/Ready')}
        blocked = {'NoFG': 'No native DLSS-G detected', 'NoNR': 'The NR runtime is unavailable'}
        groups = plan.offer_groups('install', 'nr-mfg', 'skynizz', rows, ready, blocked)
        self.assertEqual([(code, mode, [row['name'] for row in subset]) for code, mode, subset in groups],
                         [('no-native-dlssg', 'nr-only', ['NoFG']), ('nr-runtime-unavailable', 'mfg-only', ['NoNR'])])
        self.assertEqual(plan.offer_groups('install', 'nr-mfg', 'dlss-unlocked', rows, ready, blocked), [],
                         'native NR-only subsets need Skynizz')
        self.assertEqual(plan.offer_groups('repair', 'nr-mfg', 'skynizz', rows, ready, blocked), [])
        self.assertEqual(plan.offer_groups('install', 'mfg-only', 'skynizz', rows, ready, blocked), [])


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.calls, self.discarded, self.downloads = [], [], []
        self.refuse = {}

    def prepare(self, rows, mode, operation, settings):
        self.calls.append(([row['name'] for row in rows], mode, operation, settings['runtime_provider'], settings['prefer_bundled_nr_only']))
        token = str(len(self.calls))
        ready = [row for row in rows if (row['name'], mode) not in self.refuse]
        return {'token': token, 'rows': [{'name': row['name'], 'game': row['game']} for row in ready],
                'blocked': [{'name': row['name'], 'reason': self.refuse[(row['name'], mode)]} for row in rows if row not in ready],
                'warnings': []}

    def run_plan(self, rows, operation='install', mode='nr-mfg'):
        return plan.plan(self.prepare, self.discarded.extend, rows, operation, mode, SETTINGS, self.downloads.append)

    def test_routes_downloads_and_offers_in_one_plan(self):
        self.refuse = {('NoFG', 'nr-mfg'): 'No native DLSS-G detected'}
        rows = [game('Ready', native_dlssg=True), game('Feeder', runtime_provider='feeder'), game('NoFG', native_dlss=True)]
        result = self.run_plan(rows)
        self.assertEqual(len(self.downloads), 1)
        self.assertEqual(self.calls, [(['Feeder'], 'nr-mfg', 'install', 'skynizz', False),
                                      (['NoFG', 'Ready'], 'nr-mfg', 'install', 'skynizz', False),
                                      (['NoFG'], 'nr-only', 'install', 'skynizz', True)])
        # Feeder gives NR only, so with NR + MFG chosen it is an opt-in offer, like a native NR-only game.
        self.assertEqual([entry['route'] for entry in result['steps']], ['skynizz'])
        self.assertEqual([(offer['code'], [row['name'] for row in offer['review']['rows']]) for offer in result['offers']],
                         [('feeder-nr-only', ['Feeder']), ('no-native-dlssg', ['NoFG'])])
        self.assertEqual(result['blocked'], [], 'an offered game is not also listed as refused')
        self.assertEqual(self.discarded, [])

    def test_batch_repair_uses_each_games_installed_mode(self):
        rows = [game('Combined', installed=True, runtime_provider='skynizz', feature_mode='nr-mfg'),
                game('NR', installed=True, runtime_provider='skynizz', feature_mode='nr-only')]
        result = self.run_plan(rows, operation='repair', mode='mfg-only')
        self.assertEqual([(names, mode) for names, mode, *_ in self.calls],
                         [(['Combined'], 'nr-mfg'), (['NR'], 'nr-only')])
        self.assertEqual(len(result['steps']), 2)
        self.assertEqual({batch['mode'] for batch in self.downloads[0]}, {'nr-mfg', 'nr-only'})

    def test_a_subset_that_admits_nothing_is_discarded_and_the_refusal_kept(self):
        self.refuse = {('NoFG', 'nr-mfg'): 'No native DLSS-G detected', ('NoFG', 'nr-only'): 'Still unsupported'}
        result = self.run_plan([game('NoFG', native_dlss=True)])
        self.assertEqual(result['steps'], [])
        self.assertEqual(result['offers'], [])
        self.assertEqual(result['blocked'], [{'name': 'NoFG', 'reason': 'No native DLSS-G detected'}])
        self.assertEqual(sorted(self.discarded), ['1', '2'])

    def test_a_feeder_setup_problem_replaces_the_main_refusal(self):
        self.refuse = {('F', 'nr-mfg'): 'Not supported by this package', ('F', 'nr-only'): 'Feeder files are missing'}
        result = self.run_plan([game('F', install_provider='feeder', feeder_available=True)])
        self.assertEqual(result['blocked'], [{'name': 'F', 'reason': 'Feeder files are missing'}])

    def test_a_failure_discards_every_token(self):
        def broken(rows, mode, operation, settings):
            if len(self.calls) == 1:
                raise RuntimeError('host failed')
            self.calls.append(rows)
            return {'token': 'first', 'rows': [{'name': rows[0]['name'], 'game': rows[0]['game']}], 'blocked': []}
        with self.assertRaises(RuntimeError):
            plan.plan(broken, self.discarded.extend, [game('A'), game('B', runtime_provider='feeder')], 'install', 'nr-mfg', SETTINGS)
        self.assertEqual(self.discarded, ['first'])

    def test_split_render_is_bound_to_all_exact_install_reviews(self):
        self.refuse = {('NoFG', 'nr-mfg'): 'No native DLSS-G detected'}
        prepared = []
        routes = plan.ReviewedRoutes(lambda p: self.prepare(p['rows'], p['mode'], p['operation'], p['settings']),
            None, None, lambda p: self.discarded.extend(p['tokens']), lambda: SETTINGS, split_render=prepared.append)
        review = routes.prepare({'rows': [game('Ready', native_dlssg=True), game('NoFG', native_dlss=True)],
                                 'operation': 'install', 'mode': 'nr-mfg'})
        choice = {'auto': True, 'model': 'old'}
        routes.split_render({'token': review['token'], 'tokens': ['unrelated'], 'revision': 1, 'choice': choice})
        self.assertEqual(prepared[0]['tokens'], ['1', '2'])
        self.assertEqual(prepared[0]['choice'], choice)
        self.assertEqual(prepared[0]['revision'], 1)
        routes.discard({'token': review['token']})
        with self.assertRaisesRegex(ValueError, 'review expired'):
            routes.split_render({'token': review['token'], 'revision': 2, 'choice': None})

    def test_uninstall_has_no_downloads_or_offers(self):
        result = self.run_plan([game('A', installed=True)], operation='uninstall')
        self.assertEqual(self.downloads, [])
        self.assertEqual(result['offers'], [])
        self.assertEqual([entry['operation'] for entry in result['steps']], ['uninstall'])


if __name__ == '__main__':
    unittest.main()
