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
    suffix='-light' if light else ''
    expected=ui.Gdk.Texture.new_from_filename(str(ROOT/'gui/icons/hicolor/scalable/apps'/f'io.github.lrnolivia.RTXForge{suffix}.svg')).save_to_png_bytes().get_data()
    assert len(ui.BRAND_IMAGES)>=3
    assert all(image.get_paintable().save_to_png_bytes().get_data()==expected for image in ui.BRAND_IMAGES)

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
    w.show_settings()
    assert w.dialog._scaled_child is None
    widgets=list(children(w.dialog.get_child()))
    rows={x.get_title():x for x in widgets if isinstance(x,Adw.ComboRow)}
    assert 'UI Scale' in rows
    rows['UI Scale'].emit('activated')
    rows['UI Scale'].set_selected(3)
    assert w.presentation_scale==1
    w.settings_stack=next(x for x in widgets if isinstance(x,Gtk.Stack) and x.get_child_by_name('Appearance'))
    next(x for x in widgets if isinstance(x,Gtk.ListBoxRow) and getattr(x,'page_name',None)=='Appearance').get_parent().select_row(next(x for x in widgets if isinstance(x,Gtk.ListBoxRow) and getattr(x,'page_name',None)=='Appearance'))
    assert next(x for x in children(w.settings_stack.get_visible_child()) if isinstance(x,Adw.PreferencesGroup)).get_title()=='Theme'
    w.theme_control=next(x for x in widgets if isinstance(x,Adw.ToggleGroup) and x.get_active_name() in ('dark','light','night'))
def theme():
    w=app.window;w.theme_control.set_active_name('light')
    w.text_probe=ui.button('Continue',lambda *_:None,'suggested-action')
    w.dialog.get_child().append(w.text_probe)
def appearance():
    assert_brand(True)
    w=app.window
    text=next(x for x in children(w.text_probe) if isinstance(x,Gtk.Label))
    color=text.get_style_context().get_color()
    assert max(color.red,color.green,color.blue)<0.5
    w.dialog.get_child().remove(w.text_probe)
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
    rows=list(children(w.dialog.get_child()))
    target=next(x for x in rows if isinstance(x,Gtk.ListBoxRow) and getattr(x,'page_name',None)=='Gaming Mode')
    target.get_parent().select_row(target)

def gaming():
    w=app.window
    assert w.capture('settings-refined-gaming-mode.png')
    scroll=w.settings_stack.get_visible_child().get_child()
    adj=scroll.get_vadjustment();adj.set_value(adj.get_upper()-adj.get_page_size())
    assert w.settings_stack.get_visible_child().bottom_fade.get_opacity()==0
    w.theme_control.set_active_name('night')
    assert_brand(False)
    w.theme_control.set_active_name('dark')
    assert_brand(False)
    w.set_big_picture_ui(False);w.set_input_surface(True)
    assert w.input_stack.get_visible_child_name()=='desktop'
    w.set_big_picture_ui(True)
    w.dialog.close()
def extras_open():
    app.window.show_extras()
def extras():
    w=app.window
    assert any(isinstance(x,Gtk.Picture) for x in children(w.dialog.get_child())) or not any(g.get('poster') for g in w.games)
    assert w.capture('settings-refined-extras.png')
    w.dialog.close()
def details_open():
    w=app.window;w.details(w.games[0])
    close=next(x for x in children(w.dialog.get_child()) if x.has_css_class('game-detail-close'))
    close.add_css_class('light');w.test_close=close
def details_check():
    w=app.window
    color=w.test_close.get_style_context().get_color()
    assert max(color.red,color.green,color.blue)<.2
    w.test_close.emit('clicked')
def game_mode():
    w=app.window;w.set_input_surface(True);w.set_display_preference('ui_scale',150)
    assert w.presentation_scale==1.5
    w.couch.open('settings');w.couch.navigate('right')
    w.set_input_surface(False)
    assert w.presentation_scale==1
    adj=w.library_scroll.get_vadjustment();adj.set_value(adj.get_upper()-adj.get_page_size())
    assert w.library_bottom_fade.get_opacity()==0
def system_theme():
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.DEFAULT)
def system_brand():
    assert_brand(not Adw.StyleManager.get_default().get_dark())

steps=[start,theme,appearance,choice_sizes,gaming,extras_open,extras,details_open,details_check,game_mode,system_theme,system_brand]
def step():
    try:
        if steps:steps.pop(0)();GLib.timeout_add(800,step)
        else:print('PASS: native Settings choices/theme/close lifecycle, Gaming Mode disable, desktop scaling isolation, artwork and scroll end visibility',flush=True);app.quit()
    except Exception:traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(2000,step)
result=app.run([sys.argv[0]])
raise SystemExit(app.exit_code or result)
