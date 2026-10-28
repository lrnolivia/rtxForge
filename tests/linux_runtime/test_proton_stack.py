"""Proton prerequisite detection for native NR + Ada MFG: read-only, fixture-only."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_fixture as fx
import proton_stack


class ProtonStackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proc, self.wine = fx.driver(self.root)
        self.lib = fx.proton(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def detect(self, pfx, mode='nr-mfg', **kwargs):
        return proton_stack.detect(pfx, mode, driver_root=self.proc, driver_dirs=(str(self.wine),), **kwargs)

    def failing(self, report):
        return {c['id'] for c in report['checks'] if c['required'] and c['state'] != 'ok'}

    def test_complete_stack_meets_prerequisites_but_is_never_runtime_verified(self):
        pfx = fx.prefix(self.root / 'lib', 1091500, self.lib)
        report = self.detect(pfx, native_dlssg=True)
        self.assertTrue(report['prerequisites_met'], report['reasons'])
        self.assertFalse(report['runtime_verified'])
        self.assertIn('not yet verified', report['label'])
        self.assertEqual(report['tool']['version'], '10.0-200')
        self.assertEqual(report['components']['dxvk-nvapi'], {'present': True, 'version': 'v0.9.0'})
        self.assertEqual(report['gpu']['architecture'], 'ada')

    def test_each_missing_piece_has_its_own_reason(self):
        cases = [
            ('vkd3d-missing', dict(components=('dxvk', 'nvapi')), {}),
            ('nvapi-missing', dict(components=('dxvk', 'vkd3d-proton')), {}),
            ('nvapi-not-in-prefix', {}, dict(nvapi=False)),
            ('ngx-not-in-prefix', {}, dict(ngx=False)),
        ]
        for index, (reason, tool, pfx_options) in enumerate(cases):
            with self.subTest(reason=reason):
                lib = fx.proton(self.root / f'tool{index}', **tool) if tool else self.lib
                pfx = fx.prefix(self.root / f'lib{index}', 100 + index, lib, **pfx_options)
                report = self.detect(pfx, native_dlssg=True)
                self.assertFalse(report['prerequisites_met'])
                self.assertEqual(report['reasons'], [reason])
                self.assertTrue(proton_stack.REASONS[reason])

    def test_mfg_needs_protons_working_cuda_library(self):
        # Proton's default nvcuda.dll exports nothing, so the MFG Unlocker
        # cannot identify the GPU (gpuSelectionFailure 200).
        pfx = fx.prefix(self.root / 'stub', 31, self.lib, cuda=False)
        report = self.detect(pfx, native_dlssg=True)
        self.assertEqual(report['reasons'], ['cuda-off'])
        self.assertIn('PROTON_NVIDIA_NVCUDA=1', proton_stack.REASONS['cuda-off'])
        # NR alone never asks for CUDA.
        self.assertTrue(self.detect(pfx, 'nr-only')['prerequisites_met'])
        # Requested for the next run: in the launch options or the build's user_settings.py.
        for switch in ('PROTON_NVIDIA_NVCUDA=1', 'PROTON_NVIDIA_LIBS=1'):
            with self.subTest(switch=switch):
                self.assertTrue(self.detect(pfx, native_dlssg=True, launch_options=switch + ' %command%')['prerequisites_met'])
        self.assertFalse(self.detect(pfx, native_dlssg=True,
                                     launch_options='PROTON_NVIDIA_NVCUDA=0 %command%')['prerequisites_met'])
        settings = self.lib.parent.parent / 'user_settings.py'
        settings.write_text('user_settings = {\n    "PROTON_NVIDIA_NVCUDA": "1",\n}\n')
        self.assertTrue(self.detect(pfx, native_dlssg=True)['prerequisites_met'])
        settings.write_text('user_settings = {"PROTON_NVIDIA_NVCUDA": "0"}\n')
        self.assertEqual(self.detect(pfx, native_dlssg=True)['reasons'], ['cuda-off'])
        # A build without nvidia-libs cannot provide it at all.
        lib = fx.proton(self.root / 'plain', nvcuda=False)
        pfx = fx.prefix(self.root / 'plainlib', 32, lib, cuda=False)
        self.assertEqual(self.detect(pfx, native_dlssg=True,
                                     launch_options='PROTON_NVIDIA_NVCUDA=1 %command%')['reasons'], ['cuda-missing'])

    def test_unlaunched_game_and_unreadable_tool(self):
        report = self.detect(None)
        self.assertIn('prefix-missing', report['reasons'])
        pfx = fx.prefix(self.root / 'lib', 7, self.lib)
        (pfx.parent / 'config_info').write_text('garbage\n')
        self.assertIn('tool-unknown', self.detect(pfx)['reasons'])

    def test_launch_options_that_disable_d3d12_or_nvapi_refuse(self):
        pfx = fx.prefix(self.root / 'lib', 1091500, self.lib)
        self.assertIn('vkd3d-disabled', self.detect(pfx, launch_options='PROTON_USE_WINED3D=1 %command%')['reasons'])
        self.assertIn('vkd3d-disabled', self.detect(pfx, launch_options='PROTON_NO_D3D12=1 %command%')['reasons'])
        self.assertIn('nvapi-disabled', self.detect(pfx, launch_options='PROTON_DISABLE_NVAPI=1 %command%')['reasons'])
        forced = self.detect(pfx, launch_options='PROTON_DISABLE_NVAPI=1 PROTON_FORCE_NVAPI=1 %command%')
        self.assertNotIn('nvapi-disabled', forced['reasons'])
        # Assignments after %command% are game arguments, not environment.
        self.assertTrue(self.detect(pfx, launch_options='%command% PROTON_NO_D3D12=1')['prerequisites_met'])

    def test_mfg_is_only_offered_on_ada_but_nr_only_runs_on_any_rtx(self):
        for model, arch in [('NVIDIA GeForce RTX 3080', 'ampere'), ('NVIDIA GeForce RTX 2070 SUPER', 'turing'),
                            ('NVIDIA GeForce RTX 5090', 'blackwell'), ('NVIDIA GeForce RTX 4060 Laptop GPU', 'ada')]:
            with self.subTest(model=model):
                self.assertEqual(proton_stack.architecture(model), arch)
        root = self.root / 'ampere'
        root.mkdir()
        proc, wine = fx.driver(root, model='NVIDIA GeForce RTX 3080')
        pfx = fx.prefix(self.root / 'lib', 1091500, self.lib)
        mfg = proton_stack.detect(pfx, 'nr-mfg', driver_root=proc, driver_dirs=(str(wine),))
        self.assertEqual(mfg['reasons'], ['mfg-gpu-unverified-linux'])
        nr = proton_stack.detect(pfx, 'nr-only', driver_root=proc, driver_dirs=(str(wine),))
        self.assertTrue(nr['prerequisites_met'])
        self.assertEqual(proton_stack.architecture('AMD Radeon RX 7900 XTX'), 'unknown')

    def test_driver_missing_old_or_without_wine_ngx(self):
        pfx = fx.prefix(self.root / 'lib', 1091500, self.lib)
        empty = self.root / 'no-driver'
        empty.mkdir()
        report = proton_stack.detect(pfx, 'nr-only', driver_root=empty, driver_dirs=(str(empty),))
        self.assertIn('nvidia-driver-missing', report['reasons'])
        self.assertIn('driver-ngx-missing', report['reasons'])
        old = self.root / 'old'
        old.mkdir()
        proc, wine = fx.driver(old, version='550.120')
        self.assertIn('nvidia-driver-old', proton_stack.detect(pfx, 'nr-only', driver_root=proc, driver_dirs=(str(wine),))['reasons'])

    def test_game_without_native_dlssg_cannot_take_mfg(self):
        pfx = fx.prefix(self.root / 'lib', 1091500, self.lib)
        self.assertEqual(self.detect(pfx, native_dlssg=False)['reasons'], ['native-dlssg-missing'])

    def test_evidence_needs_a_human_confirmed_observation_for_the_exact_identity(self):
        state = self.root / 'state'
        self.assertIsNone(proton_stack.evidence(state, 1091500, '10.0-200', 'RTX 4070', 'universal-1.6.1'))
        with self.assertRaises(ValueError):
            proton_stack.record_evidence(state, 1091500, '10.0-200', 'RTX 4070', 'universal-1.6.1', '', 'Lauren')
        with self.assertRaises(ValueError):
            proton_stack.record_evidence(state, 1091500, '10.0-200', 'RTX 4070', 'universal-1.6.1', '4x presented', ' ')
        proton_stack.record_evidence(state, 1091500, '10.0-200', 'RTX 4070', 'universal-1.6.1', '4 frames presented per real frame', 'Lauren')
        self.assertIsNotNone(proton_stack.evidence(state, 1091500, '10.0-200', 'RTX 4070', 'universal-1.6.1'))
        # A different Proton build is a different identity.
        self.assertIsNone(proton_stack.evidence(state, 1091500, '11.0-100', 'RTX 4070', 'universal-1.6.1'))

    def test_detection_never_writes(self):
        pfx = fx.prefix(self.root / 'lib', 1091500, self.lib)
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}
        self.detect(pfx, native_dlssg=True, launch_options='PROTON_LOG=1 %command%')
        after = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}
        self.assertEqual(before, after)

    def test_feeder_route_is_reported_but_never_offered(self):
        pfx = fx.prefix(self.root / 'lib', 1328670, self.lib)
        report = proton_stack.feeder_detect(pfx, driver_root=self.proc, driver_dirs=(str(self.wine),))
        self.assertTrue(report['prerequisites_met'])
        self.assertFalse(report['offered'])
        self.assertIn('Windows-only', report['offer_reason'])
        lib = fx.proton(self.root / 'no-dxvk', components=('vkd3d-proton', 'nvapi'))
        pfx = fx.prefix(self.root / 'lib2', 1328670, lib)
        report = proton_stack.feeder_detect(pfx, driver_root=self.proc, driver_dirs=(str(self.wine),))
        self.assertEqual(report['reasons'], ['dxvk-missing'])

    def test_not_linux(self):
        self.assertEqual(proton_stack.detect(None, system='windows')['reasons'], ['not-linux'])


if __name__ == '__main__':
    unittest.main()
