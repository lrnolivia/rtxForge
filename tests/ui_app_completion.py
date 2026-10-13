"""Native GTK verification of new app surfaces; game writes disabled."""
import argparse,json,os,sys,traceback,time
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import Gtk,Adw,GLib
options=argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic')
app=ui.Application(options);results=[];native={}

def palette():
    context=Gtk.Label().get_style_context()
    return {name:context.lookup_color(name)[1].to_string() for name in ('window_bg_color','view_bg_color','sidebar_bg_color','card_bg_color')}

def theme(mode):
    ui.THEME_MODE=mode
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT if mode=='light' else Adw.ColorScheme.FORCE_DARK)
    # Capture stock colors with app overrides removed.
    ui.NEUTRAL_PROVIDER.load_from_data(b'')
    native[mode]=palette()
    ui.apply_neutral_palette()
    if mode!='night':assert palette()==native[mode],(mode,palette(),native[mode])
    app.window.settings['theme']=mode


class FrameNotReady(Exception):pass

def capture(name):
    path=app.window.capture(name)
    if path is None:raise FrameNotReady(name)
    assert path.is_file();results.append(name)


def reduced_motion():
    settings=Gtk.Settings.get_default();settings.set_property('gtk-enable-animations',False)
    d,_,_=app.window.open_panel('Motion fixture',width=400,height=250)
    app.window.animate_dialog_width(642);app.window.animate_dialog_height(d,442)
    assert d.get_content_width()==642 and d.get_content_height()==442,(d.get_content_width(),d.get_content_height())
    settings.set_property('gtk-enable-animations',True)


def couch():
    ui.COUCH_MODE='couch'
    row=ui.safe_combo_row(title='Fixture',model=Gtk.StringList.new(['a','b']))
    seen=[];row.connect('notify::selected',lambda *_:seen.append(row.get_selected()))
    row.choice.set_selected(1);assert row.get_selected()==1 and seen==[1]
    app.window.show_settings()

steps=[lambda:theme('light'),lambda:capture('completion-light.png'),lambda:theme('night'),lambda:capture('completion-night.png'),lambda:theme('dark'),lambda:app.window.show_settings(),lambda:capture('completion-settings.png'),reduced_motion,lambda:app.window.dialog.close(),lambda:app.window.details(app.window.games[0]),lambda:app.window.detail_pages.set_visible_child_name('Tools'),lambda:capture('completion-tools.png'),lambda:app.window.show_diagnostics(app.window.games[0]),lambda:capture('completion-diagnostics.png'),lambda:app.window.show_reports(),lambda:capture('completion-reports.png'),lambda:app.window.preview_report({'library.json':'{"name":"Demo", "visual_result":"Not established"}'}),lambda:capture('completion-report-preview.png'),lambda:app.window.show_controller_menu(),lambda:capture('completion-controller-menu.png'),couch,lambda:capture('completion-couch-settings.png'),lambda:app.window.details(app.window.games[0]),lambda:app.window.detail_pages.set_visible_child_name('Tools'),lambda:capture('completion-couch-tools.png'),lambda:app.window.dialog.close(),lambda:app.window.toggle_compact_header(),lambda:capture('completion-couch-library.png')]

capture_deadline=None
def step():
    global capture_deadline
    try:
        if steps:
            try:steps[0]()
            except FrameNotReady:
                if capture_deadline is None:capture_deadline=time.monotonic()+5
                if time.monotonic()>=capture_deadline:raise AssertionError('Native frame did not become capturable within five seconds')
                GLib.timeout_add(100,step);return False
            steps.pop(0);capture_deadline=None;GLib.timeout_add(400,step)
        else:
            (ROOT/'dist/ui-app-completion.json').write_text(json.dumps({'game_writes':False,'screenshots':results,'native_roles':native},indent=2));app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(1500,step)
result=app.run([sys.argv[0]])
raise SystemExit(app.exit_code or result)
