"""Proton's working CUDA library for the Universal MFG Unlocker, without launch options.

The Unlocker identifies the GPU through cuDeviceGetLuid and
cuDeviceComputeCapability. Proton's default nvcuda.dll exports neither, and
Proton installs its working nvidia-libs nvcuda only when PROTON_NVIDIA_NVCUDA
(or PROTON_NVIDIA_LIBS) is set. Proton also rewrites system32/nvcuda.dll and
sets nvcuda=b through WINEDLLOVERRIDES on every launch, which outranks the
prefix registry, so nothing written into one game's prefix can turn it on.
Protonfixes' local fixes run after the prefix is set up, which is too late.

What can: the Proton build's own user_settings.py, which Proton loads before
it sets up the prefix. It is per Proton build, not per game: every game that
uses that build gets the working library, and the review says so.

rtxForge writes the file only when the build has none, records which games
asked for it, and deletes it when the last of them is restored, unless it was
edited since. A user_settings.py of the user's own is never rewritten; the
review asks them to add the one line instead.
"""
from pathlib import Path
import hashlib
import json

import proton_prefix
import proton_stack

RECORD_NAME = 'proton-cuda.json'
CONTENT = ('# Written by rtxForge so the Universal MFG Unlocker can identify the GPU under Proton.\n'
           '# Applies to every game that uses this Proton build. rtxForge removes it when the last\n'
           '# game that needs it is restored; edit it and rtxForge leaves it alone.\n'
           'user_settings = {\n'
           '    "PROTON_NVIDIA_NVCUDA": "1",\n'
           '}\n')


class CudaError(ValueError):
    """A reason the CUDA setting cannot be made, phrased as a next step."""


def _digest(text):
    return hashlib.sha256(text.encode('utf-8', 'surrogateescape')).hexdigest()


def settings_path(lib_dir):
    """<tool>/user_settings.py for a Proton build's files/lib directory."""
    return Path(lib_dir).parent.parent / 'user_settings.py'


def _current(path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise CudaError(f'{path} is not a regular file. Remove it, then review again.')
    return path.read_text(encoding='utf-8', errors='surrogateescape') if path.is_file() else None


def plan(lib_dir, compatdata=None):
    """What turning on CUDA for this Proton build would change; nothing is written.

    compatdata -- the game's compatdata/<appid>, so a refusal can tell a stale last run apart.
    """
    if not lib_dir:
        raise CudaError(proton_stack.REASONS['tool-unknown'])
    if not (Path(lib_dir) / proton_stack.NVCUDA).is_file():
        raise CudaError(proton_stack.REASONS[proton_stack.cuda_missing_reason(compatdata) if compatdata else 'cuda-missing'])
    path = settings_path(lib_dir)
    tool = path.parent.name
    text = _current(path)
    if text is None:
        action = 'write'
        summary = f"Turns on Proton's CUDA library for every game that uses {tool} (its user_settings.py) · applies next launch"
    elif proton_stack.cuda_requested(lib_dir, {}):
        action = 'keep'
        summary = f"Proton's CUDA library is already on in {tool}"
    else:
        raise CudaError(f'{tool} already has a user_settings.py of its own. Add "PROTON_NVIDIA_NVCUDA": "1" to its '
                        'user_settings, or set PROTON_NVIDIA_NVCUDA=1 in this game\'s launch options, then review again.')
    return {'path': str(path), 'tool': tool, 'action': action,
            'before_sha256': None if text is None else _digest(text), 'summary': summary}


def _load(state_root):
    path = Path(state_root) / RECORD_NAME
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def _save(state_root, record):
    Path(state_root).mkdir(parents=True, exist_ok=True)
    proton_prefix._write_atomic(Path(state_root) / RECORD_NAME, json.dumps(record, indent=1, sort_keys=True) + '\n')


def apply(reviewed, state_root, game_key):
    """Write a reviewed plan. Refuses a file that changed since review."""
    path = Path(reviewed['path'])
    text = _current(path)
    current = None if text is None else _digest(text)
    record = _load(state_root)
    entry = record.get(str(path))
    if entry and current == entry['sha256']:
        # rtxForge's own file, written since review by another game on this build (one batch).
        reviewed = dict(reviewed, action='keep', before_sha256=current)
    if current != reviewed['before_sha256']:
        raise CudaError("The Proton build's user_settings.py changed since review. Review again.")
    if reviewed['action'] == 'write':
        proton_prefix._write_atomic(path, CONTENT)
        entry = {'sha256': _digest(CONTENT), 'games': []}
    elif not entry or entry['sha256'] != reviewed['before_sha256']:
        return {'status': 'already-on'}  # the user's own file: nothing of ours to track
    if game_key not in entry['games']:
        entry['games'].append(game_key)
    record[str(path)] = entry
    _save(state_root, record)
    return {'status': 'written' if reviewed['action'] == 'write' else 'shared', 'path': str(path)}


def restore(state_root, game_key):
    """Drop this game's need for the setting; delete rtxForge's file once no game needs it."""
    record = _load(state_root)
    result = {'status': 'none'}
    for name, entry in list(record.items()):
        if game_key not in entry['games']:
            continue
        entry['games'].remove(game_key)
        result = {'status': 'kept', 'path': name, 'games': len(entry['games'])}
        if entry['games']:
            continue
        path = Path(name)
        text = _current(path)
        if text is not None and _digest(text) == entry['sha256']:
            path.unlink()
            result = {'status': 'removed', 'path': name}
        else:
            result = {'status': 'edited-kept' if text is not None else 'gone', 'path': name}
        del record[name]
    if result['status'] != 'none':
        _save(state_root, record)
    return result
