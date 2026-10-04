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
    w.detail_pages.set_visible_child_name('Appearance')
def artwork_capture():
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
    d,b,f=w.open_panel('Review Installation',width=640,height=390)
    w.operation_games=w.games;w.review_check_view(d,b,w.games)
    f.append(ui.button('Cancel',lambda *_:None))
    w.event({'kind':'progress','label':'Verifying feature package'})
def package():
    w=app.window;state=w.review_check_state
    assert state['counter'].get_text()=='0 of 3 checked' and not state['determinate']
    assert w.capture('review-check-package.png')
    w.event({'kind':'progress','phase':'review-check','label':'Game checked','game':w.games[1]['name'],'checked':2,'total':3})
def checking():
    w=app.window;state=w.review_check_state
    assert state['counter'].get_text()=='2 of 3 checked'
    assert abs(state['bar'].get_fraction()-2/3)<0.01
    assert state['game'].get_text()==w.games[1]['name']
    assert state['art'].has_css_class('review-bezel')
    assert state['card'].has_css_class(w._ensure_game_accent(w.games[1]))
    scroll=w.dialog.get_child().get_first_child().get_next_sibling()
    adj=scroll.get_vadjustment()
    assert adj.get_upper()<=adj.get_page_size()+1, (adj.get_upper(),adj.get_page_size())
    assert scroll.get_policy()[1]==Gtk.PolicyType.NEVER
    assert w.capture('review-check-counter.png')
    w.action_ready({'operation':'install','rows':[{'name':g['name'],'detail':'Fixture changes'} for g in w.games[1:]],'blocked':[]},w.dialog,w.dialog.get_child().get_first_child().get_next_sibling().get_child().get_child(),w.dialog.get_child().get_last_child())
    assert w.review_check_state is None
def large_review():
    w=app.window
    d,b,f=w.open_panel('Review Installation',width=640,height=720)
    w.operation_games=w.games
    w.action_ready({'operation':'install','rows':[{'name':w.games[i%3]['name'],'detail':'Fixture changes'} for i in range(20)],'blocked':[]},d,b,f)
    w.fixture_review=d
    w.fixture_footer=f
def compact_progress():
    w=app.window
    assert w.fixture_footer.get_margin_top()==28
    overlay=w.fixture_review.get_child().get_first_child().get_next_sibling()
    assert isinstance(overlay,Gtk.Overlay) and overlay.bottom_fade.get_height()==28
    adj=overlay.get_child().get_vadjustment()
    end=adj.get_upper()-adj.get_page_size()
    adj.set_value(end-5)
    assert overlay.bottom_fade.get_opacity()==1
    adj.set_value(end)
    assert overlay.bottom_fade.get_opacity()==0
    adj.set_value(0)
    w.options.demo=False
    w.start=lambda *args:None  # Exercise the real transition without executing files.
    w.operation_cancel=__import__('threading').Event()
    w.execute({'kind':'engine'},w.fixture_review,None,w.fixture_footer)
    w.options.demo=True
    d=w.dialog;f=w.fixture_footer
    w.job_caption.set_text('Backing up your current files')
    w.update_progress_art(w.games[1]['name'])
    w.compact_footer=f
    ui.apply_corner_style('square')
def square_progress():
    w=app.window
    assert w.dialog.get_child().get_height()<400, w.dialog.get_child().get_height()
    assert w.capture('compact-square-progress.png')
    w.finish_progress(True,'20 games updated. Fixture only; no game files changed.',w.compact_footer)
def compact_done():
    w=app.window
    assert w.dialog.get_child().get_height()<300, w.dialog.get_child().get_height()
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
