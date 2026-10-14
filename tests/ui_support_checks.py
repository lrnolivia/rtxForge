"""Write-disabled native unsupported explanations and real preparation counters."""
import argparse,os,sys,traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gui'),str(ROOT/'scripts')]
import rtxforge_gtk as ui
import engine_bridge
import ui as events
from gi.repository import Gtk,Adw,GLib

def counters():
    class Stop(Exception):pass
    engine=SimpleNamespace(Stop=Stop,Y4MY_PROVIDER={'name':'Fixture','id':'fixture'},visual_defaults=lambda *_:None,load_baseline=lambda *_:{'managed_paths':['fixture.dll']},verify_baseline_integrity=lambda *_,**__:None,verify_native_restore=lambda *_:None)
    rows=[{'name':'Ready game','game':'/fixture/a'},{'name':'Skipped game','game':'/fixture/b'}]
    def game(_,row):
        if row['name']=='Skipped game':raise Stop('No Windows executable found')
        return SimpleNamespace(root=Path(row['game']),target_dir=Path(row['game']))
    reported=[]
    with patch.object(engine_bridge,'module',return_value=engine),patch.object(engine_bridge,'desktop_mode'),patch.object(engine_bridge,'game',side_effect=game),patch.object(engine_bridge,'fingerprint',return_value='fixture'),events.report_to(reported.append):
        result=engine_bridge.prepare({},rows,'mfg-only','uninstall',{})
    assert len(result['rows'])==1 and len(result['blocked'])==1
    assert [e['checked'] for e in reported if e.get('phase')=='review-check']==[0,1,1,2]
    assert all(e['total']==2 for e in reported if e.get('phase')=='review-check')

app=ui.Application(argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic'))
def children(widget):
    yield widget
    child=widget.get_first_child()
    while child:yield from children(child);child=child.get_next_sibling()
def start():
    counters()
    w=app.window;w.scan=lambda *args:None;w.set_default_size(1440,960)
    w.games=w.games[:3];w.filter='all';w.games[0]['blocked']='No native DLSS-G detected';w.games[0]['installed']=False
    w.show_games(w.games,False)
    w.cards[w.games[0]['game']]['overlay'].support_info.emit('clicked')
def caution():
    w=app.window;control=w.cards[w.games[0]['game']]['overlay'].support_info
    assert control.get_child().get_paintable() is not None
    ui.set_button_glyphs(False)
    assert control.get_child().get_visible()
    ui.set_button_glyphs(True)
    assert control.get_child().get_pixel_size()==14
    assert control.get_margin_top()==10 and control.get_margin_start()==10
    assert control.support_popover.get_visible()
    assert any(isinstance(x,Gtk.Label) and x.get_text()==w.support_reason(control._support_game) for x in children(control.support_popover))
    assert not any(isinstance(x,Gtk.Label) and x.get_text().startswith('Unsupported:') for x in children(control.support_popover))
    control.support_popover.popdown();w.details(w.games[0])
def artwork():
    w=app.window
    import tempfile
    from gi.repository import GdkPixbuf
    with tempfile.TemporaryDirectory() as directory:
        for name,width,height in [('poster',600,900),('hero',1920,620),('capsule',920,430)]:
            pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,width,height)
            pix.fill(0x447799ff);pix.savev(str(Path(directory)/(name+'.png')),'png',[],[])
        paths={key:str(Path(directory)/(key+'.png')) for key in ('poster','hero','capsule')}
        assert ui.poster_art_path(paths)==paths['poster']
        assert ui.poster_art_path({**paths,'poster':paths['hero']}) is None
        assert ui.poster_art_path({**paths,'poster':paths['capsule']}) is None
        assert ui.poster_art_path({'poster':paths['hero']}) is None
    page=w.detail_pages.get_child_by_name('Appearance')
    group=page.get_first_child()
    assert group.get_title()=='Custom Artwork'
    assert set(group.artwork_controls)=={'poster','capsule','hero'}
    for controls in group.artwork_controls.values():
        assert all(not controls[key].get_sensitive() for key in ('choose','search','reset'))
    w.dialog.set_default_size(1100,900)
    w.detail_pages.set_visible_child_name('Appearance')
def artwork_capture():
    group=app.window.detail_pages.get_child_by_name('Appearance').get_first_child()
    controls=list(group.artwork_controls.values())
    areas=[c['preview'].get_width()*c['preview'].get_height() for c in controls]
    assert min(areas)>0 and max(areas)/min(areas)<1.15, areas
    assert max(c['row'].get_width() for c in controls)-min(c['row'].get_width() for c in controls)<=1
    assert app.window.capture('custom-artwork-appearance.png')
    app.window.detail_pages.set_visible_child_name('Overview')
