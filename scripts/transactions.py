"""Portable hash-guarded transactions used by the v1.6 live tool."""
from __future__ import annotations
import argparse, contextlib, configparser, datetime, hashlib, json, os, pathlib, re, shutil, stat, struct, sys, uuid
P = pathlib.Path
HERE = P(__file__).resolve().parent
PROXIES = {'dxgi.dll', 'winmm.dll', 'version.dll', 'dbghelp.dll', 'd3d12.dll', 'wininet.dll', 'winhttp.dll', 'd3d9.dll', 'd3d10.dll', 'd3d11.dll', 'opengl32.dll', 'dinput8.dll', 'dsound.dll'}
SUPPORTED_PROXIES = {'dxgi.dll', 'winmm.dll', 'version.dll'}
NATIVE = {'nvngx_dlss.dll', 'nvngx_dlssg.dll', 'nvngx_dlssd.dll'}
MODEL_SIZE = 165840496
MAX_BACKUP = 1024 ** 3

class Refusal(RuntimeError):
    pass

def need(ok, why):
    if not ok:
        raise Refusal(why)

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def digest(p):
    with P(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read_json(p):
    return json.loads(P(p).read_text(encoding='utf-8-sig'))

def relative(s):
    need(isinstance(s, str) and s and ('\\' not in s) and (':' not in s), 'Unsafe relative path')
    p = pathlib.PurePosixPath(s)
    need(not p.is_absolute() and all((x not in ('', '.', '..') for x in s.split('/'))), 'Unsafe relative path')
    need(all((not x.endswith((' ', '.')) and (not re.match('(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\\.|$)', x)) for x in p.parts)), 'Windows ambiguous path')
    return p

def safe(p):
    p = P(os.path.abspath(p))
    need(p == p.resolve(), 'Symlink/path alias refused: ' + str(p))
    for part in [p, *p.parents]:
        if part.exists():
            st = part.lstat()
            need(not stat.S_ISLNK(st.st_mode) and (not getattr(st, 'st_file_attributes', 0) & 1024), 'Link/reparse point refused')
    if p.exists():
        st = p.stat()
        need(p.is_dir() or (stat.S_ISREG(st.st_mode) and st.st_nlink == 1), 'Special/shared file refused')
    return p

def files(root):
    root = safe(root)
    need(root.is_dir(), 'Directory absent: ' + str(root))
    out = {}
    for base, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            p = safe(P(base) / name)
            r = p.relative_to(root).as_posix()
            relative(r)
            key = r.casefold()
            need(key not in out, 'Case collision: ' + r)
            out[key] = r
    return {k: v for k, v in out.items() if (root / v).is_file()}

def ini(text):
    c = configparser.ConfigParser(interpolation=None, strict=True)
    c.optionxform = str
    c.read_string(text)
    need(len({s.casefold() for s in c.sections()}) == len(c.sections()), 'Duplicate INI section')
    for s in c.sections():
        need(len({k.casefold() for k in c[s]}) == len(c[s]), 'Duplicate INI key')
    return c

def section(text, name):
    ini(text)
    m = re.search('(?ims)^\\s*\\[' + re.escape(name) + '\\][^\\r\\n]*\\r?\\n.*?(?=^\\s*\\[[^\\]]+\\]|\\Z)', text)
    return m.group() if m else None

def setvalue(text, sect, key, val):
    block = section(text, sect)
    if block is None:
        return text.rstrip() + '\n\n[' + sect + ']\n' + key + '=' + val + '\n'
    pattern = '(?im)^[ \\t]*' + re.escape(key) + '[ \\t]*=.*$'
    new = re.sub(pattern, key + '=' + val, block) if re.search(pattern, block) else block.rstrip() + '\n' + key + '=' + val + '\n\n'
    return text.replace(block, new, 1)

def executable_check(path):
    with P(path).open('rb') as f:
        header = f.read(64)
        need(len(header) == 64 and header[:2] == b'MZ', 'Executable is not a Windows PE file')
        offset = struct.unpack_from('<I', header, 60)[0]
        need(64 <= offset <= 1024 ** 2, 'Invalid PE header offset')
        f.seek(offset)
        pe = f.read(6)
        need(pe[:4] == b'PE\x00\x00' and pe[4:] == b'd\x86', 'Only x64 Windows games are supported')

def check_plan(plan):
    copy = dict(plan)
    h = copy.pop('plan_sha256', None)
    need(h == sha(json.dumps(copy, sort_keys=True).encode()), 'Plan integrity mismatch')
    need(not plan['conflicts'], 'Plan has conflicts')
    root = safe(plan['game'])
    need(files(root) == plan['listing'], 'Game file listing changed since preview')
    for p, h in plan['inputs'].items():
        need(safe(p).is_file() and digest(p) == h, 'Input drift: ' + p)
    seen = set()
    for r in plan['changes']:
        relative(r['path'])
        key = r['path'].casefold()
        need(key not in seen, 'Duplicate change')
        seen.add(key)
        p = safe(root / r['path'])
        current = digest(p) if p.exists() else None
        need(current == r['before'], 'Target drift: ' + r['path'])
        if r['after'] is not None:
            data = P(r['source']).read_bytes() if 'source' in r else r['text'].encode()
            need(sha(data) == r['after'], 'Planned content drift')
    return root

def save_new(path, obj):
    with safe(path).open('x', encoding='utf-8') as f:
        json.dump(obj, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())

def record_write(path, obj):
    temp = safe(path.with_name(path.name + '.new'))
    save_new(temp, obj)
    os.replace(temp, path)

def atomic_file(path, data, mode):
    path = safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = safe(path.with_name('.opti-' + uuid.uuid4().hex + '.tmp'))
    with tmp.open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, path)

