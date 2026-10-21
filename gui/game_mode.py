"""Game Mode: the controller-first interface, as in the Windows build.

The approved design (MagicPath radiant-rock-8795) in GTK: a full-screen view
over the same library, engine, artwork and accents as the desktop.

  header   brand (main menu) · Library  Presets  Settings
  body     the current page (Library, Game Details, Presets, Settings)
  footer   controller / keyboard hints
  modal    one dialog at a time; it keeps focus and restores it on close

Every write goes through the desktop's review → execute path (GameModeFlow
speaks the same interface as the desktop operation dialog), so nothing is
written before the review is confirmed.
"""
from pathlib import Path
import time

from gi.repository import Gdk, Gio, GLib, Gtk, Pango

import controller_input
import game_notes
import library_media
import ui_colors
import user_messages
from operation_scope import operation_targets, ScopeError
import mfg_choice
import overview_facts

ACCENT = '#76b900'
ACCENT_INK = '#151c07'
NO_ACCENT = '#b4b4b4'

# Prototype tokens (.rf-prototype). Night is the Game Mode default.
THEMES = {
    'night': dict(window='#080808', view='#0f0f0f', panel='#171717', card='#252525', fg='#f2f2f2', muted='#c5c5c5',
                  focus='#fafafa', danger='#ffc1c6', danger_bg='#4b2328', line='#454545', active='#505050',
                  active_fg='#ffffff', segment='#575757', row_focus='#414141', disabled='#2a2a2a',
                  disabled_fg='#9fa2a8', dlss='#363636', dlss_ink='#f2f2f2', dlss_border='#888888'),
    'dark': dict(window='#242424', view='#2a2a2a', panel='#303030', card='#383838', fg='#f2f2f2', muted='#c5c5c5',
                 focus='#fafafa', danger='#ffc1c6', danger_bg='#4b2328', line='#454545', active='#505050',
                 active_fg='#ffffff', segment='#575757', row_focus='#414141', disabled='#333333',
                 disabled_fg='#9fa2a8', dlss='#474747', dlss_ink='#ffffff', dlss_border='#999999'),
    'light': dict(window='#f5f5f5', view='#fafafa', panel='#ebebeb', card='#ffffff', fg='#222222', muted='#555555',
                  focus='#222222', danger='#8b2029', danger_bg='#f6dce0', line='#cecece', active='#d2d2d2',
                  active_fg='#222222', segment='#d4d4d4', row_focus='#dedede', disabled='#e5e5e5',
                  disabled_fg='#666666', dlss='#ffffff', dlss_ink='#222222', dlss_border='#707070'),
}
PAGES = (('library', 'Library'), ('presets', 'Presets'), ('settings', 'Settings'))
SECTIONS = ('Overview', 'Features', 'DLSS Files', 'Tools', 'Appearance', 'Notes')
SETTINGS_SECTIONS = ('Gaming Mode', 'Appearance', 'Library', 'Controller', 'Keyboard', 'System')
MULTIPLIERS = ('auto', 0, 2, 3, 4, 5, 6)


class Theme:
    """Palette and the prototype's --unit (26 px; 22 ≤1500 wide, 20 ≤1050, 46 ≥3000)."""

    def __init__(self, name, scale='auto'):
        self.name = name if name in THEMES else 'night'
        self.c = THEMES[self.name]
        self.scale = scale
        self.unit = 26
        self.compact = False

    @property
    def light(self):
        return self.name == 'light'

    def resize(self, width, height):
        unit = 46 if width >= 3000 else 20 if width <= 1050 else 22 if width <= 1500 else 26
        compact = height <= 800 and width <= 2000
        changed = (unit, compact) != (self.unit, self.compact)
        self.unit, self.compact = unit, compact
        return changed

    def px(self, value):
        return round(value * self.unit / 26)

    def em(self, value):
        return round(self.unit * value, 1)

    def game_colors(self, accent):
        """Per-game roles: accent, title, tint, pill, ink, tint text."""
        accent = accent or NO_ACCENT
        view, panel = self.c['view'], self.c['panel']
        title = ui_colors.readable(accent, view) if self.light else ui_colors.vibrant_readable(accent, view, 4.5)
        tint = ui_colors.mix(accent, panel, 0.18 if self.light else 0.24)
        ink = ui_colors.readable(ui_colors.mix('#000000', accent, 0.82), accent)
        return dict(accent=accent, title=title, tint=tint, pill=accent, ink=ink, tint_text=ui_colors.readable(accent, tint))


def stylesheet(t):
    """Everything is scoped under .gm so the desktop is never restyled."""
    c, px, em = t.c, t.px, t.em
    return f'''
.gm {{ background: {c['window']}; color: {c['fg']}; font-size: {em(0.85)}px; }}
.gm label {{ color: inherit; }}
.gm .gm-view {{ background: {c['view']}; }}
.gm .gm-header, .gm .gm-footer {{ background: {c['window']}; }}
.gm .gm-h1 {{ font-size: {em(1.62)}px; font-weight: 700; letter-spacing: -0.5px; }}
.gm .gm-h1.compact {{ font-size: {em(1.18)}px; }}
.gm .gm-h2 {{ font-size: {em(1.27)}px; font-weight: 600; letter-spacing: -0.3px; }}
.gm .gm-h3 {{ font-size: {em(1.06)}px; font-weight: 600; }}
.gm .gm-p {{ color: {c['muted']}; font-size: {em(0.85)}px; }}
.gm .gm-small {{ color: {c['muted']}; font-size: {em(0.77)}px; }}
.gm .gm-strong {{ font-weight: 600; font-size: {em(0.96)}px; }}
.gm .gm-brand-title {{ font-family: "Bakbak One"; font-size: {em(1.4 if t.compact else 1.62)}px; }}
.gm button {{ background: none; box-shadow: none; border: none; color: {c['fg']}; min-height: 0; min-width: 0; padding: 0;
  outline-color: {c['focus']}; outline-style: solid; outline-width: 0; transition: none; }}
.gm button:focus-visible {{ outline-width: {px(4)}px; outline-offset: {px(4)}px; }}
.gm button.gm-btn {{ border-radius: 999px; padding: {px(14)}px {px(24)}px; min-height: {px(60 if not t.compact else 48) - px(28)}px;
  font-size: {em(0.85)}px; font-weight: 550; background: {c['card']}; color: {c['fg']}; }}
.gm button.gm-btn.gm-primary {{ background: {ACCENT}; color: {ACCENT_INK}; font-weight: 650; }}
.gm button.gm-btn.gm-danger {{ background: {c['danger_bg']}; color: {c['danger']}; }}
.gm button.gm-btn.gm-dlss {{ background: {c['dlss']}; color: {c['dlss_ink']}; border: {px(2)}px solid {c['dlss_border']}; }}
.gm button.gm-btn.gm-quiet {{ background: none; padding: {px(12)}px {px(16)}px; }}
.gm button.gm-btn.gm-active {{ background: {c['active']}; color: {c['active_fg']}; }}
.gm button.gm-btn.gm-ghost {{ background: none; }}
.gm button.gm-btn:hover {{ background-image: image(alpha(currentColor,0.08)); }}
.gm button.gm-btn:disabled, .gm button.gm-rowbtn:disabled, .gm button.gm-tile:disabled {{ background: {c['disabled']}; color: {c['disabled_fg']}; border-color: transparent; }}
.gm button.gm-btn.gm-quiet:disabled, .gm button.gm-btn.gm-ghost:disabled {{ background: none; }}
.gm .gm-tabs {{ background: {c['panel']}; border-radius: 999px; padding: {px(8)}px; }}
.gm .gm-tabs button.gm-btn {{ padding: {px(8)}px {px(26)}px; min-height: {px(54) - px(16)}px; font-size: {em(0.92)}px; }}
.gm .gm-segments {{ background: {c['card']}; border-radius: 999px; padding: {px(4)}px; }}
.gm .gm-segments.gm-panel {{ background: {c['panel']}; }}
.gm .gm-segments button {{ border-radius: 999px; padding: {px(10)}px {px(22)}px; min-height: {px(54 if not t.compact else 40) - px(20)}px; font-size: {em(0.85)}px; font-weight: 550; }}
.gm .gm-segments button:focus-visible {{ outline-offset: -{px(6)}px; }}
.gm .gm-segments button.on {{ background: {c['segment']}; color: {c['active_fg']}; }}
.gm .gm-segments.gm-panel button.on {{ background: {c['card']}; }}
.gm .gm-surface {{ background: {c['panel']}; border-radius: {px(16)}px; }}
.gm .gm-pill {{ background: {c['panel']}; border-radius: 999px; padding: {px(10 if not t.compact else 7)}px {px(20)}px; font-size: {em(0.85)}px; }}
.gm .gm-group {{ background: {c['panel']}; border-radius: {px(16)}px; }}
.gm .gm-group.gm-on-card {{ background: {c['card']}; }}
.gm .gm-sep {{ background: {c['line']}; min-height: 1px; }}
.gm button.gm-rowbtn {{ border-radius: {px(12)}px; padding: {px(24 if not t.compact else 16)}px {px(30)}px; }}
.gm button.gm-rowbtn:focus-visible {{ outline-offset: -{px(8)}px; background: {c['row_focus']}; }}
.gm button.gm-rowbtn.gm-danger-row {{ color: {c['danger']}; }}
.gm button.gm-rowbtn:disabled {{ background: none; }}
.gm .gm-value {{ color: {c['muted']}; font-size: {em(0.85)}px; }}
.gm .gm-stepper-value {{ font-size: {em(1.18)}px; font-weight: 700; }}
.gm .gm-step {{ background: {c['card']}; border-radius: {px(8)}px; padding: {px(8)}px; }}
.gm .gm-key {{ background: {c['card']}; border-radius: {px(6)}px; padding: {px(4)}px {px(10)}px; min-width: {px(32) - px(20)}px; min-height: {px(32) - px(8)}px; font-weight: 650; font-size: {em(0.72)}px; }}
.gm .gm-badge {{ border-radius: 999px; padding: {px(7)}px {px(12)}px; font-weight: 650; font-size: {em(0.62)}px; }}
.gm .gm-badge.gm-big {{ font-size: {em(0.74)}px; }}
.gm .gm-badge-ready {{ background: {c['panel']}; color: {c['fg']}; }}
.gm .gm-badge-skipped {{ background: {c['panel']}; color: {c['danger']}; }}
.gm .gm-badge-tested {{ background: #573d18; color: #ffe8a2; }}
.gm .gm-badge-source {{ background: {c['card']}; color: {c['fg']}; }}
.gm .gm-badge-profile {{ background: alpha(black,0.8); color: white; }}
.gm .gm-chip {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 999px; padding: {px(12)}px {px(18)}px; font-size: {em(0.76)}px; font-weight: 650; }}
.gm .gm-chip.gm-plain {{ border-color: {c['card']}; }}
.gm button.gm-gamecard {{ border-radius: {px(14)}px; }}
.gm button.gm-gamecard:focus-visible {{ outline-width: 0; }}
.gm .gm-art {{ border: {px(2)}px solid {c['line']}; border-radius: {px(12)}px; background: {c['card']}; }}
.gm button.gm-gamecard:focus-visible .gm-art {{ outline: {px(4)}px solid {c['focus']}; outline-offset: {px(5)}px; }}
.gm .gm-art-fallback {{ color: {c['muted']}; font-weight: 600; font-size: {em(0.8)}px; }}
.gm .gm-cardtitle {{ font-weight: 600; font-size: {em(0.93)}px; }}
.gm .gm-check {{ border: {px(2)}px solid {c['focus']}; background: {c['window']}; border-radius: {px(6)}px; min-width: {px(28)}px; min-height: {px(28)}px; }}
.gm button.gm-listrow {{ border-radius: 0; }}
.gm button.gm-listrow.first, .gm button.gm-listrow.first .gm-listsurface {{ border-top-left-radius: {px(16)}px; border-top-right-radius: {px(16)}px; }}
.gm button.gm-listrow.last, .gm button.gm-listrow.last .gm-listsurface {{ border-bottom-left-radius: {px(16)}px; border-bottom-right-radius: {px(16)}px; }}
.gm button.gm-listrow:focus-visible {{ outline-offset: -{px(6)}px; }}
.gm .gm-listsurface {{ background: {c['panel']}; padding: {px(16)}px {px(24)}px; }}
.gm .gm-dot {{ min-width: {px(8)}px; min-height: {px(8)}px; border-radius: 999px; border: 1.5px solid {c['muted']}; }}
.gm .gm-dot.on {{ background: {ACCENT}; border-color: {ACCENT}; }}
.gm .gm-hero-scrim {{ background-image: linear-gradient(to right, alpha({c['view']},0.82), alpha({c['view']},0.55) 38%, alpha({c['view']},0) 72%),
  linear-gradient(to bottom, alpha({c['view']},0) 30%, {c['view']}); }}
.gm .gm-poster {{ border: {px(3)}px solid {c['line']}; border-radius: {px(10)}px; background: {c['card']}; }}
.gm .gm-gametitle {{ font-family: "Bakbak One"; font-size: {em(1.35 if t.compact else 1.65)}px; }}
.gm button.gm-back {{ background: alpha(#121212,0.86); color: white; border-radius: {px(12)}px; padding: {px(10)}px {px(18)}px; font-size: {em(0.78)}px; }}
.gm button.gm-navbtn {{ border-radius: {px(12)}px; padding: {px(12)}px {px(18)}px; font-size: {em(0.88)}px; }}
.gm button.gm-navbtn.on {{ background: {c['card']}; }}
.gm button.gm-tile {{ background: {c['card']}; border-radius: {px(14)}px; padding: {px(20)}px; min-height: {px(116 if not t.compact else 90) - px(40)}px; }}
.gm .gm-swatch {{ border-radius: 999px; border: {px(3)}px solid transparent; padding: {px(4)}px; }}
.gm .gm-swatch.on {{ border-color: {c['focus']}; }}
.gm button.gm-swatch-button {{ border-radius: {px(16)}px; padding: {px(10)}px; }}
.gm textview.gm-notes, .gm textview.gm-notes text {{ background: {c['panel']}; color: {c['fg']}; }}
.gm textview.gm-notes {{ border: 1px solid {c['line']}; border-radius: {px(12)}px; padding: {px(20)}px; font-size: {em(0.9)}px; }}
.gm .gm-modal-layer {{ background: alpha(black,0.7); }}
.gm .gm-dialog {{ background: {c['panel']}; border-radius: {px(20)}px; padding: {px(40 if not t.compact else 24)}px; box-shadow: 0 {px(18)}px {px(48)}px alpha(black,0.5); }}
.gm .gm-dialog .gm-group {{ background: {c['card']}; }}
.gm .gm-dialog button.gm-btn:not(.gm-primary):not(.gm-danger) {{ background: {c['card']}; }}
.gm .gm-toast {{ background: {c['card']}; border-radius: {px(16)}px; padding: {px(14)}px {px(24)}px; }}
.gm .gm-step-poster {{ border: {px(3)}px solid {c['line']}; border-radius: {px(12)}px; background: {c['card']}; }}
.gm .gm-step-title {{ font-size: {em(1.3)}px; font-weight: 600; }}
.gm progressbar trough {{ background: {c['card']}; border-radius: {px(8)}px; min-height: {px(12)}px; }}
.gm progressbar progress {{ background: {ACCENT}; border-radius: {px(8)}px; min-height: {px(12)}px; }}
.gm .gm-mark {{ border: {px(2)}px solid {c['muted']}; border-radius: 999px; min-width: {px(30)}px; min-height: {px(30)}px; }}
.gm .gm-mark.on {{ background: {ACCENT}; border-color: {ACCENT}; color: {ACCENT_INK}; }}
.gm .gm-done-icon {{ color: {c['fg']}; }}
.gm .gm-done-icon.failed {{ color: {c['danger']}; }}
.gm scrollbar {{ opacity: 0.6; }}
'''


