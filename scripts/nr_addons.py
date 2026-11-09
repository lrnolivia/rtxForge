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
- Lecram never runs where OptiScaler is installed (see the catalog's reason).
- Where OptiScaler runs its own NR (Skynizz), that NR is the Environment: the
  slot shows it as the world choice, and only an add-on marked
  with_optiscaler_nr may take Character.
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
# Lecram 10.8 + ShortFuse: both NR passes, Ray Reconstruction and the game's frame generation
# ran together in The Witcher 3 (RTX 4070, 2026-11-05).
VERIFIED_PAIRS: set[frozenset] = {frozenset({('lecram', '10.8'), ('shortfuse', '26.1025.0009')})}
# OptiScaler's NR as Environment with ShortFuse as Character also ran with Ray Reconstruction and
# multi-frame generation (The Witcher 3, RTX 4070, 2026-11-06); a single add-on counts as verified.
OPTISCALER_NR = ('nr-mfg', 'nr-only')
OTHER_RUNTIMES = (None, 'feeder', 'vulkan-native')
# The Environment choice that means "the NR OptiScaler already runs in this game".
RUNTIME = 'optiscaler'
# How that world is named: by the package that brings it, like the add-ons.
RUNTIME_NAMES = {'skynizz': 'Skynizz', 'y4my': 'y4my', 'dlss-unlocked': 'DLSS-Unlocked'}


def optiscaler_mode(game):
    """OptiScaler's feature mode in this game, 'unknown' when it can't be read, or None without it."""
    if 'optiscaler_mode' in game:
        return game['optiscaler_mode']
    if game.get('installed') and game.get('runtime_provider') not in OTHER_RUNTIMES:
        return game.get('feature_mode') or 'unknown'
    return None


def runtime_name(game):
    """The name of the package whose NR is (or would be) this game's world: Skynizz unless another one is installed."""
    return RUNTIME_NAMES.get(game.get('runtime_provider'), 'Skynizz')


def runtime_nr(game):
    """The Environment choice OptiScaler's own NR fills in this game, or None where it doesn't run NR."""
    if optiscaler_mode(game) in OPTISCALER_NR:
        return {'id': RUNTIME, 'name': runtime_name(game)}
    return None

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
    beside = addon.get('beside_optiscaler') or {}
    if optiscaler_mode(game):
        t.need(beside.get('allowed', True), f'{addon["name"]} can\'t run where OptiScaler is installed: {beside.get("reason", "")}')
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
    # ShortFuse stores its processing scale as a whole percent.
    percent = catalog()['addons'][addon_id].get('percent', ())
    return {settings[name]: round(value * 100) if name in percent else value
            for name, value in values.items() if settings.get(name)}


def plan(game, setup):
    """What installing this setup in this game takes, or a Refusal saying why it can't."""
    t.need(isinstance(setup, dict), 'Choose an add-on for Environment.')
    addons = catalog()['addons']
    mode = optiscaler_mode(game)
    t.need(mode != 'unknown', "rtxForge can't tell whether OptiScaler's NR is on in this game. Repair OptiScaler here first.")
    optiscaler_nr = mode in OPTISCALER_NR
    world = runtime_name(game)
    environment = setup.get('environment')
    if optiscaler_nr:
        if environment and environment.get('addon') != RUNTIME:
            _slot(environment, 'environment', game)  # an add-on that can't run here says why first
            raise t.Refusal(f'{world} already covers the environment in this game. '
                            f'Keep {world} as Environment and choose a Character add-on.')
        t.need(setup.get('character'), f'{world} covers the environment in this game. Choose a Character add-on.')
        slots = [_slot(setup['character'], 'character', game)]
        addon = addons[slots[0]['addon']]
        t.need((addon.get('beside_optiscaler') or {}).get('with_optiscaler_nr'),
               f"{addon['name']} can't run beside {world}'s NR. Switch {world} to MFG Only to use it.")
    else:
        t.need(not environment or environment.get('addon') != RUNTIME,
               f"{world} doesn't run NR in this game. Choose an add-on for Environment.")
        t.need(environment, 'Choose an add-on for Environment.')
        slots = [_slot(setup['environment'], 'environment', game)]
        if setup.get('character'):
            slots.append(_slot(setup['character'], 'character', game))
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
        section = addons[only['addon']]['section']
        values = dict(_keys(only['addon'], only['values']))
        values.update(_keys(only['addon'], slots[1]['values'], pass_number=2))
        passes_key = addons[only['addon']]['settings'].get('passes')
        if passes_key:
            values[passes_key] = 2
        ini[section] = values
        install.append({'addon': only['addon'], 'build': only['build']})
    else:
        for s in slots:
            section = addons[s['addon']]['section']
            values = _keys(s['addon'], s['values'])
            coexist = addons[s['addon']].get('coexist')
            if coexist and len(ids) > 1:
                values[coexist['key']] = coexist['value']
            ini.setdefault(section, {}).update(values)
            install.append({'addon': s['addon'], 'build': s['build']})
    for addon_id in ids:
        # Lecram remembers its F6 toggle as NeuralUplift; an install always starts with NR on.
        launch = addons[addon_id].get('on_at_launch')
        if launch:
            ini.setdefault(addons[addon_id]['section'], {})[launch['key']] = launch['value']
    feeder = any(addons[s['addon']]['route'] == 'feeder' for s in slots) and not game.get('native_dlss')
    pair = frozenset((s['addon'], s['build']) for s in slots)
    return {'slots': slots, 'install': install, 'ini': ini, 'feeder': feeder,
            # OptiScaler's NR brings its own model, which the add-on shares.
            'model': None if optiscaler_nr else slots[0]['model'], 'optiscaler_nr': optiscaler_nr,
            'world': world if optiscaler_nr else slots[0]['name'].split(' (')[0],
            'verified': len(ids) == 1 and len(slots) == 1 or pair in VERIFIED_PAIRS,
            'skipped': sorted({name for s in slots for name in s['skipped']}),
            # Add-ons ReShade must load while it starts (ReShade.ini [ADDON] LoadFromDllMain).
            'load_early': sorted(addons[a]['file'] for a in ids if addons[a].get('load_early'))}


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
    if (combo.get('environment') or {}).get('addon') == RUNTIME:
        combo.pop('environment')  # the game's own world: saved as no Environment add-on
    t.need(combo, 'Choose the add-ons for the combo.')
    # Validate the add-ons, builds, models and values without a particular game. A combo without
    # an Environment add-on is for games where Skynizz's NR covers it.
    plan({'native_dlss': True, 'arch': 'x64', 'optiscaler_mode': None if combo.get('environment') else 'nr-mfg'}, combo)
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


def combo_setup(game, combo):
    """What a combo means in one game. Its Environment is the world: where Skynizz runs NR, Skynizz
    is the world instead of the combo's add-on, and the combo's beside_runtime_nr settings apply."""
    setup = {slot: copy.deepcopy(combo[slot]) for slot in SLOTS if combo.get(slot)}
    world = runtime_nr(game)
    if world:
        beside = combo.get('beside_runtime_nr') or {}
        if beside.get('character'):
            setup['character'] = copy.deepcopy(beside['character'])
        setup['environment'] = {'addon': world['id']}
    elif (setup.get('environment') or {}).get('addon') == RUNTIME:
        setup.pop('environment')
    return setup


def catalog_view(config, game=None):
    """The catalog as the apps show it: add-ons with their builds, models and combos. For a game,
    each combo is what it means there, and runtime_nr names the world Skynizz already provides."""
    cat = catalog()
    found = combos(config)
    if game is not None:
        found = {key: dict(combo_setup(game, combo), name=combo.get('name', key), builtin=combo['builtin'])
                 for key, combo in found.items()}
    return {'addons': [{'id': key, 'name': a['name'], 'needs_native_dlss': a.get('needs_native_dlss', False),
                        'exclusive': a.get('exclusive', False),
                        'builds': [{'id': b, 'label': v['label'], 'default': bool(v.get('default'))} for b, v in a['builds'].items()]}
                       for key, a in cat['addons'].items()],
            'models': [{'id': key, 'label': m['label']} for key, m in cat['models'].items()],
            'combos': found,
            'runtime_nr': runtime_nr(game) if game is not None else None}


def install_choices(config):
    """Choices shared by the package install reviews. Saved combos carry custom builds and tuning."""
    cat = catalog()
    choices = [{'label': combo['name'], 'setup': combo, 'adapt': True}
               for combo in combos(config).values()]
    for slot, title in (('environment', 'Environment'), ('character', 'Character detail')):
        for key, addon in cat['addons'].items():
            if slot == 'character' and not (addon.get('beside_optiscaler') or {}).get('with_optiscaler_nr'):
                continue  # A single Character add-on requires the runtime to provide the world.
            for model, spec in cat['models'].items():
                choices.append({'label': f'{title} · {addon["name"]} · {spec["label"]}',
                                'setup': {slot: {'addon': key, 'model': model}}, 'adapt': False})
    return choices


def default_setup(game):
    """The setup a game's picker starts on: Lecram for the environment, or Skynizz for the
    environment with ShortFuse for characters where Skynizz's NR covers it."""
    world = runtime_nr(game)
    if world:
        return {'environment': {'addon': world['id']}, 'character': {'addon': 'shortfuse'}}
    return {'environment': {'addon': 'lecram'}}


def install_plan(game, setup):
    """The standalone add-on operation cannot install the Feeder stack."""
    result = plan(game, setup)
    t.need(not result['feeder'],
           'This game has no DLSS of its own, so Lecram runs through Feeder NR. Choose Feeder NR for it.')
    return result


def check(game, setup):
    """Whether this setup works in this game, without changing anything."""
    try:
        p = install_plan(game, setup)
        return {'ok': True, 'verified': p['verified'], 'feeder': p['feeder'], 'skipped': p['skipped'],
                'install': p['install'], 'model': p['model'], 'optiscaler_nr': p['optiscaler_nr'], 'world': p['world']}
    except t.Refusal as error:
        return {'ok': False, 'reason': str(error)}


def apply_combo(game, combo):
    """A saved combo applied to one game: its plan, or the reason this game can't use it."""
    setup = combo_setup(game, combo)
    try:
        return {'ok': True, 'plan': install_plan(game, setup)}
    except t.Refusal as error:
        return {'ok': False, 'reason': str(error)}
