"""Game Mode (the Windows design in GTK): pages, details, modals, focus and the install flow; write-disabled."""
import argparse,os,sys,time,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from game_mode import GameModeFlow,descendants
from demo_assets import prepare
prepare(ROOT)
from gi.repository import GLib,Gdk,Gtk
app=ui.Application(argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic'))
images=[]
def key(name):
 return app.window.couch.find_key(app.window.couch,name)
def labels(scope):
 return [w.get_text() for w in descendants(scope) if isinstance(w,Gtk.Label)]
def setup():
 w=app.window;w.set_default_size(1280,820);w.set_input_surface(True)
 c=w.couch
 assert w.input_stack.get_visible_child_name()=='couch'
 assert c.page=='library' and key('tab-library') and key('brand')
 assert any(k.startswith('game-') for k in (getattr(x,'_gm_key','') for x in descendants(c.body)))
def keyboard():
 w=app.window;c=w.couch
 w.keyboard_input(None,Gdk.KEY_comma,0,Gdk.ModifierType.CONTROL_MASK);assert c.page=='settings'
 w.keyboard_input(None,Gdk.KEY_Escape,0,0);assert c.page=='library'
 w.keyboard_input(None,Gdk.KEY_2,0,Gdk.ModifierType.CONTROL_MASK);assert c.page=='presets'
 c.navigate('next');assert c.page=='packages'
 c.navigate('next');assert c.page=='extras'
 c.navigate('next');assert c.page=='settings'
 c.navigate('next');assert c.page=='library'
 for keyval,target in ((Gdk.KEY_3,'packages'),(Gdk.KEY_4,'extras'),(Gdk.KEY_5,'settings')):
  w.keyboard_input(None,keyval,0,Gdk.ModifierType.CONTROL_MASK);assert c.page==target
 c.open('library')
 w.set_input_kind('keyboard');assert 'Esc' in labels(c.footer)
 w.set_input_kind('controller');assert 'Esc' not in labels(c.footer)
 w.set_input_kind('keyboard')

def rapid_navigation():
 c=app.window.couch
 def settle():
  end=time.monotonic()+.035
  while time.monotonic()<end:
   while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
   time.sleep(.001)
 for page in ('extras','presets','settings','packages','library'):
  c.open(page);settle()
  focus=app.window.get_focus()
  assert focus is not None and focus.is_sensitive(),page
  node=focus
  while node is not None and node not in (c.body.current,c.header,c.bottom_nav):node=node.get_parent()
  assert node is not None,('focus belongs to outgoing scene',page)
 # A navigation input arriving before the scheduled page focus restore wins.
 c.open('extras')
 c.navigate('down')
 first=app.window.get_focus();assert first is not None and first.get_focusable()
 assert first.is_ancestor(c.body.current),'new page input went to the header'
 c.navigate('down')
 target=app.window.get_focus()
 assert target is not None and target.is_sensitive()
 assert target is not first,'input before allocation did not advance native focus'
 c.navigate('up');assert app.window.get_focus() is first,'immediate reversal lost focus'
 c.navigate('down');assert app.window.get_focus() is target
 settle()
 assert app.window.get_focus() is target,'delayed restoration replaced newer input'
 c.open('library');settle()
 for layout in ('capsules','list','posters'):
  c.set_library_view(layout);settle()
  assert c.focus_key()=='seg-'+layout,(layout,c.focus_key())
  assert app.window.get_focus().is_sensitive()

def virtual_library():
 c=app.window.couch;w=app.window;original=w.games
 def settle(ms=40):
  end=time.monotonic()+ms/1000
  while time.monotonic()<end:
   while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
   time.sleep(.001)
 try:
  w.games=[dict(g,game=g['game']+'-motion-'+str(i)) for i in range(10) for g in original]
  c.open('library');settle()
  assert c.library_virtual is not None
  cards=lambda:[x for x in descendants(c.body.current) if isinstance(x,Gtk.Button) and x.has_css_class('gm-gamecard')]
  assert len(cards())<70,len(cards())
  first=c.library_virtual.ensure('game-'+c.filtered_games()[0]['game']);first.grab_focus()
  for _ in range(18):c.navigate('down');settle(8)
  focused=c.focus_key();offset=c.library_scroll.get_vadjustment().get_value()
  game=next(g for g in c.filtered_games() if 'game-'+g['game']==focused)
  assert offset>0
  c.open_details(game);settle();c.navigate('back');settle(80)
  assert c.focus_key()==focused,(c.focus_key(),focused)
  assert abs(c.library_scroll.get_vadjustment().get_value()-offset)<3
  c.set_library_view('list');settle()
  assert c.library_virtual is not None
  assert len([x for x in descendants(c.body.current) if isinstance(x,Gtk.Button) and x.has_css_class('gm-listrow')])<40
 finally:
  w.games=original;c.set_library_view('posters');settle()
def section_motion():
 c=app.window.couch
 c.open('settings');c.open_settings_section('Appearance')
 assert not any('sized for the couch' in text.lower() for text in labels(c.body.current))
 assert any(isinstance(x,Gtk.Switch) for x in descendants(c.body.current))
 c.open_settings_section('Gaming Mode')
 assert c.body.outgoing is not None
 c.open('library')


def deferred_desktop_layout():
 w=app.window;c=w.couch
 c.set_library_view('posters')
 w.set_input_surface(False)
 assert w.library_stack.get_visible_child_name()=='gallery'
 w.set_input_surface(True)
 c.set_library_view('list')
 assert w.settings['library_view']=='list'
 assert w.library_stack.get_visible_child_name()=='gallery','hidden Desktop was rebuilt'
 w.set_input_surface(False)
 assert w.library_stack.get_visible_child_name()=='list','Desktop did not restore the chosen view'
 w.set_input_surface(True);c.set_library_view('posters')

def action_wording():
 w=app.window;c=w.couch
 c.open('library');w.select_all(False);w.controls()
 def compare():
  for desktop,game_mode in ((w.install_all,'lib-install'),(w.uninstall_all,'lib-restore')):
   assert desktop.text_label.get_text() in labels(key(game_mode)),(desktop.text_label.get_text(),labels(key(game_mode)))
 compare()
 game=next(g for g in c.filtered_games() if not g.get('blocked'))
 w.cards[game['game']]['check'].set_active(True)
 c.selecting=True;c.selected={game['game']};c.render()
 compare()
 c.selecting=False;c.selected.clear();w.select_all(False);c.render()


def menu():
 c=app.window.couch
 c.navigate('menu');assert c.modals and 'Exit App' in labels(c.modal_layer)
 c.navigate('back');assert not c.modals and c.page_box.get_sensitive()
def panel_shortcut():
 w=app.window;c=w.couch
 def record(scope):
  row=next(x for x in descendants(scope) if isinstance(x,Gtk.Button) and 'Panel shortcut' in labels(x))
  row.emit('clicked');assert c.modals and c.shortcut_recorder
 c.open('settings');c.open_settings_section('Overlay');record(c.body)
 w.keyboard_input(None,Gdk.KEY_Insert,0,0);assert c.modals and any('OptiScaler' in t for t in labels(c.modal_layer))
 w.keyboard_input(None,Gdk.KEY_F9,0,Gdk.ModifierType.CONTROL_MASK)
 assert not c.modals and c.shortcut_recorder is None and w.settings['panel_hotkey']=='Ctrl+F9',w.settings.get('panel_hotkey')
 game=c.filtered_games()[0];w.settings.setdefault('game_overlay_settings',{})[game['game']]={}
 c.open_game_overlay(game);record(c.modal_layer)
 w.keyboard_input(None,Gdk.KEY_F7,0,0)
 assert w.settings['game_overlay_settings'][game['game']]['panel_hotkey']=='F7' and len(c.modals)==1
 record(c.modal_layer);w.keyboard_input(None,Gdk.KEY_Escape,0,0)
 assert w.settings['game_overlay_settings'][game['game']]['panel_hotkey']=='F7' and len(c.modals)==1
 c.close_modal();w.settings['game_overlay_settings'].pop(game['game']);w.settings['panel_hotkey']='Delete';c.open('library')
def presets_page():
 c=app.window.couch;c.open('presets');assert c.page=='presets'
 text=labels(c.body)
 for heading in ('Multi-Frame Generation','Neural rendering','DLSS presets','Image tuning'):assert heading in text,heading
 for name in ('preset-mfg-enabled-1','preset-mfg-mode-1','preset-mfg-ratio-2'):
  button=key(name);assert button is not None,name
  if button.get_sensitive():button.emit('clicked')
 value=c.preset_value()
 assert {'nr_strength','sharpening_strength','mfg_multiplier','dynamic_mfg','mfg_saved_mode','mfg_saved_multiplier'}<=set(value),value
 assert value['mfg_multiplier'] in ('auto',0,4) and value['mfg_saved_multiplier']==4,value
 c.open('library')
def details():
 w=app.window;c=w.couch
 # Demo artwork can be missing (offline CI): any installed game will do.
 # Available excludes installed games (Windows LibraryScope); pick from the library.
 games=sorted(w.games,key=lambda g:g['name'].casefold())
 game=next((g for g in games if g.get('poster') and g.get('installed')),None) or next((g for g in games if g.get('installed')),None) or games[0]
 c.open_details(game);assert c.page=='details' and c.details_game is game
 assert game['name'] in labels(c.body)
def section(name):
 c=app.window.couch;c.open_section(name);assert c.section==name
 assert name in labels(c.body)
def stepper():
 c=app.window.couch;c.open_section('Features');c.toggle_presets()
 # Windows layout: Sharpening is a disclosure on the Image tuning side.
 here=lambda name:c.find_key(c.body.current,name)
 opener=here('preset-disclosure-Sharpening');assert opener is not None
 # Disclosures stay open across renders, and this step runs once per window size.
 if 'Sharpening' not in getattr(c,'preset_disclosures',set()):opener.emit('clicked')
 end=time.monotonic()+.3
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
 row=here('preset-field-sharpness');assert row is not None,'sharpness field';assert row.get_sensitive(),'sharpness disabled';assert row.get_mapped(),'sharpness not shown'
 value=lambda:next(w.get_text() for w in descendants(row) if isinstance(w,Gtk.Label) and w.has_css_class('gm-stepper-value'))
 before=value()
 row.grab_focus();c.navigate('right')
 after=value()
 assert before!=after,(before,after)
def back_to_library():
 c=app.window.couch;c.navigate('back');assert c.page=='library'
def select():
 c=app.window.couch
 c.start_selecting();assert c.selecting
 game=next(g for g in c.filtered_games() if not g.get('blocked'))
 c.activate_game(game);assert game['game'] in c.selected
 assert key('lib-install').get_sensitive()
def install():
 w=app.window;c=w.couch
 w.calls=[];w.execute=lambda review,*_:(w.calls.append(review),w.operation_flow.show_progress(len(review.get('rows',[])) or 1))
 c.run_operation('install',c.selected_games(),{})
 assert isinstance(w.operation_flow,GameModeFlow),type(getattr(w,'operation_flow',None))
 assert c.modals
def wait_review():
 flow=app.window.operation_flow
 assert flow.stage=='review',flow.stage
 assert flow.primary.get_parent() is not None
def confirm():
 # Preview mode disables writes; stand in for execute and show its progress stage.
 w=app.window;flow=w.operation_flow
 assert not flow.primary.get_sensitive(),'preview mode never enables the write'
 flow.on_confirm(flow.review);assert w.calls and flow.stage=='progress'
 flow.progress_event({'game':flow.games[0]['name'],'label':'Copying files','current':1,'total':1,'fraction':0.5})
def finish():
 w=app.window;w.finish_progress(True,'Features installed. Launch the game to check the effect.')
 assert w.operation_flow is None or w.operation_flow.stage=='done'
def wait_done():
 w=app.window;flow=w.operation_flow
 assert flow is None or flow.stage=='done',flow and flow.stage
 if flow:flow.close()
 c=w.couch;assert not c.modals and c.page_box.get_sensitive()
 c.stop_selecting()
def filter_modal():
 c=app.window.couch;c.open_filter();assert c.modals and 'Filter library' in labels(c.modal_layer)
def close_modal():
 c=app.window.couch;c.navigate('back');assert not c.modals
def view(name):
 c=app.window.couch;c.set_library_view(name);assert app.window.settings['library_view']==name
def settings(name):
 c=app.window.couch;c.open('settings');c.open_settings_section(name);assert name in labels(c.body)
def fits():
 w=app.window;c=w.couch
 assert c.body.get_width()<=w.get_width()+1,(c.body.get_width(),w.get_width())
def capture(name):
 fits()
 # Slow software renderers (CI) can still be finishing a resize or page slide; let
 # pending frames run before failing, for at most about two seconds.
 import time
 path=app.window.capture(name);deadline=time.monotonic()+2
 while not path and time.monotonic()<deadline:
  GLib.MainContext.default().iteration(False);time.sleep(.02);path=app.window.capture(name)
 assert path and path.is_file(),(name,app.window.get_mapped(),app.window.get_width(),app.window.get_height());images.append(str(path))
def prompts(scope):
 return [w._gm_prompt for w in descendants(scope) if hasattr(w,'_gm_prompt')]
def glyphs():
 w=app.window;c=w.couch;w.set_input_kind('controller')
 expected={'xbox':('A','text'),'playstation':('Cross','cross'),'nintendo':('B','text'),'steam':('A','text'),'generic':('South','position0')}
 for family,first in expected.items():
  w.settings['controller_glyphs']=family;c.update_prompts(force=True)
  assert prompts(c.footer)[0]==first,(family,prompts(c.footer))
  assert 'Enter' not in labels(c.footer)
 w.settings['controller_glyphs']='xbox';w.set_input_kind('keyboard')
def controller_guide(family):
 w=app.window;c=w.couch;w.settings['controller_glyphs']=family;w.set_input_kind('controller')
 c.open('settings');c.open_settings_section('Gaming Mode')
 row=next(b for b in descendants(c.body) if isinstance(b,Gtk.Button) and 'Controller buttons' in labels(b))
 row.emit('clicked');assert c.modals
 shown=[label for label,_ in prompts(c.modals[-1]['dialog'])]
 bumpers={'playstation':['L1','R1'],'nintendo':['L','R']}.get(family,['LB','RB'])
 assert shown[:2]==['D-pad',{'playstation':'Cross','nintendo':'B'}.get(family,'A')] and all(b in shown for b in bumpers),shown
 assert 'Right stick' in labels(c.modals[-1]['dialog'])
def card_surfaces():
 w=app.window;c=w.couch
 row=c.find_key(c.body,'card-opacity');assert row is not None and 'Card surfaces' in labels(c.body)
 assert row._gm_scale.get_value()==10==w.settings['game_mode_card_opacity']
 row.grab_focus();c.navigate('right');assert w.settings['game_mode_card_opacity']==15
 c.navigate('left');assert w.settings['game_mode_card_opacity']==10
def frost(percent):
 w=app.window;c=w.couch;c.set_card_opacity(percent);c.open('library')
def frosted_drawn():
 c=app.window.couch;area=__import__('gi.repository.Graphene',fromlist=['Graphene']).Rect().init(0,0,c.backdrop.get_width(),c.backdrop.get_height())
 assert c.backdrop.frosted_regions(area),'frosted surfaces over the artwork'
def preparing():
 w=app.window;c=w.couch
 flow=GameModeFlow(c,w,'install',w.games[:3],('Review install','Install','Installing'));flow.show_checking()
 flow.checking_event({'phase':'review-check','label':'Game checked','game':w.games[1]['name'],'checked':2,'total':3})
 flow.checking_event({'kind':'progress','label':'Verifying feature package'})
 assert flow.step['counter'].get_text()=='Preparing 2 of 3',flow.step['counter'].get_text()
 assert flow.step['phase'].get_text()=='Downloading packages/files…' and flow.step['title'].get_text()==w.games[1]['name']
 assert 'Preparing' in labels(c.modals[-1]['dialog']) and not any(isinstance(b,Gtk.Button) and 'Install' in labels(b) for b in descendants(c.modals[-1]['dialog']))
 w._preparing=flow
def preparing_close():
 w=app.window;w._preparing.show_review({'rows':[{'name':w.games[1]['name'],'detail':'Fixture changes'}]},lambda:None)
 assert w._preparing.step['bar'].get_fraction()==1.0 and w._preparing.stage=='review'
 w.couch.close_modal();assert not w.couch.modals
def overlay_section():
 c=app.window.couch;c.open('settings');c.open_settings_section('Overlay')
def overlay_appearance():
 c=app.window.couch;text=labels(c.body)
 assert 'Appearance' in text and 'Dark' in text,'overlay Appearance choice'
 # Panel rows sit under rtxForge Panel, not OptiScaler (Windows grouping).
 order=[x for x in text if x in ('rtxForge Panel','Live feature statistics','Panel shortcut','OptiScaler','OptiScaler menu')]
 assert order.index('Panel shortcut')<order.index('OptiScaler')<order.index('OptiScaler menu'),order
def slide_start():
 c=app.window.couch;c.open('library');app.window._slide_from=c.body.current;c.open('presets')
 assert c.body.current is not app.window._slide_from and getattr(c.body.current,'_gm_offset',0)>0,'presets enters from the right'
def slide_settled():
 c=app.window.couch;assert getattr(c.body.current,'_gm_offset',0)==0 and c.body.current.get_opacity()==1
def guide_close():
 w=app.window;w.couch.close_modal();w.settings['controller_glyphs']='xbox';w.set_input_kind('keyboard')
def right_stick():
 c=app.window.couch
 assert c.scroll_main_view(400),'the settings page scrolls'
 scroll=max((x for x in descendants(c.body.current) if isinstance(x,Gtk.ScrolledWindow) and x.get_mapped()),key=lambda x:x.get_width()*x.get_height())
 moved=scroll.get_vadjustment().get_value();assert moved>0,moved
 c.scroll_main_view(-10000);assert scroll.get_vadjustment().get_value()==scroll.get_vadjustment().get_lower()
def theme(name):
 w=app.window;c=w.couch;w.settings['theme']=name;c.apply_theme();c.render()
 assert c.theme.name==name
def review_op(operation):
 w=app.window;c=w.couch;c.open('library')
 games=[g for g in w.games if g.get('installed')] if operation=='uninstall' else [g for g in w.games if not g.get('blocked')][:2]
 c.run_operation(operation,games)
 assert isinstance(w.operation_flow,GameModeFlow) and c.modals
def review_ready():
 flow=app.window.operation_flow;assert flow.stage=='review',flow.stage
 assert not flow.primary.get_sensitive(),'preview mode never enables the write'
def review_close():
 w=app.window;w.operation_flow.cancel_button.emit('clicked')
 assert not w.couch.modals and w.operation_flow is None
def size(width,height):
 app.window.set_default_size(width,height);app.window.couch.resize(width,height)
steps=[setup,keyboard,panel_shortcut,presets_page,menu,glyphs,
       lambda:controller_guide('xbox'),lambda:capture('gm-controller-guide-xbox.png'),guide_close,
       lambda:controller_guide('playstation'),lambda:capture('gm-controller-guide-playstation.png'),guide_close,
       lambda:controller_guide('steam'),lambda:capture('gm-controller-guide-steam.png'),guide_close,
       lambda:(app.window.couch.open('settings'),app.window.couch.open_settings_section('Gaming Mode')),right_stick,
       lambda:(app.window.couch.open('settings'),app.window.couch.open_settings_section('Appearance')),card_surfaces,lambda:capture('gm-settings-card-surfaces.png'),
       lambda:frost(0),frosted_drawn,lambda:capture('gm-frost-0.png'),lambda:frost(100),lambda:capture('gm-frost-100.png'),
       lambda:frost(10),lambda:capture('gm-frost-10.png'),preparing,lambda:capture('gm-preparing.png'),preparing_close,overlay_section,overlay_appearance,lambda:capture('gm-settings-overlay-appearance.png'),slide_start,slide_settled,lambda:app.window.couch.open('library'),
       lambda:(app.window.set_input_kind('controller'),app.window.couch.update_prompts(force=True)),lambda:capture('gm-footer-controller.png'),
       lambda:app.window.set_input_kind('keyboard'),lambda:theme('light'),lambda:capture('gm-library-light.png'),lambda:theme('night'),
       lambda:app.window.couch.open('packages'),lambda:capture('gm-packages.png'),
       lambda:app.window.couch.open('extras'),lambda:capture('gm-extras.png'),
       lambda:app.window.couch.open('library'),menu,lambda:app.window.couch.open_main_menu(),lambda:capture('gm-main-menu.png'),close_modal,
       lambda:review_op('uninstall'),review_ready,lambda:capture('gm-review-restore.png'),review_close,
       lambda:review_op('update-dlss'),review_ready,lambda:capture('gm-review-update-dlss.png'),review_close]
for width,height in ((1280,820),(1920,1080),(1000,700)):
 steps.append(lambda width=width,height=height:size(width,height))
 tag=f'{width}x{height}'
 steps+=[lambda:view('posters'),lambda tag=tag:capture(f'gm-library-posters-{tag}.png'),
         lambda:view('capsules'),lambda tag=tag:capture(f'gm-library-capsules-{tag}.png'),
         lambda:view('list'),lambda tag=tag:capture(f'gm-library-list-{tag}.png'),lambda:view('posters'),
         filter_modal,lambda tag=tag:capture(f'gm-filter-{tag}.png'),close_modal,
         details,lambda tag=tag:capture(f'gm-details-overview-{tag}.png')]
 for name in ('Features','DLSS Files','Tools','Appearance','Notes'):
  steps+=[lambda name=name:section(name),lambda name=name,tag=tag:capture(f'gm-details-{name.lower().replace(" ","-")}-{tag}.png')]
 steps+=[stepper,lambda tag=tag:capture(f'gm-details-presets-{tag}.png'),back_to_library,
         lambda:app.window.couch.open('presets'),lambda tag=tag:capture(f'gm-presets-{tag}.png')]
 for name in ('Graphics','Overlay','Appearance','Library','Gaming Mode','System','Recovery','About'):
  steps+=[lambda name=name:settings(name),lambda name=name,tag=tag:capture(f'gm-settings-{name.lower().replace(" ","-")}-{tag}.png')]
 steps+=[lambda:app.window.couch.open('library'),select,install]
 steps+=[wait_review,lambda tag=tag:capture(f'gm-review-{tag}.png'),confirm,lambda tag=tag:capture(f'gm-progress-{tag}.png'),finish,lambda tag=tag:capture(f'gm-done-{tag}.png'),wait_done]

if os.environ.get('RTXFORGE_GAME_MODE_MOTION_ONLY'):
 steps=[setup,rapid_navigation,virtual_library,section_motion,deferred_desktop_layout,action_wording,panel_shortcut,presets_page,menu,details,back_to_library]
def step():
 try:
  if steps:steps.pop(0)();GLib.timeout_add(500,step)
  else:print('PASS: Game Mode pages, details sections, modals, keyboard, selection and the review to done flow\n'+'\n'.join(images),flush=True);app.quit()
 except Exception:traceback.print_exc();app.exit_code=1;app.quit()
 return False
GLib.timeout_add(1800,step);app.run([]);raise SystemExit(app.exit_code)
