import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('review_routes', Path(__file__).resolve().parents[1] / 'bridge/review_routes.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls, self.executed, self.discarded, self.cancelled = [], [], [], []
        self.sequence = 0
        self.trust = None
        self.on_execute = None
        self.routes = module.ReviewedRoutes(self.prepare, self.execute, lambda p: self.cancelled.append(p['token']),
                                            lambda p: self.discarded.extend(p['tokens']), lambda: {'runtime_provider': 'skynizz'})

    def tearDown(self):
        self.temp.cleanup()

    def game(self, name, feeder=False):
        return {'name': name, 'game': str(Path(self.temp.name) / name), 'exe': 'fixture.exe',
                'runtime_provider': 'feeder' if feeder else 'skynizz', 'native_dlss': True, 'native_dlssg': not feeder}

    def prepare(self, params):
        self.calls.append(params)
        self.sequence += 1
        return {'token': str(self.sequence), 'rows': [{'name': row['name'], 'game': row['game'], 'detail': 'Fixture only'} for row in params['rows']], 'blocked': [], 'trust': self.trust}

    def execute(self, params):
        self.executed.append(params['token'])
        if self.on_execute:
            self.on_execute(params)
        return {'report': 'Fixture only'}

    def review(self):
        return self.routes.prepare({'operation': 'install', 'mode': 'nr-mfg', 'rows': [self.game('C'), self.game('B', True), self.game('A')]})

    def test_consecutive_routes_preserve_alphabetical_order_and_opt_in_subsets(self):
        review = self.review()
        self.assertEqual([['A'], ['B'], ['C']], [[row['name'] for row in call['rows']] for call in self.calls])
        self.assertEqual(['A', 'C'], [row['name'] for row in review['rows']])
        self.assertFalse(review['supported'][0]['mfg'])
        self.assertTrue(review['supported'][0]['nr'])
        result = self.routes.execute({'token': review['token'], 'supported': []})
        self.assertEqual(['1', '3'], self.executed)
        self.assertEqual(2, result['completed_batches'])
        self.assertEqual({'1', '2', '3'}, set(self.discarded))

    def test_unknown_subset_is_refused_before_any_execution(self):
        review = self.review()
        with self.assertRaisesRegex(ValueError, 'differs from the review'):
            self.routes.execute({'token': review['token'], 'supported': ['not-reviewed']})
        self.assertEqual([], self.executed)
        self.routes.execute({'token': review['token'], 'supported': [review['supported'][0]['token']]})
        self.assertEqual(['1', '2', '3'], self.executed)
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.routes.execute({'token': review['token']})

    def test_supported_only_requires_explicit_selection(self):
        review = self.routes.prepare({'operation': 'install', 'mode': 'nr-mfg', 'rows': [self.game('B', True)]})
        self.assertEqual([], review['rows'])
        with self.assertRaisesRegex(ValueError, 'at least one'):
            self.routes.execute({'token': review['token']})
        self.assertEqual([], self.executed)

    def test_exact_notice_must_be_acknowledged(self):
        self.trust = 'Offline-only fixture notice'
        review = self.review()
        self.assertEqual(self.trust, review['trust'])
        with self.assertRaisesRegex(ValueError, 'Acknowledge'):
            self.routes.execute({'token': review['token']})
        self.assertEqual([], self.executed)
        self.routes.execute({'token': review['token'], 'offline_acknowledged': True})
        self.assertEqual(['1', '3'], self.executed)

    def test_cancellation_stops_between_batches_and_releases_every_token(self):
        review = self.review()
        self.on_execute = lambda _p: self.routes.cancel({'token': review['token']})
        result = self.routes.execute({'token': review['token']})
        self.assertTrue(result['cancelled'])
        self.assertEqual(['1'], self.executed)
        self.assertEqual({'1', '2', '3'}, set(self.cancelled))
        self.assertEqual({'1', '2', '3'}, set(self.discarded))

    def test_discard_releases_primary_and_optional_tokens(self):
        review = self.review()
        self.routes.discard({'tokens': [review['token']]})
        self.assertEqual({'1', '2', '3'}, set(self.discarded))
        self.assertEqual([], self.executed)

    def enable_defaults(self):
        self.saved = []
        self.routes._defaults = (lambda p: {'token': 'defaults-exact', 'rows': [{'name': 'Defaults'}]},
                                 lambda p: self.saved.append((p['token'], list(self.executed))))

    def test_defaults_only_is_reviewed_and_one_use(self):
        self.enable_defaults()
        review = self.routes.prepare({'operation': 'apply', 'mode': 'nr-mfg', 'rows': [], 'defaults': {'nr_strength': 2.5}})
        self.assertEqual([], self.saved)
        self.assertEqual('Library defaults', review['rows'][0]['name'])
        self.routes.execute({'token': review['token']})
        self.assertEqual([('defaults-exact', [])], self.saved)
        self.assertIn('defaults-exact', self.discarded)
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.routes.execute({'token': review['token']})

    def test_defaults_save_after_all_reviewed_games_and_not_on_cancel(self):
        self.enable_defaults()
        params = {'operation': 'apply', 'mode': 'nr-mfg', 'rows': [self.game('A'), self.game('B', True)], 'defaults': {'mfg_multiplier': 3}}
        review = self.routes.prepare(params)
        self.routes.execute({'token': review['token']})
        self.assertEqual([('defaults-exact', ['1', '2'])], self.saved)
        self.saved.clear()
        review = self.routes.prepare(params)
        self.on_execute = lambda _p: self.routes.cancel({'token': review['token']})
        self.routes.execute({'token': review['token']})
        self.assertEqual([], self.saved)

    def test_default_tokens_discard_without_saving_and_arbitrary_settings_refused(self):
        self.enable_defaults()
        review = self.routes.prepare({'operation': 'apply', 'mode': 'nr-mfg', 'rows': [], 'defaults': {'nr_strength': 2}})
        self.routes.discard({'tokens': [review['token']]})
        self.assertEqual(['defaults-exact'], self.discarded)
        self.assertEqual([], self.saved)
        with self.assertRaisesRegex(ValueError, 'supported library'):
            self.routes.prepare({'operation': 'apply', 'mode': 'nr-mfg', 'rows': [], 'defaults': {'extra_folders': ['arbitrary']}})


if __name__ == '__main__':
    unittest.main()