def accent_css(t, hexcolor):
    """Per-game states: accent only on focus or selection (neutral when idle)."""
    g = t.game_colors(hexcolor)
    name = 'gm-acc-' + hexcolor.lstrip('#')
    dark = ui_colors.readable(ui_colors.mix('#000000', g['accent'], 0.75), g['accent'])
    return name, f'''
.gm button.gm-gamecard.{name}:focus-visible .gm-art, .gm button.gm-gamecard.{name}:hover .gm-art,
.gm button.gm-gamecard.{name}.gm-selected .gm-art, .gm button.gm-listrow.{name}:focus-visible .gm-art,
.gm button.gm-listrow.{name}:hover .gm-art {{ border-color: {g['accent']}; }}
.gm button.gm-gamecard.{name}:focus-visible .gm-cardtitle, .gm button.gm-gamecard.{name}:hover .gm-cardtitle,
.gm button.gm-gamecard.{name}.gm-selected .gm-cardtitle, .gm button.gm-listrow.{name}:focus-visible .gm-rowtitle,
.gm button.gm-listrow.{name}:hover .gm-rowtitle {{ color: {g['title']}; }}
.gm .{name}.gm-selected .gm-check {{ background: {g['accent']}; border-color: {g['accent']}; color: {g['ink']}; }}
.gm button.gm-listrow.{name}.gm-selected .gm-listsurface {{ background: {g['accent']}; }}
.gm button.gm-listrow.{name}.gm-selected .gm-listsurface label {{ color: {dark}; }}
.gm button.gm-listrow.{name}.gm-selected .gm-chip {{ background: alpha(black,0.16); border-color: transparent; }}
.gm .{name} .gm-poster, .gm .{name} .gm-step-poster, .gm .{name}.gm-review-row .gm-art {{ border-color: {g['accent']}; }}
.gm .{name} .gm-gametitle, .gm .{name} .gm-step-title, .gm .{name}.gm-review-row .gm-rowtitle {{ color: {g['title']}; }}
.gm .{name} .gm-badge-source {{ background: {g['pill']}; color: {g['ink']}; }}
.gm .{name} button.gm-navbtn.on {{ background: {g['tint']}; color: {g['tint_text']}; }}
.gm .{name} progressbar progress {{ background: {g['accent']}; }}
.gm .{name}.gm-review-row .gm-badge-ready {{ background: {g['tint']}; color: {g['tint_text']}; }}
'''


