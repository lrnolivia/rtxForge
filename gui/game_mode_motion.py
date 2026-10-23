"""Native Game Mode motion. Rendering changes pose, never allocation or input timing."""
import math
import weakref

import gi
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, GLib, Graphene, Gsk, Gtk
from game_mode_contract import MOTION, scroll_fade, scroll_fade_alpha

PRESS_MS, FOCUS_MS, SURFACE_MS, FADE_MS = (MOTION[k] for k in ('press_ms', 'focus_ms', 'surface_ms', 'fade_ms'))
CARD_SCALE, CARD_LIFT = MOTION['card_scale'], MOTION['card_lift']


class FadedScrolledWindow(Gtk.ScrolledWindow):
    """Native scrolling with broad alpha edges, keeping native scrollbar opacity."""
    __gtype_name__ = 'RtxForgeFadedScrolledWindow'

    def __init__(self, *, fade_unit=1, **kwargs):
        super().__init__(**kwargs)
        self._fade_unit = fade_unit
        self._fade_key = None
        self._fade_stops = []
        for adjustment in (self.get_vadjustment(), self.get_hadjustment()):
            adjustment.connect('value-changed', self._scroll_changed)
            adjustment.connect('changed', self._scroll_changed)

    def _scroll_changed(self, *_):
        self.queue_draw()

    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()
        adjustment = self.get_vadjustment()
        extent = max(0, adjustment.get_upper() - adjustment.get_page_size() - adjustment.get_lower())
        depth, top, bottom = scroll_fade(height, adjustment.get_value() - adjustment.get_lower(), extent, self._fade_unit)
        if width <= 0 or depth <= 0 or (top == 0 and bottom == 0):
            Gtk.ScrolledWindow.do_snapshot(self, snapshot)
            return
        key = (height, depth, top, bottom)
        if self._fade_key != key:
            samples = int(MOTION['scroll_fade_samples'])
            positions = ([depth * i / samples for i in range(samples + 1)]
                         + [height - depth + depth * i / samples for i in range(samples + 1)])
            self._fade_stops = []
            for y in positions:
                stop = Gsk.ColorStop()
                stop.offset = y / height
                color = Gdk.RGBA()
                color.red = color.green = color.blue = 1
                color.alpha = scroll_fade_alpha(y, height, depth, top, bottom)
                stop.color = color
                self._fade_stops.append(stop)
            self._fade_key = key
        bounds = Graphene.Rect().init(0, 0, width, height)
        snapshot.push_mask(Gsk.MaskMode.ALPHA)
        snapshot.append_linear_gradient(bounds, Graphene.Point().init(0, 0),
                                        Graphene.Point().init(0, height), self._fade_stops)
        white = Gdk.RGBA()
        white.red = white.green = white.blue = white.alpha = 1
        for bar in (self.get_vscrollbar(), self.get_hscrollbar()):
            if bar and bar.get_mapped():
                valid, rect = bar.compute_bounds(self)
                if valid:
                    snapshot.append_color(white, rect)
        snapshot.pop()
        Gtk.ScrolledWindow.do_snapshot(self, snapshot)
        snapshot.pop()


def enabled(widget, preferences):
    return (not preferences.get('reduce_motion', False)
            and widget.get_settings().get_property('gtk-enable-animations'))


