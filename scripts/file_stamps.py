"""SHA-256 of a file computed once per version of that file.

A version is the file's stamp: its path, size, modified and changed/created
times, and its file identity (inode or NTFS file index, and volume). Writing
or replacing a file changes its stamp, so an unchanged stamp has unchanged
bytes. Library scans and status checks read the digest through the stamp
instead of re-reading multi-gigabyte game files on every refresh. (A tool
that rewrites bytes in place and then sets the old modified time back is not
seen on Windows, whose stat has no change time; that is why the checks before
a write still read the bytes once, below.)

Two ways to ask:

  digest(path)       trusts a stamp seen before, including in an earlier run
                     (kept in file-stamps.json). For status and inspection.
  Operation()        hashes each file once per operation, then trusts the
                     stamp for the rest of that operation. For the checks a
                     review and its execution make before writing; the first
                     check in each still reads the bytes.

Every new digest also feeds the shared cache, so the scan after an install
or repair finds the files it just verified. RTXFORGE_STAMP_CACHE names the
cache file; set it empty to keep digests in memory only.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import stat
import threading
from pathlib import Path

SCHEMA = 1
# Small files are cheaper to hash than to look up and store.
MIN_SIZE = 64 * 1024
MAX_ENTRIES = 50000

_lock = threading.Lock()
_entries: dict[str, list] | None = None
_dirty = False


def _cache_path():
    if os.environ.get('RTXFORGE_STAMP_CACHE') is not None:
        return Path(os.environ['RTXFORGE_STAMP_CACHE']) if os.environ['RTXFORGE_STAMP_CACHE'] else None
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or str(Path.home() / '.cache')
    return Path(base) / 'rtxForge' / 'file-stamps.json'


def _key(path):
    return os.path.normcase(os.path.abspath(path))


def stamp(path):
    """The file's version, or None when it is not a regular file."""
    try:
        info = os.stat(path)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return [info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino, info.st_dev]


def _hash(path):
    with open(path, 'rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _load():
    global _entries
    if _entries is not None:
        return _entries
    _entries = {}
    path = _cache_path()
    if path and path.is_file():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict) and data.get('schema') == SCHEMA and isinstance(data.get('files'), dict):
                _entries = {key: value for key, value in data['files'].items()
                            if isinstance(value, list) and len(value) == 6 and isinstance(value[5], str)}
        except (OSError, ValueError):
            _entries = {}
    return _entries


def _remember(key, version, value):
    global _dirty
    if version[0] < MIN_SIZE:
        return
    with _lock:
        entries = _load()
        if entries.get(key) != [*version, value]:
            entries[key] = [*version, value]
            _dirty = True
            if len(entries) > MAX_ENTRIES:
                for old in list(entries)[:len(entries) - MAX_ENTRIES]:
                    del entries[old]


def _recall(key, version):
    with _lock:
        hit = _load().get(key)
    return hit[5] if hit and hit[:5] == version else None


def _measure(path, key):
    """Hash the bytes, keeping the result only if the file did not change while being read."""
    before = stamp(path)
    if before is None:
        raise FileNotFoundError(path)
    value = _hash(path)
    if stamp(path) == before:
        _remember(key, before, value)
    return value, before


def digest(path):
    """SHA-256 of a regular file, read again only when its stamp changed."""
    key = _key(path)
    version = stamp(path)
    if version is not None:
        hit = _recall(key, version)
        if hit:
            return hit
    return _measure(path, key)[0]


def save():
    """Write new digests to the cache file. A failure only costs a re-hash next run."""
    global _dirty
    path = _cache_path()
    with _lock:
        if not _dirty or path is None or _entries is None:
            return
        payload = json.dumps({'schema': SCHEMA, 'files': _entries}, separators=(',', ':'))
        _dirty = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
        temporary.write_text(payload, encoding='utf-8')
        os.replace(temporary, path)
    except OSError:
        pass


atexit.register(save)


def forget():
    """Drop every remembered digest (tests, and a cache reset)."""
    global _entries, _dirty
    with _lock:
        _entries, _dirty = None, False


class Operation:
    """Digests for one review or one execution: each file is read once, then its stamp is trusted."""

    def __init__(self):
        self._seen: dict[str, tuple] = {}

    def digest(self, path):
        key = _key(path)
        version = stamp(path)
        seen = self._seen.get(key)
        if version is not None and seen and seen[0] == version:
            return seen[1]
        value, version = _measure(path, key)
        self._seen[key] = (version, value)
        return value

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        save()
        return False