class ArtPicture(Gtk.Picture):
    """Artwork at a set size (cover crop); a Gtk.Picture alone asks for the image's own size."""

    def __init__(self, width, height):
        super().__init__(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        self.size = (width, height)

    def do_measure(self, orientation, for_size):
        size = self.size[0 if orientation == Gtk.Orientation.HORIZONTAL else 1]
        return (0, 0, -1, -1) if size is None else (size, size, -1, -1)


def clear(box):
    child = box.get_first_child()
    while child is not None:
        nxt = child.get_next_sibling()
        box.remove(child)
        child = nxt


def descendants(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from descendants(child)
        child = child.get_next_sibling()


class GameMode(Gtk.Overlay):
    def __init__(self, owner, helpers):
        super().__init__()
        self.owner = owner
        self.h = helpers
        self.add_css_class('gm')
        self.theme = Theme(owner.settings.get('theme') or 'night', owner.settings.get('ui_scale', 'auto'))
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 20)
        self.accent_providers = {}
        self.layout_width, self.layout_height = 1280, 800
        # Owner-facing state (kept for the desktop window's hooks).
        self.page = 'library'
        self.game = None
        self.current = 0
        self.hint_timer = 0
        self.details_game = None
        self.section = 'Overview'
        self.settings_section = 'Gaming Mode'
        self.selecting = False
        self.selected = set()
        self.presets_expanded = False
        self.notes_status = None
        self.notes_draft = None
        self.library_focus = None
        self.pending_focus = None
        self.modals = []
        self.prompt_spec = None
        self.render_source = 0

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)
        self.page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        root.append(self.page_box)
        self.header = Gtk.CenterBox()
        self.header.add_css_class('gm-header')
        self.page_box.append(self.header)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True, hexpand=True)
        self.body.add_css_class('gm-view')
        self.page_box.append(self.body)
        self.bottom_nav = Gtk.Box(halign=Gtk.Align.CENTER, visible=False)
        self.bottom_nav.add_css_class('gm-view')
        self.page_box.append(self.bottom_nav)
        self.footer = Gtk.Box()
        self.footer.add_css_class('gm-footer')
        root.append(self.footer)
        self.hints = Gtk.Box(valign=Gtk.Align.CENTER)
        self.footer.append(self.hints)

        self.modal_layer = Gtk.Box(visible=False, hexpand=True, vexpand=True)
        self.modal_layer.add_css_class('gm-modal-layer')
        self.add_overlay(self.modal_layer)
        self.toast_box = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE, halign=Gtk.Align.CENTER,
                                      valign=Gtk.Align.END, can_target=False)
        self.toast_label = Gtk.Label(wrap=True, max_width_chars=60)
        toast = Gtk.Box()
        toast.add_css_class('gm-toast')
        toast.append(self.toast_label)
        self.toast_box.set_child(toast)
        self.add_overlay(self.toast_box)
        self.toast_source = 0
        self.apply_theme()

    # ---------------- theme ----------------

    def apply_theme(self):
        self.theme = Theme(self.owner.settings.get('theme') or 'night', self.owner.settings.get('ui_scale', 'auto'))
        self.theme.resize(self.layout_width, self.layout_height)
        self.provider.load_from_data(stylesheet(self.theme).encode())
        for provider in self.accent_providers.values():
            Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(), provider)
        self.accent_providers = {}

    def accent_class(self, game):
        """The CSS class carrying this game's accent roles (artwork-derived or custom)."""
        accent = self.owner._ensure_game_accent(game) if game else None
        hexcolor = '#' + accent[4:] if accent and accent.startswith('art-') else NO_ACCENT
        name, css = accent_css(self.theme, hexcolor)
        if name not in self.accent_providers:
            provider = Gtk.CssProvider()
            provider.load_from_data(css.encode())
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 21)
            self.accent_providers[name] = provider
        return name

    # ---------------- owner hooks ----------------

    def resize(self, width, height=None):
        if width < 400:
            return
        height = height or self.layout_height
        changed = (width, height) != (self.layout_width, self.layout_height)
        self.layout_width, self.layout_height = width, height
        if self.theme.resize(width, height):
            self.provider.load_from_data(stylesheet(self.theme).encode())
            for provider in self.accent_providers.values():
                Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(), provider)
            self.accent_providers = {}
            changed = True
        if changed:
            self.schedule_render()

    def schedule_render(self):
        if self.render_source:
            return
        def run():
            self.render_source = 0
            if not self.modals:
                self.render(keep_focus=True)
            return False
        self.render_source = GLib.timeout_add(60, run)

    def refresh(self):
        if self.details_game:
            match = next((g for g in self.owner.games if g['game'] == self.details_game['game']), None)
            if match:
                self.details_game = self.game = match
            elif self.page == 'details':
                self.page, self.details_game, self.game = 'library', None, None
        self.selected &= {g['game'] for g in self.owner.games}
        if not self.modals:
            self.render(keep_focus=True)

    def artwork_updated(self, game):
        if self.get_mapped():
            self.schedule_render()

    def apply_navigation_preferences(self):
        # Called on every display check; only a moved navigation bar needs a render.
        position = self.owner.settings.get('navigation_position', 'top')
        if position != getattr(self, 'navigation_position', position) and not self.modals:
            self.render(keep_focus=True)
        self.navigation_position = position

    def panel_navigation(self, dialog):
        return None   # Game Mode dialogs carry their own Back

    def open(self, target):
        if target == 'menu':
            self.open_main_menu()
            return
        target = {'dlss': 'settings', 'dashboard': 'library'}.get(target, target)
        self.close_all_modals()
        self.page = target
        self.render()

    # ---------------- helpers ----------------

    def save_settings(self):
        if not self.owner.options.demo:
            library_media.save_settings(self.owner.service.config, self.owner.settings)

    def toast(self, text):
        self.toast_label.set_text(str(text))
        self.toast_box.set_margin_bottom(self.theme.px(24) + self.footer.get_height())
        self.toast_box.set_reveal_child(True)
        if self.toast_source:
            GLib.source_remove(self.toast_source)
        self.toast_source = GLib.timeout_add(4000, self._hide_toast)

    def _hide_toast(self):
        self.toast_source = 0
        self.toast_box.set_reveal_child(False)
        return False

    def label(self, text, *classes, wrap=False, xalign=0.0, lines=0):
        widget = Gtk.Label(label=str(text), xalign=xalign, wrap=wrap)
        if wrap:
            widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if lines:
            widget.set_lines(lines)
            widget.set_ellipsize(Pango.EllipsizeMode.END)
        elif not wrap:
            widget.set_ellipsize(Pango.EllipsizeMode.END)
        for css in classes:
            widget.add_css_class(css)
        return widget

    def icon(self, name, size=None):
        image = Gtk.Image.new_from_icon_name(name)
        image.set_pixel_size(size or self.theme.px(20))
        return image

    def content(self, text, icon=None):
        """Button content: label with an optional leading icon (button glyphs preference)."""
        box = Gtk.Box(spacing=self.theme.px(12), halign=Gtk.Align.CENTER)
        if icon and self.owner.settings.get('button_glyphs', True):
            box.append(self.icon(icon, self.theme.px(18)))
        caption = self.label(text)
        caption.set_ellipsize(Pango.EllipsizeMode.NONE)
        box.append(caption)
        return box

    def key(self, widget, name):
        widget._gm_key = name
        return widget

    def button(self, text, action, kind='card', icon=None, enabled=True, key=None, halign=None):
        child = text if isinstance(text, Gtk.Widget) else self.content(text, icon)
        widget = Gtk.Button(child=child, sensitive=enabled)
        widget.add_css_class('gm-btn')
        if kind != 'card':
            widget.add_css_class('gm-' + kind)
        if halign is not None:
            widget.set_halign(halign)
        if action:
            widget.connect('clicked', lambda *_: action())
        if key:
            self.key(widget, key)
        return widget

    def segments(self, items, selected, pick, panel=False):
        box = Gtk.Box(spacing=self.theme.px(4), halign=Gtk.Align.START, valign=Gtk.Align.CENTER)
        box.add_css_class('gm-segments')
        if panel:
            box.add_css_class('gm-panel')
        for item in items:
            key, text, enabled = item[0], item[1], (item[2] if len(item) > 2 else True)
            child = item[3] if len(item) > 3 else self.label(text)
            if isinstance(child, Gtk.Label):
                child.set_ellipsize(Pango.EllipsizeMode.NONE)
            control = Gtk.Button(child=child, sensitive=enabled)
            if key == selected:
                control.add_css_class('on')
            control.connect('clicked', lambda *_, key=key: pick(key))
            self.key(control, 'seg-' + str(key))
            box.append(control)
        return box

    def group(self, rows, on_card=False):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class('gm-group')
        if on_card:
            box.add_css_class('gm-on-card')
        for index, row in enumerate(rows):
            if index:
                sep = Gtk.Box()
                sep.add_css_class('gm-sep')
                box.append(sep)
            box.append(row)
        return box

    def preference(self, title, description=None, right=None, inset=True):
        """A row's content; inset=False inside a row button, which brings its own padding."""
        t = self.theme
        line = Gtk.Box(spacing=t.px(28))
        if inset:
            line.set_margin_start(t.px(30))
            line.set_margin_end(t.px(30))
            line.set_margin_top(t.px(16 if t.compact else 26))
            line.set_margin_bottom(t.px(16 if t.compact else 26))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(8), hexpand=True, valign=Gtk.Align.CENTER)
        text.append(self.label(title, 'gm-strong', wrap=True))
        if description:
            text.append(self.label(description, 'gm-p', wrap=True))
        line.append(text)
        if right is not None:
            right.set_valign(Gtk.Align.CENTER)
            line.append(right)
        return line

    def row_button(self, title, value=None, action=None, danger=False, description=None, icon=None, enabled=True, key=None):
        t = self.theme
        line = Gtk.Box(spacing=t.px(22))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(8), hexpand=True, valign=Gtk.Align.CENTER)
        head = Gtk.Box(spacing=t.px(12))
        if icon and self.owner.settings.get('button_glyphs', True):
            head.append(self.icon(icon, t.px(18)))
        head.append(self.label(title, 'gm-strong'))
        text.append(head)
        if description:
            text.append(self.label(description, 'gm-p', wrap=True))
        line.append(text)
        if value is not None:
            shown = self.label(value, 'gm-value')
            shown.set_valign(Gtk.Align.CENTER)
            line.append(shown)
            line._value = shown
        line.append(self.icon('go-next-symbolic', t.px(16)))
        widget = Gtk.Button(child=line, sensitive=enabled, hexpand=True)
        widget.add_css_class('gm-rowbtn')
        if danger:
            widget.add_css_class('gm-danger-row')
        if action:
            widget.connect('clicked', lambda *_: action())
        if key:
            self.key(widget, key)
        return widget

    def stepper(self, title, description, value, adjust, enabled=True, key=None):
        """A whole-row focus target; Left/Right (D-pad) adjust, the − / + steps click."""
        t = self.theme
        shown = self.label(value(), 'gm-stepper-value', xalign=0.5)
        shown.set_size_request(t.px(90), -1)
        def step(delta):
            adjust(delta)
            shown.set_text(value())
        controls = Gtk.Box(spacing=t.px(28), valign=Gtk.Align.CENTER)
        for icon, delta in (('list-remove-symbolic', -1), ('list-add-symbolic', 1)):
            box = Gtk.Box(valign=Gtk.Align.CENTER)
            box.add_css_class('gm-step')
            box.append(self.icon(icon, t.px(16)))
            if enabled:
                click = Gtk.GestureClick()
                click.connect('released', lambda *_a, delta=delta: step(delta))
                box.add_controller(click)
            controls.append(box)
            if delta < 0:
                controls.append(shown)
        row = self.preference(title, description, controls, inset=False)
        widget = Gtk.Button(child=row, sensitive=enabled, hexpand=True)
        widget.add_css_class('gm-rowbtn')
        widget.set_margin_start(0)
        widget._gm_adjust = step
        if key:
            self.key(widget, key)
        return widget

    def choice(self, title, description, keys, captions, get, setter):
        """A choice row: Select cycles forward, Left/Right step through the choices."""
        def caption():
            value = get()
            return captions[keys.index(value)] if value in keys else captions[0]
        def step(delta):
            value = get()
            index = (keys.index(value) if value in keys else 0) + delta
            setter(keys[index % len(keys)])
            self.save_settings()
            self.render(keep_focus=True)
        row = self.row_button(title, caption(), lambda: step(1), description=description, key='choice-' + title)
        row._gm_adjust = step
        return row

    def keycap(self, text):
        cap = self.label(text, 'gm-key', xalign=0.5)
        cap.set_valign(Gtk.Align.CENTER)
        return cap

    def badge(self, text, css, icon=None, big=False):
        box = Gtk.Box(spacing=self.theme.px(6), halign=Gtk.Align.START, valign=Gtk.Align.CENTER)
        box.add_css_class('gm-badge')
        box.add_css_class(css)
        if big:
            box.add_css_class('gm-big')
        if icon:
            box.append(self.icon(icon, self.theme.px(14)))
        box.append(self.label(text))
        return box

    def picture(self, path, width, height, css='gm-art'):
        """Artwork that fills a fixed frame (cover); width None fills the row."""
        frame = Gtk.Box(halign=Gtk.Align.FILL if width is None else Gtk.Align.START, valign=Gtk.Align.START)
        frame.add_css_class(css)
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        # The frame's border sits inside the requested size.
        border = 2 * self.theme.px({'gm-art': 2, 'gm-poster': 3, 'gm-step-poster': 3}.get(css, 0))
        picture = ArtPicture(None if width is None else max(1, width - border), max(1, height - border))
        picture.set_hexpand(width is None)
        if path:
            try:
                picture.set_filename(str(path))
            except Exception:
                pass
        frame.append(picture)
        frame._picture = picture
        return frame

    # ---------------- rendering ----------------

    def render(self, index=None, keep_focus=False):
        focus_key = self.focus_key() if keep_focus else None
        self.render_header()
        clear(self.body)
        page = self.page
        if page == 'details' and self.details_game:
            content = self.build_details(self.details_game)
        elif page == 'presets':
            content = self.build_presets()
        elif page == 'settings':
            content = self.build_settings()
        else:
            self.page = 'library'
            content = self.build_library()
        self.body.append(content)
        self.update_prompts(force=True)
        target = self.pending_focus or focus_key
        self.pending_focus = None
        GLib.idle_add(self.restore_focus, target)

    def focus_key(self):
        widget = self.owner.get_focus()
        while widget is not None:
            if getattr(widget, '_gm_key', None):
                return widget._gm_key
            widget = widget.get_parent()
        return None

    def find_key(self, scope, key):
        for widget in descendants(scope):
            if getattr(widget, '_gm_key', None) == key:
                return widget
        return None

    def restore_focus(self, key):
        if self.modals:
            return False
        target = self.find_key(self.page_box, key) if key else None
        if target is None or not target.get_sensitive():
            target = self.first_focus or self.first_focusable(self.body)
        if target is not None:
            target.grab_focus()
        self.first_focus = None
        return False

    first_focus = None

    def first_focusable(self, scope):
        for widget in descendants(scope):
            if isinstance(widget, (Gtk.Button, Gtk.TextView)) and widget.get_sensitive() and widget.get_visible() and widget.get_mapped():
                return widget
        return None

    def render_header(self):
        t = self.theme
        self.header.set_size_request(-1, t.px(80 if t.compact else 104))
        for side in ('start', 'end'):
            getattr(self.header, 'set_margin_' + side)(t.px(56))
        brand = Gtk.Box(spacing=t.px(16))
        mark = self.h.make_brand_icon(t.px(48 if t.compact else 64))
        brand.append(mark)
        brand.append(self.label('rtxForge', 'gm-brand-title'))
        brand_button = self.button(brand, self.open_main_menu, 'ghost', key='brand')
        brand_button.update_property([Gtk.AccessibleProperty.LABEL], ['rtxForge main menu'])
        brand_button.set_valign(Gtk.Align.CENTER)
        self.header.set_start_widget(brand_button)
        tabs = Gtk.Box(spacing=t.px(8), halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        tabs.add_css_class('gm-tabs')
        for key, title in PAGES:
            active = self.page == key or (key == 'library' and self.page == 'details')
            tabs.append(self.button(title, lambda key=key: self.open(key), 'active' if active else 'ghost', key='tab-' + key))
        bottom = self.owner.settings.get('navigation_position', 'top') == 'bottom'
        clear(self.bottom_nav)
        self.bottom_nav.set_visible(bottom)
        if bottom:
            self.header.set_center_widget(None)
            self.bottom_nav.set_margin_top(t.px(8))
            self.bottom_nav.set_margin_bottom(t.px(18))
            self.bottom_nav.append(tabs)
        else:
            self.header.set_center_widget(tabs)

    def update_prompts(self, force=False):
        t = self.theme
        keyboard = getattr(self.owner, 'input_kind', 'keyboard') != 'controller'
        family = self.owner.settings.get('controller_glyphs', 'auto')
        if family == 'auto':
            family = getattr(getattr(self.owner, 'controller', None), 'family', 'xbox') or 'xbox'
        glyphs = controller_input.GLYPHS.get(family, controller_input.GLYPHS['generic'])
        accept_label = 'Game Details' if self.page == 'library' and not self.modals and not self.selecting else 'Select'
        spec = (keyboard, family, accept_label, bool(self.modals), t.unit)
        if spec == self.prompt_spec and not force:
            return
        self.prompt_spec = spec
        clear(self.hints)
        self.hints.set_spacing(t.px(30))
        self.footer.set_size_request(-1, t.px(64 if t.compact else 90))
        for side in ('start', 'end'):
            getattr(self.hints, 'set_margin_' + side)(t.px(56))
        entries = [(('Enter' if keyboard else glyphs[0]), accept_label, 'accept'), (('Esc' if keyboard else glyphs[1]), 'Back', 'back')]
        if not self.modals:
            entries.append((('Ctrl+L' if keyboard else glyphs[2]), 'Library', 'search'))
        for key, text, action in entries:
            pair = Gtk.Box(spacing=t.px(10))
            pair.append(self.keycap(key))
            pair.append(self.label(text))
            hint = Gtk.Button(child=pair, focusable=False)
            hint.connect('clicked', lambda *_, action=action: self.navigate(action))
            self.hints.append(hint)
        self.wake_hints()

    def wake_hints(self):
        self.hints.set_opacity(1)
        if self.hint_timer:
            GLib.source_remove(self.hint_timer)
            self.hint_timer = 0
        if self.owner.settings.get('controller_hints', 'always') == 'auto':
            self.hint_timer = GLib.timeout_add(3500, self._hide_hints)

    def _hide_hints(self):
        self.hint_timer = 0
        self.hints.set_opacity(0)
        return False

    # ---------------- input ----------------

    def navigate(self, action):
        self.wake_hints()
        self.owner.set_focus_visible(True)
        focus = self.owner.get_focus()
        if action in ('up', 'down', 'left', 'right'):
            adjust = getattr(focus, '_gm_adjust', None)
            if action in ('left', 'right') and adjust:
                adjust(1 if action == 'right' else -1)
                return
            scope = self.modals[-1]['dialog'] if self.modals else self.page_box
            direction = {'up': Gtk.DirectionType.UP, 'down': Gtk.DirectionType.DOWN,
                         'left': Gtk.DirectionType.LEFT, 'right': Gtk.DirectionType.RIGHT}[action]
            inside = focus is not None and (focus is scope or focus.is_ancestor(scope))
            if not inside or not scope.child_focus(direction):
                if not inside:
                    target = self.first_focusable(scope)
                    if target:
                        target.grab_focus()
            return
        if action == 'accept':
            if isinstance(focus, Gtk.Button) and focus.get_sensitive():
                focus.emit('clicked')
            elif isinstance(focus, Gtk.TextView):
                focus.grab_focus()
            return
        if action == 'back':
            self.back()
        elif action == 'search' and not self.modals:
            self.open('library')
        elif action == 'settings' and not self.modals:
            self.open('settings')
        elif action == 'menu' and not self.modals:
            self.open_main_menu()
        elif action in ('previous', 'next') and not self.modals:
            self.cycle_tab(-1 if action == 'previous' else 1)
        elif action == 'select':
            self.toggle_select_focused(focus)

    def cycle_tab(self, direction):
        order = [key for key, _ in PAGES]
        current = order.index('library' if self.page == 'details' else self.page) if self.page in order or self.page == 'details' else 0
        target = order[(current + direction) % len(order)]
        self.pending_focus = 'tab-' + target
        self.open(target)

    def back(self):
        if self.modals:
            self.modals[-1]['on_back']()
            return
        if self.page == 'details':
            self.close_details()
        elif self.page in ('presets', 'settings'):
            self.open('library')
        elif self.selecting:
            self.selecting = False
            self.selected.clear()
            self.render(keep_focus=True)

    # ---------------- modals ----------------

    def show_modal(self, title, content, actions, on_back, width=1100, focus=None):
        t = self.theme
        restore = self.owner.get_focus()
        dialog = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(18 if t.compact else 26),
                         halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        dialog.add_css_class('gm-dialog')
        dialog.set_size_request(min(t.px(width), max(320, self.layout_width - t.px(96))), -1)
        if title:
            dialog.append(self.label(title, 'gm-h2'))
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                    max_content_height=max(240, self.layout_height - t.px(320)))
        scroll.set_child(content)
        dialog.append(scroll)
        row = Gtk.Box(spacing=t.px(18), halign=Gtk.Align.END)
        for action in actions:
            row.append(action)
        if actions:
            dialog.append(row)
        layer = Gtk.Box(hexpand=True, vexpand=True, halign=Gtk.Align.FILL, valign=Gtk.Align.FILL)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(layer, 'set_margin_' + side)(t.px(48))
        center = Gtk.CenterBox(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        center.set_center_widget(dialog)
        layer.append(center)
        modal = {'layer': layer, 'dialog': dialog, 'on_back': on_back, 'restore': restore, 'actions': row, 'scroll': scroll}
        if self.modals:
            self.modals[-1]['layer'].set_visible(False)
        self.modal_layer.append(layer)
        self.modal_layer.set_visible(True)
        self.page_box.set_sensitive(False)
        self.modals.append(modal)
        self.update_prompts()
        def first():
            target = focus if focus is not None and focus.get_sensitive() else self.first_focusable(dialog)
            if target is not None:
                target.grab_focus()
            return False
        GLib.idle_add(first)
        return modal

    def close_modal(self, modal=None):
        if not self.modals:
            return
        modal = modal or self.modals[-1]
        if modal not in self.modals:
            return
        self.modals.remove(modal)
        self.modal_layer.remove(modal['layer'])
        if self.modals:
            self.modals[-1]['layer'].set_visible(True)
        else:
            self.modal_layer.set_visible(False)
            self.page_box.set_sensitive(True)
        self.update_prompts()
        restore = modal['restore']
        if restore is not None and restore.get_root() is not None and restore.get_sensitive():
            restore.grab_focus()
        elif not self.modals:
            target = self.first_focusable(self.body)
            if target:
                target.grab_focus()

    def close_all_modals(self):
        while self.modals:
            self.close_modal()

    # ---------------- main menu ----------------

    def open_main_menu(self):
        if self.modals:
            return
        rows = [
            self.row_button('Library', action=lambda: (self.close_modal(), self.open('library'))),
            self.row_button('Packages', action=lambda: (self.close_modal(), self.owner.show_packages())),
            self.row_button('Refresh library', action=lambda: (self.close_modal(), self.refresh_library()), icon='view-refresh-symbolic'),
            self.row_button('Desktop UI', action=lambda: (self.close_modal(), self.owner.set_input_surface(False))),
            self.row_button('Exit App', action=self.confirm_exit, danger=True),
        ]
        self.show_modal('rtxForge', self.group(rows, True), [self.button('Back', self.close_modal)], self.close_modal, 900)

    def confirm_exit(self):
        stay = self.button('Stay', self.close_modal)
        leave = self.button('Exit App', self.owner.close, 'danger')
        self.show_modal('Exit rtxForge?', self.label('Game Mode closes. Your library and settings are saved.', 'gm-p', wrap=True),
                        [stay, leave], self.close_modal, 760, stay)

    def refresh_library(self):
        if self.owner.options.demo:
            self.toast('Preview mode · the library is a fixture.')
            return
        self.toast('Refreshing your library…')
        self.owner.scan()

    # ---------------- library ----------------

    def filtered_games(self):
        mode = self.owner.settings.get('library_filter', 'available')
        games = [g for g in self.owner.games
                 if mode == 'all' or (mode == 'installed' and g.get('installed')) or (mode not in ('all', 'installed') and not g.get('blocked'))]
        return sorted(games, key=lambda g: g['name'].casefold())

    @staticmethod
    def filter_label(key):
        return {'installed': 'Installed', 'all': 'All'}.get(key, 'Available')

    def provider_name(self):
        return {'dlss-unlocked': 'DLSS-Unlocked', 'custom': 'Custom package'}.get(self.owner.settings.get('runtime_provider'), 'y4my Multipass')

    def build_library(self):
        t = self.theme
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(12 if t.compact else 14), vexpand=True)
        main.set_margin_start(t.px(56))
        main.set_margin_end(t.px(56))
        main.set_margin_top(t.px(16 if t.compact else 24))
        games = self.filtered_games()
        owner = self.owner

        heading = Gtk.Box()
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(10), hexpand=True)
        h1 = self.label('Select games' if self.selecting else 'Library', 'gm-h1')
        if t.compact:
            h1.add_css_class('compact')
        titles.append(h1)
        configured = sum(1 for g in owner.games if g.get('installed'))
        if not t.compact:
            titles.append(self.label(f"{len(self.selected)} selected · {self.filter_label(owner.settings.get('library_filter'))}"
                                     if self.selecting else f"{len(owner.games)} games · {configured} configured", 'gm-p'))
        heading.append(titles)
        provider = Gtk.Box(spacing=t.px(10), valign=Gtk.Align.CENTER)
        provider.add_css_class('gm-pill')
        provider.append(self.icon('package-x-generic-symbolic', t.px(16)))
        provider.append(self.label(self.provider_name()))
        heading.append(provider)
        main.append(heading)

        # Toolbar: Features + operations.
        toolbar = Gtk.Box(spacing=t.px(20))
        toolbar.add_css_class('gm-surface')
        for side in ('start', 'end'):
            getattr(toolbar, 'set_margin_' + side)(0)
        inner = Gtk.Box(spacing=t.px(20), hexpand=True)
        for side, value in (('start', 24), ('end', 24), ('top', 8 if t.compact else 20), ('bottom', 8 if t.compact else 20)):
            getattr(inner, 'set_margin_' + side)(t.px(value))
        toolbar.append(inner)
        narrow = self.layout_width <= 1180
        if narrow:
            inner.set_orientation(Gtk.Orientation.VERTICAL)
            inner.set_spacing(t.px(12))
        mode = Gtk.Box(spacing=t.px(28), hexpand=True, valign=Gtk.Align.CENTER)
        mode.append(self.label('Features', 'gm-strong'))
        nr_available = owner.settings.get('runtime_provider', 'y4my') in ('dlss-unlocked', 'custom')
        mode.append(self.segments([('nr-only', 'NR Only', nr_available), ('mfg-only', 'MFG Only'), ('nr-mfg', 'NR + MFG')],
                                  owner.mode, self.set_mode))
        inner.append(mode)
        pool = self.selected_games() if self.selecting else games
        actions = Gtk.Box(spacing=t.px(12), valign=Gtk.Align.CENTER, halign=Gtk.Align.START)
        actions.append(self.button(f'Install selected ({len(self.selected)})' if self.selecting else f'Install shown ({sum(1 for g in games if not g.get("blocked"))})',
                                   lambda: self.run_operation('install', self.scoped_targets()), 'primary', 'folder-download-symbolic',
                                   enabled=any(not g.get('blocked') for g in pool), key='lib-install'))
        actions.append(self.button('Restore', lambda: self.run_operation('uninstall', [g for g in self.scoped_targets() if g.get('installed')]),
                                   'danger', 'edit-undo-symbolic', enabled=any(g.get('installed') for g in pool), key='lib-restore'))
        actions.append(self.button('Update DLSS', lambda: self.run_operation('update-dlss', self.scoped_targets()), 'dlss', 'emblem-synchronizing-symbolic',
                                   enabled=any(not g.get('blocked') for g in pool), key='lib-update'))
        inner.append(actions)
        main.append(toolbar)

        # Sub-bar: filter · views · selection.
        # A Box, not a CenterBox: a CenterBox asks for twice its widest side.
        subbar = Gtk.Box(spacing=self.theme.px(16))
        filt = Gtk.Box(spacing=t.px(16), valign=Gtk.Align.CENTER)
        filt.append(self.label('Show: ' + self.filter_label(owner.settings.get('library_filter')), 'gm-p'))
        filt.append(self.button('Filter', self.open_filter, 'quiet', 'view-more-horizontal-symbolic', key='lib-filter'))
        subbar.append(filt)
        subbar.append(Gtk.Box(hexpand=True))
        view = owner.settings.get('library_view', 'posters')
        subbar.append(self.segments([(key, title) for key, title in (('posters', 'Posters'), ('capsules', 'Wide Capsule'), ('list', 'List'))],
                                               view, self.set_library_view, panel=True))
        selection = Gtk.Box(spacing=t.px(4), halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
        if self.selecting:
            selection.append(self.button('Select all', self.select_all_visible, 'quiet', key='sel-all'))
            selection.append(self.button('Clear', lambda: (self.selected.clear(), self.render(keep_focus=True)), 'quiet', enabled=bool(self.selected), key='sel-clear'))
            selection.append(self.button('Done', self.stop_selecting, key='sel-done'))
        else:
            selection.append(self.button('Select games', self.start_selecting, 'quiet', 'object-select-symbolic', key='sel-start'))
        subbar.append(Gtk.Box(hexpand=True))
        subbar.append(selection)
        main.append(subbar)

        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        available = max(320, self.layout_width - t.px(56) * 2 - t.px(40))
        if not games:
            scroll.set_child(self.empty_library())
        elif view == 'list':
            scroll.set_child(self.list_layout(games))
        else:
            scroll.set_child(self.card_layout(games, available, view == 'capsules'))
        main.append(scroll)
        self.library_scroll = scroll
        return main

    def set_mode(self, key):
        self.owner.profile_group.set_active_name(key)
        self.owner.mode = key
        self.render(keep_focus=True)

    def set_library_view(self, key):
        owner = self.owner
        control = getattr(owner, 'view_buttons', {}).get(key)
        if control is not None:
            # The desktop's own path switches its gallery and stores the choice;
            # run it even when the hidden toggle is already active.
            control.set_active(True)
            owner.view_changed(control, key)
        owner.settings['library_view'] = key
        self.save_settings()
        self.pending_focus = 'seg-' + key
        self.render()

    def empty_library(self):
        t = self.theme
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(24), halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        page.set_margin_top(t.px(60))
        page.append(self.icon('applications-games-symbolic', t.px(60)))
        page.append(self.label('No games found' if not self.owner.games else 'No games match this filter', 'gm-h2', xalign=0.5))
        page.append(self.label('Refresh the library, or add a game folder in Desktop UI.' if not self.owner.games
                               else 'Choose a different filter to see more of your library.', 'gm-p', wrap=True, xalign=0.5))
        actions = Gtk.Box(spacing=t.px(16), halign=Gtk.Align.CENTER)
        actions.append(self.button('Refresh library', self.refresh_library))
        actions.append(self.button('Filter', self.open_filter))
        page.append(actions)
        return page

    def card_layout(self, games, width, wide):
        t = self.theme
        if not wide:
            columns = 5 if self.layout_width <= 1050 else 7
        else:
            columns = 4 if t.compact else 2 if self.layout_width <= 1050 else 3 if self.layout_width <= 1500 else 4
        gap = t.px(18 if t.compact else 24)
        cell = int((width - gap * (columns - 1)) // columns)
        grid = Gtk.Grid(column_spacing=gap, row_spacing=t.px(18 if t.compact else 24), halign=Gtk.Align.START, valign=Gtk.Align.START)
        for side, value in (('start', 12), ('end', 22), ('top', 18), ('bottom', 18)):
            getattr(grid, 'set_margin_' + side)(t.px(value))
        for index, game in enumerate(games):
            grid.attach(self.game_card(game, cell, wide), index % columns, index // columns, 1, 1)
        return grid

    def game_card(self, game, width, wide):
        t = self.theme
        art_height = round(width * 430 / 920) if wide else round(width * 1.5)
        source = (self.h.capsule_art_path(game) or self.h.poster_art_path(game)) if wide else (self.h.poster_art_path(game) or self.h.capsule_art_path(game))
        frame = self.picture(source, width, art_height)
        overlay = Gtk.Overlay()
        overlay.set_child(frame)
        if not source:
            fallback = self.label(game['name'], 'gm-art-fallback', wrap=True, xalign=0.5)
            fallback.set_valign(Gtk.Align.CENTER)
            fallback.set_justify(Gtk.Justification.CENTER)
            fallback.set_margin_start(self.theme.px(12))
            fallback.set_margin_end(self.theme.px(12))
            overlay.add_overlay(fallback)
        check = self.selection_check(game)
        if check is not None:
            overlay.add_overlay(check)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(8 if t.compact else 14))
        column.append(overlay)
        title = self.label(game['name'], 'gm-cardtitle', wrap=True, lines=2)
        title.set_size_request(width, -1)
        title.set_width_chars(1)
        column.append(title)
        enabled = not self.selecting or not game.get('blocked')
        card = Gtk.Button(child=column, sensitive=enabled)
        card.add_css_class('gm-gamecard')
        card.add_css_class(self.accent_class(game))
        if self.selecting and game['game'] in self.selected:
            card.add_css_class('gm-selected')
        if not enabled:
            frame.set_opacity(0.5)
        card.update_property([Gtk.AccessibleProperty.LABEL], [game['name']])
        card.connect('clicked', lambda *_: self.activate_game(game))
        self.key(card, 'game-' + game['game'])
        return card

    def selection_check(self, game):
        if not self.selecting:
            return None
        box = Gtk.Box(halign=Gtk.Align.END, valign=Gtk.Align.START)
        for side in ('top', 'end', 'start', 'bottom'):
            getattr(box, 'set_margin_' + side)(self.theme.px(14))
        box.add_css_class('gm-check')
        if game['game'] in self.selected:
            box.append(self.icon('object-select-symbolic', self.theme.px(18)))
        return box

    def list_layout(self, games):
        t = self.theme
        stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(2))
        for side, value in (('start', 12), ('end', 22), ('top', 18), ('bottom', 18)):
            getattr(stack, 'set_margin_' + side)(t.px(value))
        for index, game in enumerate(games):
            stack.append(self.list_row(game, index == 0, index == len(games) - 1))
        return stack

    def list_row(self, game, first, last):
        t = self.theme
        surface = Gtk.Box(spacing=t.px(28))
        surface.add_css_class('gm-listsurface')
        surface.set_size_request(-1, t.px(84 if t.compact else 112) - t.px(32))
        art_cell = Gtk.Box(spacing=t.px(16), valign=Gtk.Align.CENTER)
        check = self.selection_check(game)
        if check is not None:
            for side in ('top', 'end', 'start', 'bottom'):
                getattr(check, 'set_margin_' + side)(0)
            check.set_valign(Gtk.Align.CENTER)
            art_cell.append(check)
        art_cell.append(self.picture(self.h.capsule_art_path(game) or self.h.poster_art_path(game), t.px(144), t.px(68)))
        surface.append(art_cell)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(4), hexpand=True, valign=Gtk.Align.CENTER)
        title = self.label(game['name'], 'gm-strong', 'gm-rowtitle')
        names.append(title)
        names.append(self.label(game.get('source') or 'Folder', 'gm-small'))
        surface.append(names)
        chip = self.label(game.get('profile', 'Configured') if game.get('installed') else 'Not configured', 'gm-chip')
        chip.set_valign(Gtk.Align.CENTER)
        chip.set_size_request(t.px(230), -1)
        surface.append(chip)
        state = Gtk.Box(spacing=t.px(10), valign=Gtk.Align.CENTER)
        state.set_size_request(t.px(160), -1)
        dot = Gtk.Box(valign=Gtk.Align.CENTER)
        dot.add_css_class('gm-dot')
        if game.get('installed'):
            dot.add_css_class('on')
        state.append(dot)
        state.append(self.label('Unsupported' if game.get('blocked') else 'Installed' if game.get('installed') else 'Available', 'gm-p'))
        if game.get('installed') and game.get('installed_on') in ('linux', 'windows'):
            mark = self.icon('rtx-os-' + game['installed_on'] + '-symbolic', t.px(14))
            mark.set_tooltip_text('Installed with rtxForge on ' + game['installed_on'].title())
            state.append(mark)
        surface.append(state)
        details = self.label('Select' if self.selecting else 'Details', 'gm-chip', 'gm-plain', xalign=0.5)
        details.set_valign(Gtk.Align.CENTER)
        surface.append(details)
        enabled = not self.selecting or not game.get('blocked')
        row = Gtk.Button(child=surface, sensitive=enabled, hexpand=True)
        row.add_css_class('gm-listrow')
        row.add_css_class(self.accent_class(game))
        if first:
            row.add_css_class('first')
        if last:
            row.add_css_class('last')
        if self.selecting and game['game'] in self.selected:
            row.add_css_class('gm-selected')
        row.connect('clicked', lambda *_: self.activate_game(game))
        self.key(row, 'game-' + game['game'])
        return row

    def selected_games(self):
        return [g for g in self.owner.games if g['game'] in self.selected]

    def scoped_targets(self):
        """Explicit selection wins, else the current filter; never the whole library by default."""
        if self.selecting and not self.selected:
            self.toast('No games selected.')
            return []
        visible = {g['game'] for g in self.filtered_games()}
        try:
            return operation_targets(self.owner.games, self.selected if self.selecting else set(),
                                     lambda g: g['game'] in visible)
        except ScopeError as error:
            self.toast(str(error))
            return []

    def start_selecting(self):
        self.selecting = True
        self.render(keep_focus=True)

    def stop_selecting(self):
        self.selecting = False
        self.selected.clear()
        self.render()

    def select_all_visible(self):
        self.selected |= {g['game'] for g in self.filtered_games() if not g.get('blocked')}
        self.render(keep_focus=True)

    def activate_game(self, game):
        if self.selecting:
            if game.get('blocked'):
                return
            self.selected ^= {game['game']}
            self.render(keep_focus=True)
            return
        self.open_details(game)

    def toggle_select_focused(self, focus):
        if self.page != 'library' or self.modals:
            return
        key = getattr(focus, '_gm_key', '') or ''
        game = next((g for g in self.filtered_games() if key == 'game-' + g['game']), None)
        if game is None:
            return
        self.selecting = True
        self.activate_game(game)

    def open_filter(self):
        t = self.theme
        current = self.owner.settings.get('library_filter', 'available')
        current = current if current in ('installed', 'all') else 'available'
        state = {'pending': current}
        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(12))
        status = self.label('', 'gm-p', wrap=True)
        marks = {}
        buttons = {}
        def refresh():
            for key, mark in marks.items():
                on = key == state['pending']
                (mark.add_css_class if on else mark.remove_css_class)('on')
                clear(mark)
                if on:
                    mark.append(self.icon('object-select-symbolic', t.px(16)))
            status.set_text(f"Current: {self.filter_label(current)} · Pending: {self.filter_label(state['pending'])} · Up/down move · Select changes the choice.")
        for key, title, description in (('available', 'Available', 'Supported game folders'), ('installed', 'Installed', 'Games with managed features'), ('all', 'All', 'Every discovered game')):
            mark = Gtk.Box(valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
            mark.add_css_class('gm-mark')
            marks[key] = mark
            line = Gtk.Box(spacing=t.px(22))
            line.append(mark)
            name = self.label(title, 'gm-strong')
            name.set_hexpand(True)
            line.append(name)
            line.append(self.label(description, 'gm-p'))
            option = Gtk.Button(child=line, hexpand=True)
            option.add_css_class('gm-btn')
            option.connect('clicked', lambda *_, key=key: (state.update(pending=key), refresh()))
            buttons[key] = option
            options.append(option)
        refresh()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(20))
        content.append(self.label('Choose which games to show, then Apply.', 'gm-p'))
        content.append(options)
        content.append(status)
        def apply():
            self.owner.settings['library_filter'] = state['pending']
            self.save_settings()
            self.close_modal()
            self.render(keep_focus=True)
        actions = [self.button('Reset', lambda: (state.update(pending='available'), refresh())), self.button('Back', self.close_modal),
                   self.button('Apply', apply, 'primary', 'object-select-symbolic')]
        self.show_modal('Filter library', content, actions, self.close_modal, 900, buttons[current])

    # ---------------- details ----------------

    def open_details(self, game):
        self.library_focus = self.focus_key()
        self.details_game = self.game = game
        self.section = 'Overview'
        self.presets_expanded = False
        self.notes_status = None
        self.notes_draft = None
        self.page = 'details'
        self.render()

    def close_details(self):
        self.page = 'library'
        self.pending_focus = self.library_focus
        self.render()

    def build_details(self, g):
        t = self.theme
        width = self.layout_width
        hero_height = t.px(290 if t.compact else 340 if width <= 1500 else 390)
        nav_width = t.px(184 if width <= 1050 else 246 if width <= 1500 else 254)
        side = t.px(24 if width <= 1050 else 36 if width <= 1500 else 56)
        accent = self.accent_class(g)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(12 if t.compact else 22), vexpand=True)
        page.add_css_class(accent)

        hero = Gtk.Overlay()
        hero.set_size_request(-1, hero_height)
        art = self.picture(g.get('hero') or self.h.capsule_art_path(g), None, hero_height, css='gm-hero')
        art.set_hexpand(True)
        hero.set_child(art)
        scrim = Gtk.Box(can_target=False)
        scrim.add_css_class('gm-hero-scrim')
        hero.add_overlay(scrim)
        identity = Gtk.Box(spacing=t.px(30), valign=Gtk.Align.END)
        for side_name, value in (('start', side), ('end', side), ('bottom', t.px(18 if t.compact else 26))):
            getattr(identity, 'set_margin_' + side_name)(value)
        poster_height = t.px(156 if t.compact else 184 if width <= 1500 else 210)
        poster = self.picture(self.h.poster_art_path(g) or self.h.capsule_art_path(g), round(poster_height * 2 / 3), poster_height, css='gm-poster')
        poster.set_valign(Gtk.Align.END)
        identity.append(poster)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(8), valign=Gtk.Align.END, hexpand=True)
        tight = t.compact or width <= 1180
        title = self.label(g['name'], 'gm-gametitle', wrap=not tight, lines=0 if tight else 2)
        text.append(title)
        badges = Gtk.Box(spacing=t.px(8))
        source = g.get('source') or 'Folder'
        if g.get('installed') and g.get('profile'):
            badges.append(self.badge(g['profile'], 'gm-badge-profile', big=True))
        badges.append(self.badge(source, 'gm-badge-source', 'rtx-steam-symbolic' if source == 'Steam' else None, big=True))
        tested = (g.get('test_record') or {}).get('status', 'Untested') not in ('Untested', '')
        badges.append(self.badge('Tested' if tested else 'Untested', 'gm-badge-tested', 'object-select-symbolic' if tested else 'applications-science-symbolic', big=True))
        if g.get('installed') and g.get('installed_on') in ('linux', 'windows'):
            badges.append(self.badge(g['installed_on'].title(), 'gm-badge-source', 'rtx-os-' + g['installed_on'] + '-symbolic', big=True))
        text.append(badges)
        # Windows hero: title and badges own the full width; developer ·
        # release and summary sit beside the actions underneath.
        lower_row = Gtk.Box(spacing=t.px(24))
        about = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(6), hexpand=True, valign=Gtk.Align.END)
        meta = ' · '.join(str(g[k]) for k in ('developers', 'release') if g.get(k))
        if meta:
            about.append(self.label(meta, 'gm-small'))
        if g.get('description'):
            summary = self.label(g['description'], 'gm-p', wrap=True, lines=2)
            summary.set_max_width_chars(80)
            summary.set_ellipsize(Pango.EllipsizeMode.END)
            about.append(summary)
        lower_row.append(about)
        text.append(lower_row)
        identity.append(text)
        actions = Gtk.Box(spacing=t.px(12), valign=Gtk.Align.END)
        setup = self.owner.needs_linux_setup(g)
        actions.append(self.button(('Set Up' if setup else 'Repair' if g.get('installed') else 'Install') if tight else
                                   'Set Up for Linux' if setup else 'Repair Features' if g.get('installed') else 'Install Features',
                                   lambda: self.run_operation('install', [g]), 'primary', 'folder-download-symbolic', enabled=not g.get('blocked'), key='hero-install'))
        actions.append(self.button('Restore' if tight else 'Restore Original Files', lambda: self.run_operation('uninstall', [g]), 'danger', 'edit-undo-symbolic',
                                   enabled=bool(g.get('installed')), key='hero-restore'))
        actions.append(self.button('Update DLSS', lambda: self.run_operation('update-dlss', [g]), 'dlss', 'emblem-synchronizing-symbolic',
                                   enabled=not g.get('blocked'), key='hero-update'))
        if tight:
            # Narrow windows drop the actions under the summary.
            lower_row.set_orientation(Gtk.Orientation.VERTICAL)
        lower_row.append(actions)
        hero.add_overlay(identity)
        back = Gtk.Button(child=self.content('Back to Library', 'go-previous-symbolic'), halign=Gtk.Align.START, valign=Gtk.Align.START)
        back.add_css_class('gm-back')
        back.set_margin_start(side)
        back.set_margin_top(t.px(12 if t.compact else 18))
        back.connect('clicked', lambda *_: self.close_details())
        self.key(back, 'details-back')
        hero.add_overlay(back)
        page.append(hero)

        lower = Gtk.Box(spacing=t.px(26), vexpand=True)
        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(6 if t.compact else 12))
        nav.set_size_request(nav_width, -1)
        nav.set_margin_start(side)
        heading = self.label('Game Details', 'gm-h3', wrap=True)
        heading.set_margin_start(t.px(16))
        heading.set_margin_bottom(t.px(12 if t.compact else 20))
        nav.append(heading)
        first = None
        for section in SECTIONS:
            button = Gtk.Button(child=self.label(section))
            button.add_css_class('gm-navbtn')
            if section == self.section:
                button.add_css_class('on')
                first = button
            button.connect('clicked', lambda *_, section=section: self.open_section(section))
            self.key(button, 'section-' + section)
            nav.append(button)
        nav_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        nav_scroll.set_child(nav)
        lower.append(nav_scroll)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(24))
        for side_name, value in (('start', 24), ('end', 24), ('top', 12), ('bottom', 12)):
            getattr(content, 'set_margin_' + side_name)(t.px(value))
        self.build_section(g, content)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True)
        scroll.set_margin_end(side)
        scroll.set_child(content)
        lower.append(scroll)
        page.append(lower)
        if first is not None and not self.pending_focus:
            self.first_focus = first
        return page

    def open_section(self, section):
        self.section = section
        self.pending_focus = 'section-' + section
        self.render()

    def section_title(self, content, title, description=None):
        block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=self.theme.px(10))
        block.append(self.label(title, 'gm-h2'))
        if description:
            block.append(self.label(description, 'gm-p', wrap=True))
        content.append(block)

    def build_section(self, g, content):
        t = self.theme
        owner = self.owner
        section = self.section
        if section == 'Features':
            setup = owner.needs_linux_setup(g)
            legacy = g.get('installed_on') == 'windows' and not g.get('adaptable')
            if g.get('installed_on') == 'windows' and g.get('adaptable'):
                description = ('Installed with rtxForge on Windows. Set Up for Linux hands it to rtxForge here and adds the Proton setting; '
                               'the game files stay as Windows installed them. Restore Original Files works from here too.')
            elif legacy:
                description = ('Installed with rtxForge on Windows. Set Up for Linux adds only the Proton setting; the game files stay as Windows installed them.'
                               if setup else 'Installed with rtxForge on Windows and set up for Linux. Restore its original files in rtxForge on Windows.')
            elif g.get('installed'):
                description = f"Saved: {g.get('profile') or 'Configured'}. The rendered effect still needs an in-game check."
            else:
                description = g.get('blocked') or 'Not installed. Review every file change before installing.'
            self.section_title(content, 'Features', description)
            expander = Gtk.Box(spacing=t.px(16))
            expander.append(self.icon('pan-down-symbolic' if self.presets_expanded else 'pan-end-symbolic', t.px(16)))
            caption = self.label('Presets', 'gm-strong')
            caption.set_hexpand(True)
            expander.append(caption)
            expander.append(self.label('Expanded' if self.presets_expanded else 'Collapsed', 'gm-small'))
            toggle = Gtk.Button(child=expander, hexpand=True)
            toggle.add_css_class('gm-rowbtn')
            toggle.connect('clicked', lambda *_: self.toggle_presets())
            self.key(toggle, 'presets-expander')
            content.append(toggle)
            if self.presets_expanded:
                rows, value = self.preset_rows(g, g.get('installed') and not g.get('blocked'))
                content.append(self.label('Only this game changes. Review the changes before applying.', 'gm-p'))
                content.append(self.group(rows))
                content.append(self.button('Apply to this game', lambda: self.run_operation('reset', [g], value()), 'primary',
                                           enabled=bool(g.get('installed') and not g.get('blocked')), halign=Gtk.Align.START))
            self.section_title(content, 'Installation')
            content.append(self.group([
                self.row_button('Set Up for Linux' if setup else 'Install Features', action=lambda: self.run_operation('install', [g]), enabled=not g.get('blocked')),
                self.row_button('Repair Feature Files', action=lambda: self.run_operation('install', [g]), enabled=bool(g.get('installed') and not g.get('blocked') and not setup)),
                self.row_button('Remove Linux Setup' if legacy else 'Restore Original Files',
                                action=lambda: self.run_operation('uninstall', [g]), danger=True, enabled=bool(g.get('installed'))),
            ]))
        elif section == 'DLSS Files':
            self.section_title(content, 'DLSS Files', 'Updater backups are previous copies, not proof of the version currently shipped by the game.')
            content.append(self.group([self.preference('Installed DLSS version', None, self.label(g.get('dlss_version') or 'Checked during update', 'gm-value'))]))
            self.section_title(content, 'File Management')
            content.append(self.group([
                self.row_button('Update DLSS files', action=lambda: self.run_operation('update-dlss', [g]), enabled=not g.get('blocked')),
                self.row_button('Restore original DLSS files', action=lambda: owner.manage_dlss_files(g, restore=True), danger=True, enabled=not g.get('blocked')),
            ]))
        elif section == 'Tools':
            self.section_title(content, 'Tools', 'Check NR or add ReShade to this game. Existing graphics files are kept safe.')
            tools = Gtk.Grid(column_spacing=t.px(20), row_spacing=t.px(20), column_homogeneous=True)
            demo = owner.options.demo
            for index, (icon, title, enabled, action) in enumerate((
                    ('system-search-symbolic', 'Diagnose NR', bool(g.get('installed')), lambda: owner.show_diagnostics(g)),
                    ('applications-graphics-symbolic', 'Install ReShade', not demo and not g.get('blocked'), lambda: owner.choose_extra(g, 'reshade')),
                    ('list-add-symbolic', 'Install Add-on', not demo and not g.get('blocked'), lambda: owner.choose_extra(g, 'addon')),
                    ('web-browser-symbolic', 'ReShade Downloads', True, lambda: Gtk.UriLauncher.new('https://reshade.me/').launch(owner, None, None)))):
                tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(10), halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
                tile.append(self.icon(icon, t.px(22)))
                tile.append(self.label(title, 'gm-strong', xalign=0.5))
                widget = Gtk.Button(child=tile, sensitive=enabled, hexpand=True)
                widget.add_css_class('gm-tile')
                widget.connect('clicked', lambda *_, action=action: action())
                self.key(widget, 'tool-' + title)
                tools.attach(widget, index % 2, index // 2, 1, 1)
            content.append(tools)
            content.append(self.label('Use an extracted x64 ReShade DLL or .addon64 file from a source you trust. Each install is reviewed first and can be restored.', 'gm-p', wrap=True))
        elif section == 'Notes':
            self.section_title(content, 'Notes', 'Kept with this game in rtxForge.')
            record = g.get('test_record') or {'status': 'Untested', 'notes': ''}
            notes = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, height_request=t.px(160))
            notes.add_css_class('gm-notes')
            notes.get_buffer().set_text(self.notes_draft if self.notes_draft is not None else record.get('notes', ''))
            notes.get_buffer().connect('changed', lambda buf: setattr(self, 'notes_draft', buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)))
            self.key(notes, 'notes')
            content.append(notes)
            if self.notes_status is None:
                self.notes_status = record.get('status', 'Untested')
            states = list(game_notes.STATES)
            row = self.row_button('Test Result', self.notes_status, None, description='Bench excludes this game from bulk installation and repair.', key='choice-test')
            def step(delta):
                self.notes_status = states[(states.index(self.notes_status) + delta) % len(states)]
                row.get_child()._value.set_text(self.notes_status)
            row.connect('clicked', lambda *_: step(1))
            row._gm_adjust = step
            content.append(self.group([row]))
            content.append(self.label("Controller text entry uses Steam's on-screen keyboard (Steam + X).", 'gm-p', wrap=True))
            actions = Gtk.Box(spacing=t.px(16))
            actions.append(self.button('Save Notes', lambda: self.save_notes(g, notes), 'primary', key='notes-save'))
            actions.append(self.button('Finish Test' if record.get('active') else 'Start Test', lambda: owner.record_test(g, bool(record.get('active'))),
                                       enabled=not owner.options.demo, key='notes-test'))
            content.append(actions)
        elif section == 'Appearance':
            self.section_title(content, 'Accent Color', "Pick a suggestion from this game's artwork. Your own picks are kept.")
            current = owner.settings.get('game_accents', {}).get(g['game'])
            content.append(self.group([self.preference('Game Accent', 'Custom' if current else 'Artwork-derived', self.label((current or 'Automatic').upper(), 'gm-value'))]))
            swatches = Gtk.Box(spacing=t.px(16))
            source = self.h.accent_source(g)
            try:
                suggestions = ui_colors.accent_suggestions(self.h.artwork_pixels(source)) if source else []
            except Exception:
                suggestions = []
            if not suggestions:
                swatches.append(self.label('No artwork to sample.', 'gm-p'))
            for name, color in suggestions:
                cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(8))
                ring = Gtk.Box(halign=Gtk.Align.CENTER)
                ring.add_css_class('gm-swatch')
                if current and current.lower() == color.lower():
                    ring.add_css_class('on')
                dot = Gtk.DrawingArea(content_width=t.px(48), content_height=t.px(48))
                def draw(_area, cr, w, h, color=color):
                    rgba = Gdk.RGBA()
                    rgba.parse(color)
                    cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
                    cr.arc(w / 2, h / 2, min(w, h) / 2, 0, 6.283185)
                    cr.fill()
                dot.set_draw_func(draw)
                ring.append(dot)
                cell.append(ring)
                cell.append(self.label(name, 'gm-small', xalign=0.5))
                swatch = Gtk.Button(child=cell)
                swatch.add_css_class('gm-swatch-button')
                swatch.update_property([Gtk.AccessibleProperty.LABEL], [f'{name} {color}'])
                swatch.connect('clicked', lambda *_, color=color: self.set_accent(g, color))
                self.key(swatch, 'swatch-' + name)
                swatches.append(swatch)
            content.append(swatches)
            content.append(self.button('Use artwork color', lambda: self.set_accent(g, None), enabled=bool(current), halign=Gtk.Align.START))
        else:
            self.section_title(content, 'Overview')
            if g.get('description'):
                content.append(self.label('About', 'gm-h3'))
                about = self.label(g['description'], 'gm-p', wrap=True)
                about.set_max_width_chars(90)
                content.append(about)
            content.append(self.label('Game Information', 'gm-h3'))
            rows = [self.preference(title, None, self.label(str(value), 'gm-value')) for title, value in overview_facts.compact_facts(g)]
            if g.get('blocked'):
                rows.append(self.preference('Compatibility', None, self.label(str(g['blocked']), 'gm-value')))
            folder = overview_facts.folder(g)
            if folder:
                location = self.label(folder, 'gm-value', wrap=True, xalign=0)
                location.set_max_width_chars(60)
                open_folder = self.button('Open folder', lambda: Gio.AppInfo.launch_default_for_uri(Path(folder).as_uri(), None),
                                          enabled=not self.owner.options.demo, key='details-open-folder')
                rows.append(self.preference('Game folder', None, location))
            content.append(self.group(rows))
            if folder:
                open_folder.set_halign(Gtk.Align.START)
                content.append(open_folder)

    def toggle_presets(self):
        self.presets_expanded = not self.presets_expanded
        self.render(keep_focus=True)

    def save_notes(self, g, view):
        buffer = view.get_buffer()
        record = dict(g.get('test_record') or {})
        record.update(status=self.notes_status or record.get('status', 'Untested'), notes=buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True))
        if not self.owner.options.demo:
            game_notes.save(self.owner.service.config, g['game'], record)
        g['test_record'] = record
        self.notes_draft = None
        self.toast('Notes saved')

    def set_accent(self, g, color):
        accents = self.owner.settings.setdefault('game_accents', {})
        if color:
            accents[g['game']] = color
        else:
            accents.pop(g['game'], None)
        g.pop('accent_class', None)
        self.save_settings()
        entry = self.owner.cards.get(g['game']) if hasattr(self.owner, 'cards') else None
        if entry:
            self.owner.paint_card(entry)
        self.render(keep_focus=True)

    def preset_rows(self, game, enabled=True):
        owner = self.owner
        source = game if game is not None else owner.settings
        state = {'nr': float(source.get('nr_strength', owner.settings.get('nr_strength', 2.0)) or 0),
                 'sharp': float(source.get('sharpening_strength', owner.settings.get('sharpening_strength', 0.5)) or 0),
                 }
        saved = dict(owner.settings)
        saved.update({k: source[k] for k in ('mfg_multiplier', 'dynamic_mfg', 'mfg_saved_mode', 'mfg_saved_multiplier') if source.get(k) is not None})
        dynamic_available = bool(game.get('dynamic_mfg_available')) if game is not None else owner.settings.get('runtime_provider') == 'skynizz'
        state['mfg_on'], state['mfg_mode'], state['mfg_ratio'] = mfg_choice.from_values(saved)
        if state['mfg_mode'] == mfg_choice.DYNAMIC and not dynamic_available:
            state['mfg_mode'] = mfg_choice.CUSTOM
        modes = [m for m in mfg_choice.MODES if m != mfg_choice.DYNAMIC or dynamic_available]
        def mode_step(delta):
            state['mfg_mode'] = modes[max(0, min(len(modes) - 1, modes.index(state['mfg_mode']) + delta))]
        def ratio_step(delta):
            state['mfg_ratio'] = max(2, min(6, state['mfg_ratio'] + delta))
        mfg_enabled = enabled and owner.mode != 'nr-only'
        rows = [
            self.stepper('NR Strength', '0.0 turns the effect off.', lambda: f"{state['nr']:.1f}",
                         lambda d: state.update(nr=max(0.0, min(2.0, round(state['nr'] + d * 0.1, 1)))), enabled and owner.mode != 'mfg-only', key='step-nr'),
            self.stepper('Sharpening', '0.0 turns sharpening off.', lambda: f"{state['sharp']:.1f}",
                         lambda d: state.update(sharp=max(0.0, min(1.0, round(state['sharp'] + d * 0.1, 1)))), enabled, key='step-sharp'),
            self.stepper('Multi-Frame Generation', 'Enable frame generation in the game as well.', lambda: 'On' if state['mfg_on'] else 'Off',
                         lambda d: state.update(mfg_on=d > 0), mfg_enabled, key='step-mfg'),
            self.stepper('MFG mode', 'Auto follows the game · Custom is fixed · Dynamic is a maximum where supported.',
                         lambda: mfg_choice.MODE_NAMES[state['mfg_mode']], mode_step, mfg_enabled, key='step-mfg-mode'),
            self.stepper('MFG ratio', 'Used by Custom and Dynamic.', lambda: f"{state['mfg_ratio']}×", ratio_step, mfg_enabled, key='step-mfg-ratio'),
        ]
        return rows, lambda: {'nr_strength': state['nr'], 'sharpening_strength': state['sharp'],
                              **mfg_choice.to_values(state['mfg_on'], state['mfg_mode'], state['mfg_ratio'], dynamic_available)}

    # ---------------- presets ----------------

    def build_presets(self):
        t = self.theme
        owner = self.owner
        column = min(t.px(1600), max(0, self.layout_width - t.px(56) * 2))
        side = max(t.px(56), (self.layout_width - column) // 2)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(24))
        for name, value in (('start', side), ('end', side), ('top', t.px(32)), ('bottom', t.px(24))):
            getattr(page, 'set_margin_' + name)(value)
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(10))
        head.append(self.label('Library presets', 'gm-h1'))
        head.append(self.label('Apply to your configured games. Unmanaged games are skipped.', 'gm-p'))
        page.append(head)
        rows, value = self.preset_rows(None)
        self.preset_value = value
        page.append(self.group(rows))
        note = Gtk.Box(spacing=t.px(12))
        note.append(self.icon('dialog-information-symbolic', t.px(18)))
        note.append(self.label('Saved settings take effect on the next game launch. They do not verify the rendered effect.', 'gm-p', wrap=True))
        page.append(note)
        configured = [g for g in owner.games if g.get('installed') and not g.get('blocked')]
        actions = Gtk.Box(spacing=t.px(16))
        actions.append(self.button(f'Apply to all configured games ({len(configured)})', lambda: self.apply_presets(configured), 'primary',
                                   enabled=bool(configured), key='presets-apply'))
        def choose():
            self.save_presets()
            self.selecting = True
            self.selected.clear()
            self.open('library')
            self.toast('Select games, then Install selected or use Presets › Apply.')
        actions.append(self.button('Select games to apply', choose, enabled=bool(configured)))
        actions.append(self.button('Reset Presets', lambda: self.render()))
        page.append(actions)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroll.set_child(page)
        return scroll

    def save_presets(self):
        values = self.preset_value() if getattr(self, 'preset_value', None) else None
        if not values:
            return
        self.owner.settings.update(values)
        for key, widget in self.owner.tuning_widgets.items():
            if key == 'mfg_multiplier':
                widget.set_values(values)
            else:
                widget.set_value(values[key])
        self.save_settings()

    def apply_presets(self, games):
        self.save_presets()
        keys = ('nr_strength', 'sharpening_strength', 'mfg_multiplier', 'dynamic_mfg', 'mfg_saved_mode', 'mfg_saved_multiplier')
        self.run_operation('reset', games, {k: self.owner.settings[k] for k in keys if k in self.owner.settings})

    # ---------------- settings ----------------

    def build_settings(self):
        t = self.theme
        width = self.layout_width
        grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(22), vexpand=True)
        for name, value in (('start', 56), ('end', 56), ('top', 32)):
            getattr(grid, 'set_margin_' + name)(t.px(value))
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(10))
        head.append(self.label('Settings', 'gm-h1'))
        head.append(self.label('The same rtxForge preferences, sized for the couch.', 'gm-p'))
        grid.append(head)
        lower = Gtk.Box(spacing=t.px(40), vexpand=True)
        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(12))
        nav.set_size_request(t.px(180 if width <= 1050 else 220 if width <= 1500 else 270), -1)
        for section in SETTINGS_SECTIONS:
            button = Gtk.Button(child=self.label(section))
            button.add_css_class('gm-navbtn')
            if section == self.settings_section:
                button.add_css_class('on')
                if not self.pending_focus:
                    self.first_focus = button
            button.connect('clicked', lambda *_, section=section: self.open_settings_section(section))
            self.key(button, 'set-' + section)
            nav.append(button)
        lower.append(nav)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(24))
        description, rows = self.settings_rows(self.settings_section)
        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(10))
        title.append(self.label(self.settings_section, 'gm-h2'))
        title.append(self.label(description, 'gm-p', wrap=True))
        content.append(title)
        content.append(self.group(rows))
        if self.settings_section == 'Controller':
            buttons = self.label('Buttons', 'gm-h3')
            buttons.set_margin_top(t.px(12))
            content.append(buttons)
            content.append(self.group(self.guide_rows('controller')))
        note = Gtk.Box(spacing=t.px(12))
        note.append(self.icon('dialog-information-symbolic', t.px(18)))
        note.append(self.label('Mouse or keyboard input keeps your chosen interface.', 'gm-p'))
        content.append(note)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True)
        scroll.set_child(content)
        lower.append(scroll)
        grid.append(lower)
        return grid

    def open_settings_section(self, section):
        self.settings_section = section
        self.pending_focus = 'set-' + section
        self.render()

    def guide_rows(self, view):
        family = self.owner.settings.get('controller_glyphs', 'auto')
        if family == 'auto':
            family = getattr(getattr(self.owner, 'controller', None), 'family', 'xbox') or 'xbox'
        accept, back, library, menu = controller_input.GLYPHS.get(family, controller_input.GLYPHS['generic'])
        select, settings_key, bumpers = {'playstation': ('□', 'Create', 'L1 / R1'), 'nintendo': ('Y', '−', 'L / R'),
                                         'generic': ('West', 'Back', 'Left / Right shoulder')}.get(family, ('X', 'View', 'LB / RB'))
        if view == 'controller':
            entries = [('Move between items', 'D-pad / Left stick'), ('Select', accept), ('Back, or close a dialog', back), ('Library', library),
                       ('Select games', select), ('Switch pages', bumpers), ('Adjust a value', 'D-pad left / right'), ('Settings', settings_key), ('Main menu', menu)]
        else:
            entries = [('Move between items', 'Arrow keys'), ('Select', 'Enter'), ('Back, or close a dialog', 'Esc'), ('Library', 'Ctrl+L'),
                       ('Select games', 'X'), ('Switch pages', 'Page Up / Page Down'), ('Adjust a value', 'Left / Right'), ('Settings', 'Ctrl+,'),
                       ('Main menu', 'F10'), ('Move focus in order', 'Tab / Shift+Tab')]
        rows = []
        for action, key in entries:
            row = Gtk.Button(child=self.preference(action, None, self.keycap(key), inset=False), hexpand=True)
            row.add_css_class('gm-rowbtn')
            rows.append(row)
        return rows

    def settings_rows(self, section):
        owner = self.owner
        s = owner.settings
        def set_theme(value):
            s['theme'] = value
            s['dark'] = value != 'light'
            GLib.idle_add(lambda: (self.apply_theme(), self.render(keep_focus=True), False)[-1])
        if section == 'Appearance':
            return 'Shared desktop appearance. Gaming Mode keeps a clear focus ring.', [
                self.choice('Theme', 'Night is the Game Mode default.', ['night', 'dark', 'light'], ['Night', 'Dark', 'Light'],
                            lambda: s.get('theme') if s.get('theme') in ('light', 'dark') else 'night', set_theme),
                self.choice('Button glyphs', 'Icons beside action labels; selection and package identity stay visible.', [True, False], ['On', 'Off'],
                            lambda: bool(s.get('button_glyphs', True)), lambda v: s.update(button_glyphs=v)),
            ]
        if section == 'Library':
            return 'Manage the library layout and artwork sources.', [
                self.choice('Library layout', None, ['posters', 'capsules', 'list'], ['Posters', 'Wide Capsule', 'List'],
                            lambda: s.get('library_view', 'posters'), lambda v: s.update(library_view=v)),
                self.row_button('Refresh artwork', 'Refresh', lambda: (self.toast('Refreshing artwork…'), owner.fetch_media(True)), icon='view-refresh-symbolic'),
                self.row_button('Sync artwork to Steam', None, lambda: owner.sync_steam_artwork(), description='Review and sync artwork for your library.', icon='rtx-steam-symbolic'),
                self.row_button('Steam artwork profile', None, owner.choose_steam_artwork_profile, description='Choose which local Steam account receives artwork.'),
                self.row_button('Connect SteamGridDB', None, owner.show_steamgrid_connection, description='Connect your account to browse custom artwork.'),
            ]
        if section == 'Controller':
            return 'Keep button labels and hints consistent with your controller.', [
                self.choice('Button labels', 'Match your controller family.', ['auto', 'xbox', 'playstation', 'nintendo', 'generic'],
                            ['Automatic', 'Xbox', 'PlayStation', 'Nintendo', 'Generic'], lambda: s.get('controller_glyphs', 'auto'), lambda v: s.update(controller_glyphs=v)),
                self.choice('Controller hints', None, ['always', 'auto'], ['Always visible', 'Hide when idle'],
                            lambda: s.get('controller_hints', 'always'), lambda v: s.update(controller_hints=v)),
            ]
        if section == 'Keyboard':
            return 'Every keyboard shortcut in Gaming Mode.', self.guide_rows('keyboard')
        if section == 'System':
            def set_scale(value):
                s['ui_scale'] = value
                owner.apply_display_preferences()
                GLib.idle_add(lambda: (self.apply_theme(), self.render(keep_focus=True), False)[-1])
            return 'Display scaling, navigation, recovery and updates.', [
                self.choice('UI scale', 'Automatic follows the window size (130% at 4K).', ['auto', '100', '125', '130', '150', '175', '200'],
                            ['Automatic', '100%', '125%', '130%', '150%', '175%', '200%'], lambda: str(s.get('ui_scale', 'auto')), set_scale),
                self.choice('Navigation', None, ['top', 'bottom'], ['Top', 'Bottom'], lambda: s.get('navigation_position', 'top'), lambda v: s.update(navigation_position=v)),
                self.row_button('Previous changes', None, owner.show_undo, description='Browse available recovery records.', icon='document-revert-symbolic'),
                self.row_button('Old NR files', None, owner.show_cleanup, description='Find NR files left by older tools.'),
                self.row_button('Check for updates', None, owner.check_app_update, description='rtxForge ' + self.h.app_version + ' · download, verify and install.'),
            ]
        steam_added = owner.steam_shortcut_added() if hasattr(owner, 'steam_shortcut_added') else False
        return 'Open rtxForge from your existing gaming environment.', [
            self.choice('Interface', None, ['game', 'desktop'], ['Gaming Mode', 'Desktop'], lambda: 'game',
                        lambda v: GLib.idle_add(lambda: (owner.set_input_surface(False), False)[1]) if v == 'desktop' else None),
            self.row_button('Remove rtxForge from Steam' if steam_added else 'Add rtxForge to Steam', None, owner.toggle_rtxforge_in_steam,
                            icon='rtx-steam-symbolic', key='steam-shortcut'),
        ]

    # ---------------- operations ----------------

    def run_operation(self, operation, targets=None, values=None):
        """Optional presets, then the shared review → execute path in Game Mode dialogs."""
        owner = self.owner
        if owner.busy and owner.task_kind != 'art':
            self.toast('Another operation is running.')
            return
        if targets is None:
            targets = self.scoped_targets()
            targets = [g for g in targets if g.get('installed')] if operation == 'uninstall' else [g for g in targets if not g.get('blocked')]
        if not targets:
            self.toast('No eligible games.')
            return
        if operation == 'update-dlss':
            owner.update_dlss_games(targets)
            return
        if operation == 'install' and values is None and not all(owner.needs_linux_setup(g) for g in targets):
            self.ask_presets(targets, lambda chosen: owner.launch_action('install', targets=targets, visual_settings={**owner.settings, **chosen}, _presets_confirmed=True))
            return
        owner.launch_action(operation, targets=targets, visual_settings=values if values is None else {**owner.settings, **values}, _presets_confirmed=True)

    def ask_presets(self, targets, proceed):
        t = self.theme
        rows, value = self.preset_rows(targets[0] if len(targets) == 1 else None)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(20))
        content.append(self.label('Adjust your presets or continue. You can change these settings later in OptiScaler.', 'gm-p', wrap=True))
        line = Gtk.Box(spacing=t.px(12))
        line.append(self.icon('package-x-generic-symbolic', t.px(16)))
        line.append(self.label(self.provider_name()))
        content.append(line)
        content.append(self.group(rows, True))
        cancel = self.button('Cancel', self.close_modal)
        go = self.button('Continue', lambda: (self.close_modal(), proceed(value())), 'primary')
        self.show_modal('Install Features', content, [cancel, go], self.close_modal, 1100, cancel)


