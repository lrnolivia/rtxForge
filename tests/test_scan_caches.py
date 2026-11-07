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

    def test_a_name_across_a_chunk_boundary_is_found(self):
        import re
        pattern = re.compile(rb'(?i)d3d(9|10_1|10|11|12)\.dll')
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'packed.exe'
            for offset in range(0, 24):
                data = b'x' * offset + b'D3D10_1.Dll' + b'y' * 7 + b'd3D12.DLL' + b'z' * 5
                exe.write_bytes(data)
                expected = {'d3d' + match[1].decode().lower() for match in pattern.finditer(data)}
                self.assertEqual(feeder.mentioned_apis(exe, chunk=8), expected, offset)


class PrefetchTest(unittest.TestCase):
    def test_prefetch_fills_the_cache_the_later_digests_read(self):
        import file_stamps
        with tempfile.TemporaryDirectory() as folder:
            files = [Path(folder) / f'part{i}.dll' for i in range(4)]
            for index, path in enumerate(files):
                path.write_bytes(bytes([index]) * (file_stamps.MIN_SIZE + 1))
            small = Path(folder) / 'small.txt'; small.write_bytes(b'small')
            with mock.patch.dict(os.environ, {'RTXFORGE_STAMP_CACHE': ''}):
                file_stamps.forget()
                self.addCleanup(file_stamps.forget)
                expected = [file_stamps._hash(path) for path in files]
                with mock.patch.object(file_stamps, '_hash', wraps=file_stamps._hash) as read:
                    file_stamps.prefetch([*files, small, Path(folder) / 'absent.dll', files[0]])
                    self.assertEqual(read.call_count, 4)  # each large file once; small and absent ones left alone
                    self.assertEqual([file_stamps.digest(path) for path in files], expected)
                    self.assertEqual(read.call_count, 4)
                    file_stamps.prefetch(files)
                    self.assertEqual(read.call_count, 4)

    def test_intact_gives_the_same_answer_with_prefetched_digests(self):
        import cross_os
        import file_stamps
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            names = ['nvngx.dll', 'sub/OptiScaler.asi', 'OptiScaler.ini']
            for name in names:
                (target / name).parent.mkdir(parents=True, exist_ok=True)
                (target / name).write_bytes(name.encode() * (file_stamps.MIN_SIZE // len(name) + 1))
            with mock.patch.dict(os.environ, {'RTXFORGE_STAMP_CACHE': ''}):
                file_stamps.forget()
                self.addCleanup(file_stamps.forget)
                record = {'provider': {'id': 'skynizz'}, 'files': {name: file_stamps._hash(target / name) for name in names}}
                self.assertTrue(cross_os.intact(target, record))
                (target / 'OptiScaler.ini').write_bytes(b'edited in game')  # tuning never breaks identity
                self.assertTrue(cross_os.intact(target, record))
                (target / 'nvngx.dll').write_bytes(b'changed')
                self.assertFalse(cross_os.intact(target, record))
                (target / 'nvngx.dll').unlink()
                self.assertFalse(cross_os.intact(target, record))

    def test_delay_imports_of_a_file_that_is_not_a_program(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'empty.exe'
            exe.write_bytes(b'')
            self.assertEqual(feeder.delay_imported_dlls(exe), set())
            exe.write_bytes(b'MZ' + bytes(200))
            self.assertEqual(feeder.delay_imported_dlls(exe), set())


if __name__ == '__main__':
    unittest.main()
