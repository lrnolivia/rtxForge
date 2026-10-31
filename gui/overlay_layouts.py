"""Native illustrated choices for the three overlay arrangements."""
from gi.repository import Gtk

LAYOUTS = ('floating', 'centered', 'bar')
CAPTIONS = ('Side Panel', 'Advanced', 'Bar')


class LayoutPicker(Gtk.Box):
    def __init__(self, selected, changed):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, homogeneous=True)
        first = None
        for index, (key, caption) in enumerate(zip(LAYOUTS, CAPTIONS)):
            button = Gtk.ToggleButton(hexpand=True)
            if first is None: first = button
            else: button.set_group(first)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                           margin_top=16, margin_bottom=16, margin_start=12, margin_end=12)
            diagram = Gtk.DrawingArea(content_width=100, content_height=88, hexpand=True)
            diagram.set_draw_func(lambda widget, cr, width, height, layout=index: self.draw(widget, cr, width, height, layout))
            body.append(diagram)
            body.append(Gtk.Label(label=caption, wrap=True, justify=Gtk.Justification.CENTER))
            button.set_child(body);button.set_tooltip_text(caption);button.set_active(key == selected)
            button.connect('toggled', lambda item, value=key: changed(value) if item.get_active() else None)
            self.append(button)

    @staticmethod
    def draw(widget, cr, width, height, layout):
        scale = min(width / 180, height / 104)
        cr.translate((width - 180 * scale) / 2, (height - 104 * scale) / 2);cr.scale(scale, scale)
        color = widget.get_style_context().get_color()
        found, accent = widget.get_style_context().lookup_color('accent_bg_color')
        if not found: accent = color
        def shape(x, y, w, h, alpha=.16, active=False):
            ink = accent if active else color
            cr.set_source_rgba(ink.red, ink.green, ink.blue, alpha)
            cr.rectangle(x, y, w, h);cr.fill()
        shape(0, 0, 180, 104, .06)
        if layout == 0:
            shape(12, 10, 53, 84);shape(20, 18, 26, 4, 1, True)
            for row in range(3): shape(20, 30 + row * 18, 37, 12, .22)
            shape(72, 39, 34, 43, .11)
        elif layout == 1:
            shape(26, 16, 128, 72);shape(34, 24, 25, 4, 1, True)
            for row in range(4): shape(34, 37 + row * 10, 25, 4, .25)
            shape(69, 25, 76, 19, .22);shape(69, 51, 34, 27);shape(110, 51, 35, 27)
        else:
            shape(14, 74, 152, 19, .18);shape(23, 81, 26, 4, 1, True)
            for col in range(3): shape(61 + col * 31, 80, 24, 6, .28)
            shape(92, 27, 55, 39, .14);shape(102, 35, 26, 4, .7, True);shape(102, 46, 35, 11, .22)
