"""Native controller layouts, shared appearance and navigation; no game writes."""
import argparse
import json
import os
import sys
import traceback
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


def capture(name):
    assert app.window.capture(name).is_file()
    captured.append(name)


def compact_presets_fit():
    couch = app.window.couch
    adjustment = couch.panel_scroll.get_vadjustment()
    assert adjustment.get_upper() <= adjustment.get_page_size() + 1, 'Both preset scope actions must fit the compact viewport'


def setup():
    window = app.window
    window.settings['controller_glyphs'] = 'xbox'
    window.settings['runtime_provider'] = 'dlss-unlocked'
    window.games.sort(key=lambda game: not bool(game.get('capsule')))
    window.games[0]['feature_mode'] = 'nr-mfg'
    window.games[0]['profile'] = 'NR + MFG'
    window.set_input_surface(True)
    assert window.couch.page == 'dashboard'


def view(name):
    couch = app.window.couch
    couch.open('library')
    couch.set_library_view(name)
    couch.focus(0)
    assert app.window.settings['library_view'] == name
    assert app.window.view_buttons[name].get_active()


def glyphs(family):
    app.window.settings['controller_glyphs'] = family
    app.window.couch.update_prompts()


def grid_navigation():
    couch = app.window.couch
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
    next(entry for entry in couch.entries if entry['title'] == 'Library layout')['adjust'](1)
    assert couch.library_view == 'capsules'
    couch.navigate('back')
    assert couch.page == 'library'
    couch.set_library_view('list')
    couch.focus(0)
    couch.navigate('up')
    assert couch.zone == 'views'
    assert len(couch.view_buttons) == 2  # Primary action plus consolidated Filter & View.
    assert couch.library_view == 'list'
    couch.navigate('down')
    couch.navigate('down')
    assert couch.current == 1
    couch.focus(len(couch.entries) - 1)


def scroll_and_tabs():
    couch = app.window.couch
    adjustment = couch.grid_scroll.get_vadjustment()
    assert adjustment.get_value() > 0
    allocation = couch.controls[couch.current].get_allocation()
    assert allocation.y + allocation.height <= adjustment.get_value() + adjustment.get_page_size() + 2
    couch.focus(0)
    couch.navigate('up')
    couch.navigate('up')
    assert couch.zone == 'nav'
    couch.navigate('right')
    couch.navigate('accept')
    assert couch.page == 'presets'
    assert couch.tabs[2].has_css_class('active')
    assert couch.game is app.window.games[0]
    couch.navigate('back')
    assert couch.page == 'library'
    couch.navigate('next')
    assert couch.page == 'presets'
    couch.navigate('next')
    assert couch.page == 'dlss'
    assert couch.game is app.window.games[0]
    assert [entry['title'] for entry in couch.entries] == ['Update all', 'Select games to update']
    couch.navigate('up')
    couch.navigate('up')
    couch.navigate('right')
    assert couch.tab_index == 4
    couch.navigate('accept')
    assert couch.page == 'menu' and not couch.settings_button.get_visible()
    couch.navigate('back')
    assert couch.page == 'dlss'


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
        assert couch.view_index == 0
        couch.navigate('right')  # Consolidated Filter & View.
        assert couch.view_index == 1
        couch.navigate('accept')
        assert couch.page == 'library_filters' and couch.dlss_selection == chosen
        couch.navigate('back')
        couch.focus(0);couch.navigate('up')
        assert couch.view_index == 0
        couch.navigate('accept')
        assert set(calls[-1][1]) == chosen
        couch.navigate('back')
        assert couch.page == 'dlss' and couch.dlss_selection is None
        couch.open('library')
        couch.focus(0)
        couch.navigate('up')
        assert couch.view_index == 0
        couch.navigate('accept')
        assert couch.page == 'features_all'
        couch.focus(0)
        couch.navigate('accept')
        assert calls[-1][0] == 'install'
        assert calls[-1][1]['targets'] == [g for g in window.games if g.get('test_record', {}).get('status') != 'Bench']
        assert not calls[-1][1].get('entire')  # Always retain installation review.
        couch.navigate('back')
        assert couch.page == 'library'
        game = window.games[0]
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
        selected = window.games[eligible]
        assert couch.dlss_selection == {selected['game']}
        couch.library_primary_action()
        assert calls[-1][1]['targets'] == [selected]
        assert calls[-1][1]['visual_settings']['sharpening_strength'] == .4
        couch.navigate('back')
        assert couch.page == 'presets' and couch.pending['sharpening_strength'] == .4
        couch.open('library')
        couch.open_game(selected)
        next(entry for entry in couch.entries if entry['title'] == 'Presets')['action']()
        assert couch.page == 'game_presets'
        assert couch.tabs[1].has_css_class('active') and not couch.tabs[2].has_css_class('active')
        assert couch.panel_detail.get_text() == selected['name']
        couch.navigate('back')
        assert couch.page == 'game'
        couch.navigate('menu')
        assert couch.page == 'menu'
        couch.navigate('back')
        assert couch.page == 'game'
        couch.navigate('settings')
        assert couch.page == 'settings' and any(e['title'] == 'Exit app' for e in couch.entries)
        couch.navigate('back')
        assert couch.page == 'game'
        couch.open('dashboard')
        couch.navigate('back')
        assert couch.page == 'dashboard'
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



