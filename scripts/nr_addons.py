"""DLSS5 neural-rendering add-on choice per game: Environment and Character slots.

Each slot takes the add-on the user chooses (Lecram, ShortFuse or GITC Uplift),
one of its pinned builds, an Old or New DLSS5 model, and its settings. plan()
turns a game and a setup into what an install needs: the add-ons and model to
fetch (all pinned in providers/nr-addons.json), the ReShade.ini values to write,
whether Feeder supplies the frames, and whether this pairing has been verified.
It refuses what cannot work instead of guessing:
- ShortFuse hooks the game's own DLSS calls, so it needs a 64-bit DLSS game.
- GITC Uplift stops itself beside any other NR add-on.
- Lecram stands down beside another NR add-on unless ForeignNr=observe is set,
  so a pairing sets it.
- A setting whose key or value encoding is not verified is never written.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import transactions as t

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'providers' / 'nr-addons.json'
SLOTS = ('environment', 'character')
MODELS = ('old', 'new')
# Numeric settings and the range each accepts. Values outside are refused.
RANGES = {'intensity': (0.0, 2.0), 'local_tone': (0.0, 2.0), 'structure': (0.0, 2.0), 'character': (0.0, 2.0),
          'resolution_scale': (0.25, 1.0), 'diffuse_white_nits': (40, 400)}
SWITCHES = ('character_mask', 'independent_skin', 'ui_correction', 'block_hudless')
COUNTS = {'passes': (1, 4), 'style': (0, 2)}
# Pairings confirmed on a Forge Lab copy. Everything else is "not verified".
VERIFIED_PAIRS: set[frozenset] = set()

_catalog = None


def catalog():
    global _catalog
    if _catalog is None:
        _catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
        t.need(_catalog.get('schema') == 1, 'NR add-on catalog schema is unsupported')
    return copy.deepcopy(_catalog)


def builtin_combos():
    return catalog()['combos']


def _value(name, value):
    if name in RANGES:
        low, high = RANGES[name]
        t.need(isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high,
               f'{name.replace("_", " ").capitalize()} must be between {low} and {high}.')
        return value
    if name in SWITCHES:
        t.need(value in (0, 1, True, False), f'{name.replace("_", " ").capitalize()} must be on or off.')
        return int(bool(value))
    if name in COUNTS:
        low, high = COUNTS[name]
        t.need(type(value) is int and low <= value <= high, f'{name.capitalize()} must be {low}–{high}.')
        return value
    raise t.Refusal(f'Unknown NR setting: {name}')


def _slot(spec, slot, game):
    addons = catalog()['addons']
    t.need(isinstance(spec, dict), f'Choose an add-on for {slot}.')
    addon_id = spec.get('addon')
    t.need(addon_id in addons, f'Unknown NR add-on for {slot}: {addon_id}')
    addon = addons[addon_id]
    build_id = spec.get('build') or next(b for b, v in addon['builds'].items() if v.get('default'))
    t.need(build_id in addon['builds'], f'{addon["name"]} has no build {build_id}.')
    model = spec.get('model', 'new')
    t.need(model in MODELS, 'Choose the Old or New DLSS5 model.')
    if addon.get('needs_native_dlss'):
        t.need(game.get('native_dlss'), f'{addon["name"]} hooks the game\'s own DLSS, and this game has none.')
    if addon.get('arch'):
        t.need(game.get('arch', 'x64') in addon['arch'], f'{addon["name"]} supports 64-bit games only.')
    values, skipped = {}, []
    for name, value in (spec.get('values') or {}).items():
        value = _value(name, value)
        if addon['settings'].get(name):
            values[name] = value
        else:
            skipped.append(name)
    return {'slot': slot, 'addon': addon_id, 'build': build_id, 'model': model, 'values': values,
            'skipped': skipped, 'name': addon['name']}


# Lecram's per-pass keys (NRPass2..4<suffix>), read from the 10.8.0 add-on.
# Other add-ons' per-pass keys are not verified, so their second slot is refused.
LECRAM_PASS = {'intensity': 'Intensity', 'style': 'Style', 'local_tone': 'LocalTone', 'structure': 'Structure',
               'character': 'Skin', 'character_mask': 'AutoMask', 'ui_correction': 'UICorrection'}


def _keys(addon_id, values, pass_number=1):
    """ReShade.ini key/value pairs for one add-on pass. Only verified keys are written."""
    settings = catalog()['addons'][addon_id]['settings']
    if pass_number > 1:
        out = {f'NRPass{pass_number}FollowPass1': 0}
        out.update({f'NRPass{pass_number}{LECRAM_PASS[name]}': value for name, value in values.items() if name in LECRAM_PASS})
        return out
    return {settings[name]: value for name, value in values.items() if settings.get(name)}


def plan(game, setup):
    """What installing this setup in this game takes, or a Refusal saying why it can't."""
    t.need(isinstance(setup, dict) and setup.get('environment'), 'Choose an add-on for Environment.')
    slots = [_slot(setup['environment'], 'environment', game)]
    if setup.get('character'):
        slots.append(_slot(setup['character'], 'character', game))
    addons = catalog()['addons']
    ids = {s['addon'] for s in slots}
    for s in slots:
        if addons[s['addon']].get('exclusive') and len(ids) > 1:
            raise t.Refusal(f'{s["name"]} runs alone: it stops when another NR add-on is present. '
                            'Use it in both slots, or choose another add-on.')
    if len(slots) == 2 and slots[0]['model'] != slots[1]['model'] and len(ids) > 1:
        raise t.Refusal('Two different add-ons share one NR model file: choose the same Old or New model for both.')
    ini, install = {}, []
    if len(ids) == 1 and len(slots) == 2:
        # One add-on, two passes: environment is pass 1, character is pass 2.
        only = slots[0]
        t.need(only['addon'] == 'lecram', f'{only["name"]} in both slots is not supported yet: its per-pass '
               'settings are not verified. Use it in one slot.')
        section = addons[only['addon']]['section'] or addons[only['addon']].get('section_candidate')
        values = dict(_keys(only['addon'], only['values']))
        values.update(_keys(only['addon'], slots[1]['values'], pass_number=2))
        passes_key = addons[only['addon']]['settings'].get('passes')
        if passes_key:
            values[passes_key] = 2
        ini[section] = values
        install.append({'addon': only['addon'], 'build': only['build']})
    else:
        for s in slots:
            section = addons[s['addon']]['section'] or addons[s['addon']].get('section_candidate')
            values = _keys(s['addon'], s['values'])
            coexist = addons[s['addon']].get('coexist')
            if coexist and len(ids) > 1:
                values[coexist['key']] = coexist['value']
            ini.setdefault(section, {}).update(values)
            install.append({'addon': s['addon'], 'build': s['build']})
    feeder = any(addons[s['addon']]['route'] == 'feeder' for s in slots) and not game.get('native_dlss')
    pair = frozenset((s['addon'], s['build']) for s in slots)
    return {'slots': slots, 'install': install, 'model': slots[0]['model'], 'ini': ini, 'feeder': feeder,
            'verified': len(ids) == 1 and len(slots) == 1 or pair in VERIFIED_PAIRS,
            'skipped': sorted({name for s in slots for name in s['skipped']}),
            # ShortFuse's ReShade.ini section is inferred from its file and still to be confirmed in a game.
            'unconfirmed_sections': sorted(addons[a]['section_candidate'] for a in ids if not addons[a]['section'])}


def apply_combo(game, combo):
    """A saved combo applied to one game: its plan, or the reason this game can't use it."""
    setup = {slot: combo[slot] for slot in SLOTS if combo.get(slot)}
    try:
        return {'ok': True, 'plan': plan(game, setup)}
    except t.Refusal as error:
        return {'ok': False, 'reason': str(error)}
