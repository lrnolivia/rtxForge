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
VERIFIED_PAIRS: set[frozenset] = {
    # The Witcher 3 DX12, RTX 4070, driver 621.01, 2026-11-05: both add-ons loaded, NR ran (Lecram readback).
    frozenset({('lecram', '10.8'), ('shortfuse', '26.1025.0009')}),
}

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


MAX_SAVED = 100


def _combo_file(config):
    import storage
    return t.safe(storage.storage(config) / 'nr-combos.json')


def saved_combos(config):
    path = _combo_file(config)
    if not path.is_file():
        return {}
    t.need(path.stat().st_size < 1024**2, 'Saved NR combos are too large.')
    data = t.read_json(path)
    return {k: v for k, v in (data.get('combos') or {}).items() if isinstance(v, dict)} if data.get('schema') == 1 else {}


def combos(config):
    """Built-in and saved combos; every combo is available for every game."""
    return {**{k: dict(v, builtin=True) for k, v in builtin_combos().items()},
            **{k: dict(v, builtin=False) for k, v in saved_combos(config).items()}}


def _store(config, saved):
    t.atomic_file(_combo_file(config), json.dumps({'schema': 1, 'combos': saved}, indent=2).encode(), 0o600)


def save_combo(config, name, combo):
    name = str(name or '').strip()
    t.need(0 < len(name) <= 60, 'Name the combo (up to 60 characters).')
    t.need(isinstance(combo, dict), 'Choose the add-ons for the combo.')
    combo = {slot: combo[slot] for slot in SLOTS if combo.get(slot)}
    t.need(combo.get('environment'), 'A combo needs an Environment add-on.')
    # Validate the add-ons, builds, models and values without a particular game.
    plan({'native_dlss': True, 'arch': 'x64'}, combo)
    key = 'user-' + t.sha(name.casefold().encode())[:12]
    saved = saved_combos(config)
    t.need(key in saved or len(saved) < MAX_SAVED, f'Up to {MAX_SAVED} saved combos.')
    saved[key] = dict(combo, name=name)
    _store(config, saved)
    return key


def delete_combo(config, key):
    saved = saved_combos(config)
    t.need(key in saved, 'Built-in combos cannot be deleted.')
    saved.pop(key)
    _store(config, saved)


def catalog_view(config):
    """The catalog as the apps show it: add-ons with their builds, models and combos."""
    cat = catalog()
    return {'addons': [{'id': key, 'name': a['name'], 'needs_native_dlss': a.get('needs_native_dlss', False),
                        'exclusive': a.get('exclusive', False),
                        'builds': [{'id': b, 'label': v['label'], 'default': bool(v.get('default'))} for b, v in a['builds'].items()]}
                       for key, a in cat['addons'].items()],
            'models': [{'id': key, 'label': m['label']} for key, m in cat['models'].items()],
            'combos': combos(config)}


def check(game, setup):
    """Whether this setup works in this game, without changing anything."""
    try:
        p = plan(game, setup)
        return {'ok': True, 'verified': p['verified'], 'feeder': p['feeder'], 'skipped': p['skipped'],
                'install': p['install'], 'model': p['model']}
    except t.Refusal as error:
        return {'ok': False, 'reason': str(error)}


def apply_combo(game, combo):
    """A saved combo applied to one game: its plan, or the reason this game can't use it."""
    setup = {slot: combo[slot] for slot in SLOTS if combo.get(slot)}
    try:
        return {'ok': True, 'plan': plan(game, setup)}
    except t.Refusal as error:
        return {'ok': False, 'reason': str(error)}
