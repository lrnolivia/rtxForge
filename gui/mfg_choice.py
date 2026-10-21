"""Multi-Frame Generation choice <-> saved preset values.

Mirrors the Windows editor: a separate On/Off switch, Auto/Custom/Dynamic
modes and 2x-6x ratios (fixed in Custom, a ceiling in Dynamic).  Turning
MFG off keeps the last mode and ratio dormant so they return on reopen.

Saved keys:
  mfg_multiplier        'auto' | 0 (off) | 2..6
  dynamic_mfg           0 | 1        (DLSSG.OverrideForceDMFG)
  mfg_saved_mode        0 Auto | 1 Custom | 2 Dynamic   (rtxForge.Presets.MfgMode)
  mfg_saved_multiplier  2..6                            (rtxForge.Presets.MfgMultiplier)
"""

AUTO, CUSTOM, DYNAMIC = 0, 1, 2
MODES = (AUTO, CUSTOM, DYNAMIC)
MODE_NAMES = ('Auto', 'Custom', 'Dynamic')
RATIOS = (2, 3, 4, 5, 6)


def _ratio(value, fallback=2):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return fallback
    return value if value in RATIOS else fallback


def from_values(values):
    """Return (enabled, mode, ratio) for a saved preset."""
    multiplier = values.get('mfg_multiplier', 'auto')
    saved_mode = values.get('mfg_saved_mode')
    saved_ratio = _ratio(values.get('mfg_saved_multiplier'))
    dynamic = bool(values.get('dynamic_mfg'))
    if multiplier in (0, '0', 'off'):
        mode = saved_mode if saved_mode in MODES else AUTO
        return False, mode, saved_ratio
    if multiplier in ('auto', None, -1, '-1'):
        return True, AUTO, saved_ratio
    ratio = _ratio(multiplier, saved_ratio)
    return True, DYNAMIC if dynamic else CUSTOM, ratio


def to_values(enabled, mode, ratio, dynamic_available=True):
    """Return the saved preset keys for a choice."""
    if mode not in MODES:
        mode = AUTO
    if mode == DYNAMIC and not dynamic_available:
        mode = CUSTOM
    ratio = _ratio(ratio)
    saved = {'mfg_saved_mode': mode, 'mfg_saved_multiplier': ratio}
    if not enabled:
        return {'mfg_multiplier': 0, 'dynamic_mfg': 0, **saved}
    if mode == AUTO:
        return {'mfg_multiplier': 'auto', 'dynamic_mfg': 0, **saved}
    return {'mfg_multiplier': ratio, 'dynamic_mfg': int(mode == DYNAMIC), **saved}


def summary(values):
    enabled, mode, ratio = from_values(values)
    if not enabled:
        return 'Off'
    if mode == AUTO:
        return 'Auto'
    return f'{ratio}×' if mode == CUSTOM else f'Dynamic up to {ratio}×'
