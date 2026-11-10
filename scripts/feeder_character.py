"""Character mask assignment for a verified Feeder NR installation."""
from __future__ import annotations

import configparser
import math

import cross_os
import engine_bridge
import feeder_provider as feeder
from operation_session import LIVE, Session
import transactions as t

SECTION = 'RenoDX.DLSS5'
MAX_PASSES = 4
STOCK_SKIN = -1.0


def _skin_value(value):
    return STOCK_SKIN if value < 0 else value


def _pass_options(parsed):
    options = []
    for number in range(1, MAX_PASSES + 1):
        prefix = f'NRPass{number}'
        inherited = number > 1 and parsed.getboolean(SECTION, prefix + 'FollowPass1', fallback=True)
        main = number == 1 or inherited
        mask_key = 'NRAutoMask' if main else prefix + 'AutoMask'
        skin_key = 'NRSkinStructure' if main else prefix + 'Skin'
        skin = parsed.getfloat(SECTION, skin_key, fallback=STOCK_SKIN)
        t.need(math.isfinite(skin) and -1 <= skin <= 1, 'Check the saved Skin detail in the Feeder NR panel.')
        options.append({'number': number, 'inherited': inherited,
                        'character': parsed.getboolean(SECTION, mask_key, fallback=False),
                        'skin': _skin_value(skin)})
    return options


def _apply_role(text, values, number, character, skin):
    option = values['options'][number - 1]
    changes = {}
    if values['passes'] < number:
        changes['NRPasses'] = str(number)
    if character == option['character'] and skin == option['skin']:
        return t.setvalue(text, SECTION, 'NRPasses', changes['NRPasses']) if changes else text

    prefix = 'NR' if number == 1 else f'NRPass{number}'
    skin_key = 'NRSkinStructure' if number == 1 else prefix + 'Skin'
    if option['inherited']:
        # Copy the active main settings before detaching this pass. Intensity,
        # transfer and color already belong to the selected pass.
        parsed = t.ini(text)
        changes[prefix + 'Style'] = str(parsed.getint(SECTION, 'NRStyle', fallback=0))
        for suffix, main_key, default in (
                ('LocalTone', 'NRLocalTone', 1.0),
                ('Structure', 'NRLocalStructure', 1.0)):
            value = parsed.getfloat(SECTION, main_key, fallback=default)
            t.need(math.isfinite(value), 'Check the main pass settings in the Feeder NR panel.')
            changes[prefix + suffix] = str(value)
        changes[prefix + 'UICorrection'] = str(int(parsed.getboolean(SECTION, 'NRUICorrection', fallback=False)))
        changes[prefix + 'FollowPass1'] = '0'
        changes[skin_key] = f'{skin:.2f}'
    elif skin != option['skin']:
        changes[skin_key] = f'{skin:.2f}'

    if option['inherited'] or character != option['character']:
        changes[prefix + 'AutoMask'] = str(int(character))
    for key, value in changes.items():
        text = t.setvalue(text, SECTION, key, value)
    return text


def _read(e, row):
    root, exe, directory = feeder.target(row)
    record = feeder.state(e, directory)
    legacy = (record or {}).get('legacy_recipe')
    if record is None:
        shared = cross_os.read(directory) or {}
        provider = shared.get('provider')
        t.need(cross_os.THIS_OS == 'linux' and isinstance(provider, dict) and provider.get('id') == 'feeder'
               and not shared.get('legacy_recipe'),
               'Install or recognize Feeder NR to assign a pass role here.')
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
    t.need(1 <= passes <= MAX_PASSES, 'Check the saved Passes value in the Feeder NR panel.')
    # Bind the review to the displayed settings and exact game executable.
    stamp = t.sha(f'{exe}\n{path}\n{t.sha(raw)}'.encode())
    return root, path, raw, text, {
        'available': True, 'stamp': stamp, 'passes': passes, 'options': _pass_options(parsed),
        'nr_enabled': parsed.getboolean(SECTION, 'NeuralUplift', fallback=False),
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


def apply(config, row, stamp, skin, pass_number=2, character=True):
    t.need(type(pass_number) is int and 1 <= pass_number <= MAX_PASSES, 'Choose a Feeder NR pass from 1 to 4.')
    t.need(type(character) is bool, 'Choose Standard or Character.')
    t.need(skin is None or (type(skin) in (int, float) and math.isfinite(skin) and -1 <= skin <= 1),
           'Choose Skin detail between −1.00 and 1.00.')
    e = engine_bridge.module(config)
    with e.mutation_lock():
        root, path, raw, text, values = _read(e, row)
        t.need(stamp == values['stamp'], 'Feeder settings changed. Refresh the setup before applying again.')
        t.need(not row.get('anti_cheat') and e.scan_game_files(root)[2] is None,
               'Use the in-game Feeder NR panel for this installation.')
        t.need(not feeder.running_under(e, root), 'Close the game before saving the pass role.')
        option = values['options'][pass_number - 1]
        target_skin = _skin_value(skin) if character and skin is not None else option['skin']
        changed = _apply_role(text, values, pass_number, character, target_skin)
        if changed == text:
            return {'message': f'Pass {pass_number} already has these settings.'}
        data = changed.encode('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8')

        session = Session(e.STATE_ROOT / 'desktop-operations')
        try:
            checkpoint = session.capture([path], label=row['name'])
            t.need(t.digest(path) == t.sha(raw), 'Feeder settings changed. Refresh the setup before applying again.')
            t.need(not feeder.running_under(e, root), 'Close the game before saving the pass role.')
            try:
                t.atomic_file(path, data, path.stat().st_mode & 0o777)
                t.need(t.digest(path) == t.sha(data), 'Could not verify the saved Feeder NR settings.')
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
    role = 'Character' if character else 'Standard'
    return {'message': f'Pass {pass_number} saved as {role} for the next launch.'}
