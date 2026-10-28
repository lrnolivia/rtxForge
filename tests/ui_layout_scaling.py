"""Native 4K layout, zoom, dialog navigation and controller-hint checks."""
import argparse,os,sys,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import GLib,Gtk
from demo_assets import prepare
prepare(ROOT)
options=argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic')
app=ui.Application(options)

def start():
    w=app.window
    w.settings.update(controller_glyphs='xbox',ui_scale=130)
    w.set_default_size(3840,2160)
    w.set_input_surface(True)
    assert w.couch.page=='library'
    w.couch.set_library_view('capsules')
    if os.environ.get('RTXFORGE_QA_FULLSCREEN'):w.fullscreen()
    w.apply_display_preferences()

def native_scale():
    w=app.window;c=w.couch
    if os.environ.get('RTXFORGE_QA_FULLSCREEN'):assert w.is_fullscreen()
    assert w.presentation_scale==1.0
    assert c.theme.unit==22.5
    assert c.get_width()==w.get_width()
    assert c.layout_width==c.get_width()
    assert w.capture('layout-4k-wide-top.png')
    c.set_library_view('posters')

def cards(c):
    from game_mode import descendants
    return [x for x in descendants(c.body) if isinstance(x,ui.Gtk.Button) and x.has_css_class('gm-gamecard')]

def poster():
    w=app.window;c=w.couch
    from game_mode import ArtPicture,descendants
    first=cards(c)[0];game=c.filtered_games()[0]
    picture=next(x for x in descendants(first) if isinstance(x,ArtPicture))
    assert picture.get_file().get_path()==ui.poster_art_path(game)
    first.grab_focus();c.navigate('right');assert w.get_focus() is cards(c)[1]

def poster_capture():
    w=app.window
    assert w.capture('layout-4k-posters-top.png')
    w.set_display_preference('navigation_position','bottom')

def bottom():
    w=app.window;c=w.couch
    assert c.bottom_nav.get_visible() and c.find_key(c.bottom_nav,'tab-library') is not None
    assert c.header.get_center_widget() is None
    c._hide_hints();assert c.hints.get_opacity()==0
    c.navigate('right');assert c.hints.get_opacity()==1

def bottom_capture():
    assert app.window.capture('layout-4k-posters-bottom.png')
    app.window.couch.open('settings')

def settings():
    w=app.window;c=w.couch
    from game_mode import descendants
    assert c.bottom_nav.get_visible()
    expected={'Gaming Mode':{'Interface','Controller hints','Game Mode scale','Navigation placement'},'System':{'Hardware information'},
              'Library':{'Library layout'},'Appearance':{'Color theme','Reduce motion'}}
    for section,titles in expected.items():
        c.open_settings_section(section)
        assert titles <= {x.get_text() for x in descendants(c.body) if isinstance(x,ui.Gtk.Label)},section
        nav = [x for x in descendants(c.body.current) if isinstance(x, ui.Gtk.Button) and x.has_css_class('gm-navbtn')]
        for button in nav:
            images = [x for x in descendants(button) if isinstance(x, ui.Gtk.Image)]
            assert all(image.get_pixel_size() == c.theme.px(26) for image in images), section
        if section == 'Appearance':
            choices = [x for x in descendants(c.body.current) if isinstance(x, ui.Gtk.Button)
                       and getattr(x, '_gm_key', '').startswith('choice-')]
            assert choices[0]._gm_key == 'choice-Color theme', 'Color theme must be first'
    c.open_settings_section('System')

def settings_capture():
    w=app.window
    assert w.capture('layout-4k-settings-bottom.png')
    w.show_settings()

def panel():
    w=app.window
    # In Game Mode, Settings opens Game Mode's own page, never the native-DPI desktop dialog.
    assert not w.dialog and w.couch.page=='settings'
    assert w.capture('layout-4k-settings-panel.png')
    w.couch.open('library')
    w.set_display_preference('navigation_position','top')
    w.set_display_preference('ui_scale',100)
    w.couch.set_library_view('capsules')
    w.unfullscreen()
    w.set_default_size(800,600)

def compact():
    w=app.window;c=w.couch
    assert w.presentation_scale==1
    assert c.get_width()==w.get_width()
    assert c.header.get_center_widget() is not None and not c.bottom_nav.get_visible()
    assert c.hints.get_opacity()==1
    assert w.capture('layout-compact-top.png')


def header_size(width, height):
    app.window.set_display_preference('ui_scale', 130)
    app.window.set_default_size(width, height)


def header_clearance():
    c = app.window.couch
    brand, tabs, menu = c.header.get_start_widget(), c.header.get_center_widget(), c.header.get_end_widget()
    bounds = [widget.compute_bounds(c.header) for widget in (brand, tabs, menu)]
    assert all(valid for valid, _ in bounds)
    left, nav, right = [rect for _, rect in bounds]
    gap = c.theme.px(20)
    assert left.get_x() + left.get_width() + gap <= nav.get_x(), ('brand/nav collision', c.layout_width, c.theme.header_density)
    assert nav.get_x() + nav.get_width() + gap <= right.get_x(), ('nav/menu collision', c.layout_width, c.theme.header_density)
    assert len([x for x in c.focusable_widgets(tabs) if getattr(x, '_gm_key', '').startswith('tab-')]) == 5

steps=[start,native_scale,poster,poster_capture,bottom,bottom_capture,settings,settings_capture,panel,compact]
for width, height in ((960, 540), (1280, 720), (1920, 1080)):
    steps.extend([lambda w=width, h=height: header_size(w, h), header_clearance])
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(1800,step)
        else:print('PASS: native 4K scaling, Library artwork, top/bottom focus, hints and Settings panels; demo writes disabled',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(2000,step)
result=app.run([sys.argv[0]])
raise SystemExit(app.exit_code or result)
