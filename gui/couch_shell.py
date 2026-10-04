"""Focus-led game library sharing the desktop service and reviewed operations."""
from pathlib import Path
import re
import time
from gi.repository import Gtk, Adw, Gdk, GLib, Gio, Pango
import controller_input
import library_media
import ui_colors
import user_messages


CSS = b'''
.couch-prompt-button { background: transparent; border: 0; padding: 6px 2px; color: #c5c7cc; }
.couch-prompt-button:hover { background: #292b30; }
.couch-prompts { transition: opacity 180ms ease-out; }
.couch-shell.bottom-navigation .couch-prompts { font-size: 12px; }
.couch-shell.bottom-navigation .couch-prompt-button { padding: 2px; }

.couch-shell { background: #101113; color: #fafafa; }
.couch-game-meta { font-size: 15px; color: #c5c7cc; }
.couch-game-summary { font-size: 16px; color: #c5c7cc; }
.couch-badges { font-size: 12px; color: #c5c7cc; }
.couch-tab.focused { outline: 2px solid #fafafa; outline-offset: 2px; }
.couch-shell .couch-library-action { background: #f1f1f2; color: #202124; }
.couch-shade {
  background-image: linear-gradient(0deg, #101113 0%, #101113 22%, rgba(16,17,19,0.72) 43%, rgba(16,17,19,0.12) 76%, rgba(16,17,19,0.58) 100%),
                    linear-gradient(90deg, rgba(16,17,19,0.78), rgba(16,17,19,0.10) 75%);
}
.couch-shell.panel-open .couch-shade { background: rgba(16,17,19,0.92); }
.couch-shell.library-open .couch-shade { background: rgba(16,17,19,0.97); }
.couch-content { padding: 30px 52px 24px; }
.couch-brand { font-size: 20px; font-weight: 700; }
.couch-context { font-size: 14px; font-weight: 500; color: #c2c4c8; background: #101113; border-radius: 12px; padding: 6px 10px; }
.couch-tabs { border-radius: 24px; background: #1c1d20; padding: 4px; }
.couch-shell button, .couch-shell row { background-image: none; box-shadow: none; }
.couch-tab { background: transparent; box-shadow: none; border: none; border-radius: 20px; padding: 10px 22px; color: #d8d9dc; font-size: 16px; font-weight: 600; }
.couch-tab.active { background: rgba(245,245,250,0.16); color: white; }
.couch-tab.focused { background: #fafafa; color: #191a1d; }
.couch-title { font-size: 52px; font-weight: 750; letter-spacing: -1.5px; }
.couch-detail { font-size: 18px; font-weight: 450; color: #d1d2d5; }
.couch-section { font-size: 23px; font-weight: 650; letter-spacing: -0.4px; }
.couch-subtle { font-size: 15px; color: #b2b4ba; }
.couch-tile { background: transparent; border: none; box-shadow: none; padding: 8px; border-radius: 18px; }
.couch-tile:focus { outline: none; }
.couch-cover { border-radius: 12px; background: #27292d; }
.couch-tile.focused .couch-cover { outline: 3px solid #fafafa; outline-offset: 4px; }
.couch-tile-title { font-size: 16px; font-weight: 550; color: #c8c9cc; }
.couch-tile.focused .couch-tile-title { color: white; }
.couch-library-grid { padding: 8px; }
.couch-library-header { margin: 12px 0 6px; }
.couch-view-switch { background: #202226; border-radius: 16px; padding: 4px; }
.couch-view { background: transparent; color: #c9cbd1; box-shadow: none; border: none; border-radius: 12px; padding: 10px 16px; font-size: 15px; font-weight: 550; }
.couch-view.active { background: #37393f; color: #fafafa; }
.couch-list-row { background: #1b1d21; border: none; box-shadow: none; border-radius: 0; padding: 10px 18px; border-bottom: 1px solid rgba(255,255,255,0.07); color: #fafafa; }
.couch-list-row.joined-first { border-top-left-radius: 12px; border-top-right-radius: 12px; }
.couch-list-row.joined-last { border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; border-bottom: 0; }
.couch-list-row:focus { outline: none; }
.couch-list-row.focused { background: #27292d; outline: 2px solid #fafafa; outline-offset: -2px; }
.couch-list-title { font-size: 20px; font-weight: 600; }
.couch-list-art { border-radius: 8px; background: #292b30; }
.couch-list-status { font-size: 15px; color: #c4c6cc; }
.couch-library-count { font-size: 16px; color: #b4b7be; }
.couch-action { padding: 16px 26px; border-radius: 16px; background: #2b2c2f; color: #f4f4f6; box-shadow: none; border: none; font-size: 19px; font-weight: 650; }
.couch-action.focused { background: #fafafa; color: #17181b; }
.couch-action:focus { outline: none; }
.couch-action:disabled { color: #9a9da5; background: #1e1f21; }
.couch-options { background: transparent; color: #f4f4f6; }
.couch-options row { border-radius: 16px; margin: 0 0 10px; padding: 18px 24px; min-height: 28px; background: #222326; }
.couch-options row label { font-size: 20px; font-weight: 550; }
.couch-options row:selected { background: #fafafa; color: #191a1d; }
.couch-options.nav-focused row:selected { background: #222326; color: #f4f4f6; }
.couch-options row:disabled { opacity: 0.45; }
.couch-options row:focus { outline: none; }
.couch-value { font-weight: 650; }
.couch-caption { font-size: 16px; color: #c1c3c8; }
.couch-panel-heading { font-size: 36px; font-weight: 700; letter-spacing: -0.8px; }
.couch-prompts { font-size: 14px; color: #b5b8bf; }
.couch-shell.compact .couch-content { padding: 22px 30px 18px; }
.couch-shell.compact .couch-title { font-size: 38px; letter-spacing: -0.8px; }
.couch-shell.compact .couch-tab { padding: 8px 16px; font-size: 14px; }
.couch-shell.compact .couch-detail { font-size: 16px; }
.couch-shell.compact .couch-action { padding: 14px 20px; font-size: 17px; }
.couch-shell.compact .couch-options row { padding: 9px 20px; margin-bottom: 8px; }
.couch-shell.compact .couch-options row label { font-size: 18px; }
.couch-shell.compact .couch-panel-heading { font-size: 30px; }
.couch-shell.compact .couch-view { padding: 9px 12px; font-size: 14px; }
.couch-shell.compact .couch-list-title { font-size: 18px; }
.couch-selection { background: #101113; border-radius: 8px; padding: 5px; }
.couch-shell .couch-settings { padding: 10px; min-width: 24px; min-height: 24px; }
'''

PAGES = ('dashboard', 'library', 'presets', 'dlss')
VIEWS = ('posters', 'capsules', 'list')


def label(text, style=None, wrap=False):
    widget = Gtk.Label(label=text, xalign=0, wrap=wrap)
    if style:
        widget.add_css_class(style)
    return widget


def clear(box):
    while box.get_first_child():
        box.remove(box.get_first_child())


