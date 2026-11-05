"""Validated overlay preferences shared by reviews, helpers and per-game editors."""
import os
import configparser
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
                t.need(set(override) <= set(DEFAULTS), 'Unknown per-game overlay option.')
                merged=values | override
                merged['overlay_appearance']=values['overlay_appearance'] | override.get('overlay_appearance',{})
                values = options(merged)
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
    t.need(key in DEFAULTS, 'Change app defaults in Desktop or Game Mode settings.')
    identity=str(Path(game).resolve())
    result=effective(settings,game) | {key:value}
    options(result)
    mapping={path:dict(values) for path,values in settings.get('game_overlay_settings',{}).items()}
    matching=next((path for path in mapping if os.path.normcase(str(Path(path).resolve()))==os.path.normcase(identity)),identity)
    mapping.setdefault(matching,{})[key]=value
    return mapping


# Per-game choices that are not the overlay's look; Apply Globally leaves them as each game has them
# (matches GlassAppearance.ControlKeys on Windows).
CONTROL_KEYS = ('TextSize', 'Scale', 'ScaleBaseline', 'OriginalLabels', 'Motion', 'ShowNotifications', 'ToastPill')


def apply_style_globally(settings, appearance, theme):
    """Settings with one overlay style everywhere: the defaults and every game's saved appearance.

    appearance is the style being applied (the defaults, or one game's); theme is its overlay_theme.
    Each game keeps its text size, motion, notifications, menus and shortcuts."""
    import glass_preferences
    style = {key: value for key, value in glass_preferences.validate(appearance).items() if key not in CONTROL_KEYS}
    t.need(theme in ENUMS['overlay_theme'], 'Choose a supported overlay theme.')
    result = dict(settings)
    result['overlay_appearance'] = dict(settings.get('overlay_appearance') or {}) | style
    result['overlay_theme'] = theme
    games = {}
    for path, values in (settings.get('game_overlay_settings') or {}).items():
        values = dict(values)
        if isinstance(values.get('overlay_appearance'), dict):
            values['overlay_appearance'] = values['overlay_appearance'] | style
        if 'overlay_theme' in values:
            values['overlay_theme'] = theme
        games[path] = values
    result['game_overlay_settings'] = games
    options(result)
    return result


def native_overlays(settings, game, global_default=False):
    """An explicit onboarding opt-out; other games keep their overrides."""
    t.need(type(global_default) is bool, 'Choose whether to change the default.')
    changes={'overlay_renderer':'optiscaler','optiscaler_ui':True,'reshade_ui':True}
    mapping=game_edit(settings,game,'overlay_renderer','optiscaler')
    current=settings | {'game_overlay_settings':mapping}
    for key,value in changes.items():
        mapping=game_edit(current,game,key,value)
        current['game_overlay_settings']=mapping
    if effective(current,game)['optiscaler_hotkey']=='Disabled':
        current['game_overlay_settings']=game_edit(current,game,'optiscaler_hotkey','Insert')
    if global_default:
        current.update(changes)
        if current.get('optiscaler_hotkey')=='Disabled':current['optiscaler_hotkey']='Insert'
    return current


def native_shortcuts(settings, game, exe=''):
    """Read the installed native menu keys, without changing a game file."""
    root=Path(game).resolve();folder=(root/exe).resolve().parent if exe else root
    if not folder.is_relative_to(root):folder=root
    result=[]
    names={code:name for name,code in proton_overlay._KEYS.items()}
    names[45]='Insert'
    def key_name(key,mods=()):return '+'.join([name for name,on in mods if on]+[names.get(key,hex(key))])
    for name,filename,section,key in [('OptiScaler','OptiScaler.ini','Menu','ShortcutKey'),('ReShade','ReShade.ini','INPUT','KeyOverlay')]:
        path=next((base/filename for base in (folder,folder/'OptiScaler',root) if (base/filename).is_file()),None)
        if path is None:continue
        try:
            if path.stat().st_size>256*1024:continue
            parser=t.ini(path.read_text(encoding='utf-8-sig',errors='replace'))
            raw=parser.get(section,key,fallback='0x2D' if name=='OptiScaler' else '36,0,0,0')
            if name=='OptiScaler' and 'overlay_renderer' in settings:raw={'Insert':'0x2D','F8':'0x77','Disabled':'0'}.get(settings.get('optiscaler_hotkey','Insert'),'0x2D')
            parts=[part.strip() for part in raw.split(',')]
            code=int(parts[0],16 if parts[0].lower().startswith('0x') else 10)
            mods=list(zip(('Ctrl','Shift','Alt'),[part=='1' for part in parts[1:4]])) if name=='ReShade' else []
            enabled=code!=0 and settings.get('optiscaler_ui' if name=='OptiScaler' else 'reshade_ui',True)
            if name=='ReShade' and code==0:
                saved=parser.get('rtxForge.UI','ReShadeShortcut',fallback='36,0,0,0').split(',')
                code=int(saved[0]);mods=list(zip(('Ctrl','Shift','Alt'),[part.strip()=='1' for part in saved[1:4]]))
            if not 0<=code<=255:continue
            result.append({'name':name,'key':key_name(code if code else 45 if name=='OptiScaler' else 36,mods),'enabled':enabled})
        except (OSError,ValueError,KeyError,configparser.Error,t.Refusal):continue
    return result


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
