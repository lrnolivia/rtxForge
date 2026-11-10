"""Prefilled character detail for a verified Feeder NR installation."""
from __future__ import annotations

import configparser
import math

import cross_os
import engine_bridge
import feeder_provider as feeder
from operation_session import LIVE, Session
import transactions as t

SECTION = 'RenoDX.DLSS5'
# Matches the starter Skin detail value in the in-game Pass 2 controls.
STARTER_SKIN = 0.5


def _settings(passes, skin):
    return {'feature_controls': {'passes': passes, 'pass2_inherit': 0, 'pass2_skin': skin}}


def _read(e, row):
    root, exe, directory = feeder.target(row)
    record = feeder.state(e, directory)
    legacy = (record or {}).get('legacy_recipe')
    if record is None:
        shared = cross_os.read(directory) or {}
        provider = shared.get('provider')
        t.need(cross_os.THIS_OS == 'linux' and isinstance(provider, dict) and provider.get('id') == 'feeder'
               and not shared.get('legacy_recipe'),
               'Install or recognize Feeder NR to save the character pass here.')
    else:
        t.need(record.get('status') == 'active', 'Restore or repair the Feeder installation first.')
    feeder.inspect(e, row)
    runtime = directory
    if legacy:
        import feeder_legacy
        runtime = feeder_legacy.runtime(directory, legacy)
    path = t.safe(runtime / 'ReShade.ini')
    t.need(path.is_file() and path.stat().st_size <= 256 * 1024, 'Repair Feeder NR to restore ReShade.ini.')
    raw = path.read_bytes()
    text = raw.decode('utf-8-sig')
    parsed = t.ini(text)

    passes = parsed.getint(SECTION, 'NRPasses', fallback=1)
    t.need(1 <= passes <= 4, 'Check the saved Passes value in the Feeder NR panel.')
    inherit = parsed.getboolean(SECTION, 'NRPass2FollowPass1', fallback=True)
    skin = parsed.getfloat(SECTION, 'NRPass2Skin', fallback=None)
    if skin is not None:
        t.need(math.isfinite(skin) and -1 <= skin <= 1, 'Check the saved Skin detail in the Feeder NR panel.')
    proposed = STARTER_SKIN if skin is None or inherit and skin == -1 else skin
    # Bind the button to the displayed settings and the exact game executable.
    stamp = t.sha(f'{exe}\n{path}\n{t.sha(raw)}'.encode())
    return root, path, raw, text, {
        'available': True, 'stamp': stamp, 'passes': passes, 'target_passes': max(2, passes),
        'inherit': inherit, 'skin': skin, 'target_skin': proposed,
        'nr_enabled': parsed.getboolean(SECTION, 'NeuralUplift', fallback=False),
        'changes': bool(feeder.tuning_changes(text, _settings(max(2, passes), proposed))),
    }


def snapshot(config, row):
    try:
        e = engine_bridge.module(config)
        root, _, _, _, result = _read(e, row)
        if row.get('anti_cheat'):
            result['reason'] = 'Use the in-game Feeder NR panel for this installation.'
        elif feeder.running_under(e, root):
            result['reason'] = 'Close the game and reopen Tools to save these settings for its next launch.'
        return result
    except (RuntimeError, OSError, ValueError, KeyError, TypeError, configparser.Error) as error:
        return {'available': False, 'reason': str(error)}


def apply(config, row, stamp, skin):
    t.need(type(skin) in (int, float) and math.isfinite(skin) and -1 <= skin <= 1,
           'Choose Skin detail between −1.00 and 1.00.')
    e = engine_bridge.module(config)
    with e.mutation_lock():
        root, path, raw, text, values = _read(e, row)
        t.need(stamp == values['stamp'], 'Feeder settings changed. Refresh the setup before applying again.')
        t.need(not row.get('anti_cheat') and e.scan_game_files(root)[2] is None,
               'Use the in-game Feeder NR panel for this installation.')
        t.need(not feeder.running_under(e, root), 'Close the game before saving character detail.')
        changed = feeder.apply_tuning(text, _settings(values['target_passes'], skin))
        if changed == text:
            return {'message': 'The saved Pass 2 settings are already in use.'}
        data = changed.encode('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8')

        session = Session(e.STATE_ROOT / 'desktop-operations')
        try:
            checkpoint = session.capture([path], label=row['name'])
            t.need(t.digest(path) == t.sha(raw), 'Feeder settings changed. Refresh the setup before applying again.')
            t.need(not feeder.running_under(e, root), 'Close the game before saving character detail.')
            try:
                t.atomic_file(path, data, path.stat().st_mode & 0o777)
                t.need(t.digest(path) == t.sha(data), 'Could not verify the saved Pass 2 settings.')
            except BaseException:
                session.seal(checkpoint)
                # Restore only our own write. Keep external changes and the recovery copy.
                if path.is_file() and t.digest(path) == t.sha(data):
                    session.undo(checkpoint)
                session.close('failed')
                raise
            session.seal(checkpoint)
            session.complete()
        finally:
            LIVE.discard(str(session.root))
    return {'message': 'Character detail saved for the next launch.'}
