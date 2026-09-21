"""Native DLSS updates using existing hash-guarded transactions.

Catalog adapters are independent of the feature provider. No game writes occur
until apply(); only existing native SR/RR/FG files are eligible.
"""
from pathlib import Path
import hashlib
import json
import mmap
import re
import shutil
import struct
import urllib.parse
import urllib.request
import uuid

import discovery
import engine_bridge
import transactions as t
import ui
from storage import storage

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = {
    'nvngx_dlss.dll': 'Super Resolution',
    'nvngx_dlssd.dll': 'Ray Reconstruction',
    'nvngx_dlssg.dll': 'Frame Generation',
}
MAX_DLL = 256 * 1024 * 1024


def version(path):
    """Read VS_FIXEDFILEINFO without loading or executing a DLL."""
    t.executable_check(path)
    with Path(path).open('rb') as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
            offset = data.find(struct.pack('<II', 0xFEEF04BD, 0x10000))
            if offset < 0 or offset + 16 > len(data):
                return None
            ms, ls = struct.unpack_from('<II', data, offset + 8)
    return '.'.join(map(str, (ms >> 16, ms & 65535, ls >> 16, ls & 65535)))


def _json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'rtxForge-runtime-updates'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(4 * 1024 * 1024 + 1)
    t.need(len(data) <= 4 * 1024 * 1024, 'Runtime catalog exceeds size limit')
    return json.loads(data)


