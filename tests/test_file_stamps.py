import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import file_stamps


class FileStampsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / 'file-stamps.json'
        patcher = mock.patch.dict(os.environ, {'RTXFORGE_STAMP_CACHE': str(self.cache)})
        patcher.start(); self.addCleanup(patcher.stop)
        file_stamps.forget(); self.addCleanup(file_stamps.forget)
        self.reads = []
        real = file_stamps._hash
        def counted(path):
            self.reads.append(Path(path).name)
            return real(path)
        patcher = mock.patch.object(file_stamps, '_hash', counted)
        patcher.start(); self.addCleanup(patcher.stop)
        self.data = os.urandom(file_stamps.MIN_SIZE + 10)
        self.file = self.root / 'nvngx_dlss.dll'
        self.file.write_bytes(self.data)

    def sha(self, data):
        return hashlib.sha256(data).hexdigest()

    def test_unchanged_file_is_read_once(self):
        self.assertEqual(file_stamps.digest(self.file), self.sha(self.data))
        self.assertEqual(file_stamps.digest(self.file), self.sha(self.data))
        self.assertEqual(self.reads, ['nvngx_dlss.dll'])

    def test_written_or_replaced_file_is_read_again(self):
        file_stamps.digest(self.file)
        changed = self.data[:-1] + bytes([self.data[-1] ^ 1])
        # Same size, the old modified time put back, and a new file in its place.
        replacement = self.root / 'replacement'
        replacement.write_bytes(changed)
        info = self.file.stat()
        os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
        os.replace(replacement, self.file)
        self.assertEqual(file_stamps.digest(self.file), self.sha(changed))
        grown = changed + b'x'
        self.file.write_bytes(grown)
        self.assertEqual(file_stamps.digest(self.file), self.sha(grown))
        self.assertEqual(len(self.reads), 3)

    def test_digests_survive_a_restart(self):
        file_stamps.digest(self.file)
        file_stamps.save()
        file_stamps.forget()
        self.assertEqual(file_stamps.digest(self.file), self.sha(self.data))
        self.assertEqual(self.reads, ['nvngx_dlss.dll'])

    def test_small_files_and_memory_only_cache_are_not_written(self):
        small = self.root / 'OptiScaler.ini'; small.write_bytes(b'[DLSS]\n')
        file_stamps.digest(small)
        file_stamps.save()
        self.assertFalse(self.cache.exists())
        with mock.patch.dict(os.environ, {'RTXFORGE_STAMP_CACHE': ''}):
            file_stamps.digest(self.file); file_stamps.save()
        self.assertFalse(self.cache.exists())

    def test_damaged_cache_is_ignored(self):
        self.cache.write_text('{not json', encoding='utf-8')
        self.assertEqual(file_stamps.digest(self.file), self.sha(self.data))
        self.cache.write_text('{"schema": 1, "files": {"x": [1, 2]}}', encoding='utf-8')
        file_stamps.forget()
        self.assertEqual(file_stamps.digest(self.file), self.sha(self.data))

    def test_file_changing_while_read_is_not_remembered(self):
        real = file_stamps._hash
        def racing(path):
            value = real(path)
            Path(path).write_bytes(self.data + b'late')
            return value
        with mock.patch.object(file_stamps, '_hash', racing):
            file_stamps.digest(self.file)
        self.assertEqual(file_stamps.digest(self.file), self.sha(self.data + b'late'))

    def test_operation_reads_each_file_once_even_if_known(self):
        file_stamps.digest(self.file)
        self.reads.clear()
        operation = file_stamps.Operation()
        self.assertEqual(operation.digest(self.file), self.sha(self.data))
        self.assertEqual(operation.digest(self.file), self.sha(self.data))
        self.assertEqual(self.reads, ['nvngx_dlss.dll'])
        self.file.write_bytes(b'changed during the operation')
        self.assertEqual(operation.digest(self.file), self.sha(b'changed during the operation'))
        self.assertEqual(file_stamps.Operation().digest(self.file), self.sha(b'changed during the operation'))
        self.assertEqual(len(self.reads), 3)

    def test_known_never_reads_a_large_file_and_warm_fills_it_in(self):
        self.assertIsNone(file_stamps.known(self.file))
        self.assertEqual(self.reads, [])
        file_stamps.warm([self.file]).join(10)
        self.assertEqual(file_stamps.known(self.file), self.sha(self.data))
        self.assertEqual(self.reads, ['nvngx_dlss.dll'])
        self.assertTrue(self.cache.exists(), 'warm-up did not save the cache')
        small = self.root / 'dxgi.dll'; small.write_bytes(b'MZ small')
        self.assertEqual(file_stamps.known(small), self.sha(b'MZ small'))
        self.assertIsNone(file_stamps.known(self.root / 'absent.dll'))

    def test_package_drift_reports_known_changes_and_warms_the_rest(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        import package_drift
        target = self.root / 'game'; target.mkdir()
        large = target / 'nvngx_dlssnr.dll'; large.write_bytes(self.data)
        loader = target / 'dxgi.dll'; loader.write_bytes(b'MZ loader')
        (target / 'OptiScaler.ini').write_text('[DLSS]\n')
        hashes = {'nvngx_dlssnr.dll': self.sha(self.data), 'dxgi.dll': self.sha(b'MZ loader'),
                  'OptiScaler.ini': 'settings change in normal use', 'OptiScaler/missing.dll': 'x'}
        engine = mock.Mock(Stop=RuntimeError, load_baseline=lambda *a, **k: {'status': 'active', 'current': {'installed_hashes': hashes}})
        row = {'name': 'Game', 'game': str(target), 'exe': 'game.exe', 'installed': True, 'runtime_provider': 'skynizz'}
        first = package_drift.decorate(engine, [dict(row)])[0]
        # The large file is not read during the scan; it is warmed for the next one.
        self.assertEqual(first['package_drift']['files'], [{'name': 'OptiScaler/missing.dll', 'fix': 'missing'}])
        self.assertNotIn('nvngx_dlssnr.dll', self.reads)
        for thread in [t for t in __import__('threading').enumerate() if t.name == 'file-stamps-warm']:
            thread.join(10)
        large.write_bytes(self.data[:-1] + b'!')
        file_stamps.warm([large]).join(10)
        loader.write_bytes(b'MZ replaced')
        second = package_drift.decorate(engine, [dict(row)])[0]
        self.assertEqual(second['package_drift']['files'], [
            {'name': 'OptiScaler/missing.dll', 'fix': 'missing'}, {'name': 'dxgi.dll', 'fix': 'restore'},
            {'name': 'nvngx_dlssnr.dll', 'fix': 'record'}])
        self.assertIn('3 package files changed', second['package_drift']['summary'])
        # The game's NR model alone: Repair records it, nothing is replaced.
        model_only = {'status': 'active', 'current': {'installed_hashes': {'nvngx_dlssnr.dll': self.sha(self.data)}}}
        engine.load_baseline = lambda *a, **k: model_only
        drift = package_drift.decorate(engine, [dict(row)])[0]['package_drift']
        self.assertEqual(drift['files'], [{'name': 'nvngx_dlssnr.dll', 'fix': 'record'}])
        self.assertIn('Repair records it; nothing is replaced', drift['summary'])
        for other in ({'runtime_provider': 'feeder'}, {'installed': False}, {'blocked': 'Anti-cheat detected'}):
            self.assertNotIn('package_drift', package_drift.decorate(engine, [row | other])[0])

    def test_missing_or_special_paths_are_refused(self):
        with self.assertRaises(OSError):
            file_stamps.digest(self.root / 'absent.dll')
        with self.assertRaises(OSError):
            file_stamps.digest(self.root)


if __name__ == '__main__':
    unittest.main()
