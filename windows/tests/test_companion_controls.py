"""Owned-target, preset persistence and actual Windows mailbox protocol checks."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'windows/engine-host')]
import companion_controls as control
import transactions as t


def snapshot(pid=123, version=2):
    raw = bytearray(512 if version >= 3 else 256)
    struct.pack_into('<IIIi', raw, 0, control.MAGIC, version, pid, 10)
    for key, offset in control.OFFSETS.items():
        if key not in control.supported_keys(version): continue
        struct.pack_into('<f' if key in control._FLOATS else '<i', raw, offset, control.DEFAULTS[key])
    struct.pack_into('<iffiiii', raw, 100, 1, 0.0, 28.0, 5, 3, 100, 300)
    if version >= 2: struct.pack_into('<iiiiii', raw, 136, 0, 4, 100, 1000, 1, 3)
    return raw


class ControlsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.game = self.root / 'game'
        self.target = self.game / 'Bin'
        self.target.mkdir(parents=True)
        (self.target / 'Game.exe').write_bytes(b'game')
        (self.target / 'winhttp.dll').write_bytes(b'verified loader')
        (self.target / 'OptiScaler.ini').write_text('[DlssNr]\nEnabled=true\nPreset=2\nPreSr=true\nCacheEnabled=false\n[DLSSG]\nOverrideInterpolationCount=3\n')
        self.metadata = {'provider': {'id': 'skynizz'}, 'feature_mode': 'nr-mfg', 'proxy': 'winhttp.dll',
                         'files': {'winhttp.dll': hashlib.sha256(b'verified loader').hexdigest(),
                                   'nvngx_dlssnr.dll': 'a' * 64}}
        self.write_metadata()
        self.row = {'game': str(self.game), 'exe': 'Bin/Game.exe', 'name': 'Fixture', 'appid': '1'}
        self.addCleanup(patch.stopall)
        patch.object(control.Controls, '_start_watcher', lambda _: None).start()
        self.controls = control.Controls(self.root / 'state')

    def write_metadata(self):
        (self.target / '.rtxforge-install.json').write_text(json.dumps(self.metadata))

    def test_versions_and_actual_presents_are_separate_from_requested_values(self):
        found = control.decode(snapshot(), 123)
        self.assertEqual(found['values']['multiplier'], -1)
        self.assertEqual(found['native_presented'], 4)
        older = control.decode(snapshot(version=1), 123)
        self.assertNotIn('native_presented', older)
        expanded = control.decode(snapshot(version=3), 123)
        self.assertEqual(expanded['values']['skin'], -1)
        self.assertEqual(expanded['values']['passes'], 1)
        self.assertEqual(expanded['values']['work_scale'], 1)
        self.assertNotIn('work_scale', found['values'])
        for data, pid in [(snapshot(), 999), (snapshot(version=99), 123), (snapshot()[:200], 123)]:
            with self.assertRaises(t.Refusal): control.decode(data, pid)

    def test_invalid_requests_and_nonfinite_snapshots_refuse(self):
        for values in [{'intensity': float('nan')}, {'tone': float('inf')}, {'multiplier': 1},
                       {'enabled': True}, {'preset': 4}, {'interval': 0}, {'unknown': 1},
                       {'skin': -1.01}, {'work_scale': .24}, {'passes': 4}, {'auto_mask': 2}]:
            with self.subTest(values=values), self.assertRaises(t.Refusal): control.validate_changes(values)
        raw = snapshot()
        struct.pack_into('<f', raw, 68, float('nan'))
        with self.assertRaises(t.Refusal): control.decode(raw, 123)

    def test_original_overlay_session_is_read_only_to_the_companion(self):
        raw = snapshot(version=5)
        struct.pack_into('<ii', raw, 368, 1, 0x2d)
        struct.pack_into('<f', raw, control.OFFSETS['colour'], 4.0)
        found = control.decode(raw, 123)
        box = SimpleNamespace(pid=123, k=SimpleNamespace(GetTickCount=lambda:1010))
        status = self.controls._present(self.controls._game({'row':self.row}), box, found)
        self.assertEqual(found['original_menu_key'], 0x2d)
        self.assertAlmostEqual(found['values']['colour'], 4.0)
        self.assertFalse(status['can_edit'])
        self.assertFalse(status['can_save'])
        self.assertIn('Restart', status['detail'])
        # File ownership or reported NR activity cannot bypass native ownership.
        self.assertTrue(found['nr_running'])
        self.assertTrue(status['native_fresh'])

    def test_launch_policy_wins_over_saved_nr_enablement(self):
        saved = {'enabled': 1, 'multiplier': 4, 'intensity': 1.37}
        self.assertEqual(control.startup_changes({'nr_on_launch': False, 'can_nr': True}, saved),
                         {'enabled': 0, 'multiplier': 4, 'intensity': 1.37})
        self.assertEqual(saved['enabled'], 1)
        self.assertEqual(control.startup_changes({'can_nr': True}, saved), saved)

    def test_colour_matches_upstream_range_and_other_image_bounds_stay_intact(self):
        self.assertEqual(control.validate_changes({'colour':4.0}), {'colour':4.0})
        for changes in ({'colour':4.01},{'intensity':2.01},{'structure':2.01},{'tone':2.01}):
            with self.assertRaises(t.Refusal): control.validate_changes(changes)

    def test_supported_subset_controls_follow_the_installed_features(self):
        self.metadata['feature_mode'] = 'mfg-only'; self.write_metadata()
        game = self.controls._game({'row':self.row})
        self.assertTrue(game['can_mfg']); self.assertFalse(game['can_nr'])
        with self.assertRaisesRegex(t.Refusal, 'Neural rendering is not installed'):
            self.controls.save({'row':self.row, 'changes':{'enabled':1, 'multiplier':4}})
        self.controls.save({'row':self.row, 'changes':{'multiplier':4}})
        self.assertEqual(next(iter(self.controls.presets.values()))['changes'], {'multiplier':4})
        self.metadata['feature_mode'] = 'nr-only'; self.write_metadata()
        game = self.controls._game({'row':self.row})
        self.assertTrue(game['can_nr']); self.assertFalse(game['can_mfg'])
        with self.assertRaisesRegex(t.Refusal, 'MFG package'):
            self.controls.save({'row':self.row, 'changes':{'multiplier':4}})

    def test_sharpening_preserves_the_actual_presets_filter_and_bounds(self):
        path = self.target/'OptiScaler.ini'
        path.write_text(path.read_text()+'[Sharpness]\nShader=da\nOverrideSharpness=true\nSharpness=0.65\n[CAS]\nEnabled=true\nMotionSharpnessEnabled=true\nMotionSharpness=0.3\n')
        values = self.controls._configured(self.controls._game({'row':self.row}))
        self.assertEqual(values['sharpen_shader'],1)
        self.assertEqual(values['sharpen'],1)
        self.assertAlmostEqual(values['sharpness'],.65)
        for changes in ({'sharpness':1.01},{'motion_sharpness':-1},{'sharpen_shader':3}):
            with self.assertRaises(t.Refusal):control.validate_changes(changes)

    def test_file_pills_distinguish_owned_other_absent_and_changed(self):
        nr = self.target/'nvngx_dlssnr.dll';nr.write_bytes(b'managed NR')
        self.metadata['files'][nr.name]=hashlib.sha256(nr.read_bytes()).hexdigest();self.write_metadata()
        (self.target/'nvngx_dlss.dll').write_bytes(b'game provided SR')
        game=self.controls._game({'row':self.row})
        states=self.controls.pipelines(game)
        self.assertEqual({key:value['state'] for key,value in states.items()},
                         {'SR':'other','RR':'absent','NR':'managed','FG':'absent'})
        self.assertIn('does not establish live activity',states['NR']['detail'])
        nr.write_bytes(b'changed NR')
        self.assertEqual(self.controls.pipelines(game)['NR']['state'],'changed')
        nr.unlink()
        self.assertEqual(self.controls.pipelines(game)['NR']['state'],'changed')

    def test_helper_target_discovery_uses_install_records_without_library_scan(self):
        self.controls.installations=self.root/'engine-state/targets'
        folder=self.controls.installations/'one';folder.mkdir(parents=True)
        record={'status':'active','name':'Fixture','exe':str(self.target/'Game.exe'),
                'current':{'archive':{'family':'skynizz'}}}
        (folder/'baseline.json').write_text(json.dumps(record))
        rows=self.controls.targets()
        self.assertEqual(rows,[{'game':str(self.target),'exe':'Game.exe','name':'Fixture','appid':None}])
        record['status']='restored';(folder/'baseline.json').write_text(json.dumps(record))
        self.assertFalse(self.controls.targets())

    def test_reset_applies_installed_settings_clears_preset_and_preserves_game_files(self):
        self.controls.save({'row':self.row,'changes':{'intensity':1.25}})
        before={str(p):p.read_bytes() for p in self.target.rglob('*') if p.is_file()}
        class Box:
            pid=123
            k=SimpleNamespace(GetTickCount=lambda:1010)
            applied=None
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def read(self):return control.decode(snapshot(version=4),self.pid)
            def apply(self,changes):
                self.applied=changes
                return self.read()|{'values':changes}
        box=Box()
        with patch.object(self.controls,'_open',return_value=box):
            with self.assertRaisesRegex(t.Refusal,'session changed'):
                self.controls.reset({'row':self.row,'pid':456})
            self.assertTrue(self.controls.presets)
            result=self.controls.reset({'row':self.row,'pid':123})
        self.assertEqual(box.applied['preset'],2)
        self.assertEqual(box.applied['multiplier'],4)
        self.assertFalse(result['saved'])
        self.assertFalse(self.controls.presets)
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.target.rglob('*') if p.is_file()})

    def test_active_game_uses_verified_process_and_never_a_library_default(self):
        class Box:
            pid = 123
            k = SimpleNamespace(GetTickCount=lambda: 1010)
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return control.decode(snapshot(), self.pid)
        with patch.object(self.controls, '_processes', return_value={'game.exe': [123]}), \
             patch.object(self.controls, '_open', return_value=Box()):
            result = self.controls.active({'rows': [self.row], 'foreground_pid': 123})
            self.assertEqual(result['row']['game'], self.row['game'])
            self.assertEqual(result['pid'], 123)
            (self.target / 'winhttp.dll').write_bytes(b'changed')
            self.assertIsNone(self.controls.active({'rows': [self.row], 'foreground_pid': 123})['row'])
        with patch.object(self.controls, '_processes', return_value={}):
            self.assertIsNone(self.controls.active({'rows': [self.row]})['row'])

    def test_two_running_games_require_foreground_or_retained_verified_session(self):
        import shutil
        second = self.root / 'second'
        shutil.copytree(self.game, second)
        row2 = self.row | {'game': str(second), 'name': 'Second'}
        class Box:
            k = SimpleNamespace(GetTickCount=lambda: 1010)
            def __init__(self, pid): self.pid = pid
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return control.decode(snapshot(self.pid), self.pid)
        with patch.object(self.controls, '_processes', return_value={'game.exe': [123, 456]}), \
             patch.object(self.controls, '_open', side_effect=lambda g: Box(123 if g['root'] == self.game else 456)):
            params = {'rows': [self.row, row2]}
            self.assertEqual(self.controls.active(params | {'foreground_pid': 456})['row']['name'], 'Second')
            self.assertIsNone(self.controls.active(params)['row'])
            self.assertEqual(self.controls.active(params | {'retained_pid': 123})['pid'], 123)

    def test_restarted_game_cannot_receive_a_previous_sessions_save(self):
        class Box:
            pid = 456
            def __enter__(self): return self
            def __exit__(self, *_): pass
        with patch.object(self.controls, '_open', return_value=Box()), \
             self.assertRaisesRegex(t.Refusal, 'session changed'):
            self.controls.save({'row': self.row, 'pid': 123, 'changes': {'intensity': 1.2}})
        self.assertFalse(self.controls.presets)

    def test_stalled_runtime_disables_edits_and_unavailable_timing_is_not_zero(self):
        game = self.controls._game({'row': self.row})
        box = SimpleNamespace(pid=123, k=SimpleNamespace(GetTickCount=lambda: 1010))
        found = control.decode(snapshot(), 123)
        self.controls.previous[123] = (found['sequence'], time.monotonic() - 10)
        result = self.controls._present(game, box, found)
        self.assertFalse(result['can_edit'])
        self.assertFalse(result['native_fresh'])
        self.assertIsNone(result['nr_ms'])
        self.assertEqual(result['state'], 'stalled')

    def test_presets_merge_without_game_writes_and_reject_changed_recipes(self):
        before = {str(p.relative_to(self.game)): p.read_bytes() for p in self.game.rglob('*') if p.is_file()}
        self.controls.save({'row': self.row, 'changes': {'intensity': 1.25}})
        self.controls.save({'row': self.row, 'changes': {'multiplier': 3}})
        with patch.object(self.controls, '_open', return_value=None):
            result = self.controls.status({'row': self.row})
            self.assertEqual(result['saved_values'], {'intensity': 1.25, 'multiplier': 3})
            self.assertTrue(result['preset_compatible'])
            reloaded = control.Controls(self.root / 'state')
            self.assertEqual(reloaded.presets, self.controls.presets)
            self.metadata['files']['nvngx_dlssnr.dll'] = 'b' * 64
            self.write_metadata()
            self.assertFalse(self.controls.status({'row': self.row})['preset_compatible'])
        # Metadata changed only in this fixture to model a package update.
        self.metadata['files']['nvngx_dlssnr.dll'] = 'a' * 64
        self.write_metadata()
        self.assertEqual(before, {str(p.relative_to(self.game)): p.read_bytes() for p in self.game.rglob('*') if p.is_file()})
        self.controls.forget({'row': self.row})
        self.assertFalse(self.controls.presets)

    def test_unowned_or_changed_loader_and_escaping_exe_refuse(self):
        self.controls._game({'row': self.row})
        (self.target / 'winhttp.dll').write_bytes(b'tampered')
        with self.assertRaisesRegex(t.Refusal, 'loader changed'): self.controls._game({'row': self.row})
        for exe in [str(self.target / 'Game.exe'), '../../outside.exe']:
            with self.assertRaises(t.Refusal): self.controls._game({'row': self.row | {'exe': exe}})

    def test_external_owner_does_not_accept_internal_mfg_commands(self):
        self.metadata['files']['renodx-mfgunlock.addon64'] = 'c' * 64
        self.write_metadata()
        with self.assertRaisesRegex(t.Refusal, 'does not support'):
            self.controls.apply({'row': self.row, 'changes': {'multiplier': 4}})
        with self.assertRaises(t.Refusal): self.controls.save({'row': self.row, 'changes': {'multiplier': 4}})
        self.controls.save({'row': self.row, 'changes': {'intensity': 1.1}})

    def test_failed_saved_command_is_attempted_once_for_a_process(self):
        self.controls.save({'row': self.row, 'changes': {'intensity': 1.1}})
        box = SimpleNamespace(pid=123, k=SimpleNamespace(GetTickCount=lambda: 1010))
        class Open:
            def __enter__(self): return box
            def __exit__(self, *_): pass
            def __getattr__(self, name): return getattr(box, name)
        box.read = lambda: control.decode(snapshot(), 123)
        with patch.object(self.controls, '_processes', return_value={'game.exe': [123]}), \
             patch.object(self.controls, '_open', return_value=Open()), \
             patch.object(box, 'apply', create=True, side_effect=t.Refusal('not accepted')) as apply, \
             patch.object(control.time, 'sleep', side_effect=[None, None, RuntimeError('stop')]):
            with self.assertRaisesRegex(RuntimeError, 'stop'): self.controls._watch()
        self.assertEqual(apply.call_count, 1)

    def test_malformed_saved_records_do_not_stop_the_watcher(self):
        self.controls.state.mkdir(parents=True)
        for index, record in enumerate([None, [], {'schema': 99}, {'schema': 1, 'row': []},
                                        {'schema': 1, 'row': {'game': 'x', 'exe': []}}]):
            (self.controls.state / f'{index}.json').write_text(json.dumps(record))
        self.assertFalse(control.Controls(self.root / 'state').presets)


@unittest.skipUnless(os.name == 'nt', 'Windows named mapping')
class WindowsProtocolTest(unittest.TestCase):
    def test_actual_mapping_ack_and_backend_ceiling(self):
        for version in (2, 3, 4):
            with self.subTest(version=version): self.mapping_round_trip(version)

    def mapping_round_trip(self, version):
        k = control._api()
        k.CreateFileMappingW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_wchar_p]
        k.CreateFileMappingW.restype = ctypes.c_void_p
        raw = snapshot(os.getpid(), version)
        handle = k.CreateFileMappingW(ctypes.c_void_p(-1), None, 4, 0, len(raw), f'Local\\rtxForge.controls.{os.getpid()}')
        self.assertTrue(handle)
        self.assertNotEqual(ctypes.get_last_error(), 183)
        view = k.MapViewOfFile(handle, 6, 0, 0, len(raw))
        self.assertTrue(view)
        stopped = threading.Event()
        ctypes.memmove(view, bytes(raw), len(raw))
        def renderer():
            while not stopped.wait(.005):
                command = ctypes.c_long.from_address(view + 16).value
                if command <= 0 or command & 1 or command == ctypes.c_long.from_address(view + 20).value: continue
                ctypes.c_long.from_address(view + 12).value += 1
                data = ctypes.string_at(view + 28, 36)
                ctypes.memmove(view + 64, data, 36)
                ctypes.c_long.from_address(view + 132).value = ctypes.c_long.from_address(view + 128).value
                if version >= 3:
                    ctypes.memmove(view + 288, ctypes.string_at(view + 256, 32), 32)
                if version >= 4:
                    ctypes.memmove(view + 344, ctypes.string_at(view + 320, 24), 24)
                ctypes.c_long.from_address(view + 24).value = 1
                ctypes.c_long.from_address(view + 20).value = command
                ctypes.c_long.from_address(view + 12).value += 1
        worker = threading.Thread(target=renderer)
        worker.start()
        try:
            with control.Mailbox(os.getpid(), Path(sys.executable).resolve(), True) as box:
                result = box.apply({'multiplier': 4, 'intensity': 1.25, 'preset': 2})
                self.assertEqual(result['values']['multiplier'], 4)
                self.assertEqual(result['values']['intensity'], 1.25)
                self.assertEqual(result['values']['preset'], 2)
                previous = result['command']
                if version >= 3:
                    result = box.apply({'work_scale': .75, 'skin': -.5, 'detail': 1.25, 'passes': 2, 'auto_mask': 0})
                    self.assertEqual(result['values']['work_scale'], .75)
                    self.assertEqual(result['values']['skin'], -.5)
                    self.assertEqual(result['values']['detail'], 1.25)
                    self.assertEqual(result['values']['passes'], 2)
                    self.assertEqual(result['values']['auto_mask'], 0)
                    previous = result['command']
                else:
                    with self.assertRaisesRegex(t.Refusal, 'Update this game package'): box.apply({'passes': 2})
                    self.assertEqual(box.read()['command'], previous)
                if version >= 4:
                    result = box.apply({'sharpen': 1, 'sharp_override': 1, 'sharpen_shader': 1, 'sharpness': .65,
                                        'motion_sharpen': 1, 'motion_sharpness': .3})
                    self.assertEqual(result['values']['sharpen_shader'], 1)
                    self.assertAlmostEqual(result['values']['sharpness'], .65)
                    previous = result['command']
                else:
                    with self.assertRaisesRegex(t.Refusal, 'Update this game package'): box.apply({'sharpness': .5})
                    self.assertEqual(box.read()['command'], previous)
                ctypes.c_long.from_address(view + 112).value = 1
                with self.assertRaises(t.Refusal): box.apply({'multiplier': 4})
                self.assertEqual(box.read()['command'], previous)
        finally:
            stopped.set(); worker.join()
            k.UnmapViewOfFile(view); k.CloseHandle(handle)


if __name__ == '__main__': unittest.main()
