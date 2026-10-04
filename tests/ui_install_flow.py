"""Write-disabled native install flow and All-actions review regression."""
import argparse,os,sys,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import Gtk,Adw,GLib
options=argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic')
app=ui.Application(options)
def children(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from children(child);child=child.get_next_sibling()
def capture(name):
    assert app.window.capture(name)
def start():
    w=app.window;w.scan=lambda *args:None;w.set_default_size(1440,960)
    w.settings['runtime_provider']='dlss-unlocked';w.games=w.games[:4];w.selected_game_ids.clear();w.show_games(w.games,False)
    w.launch_action('install',entire=True)
def presets():
    capture('install-flow-01-presets.png')
    w=app.window
    w.calls=[];w.execute=lambda *args:w.calls.append(args)
    def prepare(rows,mode,operation,*args,**kwargs):
        assert len(rows)==4
        return {'kind':'engine','operation':operation,'title':'Review Installation' if operation=='install' else 'Review Restoration','plans':[],'rows':[{'name':g['name'],'detail':('DLSS-Unlocked · 6 feature files · Your existing settings will be backed up' if operation=='install' else 'Restore 6 original files · Keep your other launch settings')} for g in rows[:3]],'blocked':[{'name':rows[3]['name'],'reason':'Preview: another graphics tool owns this proxy DLL.'}]}
    w.service.prepare=prepare
    w.start=lambda title,work,done:done(work())
    w.options.demo=False
    w.launch_action('install',entire=True,_presets_confirmed=True)
    w.options.demo=True
    assert w.calls==[]
def review():
    w=app.window
    assert len([x for x in children(w.dialog.get_child()) if isinstance(x,Adw.ExpanderRow)])==4
    first=next(x for x in children(w.dialog.get_child()) if isinstance(x,Adw.ExpanderRow) and x.get_title()==w.games[0]['name']);first.set_expanded(True)
def review_capture():
    capture('install-flow-02-review.png')
    w=app.window
    apply=next(x for x in children(w.dialog.get_child()) if isinstance(x,Gtk.Button) and x.get_label()=='Install')
    apply.emit('clicked');assert len(w.calls)==1
    d,b,f=w.calls[0][1:]
    w.progress_view(b,'Installing features…');w.add_cancel(f)
    w.update_progress_art(w.games[0]['name']);w.job_counter.set_text('1 / 3');w.job_bar.set_fraction(.35)
    w.flow_footer=f

def progress():
    capture('install-flow-03-progress.png')
    app.window.finish_progress(True,'3 games updated. Preview only; no game files were changed.',app.window.flow_footer)
def done():
    capture('install-flow-04-done.png')
    w=app.window;w.calls.clear();w.options.demo=False
    w.launch_action('uninstall',entire=True)
    w.options.demo=True
    assert w.calls==[]
def restore():
    w=app.window
    assert len([x for x in children(w.dialog.get_child()) if isinstance(x,Adw.ExpanderRow)])==4
    capture('install-flow-05-restore-review.png')
    assert w.calls==[]
def blocked():
    w=app.window
    d,b,f=w.open_panel('Review Restoration',show_close=False)
    w.action_ready({'operation':'uninstall','rows':[],'blocked':[{'name':w.games[0]['name'],'reason':'No terminal-engine baseline; use legacy Undo for an older app install'},{'name':w.games[1]['name'],'reason':'Executable selection changed; refresh the library'}]},d,b,f)
    texts=[x.get_label() for x in children(w.dialog.get_child()) if isinstance(x,Gtk.Button)]
    assert 'Previous Changes' in texts and 'Close' in texts and 'Cancel' not in texts
    assert not w.calls
steps=[start,presets,review,review_capture,progress,done,restore,blocked]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(1100,step)
        else:print('PASS: Install All and Restore All populate review and do not execute before explicit click; native install flow captured; all game writes disabled',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(2200,step)
result=app.run([sys.argv[0]])
raise SystemExit(app.exit_code or result)
