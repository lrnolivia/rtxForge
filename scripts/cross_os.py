"""The install record both rtxForge builds read, kept beside the game's files.

Each OS keeps its own engine state (baselines, backups) where the other cannot
see it, but dual-boot libraries share the game folders. After an install,
rtxForge writes <game>/.rtxforge-install.json naming the OS, the package and
every managed file with its SHA-256, and copies its baseline (the backups of
the game's original files) to <game>/.rtxforge/state. Whichever OS runs the
game next adapts the install instead of refusing it: it adopts that state as
its own (engine_bridge.adopt), adds only what it needs to load the features
(Linux: the Proton setting; Windows: nothing), and can then repair, retune or
restore the original files exactly as the installing OS could. The last OS to
change the install writes the record and the shared state again.

Schema 2 (shared with windows/engine-host):
{
  "schema": 2, "os": "linux" | "windows", "app_version": "...", "installed_at": "ISO-8601",
  "revision": "<hex>",                  # matches the shared state's cross_os_revision
  "shared_state": true,                 # .rtxforge/state holds the baseline and original files
  "provider": {"id": "...", "name": "...", "version": "..."}, "feature_mode": "mfg-only",
  "proxy": "dxgi.dll", "files": {"<path relative to the game folder, '/' separated>": "<sha256>"},
  "proton_overrides": ["dxgi"]          # DLLs Proton must load natively (Linux only)
}
Schema 1 records (no shared state) are still recognised.
"""
from pathlib import Path, PurePosixPath
import datetime, hashlib, json, os, shutil, tempfile, uuid

MARKER = '.rtxforge-install.json'
SHARED = '.rtxforge'
SCHEMA = 2
SCHEMAS = (1, 2)
OPERATING_SYSTEMS = ('linux', 'windows')
# The same scripts run under windows/engine-host, so the OS is detected, never assumed.
THIS_OS = 'windows' if os.name == 'nt' else 'linux'
OTHER_OS = 'linux' if THIS_OS == 'windows' else 'windows'
# Placeholders for the two absolute roots a baseline refers to; each OS fills in its own.
STATE_TOKEN = '{rtxforge-state}'
TARGET_TOKEN = '{rtxforge-target}'


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def managed_files(target, names):
    """{relative path: sha256} for managed files and the files inside managed folders."""
    target = Path(target)
    files = {}
    for name in names:
        path = target / name
        if path.is_symlink():
            continue
        if path.is_file():
            files[Path(name).as_posix()] = _sha256(path)
        elif path.is_dir():
            for child in sorted(path.rglob('*')):
                if child.is_file() and not child.is_symlink():
                    files[child.relative_to(target).as_posix()] = _sha256(child)
    return files


def new_revision():
    return uuid.uuid4().hex


def write(target, os_name, names, provider, feature_mode, proxy, proton_overrides=(), app_version='',
          revision=None, shared_state=False):
    if os_name not in OPERATING_SYSTEMS:
        raise ValueError('Unknown operating system: ' + str(os_name))
    record = {
        'schema': SCHEMA, 'os': os_name, 'app_version': app_version,
        'installed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'revision': revision or new_revision(), 'shared_state': bool(shared_state),
        'provider': {key: provider.get(key, '') for key in ('id', 'name', 'version')},
        'feature_mode': feature_mode, 'proxy': proxy,
        'files': managed_files(target, names),
        'proton_overrides': list(proton_overrides),
    }
    path = Path(target) / MARKER
    fd, temporary = tempfile.mkstemp(prefix='.rtxforge-', dir=target)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(record, handle, indent=1, sort_keys=True)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return record


def read(target):
    """The record, or None when absent or not one this version understands."""
    path = Path(target) / MARKER
    if not path.is_file() or path.is_symlink():
        return None
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or record.get('schema') not in SCHEMAS or record.get('os') not in OPERATING_SYSTEMS:
        return None
    if not isinstance(record.get('files'), dict) or not record['files']:
        return None
    return record


def intact(target, record):
    """True when every managed file is still exactly what the installing OS wrote."""
    target = Path(target)
    for name, digest in record['files'].items():
        path = target / name
        if '..' in Path(name).parts or path.is_symlink() or not path.is_file():
            return False
        if _sha256(path) != digest:
            return False
    return True


