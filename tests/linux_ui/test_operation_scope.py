import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'gui'))
from operation_scope import ScopeError, operation_targets  # noqa: E402

GAMES = [
    {'game': 'a', 'name': 'Alan Wake 2', 'installed': True},
    {'game': 'b', 'name': 'Control', 'installed': False},
    {'game': 'c', 'name': 'Cyberpunk 2077', 'installed': True, 'blocked': True},
]


def everything(_):
    return True


class OperationScopeTest(unittest.TestCase):
    def test_selection_wins_over_view(self):
        rows = operation_targets(GAMES, {'b'}, lambda g: g['game'] == 'a')
        self.assertEqual([g['game'] for g in rows], ['b'])

    def test_no_selection_uses_current_view_only(self):
        rows = operation_targets(GAMES, set(), lambda g: 'control' in g['name'].casefold())
        self.assertEqual([g['game'] for g in rows], ['b'])

    def test_stale_selection_never_widens_to_library(self):
        with self.assertRaises(ScopeError):
            operation_targets(GAMES, {'gone'}, everything)

    def test_stale_ids_are_dropped_from_a_live_selection(self):
        rows = operation_targets(GAMES, {'gone', 'a'}, everything)
        self.assertEqual([g['game'] for g in rows], ['a'])

    def test_empty_view_refuses(self):
        with self.assertRaises(ScopeError):
            operation_targets(GAMES, set(), lambda g: False)

    def test_unfiltered_view_is_the_library(self):
        self.assertEqual(len(operation_targets(GAMES, set(), everything)), 3)


if __name__ == '__main__':
    unittest.main()
