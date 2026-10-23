"""The full-bleed image must meet the exact solid surface without a stray strip."""
from pathlib import Path
import sys
import time
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'gui'))
try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GdkPixbuf, GLib, Graphene, Gtk
    from game_mode_visuals import Backdrop
    AVAILABLE = Gtk.init_check()
except (ImportError, ValueError):
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, 'GTK and a display required')
class BackdropPixels(unittest.TestCase):
    def test_fade_and_solid_share_the_same_edge(self):
        window = Gtk.Window(default_width=640, default_height=480, decorated=False)
        backdrop = Backdrop()
        backdrop.apply(SimpleNamespace(c={'view': '#222222'}, light=False, name='dark'), 640, 480, False)
        window.set_child(backdrop)
        window.present()
        try:
            until = time.monotonic() + .2
            while time.monotonic() < until:
                while GLib.MainContext.default().pending():
                    GLib.MainContext.default().iteration(False)
                time.sleep(.001)
            width, height = backdrop.get_width(), backdrop.get_height()
            snapshot = Gtk.Snapshot()
            Gtk.WidgetPaintable.new(backdrop).snapshot(snapshot, width, height)
            texture = window.get_renderer().render_texture(snapshot.to_node(), Graphene.Rect().init(0, 0, width, height))
            loader = GdkPixbuf.PixbufLoader.new_with_type('png')
            loader.write(bytes(texture.save_to_png_bytes().get_data()))
            loader.close()
            pixels = loader.get_pixbuf()
            data = pixels.get_pixels()
            reach = min(width * 1240 / 3840, height * .78)
            for x in (1, width // 2, width - 2):
                for y in (int(reach) + 1, int(reach) + 20, height - 2):
                    at = y * pixels.get_rowstride() + x * pixels.get_n_channels()
                    self.assertEqual(tuple(data[at:at+3]), (34, 34, 34), (x, y))
        finally:
            window.destroy()
