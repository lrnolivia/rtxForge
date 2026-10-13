"""Separated file/launch transaction boundaries, using disposable files only."""
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json, shutil, subprocess, sys, tempfile, threading, unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import engine_bridge as bridge
import operation_session
from launch_settings import Capabilities,IntentStore,LaunchBackend,OfflineSteamBackend,finish_pending
import transactions as t


def fixture_copy(args,**kwargs):
    # Execute the Session's Linux cp contract as a portable disposable-fixture
    # copy on this Mac. All Session signature/rollback logic remains real.
    assert args[:4]==['cp','-a','--reflink=auto','--']
    source,destination=map(Path,args[4:])
    if source.is_dir():shutil.copytree(source,destination,copy_function=shutil.copy2)
    else:shutil.copy2(source,destination)
    return subprocess.CompletedProcess(args,0)


class FixtureEngine:
    def __init__(self,root):
        self.STATE_ROOT=root/'state';self.target=root/'game';self.target.mkdir()
        (self.target/'Game.exe').write_bytes(b'fixture only')
        self.game=SimpleNamespace(name='Fixture',root=self.target,target_dir=self.target,exe=self.target/'Game.exe',appid='123',source='Steam')
        self.running=True;self.after_install=lambda:None
        self.choose_steam_user_config=Mock(side_effect=AssertionError('Steam account must not be accessed'))
        self.sync_launch_options_batch=Mock(side_effect=AssertionError('Steam sync must not run'))
        self.restore_launch_options_batch=Mock(side_effect=AssertionError('Steam restore must not run'))
        self.recover_pending_steam_transactions=Mock(side_effect=AssertionError('Steam recovery must not run'))
        self.install_calls=0
    def mutation_lock(self):return nullcontext()
    def steam_running(self):return self.running
    def state_dir_for(self,target):return self.STATE_ROOT/'games'/'fixture'
    def baseline_path(self,target):return self.state_dir_for(target)/'baseline.json'
    def load_baseline(self,target):
        p=self.baseline_path(target)
        return json.loads(p.read_text()) if p.exists() else None
    def save_json_atomic(self,path,value):t.atomic_file(path,json.dumps(value).encode(),0o600)
    def atomic_write(self,path,data,mode=0o600):t.atomic_file(path,data,mode)
    def install_target(self,*args,**kwargs):
        self.install_calls+=1
        record={'files':['dxgi.dll'],'launch_options':'WINEDLLOVERRIDES="dxgi=n,b" %command%'}
        (self.target/'dxgi.dll').write_bytes(b'installed fixture')
        self.save_json_atomic(self.baseline_path(self.target),{'current':record,'status':'active'})
        self.after_install()
        return record
    def verify_native_restore(self,baseline):assert baseline
    def restore_target(self,game):
        (game.target_dir/'dxgi.dll').unlink()
        shutil.rmtree(self.state_dir_for(game.target_dir))
        return {'files':['dxgi.dll']}
    def _running_processes_under_root(self,root):return []
    def now_stamp(self):return 'fixture-report'


class Backend(LaunchBackend):
    def __init__(self,live=False):self.capabilities=Capabilities('fixture',live_setter=live);self.calls=[]
    def apply(self,intent,game):self.calls.append(deepcopy(intent));return {'status':'verified','verification':'fixture backend readback'}


