"""The GUI must disable Cancel before the engine's final undo decision."""
from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import engine_bridge
import nr_install
import transactions as t


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

    def test_each_game_runs_main_then_split_render_in_one_operation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            engine = Mock(STATE_ROOT=root)
            engine.mutation_lock.return_value = nullcontext()
            engine.load_baseline.return_value = {}
            engine.target_key.return_value = 'fixture'
            engine.choose_steam_user_config.return_value = None
            engine.sync_launch_options_batch.return_value = [{'status': 'written'}]
            engine.steam_running.return_value = False
            engine.now_stamp.return_value = 'fixture'
            events = []
            plans = []
            for name in ('A', 'B'):
                target = root / name
                target.mkdir()
                game = SimpleNamespace(root=target, target_dir=target, name=name)
                plans.append({'game': game, 'row': {}, 'preview': {}, 'fingerprint': {},
                              'split_render': ({}, {'name': name, 'changes': [{'path': '.rtxforge/nr.json'}]})})
            review = dict(engine=engine, operation='install', plans=plans, mode='nr-mfg', payload={}, meta={},
                          nr=None, nrmeta=None, enable_effects=True, nr_strength=2.0, mfg_multiplier='auto',
                          sharpening_strength=0.5)
            def install(game, *args, **kwargs):
                events.append((game.name, 'main'))
                return {'launch_options': ''}
            def split(config, plan):
                events.append((plan['name'], 'split'))
                if plan['name'] == 'A':
                    raise t.Refusal('Split Render input changed')
                return {'status': 'applied'}
            engine.install_target.side_effect = install
            with (patch.object(engine_bridge, 'Session') as factory,
                  patch.object(engine_bridge, 'fingerprint', return_value={}),
                  patch.object(engine_bridge, 'share_install'),
                  patch.object(engine_bridge.linux_runtime, 'setup_paths', return_value=[]),
                  patch.object(nr_install, 'apply_after_package', side_effect=split)):
                session = factory.return_value
                session.capture.side_effect = [0, 1]
                session.changed.return_value = [root / 'A' / 'OptiScaler.ini']
                with self.assertRaisesRegex(t.Refusal, '1 game'):
                    engine_bridge.execute(review)
                self.assertEqual(events, [('A', 'main'), ('A', 'split'), ('B', 'main'), ('B', 'split')])
                self.assertIn(root / 'A' / '.rtxforge', session.capture.call_args_list[0].args[0])
                session.undo.assert_called_once_with(0)
                session.complete.assert_called_once()

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
