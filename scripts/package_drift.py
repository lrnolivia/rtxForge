"""Changed OptiScaler package files: one Repair away, not a broken game.

The scan compares each file an OptiScaler install owns with its install
record, through the stamp cache. A file not hashed before is hashed on a
background thread instead of in the scan, so a later refresh has the answer
and the scan stays fast. Settings and logs change in normal use and are not
compared. Feeder reports its own drift (feeder_provider); Vulkan routes keep
their own records.
"""
from pathlib import Path

import file_stamps
import transactions as t

SKIP = ('.ini', '.log')
OTHER_RECORDS = (None, 'feeder', 'vulkan-native')
# Every refresh keeps the game's NR model as found, so Repair records a
# different one instead of replacing it.
KEPT_AS_FOUND = {'nvngx_dlssnr.dll'}


def summary(files):
    names = ', '.join(item['name'] for item in files)
    if all(item['fix'] == 'record' for item in files):
        return f'{names} differs from this install record. Repair records it; nothing is replaced.'
    if all(item['fix'] == 'missing' for item in files):
        lead = f'{len(files)} package files are missing' if len(files) > 1 else 'A package file is missing'
    else:
        lead = f'{len(files)} package files changed' if len(files) > 1 else 'A package file changed'
    return f"{lead} ({names}). Repair puts back rtxForge's copy; your settings are kept."


def check(e, target, set_aside=frozenset()):
    """Changed or missing owned files of an active install, or None when unknown.

    set_aside: OptiScaler files the game's NR add-ons moved out on purpose (nr_install).
    """
    target = t.safe(target)
    baseline = e.load_baseline(target, readonly=True)
    if not baseline or baseline.get('status') != 'active':
        return None
    hashes = (baseline.get('current') or {}).get('installed_hashes') or {}
    t.need(isinstance(hashes, dict), 'Installed file record is corrupt')
    files, unknown = [], []
    for name, expected in sorted(hashes.items()):
        if name.casefold().endswith(SKIP) or name.replace('\\', '/').casefold() in set_aside:
            continue
        path = t.safe(target / t.relative(name))
        if not path.is_relative_to(target):
            continue
        if not path.is_file():
            files.append({'name': name, 'fix': 'missing'})
            continue
        actual = file_stamps.known(path)
        if actual is None:
            unknown.append(path)
        elif actual != expected:
            files.append({'name': name, 'fix': 'record' if name.casefold() in KEPT_AS_FOUND else 'restore'})
    if unknown:
        file_stamps.warm(unknown)
    return files


def decorate(e, rows):
    for row in rows:
        if (not row.get('installed') or row.get('blocked') or not row.get('exe')
                or row.get('runtime_provider') in OTHER_RECORDS or row.get('feeder_drift')):
            continue
        try:
            import nr_install
            aside = {name.casefold() for name in nr_install.set_aside_files(row)}
            files = check(e, (Path(row['game']) / row['exe']).parent, aside)
        except (t.Refusal, getattr(e, 'Stop', RuntimeError), OSError, ValueError):
            continue
        if files:
            row['package_drift'] = {'files': files, 'summary': summary(files)}
    return rows
