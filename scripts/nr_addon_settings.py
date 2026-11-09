"""In-game overlay settings for the DLSS5 NR add-ons rtxForge installed in a game.

Lecram and ShortFuse read their settings from ReShade.ini when the game starts,
and ShortFuse writes them back while it runs, so the overlay never edits a
running game's file. Like HDR preferences, a change is queued and written after
the game closes; the add-on picks it up at the next launch. Live adjustments
stay in each add-on's own ReShade panel.

Only settings whose key and value encoding nr_addons verified are offered, under
the slot's role: Environment, or Character detail. Lecram is never offered where
OptiScaler is installed, since it can't run there.
"""
from __future__ import annotations

import json
import math

import nr_addons
import nr_install
import renodx_hdr as hdr
import storage
import transactions as t

FOLDER = 'nr-addon-preferences'
LABELS = {'intensity': 'Strength', 'style': 'Style', 'local_tone': 'Local tone', 'structure': 'Structure',
          'character': 'Skin detail', 'character_mask': 'Character mask', 'independent_skin': 'Separate skin pass',
          'ui_correction': 'UI correction', 'passes': 'Passes', 'resolution_scale': 'Resolution scale',
          'block_hudless': 'Ignore HUD-less frames', 'diffuse_white_nits': 'Diffuse white'}
UNITS = {'diffuse_white_nits': 'nits'}
ROLES = {'environment': 'Environment', 'character': 'Character detail'}


def _group(slot, addon_id, second_pass=False):
    """The verified controls of one slot, as overlay fields with their ReShade.ini key."""
    addon = nr_addons.catalog()['addons'][addon_id]
    section = addon['section']
    percent = addon.get('percent', ())
    title = ROLES[slot] + ' · ' + addon['name'].split(' (')[0]
    fields = []
    for name, key in addon['settings'].items():
        if not key or not (name in nr_addons.RANGES or name in nr_addons.SWITCHES or name in nr_addons.COUNTS):
            continue  # an unverified encoding is never written
        if second_pass:
            if name not in nr_addons.LECRAM_PASS:
                continue
            key = f'NRPass2{nr_addons.LECRAM_PASS[name]}'
        field = {'key': f'{slot}_{name}', 'label': LABELS.get(name, name.replace('_', ' ').capitalize()),
                 'section': title, 'unit': UNITS.get(name, ''), 'reset': False, 'ini': [section, key], 'whole': False}
        if name in nr_addons.SWITCHES:
            field.update(kind='choice', choices=['Off', 'On'], min=0, max=1, step=1, default=1, whole=True)
        elif name in nr_addons.COUNTS:
            low, high = nr_addons.COUNTS[name]
            field.update(kind='slider', min=low, max=high, step=1, default=low, whole=True)
        else:
            low, high = nr_addons.RANGES[name]
            if name in percent:
                # ShortFuse stores its processing scale as a whole percent.
                field.update(kind='slider', min=round(low * 100), max=round(high * 100), step=1,
                             default=round(high * 100), unit='%', whole=True)
            elif isinstance(low, int) and isinstance(high, int):
                field.update(kind='slider', min=low, max=high, step=1, default=low, whole=True)
            else:
                field.update(kind='slider', min=low, max=high, step=0.01, default=min(max(1.0, low), high))
        fields.append(field)
    return fields


def _fields(record):
    setup = record['setup']
    slots = [(slot, setup[slot]['addon']) for slot in nr_addons.SLOTS
             if isinstance(setup.get(slot), dict) and setup[slot].get('addon') in nr_addons.catalog()['addons']]
    fields, same = [], len({a for _, a in slots}) == 1 and len(slots) == 2
    for index, (slot, addon_id) in enumerate(slots):
        if addon_id == 'lecram' and record['route'] == 'optiscaler':
            continue  # Lecram can't run beside OptiScaler
        if same and index == 1 and addon_id != 'lecram':
            continue  # only Lecram's per-pass keys are verified
        fields += _group(slot, addon_id, second_pass=same and index == 1)
    return fields


def _context(config, row):
    root = t.safe(row['game'])
    exe = t.safe(root / t.relative(row['exe']))
    t.need(exe.is_file(), 'Choose an installed game.')
    receipt = nr_install._receipt(row)
    t.need(receipt.is_file(), 'Install Split Render in rtxForge to adjust it here.')
    record = nr_install._read_receipt(root, receipt)
    ini = t.safe(exe.parent / 'ReShade.ini')
    t.need(ini.is_file() and ini.stat().st_size <= 2 * 1024**2, 'The ReShade configuration is unavailable.')
    fields = _fields(record)
    t.need(fields, 'This NR add-on setup has no settings rtxForge can adjust yet. Use the add-on\'s own panel.')
    pending = storage.storage(config) / FOLDER / (t.sha((str(root) + '\0' + row['exe']).encode()) + '.json')
    return root, exe, receipt, ini, fields, pending


def _number(value, field):
    t.need(type(value) in (int, float) and math.isfinite(value) and field['min'] <= value <= field['max'],
           'Choose a value within the supported range: ' + field['label'])
    if field['whole']:
        t.need(int(value) == value, 'Choose a whole number: ' + field['label'])
        return int(value)
    return float(value)


def _saved(ini, fields):
    """Each field's current value, and the fields whose key the file doesn't set yet."""
    parser = t.ini(ini.read_text(encoding='utf-8-sig'))
    values, unreported = {}, []
    for field in fields:
        section, key = field['ini']
        raw = parser.get(section, key, fallback=None)
        try:
            values[field['key']] = _number(float(raw), field) if raw is not None else field['default']
        except (ValueError, t.Refusal):
            values[field['key']] = field['default']
        if raw is None:
            unreported.append(field['key'])
    return values, unreported