class LaunchTransactions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.e=FixtureEngine(Path(self.temp.name).resolve())
        self.copy=patch.object(operation_session.subprocess,'run',side_effect=fixture_copy);self.copy.start();self.addCleanup(self.copy.stop)
        self.fingerprint=patch.object(bridge,'fingerprint',return_value={'fixture':1});self.fingerprint.start();self.addCleanup(self.fingerprint.stop)
    def review(self,operation='install',cancel=None,backend=None):
        return {'engine':self.e,'operation':operation,'plans':[{'game':self.e.game,'fingerprint':{'fixture':1},'preview':{'files':['dxgi.dll'],'launch_options':'WINEDLLOVERRIDES="dxgi=n,b" %command%'}}],
                'cancel_event':cancel or threading.Event(),'payload':{},'meta':{},'nr':None,'nrmeta':None,'mode':'mfg-only','enable_effects':True,'nr_strength':2,'mfg_multiplier':'auto','sharpening_strength':.5,**({'launch_backend':backend} if backend else {})}
    def execute(self,review):
        report=bridge.execute(review)
        return json.loads(Path(report).read_text())['results'][0]
    def test_steam_running_install_commits_files_and_pending_intent_without_metadata(self):
        row=self.execute(self.review())
        self.assertEqual((row['status'],row['files'],row['launch_status']),('complete','applied','pending'))
        self.assertTrue((self.e.target/'dxgi.dll').exists())
        self.assertEqual(IntentStore(self.e).load(self.e.game)['state'],'pending')
        for name in ('choose_steam_user_config','sync_launch_options_batch','restore_launch_options_batch','recover_pending_steam_transactions'):
            getattr(self.e,name).assert_not_called()
    def test_cancel_restores_only_game_and_intent_not_concurrent_steam_edit(self):
        steam=Path(self.temp.name)/'localconfig.vdf';steam.write_text('before')
        cancel=threading.Event()
        self.e.after_install=lambda:(steam.write_text('Steam changed this concurrently'),cancel.set())
        with self.assertRaises(bridge.Cancelled):bridge.execute(self.review(cancel=cancel))
        self.assertFalse((self.e.target/'dxgi.dll').exists())
        self.assertIsNone(self.e.load_baseline(self.e.target))
        self.assertIsNone(IntentStore(self.e).load(self.e.game))
        self.assertEqual(steam.read_text(),'Steam changed this concurrently')
    def test_uninstall_retains_owned_cleanup_after_baseline_deleted(self):
        self.execute(self.review())
        baseline=self.e.load_baseline(self.e.target)
        baseline['steam_launch']={'kind':'steam','appid':'123','steam_userid':'fixture-user','config_path':str(Path(self.temp.name)/'localconfig.vdf'),'original':'MANGOHUD=1 %command%','applied':'MANGOHUD=1 WINEDLLOVERRIDES="dxgi=n,b" %command%'}
        self.e.save_json_atomic(self.e.baseline_path(self.e.target),baseline)
        row=self.execute(self.review('uninstall'))
        value=IntentStore(self.e).load(self.e.game)
        self.assertEqual((row['files'],value['state']),('restored','pending'))
        self.assertEqual(value['baseline']['steam_launch'],baseline['steam_launch'])
        self.assertIsNone(self.e.load_baseline(self.e.target))
        self.e.restore_launch_options_batch.assert_not_called()
    def test_intent_failure_precedes_game_mutation(self):
        with patch.object(IntentStore,'prepare',side_effect=t.Refusal('fixture state unavailable')):
            with self.assertRaises(t.Refusal):bridge.execute(self.review())
        self.assertEqual(self.e.install_calls,0)
        self.assertFalse((self.e.target/'dxgi.dll').exists())
    def test_deferred_work_survives_store_restart_and_requires_explicit_retry(self):
        self.execute(self.review())
        value=IntentStore(self.e).load(self.e.game);backend=Backend()
        same=finish_pending(self.e,self.e.game,value['id'],backend)
        self.assertEqual(same['state'],'pending');self.assertFalse(backend.calls)
        self.e.running=False
        done=finish_pending(self.e,self.e.game,value['id'],backend)
        self.assertEqual(done['state'],'verified');self.assertEqual(len(backend.calls),1)
    def test_manual_confirmation_has_distinct_unverified_provenance_and_stale_refusal(self):
        self.execute(self.review());store=IntentStore(self.e);value=store.load(self.e.game)
        with self.assertRaises(t.Refusal):store.confirm_manual(self.e.game,'stale')
        result=store.confirm_manual(self.e.game,value['id'])
        self.assertEqual(result['state'],'user-confirmed')
        self.assertIn('not independently verified',result['verification'])
    def test_future_live_capability_is_explicit_and_applies_after_ui_finalization(self):
        backend=Backend(live=True);review=self.review(backend=backend)
        finalized=[];review['on_finalizing']=lambda:finalized.append(True)
        original=backend.apply
        def apply(intent,game):self.assertTrue(finalized);return original(intent,game)
        backend.apply=apply
        row=self.execute(review)
        self.assertEqual(row['launch_status'],'verified');self.assertEqual(len(backend.calls),1)
    def test_offline_backend_checks_steam_before_recovery_or_account_access(self):
        self.execute(self.review());intent=IntentStore(self.e).load(self.e.game)
        backend=OfflineSteamBackend(self.e);backend.capabilities=Capabilities('offline fixture')
        self.assertEqual(backend.apply(intent,self.e.game)['status'],'pending')
        self.e.recover_pending_steam_transactions.assert_not_called();self.e.choose_steam_user_config.assert_not_called()
    def test_offline_install_refuses_changed_baseline_before_sync(self):
        self.execute(self.review());store=IntentStore(self.e);intent=store.load(self.e.game)
        changed=self.e.load_baseline(self.e.target);changed['other']='changed'
        self.e.save_json_atomic(self.e.baseline_path(self.e.target),changed);self.e.running=False
        backend=OfflineSteamBackend(self.e);backend.capabilities=Capabilities('offline fixture')
        result=backend.apply(intent,self.e.game)
        self.assertEqual(result['status'],'pending');self.assertIn('changed',result['error'])
        self.e.sync_launch_options_batch.assert_not_called()
    def test_cancel_uninstall_restores_files_and_prior_pending_install_intent(self):
        self.execute(self.review());old=IntentStore(self.e).load(self.e.game)
        cancel=threading.Event();review=self.review('uninstall',cancel=cancel);review['on_finalizing']=cancel.set
        with self.assertRaises(bridge.Cancelled):bridge.execute(review)
        self.assertTrue((self.e.target/'dxgi.dll').exists())
        self.assertEqual(IntentStore(self.e).load(self.e.game)['id'],old['id'])
        self.e.restore_launch_options_batch.assert_not_called()


if __name__=='__main__':unittest.main()
