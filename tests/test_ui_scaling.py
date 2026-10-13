"""Scaling decisions for unscaled, HiDPI and explicit user choices."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'gui'))
from ui_scaling import content_scale

class ScalingTests(unittest.TestCase):
    def test_auto_4k_and_compositor_scaling(self):
        self.assertEqual(content_scale('auto',3840,2160,1),1.5)
        self.assertEqual(content_scale('auto',3840,2160,2),1)
        self.assertEqual(content_scale('auto',1920,1080,1),1)
        self.assertEqual(content_scale('auto',2560,1440,2),1)
    def test_explicit_scale_is_total_not_multiplied_twice(self):
        self.assertEqual(content_scale(150,3840,2160,2),.75)
        self.assertEqual(content_scale(125,1920,1080,1),1.25)

if __name__=='__main__':unittest.main()
