from pathlib import Path
import json
import sys
import tempfile
import unittest
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import compat_list
import game_notes
import skynizz_provider
import transactions as t

NO_DLSS = 'Skynizz needs a native DLSS Super Resolution route; D3D12/DLSS must be used in game.'
HOST = {'gpu': 'Example GPU', 'driver': '1.0', 'system': 'Windows'}


class CompatListTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = {'storage': {'root': str(self.root / 'state'), 'reserve_bytes': 0}}
        self.row = {'name': 'Example Game', 'game': str(self.root / 'Example Game'), 'exe': 'bin/Example.exe',
                    'appid': '123', 'blocked': NO_DLSS, 'package_blocked': '', 'skynizz_blocked': NO_DLSS}
        self.listed = []
        self.shipped = compat_list.shipped
        compat_list.shipped = lambda: self.listed

    def tearDown(self):
        compat_list.shipped = self.shipped
        self.tmp.cleanup()

    def test_capability_checks_are_soft_and_safety_checks_are_not(self):
        self.assertTrue(compat_list.soft(NO_DLSS))
        self.assertTrue(compat_list.soft('No native DLSS-G detected'))
        self.assertTrue(compat_list.soft('The combined NR + MFG bridge requires game-native DLSS Frame Generation.'))
        for reason in ('Anti-cheat detected', 'No Windows executable found', '', None):
            self.assertFalse(compat_list.soft(reason))

    def test_scan_marks_soft_blocks_without_lifting_them(self):
        row = compat_list.apply(self.config, [dict(self.row)])[0]
        self.assertEqual(row['blocked'], NO_DLSS)
        self.assertEqual(row['soft_reasons'], [NO_DLSS])
        self.assertNotIn('try_anyway', row)
        self.assertIsNone(row['compat'])

    def test_try_anyway_lifts_every_soft_verdict_and_says_so(self):
        compat_list.set_try_anyway(self.config, self.row['game'], True, NO_DLSS)
        row = compat_list.apply(self.config, [dict(self.row)])[0]
        self.assertEqual((row['blocked'], row['skynizz_blocked']), ('', ''))
        self.assertEqual(row['try_anyway'], NO_DLSS)
        self.assertTrue(row['nr_route_note'].startswith('Not verified'))
        self.assertEqual(row['soft_reasons'], [])
        compat_list.set_try_anyway(self.config, self.row['game'], False)
        self.assertEqual(compat_list.apply(self.config, [dict(self.row)])[0]['blocked'], NO_DLSS)

    def test_try_anyway_never_lifts_anti_cheat(self):
        with self.assertRaises(t.Refusal):
            compat_list.set_try_anyway(self.config, self.row['game'], True, 'Anti-cheat detected')
        record = game_notes.load(self.config, self.row['game'])
        record['try_anyway'] = {'reason': NO_DLSS, 'at': 'x'}
        game_notes.save(self.config, self.row['game'], record)
        row = compat_list.apply(self.config, [dict(self.row, blocked='Anti-cheat detected', skynizz_blocked='Anti-cheat detected')])[0]
        self.assertEqual(row['blocked'], 'Anti-cheat detected')
        self.assertNotIn('try_anyway', row)

    def test_prepare_recheck_is_lifted_again(self):
        # The host re-runs the package check before review; apply runs after it.
        compat_list.set_try_anyway(self.config, self.row['game'], True, NO_DLSS)
        rechecked = skynizz_provider.scan_rows([dict(self.row, blocked='', exe='bin/Example.exe', native_dlss=False)])
        self.assertEqual(rechecked[0]['blocked'], NO_DLSS)
        self.assertEqual(compat_list.apply(self.config, rechecked)[0]['blocked'], '')

    def test_your_result_comes_before_the_shipped_list(self):
        self.listed = [{'appid': '123', 'verdict': 'Problem', 'note': 'Listed'}]
        row = compat_list.apply(self.config, [dict(self.row)])[0]
        self.assertEqual(row['compat'], {'verdict': 'Problem', 'source': 'list', 'note': 'Listed'})
        game_notes.save(self.config, self.row['game'], {'status': 'Working', 'notes': '', 'sessions': []})
        row = compat_list.apply(self.config, [dict(self.row)])[0]
        self.assertEqual(row['compat']['source'], 'you')
        self.assertEqual(row['compat']['verdict'], 'Working')

    def test_list_matches_non_steam_games_by_exe(self):
        self.listed = [{'exe': 'example.exe', 'verdict': 'Working'}]
        self.assertEqual(compat_list.verdict(dict(self.row, appid=''), {})['verdict'], 'Working')

    def test_share_needs_a_result_and_builds_a_prefilled_issue(self):
        record = {'status': 'Untested', 'notes': ''}
        with self.assertRaises(t.Refusal):
            compat_list.share(self.row, record, 'Example Package', HOST, '1.0')
        record = {'status': 'Problem', 'notes': r'Crashed in C:\Users\me\game', 'try_anyway': {'reason': NO_DLSS}}
        share = compat_list.share(self.row, record, 'Example Package', HOST, '1.0')
        self.assertEqual(share['title'], '[Compatibility] Example Game · Problem')
        self.assertIn('**Tried anyway:** ' + NO_DLSS, share['body'])
        self.assertIn('**Package:** Example Package', share['body'])
        self.assertIn('**Executable:** Example.exe', share['body'])
        self.assertNotIn('Crashed', share['body'])
        query = urllib.parse.parse_qs(urllib.parse.urlparse(share['url']).query)
        self.assertEqual(query['body'][0], share['body'])
        with_notes = compat_list.share(self.row, record, 'Example Package', HOST, '1.0', include_notes=True)
        self.assertIn('Crashed in [WINDOWS PATH]', with_notes['body'])
        self.assertNotIn('Users', with_notes['body'])

    def test_shipped_list_is_valid(self):
        data = json.loads((compat_list.ROOT / 'providers/compatibility.json').read_text(encoding='utf-8'))
        self.assertEqual(data['schema'], 1)
        for entry in data['games']:
            self.assertIn(entry['verdict'], compat_list.VERDICTS)
            self.assertTrue(entry.get('appid') or entry.get('exe'))


if __name__ == '__main__':
    unittest.main()
