"""Validate: look in a game's own logs for proof that NR or MFG ran.

Read only. It opens bounded log tails beside the game's executable, never writes
game files, never takes the writer gate and never changes the result the person
chose; it only records what it found next to the test record, for Confirm.
Proof is what the runtimes themselves log while running, the same evidence the
functional test uses: NR evaluations (OptiScaler GPU windows, Feeder feature 18,
native Vulkan NR) and generated frames actually presented (DLSS-G state samples
or native Vulkan frame statistics). A setting or a DLL on disk is never proof.
"""
import datetime
import re
import time

import cross_os
import functional_test
import game_notes
import runtime_diagnostics

# Written by the Universal MFG plugin (RTXMFG-<exe>-<hash>.log) while DLSS-G runs.
DLSSG_SAMPLE = re.compile(r'DLSS-G state sample: frames presented since prior query=(\d+)'
                          r'\s*\(maximum generated per real frame=(\d+), status=(\d+)\)')


def _tail(path):
    try:
        data, info = runtime_diagnostics.read_regular(path, functional_test.LOG_LIMIT, tail=True)
    except (OSError, ValueError):
        return '', 0.0
    return data.decode('utf-8', errors='replace'), info.st_mtime


def _installed_at(record):
    try:
        return datetime.datetime.fromisoformat(str(record.get('installed_at'))).timestamp()
    except (TypeError, ValueError):
        return 0.0


def scan(row):
    """What this game's logs prove ran, from logs written after the current install."""
    target = functional_test.directory(row)
    record = cross_os.read(target) or {}
    route = (record.get('provider') or {}).get('id') or row.get('runtime_provider') or 'unknown'
    since = _installed_at(record)
    logs, newest = {}, 0.0
    for name in functional_test.LOG_NAMES:
        text, modified = _tail(target / name)
        # A log from before this install says nothing about what is installed now.
        if text and modified >= since:
            logs[name] = text
            newest = max(newest, modified)
    plugin = []
    for path in sorted(target.glob('RTXMFG-*.log')):
        if path.name.endswith('.previous.log'):
            continue
        text, modified = _tail(path)
        if text and modified >= since:
            plugin.append(text)
            newest = max(newest, modified)
    evidence = functional_test.log_evidence(logs, route)
    found, details = [], []
    if evidence.get('nr_evaluated'):
        found.append('NR')
        details.append(str(evidence.get('nr_detail') or 'NR evaluations logged.'))
    samples = [(int(a), int(b), int(c)) for a, b, c in DLSSG_SAMPLE.findall('\n'.join(plugin))]
    presented = [count for count, _, status in samples if count > 1 and status == 0]
    stats = evidence.get('mfg_stats')
    if presented:
        found.append('MFG')
        details.append(f'Frame generation presented up to {max(presented)} frames per rendered frame.')
    elif stats and stats[1] > stats[0] and stats[3] == 0:
        found.append('MFG')
        details.append(f'Frame generation presented {stats[2]:.1f}x.')
    return {'found': found, 'route': route, 'details': details,
            'log_time': newest or None, 'checked': time.time()}


def validate(config, row):
    """Scan, keep the result with the game's test record, and return the record."""
    record = game_notes.load(config, row['game'])
    # A running test session owns its record until Finish Test.
    if record.get('active'):
        return record
    result = scan(row)
    record['validation'] = result
    game_notes.save(config, row['game'], record)
    return record


def validate_all(config, rows):
    """The quiet check at app start: every installed game, one at a time, never failing the batch."""
    records = {}
    for row in rows:
        try:
            records[row['game']] = validate(config, row)
        except Exception:
            continue
    return records


def summary(found):
    """'NR and MFG' style wording for what was found."""
    return ' and '.join(found)
