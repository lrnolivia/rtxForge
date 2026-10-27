#!/usr/bin/env python3
"""Shared rules for the two-OS 'beta' GitHub release.

Windows and Linux publish into the same release from separate workflows. Each
OS owns only its own asset names and its own source line in the notes, so one
OS can publish without touching, counting or discarding the other's files.

  owned <windows|linux> <release.json>        current (non-rollback) assets the OS owns
  source <windows|linux> <release.json>       source commit of the OS's current build
  notes <windows|linux> <base.md> <release.json|-> <version> <sha> <build-url> [extra]
"""
import json
import re
import sys
from pathlib import Path

OSES = ('windows', 'linux')
LABELS = {'windows': 'Windows', 'linux': 'Linux'}
PREVIOUS = '.previous-'
OWNED = {
    'windows': re.compile(r'^rtxForge-(?:Setup|windows)-1\.0\.0-beta\.\d+-'),
    'linux': re.compile(r'^(?:rtxForge-1\.0\.0-beta\.\d+-x86_64\.AppImage(?:\.sha256)?|rtxforge-beta-linux\.json)$'),
}
LINE = re.compile(r'^(Windows|Linux): version `([^`]+)` · source `([0-9a-f]{40})`')
# Windows Beta 1 and 2 were published with one unlabelled provenance line.
LEGACY_WINDOWS = re.compile(r'^Version: `([^`]+)` · Source: `([0-9a-f]{40})`')


def owner(name):
    if PREVIOUS in name:
        return None
    found = [os_name for os_name in OSES if OWNED[os_name].match(name)]
    return found[0] if len(found) == 1 else None


def owned(os_name, release):
    return [a['name'] for a in release.get('assets', []) if owner(a['name']) == os_name]


def source_lines(body):
    """Return {os: line} for the provenance lines in an existing release body."""
    lines = {}
    for line in (body or '').splitlines():
        line = line.strip()
        match = LINE.match(line)
        if match:
            lines[match.group(1).lower()] = line
        elif LEGACY_WINDOWS.match(line) and 'windows' not in lines:
            version, sha = LEGACY_WINDOWS.match(line).groups()
            lines['windows'] = f'Windows: version `{version}` · source `{sha}`'
    return lines


def source(os_name, release):
    line = source_lines(release.get('body')).get(os_name)
    return LINE.match(line).group(3) if line else None


def notes(os_name, base, release, version, sha, build_url, extra=''):
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('source must be a full commit SHA')
    lines = source_lines((release or {}).get('body'))
    own = f'{LABELS[os_name]}: version `{version}` · source `{sha}` · [Build]({build_url})'
    lines[os_name] = f'{own}. {extra}'.rstrip() if extra else own
    block = '\n'.join(lines[name] for name in OSES if name in lines)
    return f'{base.rstrip()}\n\n{block}\n'


def load(path):
    return {} if path == '-' else json.loads(Path(path).read_text(encoding='utf-8'))


def main(argv):
    if len(argv) < 3 or argv[1] not in OSES:
        raise SystemExit(__doc__)
    command, os_name = argv[0], argv[1]
    if command == 'owned' and len(argv) == 3:
        print('\n'.join(owned(os_name, load(argv[2]))))
    elif command == 'source' and len(argv) == 3:
        sha = source(os_name, load(argv[2]))
        if not sha:
            raise SystemExit(f'No {LABELS[os_name]} source line in the beta release notes')
        print(sha)
    elif command == 'notes' and len(argv) in (7, 8):
        base = Path(argv[2]).read_text(encoding='utf-8')
        print(notes(os_name, base, load(argv[3]), *argv[4:]), end='')
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
