"""The shared background-activity line (scripts/activity.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import activity  # noqa: E402


class Clock:
    def __init__(self):
        self.now = 100.0
        self.timers = []

    def __call__(self):
        return self.now

    def timer(self, delay, callback):
        self.timers.append((self.now + delay, callback))

    def advance(self, seconds):
        self.now += seconds
        due = [callback for at, callback in self.timers if at <= self.now]
        self.timers = [(at, callback) for at, callback in self.timers if at > self.now]
        for callback in due:
            callback()


class TrackerTest(unittest.TestCase):
    def setUp(self):
        self.clock, self.sent = Clock(), []
        self.tracker = activity.Tracker(self.sent.append, clock=self.clock, timer=self.clock.timer)

    def texts(self):
        return [message['text'] for message in self.sent]

    def test_quick_work_never_appears(self):
        self.tracker.begin(1, 'scan')
        self.clock.advance(1.5)
        self.tracker.end(1)
        self.clock.advance(5)
        self.assertEqual(self.sent, [])

    def test_long_work_appears_after_two_seconds_with_its_progress_and_clears(self):
        self.tracker.begin(1, 'scan')
        self.tracker.progress(1, 'Game checked', checked=3, total=12)
        self.assertEqual(self.sent, [])
        self.clock.advance(2)
        self.tracker.progress(1, 'Game checked', checked=5, total=12)
        self.tracker.progress(1, 'Waiting for the overlay update to finish…')
        self.tracker.end(1)
        self.assertEqual(self.texts(), ['Checking your games · 3 of 12', 'Checking your games · 5 of 12',
                                        'Waiting for the overlay update to finish…', ''])
        self.assertTrue(all(message['event'] == 'activity' for message in self.sent))

    def test_silent_methods_and_unknown_keys_say_nothing(self):
        for method in ('hello', 'hardware', 'settings_get', 'companion_status', 'overlay_status'):
            self.tracker.begin(method, method)
        self.tracker.progress('missing', 'Downloading')
        self.tracker.end('missing')
        self.clock.advance(10)
        self.assertEqual(self.sent, [])

    def test_the_oldest_work_leads_and_the_rest_are_counted(self):
        self.tracker.begin('overlay', text='Updating the in-game overlay', quiet=False)
        self.tracker.begin(2, 'prefetch_install')
        self.clock.advance(2)
        self.tracker.end('overlay')
        self.assertEqual(self.texts(), ['Updating the in-game overlay', 'Updating the in-game overlay · and 1 more',
                                        'Downloading packages'])

    def test_a_failing_display_never_breaks_the_work(self):
        def broken(_message):
            raise RuntimeError('window closed')
        tracker = activity.Tracker(broken, clock=self.clock, timer=self.clock.timer)
        tracker.begin(1, 'execute', quiet=False)
        tracker.end(1)


class DescribeTest(unittest.TestCase):
    def test_wording(self):
        self.assertEqual(activity.describe('Downloading packages', 'Downloading packages/files', 0, 0), 'Downloading packages/files')
        self.assertEqual(activity.describe('Checking DLSS files', '', 9, 4), 'Checking DLSS files · 4 of 4')
        self.assertEqual(activity.describe('Checking', 'Preparing game files…', 'x', None), 'Checking')
        self.assertLessEqual(len(activity.describe('x', 'y' * 200)), activity.LIMIT)


if __name__ == '__main__':
    unittest.main()
