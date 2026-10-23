import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'gui'))
import overlay_shortcut as s  # noqa: E402


class OverlayShortcutTest(unittest.TestCase):
    def test_names_match_windows(self):
        self.assertEqual(s.compose('grave'), 'Backtick')
        self.assertEqual(s.compose('Delete'), 'Delete')
        self.assertEqual(s.compose('Page_Down', ctrl=True), 'Ctrl+PageDown')
        self.assertEqual(s.compose('p', ctrl=True, shift=True), 'Ctrl+Shift+P')
        self.assertEqual(s.compose('KP_5'), 'Num5')

    def test_modifier_alone_waits(self):
        self.assertIsNone(s.compose('Control_L', ctrl=True))

    def test_native_and_system_keys_refused(self):
        for args in (('Insert',), ('Page_Up',)):
            with self.assertRaises(s.ShortcutError):
                s.compose(*args)
        with self.assertRaises(s.ShortcutError):
            s.compose('F4', alt=True)
        with self.assertRaises(s.ShortcutError):
            s.compose('Delete', ctrl=True, alt=True)
        with self.assertRaises(s.ShortcutError):
            s.compose('F12')

    def test_display(self):
        self.assertEqual(s.display('Backtick'), '` (Backtick)')
        self.assertEqual(s.display(None), 'Delete')
        self.assertEqual(s.display('disabled'), 'Disabled')


if __name__ == '__main__':
    unittest.main()
