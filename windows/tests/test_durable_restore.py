"""Restore state may only record what NTFS has committed (a crash once undid deletions)."""
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.modules.setdefault('fcntl', types.SimpleNamespace())
sys.path[:0] = [str(ROOT / 'engine')]
import rtxengine


@unittest.skipUnless(os.name == 'nt', 'NTFS directory flush')
class DurableRestoreTest(unittest.TestCase):
    def test_directory_barriers_flush_on_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'managed.dll').write_bytes(b'installed')
            self.assertTrue(rtxengine._flush_windows_dir(folder))
            self.assertFalse(rtxengine._flush_windows_dir(folder / 'missing'))
            flushed = []
            with patch.object(rtxengine, '_flush_windows_dir', side_effect=lambda path: flushed.append(path) or True):
                rtxengine.durable_unlink(folder / 'managed.dll')
                rtxengine._sync_filesystem(folder)
            # The unlink and the tree removal both commit the game folder's entries.
            self.assertEqual(flushed, [folder, folder])
            self.assertFalse((folder / 'managed.dll').exists())


if __name__ == '__main__':
    unittest.main()
