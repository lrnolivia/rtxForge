"""Validated overlay preferences shared by reviews, helpers and per-game editors."""
import os
from pathlib import Path
import overlay_policy
import proton_overlay
import transactions as t

POSITIONS = ('top-center', 'top-left', 'top-right', 'bottom-left', 'bottom-right')
DEFAULTS = dict(overlay_policy.DEFAULTS, optiscaler_hotkey='Insert', overlay_renderer='game',
                overlay_controls='unified', overlay_theme='clear', overlay_live_stats=True, overlay_welcome=True,
                overlay_welcome_position='top-center', panel_hotkey='Delete', vulkan_mfg_native_menu=False, overlay_appearance={})
ENUMS = {'optiscaler_hotkey': ('Insert', 'F8', 'Disabled'), 'overlay_renderer': ('game', 'optiscaler'),
         'overlay_controls': ('unified', 'classic'), 'overlay_theme': ('clear', 'dark', 'light', 'accent', 'app'), 'overlay_welcome_position': POSITIONS}


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
    import glass_preferences
    result['overlay_appearance'] = glass_preferences.validate(result['overlay_appearance'])
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


def game_edit(settings, game, key, value):
    """Overlay-originated writes never replace app-wide defaults."""
    t.need(key in DEFAULTS and key != 'overlay_renderer', 'Change app defaults in Desktop or Game Mode settings.')
    identity=str(Path(game).resolve())
    result=effective(settings,game) | {key:value}
    options(result)
    mapping={path:dict(values) for path,values in settings.get('game_overlay_settings',{}).items()}
    matching=next((path for path in mapping if os.path.normcase(str(Path(path).resolve()))==os.path.normcase(identity)),identity)
    mapping.setdefault(matching,{})[key]=value
    return mapping


def shortcut_binding(value):
    """Translate the renderer's validated virtual-key binding into shared preferences."""
    t.need(isinstance(value,dict) and type(value.get('key')) is int and type(value.get('modifiers')) is int,'Choose an overlay shortcut.')
    key,modifiers=value['key'],value['modifiers']
    t.need(0<=modifiers<=7,'Choose supported shortcut modifiers.')
    if key==0 and modifiers==0:return 'panel_hotkey','Disabled'
    name=next((name for name,code in proton_overlay._KEYS.items() if code==key),None)
    t.need(name is not None,'Choose a supported overlay shortcut.')
    text=('Ctrl+' if modifiers&2 else '')+('Alt+' if modifiers&1 else '')+('Shift+' if modifiers&4 else '')+name
    return 'panel_hotkey',proton_overlay.parse_shortcut(text)[0]
