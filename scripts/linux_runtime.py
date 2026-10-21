"""Linux runtime API for the GTK app: Proton readiness, panel preferences and MFG observations.

Every function takes a library row ({'game', 'exe', 'appid', 'name', ...}) and
returns plain JSON-able data. Nothing here launches a game or changes Steam.
Writes (overlay_apply / overlay_restore) are reviewed first and refuse a busy
prefix or a registry that changed since review.
"""
from pathlib import Path
import importlib
import sys

import proton_mfg
import proton_overlay
import proton_prefix
import proton_stack


def _prefix(row):
    try:
        return proton_prefix.find_prefix(row['game'], row.get('appid'))
    except proton_prefix.PrefixError:
        return None


def _target(row):
    return (Path(row['game']) / row['exe']).parent if row.get('exe') else Path(row['game'])


def proton_report(row, mode='nr-mfg', launch_options=''):
    """Read-only readiness of this game's Proton setup for native NR/MFG (see proton_stack.REASONS)."""
    report = proton_stack.detect(_prefix(row), mode, launch_options,
                                 native_dlssg=row.get('native_dlssg') if mode != 'nr-only' else None)
    report['user_reasons'] = [proton_stack.REASONS[code] for code in report['reasons']]
    return report


def overlay_state(e, row):
    return e.STATE_ROOT / 'prefix-overlay' / e.target_key(_target(row))


def overlay_review(row, settings, accent=None):
    """What Settings → Overlay would write into this game's prefix (nothing is written)."""
    prefix = _prefix(row)
    if prefix is None:
        raise proton_overlay.OverlayError('This game has not been started with Proton yet. Play it once, quit, then try again.')
    exe = Path(row['game']) / row['exe'] if row.get('exe') else None
    return proton_overlay.plan(prefix, settings, exe, row.get('name'), accent)


def overlay_apply(e, row, reviewed):
    return proton_overlay.apply(reviewed, overlay_state(e, row))


def overlay_restore(e, row):
    return proton_overlay.restore(overlay_state(e, row))


def mfg_observation(row):
    """What the Universal plugin wrote on its last run. Observation only; never verification."""
    return proton_mfg.runtime_report(_target(row))


def record_runtime_evidence(e, row, report, observed, confirmed_by):
    """Store a human-confirmed real in-game session for this exact game/Proton build/GPU/component."""
    component = report.get('component') or {}
    return proton_stack.record_evidence(e.STATE_ROOT / 'proton-evidence', row.get('appid'), report['tool']['version'],
                                        (report.get('gpu') or {}).get('model'),
                                        f"{component.get('id', 'nr-only')}-{component.get('version', '')}".rstrip('-'),
                                        observed, confirmed_by)


# --- One-time Global review and game-menu review (shared with Windows) -----------------------

HOST = Path(__file__).resolve().parents[1] / 'windows' / 'engine-host'


def _shared(name):
    """The reviewed bulk modules the Windows host uses. They are platform-neutral Python
    over the same engine records; appended to the path so scripts/ always wins on names."""
    if str(HOST) not in sys.path:
        sys.path.append(str(HOST))
    return importlib.import_module(name)


def global_review(e, params):
    """ONE-TIME reviewed NR on/off and MFG (-1 auto, 0 off, 2..6) for installed packages.

    Never a persistent override: each game's INI changes once, with running,
    anti-cheat, drift and ownership checks; Feeder games take NR only.
    """
    return _shared('global_controls').prepare(e, e.STATE_ROOT, params)


def menus_review(e, params):
    """Reviewed OptiScaler/ReShade menu and intro changes for installed games (config only)."""
    return _shared('overlay_ui').prepare(e, params)


def apply_review(review):
    """Apply a global_review or menus_review result; every file is re-checked first."""
    return _shared('global_controls').execute(review)
