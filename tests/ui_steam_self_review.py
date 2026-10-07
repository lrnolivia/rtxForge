"""Native own-app Steam review; intercepted apply, no Steam or game writes."""
import argparse,os,sys,traceback
from pathlib import Path
from unittest.mock import patch
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import Gtk,GLib
app=ui.Application(argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic'))
review={'created':False,'profile':'Fixture','identity':{'fixture':True},'roles':[{'role':role,'status':status} for role,status in [('poster','replace'),('capsule','add'),('hero','unchanged'),('logo','add')]]}
def children(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from children(child);child=child.get_next_sibling()
def open_review():app.window.review_rtxforge_steam(review,dict(app.window.settings))
def check():
    w=app.window;rows=[x for x in children(w.dialog.get_child()) if x.has_css_class('review-game')]
    assert [x.get_title() for x in rows]==['Poster','Wide capsule','Hero background','Transparent logo']
    assert 'custom artwork' in rows[0].get_subtitle()
    assert len([x for x in children(w.dialog.get_child()) if x.has_css_class('review-bezel')])==4
    assert w.capture('steam-self-review-desktop.png')
    calls=[]
    import steam_self_install
    with patch.object(steam_self_install,'install',side_effect=lambda *args,**kwargs:calls.append(kwargs)):
        w.start=lambda title,action,done:action()
        next(x for x in children(w.dialog.get_child()) if isinstance(x,Gtk.Button) and x.get_label()=='Apply artwork').emit('clicked')
    assert len(calls)==1 and calls[0]['reviewed']==review
    w.set_input_surface(True);open_review()
def couch():
    assert app.window.capture('steam-self-review-couch.png')
    assert len([x for x in children(app.window.dialog.get_child()) if x.has_css_class('review-game')])==4
steps=[open_review,check,couch]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(900,step)
        else:print('PASS: own-app Steam slot review, artwork bezels, explicit reviewed apply, desktop and Couch; no Steam/game writes',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(1800,step);app.run([]);raise SystemExit(app.exit_code)
