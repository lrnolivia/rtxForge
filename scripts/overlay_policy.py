"""Independent game-menu and intro policy; never changes rendering settings."""
import transactions as t

DEFAULTS = {'optiscaler_ui': True, 'optiscaler_intro': False,
            'reshade_ui': True, 'reshade_intro': False}


def options(settings):
    values = {key: settings.get(key, default) for key, default in DEFAULTS.items()}
    t.need(all(type(value) is bool for value in values.values()), 'Choose on or off for each game menu and intro.')
    return values


def explicit(settings):
    return any(key in settings for key in DEFAULTS)


def _set(text, section, key, value):
    # Do not rewrite an unchanged Windows line ending or a user's spacing.
    if t.ini(text).get(section, key, fallback=None) == value: return text
    return t.setvalue(text, section, key, value)


def optiscaler(text, settings, setvalue=t.setvalue):
    values = options(settings)
    text = setvalue(text, 'Menu', 'DisableSplash', 'false' if values['optiscaler_intro'] else 'true')
    # Keep the safe legacy/swapchain choice (notably inZOI). This is menu
    # input policy, never an instruction to replace graphics hooks.
    key = settings.get('optiscaler_hotkey', 'Insert')
    t.need(key in ('Insert', 'F8', 'Disabled'), 'Choose a supported OptiScaler shortcut.')
    return setvalue(text, 'Menu', 'ShortcutKey',
                    '0' if not values['optiscaler_ui'] or key == 'Disabled' else '0x77' if key == 'F8' else '0x2D')


def reshade(text, settings):
    values = options(settings)
    parser = t.ini(text)
    # Preserve a custom shortcut while menu access is disabled. These are
    # genuine ReShade controls; never disable its effects or Feeder technique.
    current = parser.get('INPUT', 'KeyOverlay', fallback='36,0,0,0')
    saved = parser.get('rtxForge.UI', 'ReShadeShortcut', fallback=current)
    gamepad = parser.get('INPUT', 'GamepadNavigation', fallback='0')
    saved_gamepad = parser.get('rtxForge.UI', 'ReShadeGamepad', fallback=gamepad)
    was_disabled = parser.getboolean('rtxForge.UI', 'ReShadeDisabled', fallback=False)
    if not values['reshade_ui']:
        if current.split(',')[0].strip() != '0':
            text = _set(text, 'rtxForge.UI', 'ReShadeShortcut', current)
        if gamepad != '0': text = _set(text, 'rtxForge.UI', 'ReShadeGamepad', gamepad)
    restored_key = saved if was_disabled else current
    text = _set(text, 'INPUT', 'KeyOverlay', (restored_key if restored_key.split(',')[0].strip() != '0' else '36,0,0,0') if values['reshade_ui'] else '0,0,0,0')
    text = _set(text, 'INPUT', 'GamepadNavigation', (saved_gamepad if was_disabled else gamepad) if values['reshade_ui'] else '0')
    text = _set(text, 'rtxForge.UI', 'ReShadeDisabled', '0' if values['reshade_ui'] else '1')
    # Match the owner's working TS4/Mass Effect recipe. ReShade's first-run
    # guide and RenoDX's welcome dialog are distinct from its loading banner.
    text = _set(text, 'OVERLAY', 'TutorialProgress', '0' if values['reshade_intro'] else '4')
    if parser.has_section('RenoDX.DLSS5'):
        text = _set(text, 'RenoDX.DLSS5', 'UiWelcomed', '0' if values['reshade_intro'] else '1')
    return text
