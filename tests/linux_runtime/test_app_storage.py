"""Linux App Storage: two-root inventory and exact-token cleanup of unused downloads only."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_fixture  # noqa: F401
import linux_runtime as runtime


class AppStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.app, self.engine = root / 'rtxforge', root / 'rtxforge-dlss-unlocked'
        self.used = 'a' * 64
        self.write(self.app / 'packages' / self.used / 'used.zip', b'used' * 100)
        self.write(self.app / 'packages' / ('b' * 64) / 'unused.zip', b'unused' * 100)
        self.write(self.app / 'runtime-cache' / ('c' * 64) / 'nvngx_dlss.dll', b'dlss' * 50)
        self.write(self.app / 'runtime-cache' / 'local' / 'model.dll', b'model' * 10)
        self.write(self.app / 'settings.json', json.dumps({'nr_runtime': str(self.app / 'runtime-cache' / 'local' / 'model.dll')}).encode())
        # The only reference to the used package lives in the engine root's baseline.
        self.write(self.engine / 'targets' / 'game' / 'baseline.json', json.dumps({'archive': {'sha256': self.used}}).encode())
        self.write(self.engine / 'feeder-cache' / ('d' * 64), b'original game file')
        self.write(self.engine / 'desktop-operations' / 'op' / 'copy.bin', b'operation copy')
        self.write(self.app / 'transactions' / 'tx' / 'original.dll', b'original')

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def snapshot(self):
        return {p: p.read_bytes() for root in (self.app, self.engine) for p in root.rglob('*') if p.is_file()}

    def test_inventory_counts_both_roots_by_category_without_reading(self):
        report = runtime.storage_inventory(self.app, self.engine)
        by_key = {c['key']: c for c in report['categories']}
        self.assertEqual(by_key['package-downloads']['files'], 2)
        self.assertEqual(by_key['dlss-downloads']['files'], 2)
        self.assertEqual(by_key['game-backups']['files'], 1)
        self.assertEqual(by_key['feeder-restore']['files'], 1)
        self.assertEqual(by_key['operation-backups']['files'], 2)
        self.assertIsNone(report['warning'])
        self.assertEqual(report['bytes'], sum(len(v) for v in self.snapshot().values()))

    def test_only_unreferenced_downloads_are_selected_and_removed(self):
        before = self.snapshot()
        plan = runtime.storage_review(self.app, self.engine)
        self.assertEqual(self.snapshot(), before, 'review never writes')
        self.assertEqual(sorted('/'.join(p) for p in plan['files']),
                         ['app/packages/' + 'b' * 64 + '/unused.zip', 'app/runtime-cache/' + 'c' * 64 + '/nvngx_dlss.dll'])
        result = runtime.storage_cleanup(self.app, self.engine, plan)
        self.assertEqual(result['files'], 2)
        after = self.snapshot()
        removed = set(before) - set(after)
        self.assertEqual({p.name for p in removed}, {'unused.zip', 'nvngx_dlss.dll'})
        for path, data in after.items():
            self.assertEqual(before[path], data)

    def test_any_change_since_review_removes_nothing(self):
        plan = runtime.storage_review(self.app, self.engine)
        self.write(self.engine / 'targets' / 'other' / 'baseline.json', json.dumps({'sha256': 'b' * 64}).encode())
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'changed since review'):
            runtime.storage_cleanup(self.app, self.engine, plan)
        self.assertEqual(self.snapshot(), before)
        with self.assertRaisesRegex(ValueError, 'does not belong'):
            runtime.storage_cleanup(self.engine, self.app, runtime.storage_review(self.app, self.engine))

    def test_links_unfinished_downloads_and_overlapping_roots_refuse(self):
        link = self.app / 'packages' / 'link.zip'
        os.symlink(self.engine / 'feeder-cache' / ('d' * 64), link)
        with self.assertRaisesRegex(ValueError, 'linked'):
            runtime.storage_review(self.app, self.engine)
        link.unlink()
        self.write(self.app / 'packages' / ('e' * 64) / 'next.zip.part', b'partial')
        with self.assertRaisesRegex(ValueError, 'unfinished'):
            runtime.storage_review(self.app, self.engine)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            runtime.storage_review(self.app, self.app / 'nested')

    def test_hardlinked_downloads_are_kept(self):
        os.link(self.app / 'packages' / ('b' * 64) / 'unused.zip', self.app / 'packages' / ('b' * 64) / 'twin.zip')
        plan = runtime.storage_review(self.app, self.engine)
        self.assertNotIn('unused.zip', {p[-1] for p in plan['files']})


if __name__ == '__main__':
    unittest.main()
