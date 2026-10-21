"""Linux adopts a Windows Skynizz install under Proton only with the experimental opt-in."""
from pathlib import Path
from unittest.mock import patch
import sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import engine_bridge, cross_os, skynizz_provider
import transactions as t
from test_cross_os_adapt import CrossOsAdaptTest


class LinuxSkynizzAdoptionTest(unittest.TestCase):
    # The cross-OS suite's real two-engine fixture, without re-running its tests.
    setUp, tearDown = CrossOsAdaptTest.setUp, CrossOsAdaptTest.tearDown
    game, install_on_windows = CrossOsAdaptTest.game, CrossOsAdaptTest.install_on_windows

    def install_skynizz_on_windows(self):
        self.install_on_windows()
        # The same shared install, recorded as Skynizz + Universal MFG.
        e = self.windows
        baseline = e.load_baseline(self.target)
        baseline['current']['provider_id'] = 'skynizz'
        e.save_json_atomic(e.baseline_path(self.target), baseline)
        with patch.object(cross_os, 'THIS_OS', 'windows'):
            engine_bridge.share_install(e, self.game(e), {'mode': 'nr-mfg'})

    def plan(self, opted_in, operation='reset', mode='nr-mfg'):
        e, g = self.linux, self.game(self.linux)
        e.SKYNIZZ_PROTON = opted_in
        # Linux selects no Skynizz package of its own.
        e.Y4MY_PROVIDER = {'id': 'y4my', 'name': 'OptiScaler', 'version': 'test'}
        with patch.object(cross_os, 'THIS_OS', 'linux'), \
             patch.object(engine_bridge, 'steam_open_route', return_value=Path(self.tmp.name) / 'pfx'):
            record = cross_os.adoptable(self.target, 'linux')
            self.assertIsNotNone(record)
            return engine_bridge.adopt_plan(e, g, {'name': 'Game'}, record, operation, mode)

    def test_adopting_is_not_a_provider_switch_but_the_profile_must_match(self):
        self.install_skynizz_on_windows()
        plan = self.plan(True, 'install', 'mfg-only')
        self.assertIn('adds the Proton setting', plan['preview']['launch_options'])
        with self.assertRaisesRegex(t.Refusal, 'changing feature profiles'):
            self.plan(True, 'install', 'nr-mfg')

    def test_refused_by_default_and_allowed_with_the_opt_in(self):
        self.install_skynizz_on_windows()
        with self.assertRaisesRegex(t.Refusal, 'Skynizz on Proton'):
            self.plan(False)
        plan = self.plan(True)
        self.assertEqual(plan['preview']['files'], [], 'adoption changes no game files')
        self.assertIn('adapts it for Linux', plan['preview']['launch_options'])

    def test_opt_in_is_linux_only_and_strictly_boolean(self):
        with patch.object(cross_os, 'THIS_OS', 'linux'):
            self.assertTrue(engine_bridge.skynizz_proton({'skynizz_proton': True}))
            for value in (False, 'true', 1, None):
                self.assertFalse(engine_bridge.skynizz_proton({'skynizz_proton': value}))
        with patch.object(cross_os, 'THIS_OS', 'windows'):
            self.assertFalse(engine_bridge.skynizz_proton({'skynizz_proton': True}))

    def test_fresh_linux_installs_stay_windows_only(self):
        with self.assertRaisesRegex(t.Refusal, 'Windows-only'):
            skynizz_provider.require_mode('linux', 'nr-mfg', bridge=True)


del CrossOsAdaptTest  # imported for its fixture only

if __name__ == '__main__':
    unittest.main()
