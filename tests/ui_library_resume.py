"""Native Library-first checks using demo games and intercepted operations."""
import argparse,os,sys,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import GLib
app=ui.Application(argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic'))
from game_mode import descendants,SETTINGS_SECTIONS
def texts(widget):
    return {x.get_text() for x in descendants(widget) if isinstance(x,ui.Gtk.Label)}
def start():
    w=app.window;w.set_default_size(1440,960);w.set_input_surface(True);c=w.couch
    assert c.header.get_center_widget().get_valign()==ui.Gtk.Align.CENTER
    assert c.page=='library', f'Initial Game Mode page: {c.page}'
    w.games=w.games[:3]
    for game in w.games:game['blocked']='Unsupported fixture';game['installed']=False
    w.settings['library_filter']='available';c.render()
    key=lambda name:c.find_key(c.body,name)
    assert '3 games · 0 configured' in texts(c.body)
    assert not any(key(name).get_sensitive() for name in ('lib-install','lib-restore','lib-update'))
    assert 'No games match this filter' in texts(c.body)
    w.games[0]['blocked']='';w.games[0]['installed']=True
    # Available means not installed and not blocked (Windows LibraryScope),
    # so the installed game's library actions are reached from Installed.
    w.settings['library_filter']='installed';c.render()
    assert '3 games · 1 configured' in texts(c.body)
    assert all(key(name).get_sensitive() for name in ('lib-install','lib-restore','lib-update'))
    calls=[];w.launch_action=lambda *args,**kwargs:calls.append(('restore',args,kwargs));w.update_dlss_games=lambda rows:calls.append(('update',rows))
    key('lib-restore').emit('clicked');key('lib-update').emit('clicked')
    assert [call[0] for call in calls]==['restore','update']
    assert calls[0][2]['targets']==[w.games[0]] and calls[1][1]==[w.games[0]]
    # Hand the fixture back: Available needs uninstalled, unblocked games.
    for game in w.games:game['blocked']=''
    w.settings['library_filter']='available'
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
        assert w.settings['library_view']==view
        # Game Mode keeps the hidden desktop gallery as it is and applies the
        # choice when the desktop returns (view_changed's deferred path).
        assert getattr(w,'_deferred_desktop_library_view',None)==view
    couch.open('menu')
    titles=texts(couch.modal_layer)
    assert 'Exit App' in titles and 'Desktop UI' in titles and 'Dashboard' not in titles
    couch.close_all_modals()
    couch.open('dashboard')
    assert couch.page=='library'
    moved={'Add rtxForge to Steam','Sync artwork to Steam','Steam artwork profile','Connect SteamGridDB','Game Mode scale','Navigation placement','Controller hints'}
    assert not titles & moved
    couch.open('settings')
    settings_entries=set()
    for section in SETTINGS_SECTIONS:
        couch.open_settings_section(section)
        settings_entries.update(texts(couch.body))
    assert moved <= settings_entries,moved-settings_entries
    assert couch.find_key(couch,'tab-settings').get_visible()
    couch.open_settings_section('Gaming Mode')
    couch.open('library')
    # In Game Mode, show_settings opens Game Mode's Settings page; these checks
    # cover the desktop Settings dialog, so look at it from desktop input.
    w.input_stack.set_visible_child_name('desktop')
    w.show_settings()
    def descendants(widget):
        yield widget
        child=widget.get_first_child()
        while child:
            yield from descendants(child)
            child=child.get_next_sibling()
    groups=list(descendants(w.dialog))
    assert {'Steam Library','Steam integration','App and updates'} <= {item.get_title() for item in groups if isinstance(item,ui.Adw.PreferencesGroup)}
    captions={item.get_label() for item in groups if isinstance(item,ui.ActionButton)}
    assert {'Add to Steam','Sync','Connect','Choose'} <= captions
    interface=next(item for item in groups if isinstance(item,ui.Adw.ComboRow) and item.get_title()=='Interface')
    assert interface.get_model().get_n_items()==2
    assert not any(isinstance(item,ui.Adw.ComboRow) and item.get_title()=='Startup Interface' for item in groups)
    w.input_stack.set_visible_child_name('couch')
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
    w.input_stack.set_visible_child_name('desktop')
    w.show_settings()
    groups=list(descendants(w.dialog))
    selector=next(item for item in groups if isinstance(item,ui.Adw.ToggleGroup) and item.get_active_name() in ('posters','capsules','list'))
    original=w.settings['library_view']
    selector.set_active_name('list')
    assert w.view_buttons['list'].get_active() and w.settings['library_view']=='list'
    w.dialog.close()
    # Settings apply immediately, as on Windows: closing keeps the choice.
    assert w.settings['library_view']=='list' and w.view_buttons['list'].get_active()
    w.view_buttons[original].set_active(True)
    w.input_stack.set_visible_child_name('couch')
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
    # The brand is artwork only; the header's ⋯ button opens the main menu.
    couch=app.window.couch
    brand=couch.find_key(couch,'brand')
    assert not brand.get_can_target() and not brand.get_focusable()
    couch.find_key(couch,'menu').emit('clicked');assert couch.modals
    couch.navigate('back');assert not couch.modals
def gaming_theme():
    # Windows 1.0 Beta: Settings > Gaming Mode > Theme, with linked pickers.
    w=app.window;couch=w.couch
    w.input_stack.set_visible_child_name('desktop');w.show_settings()
    page=w.settings_pages['Gaming Mode'];w.dialog.set_visible_page(page)
    c=w.gaming_theme_controls
    group=c['theme'].get_ancestor(ui.Adw.PreferencesGroup)
    assert group.get_title()=='Theme' and group.get_ancestor(ui.Adw.PreferencesPage) is page
    assert c['linked'].get_ancestor(ui.Adw.PreferencesGroup) is group and c['opacity'].get_ancestor(ui.Adw.PreferencesGroup) is group
    w._theme_before=(w.settings.get('theme'),w.settings.get('game_mode_theme_linked',True))
    assert c['linked'].get_active()
    c['theme'].set_active_name('light')
    assert w.settings['theme']=='light' and couch.theme.name=='light','linked: one theme for both'
    c['linked'].set_active(False);c['theme'].set_active_name('dark')
    assert w.settings['theme']=='light' and w.settings['game_mode_theme']=='dark' and couch.theme.name=='dark','unlinked: Game Mode only'
    c['opacity'].set_value(40);assert w.settings['game_mode_card_opacity']==40
def gaming_theme_restore():
    w=app.window;c=w.gaming_theme_controls;theme,linked=w._theme_before
    c['opacity'].set_value(10);c['linked'].set_active(True);c['theme'].set_active_name(theme or 'night')
    assert w.couch.theme.name==(theme or 'night')
    w.dialog.close();w.input_stack.set_visible_child_name('couch')
def capture():
    assert app.window.capture('resume-library-first.png').is_file()
steps=[start,layout_and_settings,switch_to_desktop,desktop_selected,big_picture_selected,branding,capture,
       gaming_theme,lambda:app.window.capture('settings-gaming-theme.png'),gaming_theme_restore]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(800,step)
        else:print('PASS: Library-first, truthful empty/filtered counts, independent reviewed Restore/Update, brand menu; no game or Steam writes',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(1800,step);app.run([]);raise SystemExit(app.exit_code)
