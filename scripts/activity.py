"""One background-activity line for every rtxForge app.

The hosts (Windows, the Linux Game Mode bridge) and the Linux desktop app
report what they start, how it progresses and when it ends. This module
decides what the line says, in short words, and when to say it:

- Only work worth knowing about has a line (LABELS); reads, polls, live
  controls and cache hits stay silent.
- Work that finishes within SHOW_AFTER seconds never appears.
- The oldest visible work is shown; others are counted ("and 2 more").

send({'event': 'activity', 'text': ...}) is called whenever the line
changes; an empty text means nothing is running and the line hides.
"""
import threading
import time

SHOW_AFTER = 2.0
LIMIT = 90

# What a host method says before (or instead of) its own progress labels.
LABELS = {
    'scan': 'Checking your games',
    'scan_game': 'Checking the game',
    'prefetch_install': 'Downloading packages',
    'review_prepare': 'Checking games for the review',
    'prepare': 'Checking games for the review',
    'prepare_routes': 'Checking games for the review',
    'prepare_dlss': 'Checking DLSS files',
    'execute': 'Applying your changes',
    'execute_routes': 'Applying your changes',
    'run': 'Applying your changes',
    'update_dlss': 'Updating DLSS files',
    'update_check': 'Checking for an rtxForge update',
    'update_stage': 'Downloading the rtxForge update',
    'update_apply': 'Installing the rtxForge update',
    'overlay_refresh_retry': 'Updating the in-game overlay',
    'storage_review': 'Measuring app storage',
    'feeder_storage': 'Preparing Feeder files',
}

# Progress labels that say less than the method's own wording.
_GENERIC = {'', 'game checked', 'preparing game files', 'working'}


def describe(base, label=None, checked=0, total=0):
    """The line for one piece of work: its own label when it says more, then a count."""
    text = str(label or '').strip()
    if text.casefold().rstrip('.…') in _GENERIC:
        text = base
    try:
        checked, total = int(checked or 0), int(total or 0)
    except (TypeError, ValueError):
        checked = total = 0
    if total > 0:
        text += f' · {min(checked, total)} of {total}'
    return text if len(text) <= LIMIT else text[:LIMIT - 1].rstrip() + '…'


class Tracker:
    """Background work in one process, reduced to one line."""

    def __init__(self, send, show_after=SHOW_AFTER, clock=time.monotonic, timer=None):
        self._send, self._show_after, self._clock = send, show_after, clock
        self._timer = timer or self._start_timer
        self._lock = threading.Lock()
        self._work = {}   # key -> {'started', 'base', 'text'}
        self._shown = ''

    @staticmethod
    def _start_timer(delay, callback):
        timer = threading.Timer(delay, callback)
        timer.daemon = True
        timer.start()

    def begin(self, key, method=None, text=None, quiet=True):
        """Start work: a host method from LABELS, or plain text. quiet=False shows it at once."""
        base = text or LABELS.get(method or '')
        if not base:
            return
        with self._lock:
            started = self._clock() - (0 if quiet else self._show_after)
            self._work[key] = {'started': started, 'base': base, 'text': base}
        if quiet:
            self._timer(self._show_after, self.refresh)
        self.refresh()

    def progress(self, key, label=None, checked=0, total=0):
        with self._lock:
            item = self._work.get(key)
            if item is None:
                return
            item['text'] = describe(item['base'], label, checked, total)
        self.refresh()

    def end(self, key):
        with self._lock:
            self._work.pop(key, None)
        self.refresh()

    def line(self):
        """What the line says now, '' when nothing visible is running."""
        with self._lock:
            now = self._clock()
            visible = sorted((item for item in self._work.values() if now - item['started'] >= self._show_after - 1e-6),
                             key=lambda item: item['started'])
        if not visible:
            return ''
        text = visible[0]['text']
        return text + (f' · and {len(visible) - 1} more' if len(visible) > 1 else '')

    def refresh(self):
        text = self.line()
        with self._lock:
            if text == self._shown:
                return
            self._shown = text
        try:
            self._send({'event': 'activity', 'text': text})
        except Exception:
            pass  # the line is a courtesy; it never fails the work it describes
