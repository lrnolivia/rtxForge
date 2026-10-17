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
    raw = bytearray(256)
    struct.pack_into('<IIIi', raw, 0, control.MAGIC, version, pid, 10)
    for key, offset in control.OFFSETS.items():
        struct.pack_into('<f' if key in control._FLOATS else '<i', raw, offset, control.DEFAULTS[key])
    struct.pack_into('<iffiiii', raw, 100, 1, 0.0, 28.0, 5, 3, 100, 300)
    if version == 2: struct.pack_into('<iiiiii', raw, 136, 0, 4, 100, 1000, 1, 3)
    return raw


class ControlsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
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
        for data, pid in [(snapshot(), 999), (snapshot(version=99), 123), (snapshot()[:200], 123)]:
            with self.assertRaises(t.Refusal): control.decode(data, pid)

    def test_invalid_requests_and_nonfinite_snapshots_refuse(self):
        for values in [{'intensity': float('nan')}, {'tone': float('inf')}, {'multiplier': 1},
                       {'enabled': True}, {'preset': 4}, {'interval': 0}, {'unknown': 1}]:
            with self.subTest(values=values), self.assertRaises(t.Refusal): control.validate_changes(values)
        raw = snapshot()
        struct.pack_into('<f', raw, 68, float('nan'))
        with self.assertRaises(t.Refusal): control.decode(raw, 123)

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
        k = control._api()
        k.CreateFileMappingW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_wchar_p]
        k.CreateFileMappingW.restype = ctypes.c_void_p
        handle = k.CreateFileMappingW(ctypes.c_void_p(-1), None, 4, 0, 256, f'Local\\rtxForge.controls.{os.getpid()}')
        self.assertTrue(handle)
        self.assertNotEqual(ctypes.get_last_error(), 183)
        view = k.MapViewOfFile(handle, 6, 0, 0, 256)
        self.assertTrue(view)
        stopped = threading.Event()
        ctypes.memmove(view, bytes(snapshot(os.getpid())), 256)
        def renderer():
            while not stopped.wait(.005):
                command = ctypes.c_long.from_address(view + 16).value
                if command <= 0 or command & 1 or command == ctypes.c_long.from_address(view + 20).value: continue
                ctypes.c_long.from_address(view + 12).value += 1
                data = ctypes.string_at(view + 28, 36)
                ctypes.memmove(view + 64, data, 36)
                ctypes.c_long.from_address(view + 132).value = ctypes.c_long.from_address(view + 128).value
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
                ctypes.c_long.from_address(view + 112).value = 1
                with self.assertRaises(t.Refusal): box.apply({'multiplier': 4})
                self.assertEqual(box.read()['command'], previous)
        finally:
            stopped.set(); worker.join()
            k.UnmapViewOfFile(view); k.CloseHandle(handle)


if __name__ == '__main__': unittest.main()
