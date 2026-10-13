"""Actual engine/VDF writer, only inside the engine's disposable Steam fixture."""
from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine/tests'))
import test_v13_core_hardening as core
from launch_settings import Capabilities,IntentStore,OfflineSteamBackend

class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.fixture=core.CoreHardeningTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.e=self.fixture.m;self.e.STATE_ROOT=self.e.STATE_ROOT.resolve();self.game=self.fixture.game
        self.original='MANGOHUD=1 %command% --custom'
        self.config=self.fixture._steam_localconfig(self.original)
        self.e.steam_running=lambda:False
        self.account={'localconfig':self.config,'shortcuts':self.config.parent/'shortcuts.vdf','userid':'42','root':self.e.STEAM_ROOT_CANDIDATES[0],'score':1}
        self.e.choose_steam_user_config=lambda *args,**kwargs:self.account
        self.baseline=self.fixture._baseline(current={'installed_hashes':{},'launch_options':'WINEDLLOVERRIDES="dxgi=n,b" %command%'})
        self.backend=OfflineSteamBackend(self.e);self.backend.capabilities=Capabilities('offline fixture')
        self.store=IntentStore(self.e)
        self.intent=self.new_intent('install')
    def new_intent(self,op):
        value=self.store.prepare(self.game,op,self.baseline['current']['launch_options'],self.e.load_baseline(self.game.target_dir))
        return self.store.files_applied(self.game,value,self.e.load_baseline(self.game.target_dir))
    def install_setup(self):
        result=self.backend.apply(self.intent,self.game);self.assertEqual(result['status'],'verified')
        return self.e.load_baseline(self.game.target_dir)
    def test_reuse_unchanged_saved_setup_reads_only_while_steam_runs(self):
        self.install_setup();intent=self.new_intent('repair');before=self.config.read_bytes();self.e.steam_running=lambda:True
        with patch.object(self.e,'sync_launch_options_batch',side_effect=AssertionError('no sync')),patch.object(self.e,'recover_pending_steam_transactions',side_effect=AssertionError('no recovery')),patch.object(self.e,'atomic_write',side_effect=AssertionError('no write')):
            result=self.backend.cached_result(intent,self.game)
        self.assertEqual(result['status'],'configured');self.assertIn('live client state is unverified',result['verification'])
        self.assertEqual(self.config.read_bytes(),before)
    def test_reuse_refuses_account_change_and_changed_proxy_requirement(self):
        self.install_setup();intent=self.new_intent('repair');before=self.config.read_bytes()
        self.account['userid']='43';self.assertIsNone(self.backend.cached_result(intent,self.game));self.account['userid']='42'
        intent['required']='WINEDLLOVERRIDES="winmm=n,b" %command%'
        self.assertIsNone(self.backend.cached_result(intent,self.game));self.assertEqual(self.config.read_bytes(),before)
    def test_owned_override_drift_is_not_rewritten_by_reuse_or_offline_retry(self):
        self.install_setup();intent=self.new_intent('repair')
        self.e.update_localconfig_launch_options(self.config,{'123':'MANGOHUD=1 WINEDLLOVERRIDES="dxgi=b" %command% --custom'})
        before=self.config.read_bytes()
        self.assertIsNone(self.backend.cached_result(intent,self.game))
        self.assertEqual(self.backend.apply(intent,self.game)['status'],'pending')
        self.assertEqual(self.config.read_bytes(),before)
    def test_uninstall_restores_owned_metadata_after_game_baseline_removed(self):
        baseline=self.install_setup();intent=self.store.prepare(self.game,'uninstall',self.baseline['current']['launch_options'],baseline)
        self.e.baseline_path(self.game.target_dir).unlink();intent=self.store.files_applied(self.game,intent)
        result=self.backend.apply(intent,self.game)
        self.assertEqual(result['status'],'verified');self.assertEqual(self.e.read_localconfig_launch_options(self.config,'123'),self.original)
        self.assertFalse(self.e.baseline_path(self.game.target_dir).exists())
    def test_retry_after_metadata_commit_before_intent_result_survives(self):
        self.install_setup() # Intent result deliberately remains pending on disk.
        result=self.backend.apply(self.store.load(self.game),self.game)
        self.assertEqual(result['status'],'verified')
    def test_steam_restart_blocks_rollback_write_and_retains_recovery(self):
        original=self.e.atomic_write;started={'value':False}
        self.e.steam_running=lambda:started['value']
        def write_then_start(path,*args,**kwargs):
            original(path,*args,**kwargs)
            if Path(path)==self.config:
                started['value']=True
                raise OSError('fixture interruption after VDF write')
        self.e.atomic_write=write_then_start
        result=self.backend.apply(self.intent,self.game)
        self.assertEqual(result['status'],'pending')
        self.assertIn('rollback',result['error'].lower())
        self.assertTrue(self.e.load_pending_steam_transactions())
        self.assertIn('WINEDLLOVERRIDES',self.e.read_localconfig_launch_options(self.config,'123'))

if __name__=='__main__':unittest.main()
