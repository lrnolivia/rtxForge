"""Required overlay refresh retries and verified-bundle boundaries."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import overlay_refresh as refresh
import transactions as t


class RequiredRefreshTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.state=self.root/'state'
        self.folder=self.root/'providers/glass-overlay';self.folder.mkdir(parents=True)
        self.write_bundle(b'first renderer')

    def write_bundle(self,data):
        (self.folder/'rollout.json').write_text(json.dumps({'schema':1,'revision':1,'required':True}))
        (self.folder/'rtxforge-glass.dll').write_bytes(data)
        (self.folder/'package.json').write_text(json.dumps({'schema':1,'renderer':'rmlui','revision':1,
            'files':{'rtxforge-glass.dll':{'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}}}))

    def test_refresh_executes_exact_prepared_plan_once(self):
        review={'plans':[{'name':'Game'}],'blocked':[],'skipped':[]}
        prepare=Mock(return_value=review);execute=Mock(return_value={'message':'Updated'})
        self.assertEqual(refresh.run(self.root,self.state,prepare,execute)['status'],'complete')
        execute.assert_called_once_with(review)
        self.assertEqual(refresh.run(self.root,self.state,prepare,execute)['status'],'current')
        prepare.assert_called_once()

    def test_running_or_conflicting_game_retries_without_losing_other_games(self):
        first={'plans':[{'name':'Ready'}],'blocked':[{'title':'Running','detail':'Close the game'}]}
        second={'plans':[{'name':'Now closed'}],'blocked':[]}
        prepare=Mock(side_effect=[first,second]);execute=Mock(return_value={})
        self.assertEqual(refresh.run(self.root,self.state,prepare,execute)['status'],'pending')
        self.assertEqual(refresh.run(self.root,self.state,prepare,execute)['status'],'complete')
        self.assertEqual(execute.call_count,2)

    def test_tampered_bundle_never_reaches_game_planner(self):
        (self.folder/'rtxforge-glass.dll').write_bytes(b'foreign')
        prepare=Mock();execute=Mock()
        with self.assertRaises(t.Refusal):refresh.run(self.root,self.state,prepare,execute)
        prepare.assert_not_called();execute.assert_not_called()
        self.assertFalse((self.state/'overlay-refresh.json').exists())

    def test_new_binary_for_same_revision_refreshes_again(self):
        prepare=Mock(return_value={'plans':[],'blocked':[]});execute=Mock()
        refresh.run(self.root,self.state,prepare,execute)
        self.write_bundle(b'corrected renderer')
        self.assertEqual(refresh.run(self.root,self.state,prepare,execute)['status'],'complete')
        self.assertEqual(prepare.call_count,2)

    def test_execution_failure_does_not_mark_upgrade_complete(self):
        prepare=Mock(return_value={'plans':[{'name':'Game'}],'blocked':[]})
        with self.assertRaises(RuntimeError):refresh.run(self.root,self.state,prepare,Mock(side_effect=RuntimeError('ownership changed')))
        self.assertFalse((self.state/'overlay-refresh.json').exists())
        self.assertEqual(refresh.run(self.root,self.state,prepare,Mock(return_value={}))['status'],'complete')

    def test_older_app_does_not_downgrade_completed_overlay_revision(self):
        self.state.mkdir();(self.state/'overlay-refresh.json').write_text(json.dumps({'revision':2,'status':'complete'}))
        prepare=Mock();execute=Mock()
        self.assertEqual(refresh.run(self.root,self.state,prepare,execute)['status'],'newer-revision-kept')
        prepare.assert_not_called()

    def test_builds_without_required_overlay_policy_leave_games_untouched(self):
        (self.folder/'rollout.json').unlink();prepare=Mock();execute=Mock()
        self.assertEqual(refresh.run(self.root,self.state,prepare,execute)['status'],'not-required')
        prepare.assert_not_called();execute.assert_not_called()

    def test_start_shares_one_worker_and_stops_pending_retry(self):
        entered=threading.Event();release=threading.Event();stop=threading.Event()
        def pending(*args):
            entered.set();release.wait(2);return {'status':'pending'}
        with patch.object(refresh,'run',side_effect=pending) as run:
            worker=refresh.start(self.root,self.state,Mock(),Mock(),stop)
            self.assertTrue(entered.wait(2))
            self.assertIs(refresh.start(self.root,self.state,Mock(),Mock(),stop),worker)
            stop.set();release.set();worker.join(2)
            self.assertFalse(worker.is_alive());run.assert_called_once()

    def test_start_in_source_checkout_never_calls_planner(self):
        (self.folder/'rollout.json').unlink();prepare=Mock()
        self.assertIsNone(refresh.start(self.root,self.state,prepare,Mock()))
        prepare.assert_not_called()


if __name__=='__main__':unittest.main()
