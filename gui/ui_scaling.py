"""Native content scaling; compositor scaling remains owned by the desktop."""
import math
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gsk

SCALES = ('auto', 100, 125, 150, 175, 200)

def content_scale(choice, physical_width, physical_height, system_scale=1):
    system_scale = max(1.0, float(system_scale))
    if choice == 'auto':
        target = max(system_scale, 1.5 if physical_width >= 3840 and physical_height >= 2160 else 1.0)
    else:
        target = float(choice) / 100
    return max(.5, min(2.0, target / system_scale))

class ScaleLayout(Gtk.LayoutManager):
    def do_get_request_mode(self, widget):
        return widget.child.get_request_mode()

    def do_measure(self, widget, orientation, for_size):
        logical = math.floor(for_size / widget.factor) if for_size >= 0 else -1
        minimum, natural, _, _ = widget.child.measure(orientation, logical)
        return math.ceil(minimum * widget.factor), math.ceil(natural * widget.factor), -1, -1

    def do_allocate(self, widget, width, height, baseline):
        widget.child.allocate(max(1, round(width / widget.factor)), max(1, round(height / widget.factor)), -1, Gsk.Transform.new().scale(widget.factor, widget.factor))

class ScaledContent(Gtk.Widget):
    """Scale allocation and input coordinates together, rather than bitmap zoom."""
    def __init__(self, child, factor=1.0):
        super().__init__()
        self.child = child
        self.factor = factor
        self.set_layout_manager(ScaleLayout())
        child.set_parent(self)
        self.set_hexpand(True)
        self.set_vexpand(True)

    def set_factor(self, factor):
        if abs(self.factor - factor) > .001:
            self.factor = factor
            self.get_layout_manager().layout_changed()

    def do_snapshot(self, snapshot):
        self.snapshot_child(self.child, snapshot)

    def do_focus(self, direction):
        return self.child.child_focus(direction)

    def release(self):
        if self.child.get_parent() is self:
            self.child.unparent()
