"""Proton's working CUDA library through the build's user_settings.py: fixture-only."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_fixture as fx
import proton_cuda
import proton_stack


class ProtonCudaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lib = fx.proton(self.root)
        self.settings = self.lib.parent.parent / 'user_settings.py'
        self.state = self.root / 'state'

    def tearDown(self):
        self.tmp.cleanup()

    def test_written_once_shared_by_games_and_removed_with_the_last(self):
        plan = proton_cuda.plan(self.lib)
        self.assertEqual(plan['action'], 'write')
        self.assertIn('every game that uses Proton 10.0', plan['summary'])
        self.assertFalse(self.settings.exists())  # review writes nothing
        self.assertEqual(proton_cuda.apply(plan, self.state, 'control')['status'], 'written')
        self.assertTrue(proton_stack.cuda_requested(self.lib, {}))
        # A second game on the same build only records that it needs the file.
        second = proton_cuda.plan(self.lib)
        self.assertEqual(second['action'], 'keep')
        self.assertEqual(proton_cuda.apply(second, self.state, 'witcher')['status'], 'shared')
        self.assertEqual(proton_cuda.restore(self.state, 'control')['status'], 'kept')
        self.assertTrue(self.settings.is_file())
        self.assertEqual(proton_cuda.restore(self.state, 'witcher')['status'], 'removed')
        self.assertFalse(self.settings.exists())
        self.assertEqual(proton_cuda.restore(self.state, 'witcher')['status'], 'none')

    def test_two_games_reviewed_together_share_one_write(self):
        control, witcher = proton_cuda.plan(self.lib), proton_cuda.plan(self.lib)
        self.assertEqual(proton_cuda.apply(control, self.state, 'control')['status'], 'written')
        self.assertEqual(proton_cuda.apply(witcher, self.state, 'witcher')['status'], 'shared')
        self.assertEqual(proton_cuda.restore(self.state, 'control')['status'], 'kept')
        self.assertEqual(proton_cuda.restore(self.state, 'witcher')['status'], 'removed')

    def test_an_edited_file_is_kept_on_restore(self):
        proton_cuda.apply(proton_cuda.plan(self.lib), self.state, 'control')
        self.settings.write_text(self.settings.read_text() + '# mine now\n')
        self.assertEqual(proton_cuda.restore(self.state, 'control')['status'], 'edited-kept')
        self.assertTrue(self.settings.is_file())

    def test_the_users_own_file_is_never_rewritten(self):
        own = 'user_settings = {"PROTON_LOG": "1"}\n'
        self.settings.write_text(own)
        with self.assertRaises(proton_cuda.CudaError) as refused:
            proton_cuda.plan(self.lib)
        self.assertIn('"PROTON_NVIDIA_NVCUDA": "1"', str(refused.exception))
        # Already turned on by the user: nothing to write, nothing to track or remove.
        own = 'user_settings = {"PROTON_NVIDIA_NVCUDA": "1"}\n'
        self.settings.write_text(own)
        plan = proton_cuda.plan(self.lib)
        self.assertEqual(proton_cuda.apply(plan, self.state, 'control')['status'], 'already-on')
        self.assertEqual(proton_cuda.restore(self.state, 'control')['status'], 'none')
        self.assertEqual(self.settings.read_text(), own)

    def test_a_change_since_review_and_a_build_without_cuda_refuse(self):
        plan = proton_cuda.plan(self.lib)
        self.settings.write_text('user_settings = {}\n')
        with self.assertRaises(proton_cuda.CudaError):
            proton_cuda.apply(plan, self.state, 'control')
        with self.assertRaises(proton_cuda.CudaError) as refused:
            proton_cuda.plan(fx.proton(self.root / 'plain', nvcuda=False))
        self.assertEqual(str(refused.exception), proton_stack.REASONS['cuda-missing'])
        with self.assertRaises(proton_cuda.CudaError):
            proton_cuda.plan(None)


if __name__ == '__main__':
    unittest.main()
