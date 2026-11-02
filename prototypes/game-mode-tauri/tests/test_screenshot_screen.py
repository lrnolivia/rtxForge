import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('screenshot_screen', Path(__file__).resolve().parents[1] / 'bridge/screenshot_screen.py')
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)


def rectangle(x, y, w, h):
    return [[x, y], [x+w, y], [x+w, y+h], [x, y+h]]


class ScreenshotScreenTests(unittest.TestCase):
    def test_clean_scene_and_one_small_environmental_sign(self):
        self.assertTrue(screen.text_layout([], 1280, 720)['clean'])
        self.assertTrue(screen.text_layout([rectangle(600, 300, 60, 15)], 1280, 720)['clean'])

    def test_hud_numbers_and_menu_labels_are_not_clean(self):
        for box in [rectangle(1200, 90, 30, 25), rectangle(15, 40, 100, 25), rectangle(600, 660, 100, 20)]:
            self.assertFalse(screen.text_layout([box], 1280, 720)['clean'])

    def test_promotional_panels_and_text_heavy_frames_are_not_clean(self):
        self.assertFalse(screen.text_layout([rectangle(300, 300, 650, 60)], 1280, 720)['clean'])
        self.assertFalse(screen.text_layout([rectangle(300+i*100, 300, 50, 20) for i in range(4)], 1280, 720)['clean'])


if __name__ == '__main__':
    unittest.main()