def input_and_appearance():
    window = app.window
    couch = window.couch
    game = couch.game
    couch.open_game(game)
    assert couch.art_path == (game.get('hero') or game.get('capsule'))
    original_hero=game.get('hero')
    alternate=window.games[1].get('hero')
    if original_hero and alternate:
        window.event({'kind':'art','game':game['game'],'data':{'hero':alternate}})
        assert couch.art_path==alternate
        window.event({'kind':'art','game':game['game'],'data':{'hero':original_hero}})
    shared = '#' + window._ensure_game_accent(game).removeprefix('art-')
    assert couch.accent_color == shared
    window.settings['game_accents'][game['game']] = '#aabbcc'
    couch.set_game(game)
    assert couch.accent_color == '#aabbcc'
    del window.settings['game_accents'][game['game']]
    couch.set_game(game)
    active = window.is_active
    window.is_active = lambda: True
    try:
        window.set_input_surface(True)
        for x in (0, 5, 10, 15, 20, 25, 30):
            window.pointer_input(None, x, 0)
        assert window.input_stack.get_visible_child_name() == 'desktop'
        window.set_input_surface(True)
    finally:
        window.is_active = active
    window.keyboard_input()
    assert window.input_stack.get_visible_child_name() == 'desktop'
    window.set_input_surface(True)
    assert window.input_stack.get_visible_child_name() == 'couch'
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
    couch.open('menu')
    next(entry for entry in couch.entries if entry['title'] == 'Packages')['action']()
    assert couch.page == 'packages'


steps = [
    setup,
    lambda: capture('couch-dashboard-1280.png'),
    lambda: app.window.couch.navigate('accept'),
    lambda: capture('couch-game-1280.png'),
    lambda: app.window.launch_action('install', targets=[app.window.couch.game], _presets_confirmed=True),
    lambda: capture('couch-install-review-1280.png'),
    close_review,
    lambda: app.window.couch.open('presets'),
    lambda: capture('couch-presets-1280.png'),
    lambda: app.window.couch.open('dlss'),
    lambda: capture('couch-dlss-1280.png'),
    lambda: app.window.couch.open('settings'),
    lambda: capture('couch-settings-1280.png'),
    batch_flows,
    global_and_game_presets,
    selection_preview,
    lambda: capture('couch-dlss-select-1280.png'),
    batch_review,
    lambda: capture('couch-dlss-review-1280.png'),
    close_review,
    lambda: app.window.couch.back(),
    lambda: view('posters'),
    lambda: capture('couch-library-posters-1280.png'),
    grid_navigation,
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
    lambda: app.window.couch.open('dashboard'),
    lambda: capture('couch-dashboard-800.png'),
    lambda: app.window.couch.open('presets'),
    compact_presets_fit,
    lambda: capture('couch-presets-800.png'),
    lambda: app.window.couch.open('dlss'),
    lambda: capture('couch-dlss-800.png'),
    selection_preview,
    lambda: capture('couch-dlss-select-800.png'),
    lambda: app.window.couch.back(),
    input_and_appearance,
]


def step():
    try:
        if steps:
            steps.pop(0)()
            GLib.timeout_add(550, step)
        else:
            (ROOT / 'dist/ui-couch-review.json').write_text(json.dumps({'game_writes': False, 'screenshots': captured, 'checked': ['grid navigation', 'list navigation', 'return selection', 'view cycling', 'Classic shared preference', 'last-row scrolling', 'page tabs and settings gear', 'batch DLSS target selection', 'install-to-all review routing', 'disabled first-row navigation', 'shared accent and artwork', 'input switching', 'empty library']}, indent=2))
            app.quit()
    except Exception:
        traceback.print_exc()
        app.exit_code = 1
        app.quit()
    return False


GLib.timeout_add(1800, step)
result = app.run([sys.argv[0]])
raise SystemExit(app.exit_code or result)
