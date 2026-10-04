"""Reversible local Steam artwork writes shared by desktop and controller UIs.

Only grid artwork is changed. No launch options, credentials, game binaries,
Steam processes or shortcut configuration are modified by this module.
"""
from __future__ import annotations
import contextlib, fcntl, hashlib, json, os, uuid
from pathlib import Path
from types import SimpleNamespace
import engine_bridge
import transactions as t
from storage import storage

SUFFIX = {'poster': 'p', 'capsule': '', 'hero': '_hero', 'logo': '_logo'}
EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')
MAX_BYTES = 20 * 1024 * 1024


def profiles(config, *, engine=None):
    e = engine or engine_bridge.module(config)
    out = []
    for root in e.steam_roots_for_config():
        root = Path(root).resolve()
        for user in sorted((root / 'userdata').iterdir()):
            if user.name.isdigit() and user.name != '0' and user.is_dir():
                folder = user / 'config'
                if (folder / 'localconfig.vdf').is_file() or (folder / 'shortcuts.vdf').is_file():
                    out.append({'root': str(root), 'userid': user.name, 'config': str(folder),
                                'shortcuts': str(folder / 'shortcuts.vdf')})
    return out


def target(config, settings, game, *, engine=None):
    e = engine or engine_bridge.module(config)
    root = Path(game['game']).expanduser().resolve()
    exe = (root / game.get('exe', '')).resolve()
    steam = game.get('source') == 'Steam'
    if not steam and (exe == root or not exe.is_relative_to(root)):
        raise ValueError('This installation has no safe executable path for matching its Steam shortcut.')
    model = SimpleNamespace(root=root, exe=exe, name=game.get('name', root.name), appid=game.get('appid') if steam else None)
    selected = settings.get('steam_artwork_profile')
    account = None
    if selected:
        matches = [p for p in profiles(config, engine=e) if p['root'] == selected.get('root') and p['userid'] == str(selected.get('userid'))]
        if len(matches) != 1:
            raise ValueError('The selected Steam profile is unavailable. Choose a Steam artwork profile in Settings.')
        account = matches[0]
    else:
        account = e.choose_steam_user_config([model], assume_yes=True)
    if not account:
        raise ValueError('No local Steam profile was found. Open Steam once, then sync artwork again.')
    config_dir = Path(account['config']).resolve()
    expected = Path(account['root']).resolve() / 'userdata' / str(account['userid']) / 'config'
    if config_dir != expected or not config_dir.is_dir():
        raise ValueError('Steam profile path did not match its discovered account.')
    t.safe(config_dir)
    if steam:
        value = game.get('appid')
        if isinstance(value, bool) or not str(value).isdigit() or not 0 < int(value) < 2**32:
            raise ValueError('This Steam game has no valid app ID.')
        appid = int(value)
    else:
        shortcuts = t.safe(Path(account['shortcuts']))
        match = e.match_shortcut_span(model, e.parse_shortcuts_spans(shortcuts.read_bytes()))
        if match is None:
            raise ValueError('No unique Steam shortcut matches this game. Add its existing launcher to Steam first.')
        raw = e._shortcut_int(match, 'appid')
        if isinstance(raw, bool) or not isinstance(raw, int) or not -(2**31) <= raw < 2**32:
            raise ValueError('The matching Steam shortcut has no valid app ID.')
        appid = raw & 0xffffffff
        if not appid:
            raise ValueError('The matching Steam shortcut has no valid app ID.')
    return config_dir / 'grid', str(appid)


