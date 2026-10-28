"""Controller button prompts shared with Windows (GameMode/ControllerPrompt.cs).

Physical positions match the gamepad actions, including Nintendo's labels.
Each prompt is (label, color, shape); shape 'text' draws the label.
"""

INK = '#e6e8eb'


def prompt(family, action):
    face = {'accept': 0, 'back': 1, 'select': 2, 'search': 3}.get(action, -1)
    if face >= 0:
        if family == 'playstation':
            return (('Cross', 'Circle', 'Square', 'Triangle')[face],
                    ('#72baff', '#ff8187', '#ef9bc9', '#75d9b1')[face],
                    ('cross', 'circle', 'square', 'triangle')[face])
        if family == 'nintendo':
            return ('B', 'A', 'Y', 'X')[face], ('#ffe17c', '#ff8187', '#75d9b1', '#72baff')[face], 'text'
        if family == 'steam':
            return ('A', 'B', 'X', 'Y')[face], INK, 'text'
        if family == 'generic':
            return ('South', 'East', 'West', 'North')[face], INK, 'position%d' % face
        return ('A', 'B', 'X', 'Y')[face], ('#8cdb80', '#ff8187', '#72baff', '#ffe17c')[face], 'text'
    nintendo, playstation = family == 'nintendo', family == 'playstation'
    if action == 'menu':
        return ('+', INK, 'plus') if nintendo else ('Menu', INK, 'menu')
    if action == 'settings':
        return ('−', INK, 'minus') if nintendo else ('View', INK, 'view')
    if action == 'previous':
        return ('L1' if playstation else 'L' if nintendo else 'LB'), INK, 'shoulder'
    if action == 'next':
        return ('R1' if playstation else 'R' if nintendo else 'RB'), INK, 'shoulder'
    if action in ('move', 'adjust'):
        return 'D-pad', INK, 'dpad'
    return 'Menu', INK, 'menu'


# Windows ControllerNavigation: rescale outside the deadzone so slow scrolling
# starts without a jump; 1100 px/s at full tilt, frames capped at 50 ms.
DEADZONE = .18


def scroll_delta(axis, seconds):
    """Pixels to scroll for a right-stick Y reading in -1..1 (SDL: negative is up)."""
    try:
        axis, seconds = float(axis), float(seconds)
    except (TypeError, ValueError):
        return 0.0
    if axis != axis or seconds != seconds or abs(axis) == float('inf') or abs(seconds) == float('inf'):
        return 0.0
    strength = (min(abs(axis), 1.0) - DEADZONE) / (1 - DEADZONE)
    if strength <= 0:
        return 0.0
    return (1 if axis > 0 else -1) * strength * 1100 * min(max(seconds, 0.0), .05)
