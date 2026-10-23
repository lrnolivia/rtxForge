"""Native GTK regression suite: run with a display or xvfb on Linux."""
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'gui'))
try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Adw, GLib, Gtk
    import game_mode_motion as motion
    AVAILABLE = Gtk.init_check()
except (ImportError, ValueError):
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, 'GTK 4/libadwaita and a display are required')
class NativeMotionTests(unittest.TestCase):
    def drain(self, milliseconds=60):
        until = time.monotonic() + milliseconds / 1000
        context = GLib.MainContext.default()
        while time.monotonic() < until:
            while context.pending():
                context.iteration(False)
            time.sleep(.001)

    def setUp(self):
        Adw.init()
        self.preferences = {}
        self.window = Gtk.Window(default_width=1280, default_height=720)
        self.deck = motion.MotionDeck()
        self.window.set_child(self.deck)
        self.window.present()

    def tearDown(self):
        self.window.destroy()
        self.drain(10)

    def scene(self):
        scene = motion.MotionScene(self.preferences)
        line = Gtk.Box(spacing=12)
        buttons = [motion.MotionButton(preferences=self.preferences, motion_card=True, label=str(i)) for i in range(12)]
        for button in buttons:
            line.append(button)
        scene.set_child(line)
        return scene, buttons

    def test_rapid_focus_and_reversal_never_changes_allocation(self):
        scene, buttons = self.scene()
        self.deck.show_scene(scene, False, self.preferences)
        self.drain()
        width = buttons[0].get_width()
        for i in list(range(12)) + list(reversed(range(12))):
            self.assertTrue(buttons[i].grab_focus())
            buttons[i].acknowledge()
            self.drain(8)
            self.assertIs(self.window.get_focus(), buttons[i])
        self.assertEqual(buttons[0].get_width(), width)

    def test_page_handoff_is_bounded_and_focus_is_live(self):
        for _ in range(8):
            scene, buttons = self.scene()
            self.deck.show_scene(scene, True, self.preferences)
            self.drain(8)
            self.assertTrue(buttons[0].grab_focus())
            self.assertIs(self.window.get_focus(), buttons[0])
        self.drain(180)
        self.assertIsNone(self.deck.outgoing)

    def test_reduced_motion_cancels_spatial_pose(self):
        self.preferences['reduce_motion'] = True
        scene, buttons = self.scene()
        self.deck.show_scene(scene, True, self.preferences)
        self.drain()
        buttons[0].grab_focus()
        buttons[0].acknowledge()
        self.assertFalse(motion.enabled(buttons[0], self.preferences))
        self.assertEqual(scene.progress, 1)
        self.assertEqual(buttons[0]._press_value, 0)

    def test_selection_survives_rebuild_and_keeps_true_capsule_height(self):
        states = {}
        for selected in (0, 2, 1, 0):
            line = Gtk.Box(spacing=12)
            buttons = [motion.MotionButton(preferences=self.preferences, label=name) for name in ('Posters', 'Wide Capsule', 'List')]
            for button in buttons:
                line.append(button)
            selector = motion.selection(states, 'views', line, buttons[selected], self.preferences, '#ededed')
            scene = motion.MotionScene(self.preferences)
            scene.set_child(selector)
            self.deck.show_scene(scene, False, self.preferences)
            self.drain(35)
            self.assertGreater(selector._height, 0)
            self.assertGreater(states['views']['width'], 0)
        self.drain(250)
        self.assertAlmostEqual(states['views']['width'], buttons[0].get_allocated_width(), delta=1)
        self.assertAlmostEqual(selector._height, buttons[0].get_allocated_height(), delta=1)
        # A later allocation must retarget the indicator rather than keeping its map-time size.
        buttons[0].set_size_request(180, 54)
        self.drain(300)
        self.assertAlmostEqual(states['views']['width'], buttons[0].get_allocated_width(), delta=1)


if __name__ == '__main__':
    unittest.main()
