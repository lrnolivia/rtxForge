"""Bounded admission/cache adapter for the portable screenshot worker."""
import json
import os
from pathlib import Path
import subprocess
import time

VERSION = 'text-layout-v1-090f04ab'


def command():
    explicit = os.environ.get('RTXFORGE_SCREENSHOT_SCREENER')
    if explicit:
        return [explicit]
    root = Path(__file__).resolve().parents[1]
    name = 'rtxforge-screenshot-screen' + ('.exe' if os.name == 'nt' else '')
    for folder in (root / 'screening', root / '.tools/screening'):
        executable = folder / name
        if executable.is_file():
            return [str(executable)]
    return None


def screen(paths):
    worker = command()
    if not worker or len(paths) > 12:
        return []
    try:
        result = subprocess.run(worker, input=json.dumps({'paths': [str(p) for p in paths]}),
                                text=True, capture_output=True, timeout=18,
                                creationflags=0x08000000 if os.name == 'nt' else 0)
        if result.returncode or len(result.stdout) > 64 * 1024:
            return []
        data = json.loads(result.stdout)
        rows = data.get('results', []) if data.get('version') == VERSION else []
        if not isinstance(rows, list) or len(rows) != len(paths):
            return []
        return rows
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []


def decision(cache, identity):
    path = Path(cache) / (identity + '.screen.json')
    try:
        if path.is_symlink() or path.stat().st_size > 2048:
            return None
        data = json.loads(path.read_text('utf-8'))
        if data.get('version') != VERSION or type(data.get('clean')) is not bool:
            return None
        if data.get('reason') == 'unavailable' and time.time() - data.get('checked', 0) > 300:
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None
