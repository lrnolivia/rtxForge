"""Game-menu screenshots and input switching, with no game writes."""
import argparse,json,os,sys,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import GLib,Gtk
from demo_assets import prepare
prepare(ROOT)
options=argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic')
app=ui.Application(options);captured=[]
def capture(name):
    assert app.window.capture(name).is_file();captured.append(name)
def setup():
    w=app.window;w.settings['controller_glyphs']='xbox';w.settings['runtime_provider']='dlss-unlocked'
    w.games.sort(key=lambda g:not bool(g.get('capsule')))
    w.games[0]['feature_mode']='nr-mfg';w.games[0]['profile']='NR + MFG'
    w.set_input_surface(True);w.couch.set_game(w.games[0]);w.couch.open('game')
def presets():
    c=app.window.couch;c.open('presets');c.navigate('right');assert c.pending['nr_strength']!=None
    app.window.couch.open('presets')
def desktop():
    window=app.window;active=window.is_active;window.is_active=lambda:True
    try:
        window.set_input_surface(True)
        for x in (0,5,10,15,20,25,30):window.pointer_input(None,x,0)
        assert window.input_stack.get_visible_child_name()=='desktop'
        window.set_input_surface(True)
    finally:window.is_active=active
    app.window.keyboard_input();assert app.window.input_stack.get_visible_child_name()=='desktop'
    app.window.set_input_surface(True);assert app.window.input_stack.get_visible_child_name()=='couch'
    games=window.games;window.games=[];window.couch.refresh()
    assert window.couch.game is None and window.couch.art.get_paintable() is None and window.couch.title.get_text()=='Your library'
    window.games=games;window.couch.refresh()
def navigation():
    c=app.window.couch;c.open('library');c.navigate('right')
    assert c.game is app.window.games[1]
    c.navigate('up');assert c.zone=='nav'
    c.navigate('right');c.navigate('accept');assert c.page=='packages'
    c.navigate('next');assert c.page=='settings'
    c.navigate('back');assert c.page=='library'
    c.focus(0);c.navigate('accept');assert c.page=='game'
    assert c.context.get_visible()
    c.open('presets')
steps=[setup,lambda:capture('couch-game-1280.png'),presets,lambda:capture('couch-presets-1280.png'),lambda:app.window.couch.open('library'),lambda:capture('couch-library-1280.png'),lambda:app.window.set_default_size(800,600),lambda:capture('couch-library-800.png'),navigation,lambda:capture('couch-presets-800.png'),desktop]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(550,step)
        else:(ROOT/'dist/ui-couch-review.json').write_text(json.dumps({'game_writes':False,'screenshots':captured},indent=2));app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(1800,step)
result=app.run([sys.argv[0]]);raise SystemExit(app.exit_code or result)
