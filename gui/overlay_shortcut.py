"""In-game panel shortcut: GTK key events -> the Windows key names rtxForge stores.

The panel reads the shortcut inside the game (OptiScaler's input hook), so
Linux only records the choice. Names match OverlayShortcut on Windows and the
Proton host, e.g. 'Delete', 'Backtick', 'Ctrl+Shift+P'.
"""

DEFAULT = 'Delete'
# Native tools own these keys (OptiScaler menu, its frame generation and FPS keys).
RESERVED = {'Insert': 'OptiScaler menu', 'PageUp': 'OptiScaler FPS overlay', 'PageDown': 'OptiScaler FPS overlay'}

_GDK = {
    'Delete': 'Delete', 'End': 'End', 'Home': 'Home', 'Page_Up': 'PageUp', 'Page_Down': 'PageDown',
    'Left': 'Left', 'Up': 'Up', 'Right': 'Right', 'Down': 'Down', 'Pause': 'Pause', 'Scroll_Lock': 'ScrollLock',
    'BackSpace': 'Backspace', 'Return': 'Enter', 'space': 'Space', 'Insert': 'Insert',
    'KP_Multiply': 'NumMultiply', 'KP_Add': 'NumAdd', 'KP_Subtract': 'NumSubtract', 'KP_Decimal': 'NumDecimal',
    'KP_Divide': 'NumDivide', 'semicolon': 'Semicolon', 'equal': 'Equals', 'comma': 'Comma', 'minus': 'Minus',
    'period': 'Period', 'slash': 'Slash', 'grave': 'Backtick', 'asciitilde': 'Backtick', 'bracketleft': 'LeftBracket',
    'backslash': 'Backslash', 'bracketright': 'RightBracket', 'apostrophe': 'Quote',
}
_GDK.update({'KP_%d' % n: 'Num%d' % n for n in range(10)})
_GDK.update({'F%d' % n: 'F%d' % n for n in range(1, 25) if n != 12})
_MODIFIER_NAMES = {'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Shift_L', 'Shift_R', 'Super_L', 'Super_R', 'Meta_L', 'Meta_R', 'ISO_Level3_Shift'}


class ShortcutError(ValueError):
    pass


def key_name(gdk_name):
    """Windows key name for a GDK keyval name, or None while only a modifier is held."""
    if gdk_name in _MODIFIER_NAMES:
        return None
    if len(gdk_name) == 1 and gdk_name.isalnum():
        return gdk_name.upper()
    name = _GDK.get(gdk_name)
    if name is None:
        raise ShortcutError('That key can’t be used. Choose another key.')
    return name


def compose(gdk_name, ctrl=False, alt=False, shift=False):
    """Return the stored shortcut text, or None until a non-modifier key is pressed."""
    name = key_name(gdk_name)
    if name is None:
        return None
    if not (ctrl or alt or shift) and name in RESERVED:
        raise ShortcutError(f'{name} opens the {RESERVED[name]}. Choose another key.')
    if alt and name in ('F4', 'Space') or ctrl and alt and name == 'Delete':
        raise ShortcutError('That shortcut belongs to the system. Choose another shortcut.')
    return ('Ctrl+' if ctrl else '') + ('Alt+' if alt else '') + ('Shift+' if shift else '') + name


def display(value):
    value = (value or DEFAULT).strip()
    if value.casefold() == 'disabled':
        return 'Disabled'
    return value.replace('Backtick', '` (Backtick)')
