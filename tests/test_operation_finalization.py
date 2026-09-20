"""The GUI must disable Cancel before the engine's final undo decision."""
from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import engine_bridge


class FinalizationTest(unittest.TestCase):
    def test_cancel_at_ui_boundary_still_rolls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = Mock(STATE_ROOT=Path(folder))
            engine.mutation_lock.return_value = nullcontext()
            cancel = threading.Event()
            review = {'engine': engine, 'operation': 'reset', 'plans': [],
                      'cancel_event': cancel, 'on_finalizing': cancel.set}
            with patch.object(engine_bridge, 'Session') as session:
                with self.assertRaises(engine_bridge.Cancelled):
                    engine_bridge.execute(review)
                session.return_value.rollback.assert_called_once()
                session.return_value.complete.assert_not_called()
                engine.save_json_atomic.assert_not_called()

    def test_ui_boundary_precedes_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = Mock(STATE_ROOT=Path(folder))
            engine.mutation_lock.return_value = nullcontext()
            engine.now_stamp.return_value = 'fixture'
            events = []
            review = {'engine': engine, 'operation': 'reset', 'plans': [],
                      'cancel_event': threading.Event(),
                      'on_finalizing': lambda: events.append('ui-disabled')}
            with patch.object(engine_bridge, 'Session') as session:
                session.return_value.complete.side_effect = lambda: events.append('committed')
                engine_bridge.execute(review)
                self.assertEqual(events, ['ui-disabled', 'committed'])
                session.return_value.rollback.assert_not_called()


if __name__ == '__main__':
    unittest.main()
