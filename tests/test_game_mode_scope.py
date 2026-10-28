"""Game Mode targets the right games for each operation; no display server needed."""
from pathlib import Path
from types import SimpleNamespace
import sys, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gui'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
import game_mode


class Harness:
    """GameMode's targeting methods on a stub, without building widgets."""
    run_operation = game_mode.GameMode.run_operation
    filtered_games = game_mode.GameMode.filtered_games
    selected_games = game_mode.GameMode.selected_games
    scoped_targets = game_mode.GameMode.scoped_targets
    select_all_visible = game_mode.GameMode.select_all_visible
    activate_game = game_mode.GameMode.activate_game
    apply_presets = game_mode.GameMode.apply_presets

    def __init__(self):
        self.games = [
            {'game': 'a', 'name': 'A', 'installed': True},
            {'game': 'b', 'name': 'B', 'installed': True},
            {'game': 'c', 'name': 'C', 'installed': False},
            {'game': 'd', 'name': 'D', 'installed': True, 'blocked': 'protected'},
            {'game': 'w', 'name': 'W', 'installed': True, 'installed_on': 'windows'},
        ]
        self.calls, self.toasts, self.asked = [], [], []
        self.owner = SimpleNamespace(
            games=self.games, busy=False, task_kind='', options=SimpleNamespace(demo=True),
            settings={'library_filter': 'available', 'nr_strength': 1.0, 'mfg_multiplier': 3, 'sharpening_strength': .2},
            needs_linux_setup=lambda g: g.get('installed_on') == 'windows',
            launch_action=lambda op, **kwargs: self.calls.append((op, kwargs)),
            update_dlss_games=lambda games: self.calls.append(('update-dlss', {'targets': games})))
        self.selecting, self.selected = False, set()
        self.preset_value = None

    def toast(self, text): self.toasts.append(text)
    def render(self, *args, **kwargs): pass
    def open_details(self, game): self.calls.append(('details', game))
    def ask_presets(self, targets, proceed): self.asked.append(targets)
    def save_presets(self): pass

    def names(self, index=-1):
        return [g['game'] for g in self.calls[index][1]['targets']]


class GameModeScopeTest(unittest.TestCase):
    def test_install_asks_for_presets_and_skips_blocked_games(self):
        h = Harness()
        h.run_operation('install')
        # As Windows LibraryScope: Available is games without managed features.
        self.assertEqual([g['game'] for g in h.asked[-1]], ['c'])
        h.owner.settings['library_filter'] = 'all'
        h.run_operation('install')
        self.assertEqual([g['game'] for g in h.asked[-1]], ['a', 'b', 'c', 'w'])
        self.assertEqual(h.calls, [], 'nothing runs before the presets step')

    def test_windows_installs_skip_the_presets_step(self):
        h = Harness()
        h.run_operation('install', [h.games[4]])
        self.assertEqual(h.asked, [])
        self.assertEqual(h.calls[-1][0], 'install')
        self.assertTrue(h.calls[-1][1]['_presets_confirmed'])

    def test_restore_targets_installed_games_in_the_current_filter(self):
        h = Harness()
        h.run_operation('uninstall')
        self.assertEqual((h.calls, h.toasts), ([], ['No eligible games.']), 'Available shows no installed games')
        h.owner.settings['library_filter'] = 'installed'
        h.run_operation('uninstall')
        self.assertEqual(h.names(), ['a', 'b', 'd', 'w'])
        h.owner.settings['library_filter'] = 'all'
        h.run_operation('uninstall')
        self.assertEqual(h.names(), ['a', 'b', 'd', 'w'])

    def test_explicit_selection_wins_over_the_filter(self):
        h = Harness()
        h.selecting, h.selected = True, {'b'}
        h.run_operation('uninstall', [g for g in h.scoped_targets() if g.get('installed')])
        self.assertEqual(h.names(), ['b'])

    def test_stale_or_empty_selection_never_expands_to_the_library(self):
        for selected in (set(), {'gone'}):
            h = Harness()
            h.selecting, h.selected = True, selected
            self.assertEqual(h.scoped_targets(), [])
            h.run_operation('install', h.scoped_targets())
            self.assertEqual((h.calls, h.asked), ([], []))

    def test_update_dlss_goes_through_its_own_review(self):
        h = Harness()
        h.owner.settings['library_filter'] = 'all'
        h.run_operation('update-dlss')
        self.assertEqual(h.calls[-1][0], 'update-dlss')
        self.assertEqual(h.names(), ['a', 'b', 'c', 'w'], 'blocked D is skipped')

    def test_presets_apply_with_the_chosen_values(self):
        h = Harness()
        h.owner.settings.update(nr_strength=0.7)
        h.apply_presets([h.games[0], h.games[1]])
        op, kwargs = h.calls[-1]
        self.assertEqual(op, 'reset')
        self.assertEqual(h.names(), ['a', 'b'])
        self.assertEqual(kwargs['visual_settings']['nr_strength'], 0.7)

    def test_selection_never_takes_blocked_games(self):
        h = Harness()
        h.owner.settings['library_filter'] = 'all'
        h.selecting = True
        h.activate_game(h.games[3])
        self.assertEqual(h.selected, set())
        h.select_all_visible()
        self.assertEqual(h.selected, {'a', 'b', 'c', 'w'})
        h.run_operation('uninstall', [g for g in h.selected_games() if g.get('installed')])
        self.assertEqual(h.names(), ['a', 'b', 'w'])

    def test_activating_a_game_outside_selection_opens_details(self):
        h = Harness()
        h.activate_game(h.games[0])
        self.assertEqual(h.calls[-1], ('details', h.games[0]))

    def test_busy_and_empty_operations_explain_themselves(self):
        h = Harness()
        h.owner.busy = True
        h.run_operation('install')
        h.owner.busy = False
        h.run_operation('uninstall', [])
        self.assertEqual(h.toasts, ['Another operation is running.', 'No eligible games.'])
        self.assertEqual(h.calls, [])


if __name__ == '__main__':
    unittest.main()