def catalog(config):
    """Resolve one immutable Git snapshot, including content IDs for each DLL."""
    source = config.get('runtime_source') or t.read_json(ROOT / 'providers/runtime_sources.json')
    repo = source['repository']
    t.need(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo), 'Invalid runtime repository')
    ref = urllib.parse.quote(source.get('ref', 'main'), safe='')
    commit = _json(f'https://api.github.com/repos/{repo}/commits/{ref}')['sha']
    t.need(re.fullmatch(r'[a-f0-9]{40}', commit), 'Invalid source commit')
    manifest = str(t.relative(source.get('manifest', 'manifest.json')))
    directory = str(t.relative(source.get('directory', 'dlls')))
    base = f'https://raw.githubusercontent.com/{repo}/{commit}'
    doc = _json(f'{base}/{manifest}')
    tree = _json(f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1')
    t.need(not tree.get('truncated'), 'Runtime repository tree is incomplete')
    blobs = {entry['path']: entry for entry in tree['tree'] if entry['type'] == 'blob'}
    entries = {}
    for name, title in COMPONENTS.items():
        item = doc.get(name)
        blob = blobs.get(f'{directory}/{name}')
        if not item or not blob:
            continue
        t.need(re.fullmatch(r'\d+\.\d+\.\d+\.\d+', item['version']), 'Invalid runtime version')
        t.need(re.fullmatch(r'[a-f0-9]{40}', blob['sha']), 'Invalid runtime content ID')
        t.need(64 < blob['size'] <= MAX_DLL, 'Invalid runtime size')
        entries[name] = {'name': name, 'title': title, 'version': item['version'],
                         'size': blob['size'], 'blob_sha1': blob['sha'],
                         'url': f'{base}/{directory}/{name}'}
    t.need(entries, 'No supported DLSS runtimes in this source')
    return {'repository': repo, 'commit': commit, 'entries': entries}


def download(config, entry):
    cache = storage(config, entry['size'] * 2) / 'runtime-cache' / entry['blob_sha1']
    cache.mkdir(parents=True, exist_ok=True)
    target = t.safe(cache / entry['name'])

    def verify(path):
        t.need(path.stat().st_size == entry['size'], 'Runtime download size mismatch')
        h = hashlib.sha1(f"blob {entry['size']}\0".encode())
        with path.open('rb') as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                h.update(block)
        t.need(h.hexdigest() == entry['blob_sha1'], 'Runtime source content mismatch')
        t.need(version(path) == entry['version'], 'Runtime PE version mismatch')

    if target.exists():
        verify(target)
        return target
    stage = t.safe(cache / ('.download-' + uuid.uuid4().hex))
    try:
        request = urllib.request.Request(entry['url'], headers={'User-Agent': 'rtxForge-runtime-updates'})
        with urllib.request.urlopen(request, timeout=60) as response, stage.open('xb') as out:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                t.need(total <= entry['size'], 'Runtime download exceeds expected size')
                out.write(block)
        verify(stage)
        stage.replace(target)
    finally:
        stage.unlink(missing_ok=True)
    return target


def _private(path):
    return any(part.casefold() in {'optiscaler', '.git', '.rtxforge', 'rtxengine'}
               or any(word in part.casefold() for word in ('backup', 'quarantine'))
               or part.casefold().endswith(('.bak', '.old')) for part in path.parts[:-1])


def _owned(engine, root, path):
    for parent in (path.parent, *path.parent.parents):
        if not parent.is_relative_to(root):
            break
        baseline = engine.load_baseline(parent, readonly=True)
        if baseline and baseline.get('status') != 'restored':
            rel = path.relative_to(parent).as_posix().casefold()
            protected = set(baseline.get('managed_paths', [])) | set(baseline.get('originals', {}))
            if rel in {str(p).casefold() for p in protected}:
                return True
    return False


def inspect(config, games, snapshot=None):
    engine = engine_bridge.module(config)
    rows = []
    for game in games:
        root = Path(game['game']).resolve()
        row = {'name': game['name'], 'game': str(root), 'files': [], 'blocked': ''}
        try:
            t.safe(root)
            t.need(root.is_dir(), 'Game folder is unavailable')
            found = discovery.inspect_game(discovery.Game('', game['name'], str(root), game.get('source', 'Folder')))
            t.need(not found.anti_cheat, 'Anti-cheat detected')
            t.need(found.exe, 'No Windows executable found')
            for raw in found.upscalers:
                path = Path(raw)
                name = path.name.casefold()
                rel = path.relative_to(root)
                if name not in (snapshot['entries'] if snapshot else COMPONENTS) or _private(rel):
                    continue
                t.safe(path)
                if _owned(engine, root, path):
                    continue
                current = version(path)
                target = snapshot['entries'][name] if snapshot else None
                # Automatic management leaves unknown, same and newer builds untouched.
                state = 'Update available' if target else 'Installed'
                if target and current == target['version']:
                    state = 'Same version'
                elif target and current and tuple(map(int,current.split('.'))) > tuple(map(int,target['version'].split('.'))):
                    state = 'Newer installed'
                row['files'].append({'path': rel.as_posix(), 'component': name,
                                     'current': current or 'Unknown', 'target': target['version'] if target else None,
                                     'before': t.digest(path), 'status': state})
        except Exception as exc:
            row['blocked'] = str(exc)
        rows.append(row)
    return rows


def prepare(config, snapshot, selected):
    """Download selected components and build exact, read-only game plans."""
    engine = engine_bridge.module(config)
    plans = []
    for row in selected:
        t.need(not row['blocked'] and row['files'], 'No eligible runtime selection')
        root = t.safe(row['game'])
        found = discovery.inspect_game(discovery.Game('', row['name'], str(root), 'Folder'))
        t.need(not found.anti_cheat and found.exe, 'Game eligibility changed; scan again')
        changes = []
        inputs = {}
        for item in row['files']:
            rel = t.relative(item['path'])
            path = t.safe(root / rel)
            name = path.name.casefold()
            t.need(name in COMPONENTS and not _private(rel), 'Not a native DLSS target')
            t.need(not _owned(engine, root, path), 'Runtime is owned by the feature provider')
            t.need(t.digest(path) == item['before'], 'Game runtime changed; scan again')
            ui.progress('Preparing '+row['name']+' · '+COMPONENTS[name])
            source = download(config, snapshot['entries'][name])
            after = t.digest(source)
            if after == item['before']:
                continue
            inputs[str(source)] = after
            changes.append({'path': str(rel), 'before': item['before'], 'after': after, 'source': str(source)})
        if changes:
            plan = {'game': str(root), 'name': row['name'], 'listing': t.files(root),
                    'inputs': inputs, 'changes': changes, 'conflicts': [],
                    'runtime_source': {'repository': snapshot['repository'], 'commit': snapshot['commit']}}
            plan['plan_sha256'] = t.sha(json.dumps(plan, sort_keys=True).encode())
            plans.append(plan)
    return plans


def apply(config, plans):
    t.need(plans, 'Selected runtimes already match the source')
    engine = engine_bridge.module(config)
    root = storage(config) / 'runtime-transactions'
    root.mkdir(parents=True, exist_ok=True)
    # Fail preflight for every target before the first game is changed.
    for plan in plans:
        t.check_plan(plan)
        required = sum(Path(change['source']).stat().st_size for change in plan['changes'])
        t.need(shutil.disk_usage(plan['game']).free > required + 64 * 1024 * 1024,
               'Insufficient target space: ' + plan['game'])
    completed = []
    for plan in plans:
        t.need(not engine._running_processes_under_root(Path(plan['game'])), 'Close the selected game before updating')
        # Recheck ownership and eligibility at the write boundary.
        found = discovery.inspect_game(discovery.Game('', plan['name'], plan['game'], 'Folder'))
        t.need(not found.anti_cheat and found.exe, 'Game eligibility changed; scan again')
        for change in plan['changes']:
            path = Path(plan['game']) / t.relative(change['path'])
            t.need(path.name.casefold() in COMPONENTS and not _private(Path(change['path'])), 'Unsupported runtime target')
            t.need(change['before'] is not None, 'Runtime updates only replace existing DLLs')
            t.need(not _owned(engine, Path(plan['game']), path), 'Runtime ownership changed; scan again')
        state = root / uuid.uuid4().hex
        ui.progress('Updating '+plan['name'])
        try:
            t.apply_transaction(plan, state)
        except Exception as exc:
            # The engine retains verified backups; restore a partial game immediately.
            record = state / 'transaction.json'
            if record.exists() and t.read_json(record)['status'] in ('applying', 'interrupted'):
                try:
                    t.rollback_transaction(state, True)
                except Exception as recovery:
                    raise t.Refusal(f'{exc}. Recovery retained at {state}: {recovery}') from exc
            raise t.Refusal(f'{exc}. {len(completed)} earlier games completed; use DLSS Files in Game Details to restore them.') from exc
        completed.append(str(state))
    return completed


def recoveries(config):
    rows = []
    for record in sorted((storage(config) / 'runtime-transactions').glob('*/transaction.json'), reverse=True):
        doc = t.read_json(record)
        if doc['status'] in ('complete', 'applying', 'interrupted'):
            rows.append({'path': str(record.parent), 'name': doc['plan'].get('name', Path(doc['plan']['game']).name),
                         'date': doc['created_utc'], 'status': doc['status']})
    return sorted(rows, key=lambda row: row['date'], reverse=True)


def restore(config, state, apply=False):
    state = t.safe(state)
    t.need(state.parent == storage(config) / 'runtime-transactions', 'Invalid runtime recovery path')
    doc = t.read_json(state / 'transaction.json')
    if apply:
        engine = engine_bridge.module(config)
        root = Path(doc['plan']['game'])
        t.need(not engine._running_processes_under_root(root), 'Close the game before restoring')
        for change in doc['plan']['changes']:
            t.need(not _owned(engine, root, root / t.relative(change['path'])),
                   'Runtime is now owned by the feature provider; restore its stack first')
    return t.rollback_transaction(state, apply)


def manage(config, games):
    """Routine install-time management: update older known native versions only."""
    snapshot = catalog(config)
    selected = []
    skipped = []
    for row in inspect(config, games, snapshot):
        if row['blocked']:
            skipped.append(row['name']+': '+row['blocked'])
            continue
        row['files'] = [item for item in row['files']
                        if item['status'] == 'Update available' and item['current'] != 'Unknown']
        if row['files']:
            selected.append(row)
    plans = prepare(config, snapshot, selected)
    records = apply(config, plans) if plans else []
    return {'updated_games': len(records), 'records': records, 'skipped': skipped}


def game_recoveries(config, game):
    return [record for record in recoveries(config)
               if t.read_json(Path(record['path'])/'transaction.json')['plan']['game'] == str(Path(game).resolve())]


def restore_game(config, game):
    records = game_recoveries(config, game)
    t.need(records, 'No DLSS file backups for this game')
    return restore(config, records[0]['path'], True)
