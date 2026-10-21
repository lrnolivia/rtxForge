"""Fresh native process snapshots for each game-file mutation boundary."""
import ctypes
import os
from pathlib import Path

from transactions import Refusal


class Entry(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('usage', ctypes.c_uint32), ('pid', ctypes.c_uint32),
                ('heap', ctypes.c_void_p), ('module', ctypes.c_uint32), ('threads', ctypes.c_uint32),
                ('parent', ctypes.c_uint32), ('priority', ctypes.c_long), ('flags', ctypes.c_uint32),
                ('exe', ctypes.c_wchar * 260)]


def _inventory():
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    for name, args, result in [
        ('CreateToolhelp32Snapshot', [ctypes.c_uint32, ctypes.c_uint32], ctypes.c_void_p),
        ('Process32FirstW', [ctypes.c_void_p, ctypes.POINTER(Entry)], ctypes.c_bool),
        ('Process32NextW', [ctypes.c_void_p, ctypes.POINTER(Entry)], ctypes.c_bool),
        ('OpenProcess', [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32], ctypes.c_void_p),
        ('QueryFullProcessImageNameW', [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)], ctypes.c_bool),
        ('CloseHandle', [ctypes.c_void_p], ctypes.c_bool),
    ]:
        fn = getattr(k, name); fn.argtypes = args; fn.restype = result
    snapshot = k.CreateToolhelp32Snapshot(2, 0)
    if snapshot in (None, ctypes.c_void_p(-1).value): raise OSError('Process snapshot unavailable')
    found, entry = [], Entry(); entry.size = ctypes.sizeof(entry)
    try:
        if not k.Process32FirstW(snapshot, ctypes.byref(entry)): raise OSError('Process enumeration unavailable')
        while True:
            if entry.pid:
                handle = k.OpenProcess(0x1000, False, entry.pid)
                image, error = None, ctypes.get_last_error() if not handle else 0
                if handle:
                    try:
                        buffer, size = ctypes.create_unicode_buffer(32768), ctypes.c_uint32(32768)
                        if k.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)): image = buffer.value
                        else: error = ctypes.get_last_error()
                    finally: k.CloseHandle(handle)
                found.append((entry.pid, entry.exe, image, error))
            if not k.Process32NextW(snapshot, ctypes.byref(entry)): break
        if ctypes.get_last_error() not in (0, 18): raise OSError('Process enumeration incomplete')
    finally: k.CloseHandle(snapshot)
    return found


def snapshot():
    """One fresh inventory shared only within a single read-only review."""
    try:
        inventory = [(pid, name, Path(image).resolve() if image else None, error)
                     for pid, name, image, error in _inventory()]
    except (OSError, ValueError, AttributeError) as error:
        raise Refusal('Could not check running game processes. No game files were changed; retry after closing the game.') from error
    return lambda root: running_under(root, inventory=inventory)


def running_under(root, *, inventory=None):
    try:
        root = Path(root).resolve()
        if inventory is None: inventory = _inventory()
        found, denied = [], set()
        for pid, name, image, error in inventory:
            if image:
                image = image if isinstance(image, Path) else Path(image).resolve()
                if image.is_relative_to(root): found.append(f'{pid}:{name}')
            elif error not in (0, 6, 87) and name.casefold().endswith('.exe'):
                denied.add(name.casefold())
        if denied and root.is_dir():
            # Access-denied system processes don't block unrelated games. A
            # matching executable whose location cannot be established does.
            def fail(error): raise error
            for parent, dirs, files in os.walk(root, followlinks=False, onerror=fail):
                dirs[:] = [name for name in dirs if not Path(parent, name).is_symlink()]
                if denied.intersection(name.casefold() for name in files):
                    raise Refusal('Could not verify a matching running process. Close the game and retry.')
        return found
    except (OSError, ValueError, AttributeError) as error:
        raise Refusal('Could not check running game processes. No game files were changed; retry after closing the game.') from error
