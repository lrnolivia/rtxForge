"""Validated overlay preferences shared by reviews, helpers and per-game editors."""
import os
from pathlib import Path
import overlay_policy
import proton_overlay
import transactions as t

POSITIONS = ('top-center', 'top-left', 'top-right', 'bottom-left', 'bottom-right')
DEFAULTS = dict(overlay_policy.DEFAULTS, optiscaler_hotkey='Insert', overlay_renderer='game',
                overlay_controls='unified', overlay_theme='dark', overlay_live_stats=True, overlay_welcome=True,
                overlay_welcome_position='top-center', panel_hotkey='Delete', vulkan_mfg_native_menu=False)
ENUMS = {'optiscaler_hotkey': ('Insert', 'F8', 'Disabled'), 'overlay_renderer': ('game', 'optiscaler'),
         'overlay_controls': ('unified', 'classic'), 'overlay_theme': ('dark', 'light', 'app'), 'overlay_welcome_position': POSITIONS}


def options(values):
    t.need(isinstance(values, dict), 'Choose overlay settings.')
    result = {key: values.get(key, default) for key, default in DEFAULTS.items()}
    for key, default in DEFAULTS.items():
        if type(default) is bool:
            t.need(type(result[key]) is bool, 'Choose on or off for ' + key.replace('_', ' ') + '.')
    for key, choices in ENUMS.items():
        t.need(result[key] in choices, 'Choose a supported ' + key.replace('_', ' ') + '.')
    t.need(isinstance(result['panel_hotkey'], str), 'Choose an overlay shortcut.')
    proton_overlay.parse_shortcut(result['panel_hotkey'])
    return result


def effective(settings, game=None):
    values = options(settings)
    overrides = settings.get('game_overlay_settings', {})
    t.need(isinstance(overrides, dict) and len(overrides) <= 1000, 'Per-game overlay settings need review.')
    if game is not None:
        identity = os.path.normcase(str(Path(game).resolve()))
        for path, override in overrides.items():
            t.need(isinstance(path, str) and isinstance(override, dict), 'Invalid per-game overlay settings.')
            if os.path.normcase(str(Path(path).resolve())) == identity:
                t.need(set(override) <= set(DEFAULTS) - {'overlay_renderer'}, 'Unknown per-game overlay option. The primary overlay is an app-wide choice.')
                values = options(values | override)
                break
    return values


def describe(values):
    values = options(values)
    state = lambda key: 'On' if values[key] else 'Off'
    return '\n'.join((
        'Overlay: ' + ('rtxForge' if values['overlay_renderer'] == 'game' else 'Native'),
        'Controls: ' + ('Advanced' if values['overlay_controls'] == 'classic' else 'Unified'),
        'Appearance: ' + ('Follow app' if values['overlay_theme'] == 'app' else values['overlay_theme'].capitalize()),
        'Live feature statistics: ' + state('overlay_live_stats'),
        'Welcome message: ' + state('overlay_welcome'),
        'Welcome position: ' + values['overlay_welcome_position'].replace('-', ' ').capitalize(),
        'rtxForge shortcut: ' + values['panel_hotkey'],
        'OptiScaler menu: ' + state('optiscaler_ui'),
        'OptiScaler intro: ' + state('optiscaler_intro'),
        'OptiScaler shortcut: ' + values['optiscaler_hotkey'],
        'ReShade menu: ' + state('reshade_ui'),
        'ReShade welcome: ' + state('reshade_intro'),
        'Native Vulkan MFG menu: ' + state('vulkan_mfg_native_menu'),
    ))
