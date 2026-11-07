"""Library-scan shortcuts: each answer is reused only while its input is unchanged."""
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import feeder_legacy  # noqa: E402
import feeder_provider as feeder  # noqa: E402
import transactions as t  # noqa: E402


def pe(machine=0x8664):
    header = bytearray(0x40)
    header[:2] = b'MZ'
    struct.pack_into('<I', header, 0x3C, 0x40)
    return bytes(header) + b'PE\0\0' + struct.pack('<H', machine) + bytes(64)


class ReadOnlyPassTest(unittest.TestCase):
    def counted(self, paths):
        real, calls = os.lstat, []
        def lstat(path, *a, **k):
            calls.append(str(path))
            return real(path, *a, **k)
        with mock.patch.object(t.os, 'lstat', lstat):
            for path in paths:
                t.safe(path)
        return calls

    def test_parent_folders_are_checked_once_per_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            names = [base / f'file{i}.bin' for i in range(5)]
            for name in names:
                name.write_bytes(b'x')
            outside = self.counted(names)
            with t.read_only_pass():
                inside = self.counted(names)
            depth = len(base.parents) + 1
            self.assertEqual(len(outside), 5 * (depth + 1))
            # The first path checks every folder; the rest check only themselves.
            self.assertEqual(len(inside), depth + 1 + 4)
            # The pass ends with its block.
            self.assertEqual(len(self.counted(names[:1])), depth + 1)

    def test_a_link_is_still_refused_inside_a_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            (base / 'real').mkdir()
            target = base / 'real' / 'file.bin'
            target.write_bytes(b'x')
            real = os.lstat
            def lstat(path, *a, **k):
                info = real(path, *a, **k)
                if Path(path) == base / 'real':
                    fields = list(info)
                    fields[0] = 0o120777  # S_IFLNK
                    return os.stat_result(fields)
                return info
            with t.read_only_pass(), mock.patch.object(t.os, 'lstat', lstat):
                with self.assertRaises(t.Refusal):
                    t.safe(target)
                # A refused folder is never remembered as checked.
                with self.assertRaises(t.Refusal):
                    t.safe(target)


class MachineCacheTest(unittest.TestCase):
    def test_machine_is_read_once_per_executable_version(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'game.exe'
            exe.write_bytes(pe(0x8664))
            with mock.patch.dict(os.environ, {'RTXFORGE_PROBE_CACHE': ''}), mock.patch.object(feeder, '_PROBES', None):
                with mock.patch.object(feeder_legacy, '_machine', wraps=feeder_legacy._machine) as read:
                    self.assertEqual(feeder_legacy.machine(exe), 0x8664)
                    self.assertEqual(feeder_legacy.machine(exe), 0x8664)
                    self.assertEqual(read.call_count, 1)
                    exe.write_bytes(pe(0x14c) + b'longer')
                    self.assertEqual(feeder_legacy.machine(exe), 0x14c)
                    self.assertEqual(read.call_count, 2)

    def test_an_unsupported_file_is_refused_every_time(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'tool.exe'
            exe.write_bytes(b'not a program' * 10)
            with mock.patch.dict(os.environ, {'RTXFORGE_PROBE_CACHE': ''}), mock.patch.object(feeder, '_PROBES', None):
                for _ in range(2):
                    with self.assertRaises(t.Refusal):
                        feeder_legacy.machine(exe)


class MentionedApisTest(unittest.TestCase):
    def test_one_pass_matches_any_case_like_the_old_search(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'packed.exe'
            exe.write_bytes(b'\0junk D3D11.DLL more d3d10_1.dll and D3d12.Dll; d3d9.dllx d3d10.DLL end')
            self.assertEqual(feeder.mentioned_apis(exe), {'d3d9', 'd3d10', 'd3d10_1', 'd3d11', 'd3d12'})
            exe.write_bytes(b'opengl32.dll d3dx9_43.dll dxgi.dll')
            self.assertEqual(feeder.mentioned_apis(exe), set())

    def test_delay_imports_of_a_file_that_is_not_a_program(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'empty.exe'
            exe.write_bytes(b'')
            self.assertEqual(feeder.delay_imported_dlls(exe), set())
            exe.write_bytes(b'MZ' + bytes(200))
            self.assertEqual(feeder.delay_imported_dlls(exe), set())


if __name__ == '__main__':
    unittest.main()
