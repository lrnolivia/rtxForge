"""Overlay settings for installed NR add-ons: verified keys only, written after the game closes."""
import contextlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nr_addon_settings as settings
import nr_install
import renodx_hdr as hdr
import transactions as t

PAIR = {'environment': {'addon': 'lecram', 'build': '10.8', 'model': 'new'},
        'character': {'addon': 'shortfuse', 'build': '26.1025.0009', 'model': 'new'}}


class Engine:
    running = False
    def _running_processes_under_root(self, root): return ['Game.exe'] if self.running else []
    def mutation_lock(self): return contextlib.nullcontext()


class NrAddonSettingsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.game = base / 'game'; self.game.mkdir(); self.state = base / 'state'; self.state.mkdir()
        (self.game / 'Game.exe').write_bytes(b'MZ game')
        self.row = {'name': 'A Game', 'game': str(self.game), 'exe': 'Game.exe'}
        self.engine = Engine()
        for target, name, value in [(settings.storage, 'storage', lambda config, required=0: self.state),
                                    (hdr.engine_bridge, 'module', lambda config: self.engine)]:
            p = patch.object(target, name, value); p.start(); self.addCleanup(p.stop)
        self.ini = self.game / 'ReShade.ini'
        self.ini.write_text('[RenoDX.DLSS5]\nNRIntensity=1.00\nForeignNr=observe\n'
                            '[RENODX-DLSS]\nDirectNeuralRenderingProcessingScale=82\n[Unrelated]\nKeep=mine\n', encoding='utf-8')
        self.install(PAIR)

    def install(self, setup, route='reshade'):
        path = nr_install._receipt(self.row); path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'schema': 1, 'setup': setup, 'route': route, 'host': 'dxgi.dll',
                                    'files': {}, 'ini': {}, 'plugin': None, 'settings_created': None}))

    def value(self, section, key):
        return t.ini(self.ini.read_text(encoding='utf-8')).get(section, key, fallback=None)

    def test_both_slots_are_offered_by_role_with_verified_keys_only(self):
        result = settings.snapshot({}, self.row)
        self.assertTrue(result['available'])
        groups = {f['section'] for f in result['controls']}
        self.assertEqual(groups, {'Environment · Lecram', 'Character detail · ShortFuse'})
        keys = {f['key'] for f in result['controls']}
        self.assertIn('character_resolution_scale', keys)
        self.assertIn('environment_independent_skin', keys)
        for unverified in ('encoding', 'upscaling_resources'):
            self.assertFalse(any(k.endswith(unverified) for k in keys), unverified)
        self.assertFalse(any('ini' in f for f in result['controls']), 'ReShade.ini keys stay in the helper')

    def test_shortfuse_off_uses_global_hook_method_and_requires_verified_build(self):
        self.ini.write_text(t.setvalue(self.ini.read_text(), 'RENODX-DLSS', 'DirectNeuralRenderingHookStage', '3'))
        result = settings.snapshot({}, self.row)
        field = next(f for f in result['controls'] if f['key'] == 'character_hook_point')
        self.assertEqual(field['choices'], ['Off', 'Before upscaling', 'After upscaling', 'Before presentation'])
        self.assertEqual(result['values']['character_hook_point'], 3)
        settings.save({}, self.row, {'character_hook_point': 0})
        self.assertEqual(self.value('RENODX-DLSS', 'DirectNeuralRenderingHookStage'), '0')
        self.install({'character': {'addon': 'shortfuse', 'build': 'unknown'}})
        self.assertNotIn('character_hook_point', settings.snapshot({}, self.row)['values'])

    def test_shortfuse_resolution_scale_reads_and_writes_a_whole_percent(self):
        field = next(f for f in settings.snapshot({}, self.row)['controls'] if f['key'] == 'character_resolution_scale')
        self.assertEqual((field['min'], field['max'], field['step'], field['unit']), (25, 100, 1, '%'))
        self.assertEqual(settings.snapshot({}, self.row)['values']['character_resolution_scale'], 82)
        settings.save({}, self.row, {'character_resolution_scale': 74})
        self.assertEqual(self.value('RENODX-DLSS', 'DirectNeuralRenderingProcessingScale'), '74')
        with self.assertRaises(t.Refusal):
            settings.save({}, self.row, {'character_resolution_scale': 74.5})

    def test_closed_game_writes_only_requested_keys_and_keeps_a_backup(self):
        before = self.ini.read_bytes()
        result = settings.save({}, self.row, {'environment_intensity': 1.25, 'environment_character_mask': 0})
        self.assertFalse(result['pending'])
        self.assertEqual(self.value('RenoDX.DLSS5', 'NRIntensity'), '1.25')
        self.assertEqual(self.value('RenoDX.DLSS5', 'NRAutoMask'), '0')
        self.assertEqual(self.value('RenoDX.DLSS5', 'ForeignNr'), 'observe')
        self.assertIn('Keep=mine', self.ini.read_text())
        self.assertEqual((self.state / settings.FOLDER / 'backups' / t.sha(before)).read_bytes(), before)

    def test_running_game_queues_until_it_closes(self):
        self.engine.running = True; before = self.ini.read_bytes()
        result = settings.save({}, self.row, {'character_structure': 0.6})
        self.assertTrue(result['pending']); self.assertEqual(result['values']['character_structure'], 0.6)
        self.assertEqual(self.ini.read_bytes(), before)
        self.assertEqual(settings.flush({})['applied'], 0)
        self.engine.running = False
        self.assertEqual(settings.flush({})['applied'], 1)
        self.assertEqual(self.value('RENODX-DLSS', 'DirectNeuralRenderingLocalStructureStrength'), '0.60')
        self.assertFalse(settings.snapshot({}, self.row)['pending'])

    def test_a_change_in_the_addons_own_panel_wins(self):
        self.engine.running = True
        settings.save({}, self.row, {'environment_intensity': 1.5})
        self.ini.write_text(t.setvalue(self.ini.read_text(), 'RenoDX.DLSS5', 'NRIntensity', '0.80'))
        self.engine.running = False
        self.assertEqual(settings.flush({})['applied'], 0)
        self.assertEqual(self.value('RenoDX.DLSS5', 'NRIntensity'), '0.80')
        self.assertIn("own panel", settings.snapshot({}, self.row)['message'])

    def test_lecram_is_not_offered_where_optiscaler_is_installed(self):
        self.install({'character': {'addon': 'shortfuse'}}, route='optiscaler')
        self.assertEqual({f['section'] for f in settings.snapshot({}, self.row)['controls']}, {'Character detail · ShortFuse'})
        self.install(PAIR, route='optiscaler')
        sections = {f['section'] for f in settings.snapshot({}, self.row)['controls']}
        self.assertNotIn('Environment · Lecram', sections)

    def test_lecram_in_both_slots_tunes_its_second_pass(self):
        self.install({'environment': {'addon': 'lecram'}, 'character': {'addon': 'lecram'}})
        settings.save({}, self.row, {'character_intensity': 0.7, 'environment_intensity': 1.1})
        self.assertEqual(self.value('RenoDX.DLSS5', 'NRPass2Intensity'), '0.70')
        self.assertEqual(self.value('RenoDX.DLSS5', 'NRIntensity'), '1.10')

    def test_invalid_values_are_refused_before_writes(self):
        before = self.ini.read_bytes()
        for changes in ({'environment_intensity': True}, {'environment_intensity': float('nan')},
                        {'environment_intensity': 9}, {'environment_passes': 1.5}, {'Unknown': 1}, {}):
            with self.subTest(changes=changes), self.assertRaises(t.Refusal):
                settings.save({}, self.row, changes)
        self.assertEqual(self.ini.read_bytes(), before)

    def test_games_without_an_install_are_unavailable(self):
        nr_install._receipt(self.row).unlink()
        self.assertFalse(settings.snapshot({}, self.row)['available'])
        self.assertFalse(settings.snapshot({}, {})['available'])

    def test_unset_keys_are_reported_as_the_addon_default(self):
        result = settings.snapshot({}, self.row)
        self.assertIn('character_intensity', result['unreported'])
        self.assertNotIn('environment_intensity', result['unreported'])


if __name__ == '__main__':
    unittest.main()
