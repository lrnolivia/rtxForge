"""GTK controls for the native Game Mode appearance contract."""
import base64
from pathlib import Path
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GdkPixbuf, Gio, GLib
import game_mode_appearance as shared


class AppearanceSettings:
    def __init__(self, owner):
        self.owner = owner
        self.config = owner.service.config
        self.value = shared.load(self.config) or dict(shared.DEFAULTS)
        self.groups = []
        self.refreshers = []
        self.refreshing = False
        self.feedback_group = None
        self.details = False
        self.background = None
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
        self.preview = Gtk.DrawingArea(content_width=480, content_height=270, hexpand=True)
        self.preview.set_draw_func(self.draw)
        self.feedback = Gtk.Label(xalign=0, wrap=True, visible=False)
        self.feedback.add_css_class('dim-label')
        self.tint_row = None
        self.build()

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
            if self.tint_row:
                self.tint_row.set_visible(self.value['accentMode'] != 'theme')
            self.preview.queue_draw()
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

    def build(self):
        from overlay_layouts import ThemePicker
        surface = self.group('Game Mode appearance', 'The same preferences as Game Mode, saved automatically.')
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
        body.append(Gtk.Label(label='Surface', xalign=0))
        themes = ThemePicker(self.value['theme'], lambda value: self.change('theme', value))
        def refresh_themes():
            child = themes.get_first_child()
            for key in ('light', 'clear', 'dark'):
                child.set_active(self.value['theme'] == key); child = child.get_next_sibling()
        self.refreshers.append(refresh_themes)
        body.append(themes)
        sample_choice = Gtk.DropDown(model=Gtk.StringList.new(['Library preview', 'Game Details preview']))
        sample_choice.connect('notify::selected', lambda control, *_: self.sample(control.get_selected() == 1))
        body.append(sample_choice)
        frame = Gtk.AspectFrame(ratio=16 / 9, obey_child=False, child=self.preview)
        body.append(Adw.Clamp(child=frame, maximum_size=480, tightening_threshold=380))
        custom = Adw.PreferencesRow(child=body)
        surface.add(custom)
        main = self.group('Main interface', 'Navigation and focus use this accent. Game colors remain separate.')
        color = Gdk.RGBA(); color.parse(self.value['accent'])
        chooser = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(title='Game Mode accent color', with_alpha=False), rgba=color, valign=Gtk.Align.CENTER)
        chooser.connect('notify::rgba', lambda control, *_: self.change('accent', '#%02x%02x%02x' % tuple(round(channel * 255) for channel in (control.get_rgba().red, control.get_rgba().green, control.get_rgba().blue))))
        def refresh_color():
            value = Gdk.RGBA(); value.parse(self.value['accent']); chooser.set_rgba(value)
        self.refreshers.append(refresh_color)
        row = Adw.ActionRow(title='Accent color'); row.add_suffix(chooser); main.add(row)
        row = Adw.ActionRow(title='Background', subtitle='PNG, JPEG or WebP for the main Game Mode interface.')
        buttons = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        choose = Gtk.Button(label='Choose image'); choose.connect('clicked', self.choose_background)
        reset = Gtk.Button(label='Use default'); reset.connect('clicked', lambda *_: self.change('background', None))
        buttons.append(choose); buttons.append(reset); row.add_suffix(buttons); main.add(row)
        details = self.group('Game Details', "Surface Tint follows each game's saved color or artwork.")
        self.choice(details, 'Accent', 'accentMode', [('theme', 'None'), ('adaptive', 'Adaptive'), ('custom', 'Game')])
        self.tint_row = Adw.SpinRow.new_with_range(0, 100, 5)
        self.tint_row.set_title('Surface Tint'); self.tint_row.set_subtitle('Tint strength for Game Details.')
        self.tint_row.set_value(self.value['tintStrength'])
        self.tint_row.set_visible(self.value['accentMode'] != 'theme')
        self.tint_row.connect('notify::value', lambda control, *_: self.change('tintStrength', control.get_value()))
        self.refreshers.append(lambda: self.tint_row.set_value(self.value['tintStrength']))
        details.add(self.tint_row)
        self.choice(details, 'Game Details navigation', 'detailsNavigation', [('sidebar', 'Sidebar'), ('tabs', 'Tabs')])
        reading = self.group('Reading and motion')
        self.choice(reading, 'Text size', 'text', [('standard', 'Standard'), ('large', 'Large')])
        motion = Adw.SwitchRow(title='Motion', subtitle="Follows your system's reduced-motion preference.", active=self.value['motion'])
        motion.connect('notify::active', lambda control, *_: self.change('motion', control.get_active()))
        self.refreshers.append(lambda: motion.set_active(self.value['motion']))
        reading.add(motion)
        layout = self.group('Layout')
        self.choice(layout, 'Navigation placement', 'navigation', [('top', 'Top'), ('bottom', 'Bottom')])
        self.choice(layout, 'Interface scale', 'scale', [('auto', 'Automatic'), *[(number, str(number) + '%') for number in (100, 125, 130, 150, 175, 200)]], 'Automatic adapts to the display.')
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
        reset_button.connect('clicked', reset_all); reset_row.add_suffix(reset_button); layout.add(reset_row)
        self.feedback_group = layout

    def sample(self, details):
        self.details = details
        self.preview.queue_draw()

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
        if self.background:
            Gdk.cairo_set_source_pixbuf(cr, self.background, 0, 0); cr.paint()
        ink = (.14, .14, .13) if light else (.96, .95, .93)
        def text(value, x, y, size):
            cr.set_source_rgb(*ink); cr.set_font_size(size); cr.move_to(x, y); cr.show_text(value)
        bottom = self.value['navigation'] == 'bottom'
        cr.set_source_rgba(*((.96, .96, .94, .8) if light else (.14, .14, .14, .8)))
        cr.rectangle(16, 224 if bottom else 16, 448, 30); cr.fill()
        text('rtxForge    Library    Presets    Packages    Settings', 28, 244 if bottom else 36, 12)
        title = self.posters[0][0].get('name', 'Game Details') if self.details and self.posters else 'Your library'
        text(title[:35], 20, 48 if bottom else 84, 23 if self.value['text'] == 'large' else 20)
        for index, (_game, poster) in enumerate(self.posters):
            cr.save(); cr.translate(20 + index * 73, 70 if bottom else 102); cr.scale(65 / poster.get_width(), 100 / poster.get_height())
            Gdk.cairo_set_source_pixbuf(cr, poster, 0, 0); cr.paint(); cr.restore()
        if self.details:
            color = Gdk.RGBA(); color.parse(self.value['accent'])
            cr.set_source_rgba(color.red, color.green, color.blue, .3 + self.value['tintStrength'] / 150 if self.value['accentMode'] != 'theme' else .85)
            cr.rectangle(150, 102, 300, 105); cr.fill()
            text('Overview   Graphics' if self.value['detailsNavigation'] == 'tabs' else 'Overview', 166, 130, 14)
            text('ReShade & add-ons', 166, 158, 14)


def build(owner):
    try:
        return AppearanceSettings(owner).groups
    except Exception as error:
        group = Adw.PreferencesGroup(title='Game Mode appearance')
        group.add(Adw.ActionRow(title='Appearance could not be loaded', subtitle=str(error)))
        return [group]