class MotionButton(Gtk.Button):
    """A normal accessible GtkButton with interruptible libadwaita spring contact."""
    __gtype_name__ = 'RtxForgeMotionButton'

    def __init__(self, *, preferences, motion_card=False, motion_flat=False, motion_unit=1, **kwargs):
        super().__init__(**kwargs)
        self.set_overflow(Gtk.Overflow.VISIBLE)
        self._preferences = preferences
        self._card, self._flat, self._unit = motion_card, motion_flat, motion_unit
        self._hovered = False
        self._focus_value = self._press_value = 0.0
        self._release = 0
        self._springs = {}
        self.connect('state-flags-changed', self._state)
        self.connect('unmap', self._unmap)
        self.connect('clicked', lambda *_: self.acknowledge())
        motion = Gtk.EventControllerMotion()
        motion.connect('enter', lambda *_: self._hover(True))
        motion.connect('leave', lambda *_: self._hover(False))
        self.add_controller(motion)
        gesture = Gtk.GestureClick()
        gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesture.connect('pressed', lambda *_: self._retarget('press', 1))
        gesture.connect('released', lambda *_: self._retarget('press', 0))
        gesture.connect('cancel', lambda *_: self._retarget('press', 0))
        self.add_controller(gesture)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._key_pressed)
        keys.connect('key-released', self._key_released)
        self.add_controller(keys)

    def _key_pressed(self, _controller, key, *_):
        if key in (Gdk.KEY_Return, Gdk.KEY_space, Gdk.KEY_KP_Enter):
            self._retarget('press', 1)
        return False

    def _key_released(self, _controller, key, *_):
        if key in (Gdk.KEY_Return, Gdk.KEY_space, Gdk.KEY_KP_Enter):
            self._retarget('press', 0)

    def _hover(self, on):
        self._hovered = on
        self._state()

    def _state(self, *_):
        flags = self.get_state_flags()
        focused = bool(flags & Gtk.StateFlags.FOCUS_VISIBLE)
        self._retarget('focus', float(self.get_sensitive() and (focused or self._hovered)))
        light, art = getattr(self, '_light_layer', None), getattr(self, '_light_art', None)
        if light and art:
            if self.get_sensitive() and (focused or self._hovered):
                light.show_art(self, art)
            else:
                light.hide_art(self)
        if not self.get_sensitive() or not (focused or self._hovered):
            self._retarget('press', 0)

    def _retarget(self, channel, value):
        if not self.get_mapped():
            setattr(self, '_' + channel + '_value', 0.0)
            return
        if not enabled(self, self._preferences):
            spring = self._springs.get(channel)
            if spring:
                spring.pause()
            setattr(self, '_' + channel + '_value', 0.0)
            self.queue_draw()
            return
        spring = self._springs.get(channel)
        if spring is None:
            period = FOCUS_MS if channel == 'focus' else PRESS_MS
            ratio = MOTION['focus_damping'] if channel == 'focus' else MOTION['press_damping']
            reference = weakref.ref(self)
            def pose(current):
                widget = reference()
                if widget is not None:
                    setattr(widget, '_' + channel + '_value', current)
                    widget.queue_draw()
                    light = getattr(widget, '_light_layer', None)
                    if light:
                        light.queue_draw()
            target = Adw.CallbackAnimationTarget.new(pose)
            parameters = Adw.SpringParams.new(ratio, 1, (2 * math.pi / (period / 1000)) ** 2)
            spring = Adw.SpringAnimation.new(self, 0, 0, parameters, target)
            spring.set_epsilon(.001)
            self._springs[channel] = spring
        if spring.get_value_to() == value:
            return
        current, velocity = spring.get_value(), spring.get_velocity()
        spring.pause()
        spring.set_value_from(current)
        spring.set_value_to(value)
        spring.set_initial_velocity(velocity)
        spring.play()

    def acknowledge(self):
        if self._release:
            GLib.source_remove(self._release)
        self._retarget('press', 1)
        def release():
            self._release = 0
            self._retarget('press', 0)
            return GLib.SOURCE_REMOVE
        self._release = GLib.timeout_add(round(PRESS_MS * .65), release)

    def _unmap(self, *_):
        light = getattr(self, '_light_layer', None)
        if light:
            light.hide_art(self)
        if self._release:
            GLib.source_remove(self._release)
            self._release = 0
        for spring in self._springs.values():
            spring.pause()
        self._springs.clear()
        self._focus_value = self._press_value = 0

    def do_snapshot(self, snapshot):
        active = enabled(self, self._preferences)
        focus, press = (self._focus_value, self._press_value) if active else (0, 0)
        scale = 1 + (CARD_SCALE * focus if self._card else 0) - (0 if self._flat else MOTION['card_compression'] if self._card else MOTION['button_compression']) * press
        lift = CARD_LIFT * self._unit * focus if self._card else 0
        snapshot.save()
        snapshot.translate(Graphene.Point().init(self.get_width() / 2, self.get_height() / 2 + lift))
        snapshot.scale(scale, scale)
        snapshot.translate(Graphene.Point().init(-self.get_width() / 2, -self.get_height() / 2))
        Gtk.Button.do_snapshot(self, snapshot)
        snapshot.restore()


