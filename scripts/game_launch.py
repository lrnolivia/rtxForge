"""Resolve an installed game's existing launcher without changing its configuration."""
from pathlib import Path
from types import SimpleNamespace
import engine_bridge


def steam_uri(appid, *, shortcut=False):
    try:
        value = int(str(appid))
    except (TypeError, ValueError):
        raise ValueError('This game has no valid Steam launch ID.') from None
    if shortcut:
        if not -(2**31) <= value < 2**32:
            raise ValueError('This shortcut has an invalid Steam launch ID.')
        value = ((value & 0xffffffff) << 32) | 0x02000000
    elif not 0 < value < 2**32:
        raise ValueError('This game has an invalid Steam launch ID.')
    return f'steam://rungameid/{value}'


def resolve(config, row, *, engine=None):
    """Use Steam's recorded shortcut, preserving its Proton version and launch flags.

    Store-enrichment IDs are never used to launch a non-Steam installation.
    Unknown launchers and ambiguous accounts fail explicitly rather than running
    a Windows executable with a guessed prefix or command.
    """
    if row.get('source') == 'Steam':
        return steam_uri(row.get('appid'))
    e = engine if engine is not None else engine_bridge.module(config)
    root = Path(row['game']).expanduser().resolve()
    executable = (root / row.get('exe', '')).resolve()
    if not executable.is_relative_to(root) or executable == root:
        raise ValueError('Refresh this game’s executable before launching it.')
    game = SimpleNamespace(root=root, exe=executable, name=row['name'], appid=None)
    account = e.choose_steam_user_config([game], assume_yes=True)
    if not account or not Path(account['shortcuts']).is_file():
        raise ValueError('No configured launcher was found for this game. Add its existing launcher to Steam, then try Play again.')
    shortcuts = e.parse_shortcuts_spans(Path(account['shortcuts']).read_bytes())
    match = e.match_shortcut_span(game, shortcuts)
    if match is None:
        raise ValueError('No unique Steam shortcut matches this installation. Check the shortcut’s executable path, then try Play again.')
    return steam_uri(e._shortcut_int(match, 'appid'), shortcut=True)
