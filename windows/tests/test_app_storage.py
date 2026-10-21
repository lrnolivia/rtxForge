"""Cleanup tests use disposable roots only; never the real user's app data."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'windows/engine-host'))
import app_storage as storage


class AppStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'rtxForge'
        self.root.mkdir()

    def put(self, name, data=b'original'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def record(self, name, value):
        return self.put(name, json.dumps(value).encode())

    def test_protected_namespaces_and_accounting(self):
        protected = [self.put(p) for p in ('state/runtime-transactions/one/backups/nvngx.dll',
            'engine-state/targets/one/original.dll', 'engine-state/feeder-cache/hash',
            'engine-state/desktop-operations/one/copies/file', 'recovery/build/app.exe',
            'state/runtimes/a.dll')]
        self.record('settings.json', {'theme': 'light'})
        a = self.put('state/packages/hash/archive.zip', b'123')
        b = self.put('state/runtime-cache/hash/nvngx.dll', b'12345')
        before = storage.inventory(self.root)
        plan = storage.prepare(self.root)
        self.assertEqual(len(plan.files), 2)
        result = storage.execute(self.root, plan)
        self.assertEqual((result['bytes'], result['files']), (8, 2))
        self.assertFalse(a.exists() or b.exists())
        self.assertTrue(all(p.read_bytes() == b'original' for p in protected))
        self.assertEqual(before['bytes'] - storage.inventory(self.root)['bytes'], 8)
        self.assertEqual(json.loads((self.root / 'settings.json').read_text()), {'theme': 'light'})

    def test_saved_local_paths_and_hashes_are_retained(self):
        direct = self.put('state/packages/direct/import.zip')
        digest = 'a' * 64
        hashed = self.put('state/packages/' + digest + '/archive.zip')
        model = self.put('state/runtime-cache/local/model.dll')
        unused = self.put('state/packages/unused/archive.zip')
        self.record('settings.json', {'custom': {'path': str(direct)}, 'nr_runtime': str(model.parent)})
        self.record('engine-state/targets/a/baseline.json', {'sha256': digest})
        result = storage.execute(self.root, storage.prepare(self.root))
        self.assertEqual(result['files'], 1)
        self.assertFalse(unused.exists())
        self.assertTrue(all(p.exists() for p in (direct, hashed, model)))

    def test_one_time_review_cannot_be_replayed(self):
        self.put('state/packages/hash/archive.zip')
        plan = storage.prepare(self.root)
        storage.execute(self.root, plan)
        with self.assertRaises(storage.StorageError):
            storage.execute(self.root, plan)

    def test_all_cache_trees_checked_before_any_deletion(self):
        a = self.put('state/packages/hash/archive.zip')
        b = self.put('state/runtime-cache/hash/nvngx.dll')
        plan = storage.prepare(self.root)
        b.write_bytes(b'changed')
        with self.assertRaises(storage.StorageError):
            storage.execute(self.root, plan)
        self.assertTrue(a.exists() and b.exists())

    def test_new_download_after_review_refuses_before_deletion(self):
        a = self.put('state/packages/hash/archive.zip')
        plan = storage.prepare(self.root)
        self.put('state/runtime-cache/new/nvngx.dll')
        with self.assertRaises(storage.StorageError):
            storage.execute(self.root, plan)
        self.assertTrue(a.exists())

    def test_new_reference_after_review_refuses_before_deletion(self):
        a = self.put('state/packages/hash/archive.zip')
        plan = storage.prepare(self.root)
        self.record('engine-state/targets/new/baseline.json', {'path': str(a)})
        with self.assertRaises(storage.StorageError):
            storage.execute(self.root, plan)
        self.assertTrue(a.exists())

    def test_changed_record_and_invalid_record_refused(self):
        a = self.put('state/packages/hash/archive.zip')
        record = self.record('settings.json', {'theme': 'light'})
        plan = storage.prepare(self.root)
        record.write_text('{"theme":"dark"}')
        with self.assertRaises(storage.StorageError):
            storage.execute(self.root, plan)
        record.write_text('invalid')
        with self.assertRaises(storage.StorageError):
            storage.prepare(self.root)
        self.assertTrue(a.exists())

    def test_pending_download_refused(self):
        self.put('state/packages/hash/.archive.part')
        with self.assertRaisesRegex(storage.StorageError, 'unfinished'):
            storage.prepare(self.root)

    def test_hardlinked_files_kept_and_not_counted_as_freed(self):
        original = self.put('engine-state/targets/game/original.dll')
        duplicate = self.root / 'state/runtime-cache/hash/nvngx.dll'
        duplicate.parent.mkdir(parents=True)
        os.link(original, duplicate)
        result = storage.execute(self.root, storage.prepare(self.root))
        self.assertEqual(result['bytes'], 0)
        self.assertTrue(original.exists() and duplicate.exists())

    def test_forged_root_or_target_refused(self):
        original = self.put('state/runtime-transactions/one/backups/nvngx.dll')
        self.put('state/packages/hash/archive.zip')
        plan = storage.prepare(self.root)
        for forged in (replace(plan, root=str(self.root.parent)),
                       replace(plan, files=(('state', 'runtime-transactions', 'one', 'backups', 'nvngx.dll'),)),
                       replace(plan, files=(('state', 'packages', '..', 'settings.json'),))):
            with self.assertRaises(storage.StorageError):
                storage.execute(self.root, forged)
        self.assertTrue(original.exists())

    def test_symlink_and_directory_swap_refused(self):
        a = self.put('state/packages/hash/archive.zip')
        plan = storage.prepare(self.root)
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        cache = self.root / 'state/packages'
        cache.rename(self.root / 'state/packages-original')
        try:
            cache.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Creating symlinks needs Windows Developer Mode or administrator rights')
        self.addCleanup(cache.unlink)
        with self.assertRaises(storage.StorageError):
            storage.execute(self.root, plan)
        self.assertTrue((self.root / 'state/packages-original/hash/archive.zip').exists())

    def test_empty_and_missing_storage(self):
        self.assertEqual(storage.execute(self.root, storage.prepare(self.root))['bytes'], 0)
        self.assertEqual(storage.inventory(self.root / 'missing')['bytes'], 0)

    def test_root_mentioned_by_diagnostics_does_not_pin_every_download(self):
        self.put('state/packages/hash/archive.zip')
        self.record('recovery/receipt.json', {'root': str(self.root)})
        self.assertEqual(len(storage.prepare(self.root).files), 1)


HOST_TEST = r'''
import json,sys
from pathlib import Path
repo=Path(sys.argv[1]); local=Path(sys.argv[2])/'rtxForge'
sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
saved=sys.stdout
import rtxforge_win_host as host
sys.stdout=saved
import win_features
local.mkdir(parents=True,exist_ok=True)
cache=local/'state/packages/hash/archive.zip'; cache.parent.mkdir(parents=True,exist_ok=True);cache.write_bytes(b'cached')
original=local/'state/runtime-transactions/old/backups/a.dll';original.parent.mkdir(parents=True);original.write_bytes(b'original')
review=host.METHODS['storage_review']({})
assert cache.exists() and original.exists(), 'review mutated files'
assert review['items'] and review['kind']=='storage-cleanup'
host.reviews['pending']={}
try:host.METHODS['run']({'token':review['token']})
except Exception as error:assert 'other file review' in str(error),error
else:raise AssertionError('cleanup ignored pending install')
assert cache.exists()
host.reviews.clear()
review=host.METHODS['storage_review']({})
result=host.METHODS['run']({'token':review['token']})
assert result['bytes']==6 and not cache.exists() and original.read_bytes()==b'original',result
try:host.METHODS['run']({'token':review['token']})
except Exception as error:assert 'expired' in str(error),error
else:raise AssertionError('token replayed')
assert not (local/'state/runtime-transactions/.optiscaler-operation.lock').exists()
print('host storage review, pending-install refusal, exact token cleanup, replay refusal and original preservation passed')
'''


@unittest.skipUnless(os.name == 'nt', 'Windows host adapters')
class WindowsHostStorageTest(unittest.TestCase):
    def test_real_host_dispatch_and_locks(self):
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder) / 'local'
            env = dict(os.environ, LOCALAPPDATA=str(local), RTXFORGE_ROOT=str(ROOT),
                       RTXFORGE_STATE_ROOT=str(local/'rtxForge/state'),
                       RTXFORGE_DLSS_UNLOCKED_STATE=str(local/'rtxForge/engine-state'), PYTHONUTF8='1')
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', HOST_TEST, str(ROOT), str(local)],
                                    env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr[-6000:] + result.stdout[-2000:])
            print(result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
