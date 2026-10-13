"""Native Library-first checks using demo games and intercepted operations."""
import argparse,os,sys,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import GLib
app=ui.Application(argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic'))
def start():
    w=app.window;w.set_default_size(1440,960);w.set_input_surface(True)
    assert w.couch.tab_bar.get_valign()==ui.Gtk.Align.CENTER
    assert w.couch.page=='library', f'Initial Game Mode page: {w.couch.page}'
    w.games=w.games[:3]
    for game in w.games:game['blocked']='Unsupported fixture';game['installed']=False
    w.filter='available';w.couch.render()
    assert w.couch.library_count.get_text()=='0 shown of 3 games · 0 configured'
    assert not w.couch.library_action.get_sensitive()
    assert not w.couch.library_restore.get_sensitive()
    assert not w.couch.library_update.get_sensitive()
    w.games[0]['blocked']='';w.games[0]['installed']=True
    w.couch.render()
    assert w.couch.library_count.get_text()=='1 shown of 3 games · 1 configured'
    assert all(button.get_sensitive() for button in (w.couch.library_action,w.couch.library_restore,w.couch.library_update))
    assert all(control.get_parent() is w.couch.library_controls for control in (w.couch.library_action,w.couch.filter_button,w.couch.library_restore,w.couch.library_update))
    calls=[];w.launch_action=lambda *args,**kwargs:calls.append(('restore',args,kwargs));w.update_dlss_games=lambda rows:calls.append(('update',rows))
    w.couch.zone='views';w.couch.view_index=2
    w.couch.navigate('accept');w.couch.navigate('right');w.couch.navigate('accept')
    assert [call[0] for call in calls]==['restore','update']
    assert calls[0][2]['targets']==[w.games[0]] and calls[1][1]==[w.games[0]]
    assert w.couch.install_targets()==[w.games[0]]
    w.couch.open('features_all')
    assert w.couch.panel_detail.get_text()=='Available games: 1'
    w.couch.open('library')
    w.couch.dlss_selection=set();w.couch.render()
    w.couch.zone='views';w.couch.view_index=1;w.couch.navigate('right')
    assert w.couch.view_index==0, 'Hidden Restore/Update must be skipped'
    w.couch.dlss_selection=None;w.couch.render()
def layout_and_settings():
    w=app.window;couch=w.couch
    for view in ('posters','capsules'):
        w.view_buttons[view].set_active(True)
        # A live Settings preview changes the layout without toggling the hidden
        # desktop controls. Re-selecting that active control must still apply.
        w.settings['library_view']='list'
        w.show_games(w.games,False)
        couch.set_library_view(view)
        couch.open('library')
        assert w.settings['library_view']==view and couch.library_view==view
        assert w.library_stack.get_visible_child_name()=='gallery'
    couch.open('menu')
    titles={entry['title'] for entry in couch.entries}
    assert 'Settings' in titles and 'Dashboard' not in titles
    couch.open('dashboard')
    assert couch.page=='library'
    couch.open('menu')
    moved={'Add rtxForge to Steam','Sync artwork to Steam','Steam artwork profile','Connect SteamGridDB','UI scale','Navigation','Controller hints'}
    assert not titles & moved
    couch.open('settings')
    settings_entries=set()
    for section in ('Gaming Mode','Library','Controller','System'):
        couch.set_section(section)
        settings_entries.update(entry['title'] for entry in couch.entries)
    assert moved <= settings_entries
    assert couch.settings_button.get_visible()
    couch.set_section('Gaming Mode')
    couch.open('library')
    w.show_settings()
    def descendants(widget):
        yield widget
        child=widget.get_first_child()
        while child:
            yield from descendants(child)
            child=child.get_next_sibling()
    groups=list(descendants(w.dialog))
    assert {'Steam Library','Steam Artwork','Application'} <= {item.get_title() for item in groups if isinstance(item,ui.Adw.PreferencesGroup)}
    captions={item.get_label() for item in groups if isinstance(item,ui.ActionButton)}
    assert {'Add to Steam','Sync','Connect','Choose'} <= captions
    interface=next(item for item in groups if isinstance(item,ui.Adw.ComboRow) and item.get_title()=='Interface')
    assert interface.get_model().get_n_items()==2
    assert not any(isinstance(item,ui.Adw.ComboRow) and item.get_title()=='Startup Interface' for item in groups)
    w.keyboard_input();assert w.input_stack.get_visible_child_name()=='couch'
    steam_group=next(item for item in groups if isinstance(item,ui.Adw.PreferencesGroup) and item.get_title()=='Steam Library')
    assert steam_group.get_parent() is not None
    w.steam_shortcut_added=lambda:True
    w.refresh_steam_shortcut_action()
    assert w.steam_shortcut_button.get_label()=='Remove from Steam'
    w.steam_shortcut_added=lambda:False
    w.show_about()
    assert w.dialog.get_content_width()==420
    w.dialog.close()
    w.show_settings()
    groups=list(descendants(w.dialog))
    selector=next(item for item in groups if isinstance(item,ui.Adw.ToggleGroup) and item.get_active_name() in ('posters','capsules','list'))
    original=w.settings['library_view']
    selector.set_active_name('list')
    assert w.view_buttons['list'].get_active() and w.settings['library_view']=='list'
    w.dialog.close()
    assert w.settings['library_view']==original and w.view_buttons[original].get_active()
def switch_to_desktop():
    app.window.set_big_picture_ui(False)
def desktop_selected():
    w=app.window
    assert w.input_stack.get_visible_child_name()=='desktop'
    assert w.settings['input_mode']=='desktop' and not w.settings['big_picture_ui']
    w.set_big_picture_ui(True)
def big_picture_selected():
    w=app.window
    assert w.input_stack.get_visible_child_name()=='couch'
    assert w.settings['input_mode']=='couch' and w.settings['big_picture_ui']
    w.keyboard_input()
    assert w.input_stack.get_visible_child_name()=='couch'
def branding():
    couch=app.window.couch
    couch.update_branding(80)
    assert couch.brand_icon.get_pixel_size()==40 and couch.brand_button.has_css_class('collapsed')
    couch.update_branding(0)
    assert couch.brand_icon.get_pixel_size()==72 and not couch.brand_button.has_css_class('collapsed')
def capture():
    assert app.window.capture('resume-library-first.png').is_file()
steps=[start,layout_and_settings,switch_to_desktop,desktop_selected,big_picture_selected,branding,capture]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(800,step)
        else:print('PASS: Library-first, truthful empty/filtered counts, independent reviewed Restore/Update, collapsing brand; no game or Steam writes',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(1800,step);app.run([]);raise SystemExit(app.exit_code)