def reveal(widget, preferences, duration=FADE_MS, start=.94):
    """A visible-first dissolve, without a delayed focus or an interaction gate."""
    if not widget.get_mapped():
        def mapped(current):
            current.disconnect(handler)
            reveal(current, preferences, duration, start)
        handler = widget.connect('map', mapped)
        return
    if not enabled(widget, preferences):
        widget.set_opacity(1)
        return
    previous = getattr(widget, '_gm_reveal', None)
    if previous:
        previous.pause()
    target = Adw.PropertyAnimationTarget.new(widget, 'opacity')
    animation = Adw.TimedAnimation.new(widget, start, 1, duration, target)
    animation.set_easing(Adw.Easing.EASE_OUT_EXPO)
    widget._gm_reveal = animation
    animation.play()


class MotionScene(Gtk.Overlay):
    """Surface and light move as one render subtree; layout and focus stay live."""
    __gtype_name__ = 'RtxForgeMotionScene'

    def __init__(self, preferences, unit=1, dialog=False, spatial=True, region=0):
        super().__init__(hexpand=True, vexpand=True)
        self.set_overflow(Gtk.Overflow.VISIBLE)
        self.preferences, self.unit = preferences, unit
        self.dialog, self.spatial, self.region = dialog, spatial, region
        self.progress = 1.0
        self._animation = None
        self.connect('map', self._enter)
        self.connect('unmap', self._leave)

    def _enter(self, *_):
        if not enabled(self, self.preferences):
            self.progress = 1
            return
        self.progress = 0
        reference = weakref.ref(self)
        def update(value):
            widget = reference()
            if widget:
                widget.progress = value
                widget.queue_draw()
        target = Adw.CallbackAnimationTarget.new(update)
        params = Adw.SpringParams.new(MOTION['scene_damping'], 1, (2 * math.pi / ((SURFACE_MS if self.dialog else MOTION['page_regions'][min(self.region, 3)]['period_ms']) / 1000)) ** 2)
        self._animation = Adw.SpringAnimation.new(self, 0, 1, params, target)
        self._animation.set_epsilon(.001)
        self._animation.play()

    def _leave(self, *_):
        if self._animation:
            self._animation.pause()
        self._animation = None

    def do_snapshot(self, snapshot):
        progress = self.progress if enabled(self, self.preferences) else 1
        scale = 1 - ((1 - MOTION['dialog_scale']) * (1 - progress) if self.dialog and self.spatial else 0)
        travel = ((MOTION['dialog_travel'] if self.dialog else MOTION['page_regions'][min(self.region, 3)]['travel']) * self.unit * (1 - progress)) if self.spatial else 0
        snapshot.save()
        snapshot.translate(Graphene.Point().init(self.get_width() / 2, self.get_height() / 2 + travel))
        snapshot.scale(scale, scale)
        snapshot.translate(Graphene.Point().init(-self.get_width() / 2, -self.get_height() / 2))
        snapshot.push_opacity(max(0, min(1, (.90 if self.dialog else .92) + (.10 if self.dialog else .08) * progress)))
        Gtk.Overlay.do_snapshot(self, snapshot)
        snapshot.pop()
        snapshot.restore()


class MotionDeck(Gtk.Overlay):
    """One live scene plus one short, inert outgoing scene. Never queues navigation."""
    __gtype_name__ = 'RtxForgeMotionDeck'

    def __init__(self):
        super().__init__(hexpand=True, vexpand=True)
        self.current = None
        self.outgoing = None
        self._exit = None

    def show_scene(self, scene, animate, preferences):
        if self._exit:
            self._exit.pause()
            self._exit = None
        if self.outgoing:
            self.remove_overlay(self.outgoing)
            self.outgoing = None
        previous = self.current
        self.current = scene
        if previous and animate and enabled(scene, preferences):
            previous.set_sensitive(False)
            previous.set_can_target(False)
            self.outgoing = previous
            def opacity(value):
                previous.set_opacity(value)
            self._exit = Adw.TimedAnimation.new(self, 1, 0, MOTION['exit_ms'], Adw.CallbackAnimationTarget.new(opacity))
            self._exit.set_easing(Adw.Easing.EASE_OUT_QUAD)
            def done(*_):
                if self.outgoing is previous:
                    self.remove_overlay(previous)
                    self.outgoing = None
                    self._exit = None
            self._exit.connect('done', done)
            self._exit.play()
        elif previous:
            self.remove_overlay(previous)
        self.add_overlay(scene)
        self.set_measure_overlay(scene, True)


