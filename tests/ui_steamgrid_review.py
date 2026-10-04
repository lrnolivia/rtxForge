"""Exercise the artwork modal using local fixtures, never API credentials or game writes."""
import argparse,json,os,sys,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
import steamgrid_client
from gi.repository import Gtk,Adw,GLib,GdkPixbuf
options=argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic')
app=ui.Application(options);calls=[];captures=[];game=None
class FixtureClient:
    def __init__(self,*args,**kwargs):pass
    def search(self,title):calls.append(('search',title));return [{'id':1,'name':game['name']}]
    def artwork(self,game_id,role,**options):
        calls.append(('artwork',role,options));return [{'id':i,'url':'fixture:'+str(i),'thumb':'fixture:'+str(i),'width':600,'height':900,'author':{'name':'Local fixture '+str(i)}} for i in range(1,5)]
    @staticmethod
    def thumbnail(asset):return FixtureClient.download(asset)
    @staticmethod
    def download(asset):
        path=ui.poster_art_path(game)
        if path and Path(path).is_file():return Path(path).read_bytes()
        pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,144,216);pix.fill(0x76b900ff);return bytes(pix.save_to_bufferv('png',[],[])[1])
steamgrid_client.Client=FixtureClient

def open_browser():
    global game
    game=app.window.games[0];app.window.open_steamgrid_search(game,'poster')

def capture(name):
    view=app.window._steamgrid_review
    assert len(view['state']['assets'])==4,view['status'].get_text()
    assert app.window.capture(name).is_file();captures.append(name)

def preview():
    view=app.window._steamgrid_review
    first=view['grid'].get_first_child().get_child();first.emit('clicked')

def verify_preview():
    view=app.window._steamgrid_review
    assert view['stack'].get_visible_child_name()=='preview',view['status'].get_text()
    assert app.window.dialog is view['dialog']
    capture('steamgrid-desktop-preview.png');view['back']()

def filter_results():
    app.window._steamgrid_review['style'].set_selected(2)

def verify_filter():
    assert any(x[0]=='artwork' and x[2].get('style')=='white_logo' for x in calls),calls
    capture('steamgrid-desktop-filtered.png');app.window.dialog.close()

def couch():
    ui.COUCH_MODE='couch';app.window.input_stack.set_visible_child_name('couch')
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK);open_browser()

steps=[open_browser,lambda:capture('steamgrid-desktop-results.png'),preview,verify_preview,filter_results,verify_filter,couch,lambda:capture('steamgrid-couch-results.png'),lambda:app.window.dialog.close()]
def advance():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(1000,advance)
        else:
            (ROOT/'dist/steamgrid-review.json').write_text(json.dumps({'fixture_only':True,'game_writes':False,'api_calls':False,'captures':captures,'calls':calls},indent=2));app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(1800,advance)
result=app.run([sys.argv[0]]);raise SystemExit(app.exit_code or result)
