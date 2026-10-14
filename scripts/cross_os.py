"""The install record both rtxForge builds read, kept beside the game's files.

Each OS keeps its own engine state (baselines, backups) where the other cannot
see it, but dual-boot libraries share the game folders. After an install,
rtxForge writes <game>/.rtxforge-install.json naming the OS, the package and
every managed file with its SHA-256. The other OS uses it to recognise the
install instead of treating OptiScaler as an unknown tool, and to adapt it:
Linux adds only the Proton setting a Windows install needs; Windows loads a
Linux install natively. Original files are backed up on the installing OS, so
restoring them happens there.

Schema 1 (shared with windows/engine-host):
{
  "schema": 1, "os": "linux" | "windows", "app_version": "...", "installed_at": "ISO-8601",
  "provider": {"id": "...", "name": "...", "version": "..."}, "feature_mode": "mfg-only",
  "proxy": "dxgi.dll", "files": {"<path relative to the game folder, '/' separated>": "<sha256>"},
  "proton_overrides": ["dxgi"]          # DLLs Proton must load natively (Linux only)
}
"""
from pathlib import Path
import datetime, hashlib, json, os, tempfile

MARKER = '.rtxforge-install.json'
SCHEMA = 1
OPERATING_SYSTEMS = ('linux', 'windows')
# The same scripts run under windows/engine-host, so the OS is detected, never assumed.
THIS_OS = 'windows' if os.name == 'nt' else 'linux'
OTHER_OS = 'linux' if THIS_OS == 'windows' else 'windows'


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


def write(target, os_name, names, provider, feature_mode, proxy, proton_overrides=(), app_version=''):
    if os_name not in OPERATING_SYSTEMS:
        raise ValueError('Unknown operating system: ' + str(os_name))
    record = {
        'schema': SCHEMA, 'os': os_name, 'app_version': app_version,
        'installed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
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
    if not isinstance(record, dict) or record.get('schema') != SCHEMA or record.get('os') not in OPERATING_SYSTEMS:
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
    """Drop the record after a restore, only when this OS wrote it."""
    record = read(target)
    if record and record['os'] == os_name:
        (Path(target) / MARKER).unlink(missing_ok=True)
        return True
    return False


def other_install(target, this_os):
    """The other OS's intact install in this folder, or None."""
    record = read(target)
    if not record or record['os'] == this_os:
        return None
    return record if intact(target, record) else None
