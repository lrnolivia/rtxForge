"""Dual-boot installs made by rtxForge on Windows are Set Up on Linux, never adopted."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import os, sys, tempfile, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cross_os, engine_bridge, package_adoption, feeder_provider
import transactions as t


class FakeEngine:
    """Just enough engine for detection: no local baseline, no running game."""
    def load_baseline(self, target, readonly=False):
        return None

    def _running_processes_under_root(self, root):
        return []


def windows_install(target, shared=True):
    (target / 'dxgi.dll').write_bytes(b'OptiScaler loader')
    (target / 'OptiScaler.ini').write_text('[DLSSG]\n')
    record = cross_os.write(target, 'windows', ['dxgi.dll', 'OptiScaler.ini'], {'id': 'skynizz', 'name': 'Skynizz', 'version': '1'},
                            'mfg-only', 'dxgi.dll', revision='r1', shared_state=shared)
    if shared:
        state = cross_os.shared_state(target)
        state.mkdir(parents=True)
        (state / 'baseline.json').write_text('{"cross_os_revision": "r1"}')
    return record


class DualBootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name) / 'Game'
        self.target.mkdir()
        self.game = SimpleNamespace(target_dir=self.target)

    def tearDown(self):
        for path in self.target.rglob('*'):
            path.chmod(0o700 if path.is_dir() else 0o600)
        self.tmp.cleanup()

    def row(self, **extra):
        return {'name': 'Game', 'game': str(self.target), 'exe': 'Game.exe', **extra}

    @unittest.skipIf(os.name == 'nt' or os.geteuid() == 0, 'needs POSIX permissions and a non-root user')
    def test_unreadable_record_is_detected(self):
        windows_install(self.target)
        self.assertFalse(cross_os.unreadable(self.target))
        (self.target / cross_os.MARKER).chmod(0)
        self.assertIsNone(cross_os.read(self.target))
        self.assertTrue(cross_os.unreadable(self.target))

    def test_intact_shared_install_is_taken_over_not_set_up(self):
        windows_install(self.target)
        with patch.object(cross_os, 'THIS_OS', 'linux'):
            self.assertIsNone(engine_bridge.windows_install(None, self.game, None))

    def test_changed_windows_install_gets_the_proton_setting_on_linux(self):
        # Windows' Update DLSS swaps a runtime without rewriting the record.
        windows_install(self.target)
        (self.target / 'dxgi.dll').write_bytes(b'updated runtime')
        with patch.object(cross_os, 'THIS_OS', 'linux'):
            record = engine_bridge.windows_install(None, self.game, None)
        self.assertEqual(record['os'], 'windows')
        self.assertEqual(record['proxy'], 'dxgi.dll')

    def test_windows_keeps_refusing_changed_linux_installs(self):
        (self.target / 'dxgi.dll').write_bytes(b'loader')
        cross_os.write(self.target, 'linux', ['dxgi.dll'], {'id': 'y4my'}, 'mfg-only', 'dxgi.dll')
        (self.target / 'dxgi.dll').write_bytes(b'changed')
        with patch.object(cross_os, 'THIS_OS', 'windows'):
            self.assertIsNone(engine_bridge.windows_install(None, self.game, None))

    def test_windows_install_is_never_offered_adoption(self):
        windows_install(self.target)
        (self.target / 'Game.exe').write_bytes(b'')
        rows = [self.row(installed_on='windows', adaptable=False)]
        with patch.object(cross_os, 'OTHER_OS', 'windows'):
            package_adoption.decorate(FakeEngine(), rows)
        self.assertFalse(rows[0]['adoption_available'])
        self.assertEqual(rows[0]['installed_on'], 'windows')

    def test_unreadable_install_is_never_offered_adoption(self):
        (self.target / 'OptiScaler.ini').write_text('')
        (self.target / 'Game.exe').write_bytes(b'')
        rows = [self.row(installed_on=None, record_unreadable=True, blocked='not readable')]
        package_adoption.decorate(FakeEngine(), rows)
        self.assertFalse(rows[0]['adoption_available'])

    def test_unrecorded_external_setup_is_still_offered_adoption(self):
        (self.target / 'OptiScaler.ini').write_text('')
        (self.target / 'Game.exe').write_bytes(b'')
        rows = [self.row(installed_on=None)]
        package_adoption.decorate(FakeEngine(), rows)
        self.assertTrue(rows[0]['adoption_available'])

    def test_adoption_review_refuses_other_os_installs(self):
        with patch.object(cross_os, 'OTHER_OS', 'windows'):
            review = package_adoption.prepare(None, [self.row(installed_on='windows')], 'adopt', {})
        self.assertFalse(review.get('plans'))
        self.assertIn('Set Up', str(review))

    def test_feeder_set_up_on_linux_explains_instead_of_installing(self):
        e = SimpleNamespace(DESKTOP_PLATFORM='linux')
        with patch.object(feeder_provider, 'target', lambda row: (self.target, self.target / 'Game.exe', self.target)), \
                self.assertRaises(t.Refusal) as caught:
            feeder_provider.eligible(e, self.row(installed_on='windows'), existing=True, check_running=False)
        self.assertIn('Set Up for Linux is not available for Feeder NR yet', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