class GameModeFlow:
    """The desktop OperationFlow interface, drawn as Game Mode dialogs.

    Checking → Review → Progress → Done in one modal slot; the desktop window's
    launch_action / execute / finish_progress drive it unchanged.
    """

    def __init__(self, view, owner, operation, games, words):
        self.view = view
        self.owner = owner
        self.operation = operation
        self.games = list(games)
        self.review_title, self.verb, self.progress_verb = words
        self.stage = None
        self.review = None
        self.on_confirm = None
        self.on_continue = None
        self.closed = False
        self.rescan = False
        self.modal = None
        self.step = None
        self.total = 0
        self.dialog = None
        # Plain labelled buttons: the desktop window relabels them (set_label).
        self.primary = Gtk.Button(label=self.verb)
        self.primary.add_css_class('gm-btn')
        self.primary.add_css_class('gm-primary')
        self.primary.connect('clicked', lambda *_: self._primary())
        self.cancel_button = Gtk.Button(label='Cancel')
        self.cancel_button.add_css_class('gm-btn')
        self.cancel_button.connect('clicked', lambda *_: self.cancel())
        owner.operation_flow = self

    # ----- plumbing -----

    def _show(self, title, content, actions, can_back=True):
        view = self.view
        if self.modal is not None and self.modal in view.modals:
            view.close_modal(self.modal)
        for button in (self.primary, self.cancel_button):
            parent = button.get_parent()
            if parent is not None:
                parent.remove(button)
        self.modal = view.show_modal(title, content, actions, self.cancel if can_back else (lambda: None), 1100,
                                     self.cancel_button if self.cancel_button in actions and self.cancel_button.get_visible() else None)

    def _primary(self):
        if self.stage == 'presets' and self.on_continue:
            self.on_continue()
        elif self.stage == 'review' and self.on_confirm:
            self.on_confirm(self.review)
        elif self.stage == 'done':
            self.close()

    def close(self):
        self.closed = True
        if self.modal is not None and self.modal in self.view.modals:
            self.view.close_modal(self.modal)
        if getattr(self.owner, 'operation_flow', None) is self:
            self.owner.operation_flow = None
        if self.stage == 'done' and self.rescan:
            self.owner.scan()

    def cancel(self):
        if self.stage == 'progress':
            cancel = getattr(self.owner, 'operation_cancel', None)
            if cancel is not None and self.cancel_button.get_sensitive():
                cancel.set()
                self.cancel_button.set_sensitive(False)
                self.cancel_button.set_label('Cancelling…')
                if self.step:
                    self.step['phase'].set_text('Cancelling and undoing changes…')
            return
        if self.stage in ('progress', 'working') and not self.cancel_button.get_visible():
            return
        if self.stage == 'checking' and getattr(self.owner, 'operation_cancel', None) is not None:
            self.owner.operation_cancel.set()
        self.close()

    def _title(self, text):
        pass

    def _step_layout(self):
        view, t = self.view, self.view.theme
        root = Gtk.Box(spacing=t.px(24 if view.layout_width <= 1050 else 40))
        height = t.px(225 if t.compact or view.layout_width <= 1050 else 270 if view.layout_width <= 1500 else 330)
        poster_slot = Gtk.Box()
        root.append(poster_slot)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(12), valign=Gtk.Align.CENTER, hexpand=True)
        counter = view.label('Preparing…', 'gm-p')
        title = view.label('', 'gm-step-title')
        phase = view.label('', 'gm-p')
        bar = Gtk.ProgressBar(margin_top=t.px(18), margin_bottom=t.px(10))
        for widget in (counter, title, phase, bar):
            right.append(widget)
        root.append(right)
        step = {'root': root, 'poster': poster_slot, 'height': height, 'counter': counter, 'title': title, 'phase': phase, 'bar': bar,
                'game': None, 'determinate': False, 'accent': None}
        def pulse():
            if self.step is not step or self.closed:
                return False
            if not step['determinate']:
                bar.pulse()
            return True
        GLib.timeout_add(120, pulse)
        return step

    def _step_show(self, verb, game, index, total, phase, fraction=None):
        step = self.step
        step['counter'].set_text(f'{verb} {min(index + 1, total)} of {total}' if total else 'Preparing…')
        if phase:
            step['phase'].set_text(str(phase).rstrip('.…') + '…')
        if total:
            step['determinate'] = True
            step['bar'].set_fraction(max(0.0, min(1.0, fraction if fraction is not None else index / total)))
        else:
            step['determinate'] = False
        if game is not None and game is not step['game']:
            step['game'] = game
            step['title'].set_text(game['name'])
            clear(step['poster'])
            height = step['height']
            step['poster'].append(self.view.picture(self.view.h.poster_art_path(game) or self.view.h.capsule_art_path(game),
                                                    round(height * 2 / 3), height, css='gm-step-poster'))
            if step['accent']:
                step['root'].remove_css_class(step['accent'])
            step['accent'] = self.view.accent_class(game)
            step['root'].add_css_class(step['accent'])

    # ----- stages (OperationFlow interface) -----

    def show_presets(self, tuning, on_continue):
        self.stage = 'presets'
        self.on_continue = on_continue
        on_continue()

    def show_checking(self):
        self.stage = 'checking'
        self.step = self._step_layout()
        self._step_show('Checking', self.games[0] if self.games else None, 0, 0, 'Checking game files')
        self.cancel_button.set_visible(True)
        self._show(self.review_title, self.step['root'], [self.cancel_button])

    def checking_event(self, event):
        if event.get('phase') != 'review-check':
            if event.get('label'):
                self.step['phase'].set_text(user_messages.friendly_status(event['label']).rstrip('.…') + '…')
            return
        game = next((g for g in self.games if g['name'] == event.get('game')), None)
        total = event.get('total') or len(self.games)
        self._step_show('Checking', game, max(0, event.get('checked', 0) - 1), total, user_messages.friendly_status(event.get('label', '')),
                        event.get('checked', 0) / max(1, total))

    def show_review(self, review, on_confirm, details=None, enabled=True, trust=None, note=None, extra=None):
        view, t, owner = self.view, self.view.theme, self.owner
        self.stage = 'review'
        self.review = review
        self.on_confirm = on_confirm
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(20))
        count = len(review.get('rows', []))
        summary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(10))
        summary.append(view.label(f"{count} game{'s' if count != 1 else ''} ready" if count else 'Nothing ready yet', 'gm-h2'))
        summary.append(view.label(' · '.join(details or [self.verb]), 'gm-p', wrap=True))
        content.append(summary)
        if review.get('rows'):
            rows = []
            for item in review['rows']:
                game = item.get('art') or owner.review_game(item['name'], item.get('game'))
                rows.append(self._review_row(game, item['name'], user_messages.friendly_status(item.get('detail', '')) or 'Ready to ' + self.verb.lower(),
                                             item.get('badge', 'Ready'), True))
            content.append(view.group(rows, True))
        blocked = review.get('blocked', [])
        if blocked:
            heading = view.label(f'Skipped · {len(blocked)}', 'gm-strong')
            heading.set_margin_top(t.px(12))
            content.append(heading)
            content.append(view.group([self._review_row(owner.review_game(item['name']), item['name'], user_messages.friendly_error(item['reason']), 'Skipped', False)
                                       for item in blocked], True))
        if extra is not None and extra.get_parent() is None:
            content.append(extra)
        if note:
            content.append(view.label(note, 'gm-p', wrap=True))
        ready = bool(count) and enabled
        if trust:
            trusted = {'on': False}
            toggle = view.row_button(trust, 'No', None)
            def flip():
                trusted['on'] = not trusted['on']
                toggle.get_child()._value.set_text('Yes' if trusted['on'] else 'No')
                self.primary.set_sensitive(ready and trusted['on'])
            toggle.connect('clicked', lambda *_: flip())
            content.append(view.group([toggle], True))
        content.append(view.label('Preview mode · all file changes are disabled.' if owner.options.demo else 'Your files only change after you confirm.', 'gm-p'))
        self.primary.set_label(self.verb)
        self.primary.set_sensitive(ready and not trust)
        self.primary.set_visible(True)
        self.cancel_button.set_visible(True)
        self.cancel_button.set_label('Cancel' if count else 'Close')
        self._show(self.review_title, content, [self.cancel_button, self.primary])

    def _review_row(self, game, name, detail, badge, ready):
        view, t = self.view, self.view.theme
        row = Gtk.Box(spacing=t.px(22))
        for side, value in (('start', 22), ('end', 22), ('top', 18), ('bottom', 18)):
            getattr(row, 'set_margin_' + side)(t.px(value))
        row.append(view.picture((view.h.capsule_art_path(game) or view.h.poster_art_path(game)) if game else None, t.px(128), t.px(60)))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(6), hexpand=True, valign=Gtk.Align.CENTER)
        text.append(view.label(name, 'gm-strong', 'gm-rowtitle'))
        text.append(view.label(detail, 'gm-small', wrap=True, lines=2))
        row.append(text)
        row.append(view.badge(badge.upper(), 'gm-badge-ready' if ready else 'gm-badge-skipped'))
        wrapper = Gtk.Box()
        wrapper.append(row)
        wrapper.add_css_class('gm-review-row')
        if ready and game:
            wrapper.add_css_class(view.accent_class(game))
        return wrapper

    def show_progress(self, total):
        self.stage = 'progress'
        self.total = total
        self.step = self._step_layout()
        first = next((g for g in self.games if any(r['name'] == g['name'] for r in (self.review or {}).get('rows', []))), self.games[0] if self.games else None)
        self._step_show(self.progress_verb, first, 0, total, 'Starting')
        self.cancel_button.set_visible(True)
        self.cancel_button.set_sensitive(True)
        self.cancel_button.set_label('Cancel')
        self._show(None, self.step['root'], [self.cancel_button], can_back=False)

    def progress_event(self, event):
        game = next((g for g in self.games if g['name'] == event.get('game')), None)
        total = event.get('total') or self.total
        index = max(0, int(event.get('current', 1)) - 1) if 'current' in event else self.games.index(game) if game in self.games else 0
        self._step_show(self.progress_verb, game, index, total, user_messages.friendly_status(event.get('label', '')), event.get('fraction'))

    def finalizing(self):
        self.cancel_button.set_sensitive(False)
        if self.step and not (getattr(self.owner, 'operation_cancel', None) and self.owner.operation_cancel.is_set()):
            self.step['phase'].set_text('Finishing file management…')

    def show_working(self, text, cancellable=False):
        view, t = self.view, self.view.theme
        self.stage = 'working' if self.stage not in (None, 'checking') or not cancellable else 'checking'
        box = Gtk.Box(spacing=t.px(20), halign=Gtk.Align.CENTER)
        spinner = Gtk.Spinner(spinning=True)
        spinner.set_size_request(t.px(36), t.px(36))
        box.append(spinner)
        box.append(view.label(text, 'gm-strong'))
        self.cancel_button.set_visible(cancellable)
        self._show(None, box, [self.cancel_button] if cancellable else [], can_back=cancellable)

    def show_done(self, success, message, title=None, technical=None):
        view, t = self.view, self.view.theme
        self.stage = 'done'
        line = Gtk.Box(spacing=t.px(32))
        icon = view.icon('object-select-symbolic' if success else 'dialog-warning-symbolic', t.px(64))
        icon.add_css_class('gm-done-icon')
        if not success:
            icon.add_css_class('failed')
        line.append(icon)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(12), valign=Gtk.Align.CENTER, hexpand=True)
        text.append(view.label(title or ('Done' if success else 'Could not finish'), 'gm-h2'))
        text.append(view.label(message, 'gm-p', wrap=True))
        if technical:
            details = view.label(str(technical), 'gm-small', wrap=True)
            details.set_selectable(True)
            text.append(details)
        line.append(text)
        done = view.button('Done', self.close)
        self.done_button = done
        self._show(None, line, [done])
        GLib.idle_add(lambda: (done.grab_focus(), False)[1])
