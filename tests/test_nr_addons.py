from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nr_addons as nr
import transactions as t

DLSS_GAME = {'native_dlss': True, 'arch': 'x64'}
PLAIN_GAME = {'native_dlss': False, 'arch': 'x64'}


class NrAddonTests(unittest.TestCase):
    def test_every_download_is_pinned(self):
        cat = nr.catalog()
        archives = [b['archive'] for a in cat['addons'].values() for b in a['builds'].values() if 'archive' in b]
        archives += [b['archive'] for m in cat['models'].values() for b in m['builds'].values()]
        self.assertTrue(archives)
        for archive in archives:
            self.assertTrue(archive['url'].startswith('https://github.com/'), archive['url'])
            self.assertRegex(archive['sha256'], r'^[0-9a-f]{64}$')
            self.assertGreater(archive['size'], 0)
        for addon in cat['addons'].values():
            self.assertEqual(sum(bool(b.get('default')) for b in addon['builds'].values()), 1, addon['name'])

    def test_characters_and_world_combo_pairs_shortfuse_with_lecram(self):
        combo = nr.builtin_combos()['characters-and-world']
        result = nr.apply_combo(DLSS_GAME, combo)
        self.assertTrue(result['ok'], result.get('reason'))
        plan = result['plan']
        self.assertEqual([i['addon'] for i in plan['install']], ['lecram', 'shortfuse'])
        lecram = plan['ini']['RenoDX.DLSS5']
        # Lecram stands down beside another NR add-on unless told to observe.
        self.assertEqual(lecram['ForeignNr'], 'observe')
        self.assertEqual((lecram['NRLocalTone'], lecram['NRLocalStructure'], lecram['NRSkinStructure']), (0.39, 0.40, 0.10))
        shortfuse = plan['ini']['renodx-dlss']
        self.assertEqual(shortfuse['DirectNeuralRenderingSkinStructureStrength'], 0.68)
        self.assertFalse(plan['feeder'], 'a DLSS game needs no Feeder')
        self.assertTrue(plan['verified'], 'confirmed on the Witcher 3 Forge Lab copy')
        gitc = nr.plan(DLSS_GAME, {'environment': {'addon': 'gitc'}})
        self.assertTrue(gitc['verified'], 'a single add-on needs no pairing check')
        self.assertEqual(plan['unconfirmed_sections'], ['renodx-dlss'])

    def test_shortfuse_needs_the_games_own_dlss(self):
        combo = nr.builtin_combos()['characters-and-world']
        result = nr.apply_combo(PLAIN_GAME, combo)
        self.assertFalse(result['ok'])
        self.assertIn("own DLSS", result['reason'])
        with self.assertRaises(t.Refusal):
            nr.plan({'native_dlss': True, 'arch': 'x86'}, {'environment': {'addon': 'shortfuse'}})

    def test_gitc_runs_alone(self):
        alone = nr.plan(PLAIN_GAME, {'environment': {'addon': 'gitc', 'model': 'old'}})
        self.assertEqual(alone['install'], [{'addon': 'gitc', 'build': '1.8.0'}])
        self.assertTrue(alone['verified'])
        with self.assertRaisesRegex(t.Refusal, 'runs alone'):
            nr.plan(DLSS_GAME, {'environment': {'addon': 'lecram'}, 'character': {'addon': 'gitc'}})

    def test_lecram_in_both_slots_is_one_add_on_with_two_passes(self):
        plan = nr.plan(PLAIN_GAME, {'environment': {'addon': 'lecram', 'values': {'structure': 0.4, 'character': 0.1}},
                                    'character': {'addon': 'lecram', 'values': {'character': 0.7, 'character_mask': 1}}})
        self.assertEqual(plan['install'], [{'addon': 'lecram', 'build': '10.8'}])
        ini = plan['ini']['RenoDX.DLSS5']
        self.assertEqual((ini['NRPasses'], ini['NRLocalStructure'], ini['NRSkinStructure']), (2, 0.4, 0.1))
        self.assertEqual((ini['NRPass2FollowPass1'], ini['NRPass2Skin'], ini['NRPass2AutoMask']), (0, 0.7, 1))
        self.assertNotIn('ForeignNr', ini)
        self.assertTrue(plan['feeder'], 'a game without DLSS gets its frames from Feeder')
        with self.assertRaisesRegex(t.Refusal, 'not supported yet'):
            nr.plan(DLSS_GAME, {'environment': {'addon': 'shortfuse'}, 'character': {'addon': 'shortfuse'}})

    def test_bad_values_and_choices_refuse(self):
        for setup in ({'environment': {'addon': 'lecram', 'values': {'intensity': 5}}},
                      {'environment': {'addon': 'lecram', 'values': {'passes': 9}}},
                      {'environment': {'addon': 'lecram', 'values': {'colour': 1}}},
                      {'environment': {'addon': 'lecram', 'model': 'newest'}},
                      {'environment': {'addon': 'lecram', 'build': '12.0'}},
                      {'environment': {'addon': 'reshade'}},
                      {'character': {'addon': 'lecram'}},
                      {'environment': {'addon': 'lecram', 'model': 'old'}, 'character': {'addon': 'shortfuse', 'model': 'new'}}):
            with self.subTest(setup=setup), self.assertRaises(t.Refusal):
                nr.plan(DLSS_GAME, setup)

    def test_unverified_settings_are_reported_not_written(self):
        plan = nr.plan(DLSS_GAME, {'environment': {'addon': 'shortfuse', 'values': {'independent_skin': 1, 'intensity': 1.0}}})
        self.assertEqual(plan['skipped'], ['independent_skin'])
        self.assertEqual(plan['ini']['renodx-dlss'], {'DirectNeuralRenderingIntensity': 1.0})
        for key in plan['ini']['renodx-dlss']:
            self.assertTrue(re.fullmatch(r'DirectNeuralRendering[A-Za-z]+', key), key)

    def test_saved_combos_are_shared_validated_and_deletable(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(nr, '_combo_file', lambda _config: Path(folder).resolve() / 'nr-combos.json'):
            combo = {'environment': {'addon': 'lecram', 'build': '10.8', 'model': 'new'},
                     'character': {'addon': 'shortfuse', 'model': 'new'}}
            key = nr.save_combo({}, ' My mix ', combo)
            saved = nr.combos({})
            self.assertEqual(saved[key]['name'], 'My mix')
            self.assertFalse(saved[key]['builtin'])
            self.assertTrue(saved['characters-and-world']['builtin'])
            self.assertTrue(nr.apply_combo(DLSS_GAME, saved[key])['ok'])
            self.assertFalse(nr.apply_combo(PLAIN_GAME, saved[key])['ok'])
            self.assertEqual([a['id'] for a in nr.catalog_view({})['addons']], ['lecram', 'shortfuse', 'gitc'])
            for bad in ({'character': {'addon': 'lecram'}}, {'environment': {'addon': 'gitc'}, 'character': {'addon': 'lecram'}}):
                with self.subTest(bad=bad), self.assertRaises(t.Refusal):
                    nr.save_combo({}, 'Bad', bad)
            with self.assertRaises(t.Refusal):
                nr.delete_combo({}, 'characters-and-world')
            nr.delete_combo({}, key)
            self.assertNotIn(key, nr.combos({}))

    def test_check_reports_reason_instead_of_raising(self):
        self.assertFalse(nr.check(PLAIN_GAME, {'environment': {'addon': 'shortfuse'}})['ok'])
        self.assertTrue(nr.check(DLSS_GAME, {'environment': {'addon': 'gitc'}})['ok'])


if __name__ == '__main__':
    unittest.main()
