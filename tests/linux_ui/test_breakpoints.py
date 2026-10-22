import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'gui'))
import breakpoints as b  # noqa: E402


class BreakpointsTest(unittest.TestCase):
    """Same thresholds as the Windows build."""

    def test_side_margin_matches_page_margins(self):
        self.assertEqual(b.side_margin(400), 16)
        self.assertEqual(b.side_margin(1000), 30)
        self.assertEqual(b.side_margin(2000), 200)   # centered 1600 column
        self.assertEqual(b.side_margin(1800), 100)

    def test_library_layouts(self):
        self.assertEqual([b.library_layout(w) for w in (639, 640, 999, 1000)], [2, 1, 1, 0])
        self.assertEqual([b.library_labels(w) for w in (1179, 1180)], [False, True])

    def test_list_density(self):
        self.assertEqual([b.list_density(w) for w in (859, 860, 1059, 1060)], [2, 1, 1, 0])

    def test_details(self):
        self.assertEqual([b.details_narrow(w) for w in (979, 980)], [True, False])
        self.assertEqual((b.hero_height(500), b.hero_height(1300), b.hero_height(2000)), (360, 494, 620))

    def test_navigation(self):
        self.assertEqual([b.nav_mode(w) for w in (640, 641, 1007, 1008)], ['minimal', 'compact', 'compact', 'expanded'])


if __name__ == '__main__':
    unittest.main()
