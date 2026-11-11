"""Apply per-game ReShade UI preferences after its runtime releases the INI."""
import configparser
import json

import engine_bridge
import feeder_provider
import file_stamps
import nr_install
import overlay_policy
import renodx_hdr
import storage
import transactions as t


KEYS = ('reshade_ui', 'reshade_intro')
ERRORS = (OSError, ValueError, KeyError, TypeError, configparser.Error, t.Refusal)


def _verified_host(target, owned, hosts):
    for name in hosts:
        if not name or name not in owned:
            continue
        path = t.safe(target / t.relative(name))
        if path.is_file() and file_stamps.digest(path) == owned[name]:
            return True
    return False


def _managed_configs(engine, row):
    root, exe, hdr_receipt = renodx_hdr._location(row)
    target = exe.parent
    names = set()
    if not (target / 'ReShade.ini').is_file() and not (target / 'host64/ReShade.ini').is_file():
        return root, []
    feeder = feeder_provider.state(engine, target)
    if feeder and feeder.get('status') == 'active':
        owned = feeder['installed_hashes']
        if _verified_host(target, owned, ('dxgi.dll', 'd3d9.dll', *feeder_provider.FEEDER_HOOKS)):
            names.update(name for name in owned if name in ('ReShade.ini', 'host64/ReShade.ini'))
    native = renodx_hdr._managed(engine, target)
    if native:
        current = native.get('current') or {}
        owned = current.get('installed_hashes') or {}
        if 'ReShade.ini' in owned and _verified_host(target, owned, (current.get('proxy'),)):
            names.add('ReShade.ini')
    nr_receipt = nr_install._receipt(row)
    for receipt, read in ((nr_receipt, lambda: nr_install._read_receipt(root, nr_receipt)),
                          (hdr_receipt, lambda: renodx_hdr._record(root, hdr_receipt, target))):
        if not receipt.is_file():
            continue
        record = read()
        # Only a verified ReShade host belonging to the installed package can
        # authorize changes to the game's menu policy.
        host = record.get('host')
        if not host:
            continue
        host_path = t.safe(target / t.relative(host))
        digest = record['files'].get(host_path.relative_to(root).as_posix())
        if digest and host_path.is_file() and file_stamps.digest(host_path) == digest:
            names.add('ReShade.ini')
    configs = [t.safe(target / name) for name in sorted(names)]
    return root, [path for path in configs if path.is_file() and path.stat().st_size <= 2 * 1024**2]


def _folder(config):
    return storage.storage(config) / 'reshade-ui-settings'


def _pending(folder, row):
    return folder / (t.sha((str(t.safe(row['game'])) + '\0' + row['exe']).encode()) + '.json')


def _settings(values):
    t.need(isinstance(values, dict) and values and set(values) <= set(KEYS), 'Choose ReShade UI options.')
    checked = overlay_policy.options(values)
    return {key: checked[key] for key in values}


def _update(raw, values):
    text = raw.decode('utf-8-sig')
    updated = overlay_policy.reshade(text, values, keys=values)
    return updated.encode('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8')


def stage(config, row, values):
    values = _settings(values)
    folder = _folder(config)
    path = _pending(folder, row)
    engine = engine_bridge.module(config)
    with engine.mutation_lock():
        _, configs = _managed_configs(engine, row)
        if not configs:
            return {'managed': False, 'pending': False}
        if path.is_file():
            prior = t.read_json(t.safe(path))
            values = _settings(prior['values']) | values
        if all(_update(raw := item.read_bytes(), values) == raw for item in configs):
            if path.is_file():
                path.unlink()
            return {'managed': True, 'pending': False}
        pending = {'schema': 1, 'row': {key: row[key] for key in ('game', 'exe')},
                   'values': values}
        t.atomic_file(path, (json.dumps(pending) + '\n').encode(), 0o600)
    return {'managed': True, 'pending': True}


def flush(config):
    folder = _folder(config)
    paths = list(folder.glob('*.json'))
    if not paths:
        return {'applied': 0}
    t.need(len(paths) <= 512, 'Too many pending ReShade UI settings.')
    engine = engine_bridge.module(config)
    applied = 0
    for path in paths:
        with engine.mutation_lock():
            pending = {}
            try:
                t.need(t.safe(path).stat().st_size <= 64 * 1024, 'Invalid pending ReShade UI settings.')
                pending = t.read_json(path)
                row = pending['row']
                t.need(pending.get('schema') == 1 and path == _pending(folder, row),
                       'Invalid pending ReShade UI settings.')
                root, configs = _managed_configs(engine, row)
                if engine._running_processes_under_root(root):
                    continue
                values = _settings(pending['values'])
                for ini in configs:
                    raw = ini.read_bytes()
                    updated = _update(raw, values)
                    if updated == raw:
                        continue
                    backup = folder / 'backups' / t.sha(raw)
                    if not backup.is_file():
                        t.atomic_file(backup, raw, 0o600)
                    t.need(not engine._running_processes_under_root(root),
                           'The game started. ReShade settings remain queued.')
                    t.need(ini.read_bytes() == raw, 'ReShade settings changed while applying this update.')
                    t.atomic_file(ini, updated, ini.stat().st_mode & 0o777)
                path.unlink()
                applied += bool(configs)
            except ERRORS as error:
                if isinstance(pending, dict) and pending and pending.get('error') != str(error):
                    pending['error'] = str(error)
                    t.atomic_file(path, (json.dumps(pending) + '\n').encode(), 0o600)
    return {'applied': applied}
