"""Exercise the artwork modal using local fixtures, never API credentials or game writes."""
import argparse,json,os,sys,traceback,time
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

class PreviewNotReady(Exception):pass

def capture(name):
    view=app.window._steamgrid_review
    assert len(view['state']['assets'])==4,view['status'].get_text()
    child=view['grid'].get_first_child()
    while child:
        picture=child.get_child().get_child().get_first_child()
        if picture.get_paintable() is None:raise PreviewNotReady(name)
        child=child.get_next_sibling()
    path=app.window.capture(name)
    if path is None:raise PreviewNotReady(name)
    assert path.is_file();captures.append(name)

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


# Mock only the native chooser boundary; exercise real GTK panel ownership.
picker_calls=[]
class FixtureFileDialog:
    def __init__(self,**kwargs):self.modal=False
    def set_modal(self,value):self.modal=value
    def set_filters(self,filters):pass
    def open(self,parent,cancellable,callback):
        self.parent=parent;self.callback=callback;picker_calls.append(self)
    def open_finish(self,result):raise GLib.Error('User dismissed the file chooser')

def details_for_picker():
    global game
    game=app.window.games[0];app.window.details(game)

def verify_picker_parent():
    original=ui.Gtk.FileDialog
    try:
        ui.Gtk.FileDialog=FixtureFileDialog
        parent=app.window.dialog
        assert isinstance(parent,ui.ResizablePanelWindow)
        assert parent.get_visible()
        app.window.choose_game_artwork(game,'poster')
        chooser=picker_calls[-1]
        assert chooser.parent is parent and chooser.modal
        count=len(picker_calls)
        app.window.choose_game_artwork(game,'hero')
        assert len(picker_calls)==count,'Duplicate native modals'
        chooser.callback(chooser,None)
        assert app.window._artwork_file_chooser is None
        assert app.window.dialog is parent and parent.get_visible()
        app.window.choose_game_artwork(game,'hero')
        assert len(picker_calls)==count+1,'Cancel did not restore chooser action'
        picker_calls[-1].callback(picker_calls[-1],None)
        parent.close()
    finally:ui.Gtk.FileDialog=original

def embedded_for_picker():
    app.window.open_panel('Embedded artwork',width=600,height=400)

def verify_embedded_picker_parent():
    original=ui.Gtk.FileDialog
    try:
        ui.Gtk.FileDialog=FixtureFileDialog
        panel=app.window.dialog
        assert not isinstance(panel,Gtk.Window)
        app.window.choose_game_artwork(game,'poster')
        chooser=picker_calls[-1]
        assert chooser.parent is app.window and chooser.modal
        chooser.callback(chooser,None)
        assert app.window._artwork_file_chooser is None
        panel.close()
    finally:ui.Gtk.FileDialog=original

def connection_open():
    app.window.show_steamgrid_connection()

def connection_preview():
    view=app.window._steamgrid_connection_review
    assert isinstance(view['entry'],Gtk.PasswordEntry)
    assert not view['connect'].get_sensitive()
    assert 'Preview only' in view['status'].get_text()
    assert view['entry'].get_text()==''
    path=app.window.capture('steamgrid-connect-preview.png')
    if path is None:raise PreviewNotReady('SteamGridDB connection panel')
    assert path.is_file()
    captures.append('steamgrid-connect-preview.png')
    view['dialog'].close()
    assert view['state']['closed']

steps=[connection_open,connection_preview,details_for_picker,verify_picker_parent,embedded_for_picker,verify_embedded_picker_parent,open_browser,lambda:capture('steamgrid-desktop-results.png'),preview,verify_preview,filter_results,verify_filter,couch,lambda:capture('steamgrid-couch-results.png'),lambda:app.window.dialog.close()]
preview_deadline=None
def advance():
    global preview_deadline
    try:
        if steps:
            try:steps[0]()
            except PreviewNotReady:
                if preview_deadline is None:preview_deadline=time.monotonic()+5
                if time.monotonic()>=preview_deadline:raise AssertionError('Native review surface did not become ready at step '+str(steps[0]))
                GLib.timeout_add(100,advance);return False
            steps.pop(0);preview_deadline=None;GLib.timeout_add(1000,advance)
        else:
            (ROOT/'dist/steamgrid-review.json').write_text(json.dumps({'fixture_only':True,'game_writes':False,'api_calls':False,'captures':captures,'calls':calls},indent=2));app.quit()
    except Exception:
        detail=traceback.format_exc()
        traceback.print_exc()
        if os.environ.get('GITHUB_ACTIONS'):
            safe=detail.replace('%','%25').replace('\r','%0D').replace('\n','%0A')
            print('::error title=SteamGridDB UI review::'+safe,flush=True)
        app.exit_code=1;app.quit()
    return False
GLib.timeout_add(1800,advance)
result=app.run([sys.argv[0]]);raise SystemExit(app.exit_code or result)
