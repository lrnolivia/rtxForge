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
    w.settings['runtime_provider']='dlss-unlocked';w.games=w.games[:5]
    for g in w.games[:4]:g['blocked']='';g['test_record']={'status':'Untested'}
    w.games[4]['blocked']='No native DLSS-G detected';w.selected_game_ids.clear();w.show_games(w.games,False)
    w.select_all(True)
    assert w.selected_game_ids=={g['game'] for g in w.games[:4]}
    assert w.cards[w.games[4]['game']]['picture'].get_opacity()<0.5
    assert w.cards[w.games[4]['game']]['overlay'].support_info.get_visible()
    w.select_all(False)
    w.install_all.emit('clicked')
def presets():
    capture('install-flow-01-presets.png')
    w=app.window
    w.calls=[];w.execute=lambda *args:w.calls.append(args)
    def prepare(rows,mode,operation,*args,**kwargs):
        assert len(rows)==4
        return {'kind':'engine','operation':operation,'title':'Review Installation' if operation=='install' else 'Review Restoration','plans':[],'rows':[{'name':g['name'],'detail':('DLSS-Unlocked · 6 feature files · Your existing settings will be backed up' if operation=='install' else 'Restore 6 original files · Keep your other launch settings')} for g in rows[:3]],'blocked':[{'name':rows[3]['name'],'reason':'Preview: another graphics tool owns this proxy DLL.'}]}
    w.service.prepare=prepare
    w.options.demo=False
    continue_button=next(x for x in children(w.dialog.get_child()) if isinstance(x,Gtk.Button) and x.get_label()=='Continue')
    continue_button.emit('clicked')
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
    w.uninstall_all.emit('clicked')
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
def dlss_header():
    w=app.window
    w.update_dlss_button.emit('clicked')
def dlss_review():
    w=app.window
    assert w.dialog.get_title()=='Update DLSS Files'
    assert len([x for x in children(w.dialog.get_child()) if x.has_css_class('review-game')])==4
    assert not w.calls
    capture('install-flow-06-header-dlss-review.png')
def widths():
    w=app.window
    d,b,f=w.open_panel('Grouped actions')
    group=Adw.PreferencesGroup();b.append(group);w.width_buttons=[]
    for title in ['Install','Repair','Restore Original Files']:
        row=Adw.ActionRow(title=title);control=ui.button(title,lambda *_:None)
        row.add_suffix(control);group.add(row);w.width_buttons.append(control)
def widths_check():
    assert len({x.get_width() for x in app.window.width_buttons})==1
    assert ui.action_icon('Details')=='help-about-symbolic'
    capture('install-flow-07-action-widths.png')
    app.window.dialog.close();app.window.main_menu.popup()
def menu_check():
    entries=[x for x in children(app.window.main_menu.get_popover()) if isinstance(x,ui.ActionButton)]
    assert len(entries)==6
    assert all(x.get_child().get_halign()==Gtk.Align.START for x in entries)
    app.window.main_menu.popup()
def menu_capture():
    capture('install-flow-08-left-menu.png')
    app.window.main_menu.popdown();app.window.view_buttons['list'].set_active(True)
    ui.apply_corner_style('rounded')
def rounded():
    w=app.window
    root=w.list_name_cells[w.games[4]['game']]
    assert not root._check.get_sensitive()
    assert root._artwork.picture.support_desaturated
    assert root._artwork.support_info.get_visible()
    assert w.list_action_cells[w.games[4]['game']]._primary.get_sensitive()
    assert w.library_stack.get_parent().get_margin_bottom()==16
    capture('install-flow-09-rounded-list.png')
    ui.apply_corner_style('square')
def square():
    w=app.window;capture('install-flow-10-square-list.png')
    w.set_input_surface(True);w.couch.open('library');w.couch.set_library_view('list')
def couch_support():
    w=app.window
    art=w.couch.controls[4].artwork
    assert art.picture.support_desaturated and art.picture.get_opacity()<0.5
    assert art.support_info.get_visible()
    w.couch.dlss_selection=set();w.couch.toggle_dlss_game(w.games[4])
    assert w.couch.dlss_selection==set()
    capture('install-flow-11-unsupported-couch.png')
steps=[start,presets,review,review_capture,progress,done,restore,blocked,dlss_header,dlss_review,widths,widths_check,menu_check,menu_capture,rounded,square,couch_support]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(1100,step)
        else:print('PASS: real header Install/Restore/DLSS clicks reach review without writes; unsupported selection/bulk exclusion and muted artwork in both UIs; equal row widths, Details info icon, left menu, square/rounded list headers and bottom padding',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(2200,step)
result=app.run([sys.argv[0]])
raise SystemExit(app.exit_code or result)
