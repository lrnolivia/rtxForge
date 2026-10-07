"""Native Library-first checks using demo games and intercepted operations."""
import argparse,os,sys,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import GLib
app=ui.Application(argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic'))
def start():
    w=app.window;w.set_default_size(1440,960);w.set_input_surface(True)
    assert w.couch.page=='library', f'Initial Game Mode page: {w.couch.page}'
    w.games=w.games[:3]
    for game in w.games:game['blocked']='Unsupported fixture';game['installed']=False
    w.filter='available';w.couch.render()
    assert w.couch.library_count.get_text()=='0 shown of 3 games · 0 configured'
    assert not w.couch.library_action.get_sensitive()
    assert not w.couch.library_restore.get_sensitive()
    assert not w.couch.library_update.get_sensitive()
    w.games[0]['blocked']='';w.games[0]['installed']=True
    w.couch.render()
    assert w.couch.library_count.get_text()=='1 shown of 3 games · 1 configured'
    assert all(button.get_sensitive() for button in (w.couch.library_action,w.couch.library_restore,w.couch.library_update))
    calls=[];w.launch_action=lambda *args,**kwargs:calls.append(('restore',args,kwargs));w.update_dlss_games=lambda rows:calls.append(('update',rows))
    w.couch.zone='views';w.couch.view_index=2
    w.couch.navigate('accept');w.couch.navigate('right');w.couch.navigate('accept')
    assert [call[0] for call in calls]==['restore','update']
    assert calls[0][2]['targets']==[w.games[0]] and calls[1][1]==[w.games[0]]
    assert w.couch.install_targets()==[w.games[0]]
    w.couch.open('features_all')
    assert w.couch.panel_detail.get_text()=='Available games: 1'
    w.couch.open('library')
    w.couch.dlss_selection=set();w.couch.render()
    w.couch.zone='views';w.couch.view_index=1;w.couch.navigate('right')
    assert w.couch.view_index==0, 'Hidden Restore/Update must be skipped'
    w.couch.dlss_selection=None;w.couch.render()
def branding():
    couch=app.window.couch
    couch.update_branding(80)
    assert couch.brand_icon.get_pixel_size()==40 and couch.brand_button.has_css_class('collapsed')
    couch.update_branding(0)
    assert couch.brand_icon.get_pixel_size()==72 and not couch.brand_button.has_css_class('collapsed')
def capture():
    assert app.window.capture('resume-library-first.png').is_file()
steps=[start,branding,capture]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(800,step)
        else:print('PASS: Library-first, truthful empty/filtered counts, independent reviewed Restore/Update, collapsing brand; no game or Steam writes',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(1800,step);app.run([]);raise SystemExit(app.exit_code)
