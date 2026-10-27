"""Native regression check for Settings, scaling boundaries and scroll edges."""
import argparse,os,sys,traceback
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as ui
from gi.repository import GLib,Gtk,Adw
options=argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic')
app=ui.Application(options)
def assert_brand(light):
    # In-app brand marks use the plain logo mark (no platter) in every theme;
    # the window and launcher icon follow the effective appearance.
    expected=ui.Gdk.Texture.new_from_filename(str(ROOT/'gui/icons/rtxforge-mark.svg')).save_to_png_bytes().get_data()
    images=[image for image in ui.BRAND_IMAGES if image.get_paintable() is not None]
    assert images
    assert all(image.get_paintable().save_to_png_bytes().get_data()==expected for image in images)
    assert ui.Gtk.Window.get_default_icon_name().endswith('-light')==light

def children(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from children(child)
        child=child.get_next_sibling()
def start():
    w=app.window
    w.set_input_surface(False);w.set_display_preference('ui_scale',200)
    assert w.presentation_scale==1 and not isinstance(w.get_content(),ui.ScaledContent)
    w.settings['runtime_provider']='skynizz'
    w.show_settings()
    assert isinstance(w.dialog,Adw.PreferencesDialog)
    assert w.dialog.get_search_enabled()
    assert not hasattr(w.dialog,'_scaled_child')
    widgets=list(children(w.dialog.get_child()))
    rows={x.get_title():x for x in widgets if isinstance(x,Adw.ComboRow)}
    assert 'UI Scale' in rows
    rows['UI Scale'].emit('activated')
    rows['UI Scale'].set_selected(3)
    assert w.presentation_scale==1
    w.dialog.set_visible_page_name('Appearance')
    w.appearance_group=next(x for x in children(w.settings_pages['Appearance']) if isinstance(x,Adw.PreferencesGroup))
    assert w.appearance_group.get_title()=='Theme'
    w.theme_control=next(x for x in widgets if isinstance(x,Adw.ToggleGroup) and x.get_active_name() in ('dark','light','night'))
def theme():
    w=app.window;w.theme_control.set_active_name('light')
    w.text_probe=ui.button('Continue',lambda *_:None,'suggested-action')
    w.probe_row=Adw.ActionRow(title='Action contrast fixture')
    w.probe_row.add_suffix(w.text_probe);w.appearance_group.add(w.probe_row)
def appearance():
    assert_brand(True)
    w=app.window
    text=next(x for x in children(w.text_probe) if isinstance(x,Gtk.Label))
    color=text.get_style_context().get_color()
    assert max(color.red,color.green,color.blue)<0.5
    w.appearance_group.remove(w.probe_row)
    choices=next(x for x in children(w.dialog.get_child()) if isinstance(x,Adw.ComboRow) and x.get_title()=='Corners')
    choices.emit('activated');w.corner_choice=choices
    next(x for x in children(choices) if isinstance(x,Gtk.Popover)).popup()

def choice_sizes():
    w=app.window
    popup=next(x for x in children(w.corner_choice) if isinstance(x,Gtk.Popover))
    rows=[x for x in children(popup) if x.get_css_name()=='row' and x.get_mapped()]
    assert len(rows)==3, [(x.get_css_name(),x.get_height()) for x in children(popup)]
    heights=[x.get_height() for x in rows]
    assert max(heights)-min(heights)<=1 and max(heights)<=44, heights
    assert w.capture('settings-uniform-choice.png')
    popup.popdown()
    w.dialog.set_visible_page_name('Gaming Mode')

def gaming():
    w=app.window
    assert w.capture('settings-refined-gaming-mode.png')
    assert w.dialog.get_visible_page_name()=='Gaming Mode'
    w.theme_control.set_active_name('night')
    assert_brand(False)
    w.theme_control.set_active_name('dark')
    assert_brand(False)
    w.set_big_picture_ui(False);w.set_input_surface(True)
    assert w.input_stack.get_visible_child_name()=='desktop'
    w.set_big_picture_ui(True)
    w.dialog.close()
def independent_themes():
    w=app.window;w.show_settings()
    switch=next(x for x in children(w.settings_pages['Appearance']) if isinstance(x,Adw.SwitchRow) and x.get_title()=='Use the same color theme in Desktop and Game Mode')
    assert switch.get_active()
    before=w.couch.theme.name
    switch.set_active(False)
    w.theme_control=next(x for x in children(w.settings_pages['Appearance']) if isinstance(x,Adw.ToggleGroup) and x.get_active_name() in ('dark','light','night'))
    w.theme_control.set_active_name('light' if before!='light' else 'dark')
    assert w.couch.theme.name==before
    switch.set_active(True)
    assert w.couch.theme.name==w.settings['theme']
    w.dialog.close()


def extras_open():
    app.window.show_extras()
def extras():
    # Extras is a sidebar page beside the Library, not a dialog.
    w=app.window
    page=w.page_stack.get_visible_child()
    assert w.page_stack.get_visible_child_name()=='extras'
    assert any(isinstance(x,Gtk.Picture) for x in children(page)) or not any(g.get('poster') for g in w.games)
    assert w.capture('settings-refined-extras.png')
    w.show_page('library')
def details_open():
    w=app.window;w.settings['separate_game_details']=True;w.details(w.games[0])
    close=next(x for x in children(w.dialog.get_child()) if x.has_css_class('game-detail-close'))
    close.add_css_class('light');w.test_close=close
def details_check():
    w=app.window
    color=w.test_close.get_style_context().get_color()
    assert max(color.red,color.green,color.blue)<.2
    w.test_close.emit('clicked')
def game_mode():
    w=app.window;w.set_input_surface(True);w.set_display_preference('ui_scale',150)
    assert w.presentation_scale==1
    assert w.couch.theme.unit==26.0
    w.couch.open('settings');w.couch.navigate('right')
    w.set_input_surface(False)
    assert w.presentation_scale==1
    adj=w.library_scroll.get_vadjustment();adj.set_value(adj.get_upper()-adj.get_page_size())
    assert not any(x.has_css_class('library-bottom-fade') for x in children(w))
def system_theme():
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.DEFAULT)
def system_brand():
    assert_brand(not Adw.StyleManager.get_default().get_dark())

steps=[start,theme,appearance,choice_sizes,gaming,independent_themes,extras_open,extras,details_open,details_check,game_mode,system_theme,system_brand]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(800,step)
        else:print('PASS: native Settings choices/theme/close lifecycle, Gaming Mode disable, desktop scaling isolation, artwork and scroll end visibility',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(2000,step)
result=app.run([sys.argv[0]])
raise SystemExit(app.exit_code or result)
