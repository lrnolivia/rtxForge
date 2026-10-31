"""Verified per-add-on HDR preferences, saved after the game releases ReShade.ini.

RenoDX keeps its settings callbacks private. These are startup preferences,
never a claim of live shader control. Unknown/custom builds keep their native UI.
"""
from pathlib import Path
import json
import math
import re

import renodx_hdr as hdr
import storage
import transactions as t


def _context(config, row):
    root, exe, receipt = hdr._location(row)
    t.need(receipt.is_file(), 'Install RenoDX HDR to configure it here.')
    record = hdr._record(root, receipt, exe.parent)
    t.need(all((root / name).is_file() and t.digest(t.safe(root / name)) == digest
               for name, digest in record['files'].items()), 'HDR files changed. Review the HDR installation first.')
    catalog = t.read_json(hdr.ROOT / 'providers/renodx-hdr-settings.json')
    t.need(catalog.get('schema') == 1, 'Update rtxForge for HDR settings.')
    profile = next((p for p in catalog['profiles'] if p['addon_sha256'] == record['addon_sha256']), None)
    t.need(profile, 'This add-on uses its native RenoDX settings. A verified settings adapter is not available for this build yet.')
    ini = t.safe(exe.parent / 'ReShade.ini')
    t.need(ini.is_file() and ini.stat().st_size <= 2*1024**2, 'The ReShade configuration is unavailable.')
    pending = storage.storage(config) / 'hdr-preferences' / (t.sha((str(root) + '\0' + row['exe']).encode()) + '.json')
    return root, exe, receipt, ini, profile, pending


def _number(value, field):
    t.need(type(value) in (int, float) and math.isfinite(value) and field['min'] <= value <= field['max'],
           'Choose a value within the supported HDR range: ' + field['label'])
    if field['kind'] == 'choice':
        t.need(int(value) == value, 'Choose a supported HDR option.')
    return float(value)


def _saved(ini, profile):
    parser = t.ini(ini.read_text(encoding='utf-8-sig'))
    result = {}
    for field in profile['controls']:
        try: result[field['key']] = _number(float(parser.get(profile['section'], field['key'], fallback=str(field['default']))), field)
        except (ValueError, t.Refusal): result[field['key']] = field['default']
    return result


def snapshot(config, row):
    try:
        root, exe, receipt, ini, profile, path = _context(config, row)
        values = _saved(ini, profile)
        pending = t.read_json(path) if path.is_file() else {}
        if pending.get('receipt') == t.digest(receipt):
            fields = {f['key']: f for f in profile['controls']}
            changes = pending.get('changes', {})
            t.need(isinstance(changes, dict) and set(changes) <= fields.keys(), 'Invalid pending HDR settings.')
            values.update({key: _number(value, fields[key]) for key, value in changes.items()})
        return {'available': True, 'installed': True, 'title': 'RenoDX HDR', 'controls': profile['controls'], 'values': values,
                'pending': bool(pending), 'message': pending.get('error') or
                ('Saved changes are queued until this game closes. Restart to use them.' if pending else
                 'Startup HDR preferences. Changes apply after closing and restarting the game; live adjustments remain in the native RenoDX menu.')}
    except (OSError, ValueError, KeyError, t.Refusal) as error:
        try: installed = hdr._location(row)[2].is_file()
        except (OSError, ValueError, KeyError, t.Refusal): installed = False
        return {'available': False, 'installed': installed, 'controls': [], 'values': {}, 'message': str(error)}


def save(config, row, changes):
    root, exe, receipt, ini, profile, path = _context(config, row)
    fields = {f['key']: f for f in profile['controls']}
    t.need(isinstance(changes, dict) and 0 < len(changes) <= len(fields) and set(changes) <= fields.keys(), 'Choose a supported HDR setting.')
    changes = {key: _number(value, fields[key]) for key, value in changes.items()}
    e = hdr.engine_bridge.module(config)
    with e.mutation_lock():
        root, exe, receipt, ini, profile, path = _context(config, row)
        before = _saved(ini, profile)
        prior = t.read_json(path) if path.is_file() else {}
        t.need(not prior or prior.get('receipt') == t.digest(receipt), 'The HDR package changed. Review these preferences again.')
        document = {'schema': 1, 'row': {k: row[k] for k in ('name', 'game', 'exe')}, 'receipt': t.digest(receipt),
                    'changes': {**prior.get('changes', {}), **changes},
                    'before': {**prior.get('before', {}), **{key: before[key] for key in changes}}}
        t.atomic_file(path, (json.dumps(document, indent=2) + '\n').encode(), 0o600)
    flush(config)
    return snapshot(config, row)


def flush(config):
    folder = storage.storage(config) / 'hdr-preferences'
    if not folder.is_dir(): return {'applied': 0}
    paths = list(folder.glob('*.json'))
    t.need(len(paths) <= 512, 'Too many pending HDR preference records.')
    if not paths: return {'applied': 0}
    e = hdr.engine_bridge.module(config)
    applied = 0
    for path in paths:
        with e.mutation_lock():
            pending = {}
            try:
                # A save can merge edits while another worker waits for this lock.
                # Read and retain errors under the same lock as the final write.
                t.need(t.safe(path).stat().st_size <= 256*1024, 'Invalid HDR preference record.')
                pending = t.read_json(path)
                root, exe, receipt, ini, profile, expected = _context(config, pending['row'])
                t.need(path == expected and pending.get('schema') == 1 and pending['receipt'] == t.digest(receipt), 'The HDR package changed; preferences were kept for review.')
                if e._running_processes_under_root(root): continue
                fields = {f['key']: f for f in profile['controls']}
                changes = pending['changes']
                t.need(isinstance(changes, dict) and changes and set(changes) <= fields.keys(), 'Invalid HDR preferences.')
                current = _saved(ini, profile)
                for key, value in changes.items():
                    _number(value, fields[key])
                    t.need(current[key] in (pending['before'][key], value), 'HDR settings changed in the native menu. Your newer settings were kept; review this pending change in rtxForge.')
                raw = ini.read_bytes(); text = raw.decode('utf-8-sig')
                for key, value in changes.items(): text = t.setvalue(text, profile['section'], key, format(value, '.8g'))
                backup = folder / 'backups' / t.sha(raw)
                if not backup.exists(): t.atomic_file(backup, raw, 0o600)
                # Repeat the runtime guard at the last possible write boundary.
                t.need(not e._running_processes_under_root(root), 'The game started; HDR preferences remain queued.')
                t.atomic_file(ini, text.encode('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'), ini.stat().st_mode & 0o777)
                path.unlink(); applied += 1
            except (OSError, ValueError, KeyError, t.Refusal) as error:
                if isinstance(pending, dict) and pending:
                    pending['error'] = str(error)
                    try: t.atomic_file(path, (json.dumps(pending, indent=2) + '\n').encode(), 0o600)
                    except OSError: pass
    return {'applied': applied}
