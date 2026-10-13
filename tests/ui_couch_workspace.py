"""Native workspace hierarchy, keyboard routing and responsive layout; write-disabled."""
import argparse,os,sys,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import GLib,Gdk,Gtk
app=ui.Application(argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic'))
images=[]
def descendants(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from descendants(child);child=child.get_next_sibling()
def setup():
 w=app.window;w.set_default_size(1280,820);w.set_input_surface(True)
 w.games.sort(key=lambda g:not bool(g.get('poster')))
 w.couch.open_game(w.games[0]);w.couch.open('library')
 assert w.couch.settings_button.get_visible()
 w.couch.settings_button.grab_focus()
 w.keyboard_input(None,Gdk.KEY_Return,0,0)
 assert w.couch.page=='settings' and w.couch.sidebar_buttons
 assert w.couch.settings_section=='Gaming Mode'
 w.keyboard_input(None,Gdk.KEY_Escape,0,0)
 assert w.couch.page=='library'
 w.keyboard_input(None,Gdk.KEY_comma,0,Gdk.ModifierType.CONTROL_MASK)
 assert w.couch.page=='settings'
 w.keyboard_input(None,Gdk.KEY_2,0,Gdk.ModifierType.CONTROL_MASK)
 assert w.couch.page=='presets'
 assert sum(isinstance(child,Gtk.Scale) for child in descendants(w.couch.workspace))==2
 assert any(isinstance(child,Gtk.DropDown) for child in descendants(w.couch.workspace))
 saved=dict(w.couch.pending)
 grid=w.couch.preset_grid
 controls=list(w.couch.preset_controls)
 w.couch.resize(800,820)
 assert grid.query_child(controls[2])[1]==2
 assert w.couch.pending==saved
 assert not w.couch.footer_note.get_visible()
 w.couch.resize(1280,820)
 assert grid.query_child(controls[2])[0]==2
 assert w.couch.pending==saved
 assert all(w.couch.controls[i].get_parent() is w.couch.workspace_footer for i in (3,4))
 w.set_input_kind('keyboard');assert w.couch.prompt_spec[0]=='keyboard'
 assert any(isinstance(child,Gtk.Label) and child.get_text()=='Esc' for child in descendants(w.couch.prompts))
 w.set_input_kind('controller');assert w.couch.prompt_spec[0]!='keyboard'
 w.set_input_kind('keyboard')
def page(name,section=None):
 w=app.window;c=w.couch
 if name in ('tools','game_presets'):c.open_game(w.games[0])
 c.open(name)
 if section:c.set_section(section)
 assert c.body.get_visible_child_name()=='workspace'
 assert c.settings_button.get_visible()
 if name=='presets':assert c.accent_color=='#76b900'
 if name=='game_presets':assert c.accent_color==('#'+w._ensure_game_accent(c.game).removeprefix('art-'))
def capture(name):
 w=app.window;c=w.couch
 assert c.workspace.get_width()<=w.get_width()
 assert c.workspace_footer.get_width()<=c.workspace.get_width(), 'Action footer must fit'
 assert not c.workspace_scroll.get_hadjustment().get_upper()>c.workspace_scroll.get_hadjustment().get_page_size()+1
 path=w.capture(name);assert path and path.is_file();images.append(str(path))
def small():
 app.window.set_default_size(800,820);app.window.couch.resize(800,820)
steps=[setup]
for size in (1280,800):
 if size==800:steps.append(small)
 for name,section in [('settings','Gaming Mode'),('settings','Library'),('presets',None),('game_presets',None),('dlss',None),('tools','Graphics'),('tools','Recovery'),('library_filters',None)]:
  steps.extend([lambda name=name,section=section:page(name,section),lambda name=name,section=section,size=size:capture(f'workspace-{name}-{section or "main"}-{size}.png')])
def step():
 try:
  if steps:steps.pop(0)();GLib.timeout_add(450,step)
  else:print('PASS: full-screen workspaces, Settings access, separated actions, keyboard shortcuts/keycaps, 1280/800 layouts\n'+'\n'.join(images),flush=True);app.quit()
 except Exception:traceback.print_exc();app.exit_code=1;app.quit()
 return False
GLib.timeout_add(1800,step);app.run([]);raise SystemExit(app.exit_code)