class MotionSelection(Gtk.Overlay):
    """A selection pill below the foreground; retained channel state survives page rebuilds."""
    __gtype_name__ = 'RtxForgeMotionSelection'

    def __init__(self, state, line, selected, preferences, color, surface=None):
        super().__init__(halign=line.get_halign(), valign=line.get_valign())
        self.set_overflow(Gtk.Overflow.VISIBLE)
        self.state, self.selected, self.preferences = state, selected, preferences
        self.color = Gdk.RGBA()
        self.color.parse(color)
        self.surface = Gdk.RGBA() if surface else None
        if self.surface is not None:
            self.surface.parse(surface)
        self._base_rects = []
        self._animations = []
        self._channels = {}
        self._y = self._height = 0
        self._target_bounds = None
        self._generation = state.get('generation', 0) + 1
        state['generation'] = self._generation
        for css in ('gm-tabs', 'gm-segments', 'gm-panel'):
            if line.has_css_class(css):
                line.remove_css_class(css)
                self.add_css_class(css)
        self.add_css_class('gm-slider')
        self.set_child(line)
        self.connect('map', self._map)
        self.connect('unmap', self._unmap)

    def _unmap(self, *_):
        for animation in self._animations:
            animation.pause()
        self._animations.clear()

    def _map(self, *_):
        # Map precedes the final allocation on some compositors; one idle reads settled bounds.
        GLib.idle_add(self._target)

    def _target(self):
        if not self.get_mapped() or self.state['generation'] != self._generation:
            return GLib.SOURCE_REMOVE
        ok, bounds = self.selected.compute_bounds(self)
        if not ok or bounds.get_width() <= 0 or bounds.get_height() <= 0:
            return GLib.SOURCE_REMOVE
        target_bounds = (bounds.get_x(), bounds.get_y(), bounds.get_width(), bounds.get_height(), self.get_width())
        if target_bounds == self._target_bounds:
            return GLib.SOURCE_REMOVE
        self._target_bounds = target_bounds
        self._base_rects.clear()
        child = self.get_child().get_first_child()
        while child is not None:
            valid, base = child.compute_bounds(self)
            if valid:
                rounded = Gsk.RoundedRect()
                rounded.init_from_rect(base, base.get_height() / 2)
                self._base_rects.append((base, rounded))
            child = child.get_next_sibling()
        for animation in self._animations:
            animation.pause()
        self._animations.clear()
        self._y, self._height = bounds.get_y(), bounds.get_height()
        targets = {'x': bounds.get_x(), 'width': bounds.get_width()}
        for key, value in targets.items():
            if key not in self.state or not enabled(self, self.preferences):
                self.state[key], self.state[key + '_velocity'] = value, 0
                continue
            def update(current, key=key):
                if self.state['generation'] == self._generation:
                    self.state[key] = current
                    active = self._channels.get(key)
                    if active is not None:
                        self.state[key + '_velocity'] = active.get_velocity()
                    self.queue_draw()
            params = Adw.SpringParams.new(MOTION['focus_damping'], 1, (2 * math.pi / (FOCUS_MS / 1000)) ** 2)
            animation = Adw.SpringAnimation.new(self, self.state[key], value, params, Adw.CallbackAnimationTarget.new(update))
            animation.set_initial_velocity(self.state.get(key + '_velocity', 0))
            self._channels[key] = animation
            self._animations.append(animation)
            animation.play()
        self.queue_draw()
        return GLib.SOURCE_REMOVE

    def do_snapshot(self, snapshot):
        # Overlay's native layout manager owns allocation. Read its final child bounds
        # here; map-time idle can run before text/CSS has its final allocation.
        self._target()
        if self.surface is not None:
            for rect, rounded in self._base_rects:
                snapshot.push_rounded_clip(rounded)
                snapshot.append_color(self.surface, rect)
                snapshot.pop()
        if not enabled(self, self.preferences):
            ok, bounds = self.selected.compute_bounds(self)
            if ok:
                self.state.update(x=bounds.get_x(), width=bounds.get_width())
                self._y, self._height = bounds.get_y(), bounds.get_height()
        if self._height > 0:
            rect = Graphene.Rect().init(self.state.get('x', 0), self._y, max(0, self.state.get('width', 0)), self._height)
            rounded = Gsk.RoundedRect()
            rounded.init_from_rect(rect, self._height / 2)
            snapshot.push_rounded_clip(rounded)
            snapshot.append_color(self.color, rect)
            snapshot.pop()
        Gtk.Overlay.do_snapshot(self, snapshot)


def selection(states, key, line, selected, preferences, color, surface=None):
    return MotionSelection(states.setdefault(key, {}), line, selected, preferences, color, surface)
