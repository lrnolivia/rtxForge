"""App-data accounting and one-shot cleanup of unreferenced download caches.

Recovery records, transaction originals, Feeder's content store, baselines,
settings and imported packages are never cleanup targets. No age-based backup
pruning: those files can be the only way to restore an installed game.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat


class StorageError(ValueError):
    pass


CACHES = {
    'package-downloads': ('state', 'packages'),
    'dlss-downloads': ('state', 'runtime-cache'),
}
CATEGORIES = {
    'package-downloads': ('Package downloads', 'Unused downloaded packages; needed again for future installs.', True),
    'dlss-downloads': ('DLSS downloads', 'Unused downloaded DLSS files; needed again for future updates.', True),
    'recovery': ('App recovery', 'Saved app builds and recovery snapshots. Kept.', False),
    'runtime-backups': ('DLSS restore backups', 'Original game files needed to undo DLSS updates. Kept.', False),
    'game-backups': ('Package restore backups', 'Original files and installation records. Kept.', False),
    'feeder-restore': ('Feeder restore files', 'Shared Feeder files, including original game files. Kept.', False),
    'operation-backups': ('Operation recovery', 'Saved files from previous or interrupted operations. Kept.', False),
    'other': ('Settings and other data', 'Library data, artwork, settings and other app files. Kept.', False),
}
MAX_ENTRIES = 200_000
MAX_JSON = 8 * 1024 * 1024


def size_label(value):
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or unit == 'TiB':
            return f'{value:.1f} {unit}' if unit != 'B' else f'{value} B'
        value /= 1024


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _identity(info):
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))


def _stamp(info):
    return (*_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def _anchors(root):
    root = Path(os.path.abspath(root))
    result = []
    for path in [*reversed(root.parents), root]:
        info = path.lstat()
        if _linked(info) or not stat.S_ISDIR(info.st_mode):
            raise StorageError('App storage contains a linked directory. Cleanup was refused.')
        result.append((str(path), _identity(info)))
    return tuple(result)


def _category(parts):
    if parts[:1] == ('recovery',):
        return 'recovery'
    for key, prefix in {**CACHES, 'runtime-backups': ('state', 'runtime-transactions'),
                        'game-backups': ('engine-state', 'targets'),
                        'feeder-restore': ('engine-state', 'feeder-cache'),
                        'operation-backups': ('engine-state', 'desktop-operations')}.items():
        if parts[:len(prefix)] == prefix:
            return key
    return 'other'


def _walk(root):
    """lstat every entry; never descend through a Windows junction or symlink."""
    count = 0
    pending = [(root, ())]
    while pending:
        directory, parent = pending.pop()
        if len(parent) > 64:
            raise StorageError('App storage is nested too deeply to review safely.')
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda e: e.name.casefold()):
                count += 1
                if count > MAX_ENTRIES:
                    raise StorageError('App storage has too many entries for one cleanup review.')
                # DirEntry.stat on Windows can omit file IDs and link counts;
                # lstat supplies the identity used for review and hardlink safety.
                info = Path(entry.path).lstat()
                parts = (*parent, entry.name)
                if _linked(info):
                    raise StorageError('App storage contains a linked file or folder. Cleanup was refused.')
                if stat.S_ISDIR(info.st_mode):
                    yield parts, info
                    pending.append((Path(entry.path), parts))
                elif stat.S_ISREG(info.st_mode):
                    yield parts, info
                else:
                    raise StorageError('App storage contains a special file. Cleanup was refused.')


@dataclass(frozen=True)
class Snapshot:
    root: str
    anchors: tuple
    caches: tuple
    references: tuple
    files: tuple
    categories: tuple


def _inspect(root):
    root = Path(os.path.abspath(root))
    anchors = _anchors(root)
    totals = {key: {'key': key, 'title': title, 'detail': detail, 'cache': cache,
                    'bytes': 0, 'files': 0, 'cleanable_bytes': 0}
              for key, (title, detail, cache) in CATEGORIES.items()}
    files, caches, references, paths, hashes = [], [], [], set(), set()
    cache_roots = [os.path.normcase(str(root.joinpath(*parts))) for parts in CACHES.values()]
    for parts, info in _walk(root):
        key = _category(parts)
        regular = stat.S_ISREG(info.st_mode)
        if regular:
            totals[key]['bytes'] += info.st_size
            totals[key]['files'] += 1
        if key in CACHES:
            caches.append((parts, _stamp(info)))
            if regular:
                if parts[-1].endswith('.part') or parts[-1].startswith('.download-'):
                    raise StorageError('A package download is unfinished. Finish it, then review cleanup again.')
                files.append((parts, info.st_size, info.st_nlink))
        elif regular and parts[-1].lower().endswith('.json'):
            # Local package/model paths and baseline cache references remain usable
            # offline. Hash references also retain their content-addressed bucket.
            if info.st_size > MAX_JSON:
                raise StorageError('A storage record is too large to check safely. Cleanup was refused.')
            data = root.joinpath(*parts).read_bytes()
            if _stamp(root.joinpath(*parts).lstat()) != _stamp(info):
                raise StorageError('App data changed while checking it. Review cleanup again.')
            try:
                document = json.loads(data.decode('utf-8-sig'))
            except (ValueError, UnicodeError):
                raise StorageError('An app storage record could not be read. Cleanup was refused.') from None
            references.append((parts, hashlib.sha256(data).hexdigest()))
            values = [document]
            while values:
                value = values.pop()
                if isinstance(value, dict):
                    values.extend(value.values())
                elif isinstance(value, list):
                    values.extend(value)
                elif isinstance(value, str):
                    if len(value) in (40, 64) and all(c in '0123456789abcdefABCDEF' for c in value):
                        hashes.add(value.lower())
                    if os.path.isabs(value):
                        candidate = os.path.normcase(os.path.abspath(value))
                        # A diagnostic mentioning the app-data root is not a
                        # reference to every download. Local sources must name
                        # a path inside one of the actual cache namespaces.
                        if any(candidate == c or candidate.startswith(c + os.sep) for c in cache_roots):
                            paths.add(candidate)
    selected = []
    for parts, size, links in files:
        absolute = os.path.normcase(str(root.joinpath(*parts)))
        referenced = any(absolute == p or absolute.startswith(p + os.sep) for p in paths)
        if links > 1 or referenced or any(part.lower() in hashes for part in parts):
            continue
        selected.append(parts)
        totals[_category(parts)]['cleanable_bytes'] += size
    return Snapshot(str(root), anchors, tuple(sorted(caches)), tuple(sorted(references)),
                    tuple(sorted(selected)), tuple(totals.values()))


def inventory(root):
    """Fast accounting only: never reads DLL contents or changes files."""
    root = Path(os.path.abspath(root))
    totals = {key: dict(key=key, title=v[0], detail=v[1], cache=v[2], bytes=0, files=0) for key, v in CATEGORIES.items()}
    if not root.exists():
        return {'bytes': 0, 'categories': list(totals.values()), 'warning': None}
    warning = None
    try:
        _anchors(root)
        for parts, info in _walk(root):
            if stat.S_ISREG(info.st_mode):
                item = totals[_category(parts)]
                item['bytes'] += info.st_size
                item['files'] += 1
    except (OSError, StorageError) as error:
        warning = f'Could not count all app data: {error}'
    return {'bytes': sum(c['bytes'] for c in totals.values()), 'categories': list(totals.values()), 'warning': warning}


def prepare(root):
    return _inspect(root)


def execute(root, plan):
    """Recheck every cache and every persisted reference before any unlink."""
    if not isinstance(plan, Snapshot) or plan.root != str(Path(os.path.abspath(root))):
        raise StorageError('This storage review does not belong to this app.')
    fresh = _inspect(root)
    if (fresh.anchors, fresh.caches, fresh.references, fresh.files) != (plan.anchors, plan.caches, plan.references, plan.files):
        raise StorageError('App data changed since review. Nothing was removed. Review cleanup again.')
    stamps = dict(plan.caches)
    removed = 0
    for parts in plan.files:
        # Even an internally corrupted review cannot select a protected namespace.
        if _category(parts) not in CACHES or any(p in ('', '.', '..') or '/' in p or '\\' in p for p in parts):
            raise StorageError('Cleanup target is outside the download caches.')
    for parts in plan.files:
        _anchors(Path(root).joinpath(*parts).parent)
        path = Path(root).joinpath(*parts)
        info = path.lstat()
        if _linked(info) or not stat.S_ISREG(info.st_mode) or _stamp(info) != stamps[parts]:
            raise StorageError('A download changed during cleanup. Review the remaining files again.')
        path.unlink()
        removed += stamps[parts][3]
    # Empty directories have negligible size; leave them in place rather than
    # racing a download that may have started after review.
    return {'message': f'Freed {size_label(removed)} of downloaded files. Restore backups and settings were kept.',
            'bytes': removed, 'files': len(plan.files)}
