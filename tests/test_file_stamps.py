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

    def test_missing_or_special_paths_are_refused(self):
        with self.assertRaises(OSError):
            file_stamps.digest(self.root / 'absent.dll')
        with self.assertRaises(OSError):
            file_stamps.digest(self.root)


if __name__ == '__main__':
    unittest.main()
