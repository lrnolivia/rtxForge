"""A shared game folder installed on one OS is adapted (adopted) and fully restorable on the other."""
from pathlib import Path
from unittest.mock import patch
import importlib.util, json, os, sys, tempfile, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import engine_bridge, cross_os


def engine(name, state):
    """A real rtxEngine instance with its own state root: one per simulated OS."""
    spec = importlib.util.spec_from_file_location(name, ROOT / 'engine/rtxengine.py')
    e = importlib.util.module_from_spec(spec)
    sys.modules[name] = e
    spec.loader.exec_module(e)
    e.STATE_ROOT = state
    e.Y4MY_PROVIDER = {'id': 'y4my', 'name': 'OptiScaler', 'version': 'test'}
    e._running_processes_under_root = lambda root: []
    if os.name == 'nt':
        # As windows/engine-host does: Windows flushes only through a writable handle.
        def fsync(path):
            try:
                fd = os.open(path, os.O_RDWR | os.O_BINARY)
            except PermissionError:
                return
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        e._fsync_file = fsync
    return e


class CrossOsAdaptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.target = root / 'library' / 'Game'
        self.target.mkdir(parents=True)
        (self.target / 'Game.exe').write_bytes(b'exe')
        (self.target / 'dxgi.dll').write_bytes(b'the game ships its own dxgi')
        self.windows = engine('rtxengine_windows_test', root / 'windows-state')
        self.linux = engine('rtxengine_linux_test', root / 'linux-state')
        self.linux.build_launch_options = lambda proxy, reshade, mfg=None: f'WINEDLLOVERRIDES="{proxy[:-4]}=n,b" %command%'
        self.windows.build_launch_options = lambda proxy, reshade, mfg=None: 'Loads natively on Windows (no launch options)'

    def tearDown(self):
        self.tmp.cleanup()

    def game(self, e):
        return e.Game('', 'Game', self.target, 'Steam', appid='1091500', exe=self.target / 'Game.exe', target_dir=self.target)

    def install_on_windows(self):
        """What install_target leaves behind: originals backed up, managed files written, an active baseline."""
        e, g = self.windows, self.game(self.windows)
        baseline = e.create_baseline(g, {'dxgi.dll', 'OptiScaler.ini'}, 'dxgi.dll', [])
        (self.target / 'dxgi.dll').write_bytes(b'optiscaler proxy')
        (self.target / 'OptiScaler.ini').write_text('[DLSSG]\nOverrideInterpolationCount=auto\n')
        hashes = {rel: e.sha256_file(self.target / rel) for rel in ('dxgi.dll', 'OptiScaler.ini')}
        baseline.update(status='active', managed_paths=sorted(hashes), current={
            'proxy': 'dxgi.dll', 'feature_mode': 'mfg-only', 'provider_id': 'y4my', 'reshade': {'detected': False},
            'launch_options': e.build_launch_options('dxgi.dll', {'detected': False}), 'installed_hashes': hashes})
        e.save_json_atomic(e.baseline_path(self.target), baseline)
        with patch.object(cross_os, 'THIS_OS', 'windows'):
            engine_bridge.share_install(e, g, {'mode': 'mfg-only'})

    def test_paths_round_trip_through_placeholders(self):
        state, target = Path(self.tmp.name) / 's', self.target
        value = {'backup': str(state / 'baseline-backup' / 'files' / 'dxgi.dll'), 'target_dir': str(target), 'name': 'dxgi.dll'}
        shared = cross_os.portable(value, state, target)
        self.assertEqual(shared['backup'], cross_os.STATE_TOKEN + '/baseline-backup/files/dxgi.dll')
        self.assertEqual(shared['target_dir'], cross_os.TARGET_TOKEN)
        self.assertEqual(cross_os.localize(shared, state, target), value)
        with self.assertRaises(ValueError):
            cross_os.localize(cross_os.STATE_TOKEN + '/../escape', state, target)

    def test_install_shares_its_state(self):
        self.install_on_windows()
        record = cross_os.read(self.target)
        self.assertEqual((record['schema'], record['os'], record['shared_state']), (2, 'windows', True))
        shared = json.loads((cross_os.shared_state(self.target) / 'baseline.json').read_text())
        self.assertEqual(shared['cross_os_revision'], record['revision'])
        self.assertEqual(shared['target_dir'], cross_os.TARGET_TOKEN)

    def test_linux_adopts_and_restores_a_windows_install(self):
        self.install_on_windows()
        e, g = self.linux, self.game(self.linux)
        with patch.object(cross_os, 'THIS_OS', 'linux'):
            record = cross_os.adoptable(self.target, 'linux')
            self.assertIsNotNone(record)
            baseline = engine_bridge.adopt(e, g, record)
            self.assertEqual(baseline['current']['launch_options'], 'WINEDLLOVERRIDES="dxgi=n,b" %command%', 'launch options are per OS')
            self.assertEqual(Path(baseline['target_dir']), self.target)
            self.assertIsNone(cross_os.adoptable(self.target, 'linux', baseline['cross_os_revision']), 'adopted once')
            e.restore_target(g)
            engine_bridge.release_install(g, baseline)
        self.assertEqual((self.target / 'dxgi.dll').read_bytes(), b'the game ships its own dxgi', "the game's own file is back")
        self.assertFalse((self.target / 'OptiScaler.ini').exists())
        self.assertFalse((self.target / cross_os.MARKER).exists())
        self.assertFalse((self.target / cross_os.SHARED).exists())
        # Windows sees its install restored elsewhere and clears its own state on its next change.
        windows = self.windows.load_baseline(self.target)
        with patch.object(cross_os, 'THIS_OS', 'windows'):
            self.assertTrue(engine_bridge.restored_elsewhere(self.windows, self.game(self.windows), windows))

    def test_adapted_install_is_shared_back(self):
        self.install_on_windows()
        first = cross_os.read(self.target)['revision']
        e, g = self.linux, self.game(self.linux)
        with patch.object(cross_os, 'THIS_OS', 'linux'):
            engine_bridge.adopt(e, g, cross_os.adoptable(self.target, 'linux'))
            engine_bridge.share_install(e, g, {'mode': 'mfg-only'})
        record = cross_os.read(self.target)
        self.assertEqual(record['os'], 'linux')
        self.assertNotEqual(record['revision'], first)
        # Windows adapts it back, keeping its own launch setting and dropping Linux's.
        with patch.object(cross_os, 'THIS_OS', 'windows'):
            local = self.windows.load_baseline(self.target)
            again = cross_os.adoptable(self.target, 'windows', local['cross_os_revision'])
            self.assertIsNotNone(again)
            baseline = engine_bridge.adopt(self.windows, self.game(self.windows), again)
        self.assertEqual(baseline['current']['launch_options'], 'Loads natively on Windows (no launch options)')
        retired = list((self.windows.STATE_ROOT / 'cross-os-retired').iterdir())
        self.assertEqual(len(retired), 1, 'the older Windows state is kept aside, not deleted')

    def test_tampered_files_are_not_adopted(self):
        self.install_on_windows()
        (self.target / 'dxgi.dll').write_bytes(b'changed by hand')
        self.assertIsNone(cross_os.adoptable(self.target, 'linux'))


if __name__ == '__main__':
    unittest.main()
