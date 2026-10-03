"""Focus-led game library sharing the desktop service and reviewed operations."""
from pathlib import Path
from gi.repository import Gtk, Gdk, GLib, Gio, Pango
import controller_input
import library_media


CSS = b'''
.couch-shell { background: #101113; color: #fafafa; }
.couch-shade {
  background-image: linear-gradient(0deg, #101113 0%, #101113 22%, rgba(16,17,19,0.72) 43%, rgba(16,17,19,0.12) 76%, rgba(16,17,19,0.58) 100%),
                    linear-gradient(90deg, rgba(16,17,19,0.78), rgba(16,17,19,0.10) 75%);
}
.couch-shell.panel-open .couch-shade { background: rgba(16,17,19,0.92); }
.couch-content { padding: 30px 52px 24px; }
.couch-brand { font-size: 20px; font-weight: 700; }
.couch-context { font-size: 14px; font-weight: 500; color: #c2c4c8; background: rgba(16,17,19,0.88); border-radius: 12px; padding: 6px 10px; }
.couch-tabs { border-radius: 24px; background: rgba(28,29,32,0.88); padding: 4px; }
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
.couch-action { padding: 16px 26px; border-radius: 16px; background: rgba(244,244,250,0.12); color: #f4f4f6; box-shadow: none; border: none; font-size: 19px; font-weight: 650; }
.couch-action.focused { background: #fafafa; color: #17181b; }
.couch-action:focus { outline: none; }
.couch-action:disabled { color: #9a9da5; background: rgba(244,244,250,0.06); }
.couch-options { background: transparent; color: #f4f4f6; }
.couch-options row { border-radius: 16px; margin: 0 0 10px; padding: 18px 24px; min-height: 28px; background: rgba(244,244,250,0.08); }
.couch-options row label { font-size: 20px; font-weight: 550; }
.couch-options row:selected { background: #fafafa; color: #191a1d; }
.couch-options.nav-focused row:selected { background: rgba(244,244,250,0.08); color: #f4f4f6; }
.couch-options row:disabled { opacity: 0.45; }
.couch-options row:focus { outline: none; }
.couch-value { font-weight: 650; }
.couch-caption { font-size: 16px; color: #c1c3c8; }
.couch-panel-heading { font-size: 36px; font-weight: 700; letter-spacing: -0.8px; }
.couch-prompts { font-size: 14px; color: #b5b8bf; }
.couch-key { border-radius: 20px; background: #d1d3d8; color: #1a1c20; min-width: 20px; min-height: 20px; padding: 1px 4px; font-weight: 700; font-size: 12px; }
.couch-shell.compact .couch-content { padding: 22px 30px 18px; }
.couch-shell.compact .couch-title { font-size: 38px; letter-spacing: -0.8px; }
.couch-shell.compact .couch-tab { padding: 8px 16px; font-size: 14px; }
.couch-shell.compact .couch-detail { font-size: 16px; }
.couch-shell.compact .couch-action { padding: 14px 20px; font-size: 17px; }
.couch-shell.compact .couch-options row { padding: 14px 20px; }
.couch-shell.compact .couch-options row label { font-size: 18px; }
.couch-shell.compact .couch-panel-heading { font-size: 30px; }
'''


def label(text, style=None, wrap=False):
    widget = Gtk.Label(label=text, xalign=0, wrap=wrap)
    if style:
        widget.add_css_class(style)
    return widget


def clear(box):
    while box.get_first_child():
        box.remove(box.get_first_child())