def _public(fields):
    return [{k: v for k, v in f.items() if k not in ('ini', 'whole')} for f in fields]


def snapshot(config, row):
    try:
        root, exe, receipt, ini, fields, path = _context(config, row)
        values, unreported = _saved(ini, fields)
        pending = t.read_json(path) if path.is_file() else {}
        if pending.get('receipt') == t.digest(receipt):
            by_key = {f['key']: f for f in fields}
            changes = pending.get('changes', {})
            t.need(isinstance(changes, dict) and set(changes) <= by_key.keys(), 'Invalid pending NR add-on settings.')
            values.update({key: _number(value, by_key[key]) for key, value in changes.items()})
            unreported = [key for key in unreported if key not in changes]
        else:
            pending = {}
        return {'available': True, 'installed': True, 'title': 'NR add-ons', 'controls': _public(fields),
                'values': values, 'unreported': unreported, 'pending': bool(pending),
                'message': pending.get('error') or
                ('Saved changes are queued until this game closes. Restart to use them.' if pending else
                 'The add-ons read these when the game starts, so changes apply after a restart. '
                 'Live adjustments stay in each add-on\'s own ReShade panel.')}
    except (OSError, ValueError, KeyError, TypeError, t.Refusal) as error:
        try:
            installed = nr_install._receipt(row).is_file()
        except (OSError, ValueError, KeyError, TypeError, t.Refusal):
            installed = False
        return {'available': False, 'installed': installed, 'controls': [], 'values': {}, 'message': str(error)}


def save(config, row, changes):
    root, exe, receipt, ini, fields, path = _context(config, row)
    by_key = {f['key']: f for f in fields}
    t.need(isinstance(changes, dict) and 0 < len(changes) <= len(by_key) and set(changes) <= by_key.keys(),
           'Choose a supported NR add-on setting.')
    changes = {key: _number(value, by_key[key]) for key, value in changes.items()}
    e = hdr.engine_bridge.module(config)
    with e.mutation_lock():
        root, exe, receipt, ini, fields, path = _context(config, row)
        before, _ = _saved(ini, fields)
        raw = t.ini(ini.read_text(encoding='utf-8-sig'))
        prior = t.read_json(path) if path.is_file() else {}
        t.need(not prior or prior.get('receipt') == t.digest(receipt), 'The NR add-on setup changed. Review these settings again.')
        document = {'schema': 1, 'row': {k: row[k] for k in ('name', 'game', 'exe') if k in row}, 'receipt': t.digest(receipt),
                    'changes': {**prior.get('changes', {}), **changes},
                    # The file's text before the first queued edit, None where the key was absent.
                    'before': {**{key: raw.get(*by_key[key]['ini'], fallback=None) for key in changes},
                               **prior.get('before', {})}}
        t.atomic_file(path, (json.dumps(document, indent=2) + '\n').encode(), 0o600)
    flush(config)
    return snapshot(config, row)


def _text(value):
    return str(value) if isinstance(value, int) else f'{value:.2f}'


def flush(config):
    folder = storage.storage(config) / FOLDER
    if not folder.is_dir():
        return {'applied': 0}
    paths = list(folder.glob('*.json'))
    t.need(len(paths) <= 512, 'Too many pending NR add-on records.')
    if not paths:
        return {'applied': 0}
    e = hdr.engine_bridge.module(config)
    applied = 0
    for path in paths:
        with e.mutation_lock():
            pending = {}
            try:
                t.need(t.safe(path).stat().st_size <= 256 * 1024, 'Invalid NR add-on settings record.')
                pending = t.read_json(path)
                root, exe, receipt, ini, fields, expected = _context(config, pending['row'])
                t.need(path == expected and pending.get('schema') == 1 and pending['receipt'] == t.digest(receipt),
                       'The NR add-on setup changed; these settings were kept for review.')
                if e._running_processes_under_root(root):
                    continue
                by_key = {f['key']: f for f in fields}
                changes = pending['changes']
                t.need(isinstance(changes, dict) and changes and set(changes) <= by_key.keys(), 'Invalid NR add-on settings.')
                raw = ini.read_bytes()
                text = raw.decode('utf-8-sig')
                parsed = t.ini(text)
                for key, value in changes.items():
                    _number(value, by_key[key])
                    current = parsed.get(*by_key[key]['ini'], fallback=None)
                    # An add-on writes back what its own panel changed. Keep that, and this change, for review.
                    t.need(current == pending['before'].get(key) or (current is not None and current.strip() == _text(value)),
                           'Settings changed in the add-on\'s own panel. Your newer settings were kept; review them in rtxForge.')
                for key, value in changes.items():
                    text = t.setvalue(text, *by_key[key]['ini'], _text(value))
                backup = folder / 'backups' / t.sha(raw)
                if not backup.exists():
                    t.atomic_file(backup, raw, 0o600)
                # Repeat the runtime guard at the last possible write boundary.
                t.need(not e._running_processes_under_root(root), 'The game started; NR add-on settings remain queued.')
                t.atomic_file(ini, text.encode('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'), ini.stat().st_mode & 0o777)
                path.unlink()
                applied += 1
            except (OSError, ValueError, KeyError, TypeError, t.Refusal) as error:
                if isinstance(pending, dict) and pending:
                    pending['error'] = str(error)
                    try:
                        t.atomic_file(path, (json.dumps(pending, indent=2) + '\n').encode(), 0o600)
                    except OSError:
                        pass
    return {'applied': applied}
