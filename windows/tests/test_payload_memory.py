"""Large payload files stay on disk, and a review reads each game file once."""
import gc
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.modules.setdefault('fcntl', types.SimpleNamespace())
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'scripts'), str(ROOT / 'windows' / 'engine-host')]
import rtxengine
import sl_override
import transactions


def _blob(folder: Path, name: str, data: bytes) -> 'rtxengine.FileBlob':
    path = folder / name
    path.write_bytes(data)
    return rtxengine.FileBlob.capture(path)


class FileBlobTest(unittest.TestCase):
    def test_behaves_like_the_bytes_it_holds(self):
        with tempfile.TemporaryDirectory() as directory:
            data = b'MZ' + bytes(range(256)) * 64
            blob = _blob(Path(directory), 'loader.dll', data)
            self.assertEqual(len(blob), len(data))
            self.assertEqual(blob[:2], b'MZ')
            self.assertEqual(blob[10:20], data[10:20])
            self.assertEqual(blob, data)
            self.assertEqual(data, blob)
            self.assertNotEqual(blob, data + b'!')
            self.assertEqual(rtxengine.sha256_bytes(blob), hashlib.sha256(data).hexdigest())
            self.assertEqual(transactions.sha(blob), hashlib.sha256(data).hexdigest())
            self.assertEqual(bytes(blob), data)

    def test_writes_stream_and_refuse_a_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            blob = _blob(folder, 'source.dll', b'MZ verified bytes')
            target = folder / 'game' / 'dxgi.dll'
            rtxengine.atomic_write(target, blob)
            self.assertEqual(target.read_bytes(), b'MZ verified bytes')

            (folder / 'source.dll').write_bytes(b'MZ swapped bytes!')
            target.write_bytes(b'original')
            with self.assertRaises(rtxengine.Stop):
                rtxengine.atomic_write(target, blob)
            # The refused bytes never replace the file, and no temporary copy is left.
            self.assertEqual(target.read_bytes(), b'original')
            self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ['dxgi.dll'])
            with self.assertRaises(rtxengine.Stop):
                transactions.atomic_file(folder / 'other.dll', blob, 0o644)


class ExtractedPayloadTest(unittest.TestCase):
    def test_large_files_stay_on_disk_until_the_payload_is_gone(self):
        workdir = rtxengine._payload_workdir()
        root = workdir.root
        (root / 'OptiScaler' / 'streamline').mkdir(parents=True)
        (root / 'OptiScaler.ini').write_bytes(b'[DlssNr]\n')
        big = b'MZ' + os.urandom(rtxengine.BLOB_MIN_BYTES)
        (root / 'OptiScaler' / 'streamline' / 'sl.interposer.dll').write_bytes(big)
        payload = rtxengine._collect_extracted_tree(workdir)
        del workdir

        self.assertIsInstance(payload['OptiScaler.ini'], bytes)
        large = payload['OptiScaler/streamline/sl.interposer.dll']
        self.assertIsInstance(large, rtxengine.FileBlob)
        self.assertEqual(large, big)
        # Reviews copy the map; the folder lives as long as any copy does.
        copied = dict(payload)
        del payload, large
        gc.collect()
        self.assertTrue(root.is_dir())
        del copied
        gc.collect()
        self.assertFalse(root.exists())


class ReviewHashCacheTest(unittest.TestCase):
    def test_unchanged_files_are_hashed_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'game.exe'
            path.write_bytes(b'first')
            reads = []
            original = rtxengine.sha256_file
            rtxengine.sha256_file = lambda p: reads.append(p) or original(p)
            try:
                first = rtxengine.sha256_file_cached(path)
                self.assertEqual(rtxengine.sha256_file_cached(path), first)
                self.assertEqual(len(reads), 1)
                path.write_bytes(b'second, longer')
                self.assertEqual(rtxengine.sha256_file_cached(path), hashlib.sha256(b'second, longer').hexdigest())
                self.assertEqual(len(reads), 2)
            finally:
                rtxengine.sha256_file = original

    def test_import_table_is_read_from_a_mapped_exe(self):
        imports = rtxengine.pe_imported_dlls(Path(sys.executable))
        self.assertIn('kernel32.dll', imports) if os.name == 'nt' else None
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / 'empty.exe'
            empty.write_bytes(b'')
            self.assertEqual(rtxengine.pe_imported_dlls(empty), set())
            self.assertEqual(rtxengine.pe_imported_dlls(Path(directory) / 'missing.exe'), set())


class NrRuntimeTest(unittest.TestCase):
    def test_each_game_model_is_a_file_reference_not_a_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / rtxengine.NR_RUNTIME_NAME
            with model.open('wb') as f:
                f.write(b'MZ')
                f.truncate(rtxengine.NR_RUNTIME_MIN_BYTES + 1)
            data, meta = rtxengine.load_user_nr_runtime(str(model))
            self.assertIsInstance(data, rtxengine.FileBlob)
            self.assertEqual(meta['sha256'], rtxengine.sha256_file(model))
            self.assertEqual(len(data), rtxengine.NR_RUNTIME_MIN_BYTES + 1)


class StreamlineVersionTest(unittest.TestCase):
    def test_reads_the_version_of_a_file_kept_on_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            # Signature, structure version, then FileVersionMS/LS.
            fixed = (sl_override._FIXED_INFO + (1 << 16).to_bytes(4, 'little')
                     + (2 << 16 | 9).to_bytes(4, 'little') + (1 << 16).to_bytes(4, 'little'))
            blob = _blob(Path(directory), 'sl.interposer.dll', b'MZ' + b'\0' * 64 + fixed + b'\0' * 32)
            payload = {'OptiScaler/streamline/' + name: blob for name in sl_override._PLUGINS}
            self.assertEqual(sl_override.provider_streamline(Path(directory), payload),
                             sl_override.short('2.9.1.0'))


if __name__ == '__main__':
    unittest.main()
