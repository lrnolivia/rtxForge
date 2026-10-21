"""Which games a Library-wide action may touch.

Mirrors the Windows rule: an explicit selection wins; without one, the
current filter and search limit the targets.  A selection that no longer
matches any game (stale IDs after a rescan) never widens to the library.
"""


class ScopeError(Exception):
    """The requested scope resolves to nothing the user reviewed."""


def operation_targets(games, selected_ids, matches_view):
    """Return the games an action applies to.

    games         -- every game currently in the library, in display order
    selected_ids  -- the user's explicit selection (may hold stale IDs)
    matches_view  -- callable(game) -> bool for the current filter + search
    """
    if selected_ids:
        chosen = [game for game in games if game.get('game') in selected_ids]
        if not chosen:
            raise ScopeError('The selected games are no longer in the library.')
        return chosen
    visible = [game for game in games if matches_view(game)]
    if not visible:
        raise ScopeError('No games match the current filter.')
    return visible
