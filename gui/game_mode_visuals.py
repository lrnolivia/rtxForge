"""Game Mode's shared visual world, rendered with GTK/GSK rather than desktop widgets."""
from pathlib import Path
import ctypes
import ctypes.util
import math
import weakref

from gi.repository import Gdk, Graphene, Gtk, PangoCairo

from game_mode_contract import MOTION

ARTWORK_STROKE = MOTION['artwork_stroke']
ROOT = Path(__file__).resolve().parents[1]


class LibraryWindow:
    """A bounded window of native card rows over a full-height GTK scroll canvas."""

    def __init__(self, games, columns, width, row_height, gap, factory, focus):
        self.games, self.columns, self.width = games, columns, width
        self.row_height, self.gap, self.factory, self.focus = row_height, gap, factory, focus
        self.widget = Gtk.Fixed(hexpand=True, valign=Gtk.Align.START)
        self.widget.set_overflow(Gtk.Overflow.VISIBLE)
        self.widget.set_size_request(width, math.ceil(len(games) / columns) * row_height)
        self.widget._gm_virtual = self
        self.keys = {'game-' + game['game']: index for index, game in enumerate(games)}
        self.rows = {}
        self.scroll = None
        self.pending_offset = None
        self.handlers = []
        self.widget.connect('map', self._map)
        self.widget.connect('unmap', self._unmap)

    def _map(self, *_):
        if self.scroll is not None and not self.handlers:
            self.attach(self.scroll)
        else:
            self.update()

    def attach(self, scroll):
        self.scroll = scroll
        adjustment = scroll.get_vadjustment()
        self.handlers = [adjustment.connect('value-changed', lambda *_: self.update()),
                         adjustment.connect('changed', lambda *_: self.update())]
        self.update()

    def _unmap(self, *_):
        if self.scroll is not None:
            adjustment = self.scroll.get_vadjustment()
            for handler in self.handlers:
                adjustment.disconnect(handler)
        self.handlers.clear()

    def row(self, index):
        if index not in self.rows:
            row = Gtk.Box(spacing=self.gap, halign=Gtk.Align.START, valign=Gtk.Align.START)
            row.set_size_request(self.width, -1)
            row._gm_row_index = index
            start = index * self.columns
            for position in range(start, min(start + self.columns, len(self.games))):
                button = self.factory(self.games[position], position)
                button._gm_virtual_index = position
                row.append(button)
            self.rows[index] = row
            self.widget.put(row, 0, index * self.row_height)
        return self.rows[index]

    def ensure(self, key):
        position = self.keys.get(key)
        if position is None:
            return None
        row = self.row(position // self.columns)
        button = row.get_first_child()
        for _ in range(position % self.columns):
            button = button.get_next_sibling()
        return button

    def restore(self, offset):
        self.pending_offset = offset
        self.update()

    def update(self):
        if self.scroll is None:
            return
        adjustment = self.scroll.get_vadjustment()
        if self.pending_offset is not None and adjustment.get_upper() > adjustment.get_page_size() > 0:
            offset, self.pending_offset = self.pending_offset, None
            adjustment.set_value(offset)
        offset = adjustment.get_value() if self.pending_offset is None else self.pending_offset
        height = adjustment.get_page_size() or self.row_height * 2
        first = max(0, int(offset // self.row_height) - 1)
        last = min(math.ceil(len(self.games) / self.columns), math.ceil((offset + height) / self.row_height) + 1)
        wanted = set(range(first, last))
        focus = self.focus()
        while focus is not None:
            if hasattr(focus, '_gm_row_index'):
                wanted.add(focus._gm_row_index)
                break
            focus = focus.get_parent()
        for index in wanted:
            self.row(index)
        for index in set(self.rows) - wanted:
            self.widget.remove(self.rows.pop(index))

    def move(self, focused, direction):
        while focused is not None and not hasattr(focused, '_gm_virtual_index'):
            focused = focused.get_parent()
        if focused is None:
            return False
        index = focused._gm_virtual_index
        if direction == 'left' and index % self.columns == 0:
            return False
        if direction == 'right' and index % self.columns == self.columns - 1:
            return False
        target = index + {'left': -1, 'right': 1, 'up': -self.columns, 'down': self.columns}[direction]
        if not 0 <= target < len(self.games):
            return False
        button = self.ensure('game-' + self.games[target]['game'])
        adjustment = self.scroll.get_vadjustment()
        top, bottom = (target // self.columns) * self.row_height, (target // self.columns + 1) * self.row_height
        if top < adjustment.get_value():
            adjustment.set_value(top)
        elif bottom > adjustment.get_value() + adjustment.get_page_size():
            adjustment.set_value(bottom - adjustment.get_page_size())
        result = button.grab_focus()
        self.update()
        return result


def register_fonts():
    """Process-local font registration; no installation or desktop preference change."""
    try:
        library = ctypes.CDLL(ctypes.util.find_library('fontconfig') or 'libfontconfig.so.1')
        library.FcConfigGetCurrent.restype = ctypes.c_void_p
        library.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        library.FcConfigAppFontAddFile.restype = ctypes.c_int
        for name in ('BakbakOne-Regular.ttf', 'RobotoVariable.ttf'):
            font = ROOT / 'gui' / 'fonts' / name
            if font.is_file():
                library.FcConfigAppFontAddFile(library.FcConfigGetCurrent(), str(font).encode())
        PangoCairo.FontMap.get_default().changed()
    except (OSError, AttributeError):
        pass


class Backdrop(Gtk.Overlay):
    __gtype_name__ = 'RtxForgeGameBackdrop'

    def __init__(self):
        super().__init__(can_target=False, hexpand=True, vexpand=True)
        surface = Gtk.Box(hexpand=True, vexpand=True)
        surface.add_css_class('gm-backdrop')
        self.set_child(surface)
        self.picture = Gtk.Picture.new_for_filename(str(ROOT / 'packaging/steam-artwork/exports/rtxforge-steam-hero.png'))
        self.picture.set_content_fit(Gtk.ContentFit.COVER)
        self.picture.set_can_shrink(True)
        self.picture.set_valign(Gtk.Align.START)
        self.picture.set_can_target(False)
        self.add_overlay(self.picture)
        self.scrim = Gtk.Box(valign=Gtk.Align.START, can_target=False, hexpand=True)
        self.scrim.add_css_class('gm-app-scrim')
        self.add_overlay(self.scrim)

    def apply(self, theme, width, height, details):
        reach = round(min(width * 1240 / 3840, height * .78))
        self.picture.set_size_request(-1, reach)
        self.scrim.set_size_request(-1, reach)
        self.picture.set_opacity(.24 if theme.light else .40 if theme.name == 'night' else .94)
        self.picture.set_visible(not details)
        self.scrim.set_visible(not details)


class ArtworkLight(Gtk.Widget):
    """Blurred actual artwork beneath the UI, outside every rounded group and card."""
    __gtype_name__ = 'RtxForgeArtworkLight'

    def __init__(self):
        super().__init__(hexpand=True, vexpand=True, can_target=False)
        self._owner = self._art = None
        self._node = self._cache_key = None
        self._picture_signal = None
        self.connect('unmap', lambda *_: self._disconnect_picture())

    def _disconnect_picture(self):
        if self._picture_signal:
            picture, handler = self._picture_signal
            picture.disconnect(handler)
            self._picture_signal = None

    def show_art(self, owner, artwork):
        self._disconnect_picture()
        self._owner, self._art = weakref.ref(owner), weakref.ref(artwork)
        picture = getattr(artwork, '_picture', None)
        if picture is not None:
            self._picture_signal = (picture, picture.connect('notify::paintable', lambda *_: self.queue_draw()))
        self.queue_draw()

    def hide_art(self, owner):
        if self._owner and self._owner() is owner:
            self._disconnect_picture()
            self._owner = self._art = None
            self._node = self._cache_key = None
            self.queue_draw()

    def do_snapshot(self, snapshot):
        owner = self._owner() if self._owner else None
        art = self._art() if self._art else None
        if owner is None or art is None or not owner.get_mapped() or not owner.is_sensitive():
            return
        picture = getattr(art, '_picture', None)
        texture = picture.get_paintable() if picture is not None else None
        if not isinstance(texture, Gdk.Texture):
            return
        ok, bounds = art.compute_bounds(self)
        owner_ok, owner_bounds = owner.compute_bounds(self)
        if not ok or not owner_ok or bounds.get_width() <= 0 or bounds.get_height() <= 0:
            return
        width, height = bounds.get_width(), bounds.get_height()
        unit = owner._unit
        key = (texture, width, height, unit)
        if self._cache_key != key:
            cover = max(width / texture.get_width(), height / texture.get_height())
            image_width, image_height = texture.get_width() * cover, texture.get_height() * cover
            bleed = 170 * unit
            drawing = Gtk.Snapshot.new()
            for radius, opacity in ((56, .40), (24, .72)):
                drawing.push_opacity(opacity)
                drawing.push_blur(radius * unit)
                drawing.push_clip(Graphene.Rect().init(bleed, bleed, width, height))
                drawing.append_texture(texture, Graphene.Rect().init(bleed + (width - image_width) / 2,
                    bleed + (height - image_height) / 2, image_width, image_height))
                drawing.pop()
                drawing.pop()
                drawing.pop()
            self._node = drawing.to_paintable(Graphene.Size().init(width + 2 * bleed, height + 2 * bleed))
            self._cache_key = key
        # Snapshot transforms do not change allocation. Light uses the same pose/pivot as the card.
        animated = not owner._preferences.get('reduce_motion', False) and owner.get_settings().get_property('gtk-enable-animations')
        focus, press = (owner._focus_value, owner._press_value) if animated else (0, 0)
        scale = 1 + (.022 * focus if owner._card else 0) - (0 if owner._flat else .018) * press
        lift = -3 * unit * focus if owner._card else 0
        cx, cy = owner_bounds.get_x() + owner.get_width() / 2, owner_bounds.get_y() + owner.get_height() / 2
        clips = 0
        ancestor = owner.get_parent()
        while ancestor is not None:
            if isinstance(ancestor, Gtk.ScrolledWindow):
                valid, viewport = ancestor.compute_bounds(self)
                if valid:
                    snapshot.push_clip(viewport)
                    clips += 1
            ancestor = ancestor.get_parent()
        snapshot.save()
        snapshot.translate(Graphene.Point().init(cx, cy + lift))
        snapshot.scale(scale, scale)
        bleed = 170 * unit
        snapshot.translate(Graphene.Point().init(bounds.get_x() - cx - bleed, bounds.get_y() - cy - bleed))
        self._node.snapshot(snapshot, width + 2 * bleed, height + 2 * bleed)
        snapshot.restore()
        for _ in range(clips):
            snapshot.pop()
