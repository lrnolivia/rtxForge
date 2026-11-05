"""Writers wait for one another instead of failing or racing."""
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import writer_gate  # noqa: E402


class WriterGate(unittest.TestCase):
    def test_a_change_waits_for_the_background_update_and_says_so(self):
        entered, release, order, waits = threading.Event(), threading.Event(), [], []

        def background():
            with writer_gate.hold('the overlay update'):
                entered.set(); release.wait(2); order.append('update')

        worker = threading.Thread(target=background); worker.start()
        self.assertTrue(entered.wait(2))
        self.assertEqual(writer_gate.holder(), 'the overlay update')
        threading.Timer(.2, release.set).start()
        with writer_gate.hold('your change', waits.append):
            order.append('change')
        worker.join(2)
        self.assertEqual(order, ['update', 'change'])
        self.assertEqual(waits, ['Waiting for the overlay update to finish…'])
        self.assertEqual(writer_gate.holder(), '')

    def test_the_holder_may_enter_again(self):
        with writer_gate.hold('your change'):
            with writer_gate.hold('your change'):
                self.assertEqual(writer_gate.holder(), 'your change')
            self.assertEqual(writer_gate.holder(), 'your change')
        self.assertEqual(writer_gate.holder(), '')

    def test_listeners_see_start_and_finish(self):
        seen = []
        writer_gate.on_change(seen.append)
        try:
            with writer_gate.hold('the overlay update'):
                pass
        finally:
            writer_gate._listeners.remove(seen.append)
        self.assertEqual(seen, ['the overlay update', ''])


if __name__ == '__main__':
    unittest.main()
