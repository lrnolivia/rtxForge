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
    w.settings['controller_glyphs']='xbox'
    w.set_default_size(3840,2160)
    w.set_input_surface(True)
    assert w.couch.page=='library'
    w.couch.set_library_view('capsules')
    if os.environ.get('RTXFORGE_QA_FULLSCREEN'):w.fullscreen()
    w.apply_display_preferences()

def native_scale():
    w=app.window;c=w.couch
    if os.environ.get('RTXFORGE_QA_FULLSCREEN'):assert w.is_fullscreen()
    assert w.presentation_scale==1.5
    assert c.get_width()==round(w.get_width()/1.5)
    assert c.layout_width==c.get_width()
    assert w.capture('layout-4k-wide-top.png')
    c.set_library_view('posters')

def poster():
    w=app.window;c=w.couch
    assert c.controls[0].artwork.picture.get_file().get_path()==c.entries[0]['game']['poster']
    c.focus(0);c.navigate('right');assert c.current==1

def poster_capture():
    w=app.window
    assert w.capture('layout-4k-posters-top.png')
    w.set_display_preference('navigation_position','bottom')

def bottom():
    w=app.window;c=w.couch
    assert c.tab_bar.get_parent() is c.bottom_nav
    c.focus(len(c.entries)-1)
    c.navigate('down');assert c.zone=='nav'
    c.navigate('up');assert c.zone=='content'
    c.hide_hints();assert c.prompts.get_opacity()==0
    c.navigate('right');assert c.prompts.get_opacity()==1

def bottom_capture():
    assert app.window.capture('layout-4k-posters-bottom.png')
    app.window.couch.open('settings')

def settings():
    w=app.window;c=w.couch
    assert c.tab_bar.get_parent() is c.bottom_nav
    expected={'Gaming Mode':{'Interface'},'System':{'UI scale','Navigation'},
              'Library':{'Library layout'},'Controller':{'Controller hints'}}
    for section,titles in expected.items():
        c.set_section(section)
        assert titles <= {e['title'] for e in c.entries},section
    c.set_section('System')
    assert w.capture('layout-4k-settings-bottom.png')
    w.show_settings()

def panel():
    w=app.window
    assert isinstance(w.dialog,ui.PresentationDialog)
    assert w.dialog._scaled_child.factor==1.5
    assert w.dialog._scaled_child.child.get_last_child().has_css_class('couch-tabs')
    assert w.capture('layout-4k-settings-panel.png')
    nav=w.dialog._scaled_child.child.get_last_child()
    nav.get_first_child().emit('clicked')
    assert w.couch.page=='library'
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
    assert c.tab_bar.get_parent() is c.top
    assert c.prompts.get_opacity()==1
    assert w.capture('layout-compact-top.png')

steps=[start,native_scale,poster,poster_capture,bottom,bottom_capture,settings,panel,compact]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(1800,step)
        else:print('PASS: native 4K scaling, Library artwork, top/bottom focus, hints and Settings panels; demo writes disabled',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(2000,step)
result=app.run([sys.argv[0]])
raise SystemExit(app.exit_code or result)
