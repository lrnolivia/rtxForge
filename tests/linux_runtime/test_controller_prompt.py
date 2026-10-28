import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import controller_input  # noqa: E402
import controller_prompt as p  # noqa: E402


class ControllerPromptTest(unittest.TestCase):
    def test_face_buttons_match_windows(self):
        self.assertEqual(p.prompt('xbox', 'accept'), ('A', '#8cdb80', 'text'))
        self.assertEqual(p.prompt('playstation', 'back'), ('Circle', '#ff8187', 'circle'))
        self.assertEqual(p.prompt('nintendo', 'select'), ('Y', '#75d9b1', 'text'))
        self.assertEqual(p.prompt('steam', 'search'), ('Y', p.INK, 'text'))
        self.assertEqual(p.prompt('generic', 'select'), ('West', p.INK, 'position2'))

    def test_shoulders_and_system_buttons(self):
        self.assertEqual([p.prompt(f, 'previous')[0] for f in ('xbox', 'playstation', 'nintendo', 'steam')], ['LB', 'L1', 'L', 'LB'])
        self.assertEqual(p.prompt('nintendo', 'menu')[2], 'plus')
        self.assertEqual(p.prompt('xbox', 'settings'), ('View', p.INK, 'view'))
        self.assertEqual(p.prompt('xbox', 'adjust')[2], 'dpad')

    def test_scroll_delta_follows_windows(self):
        self.assertEqual(p.scroll_delta(.18, .04), 0)
        self.assertAlmostEqual(p.scroll_delta(1, .04), 44)
        self.assertAlmostEqual(p.scroll_delta(-1, 1), -55)  # frames cap at 50 ms; up scrolls up
        self.assertAlmostEqual(p.scroll_delta(.59, .04), .5 * 44)
        self.assertEqual(p.scroll_delta(float('nan'), .04), 0)
        self.assertEqual(p.scroll_delta(1, -1), 0)

    def test_steam_controller_by_vendor(self):
        self.assertEqual(controller_input.family(0, 'Xbox 360 Controller', 0x28DE), 'steam')
        self.assertEqual(controller_input.family(1, 'Xbox Controller', 0x045E), 'xbox')
        self.assertEqual(controller_input.family(0, 'Steam Deck'), 'steam')


if __name__ == '__main__':
    unittest.main()
