"""Native controller layouts, shared appearance and navigation; no game writes."""
import argparse
import json
import os
import sys
import traceback
import time
from pathlib import Path

os.environ['GSETTINGS_BACKEND'] = 'memory'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'gui'))
import rtxforge_gtk as ui
from gi.repository import GLib
from demo_assets import prepare
prepare(ROOT)
options = argparse.Namespace(provider=None, demo=True, resize_smoke=False, smoke_test=False, live_smoke=False, library_state_smoke=False, ui_mode='classic')
app = ui.Application(options)
captured = []
desktop_view = None


class FrameNotReady(RuntimeError):
    pass


class SettledStep:
    """Keep action state across native dialog mapping/closing frames."""
    def __init__(self,factory):self.factory=factory;self.iterator=None;self.started=None
    def __call__(self):
        if self.iterator is None:self.iterator=self.factory();self.started=time.monotonic()
        if time.monotonic()-self.started>30:
            self.iterator.close()
            raise AssertionError('Native dialog did not settle: '+self.factory.__name__)
        try:next(self.iterator)
        except StopIteration:return
        raise FrameNotReady(self.factory.__name__)


pending_capture = None


def descendants(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from descendants(child)
        child=child.get_next_sibling()


def dialog_button(dialog,title):
    return next(widget for widget in descendants(dialog) if isinstance(widget,ui.Gtk.Button) and (widget.get_label()==title or getattr(widget,'text_label',None) and widget.text_label.get_text()==title))


def embedded_details():
    window=app.window;couch=window.couch
    assert couch.page=='game' and couch.body.get_visible_child_name()=='details'
    assert window.get_visible_dialog() is None, 'Details must be embedded rather than modal'
    assert [window.detail_nav.get_row_at_index(i).page_name for i in range(6)]==['Overview','Features','DLSS Files','Tools','Notes','Appearance']
    assert window.detail_nav.get_row_at_index(6) is None
    back=window.detail_back_button
    assert isinstance(back.get_child(),ui.Gtk.Box)
    assert back.get_child().get_first_child().get_icon_name()=='go-previous-symbolic'
    assert 'Configured' in window.detail_setup_metadata.get_text() if couch.game.get('installed') else 'Not installed' in window.detail_setup_metadata.get_text()
    rows=[widget for widget in descendants(window.detail_information) if widget.has_css_class('couch-information-row')]
    assert len(rows)>=3
    assert all(isinstance(item.get_first_child(),ui.Gtk.Label) and item.get_last_child().get_xalign()==1 for item in rows)


def capture(name):
    global pending_capture
    if name=='couch-game-1280.png':
        window=app.window
        back=window.detail_back_button
        back_ok,back_bounds=back.compute_bounds(window)
        posters=[widget for widget in descendants(window.couch.details_panel) if widget.has_css_class('progress-poster-frame')]
        assert back_ok and posters
        poster_ok,poster_bounds=posters[0].compute_bounds(window)
        if not (poster_ok and back_bounds.get_y()+back_bounds.get_height()<poster_bounds.get_y()):window.capture('couch-hero-overlap-debug.png')
        assert poster_ok and back_bounds.get_y()+back_bounds.get_height()<poster_bounds.get_y(), f'Back must clear the poster: back={back_bounds.get_y()}+{back_bounds.get_height()}, poster={poster_bounds.get_y()}'
    if name=='couch-library-posters-1280.png':
        couch=app.window.couch
        assert all(control.title_label.get_wrap() and control.title_label.get_lines()==2 for control in couch.controls)
        placeholders=[control.artwork.placeholder for control in couch.controls if control.artwork.placeholder]
        assert all(isinstance(widget,ui.Gtk.Image) for widget in placeholders), 'Missing artwork contains a controller icon, never a duplicate title'
    image = app.window.capture(name)
    if image is None:
        if pending_capture is None:
            pending_capture = (name, time.monotonic())
        if pending_capture[0] != name:
            raise AssertionError('Capture changed while waiting for a frame')
        if time.monotonic() - pending_capture[1] >= 5:
            raise AssertionError(f'GTK frame not ready after 5s: {name}; mapped={app.window.get_mapped()}, size={app.window.get_width()}x{app.window.get_height()}')
        app.window.queue_draw()
        raise FrameNotReady(name)
    assert image.is_file(), f'Capture did not create an image: {name}'
    pending_capture = None
    captured.append(name)


def compact_presets_fit():
    couch = app.window.couch
    adjustment = couch.workspace_scroll.get_vadjustment()
    assert couch.workspace_footer.get_visible() and couch.workspace_footer.get_height()>0, 'Preset actions must remain outside the scrolling controls'


def setup():
    global desktop_view
    window = app.window
    desktop_view=window.settings['library_view']
    window.settings['controller_glyphs'] = 'xbox'
    window.settings['runtime_provider'] = 'dlss-unlocked'
    window.nr_only.set_enabled(True)  # Match the existing package-selection capability binding.
    window.games.sort(key=lambda game: not bool(game.get('capsule')))
    window.games[0]['feature_mode'] = 'nr-mfg'
    window.games[0]['profile'] = 'NR + MFG'
    window.profile_group.set_active_name('nr-mfg')
    window.set_input_surface(True)
    window.set_input_kind('controller')
    window.couch.navigate('right');window.couch.navigate('left')
    assert window.couch.page == 'library'


def view(name):
    couch = app.window.couch
    couch.open('library')
    couch.set_library_view(name)
    couch.focus(0)
    assert app.window.settings['gaming_mode_view'] == name
    assert couch.layout_controls[name].get_active()
    assert app.window.settings['library_view'] == desktop_view


def glyphs(family):
    app.window.settings['controller_glyphs'] = family
    app.window.couch.update_prompts()


def grid_navigation():
    window=app.window
    # Guarantee overflow independently of missing network artwork and which
    # demo games the Available filter excludes.
    original=list(window.games)
    for batch in range(3):
        for game in original:
            fixture=dict(game)
            fixture['game']=f"{game['game']}-scroll-{batch}"
            fixture['blocked']=''
            window.games.append(fixture)
    couch = window.couch
    couch.open('library')
    couch.focus(0)
    couch.navigate('right')
    assert couch.current == 1
    couch.navigate('down')
    assert couch.current == 1 + couch.columns
    selected = couch.current
    game = couch.game
    couch.navigate('accept')
    assert couch.page == 'game'
    couch.navigate('back')
    assert couch.page == 'library' and couch.current == selected and couch.game is game
    couch.navigate('search')
    assert couch.page == 'library' and couch.game is game
    couch.navigate('settings')
    assert couch.page == 'settings'
    couch.set_section('Library')
    next(entry for entry in couch.entries if entry['title'] == 'Library layout')['adjust'](1)
    assert couch.library_view == 'capsules'
    couch.navigate('back')
    assert couch.page == 'library'
    couch.set_library_view('list')
    couch.focus(0)
    couch.navigate('up')
    assert couch.zone == 'views'
    assert len(couch.view_buttons)==11  # Three feature modes, three operations, Filter, three views and selection.
    assert couch.library_focus_rows==[[*couch.feature_controls.values(),couch.library_action,couch.library_restore,couch.library_update],[couch.filter_button,*couch.layout_controls.values(),couch.select_button]]
    assert set(couch.layout_controls)=={'posters','capsules','list'}
    assert couch.library_view == 'list'
    couch.navigate('down')
    couch.navigate('down')
    assert couch.current == 1


def scroll_and_tabs():
    couch = app.window.couch
    adjustment = couch.grid_scroll.get_vadjustment()
    assert adjustment.get_value() > 0
    control=couch.controls[couch.current]
    allocation = getattr(control,'library_row',control).get_allocation()
    assert allocation.y + allocation.height <= adjustment.get_value() + adjustment.get_page_size() + 2
    couch.focus(0)
    couch.navigate('up')
    assert couch.zone=='views' and couch.view_buttons[couch.view_index] is couch.filter_button
    couch.navigate('up')
    assert couch.zone=='views' and couch.view_buttons[couch.view_index] in couch.feature_controls.values()
    couch.navigate('up')
    assert couch.zone == 'nav'
    couch.navigate('right')
    couch.navigate('accept')
    assert couch.page == 'presets'
    assert couch.tabs[1].has_css_class('active')
    assert couch.game is app.window.games[0]
    couch.navigate('back')
    assert couch.page == 'library'
    couch.navigate('next')
    assert couch.page == 'presets'
    couch.navigate('next')
    assert couch.page == 'settings'
    assert couch.game is app.window.games[0]
    assert [control.get_label() for control in couch.tabs[:3]]==['Library','Presets','Settings']
    assert len(couch.tabs)==4 and couch.tabs[3] is couch.brand_button
    assert couch.tabs[2].has_css_class('active')
    couch.navigate('next')
    assert couch.page=='library'
    couch.open('dlss')  # DLSS management remains available outside the three top tabs.
    assert [entry['title'] for entry in couch.entries] == ['Update all', 'Select games to update']
    couch.navigate('back');assert couch.page=='library'


def batch_flows():
    window = app.window
    couch = window.couch
    calls = []
    update = window.update_dlss_games
    install = window.launch_action
    window.update_dlss_games = lambda games: calls.append(('dlss', [g['game'] for g in games]))
    window.launch_action = lambda operation, **kwargs: calls.append((operation, kwargs))
    try:
        couch.open('dlss')
        couch.focus(0)
        couch.navigate('accept')
        assert calls[-1] == ('dlss', [g['game'] for g in window.games])
        couch.focus(1)
        couch.navigate('accept')
        assert couch.page == 'library' and couch.dlss_selection == set()
        assert not couch.library_action.get_sensitive()
        couch.set_library_view('posters')
        couch.focus(0)
        couch.navigate('accept')
        couch.navigate('right')
        couch.navigate('accept')
        chosen = {g['game'] for g in window.games[:2]}
        assert couch.dlss_selection == chosen
        couch.set_library_view('list')
        assert couch.dlss_selection == chosen
        couch.focus(0)
        couch.navigate('up')
        filter_index=couch.view_buttons.index(couch.filter_button)
        assert couch.view_index==filter_index
        couch.navigate('accept')
        dialog=window.get_visible_dialog()
        assert dialog is not None and couch.page=='library' and couch.dlss_selection==chosen
        yield
        assert dialog.couch_footer.get_parent() is dialog.get_child() and dialog.couch_footer.get_height()>0
        controls=[];control=dialog.couch_footer.get_first_child()
        while control:controls.append(control.text_label.get_text());control=control.get_next_sibling()
        assert controls==['Reset','Back','Apply'], 'Filter actions remain in a fixed footer'
        previous_filter=window.filter
        dialog_button(dialog,'Installed').emit('clicked')
        assert window.filter==previous_filter, 'Filter remains staged until Apply'
        dialog_button(dialog,'Back').emit('clicked')
        yield
        while dialog.get_mapped():yield
        assert window.filter==previous_filter and couch.dlss_selection==chosen
        assert couch.zone=='views' and couch.view_index==filter_index, 'Filter Back preserves the invoking control and controller zone'
        couch.library_action.grab_focus()
        yield
        couch.navigate('accept')
        assert set(calls[-1][1])==chosen
        couch.navigate('back')
        assert couch.page=='library' and couch.dlss_selection is None
        couch.open('library')
        # D-pad follows each visible row; Up from Filter reaches Features.
        couch.focus(0);couch.navigate('up');couch.navigate('up')
        assert couch.view_buttons[couch.view_index] is next(control for control in couch.feature_controls.values() if control.get_sensitive())
        couch.feature_controls['mfg-only'].grab_focus();yield
        couch.navigate('accept')
        assert window.profile_group.get_active_name()=='mfg-only'
        assert couch.feature_controls['mfg-only'].get_active()
        couch.navigate('accept')
        assert couch.feature_controls['mfg-only'].get_active(), 'Reactivating the chosen mode must keep it selected'
        couch.navigate('right');couch.navigate('accept')
        assert window.profile_group.get_active_name()=='nr-mfg'
        couch.navigate('right');couch.navigate('accept')
        assert couch.page=='library', 'Install stays in Library and invokes optional tuning'
        assert calls[-1][0]=='install'
        assert calls[-1][1]['targets']==[g for g in window.games if g.get('test_record',{}).get('status')!='Bench']
        assert not calls[-1][1].get('entire') and not calls[-1][1].get('_presets_confirmed')
        assert couch.filter_summary.get_text()=='Show: '+window.filter.title()
        game = window.games[0]
        status=game.setdefault('test_record',{}).get('status','Untested')
        game['test_record']['status']='Bench'
        try:
            couch.selection_kind='install';couch.dlss_selection={game['game']}
            couch.render();couch.library_primary_action()
            assert calls[-1][1]['targets']==[game], 'Explicit Bench selection remains a deliberate install target'
        finally:
            game['test_record']['status']=status
            couch.back()
        previous = game.get('feature_mode')
        game['feature_mode'] = 'mfg-only'
        couch.focus(0)
        couch.open('game_presets')
        assert couch.current == 1  # NR row is unavailable in MFG-only mode.
        couch.navigate('up')
        assert couch.zone == 'nav'
        game['feature_mode'] = previous
    finally:
        window.update_dlss_games = update
        window.launch_action = install


def global_and_game_presets():
    window = app.window
    couch = window.couch
    calls = []
    original = window.launch_action
    window.launch_action = lambda operation, **kwargs: calls.append((operation, kwargs))
    try:
        couch.open('presets')
        assert couch.panel_detail.get_text() == 'Across your configured games'
        expected = couch.preset_targets()
        couch.entries[-2]['action']()
        assert calls[-1][0] == 'reset' and calls[-1][1]['targets'] == expected
        assert not calls[-1][1].get('entire')
        couch.pending['sharpening_strength'] = .4
        couch.entries[-1]['action']()
        assert couch.page == 'library' and couch.dlss_selection == set()
        assert not couch.library_action.get_sensitive()
        eligible = next(i for i, entry in enumerate(couch.entries) if entry['enabled'])
        couch.focus(eligible)
        couch.navigate('accept')
        selected = couch.entries[eligible]['game']
        assert couch.dlss_selection == {selected['game']}
        couch.library_primary_action()
        assert calls[-1][1]['targets'] == [selected]
        assert calls[-1][1]['visual_settings']['sharpening_strength'] == .4
        couch.navigate('back')
        assert couch.page == 'presets' and couch.pending['sharpening_strength'] == .4
        couch.open('library')
        dialog=window.get_visible_dialog()
        assert isinstance(dialog,ui.Adw.AlertDialog), 'Leaving changed presets needs the discard guard'
        yield
        dialog_button(dialog,'Discard').emit('clicked')
        yield
        while dialog.get_mapped():yield
        assert couch.page=='library'
        # Supply readable fixture presets, then exercise the actual embedded
        # Features controls rather than relying only on the legacy scope page.
        for key in ('nr_strength','sharpening_strength','mfg_multiplier'):
            if selected.get(key) is None:selected[key]=window.settings[key]
        couch.open_game(selected)
        yield
        embedded_details()
        window.detail_nav.select_row(window.detail_nav.get_row_at_index(1))
        assert window.detail_pages.get_visible_child_name()=='Features'
        expander=next(widget for widget in descendants(window.detail_pages) if isinstance(widget,ui.Gtk.Expander) and widget.get_label()=='Presets')
        assert not expander.get_expanded();expander.set_expanded(True)
        sharp=window.detail_tuning_widgets['sharpening_strength'];original_sharp=sharp.get_value()
        edited_sharp=round(original_sharp-.1 if original_sharp>0 else .1,1)
        sharp.set_value(edited_sharp)
        assert window.detail_dirty() and window.detail_apply_settings.get_sensitive()
        window.detail_apply_settings.emit('clicked')
        assert calls[-1][0]=='reset' and calls[-1][1]['targets']==[selected]
        assert calls[-1][1]['visual_settings']['sharpening_strength']==edited_sharp
        couch.open('library');dialog=window.get_visible_dialog()
        assert isinstance(dialog,ui.Adw.AlertDialog)
        yield
        dialog_button(dialog,'Stay').emit('clicked')
        yield
        while dialog.get_mapped():yield
        assert couch.page=='game' and window.detail_dirty() and sharp.get_value()==edited_sharp
        couch.open('library');dialog=window.get_visible_dialog()
        yield
        dialog_button(dialog,'Discard').emit('clicked')
        yield
        while dialog.get_mapped():yield
        assert couch.page=='library' and abs(sharp.get_value()-original_sharp)<.00001
        couch.open_game(selected)
        couch.open('game_presets')
        assert couch.page == 'game_presets'
        assert couch.tabs[0].has_css_class('active') and not couch.tabs[1].has_css_class('active')
        assert couch.panel_detail.get_text() == selected['name']
        couch.navigate('back')
        assert couch.page == 'game'
        couch.navigate('menu')
        dialog=window.get_visible_dialog()
        assert dialog is not None and couch.page=='game'
        yield
        assert dialog_button(dialog,'Exit App').get_sensitive()
        dialog_button(dialog,'Back').emit('clicked')
        yield
        while dialog.get_mapped():yield
        assert couch.page == 'game'
        couch.navigate('settings')
        assert couch.page == 'settings' and couch.tabs[2].has_css_class('active')
        couch.set_section('System')
        assert {'UI scale','Navigation'} <= {e['title'] for e in couch.entries}
        couch.navigate('back')
        assert couch.page == 'game'
        couch.open('library')
        couch.navigate('back')
        assert couch.page == 'library'
        assert not couch.library_link.get_visible()  # Library remains in the main navigation.
    finally:
        window.launch_action = original


def selection_preview():
    couch = app.window.couch
    couch.select_dlss_games()
    couch.set_library_view('posters')
    couch.focus(0)
    couch.navigate('accept')
    couch.navigate('right')
    couch.navigate('accept')


def batch_review():
    couch = app.window.couch
    couch.library_primary_action()
    assert app.window.dialog is not None
    def descendants(widget):
        yield widget
        child = widget.get_first_child()
        while child:
            yield from descendants(child)
            child = child.get_next_sibling()
    update = next(w for w in descendants(app.window.dialog) if isinstance(w, ui.Gtk.Button) and w.get_label() == 'Update DLSS Files')
    assert not update.get_sensitive()
    update.emit('clicked')  # Handler also refuses programmatic preview activation.
    assert not app.window.busy or app.window.task_kind == 'art'


def close_review():
    app.window.dialog.close()


def modal_value_routing():
    window=app.window;dialog=window.dialog
    assert dialog.get_title()=='Install Features'
    assert dialog.get_child().get_first_child().get_visible(), 'Install title stays above the scroller'
    assert any(widget.has_css_class('couch-tuning-controls') for widget in descendants(dialog))
    assert dialog.has_css_class('couch-dialog')
    scales=[widget for widget in descendants(dialog) if isinstance(widget,ui.Gtk.Scale)]
    spins=[widget for widget in descendants(dialog) if isinstance(widget,ui.Gtk.SpinButton)]
    dropdowns=[widget for widget in descendants(dialog) if isinstance(widget,ui.Gtk.DropDown)]
    assert len(scales)==2 and len(spins)==2 and len(dropdowns)==1
    for widget in scales+spins:
        original=widget.get_value();adjustment=widget.get_adjustment()
        direction='left' if original>adjustment.get_lower() else 'right'
        widget.grab_focus()
        assert window.adjust_modal_controller_value(dialog,direction)
        expected=original+adjustment.get_step_increment()*(-1 if direction=='left' else 1)
        assert abs(widget.get_value()-expected)<.00001
        widget.set_value(original)
    dropdown=dropdowns[0];original=dropdown.get_selected();dropdown.grab_focus()
    assert window.adjust_modal_controller_value(dialog,'right')
    assert dropdown.get_selected()==(original+1)%dropdown.get_model().get_n_items()
    dropdown.set_selected(original)



def loading_navigation():
    window=app.window;couch=window.couch
    previous_busy,previous_kind=window.busy,window.task_kind
    try:
        window.busy=True;window.task_kind='scan';couch.sync_library_modes()
        for control in (couch.library_action,couch.library_restore,couch.library_update):control.set_sensitive(False)
        couch.zone='nav';couch.navigate('down')
        assert couch.zone=='views' and couch.view_buttons[couch.view_index] is couch.filter_button
    finally:
        window.busy=previous_busy;window.task_kind=previous_kind;couch.render(couch.current);couch.focus(0)


def parity_viewport(theme='night'):
    window=app.window;couch=window.couch
    window.settings['gaming_mode_theme']=theme
    window.apply_input_theme();couch.apply_theme()
    window.set_input_kind('controller')
    couch.open('library');couch.set_library_view('posters');couch.focus(0)
    couch.navigate('right');couch.navigate('left')


def light_contrast():
    couch=app.window.couch
    import ui_colors
    for control in [*couch.tabs[:3],couch.filter_button,couch.select_button,*couch.layout_controls.values(),*couch.feature_controls.values()]:
        if not control.get_sensitive():continue
        color=control.get_style_context().get_color()
        value='#'+''.join(f'{round(component*255):02x}' for component in (color.red,color.green,color.blue))
        assert ui_colors.contrast(value,'#fafafa')>=4.5, f'Light controls must be readable: {value}'


def input_and_appearance():
    window = app.window
    couch = window.couch
    game = couch.game
    couch.open_game(game)
    embedded_details()
    original_paintable=window.detail_banner.get_paintable()
    assert original_paintable is not None if game.get('hero') else True
    original_hero=game.get('hero')
    alternate=window.games[1].get('hero')
    if original_hero and alternate:
        window.event({'kind':'art','game':game['game'],'data':{'hero':alternate}})
        assert window.detail_banner.get_paintable() is not original_paintable
        window.event({'kind':'art','game':game['game'],'data':{'hero':original_hero}})
    shared = '#' + window._ensure_game_accent(game).removeprefix('art-')
    assert couch.accent_color == shared
    window.settings['game_accents'][game['game']] = '#aabbcc'
    couch.set_game(game)
    assert couch.accent_color == '#aabbcc'
    del window.settings['game_accents'][game['game']]
    couch.set_game(game)
    window.set_input_surface(True)
    window.keyboard_input()
    assert window.input_stack.get_visible_child_name() == 'couch'
    assert not hasattr(window,'pointer_input'), 'Pointer motion must not auto-switch the interface'
    games = window.games
    window.games = []
    couch.refresh()
    assert couch.game is None and couch.art.get_paintable() is None and couch.title.get_text() == 'Your library'
    assert couch.accent_color == '#76b900'
    couch.open('presets')
    assert couch.page == 'presets' and not couch.entries[-1]['enabled'] and not couch.entries[-2]['enabled']
    window.games = games
    couch.open('library')
    couch.refresh()
    game = couch.game
    installed = game.get('installed')
    game['installed'] = False
    couch.open('game_presets')
    assert not couch.entries[-1]['enabled']
    game['installed'] = installed
    couch.open('packages')
    assert couch.page == 'packages'


steps = [
    setup,
    lambda: capture('couch-library-initial-1280.png'),
    lambda: app.window.couch.navigate('accept'),
    lambda: capture('couch-game-1280.png'),
    lambda: app.window.launch_action('install', targets=[app.window.couch.game], _presets_confirmed=True),
    lambda: capture('couch-install-review-1280.png'),
    close_review,
    lambda: app.window.launch_action('install',targets=[app.window.couch.game]),
    modal_value_routing,
    lambda: capture('couch-install-presets-1280.png'),
    close_review,
    lambda: app.window.couch.open('presets'),
    lambda: capture('couch-presets-1280.png'),
    lambda: app.window.couch.open('dlss'),
    lambda: capture('couch-dlss-1280.png'),
    lambda: app.window.couch.open('settings'),
    lambda: capture('couch-settings-1280.png'),
    SettledStep(batch_flows),
    SettledStep(global_and_game_presets),
    selection_preview,
    lambda: capture('couch-dlss-select-1280.png'),
    batch_review,
    lambda: capture('couch-dlss-review-1280.png'),
    close_review,
    lambda: app.window.couch.back(),
    lambda: view('posters'),
    lambda: capture('couch-library-posters-1280.png'),
    grid_navigation,
    lambda: app.window.couch.focus(len(app.window.couch.entries) - 1),
    scroll_and_tabs,
    lambda: view('capsules'),
    lambda: capture('couch-library-wide-1280.png'),
    lambda: view('list'),
    lambda: capture('couch-library-list-1280.png'),
    lambda: glyphs('playstation'),
    lambda: capture('couch-playstation-1280.png'),
    lambda: glyphs('nintendo'),
    lambda: capture('couch-nintendo-1280.png'),
    lambda: glyphs('xbox'),
    lambda: app.window.set_default_size(800, 600),
    lambda: view('posters'),
    lambda: capture('couch-library-posters-800.png'),
    lambda: view('capsules'),
    lambda: capture('couch-library-wide-800.png'),
    lambda: view('list'),
    lambda: capture('couch-library-list-800.png'),
    lambda: app.window.couch.open('library'),
    lambda: capture('couch-library-final-800.png'),
    lambda: app.window.couch.open('presets'),
    compact_presets_fit,
    lambda: capture('couch-presets-800.png'),
    lambda: app.window.couch.open('dlss'),
    lambda: capture('couch-dlss-800.png'),
    selection_preview,
    lambda: capture('couch-dlss-select-800.png'),
    lambda: app.window.couch.back(),
    input_and_appearance,
    lambda: app.window.set_default_size(1920,1080),
    parity_viewport,
    loading_navigation,
    lambda: capture('couch-parity-night-library-1920.png'),
    lambda: app.window.couch.open('library_filters'),
    lambda: capture('couch-parity-night-filter-1920.png'),
    lambda: app.window.get_visible_dialog().close(),
    lambda: app.window.couch.open('menu'),
    lambda: capture('couch-parity-night-menu-1920.png'),
    lambda: app.window.get_visible_dialog().close(),
    lambda: app.window.couch.focus(0),
    lambda: app.window.couch.navigate('accept'),
    embedded_details,
    lambda: capture('couch-parity-night-details-1920.png'),
    lambda: app.window.launch_action('install',targets=[app.window.couch.game]),
    modal_value_routing,
    lambda: capture('couch-parity-night-tuning-1920.png'),
    close_review,
    lambda: parity_viewport('light'),
    lambda: glyphs('playstation'),
    light_contrast,
    lambda: capture('couch-parity-light-library-1920.png'),
    lambda: glyphs('xbox'),
    lambda: parity_viewport('dark'),
    lambda: capture('couch-parity-dark-library-1920.png'),
    lambda: parity_viewport('night'),
]


def step():
    try:
        if steps:
            steps[0]()
            steps.pop(0)
            GLib.timeout_add(550, step)
        else:
            (ROOT / 'dist/ui-couch-review.json').write_text(json.dumps({'game_writes': False, 'screenshots': captured, 'checked': ['grid navigation', 'list navigation', 'return selection', 'view cycling', 'independent desktop/Game Mode preference', 'last-row scrolling', 'three page tabs', 'embedded six-section Details', 'staged native filter', 'native menu/exit', 'dirty preset discard', 'batch DLSS target selection', 'install-to-all review routing', 'disabled first-row navigation', 'shared accent and artwork', 'input switching', 'empty library', 'inline feature selector reactivation', 'two-row toolbar navigation', 'explicit Bench selection', 'hero Back clearance', 'two-line titles and neutral artwork placeholders', 'fixed filter footer', 'Light control contrast', 'Night/Light/Dark controller captures']}, indent=2))
            app.quit()
    except FrameNotReady:
        GLib.timeout_add(100, step)
    except Exception:
        traceback.print_exc()
        app.exit_code = 1
        app.quit()
    return False


GLib.timeout_add(1800, step)
result = app.run([sys.argv[0]])
raise SystemExit(app.exit_code or result)