class ControllerGlyph(Gtk.DrawingArea):
    """Fixed-aspect face buttons; PlayStation marks are drawn as geometry."""
    def __init__(self, family, key):
        super().__init__(content_width=26, content_height=26, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        self.family = family
        self.key = key
        self.update_property([Gtk.AccessibleProperty.LABEL], [f'{family.title()} {key} button'])
        self.set_draw_func(self.draw)

    def draw(self, _widget, context, width, height):
        context.save()
        size = min(width, height)
        context.translate((width - size) / 2, (height - size) / 2)
        context.scale(size / 26, size / 26)
        context.set_source_rgb(0.82, 0.83, 0.85)
        if self.family == 'playstation':
            context.set_line_width(2)
            context.set_line_join(1)
            context.set_line_cap(1)
            if self.key == '×':
                context.move_to(6, 6); context.line_to(20, 20)
                context.move_to(20, 6); context.line_to(6, 20)
            elif self.key == '○':
                context.arc(13, 13, 9, 0, 6.283185)
            elif self.key == '△':
                context.move_to(13, 3); context.line_to(24, 22)
                context.line_to(2, 22); context.close_path()
            else:
                context.rectangle(4, 4, 18, 18)
            context.stroke()
        else:
            context.arc(13, 13, 12, 0, 6.283185)
            context.fill()
            context.set_source_rgb(0.10, 0.11, 0.13)
            context.select_font_face('sans-serif', 0, 1)
            context.set_font_size(14)
            x, y, w, h, _, _ = context.text_extents(self.key)
            context.move_to((26 - w) / 2 - x, (26 - h) / 2 - y)
            context.show_text(self.key)
        context.restore()


class CouchShell(Gtk.Overlay):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.page = 'dashboard'
        self.game_origin = 'dashboard'
        self.preset_origin = 'dashboard'
        self.library_view = owner.settings.get('library_view', 'posters')
        self.view_index = 0
        self.layout_width = 1280
        self.columns = 1
        self.game = None
        self.entries = []
        self.controls = []
        self.pending = {}
        self.dlss_selection = None
        self.selection_kind = 'dlss'
        self.utility_origin = 'dashboard'
        self.scroll_tick = 0
        self.selection = {}
        self.current = 0
        self.art_path = None
        self.zone = 'content'
        self.tab_index = 0
        self.compact = None
        self.add_css_class('couch-shell')
        self.provider = Gtk.CssProvider()
        self.provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 4)
        self.accent_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.accent_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        self.scale_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.scale_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 6)
        self.layout_height = 820
        self.accent_color = None
        self.apply_accent(None)
        self.art = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        self.art.set_opacity(0.9)
        self.set_child(self.art)
        shade = Gtk.Box()
        shade.add_css_class('couch-shade')
        shade.set_can_target(False)
        self.add_overlay(shade)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        self.main = main
        self.hint_timer = 0
        self.navigation_position = None
        main.add_css_class('couch-content')
        self.add_overlay(main)

        top = Gtk.CenterBox()
        self.top = top
        brand = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_file(str(Path(__file__).parent / 'icons/rtxforge-artwork.svg'))
        icon.set_pixel_size(30)
        brand.append(icon)
        brand.append(label('rtxForge', 'couch-brand'))
        top.set_start_widget(brand)
        tabs = Gtk.Box()
        tabs.add_css_class('couch-tabs')
        self.tab_bar = tabs
        self.tabs = []
        for title, page in [('Dashboard', 'dashboard'), ('Library', 'library'), ('Presets', 'presets'), ('DLSS Files', 'dlss')]:
            button = Gtk.Button(label=title)
            button.add_css_class('couch-tab')
            button.connect('clicked', lambda _, p=page: self.open(p))
            tabs.append(button)
            self.tabs.append(button)
        top.set_center_widget(tabs)
        self.context = label('Preview' if owner.options.demo else 'Game Mode', 'couch-context')
        utilities = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER)
        utilities.append(self.context)
        self.settings_button = Gtk.Button(icon_name='emblem-system-symbolic', tooltip_text='Settings')
        self.settings_button.update_property([Gtk.AccessibleProperty.LABEL], ['Settings'])
        self.settings_button.add_css_class('couch-tab')
        self.settings_button.add_css_class('couch-settings')
        self.settings_button.connect('clicked', lambda _: self.open('settings'))
        utilities.append(self.settings_button)
        self.tabs.append(self.settings_button)
        top.set_end_widget(utilities)
        main.append(top)

        self.body = Gtk.Stack(vexpand=True, hhomogeneous=False, vhomogeneous=False)
        self.body.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.body.set_transition_duration(180)
        main.append(self.body)
        feature = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, vexpand=True, valign=Gtk.Align.END)
        hero.set_margin_bottom(8)
        self.title = label('Your library', 'couch-title', wrap=True)
        self.title.set_max_width_chars(32)
        self.title.set_halign(Gtk.Align.START)
        hero.append(self.title)
        self.detail = label('', 'couch-detail', wrap=True)
        self.detail.set_max_width_chars(64)
        hero.append(self.detail)
        self.game_metadata = label('', 'couch-game-meta', wrap=True)
        self.game_metadata.set_max_width_chars(70)
        hero.append(self.game_metadata)
        self.game_summary = label('', 'couch-game-summary', wrap=True)
        self.game_summary.set_max_width_chars(70)
        self.game_summary.set_lines(2)
        self.game_summary.set_ellipsize(Pango.EllipsizeMode.END)
        hero.append(self.game_summary)
        feature.append(hero)
        self.library = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        heading = Gtk.Box()
        heading.append(label('Your games', 'couch-section'))
        self.count = label('', 'couch-subtle')
        self.count.set_hexpand(True)
        self.count.set_halign(Gtk.Align.END)
        heading.append(self.count)
        self.library_link = Gtk.Button(label='View library', tooltip_text='Open the full library')
        self.library_link.add_css_class('couch-view')
        self.library_link.connect('clicked', lambda _: self.open('library'))
        heading.append(self.library_link)
        for icon,action in [('pan-start-symbolic','left'),('pan-end-symbolic','right')]:
            control=Gtk.Button(icon_name=icon,tooltip_text='Previous game' if action=='left' else 'Next game')
            control.add_css_class('couch-view')
            control.connect('clicked',lambda _,action=action:self.navigate(action))
            heading.append(control)
        self.library.append(heading)
        self.shelf = Gtk.Box(spacing=12)
        self.shelf_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC, vscrollbar_policy=Gtk.PolicyType.NEVER)
        self.shelf_scroll.set_min_content_height(186)
        self.shelf_scroll.set_child(self.shelf)
        self.library.append(self.shelf_scroll)
        feature.append(self.library)
        self.game_actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.actions = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=4,max_children_per_line=4,row_spacing=12,column_spacing=12)
        self.action_tiles=Adw.BreakpointBin(child=self.actions,width_request=400,height_request=108)
        breakpoint=Adw.Breakpoint.new(Adw.BreakpointCondition.parse('max-width: 1000px'))
        breakpoint.add_setter(self.actions,'min-children-per-line',2)
        breakpoint.add_setter(self.actions,'max-children-per-line',2)
        breakpoint.add_setter(self.action_tiles,'height-request',228)
        self.action_tiles.add_breakpoint(breakpoint)
        self.game_actions.append(self.action_tiles)
        self.action_hint = label('', 'couch-caption', wrap=True)
        self.action_hint.set_max_width_chars(70)
        self.action_hint.set_size_request(-1, 50)
        self.game_actions.append(self.action_hint)
        self.game_actions.set_margin_bottom(32)
        feature.append(self.game_actions)
        self.body.add_named(feature, 'feature')

        library_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        library_header = Gtk.Box(spacing=24)
        library_header.add_css_class('couch-library-header')
        library_title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        self.library_heading = label('Library', 'couch-panel-heading')
        library_title.append(self.library_heading)
        self.library_count = label('', 'couch-library-count')
        library_title.append(self.library_count)
        library_header.append(library_title)
        self.view_buttons = []
        self.library_action = self.owner.make_action_button('Install to all',lambda _:self.library_primary_action())
        self.library_action.add_css_class('couch-action')
        self.library_action.add_css_class('couch-library-action')
        self.view_buttons.append(self.library_action)
        library_header.append(self.library_action)
        library_page.append(library_header)
        self.grid = Gtk.Grid(column_spacing=18, row_spacing=20, column_homogeneous=True, hexpand=True, valign=Gtk.Align.START)
        self.grid.add_css_class('couch-library-grid')
        self.grid_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.EXTERNAL, vexpand=True)
        self.grid_scroll.set_child(self.grid)
        library_page.append(self.grid_scroll)
        self.body.add_named(library_page, 'library')

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.panel = panel
        self.panel.set_size_request(660, -1)
        headings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.heading = label('', 'couch-panel-heading')
        self.panel_detail = label('', 'couch-caption')
        self.panel_detail.set_ellipsize(Pango.EllipsizeMode.END)
        headings.append(self.heading)
        headings.append(self.panel_detail)
        panel.append(headings)
        self.menu = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=False)
        self.menu.add_css_class('couch-options')
        self.menu.connect('row-selected', self.selected)
        self.menu.connect('row-activated', lambda _, row: self.activate(row.get_index()))
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        scroll.set_propagate_natural_height(True)
        scroll.set_max_content_height(360)
        scroll.set_child(self.menu)
        panel.append(scroll)
        self.panel_scroll = scroll
        self.hint = label('', 'couch-caption', wrap=True)
        self.hint.set_max_width_chars(64)
        panel.append(self.hint)
        self.body.add_named(panel, 'panel')

        self.bottom_nav = Gtk.Box(halign=Gtk.Align.CENTER)
        main.append(self.bottom_nav)
        footer = Gtk.Box()
        self.footer = footer
        self.prompts = Gtk.Box(spacing=22)
        self.prompts.add_css_class('couch-prompts')
        footer.append(self.prompts)
        self.footer_note = label('', 'couch-subtle')
        self.footer_note.set_ellipsize(Pango.EllipsizeMode.END)
        self.footer_note.set_hexpand(True)
        self.footer_note.set_halign(Gtk.Align.END)
        footer.append(self.footer_note)
        main.append(footer)
        self.apply_navigation_preferences()
        self.render()

    def panel_navigation(self,dialog):
        nav=Gtk.Box(spacing=4,halign=Gtk.Align.CENTER)
        nav.add_css_class('couch-tabs')
        nav.add_css_class('couch-shell')
        for page,title in [('dashboard','Dashboard'),('library','Library'),('presets','Presets'),('dlss','DLSS Files'),('settings','Settings')]:
            control=Gtk.Button(icon_name='emblem-system-symbolic',tooltip_text='Settings') if page=='settings' else Gtk.Button(label=title)
            control.add_css_class('couch-tab')
            if self.page==page:control.add_css_class('active')
            control.set_sensitive(not self.owner.busy or self.owner.task_kind=='art')
            def go(*_,page=page):
                if not dialog.get_can_close():return
                dialog.close()
                self.open(page)
            control.connect('clicked',go)
            nav.append(control)
        return nav

    def apply_navigation_preferences(self):
        position=self.owner.settings.get('navigation_position','top')
        if position != self.navigation_position:
            if self.navigation_position == 'bottom':self.bottom_nav.remove(self.tab_bar)
            else:self.top.set_center_widget(None)
            if position == 'bottom':self.bottom_nav.append(self.tab_bar)
            else:self.top.set_center_widget(self.tab_bar)
            self.navigation_position=position
            self.bottom_nav.set_visible(position=='bottom')
            self.add_css_class('bottom-navigation') if position=='bottom' else self.remove_css_class('bottom-navigation')
            self.footer_note.set_visible(position!='bottom')
            self.prompts.set_hexpand(position=='bottom')
            self.prompts.set_halign(Gtk.Align.CENTER if position=='bottom' else Gtk.Align.START)
            self.wake_hints()
        auto=position=='bottom' or self.owner.settings.get('controller_hints','always')=='auto'
        if auto != getattr(self,'hints_auto',None):
            self.hints_auto=auto
            self.wake_hints()

    def wake_hints(self):
        if self.hint_timer:GLib.source_remove(self.hint_timer)
        self.prompts.set_opacity(1)
        self.prompts.set_can_target(True)
        self.hint_timer=0
        if getattr(self,'hints_auto',False):self.hint_timer=GLib.timeout_add(3500,self.hide_hints)

    def hide_hints(self):
        if self.prompts.get_focus_child():
            self.hint_timer=GLib.timeout_add(3500,self.hide_hints)
            return False
        self.hint_timer=0
        # Preserve the navigation's allocation while hints fade away.
        self.prompts.set_opacity(0)
        self.prompts.set_can_target(False)
        return False

    def update_prompts(self):
        family = self.owner.settings.get('controller_glyphs', 'auto')
        if family == 'auto':
            family = self.owner.controller.family
        keys = controller_input.GLYPHS.get(family, controller_input.GLYPHS['generic'])
        caption = 'Select' if self.dlss_selection is not None else 'Open' if self.page in ('dashboard', 'library') else 'Select'
        spec = (family, keys[0], keys[1], keys[2], self.page, caption, self.dlss_selection is not None)
        if spec == getattr(self, 'prompt_spec', None):
            return
        self.prompt_spec = spec
        clear(self.prompts)
        prompts = [(keys[0], caption), (keys[1], 'Back')]
        prompts.append((keys[2], 'Library'))
        for key, text in prompts:
            pair = Gtk.Box(spacing=7, valign=Gtk.Align.CENTER)
            pair.append(label(key) if family == 'generic' else ControllerGlyph(family, key))
            pair.append(label(text))
            control = Gtk.Button(child=pair)
            control.add_css_class('couch-prompt-button')
            action = 'accept' if key == keys[0] else 'back' if key == keys[1] else 'search'
            control.connect('clicked', lambda _, action=action: self.navigate(action))
            self.prompts.append(control)
        self.footer_note.set_text('Left / right to adjust' if self.page in ('presets', 'game_presets', 'settings') else 'Bumpers switch pages')

    def set_game(self, game):
        self.game = game
        self.apply_accent(game)
        self.title.set_text(game['name'])
        if game.get('blocked'):
            status = user_messages.friendly_error(game['blocked'])
        elif game.get('installed'):
            status = game.get('profile', 'Features installed') + ' installed'
            if game.get('nr_enabled') is not None:
                status += '  ·  Neural Rendering ' + ('on' if game['nr_enabled'] else 'off')
        else:
            status = 'Ready to configure'
        self.detail.set_text(status)
        values = [game.get('source'), game.get('developers'), game.get('release'), self.owner.game_status_label(game)]
        self.game_metadata.set_text(' · '.join(', '.join(map(str, value)) if isinstance(value, (list, tuple)) else str(value) for value in values if value))
        self.game_summary.set_text(re.sub('<[^>]+>', '', str(game.get('description') or '')))
        # A portrait cover is never enlarged into a landscape background.
        path = game.get('hero') or game.get('capsule')
        if path != self.art_path:
            self.art_path = path
            try:
                self.art.set_filename(path) if path else self.art.set_paintable(None)
            except (GLib.Error, OSError):
                self.art.set_paintable(None)

    def apply_accent(self, game):
        # Consume Classic's resolver and saved override; never create another
        # artwork palette or preference store for the controller interface.
        color = '#76b900'
        if game:
            shared = self.owner._ensure_game_accent(game) or 'art-76b900'
            color = '#' + shared.removeprefix('art-') if game.get('blocked') else self.owner.settings.get('game_accents', {}).get(game['game']) or '#' + shared.removeprefix('art-')
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            color = '#76b900'
        if color == self.accent_color:
            return
        self.accent_color = color
        foreground = ui_colors.readable(ui_colors.mix('#000000', color, 0.82), color)
        ring = ui_colors.vibrant_readable(color, '#101113', 3.0)
        tab_background = ui_colors.mix(color, '#1c1d20', 0.22)
        tab_foreground = ui_colors.readable(color, tab_background)
        self.accent_provider.load_from_data(f'''
          .couch-shell .couch-selection check:checked {{ background: {color}; color: {foreground}; border-color: {color}; }}
          .couch-shell .couch-tile.focused .couch-cover {{ outline-color: {ring}; }}
          .couch-shell .couch-action.focused,
          .couch-shell .couch-options:not(.nav-focused) row:selected {{ background: {color}; color: {foreground}; }}
          .couch-shell .couch-tab.active:not(.focused) {{ background: #37393f; color: #fafafa; }}
          .couch-shell .couch-view.active:not(.focused) {{ background: #37393f; color: #fafafa; }}
          .couch-shell .couch-view.focused {{ background: {color}; color: {foreground}; }}
          .couch-shell .couch-list-row.focused {{ background: {ui_colors.mix(color, '#101113', 0.13)}; outline-color: {ring}; }}
        '''.encode())

    def entry(self, title, action=None, value=None, adjust=None, enabled=True, game=None, hint=''):
        self.entries.append(dict(title=title, action=action, value=value, adjust=adjust, enabled=enabled, game=game, hint=hint))

    def navigate(self, action):
        self.wake_hints()
        if action == 'back':
            self.back()
            return
        if action == 'menu':
            self.open('menu')
            return
        if action == 'settings':
            self.open('settings')
            return
        if action == 'search':
            self.open('library')
            return
        if action in ('previous', 'next'):
            if self.tab_index == len(PAGES):
                self.tab_index = -1 if action == 'next' else 0
            self.tab_index = (self.tab_index + (1 if action == 'next' else -1)) % len(PAGES)
            self.open(PAGES[self.tab_index])
            return
        if self.zone == 'nav':
            if action in ('left', 'right'):
                self.tab_index = (self.tab_index + (1 if action == 'right' else -1)) % (len(PAGES) + 1)
            elif action == 'accept':
                self.open('settings' if self.tab_index == len(PAGES) else PAGES[self.tab_index])
            elif action == ('up' if self.navigation_position=='bottom' else 'down'):
                self.zone = 'views' if self.page == 'library' and self.navigation_position!='bottom' else 'content'
                if self.zone == 'content':
                    self.focus(self.current)
            self.update_tabs()
            return
        if self.zone == 'views':
            if action in ('left', 'right'):
                self.view_index = (self.view_index + (1 if action == 'right' else -1)) % len(self.view_buttons)
            elif action == 'accept':
                self.library_primary_action()
            elif action == 'down':
                self.zone = 'content'
                self.focus(self.current)
            elif action == 'up' and self.navigation_position!='bottom':
                self.zone = 'nav'
            self.update_tabs()
            return
        if self.page in ('game','tools') and self.controls:
            first_y=self.controls[0].get_parent().get_allocation().y
            columns=sum(control.get_parent().get_allocation().y==first_y for control in self.controls)
            columns=max(1,columns)
            if action=='up' and self.current<columns:
                if self.navigation_position!='bottom':self.zone='nav';self.update_tabs()
            elif action=='down' and self.current+columns>=len(self.controls):
                if self.navigation_position=='bottom':self.zone='nav';self.update_tabs()
            elif action in ('left','right','up','down'):
                if action=='left' and self.current%columns==0:return
                if action=='right' and (self.current%columns==columns-1 or self.current==len(self.controls)-1):return
                delta={'left':-1,'right':1,'up':-columns,'down':columns}[action]
                target=self.current+delta
                while 0<=target<len(self.entries) and not self.entries[target]['enabled']:
                    target+=1 if delta>0 else -1
                if 0<=target<len(self.entries):self.focus(target)
            elif action=='accept':self.activate(self.current)
            return
        if self.navigation_position=='bottom' and action=='down' and (self.page in ('dashboard','game') or self.current >= len(self.entries)-(self.columns if self.page=='library' else 1)):
            self.zone='nav'
            self.update_tabs()
            return
        if self.page == 'library':
            if action == 'up' and self.current < self.columns:
                self.zone = 'views'
                self.update_tabs()
            elif action in ('up', 'down', 'left', 'right'):
                delta = {'up': -self.columns, 'down': self.columns, 'left': -1, 'right': 1}[action]
                if action == 'left' and self.current % self.columns == 0:
                    return
                if action == 'right' and self.current % self.columns == self.columns - 1:
                    return
                self.focus(max(0, min(len(self.entries) - 1, self.current + delta)))
            elif action == 'accept':
                self.activate(self.current)
            return
        horizontal = self.page in ('dashboard', 'game')
        if self.navigation_position!='bottom' and action == 'up' and (horizontal or not any(entry['enabled'] for entry in self.entries[:self.current])):
            self.zone = 'nav'
            self.update_tabs()
            return
        if (horizontal and action in ('left', 'right')) or (not horizontal and action in ('up', 'down')):
            direction = 1 if action in ('right', 'down') else -1
            index = self.current
            for _ in self.entries:
                index = max(0, min(len(self.entries) - 1, index + direction))
                if self.entries[index]['enabled']:
                    self.focus(index)
                    break
        elif action == 'accept':
            self.activate(self.current)
        elif action in ('left', 'right') and self.entries:
            adjust = self.entries[self.current].get('adjust')
            if adjust:
                adjust(1 if action == 'right' else -1)
                self.render(self.current)

    def update_tabs(self):
        active = len(PAGES) if self.page == 'settings' else PAGES.index(self.page) if self.page in PAGES else PAGES.index(self.game_origin)
        for i, button in enumerate(self.tabs):
            button.add_css_class('active') if i == active else button.remove_css_class('active')
            button.add_css_class('focused') if self.zone == 'nav' and i == self.tab_index else button.remove_css_class('focused')
        self.menu.add_css_class('nav-focused') if self.zone == 'nav' else self.menu.remove_css_class('nav-focused')
        for i, button in enumerate(self.controls):
            button.add_css_class('focused') if self.zone == 'content' and i == self.current else button.remove_css_class('focused')
        for i, button in enumerate(self.view_buttons):
            button.remove_css_class('active')
            button.add_css_class('focused') if self.zone == 'views' and i == self.view_index else button.remove_css_class('focused')

    def selected(self, _, row):
        if row is not None:
            self.current = row.get_index()
            self.selection[self.page] = self.current

    def focus(self, index):
        if not self.entries:
            return
        self.current = max(0, min(index, len(self.entries) - 1))
        self.selection[self.page] = self.current
        entry = self.entries[self.current]
        if entry.get('game'):
            self.set_game(entry['game'])
        if self.controls:
            button = self.controls[self.current]
            button.grab_focus()
            if self.page in ('dashboard', 'library'):
                GLib.idle_add(self.reveal_selection)
            self.action_hint.set_text(entry.get('hint') or self.hint.get_text())
            if self.page == 'dashboard':
                self.count.set_text(f'{self.current + 1} of {len(self.entries)} · {self.owner.settings.get("dashboard_row_count",5)} across · browse left / right')
        else:
            row = self.menu.get_row_at_index(self.current)
            self.menu.select_row(row)
            if row and row.get_parent():
                row.grab_focus()
        self.update_tabs()

    def reveal_selection(self):
        if self.page not in ('dashboard', 'library') or not self.controls:
            return False
        button = self.controls[min(self.current, len(self.controls) - 1)]
        allocation = button.get_allocation()
        is_grid = self.page == 'library'
        adjustment = self.grid_scroll.get_vadjustment() if is_grid else self.shelf_scroll.get_hadjustment()
        start = allocation.y if is_grid else allocation.x
        end = start + (allocation.height if is_grid else allocation.width)
        position = adjustment.get_value()
        target = max(0, start - 8) if start < position else end - adjustment.get_page_size() + 8 if end > position + adjustment.get_page_size() else position
        target = max(adjustment.get_lower(), min(target, adjustment.get_upper() - adjustment.get_page_size()))
        if self.scroll_tick:
            self.remove_tick_callback(self.scroll_tick)
            self.scroll_tick = 0
        settings = Gtk.Settings.get_default()
        if not settings or not settings.get_property('gtk-enable-animations') or abs(target - position) < 1:
            adjustment.set_value(target)
            return False
        began = time.monotonic()
        def animate(_widget, _clock):
            t = min(1.0, (time.monotonic() - began) / .22)
            adjustment.set_value(position + (target - position) * (1 - (1 - t) ** 3))
            if t >= 1:
                self.scroll_tick = 0
                return False
            return True
        self.scroll_tick = self.add_tick_callback(animate)
        return False

    def open_game(self, game):
        if self.page in ('dashboard', 'library'):
            self.game_origin = self.page
        self.set_game(game)
        self.open('game')

    def set_library_view(self, view):
        if view not in VIEWS:
            return
        self.library_view = view
        self.view_index = 0
        # Trigger Classic's normal preference/render path as well.
        self.owner.view_buttons[view].set_active(True)
        self.render(self.current)

    def grid_dimensions(self):
        available = max(380, self.layout_width - (76 if self.compact else 120))
        if self.library_view == 'list':
            return 1, available, 82
        target = (175 if self.compact else 210) if self.library_view == 'posters' else 320
        columns = max(2, min(7 if self.library_view == 'posters' else 5, int(available / target)))
        width = max(140, int((available - 18 * (columns - 1)) / columns) - 16)
        ratio = self.owner.library_card_geometry(view=self.library_view)[5]
        height = round(width / ratio)
        return columns, width, height

    def activate(self, index):
        if index >= len(self.entries) or self.owner.busy:
            return
        entry = self.entries[index]
        if entry['enabled'] and entry['action']:
            entry['action']()

    def open(self, page):
        returning_to_presets = page == 'presets' and self.page == 'library' and self.dlss_selection is not None and self.selection_kind == 'presets'
        if page in ('menu', 'settings') and self.page not in ('menu', 'settings'):
            self.utility_origin = self.page
        if page != 'library':
            self.dlss_selection = None
        if page in ('game', 'features', 'tools', 'game_presets') and self.game is None:
            page = 'dashboard'
        if page == 'library':
            self.library_view = self.owner.settings.get('library_view', 'posters')
            self.view_index = 0
        if page == 'presets' and self.page != 'presets':
            self.preset_origin = self.page if self.page in ('dashboard', 'library', 'game') else self.game_origin
        if page in ('presets', 'game_presets') and not returning_to_presets:
            source = self.game if page == 'game_presets' else self.owner.settings
            self.pending = {key: source.get(key) if source.get(key) is not None else self.owner.settings[key] for key in ('nr_strength', 'sharpening_strength', 'mfg_multiplier')}
        self.page = page
        self.zone = 'content'
        self.tab_index = len(PAGES) if page == 'settings' else PAGES.index(page) if page in PAGES else PAGES.index(self.game_origin)
        self.render()

    def back(self):
        if self.page == 'library' and self.dlss_selection is not None:
            self.open('presets' if self.selection_kind == 'presets' else 'dlss')
            return
        if self.zone in ('nav', 'views'):
            self.zone = 'content'
            self.update_tabs()
        elif self.page == 'dashboard':
            return
        elif self.page == 'library':
            self.open('dashboard')
        elif self.page == 'presets':
            self.open(self.preset_origin)
        elif self.page == 'features_all':
            self.open('library')
        elif self.page in ('features', 'tools', 'game_presets'):
            self.open('game')
        elif self.page == 'game':
            self.open(self.game_origin)
        elif self.page in ('menu', 'settings'):
            self.open(self.utility_origin)
        else:
            self.open('dashboard')

    def install(self, mode):
        self.owner.profile_group.set_active_name(mode)
        targets = [g for g in self.owner.games if g.get('test_record', {}).get('status') != 'Bench'] if self.page == 'features_all' else [self.game]
        self.owner.launch_action('install', targets=targets, visual_settings=dict(self.owner.settings), _presets_confirmed=True)

    def select_dlss_games(self):
        self.selection_kind = 'dlss'
        self.dlss_selection = set()
        self.open('library')

    def preset_targets(self):
        return [game for game in self.owner.games if game.get('installed') and not game.get('blocked') and game.get('test_record', {}).get('status') != 'Bench']

    def select_preset_games(self):
        self.selection_kind = 'presets'
        self.dlss_selection = set()
        self.open('library')

    def apply_presets(self, targets):
        eligible = {game['game'] for game in self.preset_targets()}
        targets = [game for game in targets if game['game'] in eligible]
        if targets:
            self.owner.launch_action('reset', targets=targets, visual_settings=dict(self.pending))

    def toggle_dlss_game(self, game):
        if game.get('blocked') or (self.selection_kind == 'presets' and not game.get('installed')):
            return
        key = game['game']
        self.dlss_selection.symmetric_difference_update({key})
        self.render(self.current)

    def library_primary_action(self):
        if not self.library_action.get_sensitive():
            return
        if self.dlss_selection is not None:
            targets = [g for g in self.owner.games if g['game'] in self.dlss_selection]
            if self.selection_kind == 'presets':
                self.apply_presets(targets)
            else:
                self.owner.update_dlss_games(targets)
        else:
            self.game_origin = 'library'
            self.open('features_all')

    def selection_marker(self, game):
        marker = Gtk.CheckButton(active=game.get('game') in self.dlss_selection, can_focus=False, can_target=False)
        marker.add_css_class('couch-selection')
        marker.set_tooltip_text('Selected' if marker.get_active() else 'Not selected')
        return marker

    def adjust(self, key, direction):
        choices = [0, 2, 3, 4, 5, 6, 'auto'] if key == 'mfg_multiplier' else [round(i / 10, 1) for i in range(21 if key == 'nr_strength' else 11)]
        current = self.pending[key]
        index = choices.index(current) if current in choices else 0
        self.pending[key] = choices[max(0, min(len(choices) - 1, index + direction))]

    def setting(self, key, direction, choices):
        current = self.owner.settings.get(key)
        index = choices.index(current) if current in choices else 0
        self.owner.settings[key] = choices[(index + direction) % len(choices)]
        if not self.owner.options.demo:
            library_media.save_settings(self.owner.service.config, self.owner.settings)
        self.owner.apply_display_preferences()
        self.update_prompts()

    def build_entries(self):
        self.entries = []
        self.hint.set_text('')
        if self.page in ('dashboard', 'library'):
            for game in self.owner.games:
                self.entry(game['name'], lambda g=game: self.toggle_dlss_game(g) if self.dlss_selection is not None else self.open_game(g), game=game, enabled=self.dlss_selection is None or (not game.get('blocked') and (self.selection_kind != 'presets' or bool(game.get('installed')))))
            if not self.entries:
                self.entry('Refresh library', self.owner.scan)
                self.detail.set_text('Add a game folder in Classic to get started.')
        elif self.page == 'game':
            game = self.game
            self.entry('Configure', lambda: self.open('features'), enabled=not game.get('blocked'), hint='Choose Neural Rendering and frame generation for this game.')
            self.entry('Presets', lambda: self.open('game_presets'), enabled=game.get('installed', False), hint='Adjust graphics features for this game. Your other games stay as they are.')
            self.entry('Tools', lambda: self.open('tools'), hint='Diagnose Neural Rendering, update DLSS, or restore original files.')
            self.entry('Play', lambda: Gio.AppInfo.launch_default_for_uri('steam://rungameid/' + str(game['appid']), None), enabled=game.get('source') == 'Steam' and str(game.get('appid', '')).isdigit() and not self.owner.options.demo, hint='Launch this game in Steam.')
        elif self.page in ('features', 'features_all'):
            self.entry('Neural Rendering + MFG', lambda: self.install('nr-mfg'))
            self.entry('Frame generation only', lambda: self.install('mfg-only'))
            self.entry('Neural Rendering only', lambda: self.install('nr-only'), enabled=self.owner.settings.get('runtime_provider') in ('dlss-unlocked', 'custom'))
            self.hint.set_text('Review every file change before installing. Your current presets are used.')
        elif self.page in ('presets', 'game_presets'):
            per_game = self.page == 'game_presets'
            mode = (self.game.get('feature_mode') or {'MFG Only': 'mfg-only', 'NR Only': 'nr-only'}.get(self.game.get('profile'), 'nr-mfg')) if per_game else 'nr-mfg'
            for key, title in [('nr_strength', 'Neural Rendering'), ('mfg_multiplier', 'Frame generation'), ('sharpening_strength', 'Sharpening')]:
                raw = self.pending[key]
                value = 'In game' if raw == 'auto' else 'Off' if raw == 0 else str(raw) + ('×' if key == 'mfg_multiplier' else '')
                self.entry(title, value=value, adjust=lambda delta, key=key: self.adjust(key, delta), enabled=not (key == 'nr_strength' and mode == 'mfg-only') and not (key == 'mfg_multiplier' and mode == 'nr-only'))
            if per_game:
                self.entry('Apply to this game', lambda: self.apply_presets([self.game]), enabled=bool(self.game.get('installed')) and not self.game.get('blocked'))
                self.hint.set_text('Only this game will change. Review the changes before applying.')
            else:
                eligible = self.preset_targets()
                self.entry(f'Apply to all configured games ({len(eligible)})', lambda: self.apply_presets(self.preset_targets()), enabled=bool(eligible))
                self.entry('Select games to apply', self.select_preset_games, enabled=bool(eligible))
                self.hint.set_text('Apply to all configured games, or choose your games.')
        elif self.page == 'dlss':
            self.entry('Update all', lambda: self.owner.update_dlss_games(self.owner.games), enabled=bool(self.owner.games))
            self.entry('Select games to update', self.select_dlss_games, enabled=bool(self.owner.games))
            self.hint.set_text('Keep native DLSS files up to date across your library. Previous files are backed up.' if self.owner.games else 'Add games to your Library to update their DLSS files.')
        elif self.page == 'tools':
            self.entry('Diagnose Neural Rendering', lambda: self.owner.show_diagnostics(self.game))
            self.entry('Update DLSS files', lambda: self.owner.manage_dlss_files(self.game), enabled=not self.owner.options.demo)
            self.entry('Restore DLSS files', lambda: self.owner.manage_dlss_files(self.game, restore=True), enabled=not self.owner.options.demo)
            self.entry('Restore original game files', lambda: self.owner.launch_action('uninstall', targets=[self.game]), enabled=self.game.get('installed', False))
            self.hint.set_text('ReShade and add-on imports are available in Classic with keyboard and mouse.')
        elif self.page == 'menu':
            self.entry('Dashboard', lambda: self.open('dashboard'))
            self.entry('Library', lambda: self.open('library'))
            self.entry('Packages', lambda: self.open('packages'))
            self.entry('Refresh library', self.owner.scan)
            for key,title,choices,captions in [
                ('ui_scale','UI scale',['auto',100,125,150,175,200],['Automatic','100%','125%','150%','175%','200%']),
                ('dashboard_view','Dashboard artwork',['capsules','posters'],['Wide','Poster']),
                ('dashboard_row_count','Games across shelf',list(range(3,9)),[str(n) for n in range(3,9)]),
                ('navigation_position','Navigation',['top','bottom'],['Top','Bottom']),
                ('controller_hints','Controller hints',['always','auto'],['Always visible','Hide when idle'])]:
                value=self.owner.settings.get(key,library_media.DEFAULTS[key])
                self.entry(title,value=captions[choices.index(value)],adjust=lambda d,key=key,choices=choices:self.setting(key,d,choices))
            self.entry('Desktop controls', lambda: self.owner.set_input_surface(False))
            self.entry('Quit rtxForge', self.owner.close)
        elif self.page == 'packages':
            import package_catalog
            for package in package_catalog.catalog(self.owner.hardware_info):
                self.entry(package['name'], lambda key=package['id']: self.select_package(key), value='Selected' if self.owner.settings['runtime_provider'] == package['id'] else '', enabled=package['available'])
            self.hint.set_text('Choose a package for the next install. Restore an existing provider before switching.')
        elif self.page == 'settings':
            self.entry('Big Picture UI',lambda:self.owner.set_big_picture_ui(False),value='Enabled')
            glyphs = ['auto', 'xbox', 'playstation', 'nintendo', 'generic']
            self.entry('Button labels', value=self.owner.settings.get('controller_glyphs', 'auto').title(), adjust=lambda d: self.setting('controller_glyphs', d, glyphs))
            self.entry('Library layout', value={'posters': 'Posters', 'capsules': 'Wide', 'list': 'List'}[self.library_view], adjust=lambda d: self.set_library_view(VIEWS[(VIEWS.index(self.library_view) + d) % len(VIEWS)]))
            for key,title,choices,captions in [
                ('ui_scale','UI scale',['auto',100,125,150,175,200],['Automatic','100%','125%','150%','175%','200%']),
                ('dashboard_view','Dashboard artwork',['capsules','posters'],['Wide','Poster']),
                ('dashboard_row_count','Games across shelf',list(range(3,9)),[str(n) for n in range(3,9)]),
                ('navigation_position','Navigation',['top','bottom'],['Top','Bottom']),
                ('controller_hints','Controller hints',['always','auto'],['Always visible','Hide when idle'])]:
                value=self.owner.settings.get(key,library_media.DEFAULTS[key])
                self.entry(title,value=captions[choices.index(value)],adjust=lambda d,key=key,choices=choices:self.setting(key,d,choices))
            self.entry('Desktop controls', lambda: self.owner.set_input_surface(False))
            self.entry('Exit app', self.owner.close)
            self.hint.set_text('Use a keyboard or mouse to switch to Classic. Controller input brings you back here.')

    def artwork_widget(self, path, title, width, height, style='couch-cover'):
        cover = Gtk.Overlay()
        cover.add_css_class(style)
        cover.set_overflow(Gtk.Overflow.HIDDEN)
        cover.set_size_request(width, height)
        picture = self.owner.make_art_picture(width,height)
        cover.picture = picture
        cover.placeholder = None
        if path:
            try:
                picture.set_filename(path)
            except (GLib.Error, OSError):
                path = None
        if not path or path==self.owner.wide_art_path({}):
            placeholder = Gtk.Image.new_from_icon_name('applications-games-symbolic') if path else label(title, 'couch-tile-title', wrap=True)
            if isinstance(placeholder,Gtk.Label):placeholder.set_max_width_chars(18)
            else:placeholder.set_pixel_size(18);placeholder.add_css_class('library-ghost-icon')
            placeholder.set_halign(Gtk.Align.CENTER)
            placeholder.set_valign(Gtk.Align.CENTER)
            cover.add_overlay(placeholder)
            cover.placeholder = placeholder
        cover.set_child(picture)
        return cover

    def game_tile(self, entry, width, height, poster=False):
        game = entry.get('game') or {}
        button = Gtk.Button()
        button.add_css_class('couch-tile')
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        # Use the same resolved custom/SteamGridDB/Steam assets as Classic.
        path = (game.get('poster') or game.get('capsule')) if poster else self.owner.wide_art_path(game)
        button.artwork = self.artwork_widget(path, entry['title'], width, height)
        if self.dlss_selection is not None:
            marker = self.selection_marker(game)
            marker.set_halign(Gtk.Align.END)
            marker.set_valign(Gtk.Align.START)
            marker.set_margin_top(8)
            marker.set_margin_end(8)
            button.artwork.add_overlay(marker)
        self.owner.decorate_support_artwork(button.artwork,button.artwork.picture,game,path)
        column.append(button.artwork)
        name = label(entry['title'], 'couch-tile-title')
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_max_width_chars(23)
        column.append(name)
        info = ' · '.join(str(value) for value in (game.get('source'), game.get('profile') if game.get('installed') else 'Not configured', self.owner.game_status_label(game)) if value)
        badges = label(info, 'couch-badges')
        badges.set_max_width_chars(24)
        badges.set_ellipsize(Pango.EllipsizeMode.END)
        badges.set_tooltip_text(info)
        column.append(badges)
        button.set_child(column)
        return button

    def game_list_row(self, entry):
        game = entry.get('game') or {}
        button = Gtk.Button()
        button.add_css_class('couch-list-row')
        content = Gtk.Box(spacing=20)
        if self.dlss_selection is not None:
            content.append(self.selection_marker(game))
        path = self.owner.wide_art_path(game)
        button.artwork = self.artwork_widget(path, '', 96, 54, 'couch-list-art')
        self.owner.decorate_support_artwork(button.artwork,button.artwork.picture,game,path)
        content.append(button.artwork)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER, hexpand=True)
        title = label(entry['title'], 'couch-list-title')
        title.set_ellipsize(Pango.EllipsizeMode.END)
        names.append(title)
        names.append(label(game.get('source', 'Library'), 'couch-subtle'))
        content.append(names)
        if not self.compact:
            profile = label(game.get('profile', 'Not installed'), 'couch-list-status')
            profile.set_width_chars(16)
            content.append(profile)
        status = label('Unsupported' if game.get('blocked') else 'Installed' if game.get('installed') else 'Available', 'couch-list-status')
        status.set_width_chars(10)
        status.set_xalign(1)
        content.append(status)
        button.set_child(content)
        return button

    def artwork_updated(self, game):
        """Apply the main library's async artwork event without rebuilding focus."""
        if self.game and self.game['game'] == game['game']:
            self.set_game(game)
        if self.page not in ('dashboard', 'library'):
            return
        for index, entry in enumerate(self.entries):
            if (entry.get('game') or {}).get('game') != game['game']:
                continue
            path = (game.get('poster') or game.get('capsule')) if (self.page == 'library' and self.library_view == 'posters') or (self.page == 'dashboard' and self.owner.settings.get('dashboard_view')=='posters') else self.owner.wide_art_path(game)
            if not path:
                continue
            cover = self.controls[index].artwork
            try:
                cover.picture.set_filename(path)
                self.owner.decorate_support_artwork(cover,cover.picture,game,path)
                if cover.placeholder:
                    cover.placeholder.set_visible(False)
            except (GLib.Error, OSError):
                pass

    def render(self, index=None):
        self.build_entries()
        is_feature = self.page in ('dashboard', 'game', 'tools')
        self.body.set_visible_child_name('feature' if is_feature else 'library' if self.page == 'library' else 'panel')
        self.remove_css_class('panel-open') if is_feature else self.add_css_class('panel-open')
        self.add_css_class('library-open') if self.page == 'library' else self.remove_css_class('library-open')
        self.library.set_visible(self.page == 'dashboard')
        self.game_actions.set_visible(self.page in ('game','tools'))
        self.game_metadata.set_visible(self.page == 'game')
        self.game_summary.set_visible(self.page == 'game' and bool(self.game_summary.get_text()))
        self.count.set_text('Refreshing…' if self.owner.busy else f"{len(self.owner.games)} games · {self.owner.settings.get('dashboard_row_count',5)} across")
        installed = sum(bool(game.get('installed')) for game in self.owner.games)
        selecting = self.dlss_selection is not None
        if selecting:
            self.dlss_selection.intersection_update(g['game'] for g in self.owner.games if not g.get('blocked') and (self.selection_kind != 'presets' or g.get('installed')))
        self.library_heading.set_text('Select games' if selecting else 'Library')
        self.library_count.set_text(f'{len(self.dlss_selection)} selected  ·  ' + ('Presets' if self.selection_kind == 'presets' else 'DLSS Files') if selecting else f'{len(self.owner.games)} games  ·  {installed} configured')
        self.library_action.set_label(f"{'Apply presets' if self.selection_kind == 'presets' else 'Update selected'} ({len(self.dlss_selection)})" if selecting else 'Install to all')
        self.library_action.set_sensitive(bool(self.dlss_selection) if selecting else bool(self.owner.games))
        self.heading.set_text({'dashboard': 'Dashboard', 'library': 'Library', 'game': 'Game settings', 'menu': 'Menu', 'features': 'Configure', 'features_all': 'Install to all', 'presets': 'Library presets', 'game_presets': 'Game presets', 'dlss': 'DLSS Files', 'tools': 'Tools', 'settings': 'Settings', 'packages': 'Packages'}[self.page])
        self.panel_detail.set_text(self.game['name'] if self.game and self.page in ('features', 'game_presets', 'tools') else {'presets': 'Across your configured games', 'packages': 'Your graphics toolkit', 'dlss': 'Keep your games current', 'features_all': f'{len(self.owner.games)} games in your library', 'settings': 'Make yourself at home', 'menu': 'rtxForge'}.get(self.page, ''))
        clear(self.shelf)
        clear(self.actions)
        clear(self.menu)
        clear(self.grid)
        self.controls = []
        self.grid.set_row_spacing(0 if self.library_view=='list' else 20)
        self.columns, width, height = self.grid_dimensions()
        for i, entry in enumerate(self.entries):
            if self.page == 'dashboard':
                count=self.owner.settings.get('dashboard_row_count',5)
                available=self.shelf_scroll.get_width() or self.layout_width-(60 if self.compact else 92)
                shelf_width=max(80,round((available-12*(count-1))/count)-16)
                poster=self.owner.settings.get('dashboard_view','capsules')=='posters'
                ratio=self.owner.library_card_geometry(view='posters' if poster else 'capsules')[5]
                shelf_height=round(shelf_width/ratio)
                self.shelf_scroll.set_min_content_height(shelf_height+80)
                button = self.game_tile(entry, shelf_width, shelf_height, poster)
                self.shelf.append(button)
                self.controls.append(button)
                button.connect('clicked', lambda _, n=i: self.activate(n))
            elif self.page == 'library':
                button = self.game_list_row(entry) if self.library_view == 'list' else self.game_tile(entry, width, height, self.library_view == 'posters')
                button.set_hexpand(True)
                if self.library_view=='list':
                    if i==0:button.add_css_class('joined-first')
                    if i==len(self.entries)-1:button.add_css_class('joined-last')
                self.grid.attach(button, i % self.columns, i // self.columns, 1, 1)
                self.controls.append(button)
                button.connect('clicked', lambda _, n=i: self.activate(n))
            elif self.page in ('game','tools'):
                button = self.owner.make_action_button(entry['title'],lambda _, n=i:self.activate(n))
                button.set_size_request(180,80);button.text_label.set_wrap(True)
                button.add_css_class('couch-action')
                button.set_sensitive(entry['enabled'])
                self.actions.insert(button,-1)
                self.controls.append(button)
            else:
                row = Gtk.ListBoxRow()
                row.set_sensitive(entry['enabled'])
                line = Gtk.Box(spacing=16)
                icon_name = {'Button labels': 'input-gaming-symbolic', 'Library layout': 'view-grid-symbolic', 'Exit app': 'application-exit-symbolic', 'Quit rtxForge': 'application-exit-symbolic', 'Dashboard': 'go-home-symbolic', 'Library': 'folder-games-symbolic', 'Packages': 'package-x-generic-symbolic', 'Refresh library': 'view-refresh-symbolic', 'Desktop controls': 'computer-symbolic', 'Neural Rendering': 'image-x-generic-symbolic', 'Frame generation': 'media-playlist-repeat-symbolic', 'Sharpening': 'image-adjust-color-symbolic'}.get(entry['title'], 'emblem-system-symbolic')
                icon = Gtk.Image.new_from_icon_name(icon_name)
                icon.set_pixel_size(22)
                line.append(icon)
                title = label(entry['title'])
                title.set_hexpand(True)
                title.set_ellipsize(Pango.EllipsizeMode.END)
                line.append(title)
                if entry['value'] is not None:
                    if entry['adjust']:
                        line.append(Gtk.Image.new_from_icon_name('pan-start-symbolic'))
                    line.append(label(entry['value'], 'couch-value'))
                    if entry['adjust']:
                        line.append(Gtk.Image.new_from_icon_name('pan-end-symbolic'))
                row.set_child(line)
                self.menu.append(row)
        position = index if index is not None else self.selection.get(self.page, 0)
        if self.entries:
            position = min(position, len(self.entries) - 1)
            if not self.entries[position]['enabled']:
                position = next((i for i, e in enumerate(self.entries) if e['enabled']), position)
            self.focus(position)
        self.update_tabs()
        self.update_prompts()

    def select_package(self, key):
        self.owner.settings['runtime_provider'] = key
        self.owner.nr_only.set_enabled(key == 'dlss-unlocked')
        if not self.owner.options.demo:
            library_media.save_settings(self.owner.service.config, self.owner.settings)
        self.owner.toast('Package selected for the next install.')
        self.render()

    def refresh(self):
        self.library_view = self.owner.settings.get('library_view', 'posters')
        self.view_index = 0
        if self.game:
            match = next((g for g in self.owner.games if g['game'] == self.game['game']), None)
            if match:
                self.set_game(match)
            else:
                self.page = 'library'
                self.game = None
                self.apply_accent(None)
                self.art_path = None
                self.art.set_paintable(None)
                self.title.set_text('Your library')
                self.detail.set_text('Add games to begin.')
        self.apply_navigation_preferences()
        self.render()

    def resize(self, width, height=None):
        if width < 400:
            return
        height = height or self.layout_height
        height_changed = abs(height - self.layout_height) > 12
        self.layout_height = height
        width_changed = abs(width - self.layout_width) > 12
        if width_changed:
            self.layout_width = width
        compact = width < 1050
        if compact != self.compact or width_changed or height_changed:
            self.compact = compact
            self.add_css_class('compact') if compact else self.remove_css_class('compact')
            scale = max(.82, min(1.0, width / 1280))
            self.panel.set_size_request(min(width - 60, round(660 * scale)), -1)
            self.panel_scroll.set_max_content_height(max(180, height - round(330 * scale)))
            self.scale_provider.load_from_data(f'''
              .couch-shell .couch-content {{ padding: {round(26 * scale)}px {round(46 * scale)}px {round(20 * scale)}px; }}
              .couch-shell .couch-title {{ font-size: {round(48 * scale)}px; }}
              .couch-shell .couch-panel-heading {{ font-size: {round(34 * scale)}px; }}
              .couch-shell .couch-options row label {{ font-size: {round(20 * scale)}px; }}
              .couch-shell .couch-tab {{ font-size: {round(16 * scale)}px; padding: {round(10 * scale)}px {round(18 * scale)}px; }}
            '''.encode())
            self.context.set_visible(self.owner.options.demo or not compact)
        if width_changed and self.page in ('library','dashboard'):
            self.render(self.current)