def remove(target, os_name):
    """Drop the record and the shared state after a restore, only when this OS owns them."""
    record = read(target)
    if record and record['os'] == os_name:
        (Path(target) / MARKER).unlink(missing_ok=True)
        shared = Path(target) / SHARED
        if shared.is_dir() and not shared.is_symlink():
            shutil.rmtree(shared)
        return True
    return False


def other_install(target, this_os):
    """The other OS's intact install in this folder, or None."""
    record = read(target)
    if not record or record['os'] == this_os:
        return None
    return record if intact(target, record) else None


# ---------- shared state: the installing OS's baseline, portable ----------

def shared_state(target):
    return Path(target) / SHARED / 'state'


def adoptable(target, this_os, revision=None):
    """The other OS's intact install with shared state this OS has not adopted yet, or None.

    revision is the cross_os_revision of this OS's own baseline, if it has one.
    """
    record = other_install(target, this_os)
    if not record or not record.get('shared_state') or record.get('revision') == revision:
        return None
    state = shared_state(target)
    if Path(target, SHARED).is_symlink() or state.is_symlink() or not (state / 'baseline.json').is_file():
        return None
    return record


def _under(path, root):
    try:
        return PurePosixPath(Path(path).relative_to(root).as_posix())
    except ValueError:
        return None


def portable(value, state_dir, target):
    """The baseline with this OS's state and game paths replaced by placeholders."""
    if isinstance(value, dict):
        return {k: portable(v, state_dir, target) for k, v in value.items()}
    if isinstance(value, list):
        return [portable(v, state_dir, target) for v in value]
    if isinstance(value, str) and value and Path(value).is_absolute():
        for token, root in ((STATE_TOKEN, Path(state_dir)), (TARGET_TOKEN, Path(target))):
            rel = _under(value, root)
            if rel is not None:
                return token if str(rel) == '.' else token + '/' + str(rel)
    return value


def localize(value, state_dir, target):
    """Fill the placeholders with this OS's state and game paths."""
    if isinstance(value, dict):
        return {k: localize(v, state_dir, target) for k, v in value.items()}
    if isinstance(value, list):
        return [localize(v, state_dir, target) for v in value]
    if isinstance(value, str):
        for token, root in ((STATE_TOKEN, Path(state_dir)), (TARGET_TOKEN, Path(target))):
            if value == token:
                return str(root)
            if value.startswith(token + '/'):
                parts = PurePosixPath(value[len(token) + 1:]).parts
                if any(part in ('', '.', '..') for part in parts):
                    raise ValueError('Unsafe shared state path: ' + value)
                return str(root.joinpath(*parts))
    return value


def export_state(target, state_dir, baseline, revision, extras):
    """Copy this OS's baseline and its original-file backups into the game folder."""
    target = Path(target)
    shared = target / SHARED
    if shared.is_symlink():
        raise ValueError('Linked shared state refused: ' + str(shared))
    shared.mkdir(exist_ok=True)
    state = shared_state(target)
    staging = shared / 'state.new'
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    backups = Path(state_dir) / 'baseline-backup'
    if backups.is_dir():
        shutil.copytree(backups, staging / 'baseline-backup', symlinks=True)
    data = portable(baseline, state_dir, target)
    # What only one OS uses (its Steam launch settings) travels along for when it adopts again.
    data.pop('steam_launch', None)
    data['cross_os_extras'] = extras
    data['cross_os_revision'] = revision
    (staging / 'baseline.json').write_text(json.dumps(data, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    if state.exists():
        shutil.rmtree(state)
    os.replace(staging, state)


def import_state(target, state_dir, revision):
    """The shared baseline for this OS's state_dir, with its backups copied in.

    state_dir must not exist yet. The caller verifies the result with the engine.
    """
    state = shared_state(target)
    data = json.loads((state / 'baseline.json').read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('cross_os_revision') != revision:
        raise ValueError('The shared install state does not match its record; restore it where it was installed')
    baseline = localize(data, state_dir, target)
    state_dir = Path(state_dir)
    if state_dir.exists():
        raise ValueError('Install state already exists: ' + str(state_dir))
    state_dir.mkdir(parents=True)
    if (state / 'baseline-backup').is_dir():
        shutil.copytree(state / 'baseline-backup', state_dir / 'baseline-backup', symlinks=True)
    return baseline
