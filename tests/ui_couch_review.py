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
    assert couch.library_view == 'capsules' and couch.game is game
    couch.focus(0)
    couch.navigate('up')
    assert couch.zone == 'views'
    couch.navigate('right')
    couch.navigate('accept')
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
    assert couch.page == 'packages'
    couch.navigate('next')
    assert couch.page == 'settings'
    couch.navigate('back')
    assert couch.page == 'dashboard'


def input_and_appearance():
    window = app.window
    couch = window.couch
    game = couch.game
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
    window.games = games
    couch.refresh()


steps = [
    setup,
    lambda: capture('couch-dashboard-1280.png'),
    lambda: app.window.couch.navigate('accept'),
    lambda: capture('couch-game-1280.png'),
    lambda: app.window.couch.open('presets'),
    lambda: capture('couch-presets-1280.png'),
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
    lambda: capture('couch-presets-800.png'),
    input_and_appearance,
]


def step():
    try:
        if steps:
            steps.pop(0)()
            GLib.timeout_add(550, step)
        else:
            (ROOT / 'dist/ui-couch-review.json').write_text(json.dumps({'game_writes': False, 'screenshots': captured, 'checked': ['grid navigation', 'list navigation', 'return selection', 'view cycling', 'Classic shared preference', 'last-row scrolling', 'page tabs', 'shared accent and artwork', 'input switching', 'empty library']}, indent=2))
            app.quit()
    except Exception:
        traceback.print_exc()
        app.exit_code = 1
        app.quit()
    return False


GLib.timeout_add(1800, step)
result = app.run([sys.argv[0]])
raise SystemExit(app.exit_code or result)
