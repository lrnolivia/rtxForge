import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'gui'))
from step_count import StepCount  # noqa: E402


class StepCountTest(unittest.TestCase):
    def test_uncounted_sub_steps_keep_the_count(self):
        count = StepCount()
        self.assertIsNone(count.next('Installing', 0, None))
        self.assertEqual(count.next('Installing', 1, 4), (2, 4, .25))
        self.assertEqual(count.next('Installing', 0, None), (2, 4, .25))

    def test_never_moves_backwards_within_a_step(self):
        count = StepCount()
        count.next('Installing', 2, 4)
        self.assertEqual(count.next('Installing', 1, 4), (3, 4, .5))
        self.assertEqual(count.next('Installing', 3, 4, 1.0), (4, 4, 1.0))

    def test_a_new_verb_starts_afresh(self):
        count = StepCount()
        count.next('Preparing', 3, 4)
        self.assertEqual(count.next('Installing', 0, 4), (1, 4, 0.0))
        count.reset()
        self.assertIsNone(count.next('Installing', 0, 0))


if __name__ == '__main__':
    unittest.main()
