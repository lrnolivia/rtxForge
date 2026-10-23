"""Cross-platform Game Mode design values and independent theme preferences."""
import json
from pathlib import Path

MOTION = json.loads((Path(__file__).resolve().parents[1] / 'assets' / 'game-mode' / 'motion.json').read_text(encoding='utf-8'))
THEME_LINK_LABEL = 'Use the same color theme in Desktop and Game Mode'


def scroll_fade(height, offset, extent, unit=1):
    """Viewport alpha profile; real content boundaries remain fully visible."""
    depth = max(0, min(MOTION['scroll_fade_depth'] * unit, height * MOTION['scroll_fade_ratio']))
    ramp = max(1, MOTION['scroll_fade_ramp'] * unit)
    top = min(1, max(0, offset / ramp))
    bottom = min(1, max(0, (extent - offset) / ramp))
    return depth, top, bottom


def scroll_fade_alpha(position, height, depth, top, bottom):
    if depth <= 0:
        return 1.0
    def smooth(value):
        x = min(1, max(0, value))
        return x * x * x * (x * (x * 6 - 15) + 10)
    return ((1 - top * (1 - smooth(position / depth)))
            * (1 - bottom * (1 - smooth((height - position) / depth))))


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
