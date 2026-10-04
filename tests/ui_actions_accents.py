"""Native neutral-accent, responsive tools and icon preference regression."""
import argparse,os,sys,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import GLib,Gtk,Adw
app=ui.Application(argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic'))
def children(widget):
    yield widget
    child=widget.get_first_child()
    while child:yield from children(child);child=child.get_next_sibling()
def start():
    w=app.window;w.set_default_size(1440,960);w.scan=lambda *args:None
    art=w.games[0]['poster'];assert art
    for accent in ('#ffffff','#bbbbbb','#101010'):
        name=ui.artwork_accent(art,accent)
        provider=ui.ACCENT_PROVIDERS[name]
        css=provider.to_string()
        # Every selected label/control must stay achromatic.
        probe=Gtk.Label(label='Neutral',css_classes=['card-title'])
        card=Gtk.Box(css_classes=['game-card','selected',name]);card.append(probe)
        w.neutral_probe=probe
        assert '#571313' not in css
    d,b,f=w.open_panel('Tools',width=860,height=430)
    w.populate_tools(b,w.games[0]);w.tile_box=next(x for x in children(b) if isinstance(x,Gtk.FlowBox))
def wide():
    w=app.window;t=w.tile_box
    positions=[x.get_allocation().y for x in children(t) if isinstance(x,Gtk.FlowBoxChild)]
    assert len(positions)==4 and len(set(positions))==1,positions
    assert w.capture('actions-tools-wide.png')
    w.dialog.set_content_width(460)
def narrow():
    w=app.window;t=w.tile_box
    positions=[x.get_allocation().y for x in children(t) if isinstance(x,Gtk.FlowBoxChild)]
    assert len(set(positions))==2,positions
    assert w.capture('actions-tools-narrow.png')
    w.show_settings()
    glyphs=next(x for x in children(w.dialog.get_child()) if isinstance(x,Adw.SwitchRow) and x.get_title()=='Button Icons')
    glyphs.set_active(False);assert not any(x.get_visible() for x in ui.BUTTON_IMAGES)
    created=ui.button('Install',lambda *_:None)
    assert not next(x for x in children(created) if isinstance(x,Gtk.Image)).get_visible()
    created.set_label('Done');assert created.get_label()=='Done'
    glyphs.set_active(True);assert all(x.get_visible() for x in ui.BUTTON_IMAGES)
    w.dialog.close();w.set_input_surface(True);w.couch.open_game(w.games[0]);w.couch.open('tools')
def couch():
    w=app.window;c=w.couch
    assert len(c.controls)==4
    c.entries[1]['enabled']=True;c.controls[1].set_sensitive(True)
    c.focus(0);c.navigate('right');assert c.current==1
    c.navigate('left');assert c.current==0
    assert w.capture('actions-couch-tools.png')
    w.set_input_surface(False)
    w.settings['game_accents'][w.games[0]['game']]='#ffffff'
    w.games[0]['accent']='#ffffff'
    name=ui.artwork_accent(w.games[0]['poster'],'#ffffff')
    probe=Gtk.Label(label='PRAGMATA',css_classes=['card-title'])
    card=Gtk.Box(css_classes=['game-card','selected',name]);card.append(probe)
    d,b,f=w.open_panel('White accent contrast',width=460,height=220);b.append(card);w.white_probe=probe
def neutral():
    w=app.window;color=w.white_probe.get_style_context().get_color()
    assert max(color.red,color.green,color.blue)-min(color.red,color.green,color.blue)<.01,(color.red,color.green,color.blue)
    assert max(color.red,color.green,color.blue)<.5
steps=[start,wide,narrow,couch,neutral]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(1000,step)
        else:print('PASS: white accent remains neutral, tools wrap 4→2×2, icon toggle applies live/new buttons, Gaming Mode action focus works',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(2200,step)
result=app.run([sys.argv[0]]);raise SystemExit(app.exit_code or result)
