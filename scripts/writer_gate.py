"""One writer at a time inside an rtxForge process, and waiting rather than failing.

The engine's cross-process writer lock (rtxengine.mutation_lock) is reentrant
per process, so two threads of the same app could otherwise review and write
games at once: the background overlay update and an update the person starts
by hand, for example. Writers hold this gate instead; a writer that finds it
busy says what it is waiting for and waits its turn. A thread that already
holds the gate may enter again (a review that applies its companion reviews).
"""
import contextlib
import threading

_gate = threading.RLock()
_holder = ''
_depth = 0
_listeners = []


def holder():
    """What is writing now, or '' when nothing is."""
    return _holder


def on_change(listener):
    """listener(label) is called with the new holder, '' when the gate frees."""
    _listeners.append(listener)


def _announce(label):
    for listener in list(_listeners):
        try:
            listener(label)
        except Exception:
            pass


def _progress(text):
    try:
        import ui
        ui.progress(text)
    except Exception:
        pass


@contextlib.contextmanager
def hold(label, waiting=None):
    """Hold the gate for `label`. waiting(text) is told when this has to wait;
    by default the wait is reported as operation progress."""
    global _holder, _depth
    if not _gate.acquire(blocking=False):
        (waiting or _progress)('Waiting for ' + (_holder or 'another change') + ' to finish…')
        _gate.acquire()
    _depth += 1
    outer = _depth == 1
    if outer:
        _holder = label
        _announce(label)
    try:
        yield
    finally:
        _depth -= 1
        if outer:
            _holder = ''
        _gate.release()
        if outer:
            _announce('')
