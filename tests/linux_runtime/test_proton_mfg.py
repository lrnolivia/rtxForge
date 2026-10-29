"""Universal MFG Unlocker under Proton: gate, single ownership and post-install checks (fixture-only)."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_fixture as fx
import proton_mfg
import proton_stack
import universal_mfg_provider as universal
import skynizz_provider
import transactions as t


class ProtonMfgTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proc, self.wine = fx.driver(self.root)
        self.lib = fx.proton(self.root)
        self.prefix = fx.prefix(self.root / 'library', 870780, self.lib)
        self.target = self.root / 'library' / 'steamapps' / 'common' / 'Control'
        self.target.mkdir(parents=True)
        self.driver = patch.multiple(proton_stack, DRIVER_ROOT=self.proc, DRIVER_WINE_DIRS=(str(self.wine),))
        self.driver.start()

    def tearDown(self):
        self.driver.stop()
        self.tmp.cleanup()

    def test_gate_needs_opt_in_universal_and_every_prerequisite(self):
        with self.assertRaisesRegex(t.Refusal, 'Skynizz on Proton'):
            proton_mfg.gate({}, 'nr-mfg', 'universal', self.prefix, True)
        with self.assertRaisesRegex(t.Refusal, 'Only the Universal MFG Unlocker'):
            proton_mfg.gate({'skynizz_proton': True}, 'nr-mfg', 'mfg-unlock', self.prefix, True)
        with self.assertRaisesRegex(t.Refusal, 'Only the Universal MFG Unlocker'):
            proton_mfg.gate({'skynizz_proton': True}, 'mfg-only', 'integrated', self.prefix, True)
        with self.assertRaisesRegex(t.Refusal, 'not been started with Proton'):
            proton_mfg.gate({'skynizz_proton': True}, 'nr-mfg', 'universal', None, True)
        report = proton_mfg.gate({'skynizz_proton': True}, 'nr-mfg', 'universal', self.prefix, True)
        self.assertTrue(report['opt_in'] and report['prerequisites_met'])
        self.assertFalse(report['runtime_verified'])
        self.assertEqual(report['component'], universal.pinned())
        self.assertEqual(report['label'], proton_mfg.LABEL)
        # NR Only needs no MFG component and accepts any component setting.
        self.assertIsNone(proton_mfg.gate({'skynizz_proton': True}, 'nr-only', 'mfg-unlock', self.prefix)['component'])

    def test_require_mode_accepts_linux_only_with_a_passing_gate(self):
        with self.assertRaisesRegex(t.Refusal, 'Windows-only'):
            skynizz_provider.require_mode('linux', 'nr-mfg', bridge=True)
        for fake in ({'prerequisites_met': True}, {'opt_in': True, 'prerequisites_met': False}, 'yes'):
            with self.assertRaisesRegex(t.Refusal, 'Windows-only'):
                skynizz_provider.require_mode('linux', 'nr-mfg', bridge=True, proton=fake)
        report = proton_mfg.gate({'skynizz_proton': True}, 'nr-mfg', 'universal', self.prefix, True)
        skynizz_provider.require_mode('linux', 'nr-mfg', bridge=True, proton=report)
        # Mode rules still apply on Linux: stock Skynizz cannot provide MFG.
        with self.assertRaisesRegex(t.Refusal, 'combined Skynizz/Ada bridge'):
            skynizz_provider.require_mode('linux', 'nr-mfg', bridge=False, proton=report)
        with self.assertRaisesRegex(t.Refusal, 'Windows-only'):
            skynizz_provider.require_mode('macos', 'nr-only', proton=report)

    def test_competing_unlocks_are_named_and_refused(self):
        self.assertEqual(proton_mfg.competing(self.target), [])
        (self.target / 'RTXMFG-control-1.log').write_text('plugin run report')
        (self.target / universal.STATUS).write_text('{}')
        self.assertEqual(proton_mfg.competing(self.target), [])
        for name in ('renodx-mfgunlock.addon64', 'dlss-enabler.dll', 'RTX40MFGCore.dll', 'MFGUnlocker.dll'):
            (self.target / name).write_bytes(b'x')
            with self.subTest(name=name):
                self.assertEqual(proton_mfg.competing(self.target), [name])
                report = proton_mfg.gate({'skynizz_proton': True}, 'nr-mfg', 'universal', self.prefix, True)
                with self.assertRaisesRegex(t.Refusal, 'Another MFG unlock'):
                    proton_mfg.review(self.target, True, 'dxgi.dll', 'nr-mfg', report)
            (self.target / name).unlink()
        plugin = self.target / universal.PLUGIN
        plugin.parent.mkdir(parents=True)
        plugin.write_bytes(b'manual')
        self.assertEqual(proton_mfg.competing(self.target), [universal.PLUGIN])
        self.assertEqual(proton_mfg.competing(self.target, managed=[universal.PLUGIN]), [])

    def test_review_lines_are_user_language_with_technical_details_apart(self):
        report = proton_mfg.gate({'skynizz_proton': True}, 'nr-mfg', 'universal', self.prefix, True)
        review = proton_mfg.review(self.target, True, 'dxgi.dll', 'nr-mfg', report)
        self.assertEqual(review['lines'][0], proton_mfg.LABEL)
        self.assertIn('Universal MFG 1.6.1', review['lines'][1])
        self.assertIn("this game's prefix", review['lines'][2])
        self.assertFalse(any('sha' in line.casefold() for line in review['lines']))
        details = review['details']
        self.assertEqual(details['override'], {'dxgi': 'n,b'})
        self.assertEqual(details['plugin_sha256'], '24e3e6a8c07639fd9cbd79274e4eb21cc65a13f0453e1157720620c3d6286b33')
        self.assertEqual(details['files'][0], 'OptiScaler/plugins/MFGUnlocker.asi')
        self.assertEqual(details['ini']['Plugins'], {'LoadAsiPlugins': 'true'})

    def test_rtx_50_keeps_its_own_mfg_with_no_plugin_and_says_unverified(self):
        proc, wine = fx.driver(self.root / 'blackwell', model='NVIDIA GeForce RTX 5070 Ti')
        with patch.multiple(proton_stack, DRIVER_ROOT=proc, DRIVER_WINE_DIRS=(str(wine),)):
            # The engine routes RTX 50 to its own MFG whatever component is selected.
            report = proton_mfg.gate({'skynizz_proton': True}, 'nr-mfg', 'integrated', self.prefix, True)
        self.assertTrue(report['mfg_native'])
        self.assertIsNone(report['component'])
        self.assertEqual(report['label'], proton_mfg.NATIVE_LABEL)
        self.assertIn('not yet verified', report['label'])
        self.assertEqual(report['notes'], ['mfg-native-unverified-linux'])
        review = proton_mfg.review(self.target, True, 'dxgi.dll', 'nr-mfg', report)
        self.assertEqual(review['lines'][0], proton_mfg.NATIVE_LABEL)
        self.assertIn("the GPU's own MFG", review['lines'][1])
        self.assertNotIn('Universal', review['lines'][1])
        self.assertEqual((review['details']['files'], review['details']['ini']), ([], {}))
        # Another unlock in the folder still refuses: nothing else may own MFG.
        (self.target / 'dlss-enabler.dll').write_bytes(b'x')
        with self.assertRaisesRegex(t.Refusal, 'Another MFG unlock'):
            proton_mfg.review(self.target, True, 'dxgi.dll', 'nr-mfg', report)

    def test_rtx_30_mfg_stays_refused_on_linux(self):
        proc, wine = fx.driver(self.root / 'ampere', model='NVIDIA GeForce RTX 3080')
        with patch.multiple(proton_stack, DRIVER_ROOT=proc, DRIVER_WINE_DIRS=(str(wine),)):
            with self.assertRaisesRegex(t.Refusal, 'RTX 20 and 30 are not offered'):
                proton_mfg.gate({'skynizz_proton': True}, 'nr-mfg', 'universal', self.prefix, True)

    def installed(self, dll=b'plugin bytes', ini='[Plugins]\nLoadAsiPlugins=true\n[DLSSG]\nAdaMfgUnlock=false\n'):
        plugin = self.target / universal.PLUGIN
        plugin.parent.mkdir(parents=True, exist_ok=True)
        plugin.write_bytes(dll)
        (self.target / 'OptiScaler.ini').write_text(ini)
        component = dict(universal.pinned(), dll={'sha256': hashlib.sha256(dll).hexdigest(), 'size': len(dll)})
        return {'managed_paths': [universal.PLUGIN, 'OptiScaler.ini', 'OptiScaler'],
                'current': {'archive': {'release': {'mfg_component': component}}}}

    def test_verify_checks_exact_plugin_loading_and_single_owner(self):
        baseline = self.installed()
        self.assertEqual(proton_mfg.verify(self.target, baseline), [])
        (self.target / universal.PLUGIN).write_bytes(b'changed')
        self.assertEqual(proton_mfg.verify(self.target, baseline), ['plugin-changed'])
        baseline = self.installed(ini='[Plugins]\nLoadAsiPlugins=false\n[DLSSG]\nAdaMfgUnlock=true\n')
        self.assertEqual(proton_mfg.verify(self.target, baseline), ['plugin-not-loaded', 'competing-unlock-ini'])
        baseline = self.installed()
        (self.target / 'renodx-mfgunlock.addon64').write_bytes(b'addon')
        self.assertEqual(proton_mfg.verify(self.target, baseline), ['competing-unlock'])
        (self.target / universal.PLUGIN).unlink()
        self.assertIn('plugin-missing', proton_mfg.verify(self.target, baseline))
        self.assertEqual(proton_mfg.verify(self.target, {'current': {}}), [], 'other components are not checked here')
        for code in ('plugin-missing', 'plugin-changed', 'plugin-not-loaded', 'competing-unlock', 'competing-unlock-ini'):
            self.assertTrue(proton_mfg.REASONS[code])

    def test_runtime_report_is_an_observation_never_verification(self):
        self.assertIsNone(proton_mfg.runtime_report(self.target))
        (self.target / universal.STATUS).write_text(json.dumps({'dynamicMfgSupportKnown': True, 'dynamicMfgSupported': True}))
        report = proton_mfg.runtime_report(self.target)
        self.assertTrue(report['observed'])
        self.assertFalse(report['verified'])
        self.assertTrue(report['dynamic_supported'])
        self.assertNotIn('hint', report)
        # What CONTROL Resonant wrote under Proton with the placeholder nvcuda.dll.
        (self.target / universal.STATUS).write_text(json.dumps({'gpuFamily': 0, 'gpuSelectionFailure': 200}))
        report = proton_mfg.runtime_report(self.target)
        self.assertEqual(report['gpu_selection_failure'], 200)
        self.assertIn('PROTON_NVIDIA_NVCUDA=1', report['hint'])
        self.assertFalse(report['verified'])
        (self.target / universal.STATUS).write_text('not json')
        self.assertIsNone(proton_mfg.runtime_report(self.target))


if __name__ == '__main__':
    unittest.main()