class CouchShell(Gtk.Overlay):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.page = 'library'
        self.game = None
        self.entries = []
        self.controls = []
        self.pending = {}
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
        self.art = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        self.art.set_opacity(0.9)
        self.set_child(self.art)
        shade = Gtk.Box()
        shade.add_css_class('couch-shade')
        shade.set_can_target(False)
        self.add_overlay(shade)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        main.add_css_class('couch-content')
        self.add_overlay(main)

        top = Gtk.CenterBox()
        brand = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_file(str(Path(__file__).parent / 'icons/rtxforge-artwork.svg'))
        icon.set_pixel_size(30)
        brand.append(icon)
        brand.append(label('rtxForge', 'couch-brand'))
        top.set_start_widget(brand)
        tabs = Gtk.Box()
        tabs.add_css_class('couch-tabs')
        self.tabs = []
        for title, page in [('Library', 'library'), ('Packages', 'packages'), ('Settings', 'settings')]:
            button = Gtk.Button(label=title)
            button.add_css_class('couch-tab')
            button.connect('clicked', lambda _, p=page: self.open(p))
            tabs.append(button)
            self.tabs.append(button)
        top.set_center_widget(tabs)
        self.context = label('Preview' if owner.options.demo else 'Game Mode', 'couch-context')
        top.set_end_widget(self.context)
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
        feature.append(hero)
        self.library = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        heading = Gtk.Box()
        heading.append(label('Your games', 'couch-section'))
        self.count = label('', 'couch-subtle')
        self.count.set_hexpand(True)
        self.count.set_halign(Gtk.Align.END)
        heading.append(self.count)
        self.library.append(heading)
        self.shelf = Gtk.Box(spacing=12)
        self.shelf_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.EXTERNAL, vscrollbar_policy=Gtk.PolicyType.NEVER)
        self.shelf_scroll.set_min_content_height(186)
        self.shelf_scroll.set_child(self.shelf)
        self.library.append(self.shelf_scroll)
        feature.append(self.library)
        self.game_actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.actions = Gtk.Box(spacing=12)
        self.game_actions.append(self.actions)
        self.action_hint = label('', 'couch-caption', wrap=True)
        self.action_hint.set_max_width_chars(70)
        self.action_hint.set_size_request(-1, 50)
        self.game_actions.append(self.action_hint)
        self.game_actions.set_margin_bottom(32)
        feature.append(self.game_actions)
        self.body.add_named(feature, 'feature')

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

        footer = Gtk.Box()
        self.prompts = Gtk.Box(spacing=22)
        self.prompts.add_css_class('couch-prompts')
        footer.append(self.prompts)
        self.footer_note = label('', 'couch-subtle')
        self.footer_note.set_hexpand(True)
        self.footer_note.set_halign(Gtk.Align.END)
        footer.append(self.footer_note)
        main.append(footer)
        self.render()

    def update_prompts(self):
        family = self.owner.settings.get('controller_glyphs', 'auto')
        if family == 'auto':
            family = self.owner.controller.family
        keys = controller_input.GLYPHS.get(family, controller_input.GLYPHS['generic'])
        caption = 'Open' if self.page == 'library' else 'Select'
        spec = (keys[0], keys[1], self.page, caption)
        if spec == getattr(self, 'prompt_spec', None):
            return
        self.prompt_spec = spec
        clear(self.prompts)
        for key, text in ((keys[0], caption), (keys[1], 'Back')):
            pair = Gtk.Box(spacing=7, valign=Gtk.Align.CENTER)
            pair.append(label(key, 'couch-key'))
            pair.append(label(text))
            self.prompts.append(pair)
        self.footer_note.set_text('Left / right to adjust' if self.page in ('presets', 'settings') else 'Menu for more')

    def set_game(self, game):
        self.game = game
        self.title.set_text(game['name'])
        if game.get('blocked'):
            status = game['blocked']
        elif game.get('installed'):
            status = game.get('profile', 'Features installed') + ' installed'
            if game.get('nr_enabled') is not None:
                status += '  ·  Neural Rendering ' + ('on' if game['nr_enabled'] else 'off')
        else:
            status = 'Ready to configure'
        self.detail.set_text(status)
        # A portrait cover is never enlarged into a landscape background.
        path = game.get('hero') or game.get('capsule')
        if path != self.art_path:
            self.art_path = path
            try:
                self.art.set_filename(path) if path else self.art.set_paintable(None)
            except (GLib.Error, OSError):
                self.art.set_paintable(None)

    def entry(self, title, action=None, value=None, adjust=None, enabled=True, game=None, hint=''):
        self.entries.append(dict(title=title, action=action, value=value, adjust=adjust, enabled=enabled, game=game, hint=hint))

    def navigate(self, action):
        if action == 'back':
            self.back()
            return
        if action == 'menu':
            self.open('menu')
            return
        if action == 'search':
            self.open('library')
            return
        if action in ('previous', 'next'):
            self.tab_index = (self.tab_index + (1 if action == 'next' else -1)) % 3
            self.open(('library', 'packages', 'settings')[self.tab_index])
            return
        if self.zone == 'nav':
            if action in ('left', 'right'):
                self.tab_index = (self.tab_index + (1 if action == 'right' else -1)) % 3
            elif action == 'accept':
                self.open(('library', 'packages', 'settings')[self.tab_index])
            elif action == 'down':
                self.zone = 'content'
                self.focus(self.current)
            self.update_tabs()
            return
        horizontal = self.page in ('library', 'game')
        if action == 'up' and (horizontal or self.current == 0):
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
        active = {'packages': 1, 'settings': 2}.get(self.page, 0)
        for i, button in enumerate(self.tabs):
            button.add_css_class('active') if i == active else button.remove_css_class('active')
            button.add_css_class('focused') if self.zone == 'nav' and i == self.tab_index else button.remove_css_class('focused')
        self.menu.add_css_class('nav-focused') if self.zone == 'nav' else self.menu.remove_css_class('nav-focused')
        for i, button in enumerate(self.controls):
            button.add_css_class('focused') if self.zone == 'content' and i == self.current else button.remove_css_class('focused')

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
            if self.page == 'library':
                GLib.idle_add(self.reveal_selection)
            self.action_hint.set_text(entry.get('hint', ''))
        else:
            row = self.menu.get_row_at_index(self.current)
            self.menu.select_row(row)
            if row and row.get_parent():
                row.grab_focus()
        self.update_tabs()

    def reveal_selection(self):
        if self.page != 'library' or not self.controls:
            return False
        button = self.controls[min(self.current, len(self.controls) - 1)]
        allocation = button.get_allocation()
        adjustment = self.shelf_scroll.get_hadjustment()
        start = allocation.x
        end = start + allocation.width
        position = adjustment.get_value()
        if start < position:
            adjustment.set_value(max(0, start - 8))
        elif end > position + adjustment.get_page_size():
            adjustment.set_value(end - adjustment.get_page_size() + 8)
        return False

    def activate(self, index):
        if index >= len(self.entries) or self.owner.busy:
            return
        entry = self.entries[index]
        if entry['enabled'] and entry['action']:
            entry['action']()

    def open(self, page):
        if page in ('game', 'presets', 'features', 'tools') and self.game is None:
            page = 'library'
        if page == 'presets':
            self.pending = {key: self.game.get(key) if self.game.get(key) is not None else self.owner.settings[key] for key in ('nr_strength', 'sharpening_strength', 'mfg_multiplier')}
        self.page = page
        self.zone = 'content'
        self.tab_index = {'packages': 1, 'settings': 2}.get(page, 0)
        self.render()

    def back(self):
        if self.zone == 'nav':
            self.zone = 'content'
            self.update_tabs()
        elif self.page == 'library':
            self.open('menu')
        elif self.page in ('presets', 'features', 'tools'):
            self.open('game')
        else:
            self.open('library')

    def install(self, mode):
        self.owner.profile_group.set_active_name(mode)
        self.owner.launch_action('install', targets=[self.game], visual_settings=dict(self.owner.settings), _presets_confirmed=True)

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
        self.update_prompts()

    def build_entries(self):
        self.entries = []
        self.hint.set_text('')
        if self.page == 'library':
            for game in self.owner.games:
                self.entry(game['name'], lambda g=game: (self.set_game(g), self.open('game')), game=game)
            if not self.entries:
                self.entry('Refresh library', self.owner.scan)
                self.detail.set_text('Add a game folder in Classic to get started.')
        elif self.page == 'game':
            game = self.game
            self.entry('Configure', lambda: self.open('features'), enabled=not game.get('blocked'), hint='Choose Neural Rendering and frame generation for this game.')
            self.entry('Presets', lambda: self.open('presets'), enabled=game.get('installed', False), hint='Adjust graphics features for this game. Your other games stay as they are.')
            self.entry('Tools', lambda: self.open('tools'), hint='Diagnose Neural Rendering, update DLSS, or restore original files.')
            self.entry('Play', lambda: Gio.AppInfo.launch_default_for_uri('steam://rungameid/' + str(game['appid']), None), enabled=game.get('source') == 'Steam' and str(game.get('appid', '')).isdigit() and not self.owner.options.demo, hint='Launch this game in Steam.')
        elif self.page == 'features':
            self.entry('Neural Rendering + MFG', lambda: self.install('nr-mfg'))
            self.entry('Frame generation only', lambda: self.install('mfg-only'))
            self.entry('Neural Rendering only', lambda: self.install('nr-only'), enabled=self.owner.settings.get('runtime_provider') in ('dlss-unlocked', 'custom'))
            self.hint.set_text('Review every file change before installing. Your current presets are used.')
        elif self.page == 'presets':
            mode = self.game.get('feature_mode') or {'MFG Only': 'mfg-only', 'NR Only': 'nr-only'}.get(self.game.get('profile'), 'nr-mfg')
            for key, title in [('nr_strength', 'Neural Rendering'), ('mfg_multiplier', 'Frame generation'), ('sharpening_strength', 'Sharpening')]:
                raw = self.pending[key]
                value = 'In game' if raw == 'auto' else 'Off' if raw == 0 else str(raw) + ('×' if key == 'mfg_multiplier' else '')
                self.entry(title, value=value, adjust=lambda delta, key=key: self.adjust(key, delta), enabled=not (key == 'nr_strength' and mode == 'mfg-only') and not (key == 'mfg_multiplier' and mode == 'nr-only'))
            self.entry('Apply to this game', lambda: self.owner.launch_action('reset', targets=[self.game], visual_settings=dict(self.pending)))
            self.hint.set_text('Adjust with left and right. A strength of zero turns Neural Rendering off.')
        elif self.page == 'tools':
            self.entry('Diagnose Neural Rendering', lambda: self.owner.show_diagnostics(self.game))
            self.entry('Update DLSS files', lambda: self.owner.manage_dlss_files(self.game), enabled=not self.owner.options.demo)
            self.entry('Restore DLSS files', lambda: self.owner.manage_dlss_files(self.game, restore=True), enabled=not self.owner.options.demo)
            self.entry('Restore original game files', lambda: self.owner.launch_action('uninstall', targets=[self.game]), enabled=self.game.get('installed', False))
            self.hint.set_text('ReShade and add-on imports are available in Classic with keyboard and mouse.')
        elif self.page == 'menu':
            self.entry('Library', lambda: self.open('library'))
            self.entry('Refresh library', self.owner.scan)
            self.entry('Desktop controls', lambda: self.owner.set_input_surface(False))
            self.entry('Quit rtxForge', self.owner.close)
        elif self.page == 'packages':
            import package_catalog
            for package in package_catalog.catalog(self.owner.hardware_info):
                self.entry(package['name'], lambda key=package['id']: self.select_package(key), value='Selected' if self.owner.settings['runtime_provider'] == package['id'] else '', enabled=package['available'])
            self.hint.set_text('Choose a package for the next install. Restore an existing provider before switching.')
        elif self.page == 'settings':
            glyphs = ['auto', 'xbox', 'playstation', 'nintendo', 'generic']
            self.entry('Button labels', value=self.owner.settings.get('controller_glyphs', 'auto').title(), adjust=lambda d: self.setting('controller_glyphs', d, glyphs))
            self.entry('Desktop controls', lambda: self.owner.set_input_surface(False))
            self.hint.set_text('Use a keyboard or mouse to switch to Classic. Controller input brings you back here.')

    def render(self, index=None):
        self.build_entries()
        is_feature = self.page in ('library', 'game')
        self.body.set_visible_child_name('feature' if is_feature else 'panel')
        self.remove_css_class('panel-open') if is_feature else self.add_css_class('panel-open')
        self.library.set_visible(self.page == 'library')
        self.game_actions.set_visible(self.page == 'game')
        self.count.set_text('Refreshing…' if self.owner.busy else str(len(self.owner.games)) + ' games')
        self.heading.set_text({'library': 'Your library', 'game': 'Game settings', 'menu': 'Menu', 'features': 'Configure', 'presets': 'Graphics presets', 'tools': 'Tools', 'settings': 'Settings', 'packages': 'Packages'}[self.page])
        self.panel_detail.set_text(self.game['name'] if self.game and self.page in ('features', 'presets', 'tools') else {'packages': 'Your graphics toolkit', 'settings': 'Make yourself at home', 'menu': 'rtxForge'}.get(self.page, ''))
        clear(self.shelf)
        clear(self.actions)
        clear(self.menu)
        self.controls = []
        for i, entry in enumerate(self.entries):
            if self.page == 'library':
                button = Gtk.Button()
                button.add_css_class('couch-tile')
                column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
                game = entry.get('game') or {}
                path = game.get('capsule') or game.get('hero')
                cover = Gtk.Overlay()
                cover.add_css_class('couch-cover')
                cover.set_overflow(Gtk.Overflow.HIDDEN)
                cover.set_size_request(206, 116)
                picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
                if path:
                    picture.set_filename(path)
                else:
                    placeholder = label(game.get('name', 'Refresh library'), 'couch-tile-title', wrap=True)
                    placeholder.set_max_width_chars(18)
                    placeholder.set_halign(Gtk.Align.CENTER)
                    placeholder.set_valign(Gtk.Align.CENTER)
                    cover.add_overlay(placeholder)
                cover.set_child(picture)
                column.append(cover)
                name = label(entry['title'], 'couch-tile-title')
                name.set_ellipsize(Pango.EllipsizeMode.END)
                name.set_max_width_chars(23)
                column.append(name)
                button.set_child(column)
                self.shelf.append(button)
                self.controls.append(button)
                button.connect('clicked', lambda _, n=i: self.activate(n))
            elif self.page == 'game':
                button = Gtk.Button(label=entry['title'])
                button.add_css_class('couch-action')
                button.set_sensitive(entry['enabled'])
                button.connect('clicked', lambda _, n=i: self.activate(n))
                self.actions.append(button)
                self.controls.append(button)
            else:
                row = Gtk.ListBoxRow()
                row.set_sensitive(entry['enabled'])
                line = Gtk.Box(spacing=24)
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
        if self.game:
            match = next((g for g in self.owner.games if g['game'] == self.game['game']), None)
            if match:
                self.set_game(match)
            else:
                self.page = 'library'
                self.game = None
                self.art_path = None
                self.art.set_paintable(None)
                self.title.set_text('Your library')
                self.detail.set_text('Add games to begin.')
        self.render()

    def resize(self, width):
        compact = width < 1050
        if compact == self.compact:
            return
        self.compact = compact
        self.add_css_class('compact') if compact else self.remove_css_class('compact')
        self.panel.set_size_request(580 if compact else 660, -1)
        self.panel_scroll.set_max_content_height(280 if compact else 360)
        self.context.set_visible(self.owner.options.demo or not compact)