def image_extension(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Steam artwork must be between 1 byte and 20 MB.')
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    raise ValueError('Steam sync requires PNG or JPEG artwork. Export this image as PNG first.')


def _snapshot(grid, stem):
    result = {}
    for extension in EXTENSIONS:
        path = t.safe(grid / (stem + extension))
        if path.exists():
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('Existing Steam artwork exceeds the safe backup size.')
            result[path.name] = path.read_bytes()
    return result


def _hashes(files):
    return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


def _json(path, value):
    t.atomic_file(path, (json.dumps(value, sort_keys=True, indent=2) + '\n').encode(), 0o600)


def _recover_prepared(state, grid, appid, role):
    stem=str(appid)+SUFFIX[role]
    allowed={stem+extension for extension in EXTENSIONS}
    for journal in sorted(state.glob('operation-*')):
        journal=t.safe(journal)
        path=t.safe(journal/'record.json')
        if not path.is_file():continue
        record=json.loads(path.read_text())
        if record.get('status')!='prepared':continue
        if record.get('grid')!=str(grid) or record.get('appid')!=str(appid) or record.get('role')!=role:
            raise ValueError('Unfinished artwork operation has an invalid target.')
        before=record.get('before',{});after=record.get('after',{})
        if not isinstance(before,dict) or not isinstance(after,dict) or not (set(before)|set(after))<=allowed:
            raise ValueError('Unfinished artwork operation has unsafe entries.')
        current=_snapshot(grid,stem);hashes=_hashes(current)
        for name in set(before)|set(after)|set(current):
            if hashes.get(name) not in (before.get(name),after.get(name)):
                raise ValueError('An interrupted artwork update has newer external changes. They were preserved; inspect the retained backup before retrying.')
        restored={}
        for name,digest in before.items():
            data=t.safe(journal/name).read_bytes()
            if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Interrupted artwork backup failed verification.')
            restored[name]=data
        if _hashes(_snapshot(grid,stem))!=hashes:raise ValueError('Steam artwork changed during recovery.')
        for name,data in restored.items():t.atomic_file(t.safe(grid/name),data,0o600)
        for name in current.keys()-restored.keys():t.safe(grid/name).unlink()
        record['status']='recovered-rollback';_json(path,record)
        _json(state/'last-write.json',{**record,'after':before})


def write_slot(config, grid, appid, role, data=None, *, reset=False):
    """Apply a slot or restore its original pre-rtxForge baseline.

    Original and per-operation backups are retained. A reset refuses to destroy
    artwork changed by another app since our last write. Writes are serialized
    locally, hash-checked, and rolled back on ordinary I/O failure.
    """
    if role not in SUFFIX or not str(appid).isdigit() or not 0 < int(appid) < 2**32:
        raise ValueError('Invalid Steam artwork target.')
    extension = None if reset else image_extension(data)
    grid = t.safe(Path(grid))
    if grid.name != 'grid' or grid.parent.name != 'config' or not grid.parent.is_dir():
        raise ValueError('Not a discovered Steam grid folder.')
    key = hashlib.sha256(str(grid).encode()).hexdigest()
    state = t.safe(storage(config, MAX_BYTES * 6) / 'desktop' / 'steam-artwork' / key / str(appid) / role)
    state.mkdir(parents=True, exist_ok=True)
    with t.safe(state / 'lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        grid.mkdir(exist_ok=True)
        _recover_prepared(state, grid, appid, role)
        stem = str(appid) + SUFFIX[role]
        before = _snapshot(grid, stem)
        baseline_path = state / 'baseline.json'
        if not baseline_path.exists():
            if reset:
                return {'changed': False, 'role': role, 'grid': str(grid)}
            original = state / 'original'; original.mkdir(exist_ok=True)
            for name, content in before.items():
                t.atomic_file(original / name, content, 0o600)
            _json(baseline_path, {'grid': str(grid), 'appid': str(appid), 'role': role, 'files': _hashes(before)})
        baseline = json.loads(baseline_path.read_text())
        if baseline.get('grid') != str(grid) or baseline.get('appid') != str(appid) or baseline.get('role') != role:
            raise ValueError('Steam artwork baseline identity mismatch.')
        receipt_path = state / 'last-write.json'
        last = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
        if reset:
            if last and last.get('after') != _hashes(before):
                raise ValueError('Steam artwork changed outside rtxForge. Your newer artwork was preserved; resync or choose an image explicitly.')
            desired = {}
            for name, digest in baseline.get('files', {}).items():
                if name not in {stem + suffix for suffix in EXTENSIONS}:
                    raise ValueError('Unsafe Steam artwork backup entry.')
                content = t.safe(state / 'original' / name).read_bytes()
                if hashlib.sha256(content).hexdigest() != digest:
                    raise ValueError('Steam artwork backup failed verification.')
                desired[name] = content
        else:
            desired = {stem + extension: data}
        if _hashes(before) == _hashes(desired):
            return {'changed': False, 'role': role, 'grid': str(grid)}
        journal = state / ('operation-' + uuid.uuid4().hex); journal.mkdir()
        for name, content in before.items():
            t.atomic_file(journal / name, content, 0o600)
        record = {'grid': str(grid), 'appid': str(appid), 'role': role, 'before': _hashes(before), 'after': _hashes(desired), 'status': 'prepared'}
        _json(journal / 'record.json', record)
        if _hashes(_snapshot(grid, stem)) != record['before']:
            raise ValueError('Steam artwork changed while preparing the update; nothing was overwritten.')
        touched = set()
        try:
            for name, content in desired.items():
                t.atomic_file(t.safe(grid / name), content, 0o600); touched.add(name)
            for name in before.keys() - desired.keys():
                path = t.safe(grid / name)
                if path.read_bytes() != before[name]:
                    raise ValueError('Steam artwork changed during the update.')
                path.unlink(); touched.add(name)
            if _hashes(_snapshot(grid, stem)) != record['after']:
                raise ValueError('Steam artwork readback did not match the requested image.')
            _json(receipt_path, record)
            record['status'] = 'complete'; _json(journal / 'record.json', record)
        except Exception:
            # Restore only bytes we still own, never overwrite a concurrent editor.
            conflicts = []
            for name in touched:
                path = t.safe(grid / name)
                current = path.read_bytes() if path.exists() else None
                owned = desired.get(name)
                if current != owned:
                    conflicts.append(name); continue
                if name in before:
                    t.atomic_file(path, before[name], 0o600)
                elif path.exists():
                    path.unlink()
            record['status'] = 'rollback-conflict' if conflicts else 'rolled-back'
            record['conflicts'] = conflicts; _json(journal / 'record.json', record)
            raise
        return {'changed': True, 'role': role, 'grid': str(grid), 'backup': str(journal)}


def sync_game(config, settings, game, *, roles=None, reset_roles=(), include_displayed=False, engine=None):
    grid, appid = target(config, settings, game, engine=engine)
    selected = dict(settings.get('game_artwork', {}).get(game['game'], {}))
    if include_displayed:
        for role in SUFFIX:
            path=game.get(role)
            if role not in selected and isinstance(path,(str,Path)) and Path(path).is_file():selected[role]={'path':str(path)}
    results = []
    for role in roles or SUFFIX:
        if role in reset_roles:
            results.append(write_slot(config, grid, appid, role, reset=True))
        elif role in selected:
            path = t.safe(Path(selected[role]['path']))
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('Artwork exceeds the safe Steam sync size.')
            results.append(write_slot(config, grid, appid, role, path.read_bytes()))
    return results
