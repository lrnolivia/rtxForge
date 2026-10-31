"""Automatic provider inputs validate both archive identity and exact members."""
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import package_downloads as downloads
import transactions as t


class ProviderDownloadTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve(); self.e = SimpleNamespace(STATE_ROOT=self.root/'state')
        self.archive = self.root/'input.zip'
        with zipfile.ZipFile(self.archive, 'w') as zipped: zipped.writestr('runtime.dll', b'pinned DLL')
        self.source = dict(name='Test provider', archive='input.zip', url=self.archive.as_uri(),
                           size=self.archive.stat().st_size, sha256=t.digest(self.archive), members={'runtime.dll':'dxgi.dll'})
        self.expected = {'dxgi.dll': {'sha256':t.sha(b'pinned DLL'), 'size':10}}

    def test_empty_cache_downloads_verifies_and_reuses(self):
        first = downloads.inputs(self.e, [self.source], self.expected)
        self.assertEqual(Path(first['dxgi.dll']['path']).read_bytes(), b'pinned DLL')
        self.archive.unlink()
        self.assertEqual(downloads.inputs(self.e, [self.source], self.expected), first)

    def test_archive_integrity_failure_never_publishes_input(self):
        self.archive.write_bytes(b'changed')
        with self.assertRaises(t.Refusal): downloads.inputs(self.e, [self.source], self.expected)
        self.assertFalse((self.e.STATE_ROOT/'feeder-cache').exists())

    def test_member_hash_failure_never_publishes_input(self):
        self.expected['dxgi.dll']['sha256'] = 'f'*64
        with self.assertRaises(t.Refusal): downloads.inputs(self.e, [self.source], self.expected)
        self.assertFalse((self.e.STATE_ROOT/'feeder-cache').exists())

    def test_offline_failure_is_retryable_without_import_instructions(self):
        with patch.object(downloads.packages, 'download', side_effect=urllib.error.URLError('offline')):
            with self.assertRaisesRegex(t.Refusal, 'Check your connection and retry'):
                downloads.inputs(self.e, [self.source], self.expected)


if __name__ == '__main__': unittest.main()
