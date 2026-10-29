"""Per-game executable choices, applied before discovery inspects install ownership.

Choices affect discovery only. Install reviews still check their own target,
processes, file hashes and ownership. Invalid saved choices stay visible and
blocked rather than silently installing beside a different executable.
"""
import contextlib
import os
from pathlib import Path
import struct
import threading

import discovery
import transactions as t

_local = threading.local()
_detected = discovery.choose_exe


def key(path):
    return os.path.normcase(str(Path(path).resolve()))


def validate(root, executable):
    root = t.safe(root)
    t.need(root.is_dir(), 'The game folder is unavailable.')
    path = Path(executable)
    path = t.safe(path if path.is_absolute() else root / t.relative(path.as_posix()))
    t.need(path.is_relative_to(root) and path != root and path.suffix.casefold() == '.exe' and path.is_file(),
           'Choose a game EXE inside this game\'s folder.')
    with path.open('rb') as stream:
        header = stream.read(64)
        t.need(len(header) == 64 and header[:2] == b'MZ', 'Choose a Windows game executable.')
        offset = struct.unpack_from('<I', header, 60)[0]
        t.need(64 <= offset <= 1024**2, 'The executable has an invalid PE header.')
        stream.seek(offset)
        pe = stream.read(6)
        t.need(pe[:4] == b'PE\0\0' and pe[4:] in (b'\x4c\x01', b'\x64\x86'),
               'Choose an x86 or x64 Windows game executable.')
    return path


@contextlib.contextmanager
def choices(values):
    previous = getattr(_local, 'values', None)
    _local.values = {key(root): exe for root, exe in (values or {}).items()} if isinstance(values, dict) else {}
    try:
        yield
    finally:
        _local.values = previous


def chosen(root):
    return (getattr(_local, 'values', None) or {}).get(key(root))


def choose(root, name, upscalers, exes):
    selected = chosen(root)
    if selected:
        try:
            return validate(root, selected)
        except (t.Refusal, OSError, ValueError, TypeError):
            pass
    return _detected(root, name, upscalers, exes)


def adapt_engine(e, saved_choices):
    """The install engine independently re-inspects the exact chosen target."""
    if hasattr(e, '_rtxforge_original_choose_exe'):
        return
    detected = e.choose_game_exe
    e._rtxforge_original_choose_exe = detected
    def engine_choose(root, name, exes, evidence):
        selected = chosen(root)
        if not selected:
            values = saved_choices() or {}
            selected = {key(folder): value for folder, value in values.items()}.get(key(root))
        return validate(root, selected) if selected else detected(root, name, exes, evidence)
    e.choose_game_exe = engine_choose


discovery.choose_exe = choose


def decorate(row):
    selected = chosen(row['game'])
    if selected:
        row['executable_selected'] = True
        try:
            validate(row['game'], selected)
        except (t.Refusal, OSError, ValueError, TypeError) as error:
            row['executable_error'] = 'The selected EXE is unavailable or invalid. Choose another EXE or use the detected one. ' + str(error)
    return row


# DesktopService expands collections before the Windows library adapter sees
# them. Annotate choices at that first expansion too, on this scanning thread.
import feeder_provider
_expand = feeder_provider.expand_rows


def expand(e, rows, selected=False):
    return _expand(e, [decorate(row) for row in rows], selected)


feeder_provider.expand_rows = expand


def review(e, row, path):
    """Read-only validation before the UI saves a choice, including Reset."""
    root = t.safe(row['game'])
    if path:
        selected = validate(root, path)
    else:
        upscalers, exes, _ = discovery.scan_files(root)
        selected = _detected(root, row.get('name') or root.name, upscalers, exes)
        t.need(selected is not None, 'No game executable was detected. Choose an EXE instead.')
        selected = validate(root, selected)
    current = root / t.relative(row['exe']) if row.get('exe') else None
    if current and current.parent != selected.parent:
        import feeder_provider
        owned = feeder_provider.state(e, current.parent)
        t.need(not (owned and owned.get('status') != 'restored')
               and not e.load_baseline(current.parent, readonly=True)
               and not (current.parent / '.rtxforge-install.json').exists(),
               'Restore this game\'s installed features before choosing an EXE in another folder. Your restore backups are kept.')
    return {'exe': selected.relative_to(root).as_posix()}
