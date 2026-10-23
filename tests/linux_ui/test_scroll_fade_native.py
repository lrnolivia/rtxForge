"""Native pixels: viewport content fades to transparency without fading its backdrop."""
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'gui'))
try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Graphene, Gtk
    from game_mode_motion import FadedScrolledWindow
    AVAILABLE = Gtk.init_check()
except (ImportError, ValueError):
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, 'GTK and a display required')
class ScrollFadePixels(unittest.TestCase):
    def drain(self):
        end = time.monotonic() + .12
        while time.monotonic() < end:
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            time.sleep(.001)

    def test_partly_scrolled_artwork_light_stays_inside_viewport(self):
        from game_mode_motion import MotionButton
        from game_mode_visuals import ArtworkLight
        Adw.init()
        window = Gtk.Window(default_width=400, default_height=600)
        overlay = Gtk.Overlay()
        overlay.add_css_class('glow-test-background')
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        top = Gtk.Box(height_request=90)
        layout.append(top)
        scroll = Gtk.ScrolledWindow(height_request=300, vexpand=False,
            hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        texture = Gdk.MemoryTexture.new(100, 150, Gdk.MemoryFormat.R8G8B8A8,
            GLib.Bytes.new(bytes([255, 0, 0, 255]) * 15000), 400)
        art = Gtk.Box(width_request=200, height_request=260, halign=Gtk.Align.CENTER)
        picture = Gtk.Picture.new_for_paintable(texture)
        picture.set_can_shrink(True)
        picture.set_size_request(200, 260)
        art.append(picture)
        art._picture = picture
        button = MotionButton(preferences={}, motion_card=True, child=art)
        content.append(button)
        content.append(Gtk.Box(height_request=1200))
        scroll.set_child(content)
        layout.append(scroll)
        layout.append(Gtk.Box(vexpand=True))
        overlay.set_child(layout)
        light = ArtworkLight()
        overlay.add_overlay(light)
        window.set_child(overlay)
        css = Gtk.CssProvider()
        css.load_from_string('.glow-test-background { background: #00ff00; }')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, 900)
        window.present()
        try:
            self.drain()
            scroll.get_vadjustment().set_value(120)
            light.show_art(button, art)
            self.drain()
            snapshot = Gtk.Snapshot()
            Gtk.WidgetPaintable.new(overlay).snapshot(snapshot, overlay.get_width(), overlay.get_height())
            node = snapshot.to_node()
            texture = window.get_renderer().render_texture(node, Graphene.Rect().init(0, 0, overlay.get_width(), overlay.get_height()))
            loader = GdkPixbuf.PixbufLoader.new_with_type('png')
            loader.write(bytes(texture.save_to_png_bytes().get_data()))
            loader.close()
            pixbuf = loader.get_pixbuf()
            data = pixbuf.get_pixels()
            valid, viewport = scroll.compute_bounds(overlay)
            self.assertTrue(valid)
            y = round(viewport.get_y()) - 30
            at = y * pixbuf.get_rowstride() + 200 * pixbuf.get_n_channels()
            self.assertEqual(tuple(data[at:at + 3]), (0, 255, 0), 'No artwork glow above the viewport')
            y = round(viewport.get_y()) + 20
            at = y * pixbuf.get_rowstride() + 200 * pixbuf.get_n_channels()
            self.assertGreater(data[at], 10, 'Visible artwork/light still renders inside the viewport')
        finally:
            window.destroy()
            Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(), css)

    def test_native_alpha_edges_and_real_boundaries(self):
        Adw.init()
        window = Gtk.Window(default_width=400, default_height=400)
        box = Gtk.Box()
        box.add_css_class('fade-test-background')
        scroll = FadedScrolledWindow(vexpand=True, hexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.add_css_class('fade-test-content')
        content.set_size_request(350, 1600)
        button = Gtk.Button(label='Native input')
        button.set_halign(Gtk.Align.START)
        button.set_margin_top(200)
        content.append(button)
        scroll.set_child(content)
        box.append(scroll)
        window.set_child(box)
        css = Gtk.CssProvider()
        css.load_from_string('.fade-test-background { background: #00ff00; } .fade-test-content { background: #ff0000; }')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, 900)
        window.present()
        try:
            self.drain()
            adjustment = scroll.get_vadjustment()
            def pixel(y, x=200):
                paintable = Gtk.WidgetPaintable.new(box)
                snapshot = Gtk.Snapshot()
                paintable.snapshot(snapshot, box.get_width(), box.get_height())
                node = snapshot.to_node()
                texture = window.get_renderer().render_texture(node, Graphene.Rect().init(0, 0, box.get_width(), box.get_height()))
                loader = GdkPixbuf.PixbufLoader.new_with_type('png')
                loader.write(bytes(texture.save_to_png_bytes().get_data()))
                loader.close()
                pixbuf = loader.get_pixbuf()
                at = y * pixbuf.get_rowstride() + x * pixbuf.get_n_channels()
                return tuple(pixbuf.get_pixels()[at:at + 3])
            adjustment.set_value(500)
            self.drain()
            height = box.get_height()
            self.assertGreater(pixel(1)[1], 240)
            self.assertGreater(pixel(height - 2)[1], 240)
            for x in (1, box.get_width() - 2):
                self.assertGreater(pixel(1, x)[1], 240)
                self.assertGreater(pixel(height - 2, x)[1], 240)
            self.assertGreater(pixel(height // 2)[0], 240)
            self.assertTrue(40 < pixel(44)[0] < 230, pixel(44))
            adjustment.set_value(0)
            self.drain()
            self.assertGreater(pixel(1)[0], 240)
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
            self.drain()
            self.assertGreater(pixel(height - 2)[0], 240)
            self.assertTrue(button.grab_focus())
            self.assertIs(window.get_focus(), button)
        finally:
            window.destroy()
            Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(), css)


if __name__ == '__main__':
    unittest.main()
