from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ui_colors import readable,contrast,mix

class ContrastTest(unittest.TestCase):
    def test_standard_reference(self):
        self.assertAlmostEqual(contrast('#000000','#ffffff'),21.0)
    def test_accent_text_preserves_readable_colors(self):
        self.assertEqual(readable('#dddddd','#242424'),'#dddddd')
    def test_dark_light_and_selected_surfaces(self):
        accents=('#ec1629','#822222','#222222','#ffffff','#56b2e0','#76b900','#bbbb22')
        for color in accents:
            for backgrounds in (['#3d3d3d','#474747','#505050','#252525'],['#dedede','#d1d1d1','#c1c1c1'],[color]):
                adjusted=readable(color,backgrounds)
                for bg in backgrounds:
                    self.assertGreaterEqual(contrast(adjusted,bg),4.5,(color,adjusted,bg))
    def test_sidebar_composite(self):
        for color in ('#822222','#ec1629','#56b2e0'):
            for bg in ('#2d2d2d','#ebebeb'):
                selected=mix(color,bg,.10)
                self.assertGreaterEqual(contrast(readable(color,selected),selected),4.5)

if __name__=='__main__':unittest.main()
