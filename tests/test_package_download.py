import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import packages
import transactions as t


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'archive.zip'
        self.data = b'verified fixture'
        self.digest = hashlib.sha256(self.data).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def download(self, data=None, **kwargs):
        with patch.object(packages.urllib.request, 'urlopen', return_value=io.BytesIO(self.data if data is None else data)):
            return packages.download('https://example.invalid/archive.zip', self.path, expected=self.digest, **kwargs)

    def test_stale_partial_does_not_prevent_verified_download(self):
        stale = self.path.with_suffix('.zip.part')
        stale.write_bytes(b'interrupted old attempt')
        self.download(size=len(self.data))
        self.assertEqual(self.path.read_bytes(), self.data)
        self.assertEqual(stale.read_bytes(), b'interrupted old attempt')
        self.assertFalse(list(self.root.glob('.archive*')))

    def test_failed_hash_leaves_no_published_or_temporary_archive(self):
        with self.assertRaises(t.Refusal):
            self.download(b'wrong')
        self.assertFalse(self.path.exists())
        self.assertFalse(list(self.root.iterdir()))
        self.download()
        self.assertEqual(self.path.read_bytes(), self.data)

    def test_cached_size_is_checked(self):
        self.path.write_bytes(self.data)
        with self.assertRaises(t.Refusal):
            self.download(size=1)
        self.assertEqual(self.path.read_bytes(), self.data)

    def test_network_failure_cleans_its_temporary_file(self):
        with patch.object(packages.urllib.request, 'urlopen', side_effect=OSError('disconnected')):
            with self.assertRaises(OSError):
                packages.download('https://example.invalid', self.path, expected=self.digest)
        self.assertFalse(list(self.root.iterdir()))

    def test_symlink_destination_is_refused(self):
        other = self.root / 'other'
        other.write_bytes(self.data)
        self.path.symlink_to(other)
        with self.assertRaises(t.Refusal):
            self.download()
        self.assertEqual(other.read_bytes(), self.data)


if __name__ == '__main__':
    unittest.main()
