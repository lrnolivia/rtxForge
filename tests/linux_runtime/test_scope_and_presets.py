"""Engine-side operation scope and the shared MFG preset (Auto/Custom/Dynamic) INI mapping."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_fixture  # noqa: F401  (puts scripts/ on sys.path)
import engine_bridge
import desktop_service
import skynizz_provider
import universal_mfg_provider as universal
import transactions as t


class ScopeTest(unittest.TestCase):
    rows = [{'game': '/games/A', 'name': 'A'}, {'game': '/games/B', 'name': 'B'}]

    def test_empty_missing_and_duplicate_selections_refuse(self):
        for rows in ([], None, [{'name': 'no folder'}], [{'game': ''}]):
            with self.subTest(rows=rows), self.assertRaises(t.Refusal):
                engine_bridge.check_scope(rows)
        with self.assertRaisesRegex(t.Refusal, 'Duplicate'):
            engine_bridge.check_scope(self.rows + [{'game': '/games/A'}])
        self.assertEqual(engine_bridge.check_scope(self.rows), ['/games/A', '/games/B'])

    def test_rows_must_equal_the_reviewed_scope(self):
        scope = {'kind': 'selected', 'games': ['/games/B', '/games/A']}
        self.assertEqual(engine_bridge.check_scope(self.rows, scope), ['/games/A', '/games/B'])
        for bad in ({'kind': 'selected', 'games': ['/games/A']},                         # rows widened past the selection
                    {'kind': 'filtered', 'games': ['/games/A', '/games/B', '/games/C']},  # stale filter result
                    {'kind': 'selected', 'games': []},
                    {'kind': 'everything', 'games': ['/games/A', '/games/B']},
                    {'kind': 'selected', 'games': ['/games/A', '/games/A']}):
            with self.subTest(scope=bad), self.assertRaises(t.Refusal):
                engine_bridge.check_scope(self.rows, bad)

    def test_engine_prepare_refuses_before_loading_anything(self):
        with patch.object(engine_bridge, 'module', side_effect=AssertionError('engine loaded')):
            with self.assertRaisesRegex(t.Refusal, 'No games are selected'):
                engine_bridge.prepare({}, [], 'nr-mfg', 'install', {})
            with self.assertRaisesRegex(t.Refusal, 'no longer match'):
                engine_bridge.prepare({}, self.rows, 'nr-mfg', 'install',
                                      {'operation_scope': {'kind': 'selected', 'games': ['/games/A']}})

    def test_every_service_route_is_guarded(self):
        service = desktop_service.DesktopService.__new__(desktop_service.DesktopService)
        service.config = {}
        service.hardware = lambda: {'ready': True}
        with patch.object(desktop_service.library_media, 'load_settings', return_value={}), \
             patch.object(desktop_service.engine_bridge, 'prepare', side_effect=AssertionError('engine route reached')):
            for operation in ('install', 'uninstall', 'repair', 'reset', 'adopt', 'adopt-clean'):
                with self.subTest(operation=operation), self.assertRaises(t.Refusal):
                    service.prepare([], 'nr-mfg', operation)
            with self.assertRaisesRegex(t.Refusal, 'no longer match'):
                service.prepare(self.rows, 'nr-mfg', 'uninstall', scope={'kind': 'filtered', 'games': ['/games/A']})
        # A defaults-only Presets apply names no games and changes none.
        seen = {}
        with patch.object(desktop_service.library_media, 'load_settings', return_value={}), \
             patch.object(desktop_service.engine_bridge, 'prepare', side_effect=lambda c, rows, m, o, s: seen.update(s) or {'rows': []}):
            service.prepare([], 'nr-mfg', 'reset', visual_settings={'mfg_multiplier': 4}, save_defaults=True)
        self.assertIs(seen['defaults_only'], True)


SET = None


def engine():
    tmp = tempfile.mkdtemp()
    with patch.dict(os.environ, {'RTXFORGE_DLSS_UNLOCKED_STATE': tmp}):
        return engine_bridge.module({'storage': {'root': tmp, 'reserve_bytes': 0}})


class MfgPresetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = engine()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = SimpleNamespace(target_dir=Path(self.tmp.name))
        self.text = '[DLSSG]\nOverrideInterpolationCount=auto\nOverrideForceDMFG=false\n'

    def tearDown(self):
        self.e.MFG_PRESET = None
        self.tmp.cleanup()

    def apply(self, settings, provider, mode='nr-mfg', controls=None):
        self.e.MFG_PRESET = engine_bridge.mfg_preset(settings)
        return self.e.apply_mfg_preset(self.text, self.game, mode, provider, controls)

    def values(self, text):
        parser = t.ini(text)
        return {(s, k): v for s in parser.sections() for k, v in parser.items(s)}

    def test_preset_validation_and_defaults(self):
        self.assertIsNone(engine_bridge.mfg_preset({'mfg_multiplier': 4}), 'callers without the new keys keep old behaviour')
        self.assertEqual(engine_bridge.mfg_preset({'mfg_multiplier': 4, 'dynamic_mfg': 0}),
                         {'mfg_multiplier': 4, 'dynamic_mfg': 0, 'mfg_saved_mode': 1, 'mfg_saved_multiplier': 4})
        for bad in ({'dynamic_mfg': 2}, {'dynamic_mfg': 'yes'}, {'dynamic_mfg': 0, 'mfg_multiplier': 1},
                    {'mfg_saved_mode': 3}, {'mfg_saved_multiplier': 7}, {'mfg_saved_multiplier': 1}):
            with self.subTest(bad=bad), self.assertRaises(t.Refusal):
                engine_bridge.mfg_preset(bad)

    def test_auto_custom_dynamic_and_off_write_exact_keys_for_y4my(self):
        y4my = {'id': 'y4my'}
        cases = [
            ({'mfg_multiplier': 'auto', 'dynamic_mfg': 0, 'mfg_saved_mode': 0, 'mfg_saved_multiplier': 3}, 'auto', 'false', '0', '3'),
            ({'mfg_multiplier': 4, 'dynamic_mfg': 0, 'mfg_saved_mode': 1, 'mfg_saved_multiplier': 4}, '3', 'false', '1', '4'),
            ({'mfg_multiplier': 2, 'dynamic_mfg': 0, 'mfg_saved_mode': 1, 'mfg_saved_multiplier': 2}, '1', 'false', '1', '2'),
            ({'mfg_multiplier': 6, 'dynamic_mfg': 0, 'mfg_saved_mode': 1, 'mfg_saved_multiplier': 6}, '5', 'false', '1', '6'),
            # Off keeps the saved Dynamic choice and ratio dormant.
            ({'mfg_multiplier': 0, 'dynamic_mfg': 1, 'mfg_saved_mode': 2, 'mfg_saved_multiplier': 5}, '0', 'false', '2', '5'),
        ]
        for settings, count, force, mode, ratio in cases:
            with self.subTest(settings=settings):
                values = self.values(self.apply(settings, y4my))
                self.assertEqual(values[('DLSSG', 'OverrideInterpolationCount')], count)
                self.assertEqual(values[('DLSSG', 'OverrideForceDMFG')], force)
                self.assertEqual(values[('rtxForge.Presets', 'MfgMode')], mode)
                self.assertEqual(values[('rtxForge.Presets', 'MfgMultiplier')], ratio)

    def test_dynamic_only_where_the_route_supports_it(self):
        dynamic = {'mfg_multiplier': 6, 'dynamic_mfg': 1, 'mfg_saved_mode': 2, 'mfg_saved_multiplier': 6}
        for provider in ({'id': 'y4my'}, {'id': 'dlss-unlocked', 'family': 'dlss-unlocked'}, {'id': 'custom'}):
            with self.subTest(provider=provider), self.assertRaisesRegex(Exception, 'Dynamic Multi-Frame Generation needs'):
                self.apply(dynamic, provider)
        integrated = self.values(self.apply(dynamic, {'id': 'skynizz'}))
        self.assertEqual((integrated[('DLSSG', 'OverrideForceDMFG')], integrated[('DLSSG', 'OverrideInterpolationCount')]), ('true', '5'))
        plugin = {'id': 'skynizz', 'mfg_component': universal.pinned()}
        with self.assertRaisesRegex(Exception, 'confirmed Dynamic'):
            self.apply(dynamic, plugin)
        (self.game.target_dir / universal.STATUS).write_text(json.dumps({'dynamicMfgSupportKnown': True, 'dynamicMfgSupported': True}))
        self.assertEqual(self.values(self.apply(dynamic, plugin))[('DLSSG', 'OverrideForceDMFG')], 'true')
        (self.game.target_dir / universal.STATUS).write_text(json.dumps({'dynamicMfgSupportKnown': True, 'dynamicMfgSupported': False}))
        with self.assertRaisesRegex(Exception, 'confirmed Dynamic'):
            self.apply(dynamic, plugin)
        # Installed baselines name the component through their archive record (reset path).
        installed = {'provider_id': 'skynizz', 'archive': {'release': {'mfg_component': universal.pinned()}}}
        with self.assertRaisesRegex(Exception, 'confirmed Dynamic'):
            self.apply(dynamic, installed)
        import ada_mfg_provider
        addon = {'id': 'skynizz', 'mfg_component': ada_mfg_provider.pinned()}
        with self.assertRaisesRegex(Exception, 'Dynamic Multi-Frame Generation needs'):
            self.apply(dynamic, addon)

    def test_addon_owned_count_is_left_alone_but_the_dormant_choice_persists(self):
        import ada_mfg_provider
        addon = {'id': 'skynizz', 'mfg_component': ada_mfg_provider.pinned()}
        values = self.values(self.apply({'mfg_multiplier': 4, 'dynamic_mfg': 0, 'mfg_saved_mode': 1, 'mfg_saved_multiplier': 4}, addon))
        self.assertEqual(values[('DLSSG', 'OverrideInterpolationCount')], 'auto')
        self.assertEqual(values[('rtxForge.Presets', 'MfgMultiplier')], '4')

    def test_nr_only_and_explicit_feature_controls_win(self):
        settings = {'mfg_multiplier': 4, 'dynamic_mfg': 0, 'mfg_saved_mode': 1, 'mfg_saved_multiplier': 4}
        self.assertEqual(self.apply(settings, {'id': 'y4my'}, mode='nr-only'), self.text)
        controls = {'multiplier': 3, 'mfg_saved_multiplier': 3}
        values = self.values(self.apply(settings, {'id': 'skynizz'}, controls=controls))
        self.assertEqual(values[('DLSSG', 'OverrideInterpolationCount')], 'auto', 'the control owns the count')
        self.assertNotIn(('rtxForge.Presets', 'MfgMultiplier'), values)
        self.assertEqual(values[('rtxForge.Presets', 'MfgMode')], '1')

    def test_written_ini_reads_back_through_the_shared_schema(self):
        settings = {'mfg_multiplier': 0, 'dynamic_mfg': 1, 'mfg_saved_mode': 2, 'mfg_saved_multiplier': 5}
        path = self.game.target_dir / 'OptiScaler.ini'
        path.write_text(self.apply(settings, {'id': 'skynizz'}))
        found = skynizz_provider.read_controls(path)
        self.assertEqual((found['multiplier'], found['dynamic_mfg'], found['mfg_saved_mode'], found['mfg_saved_multiplier']), (0, 0, 2, 5))


if __name__ == '__main__':
    unittest.main()
