from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nr_addons as nr
import transactions as t

DLSS_GAME = {'native_dlss': True, 'arch': 'x64'}
PLAIN_GAME = {'native_dlss': False, 'arch': 'x64'}


class NrAddonTests(unittest.TestCase):
    def test_package_restore_detects_a_new_split_render_receipt(self):
        import nr_install
        with tempfile.TemporaryDirectory() as folder:
            row = {'game': str(Path(folder).resolve()), 'exe': 'game.exe'}
            review = nr_install.prepare_package_restore({}, row, [])
            self.assertEqual(nr_install.package_restore_paths(review), [])
            receipt = nr_install._receipt(row)
            receipt.parent.mkdir()
            receipt.write_text('{}')
            with self.assertRaisesRegex(t.Refusal, 'installed after review'):
                nr_install.check_package_restore(review)

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
        shortfuse = plan['ini']['RENODX-DLSS']
        self.assertEqual(shortfuse['DirectNeuralRenderingSkinStructureStrength'], 0.68)
        self.assertFalse(plan['feeder'], 'a DLSS game needs no Feeder')
        self.assertTrue(plan['verified'], 'verified in The Witcher 3 with the game\'s frame generation')
        self.assertEqual(plan['load_early'], ['renodx-dlss.addon64'], 'Streamline games crash unless ShortFuse loads early')
        gitc = nr.plan(DLSS_GAME, {'environment': {'addon': 'gitc'}})
        self.assertTrue(gitc['verified'], 'a single add-on needs no pairing check')
        self.assertEqual(gitc['load_early'], [])

    def test_skynizz_is_the_world_and_shortfuse_the_character(self):
        game = dict(DLSS_GAME, installed=True, runtime_provider='skynizz', feature_mode='nr-mfg')
        self.assertEqual(nr.runtime_nr(game), {'id': 'optiscaler', 'name': 'Skynizz'})
        # One combo: beside Skynizz, Skynizz is its world and ShortFuse runs at 74% on Skynizz's model.
        combo = nr.builtin_combos()['characters-and-world']
        self.assertEqual(list(nr.builtin_combos()), ['characters-and-world'])
        setup = nr.combo_setup(game, combo)
        self.assertEqual(setup['environment'], {'addon': 'optiscaler'})
        plan = nr.apply_combo(game, combo)['plan']
        self.assertEqual(plan['install'], [{'addon': 'shortfuse', 'build': '26.1025.0009'}])
        self.assertIsNone(plan['model'], "Skynizz's NR brings the model")
        self.assertTrue(plan['optiscaler_nr'])
        self.assertEqual(plan['world'], 'Skynizz')
        self.assertTrue(plan['verified'])
        self.assertEqual(plan['ini']['RENODX-DLSS']['DirectNeuralRenderingProcessingScale'], 74, 'a whole percent')
        self.assertNotIn('DirectNeuralRenderingDiffuseWhiteNits', plan['ini']['RENODX-DLSS'])
        # A setup without an Environment (saved before Skynizz was shown) still means Skynizz's world.
        self.assertEqual(nr.plan(game, {'character': {'addon': 'shortfuse'}})['install'],
                         nr.plan(game, {'environment': {'addon': 'optiscaler'}, 'character': {'addon': 'shortfuse'}})['install'])
        for setup, reason in (({'environment': {'addon': 'lecram'}}, 'where OptiScaler is installed'),
                              ({'environment': {'addon': 'shortfuse'}}, 'Keep Skynizz as Environment'),
                              ({'environment': {'addon': 'optiscaler'}, 'character': {'addon': 'gitc'}}, "can't run beside Skynizz's NR"),
                              ({'environment': {'addon': 'optiscaler'}}, 'Choose a Character add-on')):
            with self.subTest(setup=setup), self.assertRaisesRegex(t.Refusal, reason):
                nr.plan(game, setup)
        # Elsewhere the same combo keeps Lecram as its world.
        lecram = nr.apply_combo(dict(game, feature_mode='mfg-only'), combo)
        self.assertIn('Lecram', lecram['reason'], 'Lecram still never runs where OptiScaler is installed')
        self.assertEqual([i['addon'] for i in nr.apply_combo(DLSS_GAME, combo)['plan']['install']], ['lecram', 'shortfuse'])
        with self.assertRaisesRegex(t.Refusal, "Skynizz doesn't run NR in this game"):
            nr.plan(DLSS_GAME, {'environment': {'addon': 'optiscaler'}})
        self.assertTrue(nr.check(dict(game, feature_mode='mfg-only'), {'environment': {'addon': 'shortfuse'}})['ok'])
        self.assertFalse(nr.check(dict(game, feature_mode=None), {'character': {'addon': 'shortfuse'}})['ok'])
        self.assertEqual(nr.default_setup(game), {'environment': {'addon': 'optiscaler'}, 'character': {'addon': 'shortfuse'}})
        self.assertEqual(nr.default_setup(dict(game, runtime_provider='feeder')), {'environment': {'addon': 'lecram'}})
        # The catalog for a game gives each combo as it applies there, and names the world.
        from unittest import mock
        with mock.patch.object(nr, 'saved_combos', lambda _config: {}):
            view = nr.catalog_view({}, game)
            self.assertEqual(view['runtime_nr']['name'], 'Skynizz')
            self.assertEqual(view['combos']['characters-and-world']['environment'], {'addon': 'optiscaler'})
            self.assertEqual(view['combos']['characters-and-world']['name'], 'Characters + world')
            self.assertIsNone(nr.catalog_view({}, DLSS_GAME)['runtime_nr'])
            self.assertEqual(nr.catalog_view({}, DLSS_GAME)['combos']['characters-and-world']['environment']['addon'], 'lecram')

    def test_feeder_game_is_blocked_even_with_a_stale_native_dlss_flag(self):
        game = {'native_dlss': True, 'runtime_provider': 'feeder'}
        setup = nr.builtin_combos()['characters-and-world']
        result = nr.check(game, setup)
        self.assertFalse(result['ok'])
        self.assertIn('ShortFuse requires native DLSS hooks', result['reason'])
        self.assertIn('any of its four full-frame passes', result['reason'])

    def test_feeder_guidance_uses_live_hooks_even_when_the_library_row_is_stale(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as folder:
            game_dir = Path(folder).resolve()
            (game_dir / 'Game.exe').touch()
            (game_dir / 'dlss5-feed.addon64').touch()
            row = dict(DLSS_GAME, game=str(game_dir), exe='Game.exe')
            with mock.patch.object(nr, 'saved_combos', return_value={}):
                catalog = nr.catalog_view({}, row)
            result = nr.check(row, nr.builtin_combos()['characters-and-world'])
            self.assertFalse(result['ok'])
            self.assertEqual(result['reason'], catalog['blocked'])
            for instruction in ('native DLSS hooks', 'Character mask', 'four full-frame passes'):
                self.assertIn(instruction, result['reason'])

    def test_picker_refuses_an_occupied_addon_before_install_review(self):
        with tempfile.TemporaryDirectory() as folder:
            game_dir = Path(folder).resolve()
            (game_dir / 'Game.exe').touch()
            (game_dir / 'renodx-dlss5.addon64').write_bytes(b'another build')
            row = dict(DLSS_GAME, game=str(game_dir), exe='Game.exe')
            result = nr.check(row, nr.builtin_combos()['characters-and-world'])
            self.assertFalse(result['ok'])
            self.assertEqual(result['reason'], nr.occupied_file('renodx-dlss5.addon64'))

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
        self.assertEqual(plan['ini']['RENODX-DLSS'], {'DirectNeuralRenderingIntensity': 1.0})
        for key in plan['ini']['RENODX-DLSS']:
            self.assertTrue(re.fullmatch(r'DirectNeuralRendering[A-Za-z]+', key), key)

    def test_preset_editor_uses_the_package_to_choose_roles_and_providers(self):
        from unittest import mock
        with mock.patch.object(nr, 'saved_combos', return_value={}):
            native = nr.preset_catalog({}, 'native')
            self.assertIsNone(native['runtime_nr'])
            self.assertIn('lecram', {addon['id'] for addon in native['addons']})
            skynizz = nr.preset_catalog({}, 'skynizz')
            self.assertEqual(skynizz['runtime_nr']['name'], 'Skynizz')
            self.assertEqual({addon['id'] for addon in skynizz['addons']}, {'shortfuse'})
            self.assertEqual(skynizz['combos']['characters-and-world']['environment'], {'addon': 'optiscaler'})
            mfg = nr.preset_catalog({}, 'skynizz-mfg')
            self.assertIsNone(mfg['runtime_nr'])
            self.assertNotIn('lecram', {addon['id'] for addon in mfg['addons']})
            self.assertFalse(nr.preset_check('skynizz-mfg', {'environment': {'addon': 'lecram'}})['ok'])
            self.assertIn('Character mask', nr.preset_catalog({}, 'feeder')['blocked'])

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
            # A combo without an Environment add-on is for games where Skynizz's NR covers it.
            self.assertTrue(nr.save_combo({}, 'Characters only', {'character': {'addon': 'shortfuse'}}))
            beside = nr.save_combo({}, 'Beside Skynizz', {'environment': {'addon': 'optiscaler'}, 'character': {'addon': 'shortfuse'}})
            self.assertNotIn('environment', nr.saved_combos({})[beside], 'the game\'s own world is not stored as an add-on')
            for bad in ({'character': {'addon': 'lecram'}}, {'environment': {'addon': 'gitc'}, 'character': {'addon': 'lecram'}}, {}):
                with self.subTest(bad=bad), self.assertRaises(t.Refusal):
                    nr.save_combo({}, 'Bad', bad)
            with self.assertRaises(t.Refusal):
                nr.delete_combo({}, 'characters-and-world')
            nr.delete_combo({}, key)
            self.assertNotIn(key, nr.combos({}))

    def test_check_reports_reason_instead_of_raising(self):
        self.assertFalse(nr.check(PLAIN_GAME, {'environment': {'addon': 'shortfuse'}})['ok'])
        self.assertTrue(nr.check(DLSS_GAME, {'environment': {'addon': 'gitc'}})['ok'])

    def test_picker_refuses_standalone_lecram_without_native_dlss(self):
        setup = {'environment': {'addon': 'lecram'}}
        self.assertTrue(nr.plan(PLAIN_GAME, setup)['feeder'])
        result = nr.check(PLAIN_GAME, setup)
        self.assertFalse(result['ok'])
        self.assertIn('Choose Feeder NR', result['reason'])
        self.assertTrue(nr.check(DLSS_GAME, setup)['ok'])


if __name__ == '__main__':
    unittest.main()
