"""GTK controls for the native Game Mode appearance contract."""
import base64
from pathlib import Path
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GdkPixbuf, Gio, GLib
import game_mode_appearance as shared


def color_hex(color):
    return '#%02x%02x%02x' % tuple(round(channel * 255) for channel in (color.red, color.green, color.blue))


def system_accent():
    style = Adw.StyleManager.get_default()
    if hasattr(style, 'get_system_supports_accent_colors') and style.get_system_supports_accent_colors():
        return color_hex(style.get_accent_color_rgba())
    return shared.FORGE_GREEN


class AppearanceSettings:
    def __init__(self, owner):
        self.owner = owner
        self.config = owner.service.config
        self.value = shared.load(self.config) or dict(shared.DEFAULTS)
        self.groups = []
        self.refreshers = []
        self.refreshing = False
        self.feedback_group = None
        self.background = None
        self.default_backdrops = {}
        self.posters = []
        for game in owner.games:
            source = game.get('poster') or game.get('capsule')
            if source:
                try:
                    self.posters.append((game, GdkPixbuf.Pixbuf.new_from_file_at_scale(str(source), 78, 116, True)))
                except Exception:
                    pass
            if len(self.posters) == 6:
                break
        self.detail_hero = None
        if self.posters:
            game = self.posters[0][0]
            art = game.get('art') or {}
            hero = game.get('hero') or (art.get('hero') if isinstance(art, dict) else None)
            if isinstance(hero, str):
                try:
                    self.detail_hero = GdkPixbuf.Pixbuf.new_from_file_at_scale(hero, 480, 145, True)
                except GLib.Error:
                    pass
        self.preview = Gtk.DrawingArea(content_width=480, content_height=270, hexpand=True)
        self.preview.set_draw_func(self.draw)
        self.details_preview = Gtk.DrawingArea(content_width=480, content_height=270, hexpand=True)
        self.details_preview.set_draw_func(self.draw_details)
        self.feedback = Gtk.Label(xalign=0, wrap=True, visible=False)
        self.feedback.add_css_class('dim-label')
        self.tint_row = None
        self.custom_accent_row = None
        self.build()
        style = Adw.StyleManager.get_default()
        if style.find_property('accent-color-rgba'):
            def repaint(*_):
                if self.value['accentSource'] == 'system':
                    self.preview.queue_draw()
                    self.details_preview.queue_draw()
            def track(*_):
                self.accent_handler = style.connect('notify::accent-color-rgba', repaint)
                repaint()
            self.preview.connect('map', track)
            self.preview.connect('unmap', lambda *_: style.disconnect(self.accent_handler))

    def message(self, text):
        self.feedback.set_label(text)
        self.feedback.set_visible(bool(text))
        if self.feedback_group:
            self.feedback_group.set_description(text)

    def change(self, key, value):
        if self.refreshing:
            return
        before = self.value
        try:
            fresh = shared.load(self.config) or self.value.copy()
            fresh[key] = value
            self.value = shared.normalize(fresh) if self.owner.options.demo else shared.save(fresh, self.config)
            self.message('Preview only' if self.owner.options.demo else 'Saved')
            if key == 'background':
                self.background = None
            if self.custom_accent_row:
                self.custom_accent_row.set_visible(self.value['accentSource'] == 'custom')
            if self.tint_row:
                self.tint_row.set_visible(self.value['accentMode'] != 'theme')
            self.preview.queue_draw()
            self.details_preview.queue_draw()
        except Exception as error:
            self.value = before
            self.message(str(error))

    def group(self, title, description=None):
        group = Adw.PreferencesGroup(title=title)
        if description:
            group.set_description(description)
        self.groups.append(group)
        return group

    def choice(self, group, title, key, choices, description=None):
        values, labels = zip(*choices)
        row = Adw.ComboRow(title=title, model=Gtk.StringList.new(labels), selected=values.index(self.value[key]))
        if description:
            row.set_subtitle(description)
        row.connect('notify::selected', lambda control, *_: self.change(key, values[control.get_selected()]))
        self.refreshers.append(lambda: row.set_selected(values.index(self.value[key])))
        group.add(row)
        return row

    def preview_panel(self, options, sample, caption, route, preview_options):
        panel = Adw.WrapBox(child_spacing=20, line_spacing=16, hexpand=True)
        options.set_hexpand(True)
        panel.append(options)
        preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, valign=Gtk.Align.START, hexpand=True)
        title = Gtk.Label(label=caption, xalign=0)
        title.add_css_class('dim-label')
        preview.append(title)
        frame = Gtk.AspectFrame(ratio=16 / 9, obey_child=False, child=sample)
        preview.append(Adw.Clamp(child=frame, maximum_size=560, tightening_threshold=440))
        button = Gtk.Button(label='Open full preview', halign=Gtk.Align.START)
        button.update_property([Gtk.AccessibleProperty.LABEL], ['Open ' + caption])
        button.connect('clicked', lambda *_: self.owner.open_game_mode_preview(route))
        preview.append(button)
        preview.append(preview_options)
        panel.append(preview)
        panel.set_margin_top(12); panel.set_margin_bottom(12)
        panel.set_margin_start(12); panel.set_margin_end(12)
        return Adw.PreferencesRow(child=panel)

    def build(self):
        from overlay_layouts import ThemePicker
        surface = self.group('Game Mode appearance', 'The same preferences as Game Mode, saved automatically.')
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        body.append(Gtk.Label(label='Surface', xalign=0))
        themes = ThemePicker(self.value['theme'], lambda value: self.change('theme', value))
        def refresh_themes():
            child = themes.get_first_child()
            for key in ('light', 'clear', 'dark'):
                child.set_active(self.value['theme'] == key); child = child.get_next_sibling()
        self.refreshers.append(refresh_themes)
        body.append(themes)
        main = Adw.PreferencesGroup()
        body.append(main)
        preview_options = Adw.PreferencesGroup()
        surface.add(self.preview_panel(body, self.preview, 'Library preview', 'library', preview_options))
        self.choice(main, 'Accent', 'accentSource', shared.ACCENT_CHOICES)
        color = Gdk.RGBA(); color.parse(self.value['accent'])
        chooser = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(title='Game Mode accent color', with_alpha=False), rgba=color, valign=Gtk.Align.CENTER)
        chooser.connect('notify::rgba', lambda control, *_: self.change('accent', color_hex(control.get_rgba())))
        def refresh_color():
            value = Gdk.RGBA(); value.parse(self.value['accent']); chooser.set_rgba(value)
        self.refreshers.append(refresh_color)
        row = Adw.ActionRow(title='Custom accent color', visible=self.value['accentSource'] == 'custom')
        row.add_suffix(chooser); main.add(row)
        self.custom_accent_row = row
        self.refreshers.append(lambda: row.set_visible(self.value['accentSource'] == 'custom'))
        row = Adw.ActionRow(title='Background', subtitle='PNG, JPEG or WebP for the main Game Mode interface.')
        buttons = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        choose = Gtk.Button(label='Choose image'); choose.connect('clicked', self.choose_background)
        reset = Gtk.Button(label='Use default'); reset.connect('clicked', lambda *_: self.change('background', None))
        buttons.append(choose); buttons.append(reset); row.add_suffix(buttons); main.add(row)
        self.choice(main, 'Navigation placement', 'navigation', [('top', 'Top'), ('bottom', 'Bottom')])
        self.choice(main, 'Text size', 'text', [('standard', 'Standard'), ('large', 'Large')])
        self.choice(preview_options, 'Interface scale', 'scale', [('auto', 'Automatic'), *[(number, str(number) + '%') for number in (100, 125, 130, 150, 175, 200)]], 'Automatic adapts to the display.')
        details = self.group('Game Details', "Surface Tint follows each game's saved color or artwork.")
        details_options = Adw.PreferencesGroup()
        details_preview_options = Adw.PreferencesGroup()
        details.add(self.preview_panel(details_options, self.details_preview, 'Game Details preview', 'details', details_preview_options))
        self.choice(details_options, 'Surface', 'detailsTheme', [('same', 'Match Game Mode'), ('light', 'Light'), ('clear', 'Clear'), ('dark', 'Dark')])
        self.choice(details_options, 'Accent source', 'accentMode', [('theme', 'None'), ('adaptive', 'Adaptive'), ('custom', 'Game')])
        self.tint_row = Adw.SpinRow.new_with_range(0, 100, 5)
        self.tint_row.set_title('Surface Tint'); self.tint_row.set_subtitle('Tint strength for Game Details.')
        self.tint_row.set_value(self.value['tintStrength'])
        self.tint_row.set_visible(self.value['accentMode'] != 'theme')
        self.tint_row.connect('notify::value', lambda control, *_: self.change('tintStrength', control.get_value()))
        self.refreshers.append(lambda: self.tint_row.set_value(self.value['tintStrength']))
        details_options.add(self.tint_row)
        self.choice(details_preview_options, 'Game Details navigation', 'detailsNavigation', [('sidebar', 'Sidebar'), ('tabs', 'Tabs')])
        reading = self.group('Motion and reset')
        motion = Adw.SwitchRow(title='Motion', subtitle="Follows your system's reduced-motion preference.", active=self.value['motion'])
        motion.connect('notify::active', lambda control, *_: self.change('motion', control.get_active()))
        self.refreshers.append(lambda: motion.set_active(self.value['motion']))
        reading.add(motion)
        reset_row = Adw.ActionRow(title='Reset appearance', subtitle='Restore the Game Mode appearance defaults.')
        reset_button = Gtk.Button(label='Reset', valign=Gtk.Align.CENTER)
        def reset_all(*_):
            try:
                self.value = dict(shared.DEFAULTS) if self.owner.options.demo else shared.save(shared.DEFAULTS, self.config)
                self.refreshing = True
                try:
                    for refresh in self.refreshers:
                        refresh()
                finally:
                    self.refreshing = False
                self.tint_row.set_visible(self.value['accentMode'] != 'theme')
                self.message('Appearance reset.'); self.background = None; self.preview.queue_draw()
            except Exception as error:
                self.message(str(error))
        reset_button.connect('clicked', reset_all); reset_row.add_suffix(reset_button); reading.add(reset_row)
        self.feedback_group = reading

    def choose_background(self, *_):
        picker = Gtk.FileDialog(title='Game Mode background')
        filter = Gtk.FileFilter(name='Images')
        for mime in ('image/png', 'image/jpeg', 'image/webp'):
            filter.add_mime_type(mime)
        filters = Gio.ListStore.new(Gtk.FileFilter); filters.append(filter); picker.set_filters(filters)
        def selected(dialog, result):
            try:
                file = dialog.open_finish(result)
                path = file.get_path()
                if not path or Path(path).stat().st_size > 24 * 1024**2:
                    raise ValueError('Choose an image under 24 MB.')
                image = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 1920, 1080, True)
                data = ''
                for quality in ('85', '70', '50', '35'):
                    encoded = image.save_to_bufferv('jpeg', ['quality'], [quality])[1]
                    data = 'data:image/jpeg;base64,' + base64.b64encode(encoded).decode()
                    if len(data) <= 1600000:
                        break
                self.change('background', data)
            except Exception as error:
                if not (isinstance(error, GLib.Error) and error.code == Gtk.DialogError.DISMISSED):
                    self.message(str(error))
        picker.open(self.owner, None, selected)

    def app_accent(self):
        source = self.value['accentSource']
        if source == 'system':
            return system_accent()
        return shared.FORGE_GREEN if source == 'green' else self.value['accent']

    def draw(self, _widget, cr, width, height):
        cr.scale(width / 480, height / 270)
        light = self.value['theme'] == 'light'
        cr.set_source_rgb(*((.88, .88, .86) if light else (.105, .11, .115))); cr.paint()
        if self.value.get('background') and self.background is None:
            try:
                loader = GdkPixbuf.PixbufLoader.new(); loader.write(base64.b64decode(self.value['background'].split(',', 1)[1])); loader.close()
                self.background = loader.get_pixbuf().scale_simple(480, 270, GdkPixbuf.InterpType.BILINEAR)
            except Exception:
                pass
        backdrop = self.background
        if backdrop is None:
            if light not in self.default_backdrops:
                root = Path(__file__).resolve().parents[1]
                name = 'app-hero-light.png' if light else 'app-hero-dark.png'
                asset = root/'assets/game-mode'/name
                if not asset.is_file():
                    asset = root/'prototypes/game-mode-tauri/public'/name
                try:
                    self.default_backdrops[light] = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(asset), 480, 270, True)
                except GLib.Error:
                    self.default_backdrops[light] = None
            backdrop = self.default_backdrops[light]
        if backdrop:
            Gdk.cairo_set_source_pixbuf(cr, backdrop, 0, 0); cr.paint_with_alpha(.85 if light else .58)
        ink = (.14, .14, .13) if light else (.96, .95, .93)
        def text(value, x, y, size):
            cr.set_source_rgb(*ink); cr.set_font_size(size); cr.move_to(x, y); cr.show_text(value)
        bottom = self.value['navigation'] == 'bottom'
        opacity = .50 if self.value['theme'] == 'clear' else .9
        glass = (.96, .96, .94, opacity) if light else (.16, .16, .17, opacity)
        nav_y, library_y = (231, 10) if bottom else (10, 49)
        def panel(x, y, w, h, radius, color):
            from math import pi
            cr.new_sub_path()
            for cx, cy, angle in ((x+w-radius, y+radius, -.5), (x+w-radius, y+h-radius, 0),
                                  (x+radius, y+h-radius, .5), (x+radius, y+radius, 1)):
                cr.arc(cx, cy, radius, angle*pi, (angle+.5)*pi)
            cr.close_path()
            cr.set_source_rgba(*color); cr.fill()
        accent = Gdk.RGBA(); accent.parse(self.app_accent())
        panel(107, nav_y, 270, 30, 15, glass)
        panel(111, nav_y+3, 53, 23, 11, (accent.red, accent.green, accent.blue, .32))
        cr.set_source_rgb(.96, .95, .93); cr.set_font_size(13); cr.move_to(18, nav_y+19); cr.show_text('rtxForge')
        text('Library    Presets    Packages    Extras    Settings', 121, nav_y+19, 10)
        panel(12, library_y, 456, 176, 13, glass)
        text('LIBRARY', 24, library_y+30, 19 if self.value['text'] == 'large' else 16)
        top = library_y + 52
        panel(23, top-2, 67, 100, 7, (accent.red, accent.green, accent.blue, 1))
        for index in range(6):
            panel(25 + index * 72, top, 63, 96, 6, glass)
        for index, (_game, poster) in enumerate(self.posters):
            cr.save(); cr.translate(25 + index * 72, top); cr.scale(63 / poster.get_width(), 96 / poster.get_height())
            Gdk.cairo_set_source_pixbuf(cr, poster, 0, 0); cr.paint(); cr.restore()

    def draw_details(self, _widget, cr, width, height):
        cr.scale(width / 480, height / 270)
        theme = self.value['detailsTheme']
        if theme == 'same':
            theme = self.value['theme']
        light = theme == 'light'
        base = (.92, .90, .87) if light else (.16, .16, .17)
        ink = (.12, .12, .12) if light else (.97, .96, .94)
        cr.set_source_rgb(*base); cr.paint()
        accent = Gdk.RGBA(); accent.parse(self.app_accent())
        tint = 0 if self.value['accentMode'] == 'theme' else self.value['tintStrength'] / 180
        tinted = tuple(channel + (hue-channel)*tint for channel, hue in zip(base, (accent.red,accent.green,accent.blue)))
        bottom = self.value['navigation'] == 'bottom'
        nav_y, hero_y = (239,8) if bottom else (8,39)
        def panel(x,y,w,h,r,color):
            from math import pi
            cr.new_sub_path()
            for cx,cy,angle in ((x+w-r,y+r,-.5),(x+w-r,y+h-r,0),(x+r,y+h-r,.5),(x+r,y+r,1)):
                cr.arc(cx,cy,r,angle*pi,(angle+.5)*pi)
            cr.close_path(); cr.set_source_rgba(*color); cr.fill()
        def label(text,x,y,size):
            cr.set_source_rgb(*ink); cr.set_font_size(size); cr.move_to(x,y); cr.show_text(text)
        glass=(*tinted,.72 if theme=='clear' else .96)
        raised=(accent.red,accent.green,accent.blue,.23)
        panel(12,hero_y,456,190,12,glass)
        if self.detail_hero:
            cr.save(); cr.rectangle(12,hero_y,456,102);cr.clip()
            Gdk.cairo_set_source_pixbuf(cr,self.detail_hero,12,hero_y);cr.paint_with_alpha(.68);cr.restore()
        if self.posters:
            game,poster=self.posters[0]
            cr.save();cr.translate(25,hero_y+31);cr.scale(43/poster.get_width(),65/poster.get_height())
            Gdk.cairo_set_source_pixbuf(cr,poster,0,0);cr.paint();cr.restore()
        else:
            game={}
        panel(121,nav_y,248,24,12,glass)
        panel(124,nav_y+3,45,18,9,raised)
        label('rtxForge',18,nav_y+17,12)
        label('Library    Presets    Packages    Extras    Settings',132,nav_y+15,9)
        label(game.get('name','Game Details')[:31],76,hero_y+65,16)
        panel(74,hero_y+72,246,21,5,glass)
        label('Steam   ·   Overview',82,hero_y+86,9)
        panel(354,hero_y+72,96,21,11,raised)
        label('Update Features',365,hero_y+86,9)
        tabs=self.value['detailsNavigation']=='tabs'
        if tabs:
            panel(23,hero_y+111,54,19,5,raised)
            label('Overview    Features    DLSS Files    Tools    Appearance',30,hero_y+124,9)
        else:
            panel(23,hero_y+111,76,19,5,raised)
            for index,title in enumerate(('Overview','Features','DLSS Files')):
                label(title,30,hero_y+124+20*index,9)
        card_x=23 if tabs else 110
        card_y=hero_y+(136 if tabs else 111)
        card_width=(452-card_x-12)/3
        for index,title in enumerate(('Features','Compatibility','Neural rendering')):
            x=card_x+index*(card_width+6)
            panel(x,card_y,card_width,41,6,raised)
            label(title,x+7,card_y+15,8)
            panel(x+7,card_y+23,card_width*.53,7,3,glass)


def build(owner):
    try:
        return AppearanceSettings(owner).groups
    except Exception as error:
        group = Adw.PreferencesGroup(title='Game Mode appearance')
        group.add(Adw.ActionRow(title='Appearance could not be loaded', subtitle=str(error)))
        return [group]
