"""Cross-platform Game Mode design values and independent theme preferences."""
import json
from pathlib import Path

MOTION = json.loads((Path(__file__).parent / 'game-mode' / 'motion.json').read_text(encoding='utf-8'))
THEME_LINK_LABEL = 'Use the same color theme in Desktop and Game Mode'


def theme_name(settings):
    value = settings.get('theme') if settings.get('game_mode_theme_linked', True) else settings.get('game_mode_theme')
    return value if value in ('dark', 'light', 'night') else 'night'


def link_themes(settings, linked):
    if not linked and settings.get('game_mode_theme_linked', True):
        settings['game_mode_theme'] = theme_name(settings)
    settings['game_mode_theme_linked'] = bool(linked)


def set_theme(settings, value):
    if value not in ('dark', 'light', 'night'):
        raise ValueError('Unknown color theme')
    if settings.get('game_mode_theme_linked', True):
        settings.update(theme=value, dark=value != 'light')
    else:
        settings['game_mode_theme'] = value
