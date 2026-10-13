"""Native joined library/review grouping, shared media and explicit actions."""
import argparse,os,sys,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import Gtk,Adw,GLib
app=ui.Application(argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic'))
def children(widget):
    yield widget
    child=widget.get_first_child()
    while child:yield from children(child);child=child.get_next_sibling()
def start():
    w=app.window;w.scan=lambda *args:None;w.set_default_size(1440,960)
    w.games=w.games[:3];w.show_games(w.games,False);w.view_buttons['list'].set_active(True)
def library():
    w=app.window;w._column_sync_selection_widgets()
    rows=[]
    for root in w.list_name_cells.values():
        row=root.get_parent()
        while row and row.get_css_name()!='row':row=row.get_parent()
        if row:rows.append(row)
    assert len(rows)==3
    assert sum(x.has_css_class('joined-first') for x in rows)==1
    assert sum(x.has_css_class('joined-last') for x in rows)==1
    for i,row in enumerate(rows):
        assert row.has_css_class('joined-first')==(i==0)
        assert row.has_css_class('joined-last')==(i==2)
    bounds=[x.compute_bounds(w)[1] for x in rows]
    for a,b in zip(bounds,bounds[1:]):assert abs(a.get_y()+a.get_height()-b.get_y())<2
    assert w.capture('joined-library-list.png')
    d,b,f=w.open_panel('Review Installation',width=800,height=650)
    w.operation_games=w.games
    w.action_ready({'operation':'install','rows':[{'name':g['name'],'detail':'Install feature files. Your existing files will be backed up.'} for g in w.games],'blocked':[]},d,b,f)
def sorted_edges():
    w=app.window
    w.list_sort_model.set_sorter(Gtk.CustomSorter.new(lambda a,b,*_:Gtk.Ordering.SMALLER if a.game['name']>b.game['name'] else Gtk.Ordering.LARGER if a.game['name']<b.game['name'] else Gtk.Ordering.EQUAL))
def check_sorted():
    w=app.window;w._column_sync_selection_widgets()
    first=w.list_sort_model.get_item(0).game['game'];last=w.list_sort_model.get_item(2).game['game']
    for game_id,root in w.list_name_cells.items():
        row=root.get_parent()
        while row and row.get_css_name()!='row':row=row.get_parent()
        if row:
            assert row.has_css_class('joined-first')==(game_id==first)
            assert row.has_css_class('joined-last')==(game_id==last)
    w.list_sort_model.set_sorter(None)
def review():
    w=app.window;rows=[x for x in children(w.dialog.get_child()) if isinstance(x,Adw.ExpanderRow)]
    assert len(rows)==3
    pictures=[x for x in children(rows[0]) if isinstance(x,Gtk.Picture)]
    assert len(pictures)==1
    bezel=next(x for x in children(rows[0]) if isinstance(x,ui.ListArtwork))
    assert not bezel.fallback.get_visible()
    texture=ui.Gdk.Texture.new_from_filename(w.games[0]['capsule'])
    assert pictures[0].get_paintable().get_width()==texture.get_width()
    assert rows[0].has_css_class(w._ensure_game_accent(w.games[0]))
    invalid=dict(w.games[0],capsule=None,hero=w.games[0].get('hero'),poster=w.games[0].get('poster'))
    ghost=w.review_entry('Missing capsule',game=invalid)
    placeholder=next(x for x in children(ghost) if isinstance(x,ui.ListArtwork))
    assert placeholder.fallback.get_visible()
    invalid['capsule']=invalid['poster'];assert ui.capsule_art_path(invalid) is None
    widths=[]
    for row in rows:
        bezel=next(x for x in children(row) if x.has_css_class('review-bezel'))
        widths.append(bezel.get_width())
    assert len(set(widths))==1,widths
    rows[0].set_expanded(True)
def capture_review():
    w=app.window;assert w.capture('joined-install-review.png')
    w.update_dlss_games(w.games)
def dlss():
    w=app.window
    assert len([x for x in children(w.dialog.get_child()) if x.has_css_class('review-game')])==3
    assert w.capture('joined-dlss-review.png')
    listing=next(x for x in children(w.dialog.get_child()) if x.has_css_class('review-list'))
    scroll=listing.get_parent().get_parent()
    if isinstance(scroll,Gtk.Viewport):scroll=scroll.get_parent()
    last=listing.get_last_child();bounds=last.compute_bounds(scroll)[1]
    assert bounds.get_y()+bounds.get_height()<=scroll.get_height()+1
    w.dialog.close()
    targets=[dict(w.games[i%3],game='fixture-'+str(i)) for i in range(5)]
    w.update_dlss_games(targets)
def five():
    w=app.window
    listing=next(x for x in children(w.dialog.get_child()) if x.has_css_class('review-list'))
    scroll=listing.get_parent().get_parent()
    if isinstance(scroll,Gtk.Viewport):scroll=scroll.get_parent()
    bounds=listing.get_last_child().compute_bounds(scroll)[1]
    assert bounds.get_y()+bounds.get_height()<=scroll.get_height()+1
    assert w.capture('joined-five-game-review.png')
    w.dialog.close()
    w.update_dlss_games([dict(w.games[i%3],game='fixture-'+str(i)) for i in range(6)])
def six():
    w=app.window
    listing=next(x for x in children(w.dialog.get_child()) if x.has_css_class('review-list'))
    scroll=listing.get_parent().get_parent()
    if isinstance(scroll,Gtk.Viewport):scroll=scroll.get_parent()
    rows=[x for x in children(listing) if isinstance(x,Adw.ActionRow)]
    fifth=rows[4].compute_bounds(scroll)[1];sixth=rows[5].compute_bounds(scroll)[1]
    assert fifth.get_y()+fifth.get_height()<=scroll.get_height()+1
    assert sixth.get_y()>=scroll.get_height()-1
    assert w.capture('joined-six-game-review.png')
    w.dialog.close()
    w.review_extra({'kind':'reshade','name':w.games[0]['name'],'game':w.games[0]['game'],'changes':[{'path':'dxgi.dll','after':'fixture-hash'}]})
def tool():
    w=app.window
    assert len([x for x in children(w.dialog.get_child()) if x.has_css_class('review-game')])==1
    trust=next(x for x in children(w.dialog.get_child()) if isinstance(x,Gtk.CheckButton))
    assert not trust.get_active()
    w.dialog.close();w.preview_report({'status.txt':'Exact fixture report','notes.txt':'Exact fixture notes'})
def report():
    w=app.window
    assert len([x for x in children(w.dialog.get_child()) if x.has_css_class('review-game')])==2
    assert all(not x.get_editable() for x in children(w.dialog.get_child()) if isinstance(x,Gtk.TextView))
    w.dialog.close();w.show_diagnostics(w.games[0])
def diagnosis():
    w=app.window
    assert len([x for x in children(w.dialog.get_child()) if isinstance(x,Gtk.TextView)])==1
    w.dialog.close();w.set_input_surface(True);w.couch.open('library');w.couch.set_library_view('list')
def couch():
    w=app.window;c=w.couch
    assert c.grid.get_row_spacing()==0
    assert c.controls[0].has_css_class('joined-first') and c.controls[-1].has_css_class('joined-last')
    assert not c.controls[1].has_css_class('joined-first') and not c.controls[1].has_css_class('joined-last')
    c.focus(0);c.navigate('down');assert c.current==1
def couch_capture():
    assert app.window.capture('joined-couch-list.png')
steps=[start,library,sorted_edges,check_sorted,review,capture_review,dlss,five,six,tool,report,diagnosis,couch,couch_capture]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(1000,step)
        else:print('PASS: joined list boundary corners/no row gaps, capsule/accent review reuse, three/five/six-game sizing, DLSS/tool/report reviews, Gaming Mode list and focus; game writes disabled',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(2200,step)
result=app.run([sys.argv[0]]);raise SystemExit(app.exit_code or result)