def details():
    w=app.window
    badges=[x for x in children(w.dialog.get_child()) if isinstance(x,Gtk.Label) and x.has_css_class('cover-badge')]
    assert any(x.get_text()=='Unsupported' for x in badges)
    assert all(x.get_text()!='Ready for Features' for x in badges)
    overview=w.detail_pages.get_child_by_name('Overview')
    assert overview.get_first_child().has_css_class('unsupported-notice')
    notice=overview.get_first_child()
    assert any(isinstance(x,Gtk.Image) and x.get_paintable() is not None for x in children(notice))
    assert not any(isinstance(x,Adw.ExpanderRow) and x.get_title()=='Technical details' for x in children(overview))
    assert w.capture('unsupported-top-notice.png')
    # One dialog moves through Checking → Review → Progress → Done.
    w.operation_games=w.games;w.operation_cancel=__import__('threading').Event()
    flow=ui.OperationFlow(w,'install',w.games);flow.show_checking()
    w.event({'kind':'progress','label':'Verifying feature package'})
def package():
    w=app.window;flow=w.operation_flow
    assert flow.stage=='checking' and flow.step.counter.get_text()=='Preparing…' and not flow.step.determinate
    assert flow.step.phase.get_text()=='Verifying feature package…',flow.step.phase.get_text()
    assert not flow.primary.get_sensitive() and flow.primary.get_label()=='Install'
    assert w.capture('review-check-package.png')
    w.event({'kind':'progress','phase':'review-check','label':'Game checked','game':w.games[1]['name'],'checked':2,'total':3})
def checking():
    w=app.window;flow=w.operation_flow
    assert flow.step.counter.get_text()=='Checking 2 of 3',flow.step.counter.get_text()
    assert abs(flow.step.bar.get_fraction()-2/3)<0.01
    assert flow.step.title.get_text()==w.games[1]['name']
    assert flow.step.frame.has_css_class('progress-poster-frame')
    assert flow.dialog.has_css_class(w._ensure_game_accent(w.games[1]))
    assert w.capture('review-check-counter.png')
    dialog=flow.dialog
    w.action_ready({'operation':'install','rows':[{'name':g['name'],'detail':'Fixture changes'} for g in w.games[1:]],'blocked':[]})
    assert w.operation_flow is flow and flow.dialog is dialog and flow.stage=='review'
def large_review():
    w=app.window
    w.operation_games=w.games
    w.action_ready({'operation':'install','rows':[{'name':w.games[i%3]['name'],'detail':'Fixture changes'} for i in range(20)],'blocked':[]})
def compact_progress():
    w=app.window;flow=w.operation_flow
    listing=next(x for x in children(flow.dialog.get_child()) if x.has_css_class('review-list'))
    scroll=listing.get_parent()
    if isinstance(scroll,Gtk.Viewport):scroll=scroll.get_parent()
    rows=[x for x in children(listing) if isinstance(x,Adw.ActionRow)]
    fifth=rows[4].compute_bounds(scroll)[1];sixth=rows[5].compute_bounds(scroll)[1]
    assert fifth.get_y()+fifth.get_height()<=scroll.get_height()+1
    assert sixth.get_y()>=scroll.get_height()-1
    w.options.demo=False
    w.start=lambda *args:None  # Exercise the real transition without executing files.
    w.operation_cancel=__import__('threading').Event()
    w.execute({'kind':'engine','rows':[{'name':g['name']} for g in w.games]})
    w.options.demo=True
    assert flow.stage=='progress' and flow.cancel_button.get_sensitive()
    w.event({'kind':'progress','label':'Backing up your current files','game':w.games[1]['name'],'current':2,'total':3,'fraction':0.5})
    assert flow.step.counter.get_text()=='Installing 2 of 3',flow.step.counter.get_text()
    ui.apply_corner_style('square')
def square_progress():
    w=app.window
    assert w.dialog.get_child().get_height()<400, w.dialog.get_child().get_height()
    assert w.capture('compact-square-progress.png')
    w.finish_progress(True,'20 games updated. Fixture only; no game files changed.')
def compact_done():
    w=app.window
    assert w.operation_flow.stage=='done' and w.operation_flow.primary.get_label()=='Done'
    # Status page plus the bottom action bar.
    assert w.dialog.get_child().get_height()<360, w.dialog.get_child().get_height()
    assert w.capture('compact-square-done.png')
    ui.apply_corner_style('rounded')
def round_done():
    assert app.window.capture('compact-rounded-done.png')
steps=[start,caution,artwork,artwork_capture,details,package,checking,large_review,compact_progress,square_progress,compact_done,round_done]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(1100,step)
        else:print('PASS: compact Progress/Done after 20-game review, live Square/Rounded corners, shortened fade and footer spacing; caution click opens explanation; Unsupported badge; notice first without duplicate technical expander; real engine ready/skipped counters; animated preparation progress; no game writes',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(2200,step)
result=app.run([sys.argv[0]]);raise SystemExit(app.exit_code or result)
