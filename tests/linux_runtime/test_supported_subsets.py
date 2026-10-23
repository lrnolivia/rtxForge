"""NR + MFG requests offer separate, opt-in reviews for games that support only one feature."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_fixture  # noqa: F401
import desktop_service
import transactions as t


def row(name, **flags):
    return dict({'game': '/games/' + name, 'name': name, 'exe': name + '.exe'}, **flags)


class SupportedSubsetTest(unittest.TestCase):
    def setUp(self):
        self.service = desktop_service.DesktopService.__new__(desktop_service.DesktopService)
        self.service.config = {}
        self.calls = []
        self.adopt = []

    def run_with(self, rows, outcome, provider='skynizz', mode='nr-mfg', operation='install', adopt=True):
        def prepare(rows, mode, operation, adopt=False, visual_settings=None, scope=None, **kwargs):
            self.adopt.append(adopt)
            self.calls.append((mode, [r['game'] for r in rows], scope, dict(visual_settings or {})))
            return outcome(rows, mode)
        with patch.object(desktop_service.library_media, 'load_settings', return_value={'runtime_provider': provider}), \
             patch.object(self.service, 'prepare', side_effect=prepare):
            return self.service.prepare_supported(rows, mode, operation, adopt, visual_settings={'nr_on_launch': False})

    @staticmethod
    def engine(ready, blocked):
        def outcome(rows, mode):
            plans = [{'row': r} for r in rows if ready(r, mode)]
            return {'plans': plans, 'rows': [{'name': p['row']['name']} for p in plans],
                    'blocked': [{'name': r['name'], 'reason': blocked(r, mode)} for r in rows if not ready(r, mode)]}
        return outcome

    def test_nr_only_and_mfg_only_offers_with_reason_codes(self):
        rows = [row('Both', native_dlss=True, native_dlssg=True),
                row('NoFG', native_dlss=True, native_dlssg=False),
                row('NoModel', native_dlss=True, native_dlssg=True, nr_missing=True),
                row('AntiCheat', native_dlss=True, native_dlssg=False, anti_cheat=True),
                row('NoExe', native_dlss=True, native_dlssg=False, exe='')]

        def ready(r, mode):
            if r.get('anti_cheat') or not r.get('exe'):
                return False
            if mode == 'nr-mfg':
                return r.get('native_dlssg') and not r.get('nr_missing')
            if mode == 'nr-only':
                return not r.get('nr_missing')
            return r.get('native_dlssg')

        def blocked(r, mode):
            if r.get('nr_missing'):
                return 'The selected NR runtime is missing (nvngx_dlssnr.dll).'
            return 'Anti-cheat detected' if r.get('anti_cheat') else 'The combined NR + MFG bridge requires game-native DLSS Frame Generation.'

        review = self.run_with(rows, self.engine(ready, blocked))
        offers = {o['reason_code']: o for o in review['supported']}
        self.assertEqual(set(offers), {'no-native-dlssg', 'nr-runtime-unavailable'})
        self.assertEqual(offers['no-native-dlssg']['games'], ['/games/NoFG'])
        self.assertEqual((offers['no-native-dlssg']['mode'], offers['no-native-dlssg']['nr'], offers['no-native-dlssg']['mfg']), ('nr-only', True, False))
        self.assertEqual(offers['nr-runtime-unavailable']['games'], ['/games/NoModel'])
        self.assertEqual((offers['nr-runtime-unavailable']['mode'], offers['nr-runtime-unavailable']['nr']), ('mfg-only', False))
        for offer in offers.values():
            self.assertTrue(offer['reason'] and 'sha' not in offer['reason'].casefold())
        # Each offer is its own exact-scope review; hard blockers are never offered.
        for mode, games, scope, values in self.calls[1:]:
            self.assertEqual(scope, {'kind': 'selected', 'games': games})
            self.assertNotIn('/games/AntiCheat', games)
            self.assertNotIn('/games/NoExe', games)
            self.assertIs(values['prefer_bundled_nr_only'], mode == 'nr-only')
        self.assertEqual([r['game'] for r in (p['row'] for p in review['plans'])], ['/games/Both'])
        self.assertEqual({b['name'] for b in review['blocked']}, {'AntiCheat', 'NoExe'})
        self.assertEqual(set(self.adopt), {True}, 'Recognize Existing Features reaches every review')

    def test_feeder_games_are_offered_nr_only(self):
        rows = [row('MassEffect', install_provider='feeder', feeder_available=True), row('Plain', native_dlss=True, native_dlssg=True)]
        outcome = self.engine(lambda r, mode: r['name'] == 'Plain' or mode == 'nr-only',
                              lambda r, mode: 'Feeder supports NR only')
        review = self.run_with(rows, outcome, provider='y4my')
        self.assertEqual([(o['reason_code'], o['games']) for o in review['supported']], [('feeder-nr-only', ['/games/MassEffect'])])

    def test_no_offers_outside_fresh_nr_installs_or_when_the_subset_refuses(self):
        rows = [row('NoFG', native_dlss=True, native_dlssg=False)]
        outcome = self.engine(lambda r, mode: False, lambda r, mode: 'blocked')
        self.assertEqual(self.run_with(rows, outcome, operation='repair')['supported'], [])
        self.assertEqual(self.run_with(rows, outcome, mode='mfg-only')['supported'], [])
        self.assertEqual(self.run_with(rows, outcome, provider='y4my')['supported'], [], 'native NR-only subsets need Skynizz')
        self.assertEqual(self.run_with(rows, outcome)['supported'], [], 'a subset that admits nothing is not offered')

        def refuse(rows, mode):
            if mode == 'nr-only':
                raise t.Refusal('no')
            return {'plans': [], 'blocked': [{'name': 'NoFG', 'reason': 'kept'}]}
        review = self.run_with(rows, refuse)
        self.assertEqual((review['supported'], review['blocked']), ([], [{'name': 'NoFG', 'reason': 'kept'}]))


if __name__ == '__main__':
    unittest.main()
