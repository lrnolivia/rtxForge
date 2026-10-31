"""HDR startup preferences preserve native edits and wait for the game to exit."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from tests import test_renodx_hdr as fixtures
hdr, t = fixtures.hdr, fixtures.t
import renodx_hdr_settings as settings


class HdrSettingsTests(unittest.TestCase):
    def setUp(self):
        fixtures.HdrTests.setUp(self)
        hdr.apply({}, hdr.prepare({}, self.row))
        read = t.read_json
        catalog_path = hdr.ROOT / 'providers/renodx-hdr-settings.json'
        catalog = copy.deepcopy(read(catalog_path))
        catalog['profiles'][0]['addon_sha256'] = t.sha(self.addon)
        self.profile = catalog['profiles'][0]
        p = patch.object(t, 'read_json', side_effect=lambda path: copy.deepcopy(catalog) if Path(path) == catalog_path else read(path))
        p.start(); self.addCleanup(p.stop)
        self.ini = self.game / 'ReShade.ini'
        self.key = 'ToneMapGameNits'
        self.ini.write_text(t.setvalue(self.ini.read_text(encoding='utf-8'), self.profile['section'], self.key, '203') + '\n[Unrelated]\nKeep=mine\n', encoding='utf-8')

    def value(self):
        return float(t.ini(self.ini.read_text(encoding='utf-8')).get(self.profile['section'], self.key))

    def test_closed_game_applies_only_requested_keys_and_keeps_exact_backup(self):
        before = self.ini.read_bytes()
        result = settings.save({}, self.row, {self.key: 250})
        self.assertTrue(result['available']); self.assertFalse(result['pending'])
        self.assertEqual(self.value(), 250)
        self.assertIn('Keep=mine', self.ini.read_text())
        self.assertEqual((self.state / 'hdr-preferences/backups' / t.sha(before)).read_bytes(), before)

    def test_running_game_queues_and_applies_after_exit(self):
        self.engine.running = True; before = self.ini.read_bytes()
        result = settings.save({}, self.row, {self.key: 300})
        self.assertTrue(result['pending']); self.assertEqual(result['values'][self.key], 300)
        self.assertEqual(self.ini.read_bytes(), before)
        self.assertEqual(settings.flush({})['applied'], 0)
        self.engine.running = False
        self.assertEqual(settings.flush({})['applied'], 1); self.assertEqual(self.value(), 300)

    def test_native_edit_wins_until_user_explicitly_reedits(self):
        self.engine.running = True
        settings.save({}, self.row, {self.key: 300})
        self.ini.write_text(t.setvalue(self.ini.read_text(), self.profile['section'], self.key, '275'))
        self.engine.running = False
        self.assertEqual(settings.flush({})['applied'], 0); self.assertEqual(self.value(), 275)
        self.assertIn('native menu', settings.snapshot({}, self.row)['message'])
        settings.save({}, self.row, {self.key: 325})
        self.assertEqual(self.value(), 325); self.assertFalse(settings.snapshot({}, self.row)['pending'])

    def test_changed_addon_does_not_apply_queued_changes(self):
        self.engine.running = True; settings.save({}, self.row, {self.key: 300})
        (self.game / 'renodx-game.addon64').write_bytes(b'drift')
        self.engine.running = False
        self.assertEqual(settings.flush({})['applied'], 0); self.assertEqual(self.value(), 203)
        self.assertFalse(settings.snapshot({}, self.row)['available'])

    def test_invalid_values_are_refused_before_writes(self):
        before = self.ini.read_bytes()
        for changes in ({self.key: True}, {self.key: float('nan')}, {self.key: 100000}, {'Unknown': 1}, {}, {'ToneMapType': .5}):
            with self.subTest(changes=changes), self.assertRaises(t.Refusal): settings.save({}, self.row, changes)
        self.assertEqual(self.ini.read_bytes(), before)
        self.assertFalse(list((self.state / 'hdr-preferences').glob('*.json')))

    def test_invalid_row_snapshot_is_safe(self):
        self.assertFalse(settings.snapshot({}, {})['available'])

    def test_flush_reads_edits_merged_while_waiting_for_lock(self):
        import contextlib
        self.engine.running = True
        settings.save({}, self.row, {self.key: 250})
        self.engine.running = False
        path = next((self.state / 'hdr-preferences').glob('*.json'))
        @contextlib.contextmanager
        def lock():
            queued = t.read_json(path)
            queued['changes']['ToneMapUINits'] = 275
            queued['before']['ToneMapUINits'] = 203
            t.atomic_file(path, __import__('json').dumps(queued).encode(), 0o600)
            yield
        with patch.object(self.engine, 'mutation_lock', lock):
            self.assertEqual(settings.flush({})['applied'], 1)
        self.assertEqual(self.value(), 250)
        self.assertEqual(float(t.ini(self.ini.read_text()).get(self.profile['section'], 'ToneMapUINits')), 275)

    def test_unstored_display_calibration_is_not_presented_as_measured(self):
        self.assertIn('ToneMapPeakNits', settings.snapshot({}, self.row)['unreported'])
        result = settings.save({}, self.row, {'ToneMapPeakNits': 600})
        self.assertNotIn('ToneMapPeakNits', result['unreported'])
        self.assertEqual(result['values']['ToneMapPeakNits'], 600)
