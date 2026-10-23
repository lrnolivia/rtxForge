from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import hardware


class GpuFamilyTest(unittest.TestCase):
    def test_rtx_generations_by_model_number(self):
        for name, family in (('NVIDIA GeForce RTX 2060', 'turing'), ('NVIDIA GeForce RTX 2080 Ti', 'turing'),
                             ('NVIDIA GeForce RTX 3050 Laptop GPU', 'ampere'), ('NVIDIA GeForce RTX 4070', 'ada'),
                             ('NVIDIA GeForce RTX 4090', 'ada'), ('NVIDIA GeForce RTX 5090 D', 'blackwell'),
                             ('NVIDIA GeForce GTX 1080', None), ('NVIDIA RTX A4000', None), ('AMD Radeon RX 7900', None)):
            self.assertEqual(hardware.family(name), family, name)

    def test_every_rtx_family_may_install_and_only_ada_is_verified(self):
        for family in hardware.FAMILIES:
            info = hardware.ready({'gpu': 'Example GPU', 'family': family})
            self.assertTrue(info['ready'])
            self.assertEqual(info['verified'], family == 'ada')
            self.assertEqual("hasn't been verified" in info['reason'], family != 'ada')
            self.assertEqual('own MFG' in info['reason'], family == 'blackwell')


if __name__ == '__main__':
    unittest.main()