def _apply_transaction(plan, state):
    """Internal transaction engine; caller enforces explicit user confirmation and storage/target policy."""
    root = check_plan(plan)
    state = safe(state)
    need(not state.exists(), 'Transaction directory must be new')
    need(not state.is_relative_to(root) and (not root.is_relative_to(state)), 'Backup and game overlap')
    total = sum(((root / r['path']).stat().st_size for r in plan['changes'] if r['before'] is not None))
    need(total <= MAX_BACKUP, 'Backup exceeds 1 GiB bound; explicit redesign required')
    need(shutil.disk_usage(state.parent).free > total * 2 + sum((P(r['source']).stat().st_size if 'source' in r else len(r.get('text', '').encode()) for r in plan['changes'])) + 64 * 1024 ** 2, 'Insufficient transaction space')
    state.mkdir()
    (state / 'backups').mkdir()
    record = {'schema': 1, 'status': 'preparing', 'created_utc': now(), 'plan': plan, 'modes': {}}
    save_new(state / 'transaction.json', record)
    for i, r in enumerate(plan['changes']):
        p = root / r['path']
        if r['before'] is not None:
            record['modes'][r['path']] = stat.S_IMODE(p.stat().st_mode)
            with (state / 'backups' / str(i)).open('xb') as f:
                with p.open('rb') as src:
                    shutil.copyfileobj(src, f)
                f.flush()
                os.fsync(f.fileno())
            need(digest(state / 'backups' / str(i)) == r['before'], 'Backup verification failed')
    check_plan(plan)
    record['status'] = 'applying'
    record_write(state / 'transaction.json', record)
    try:
        for r in plan['changes']:
            p = safe(root / r['path'])
            need((digest(p) if p.exists() else None) == r['before'], 'Concurrent target drift')
            if r['after'] is None:
                p.unlink()
            else:
                data = P(r['source']).read_bytes() if 'source' in r else r['text'].encode()
                need(sha(data) == r['after'], 'Source changed during apply')
                atomic_file(p, data, r.get('write_mode', record['modes'].get(r['path'], 420)))
                need(digest(p) == r['after'], 'Write verification failed')
        record['status'] = 'complete'
        record['completed_utc'] = now()
        record_write(state / 'transaction.json', record)
    except BaseException:
        record['status'] = 'interrupted'
        record_write(state / 'transaction.json', record)
        raise
    return record

def _rollback_transaction(state, apply=False):
    state = safe(state)
    record = read_json(state / 'transaction.json')
    plan = record['plan']
    root = safe(plan['game'])
    need(record['status'] in ('complete', 'applying', 'interrupted'), 'Transaction not eligible for rollback')
    actions = []
    for i, r in enumerate(plan['changes']):
        relative(r['path'])
        p = safe(root / r['path'])
        current = digest(p) if p.exists() else None
        need(current in (r['after'], r['before']), 'Rollback drift: ' + r['path'])
        backup = safe(state / 'backups' / str(i))
        if r['before'] is not None:
            need(backup.is_file() and digest(backup) == r['before'], 'Backup damaged/missing: ' + r['path'])
        parts=P(r['path'].lower()).parts
        native=parts[-1] in {'nvngx_dlss.dll','nvngx_dlssd.dll','nvngx_dlssg.dll','nvapi64.dll'} or parts[-1].startswith('sl.')
        need(not (native and 'optiscaler' not in parts and r['before'] is None and current is not None), 'Refusing to remove native NVIDIA/Streamline file without an original backup: '+r['path'])
        if current != r['before'] or (r['before'] is not None and stat.S_IMODE(p.stat().st_mode) != record['modes'][r['path']]):
            actions.append((r, p, backup, current))
    if not apply:
        return {'action': 'rollback-preview', 'files': [r['path'] for r, _, _, _ in actions], 'game': str(root)}
    for r, p, b, current in reversed(actions):
        need((digest(safe(p)) if p.exists() else None) == current, 'Concurrent rollback drift')
        if r['before'] is None:
            p.unlink()
        else:
            atomic_file(p, b.read_bytes(), record['modes'][r['path']])
    record['status'] = 'rolled-back'
    record['rollback_utc'] = now()
    record_write(state / 'transaction.json', record)
    return {'status': 'rolled-back', 'restored_files': len(actions)}

@contextlib.contextmanager
def transaction_lock(state):
    lock = safe(P(state).parent / '.optiscaler-operation.lock')
    try:
        with lock.open('x') as f:
            f.write(str(os.getpid()))
    except FileExistsError:
        raise Refusal('Another transaction or stale operation lock exists; inspect recovery state first')
    try:
        yield
    finally:
        lock.unlink()

def apply_transaction(plan, state):
    with transaction_lock(state):
        return _apply_transaction(plan, state)

def rollback_transaction(state, apply=False):
    if not apply:
        return _rollback_transaction(state, False)
    with transaction_lock(state):
        return _rollback_transaction(state, True)
