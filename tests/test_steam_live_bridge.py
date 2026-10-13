"""No sockets or Steam calls: fixture-test the bounded companion contract."""
from copy import deepcopy
from dataclasses import asdict,replace
import hashlib,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine/tests'))
import test_v13_core_hardening as core
from launch_settings import IntentStore
from steam_live_bridge import Binding,CompanionBackend
import transactions as t
from test_launch_settings import FixtureEngine
import tempfile


class Peer:
    authenticated_current_user=True
    def __init__(self,binding,value):
        self.binding=binding;self.value=value;self.writes=[];self.reads=0;self.noop=False;self.change_at=None
    def hello(self):return {'protocol':1,**asdict(self.binding),'app_setter_readback_verified':True}
    def read_app(self,appid):
        self.reads+=1
        if self.reads==self.change_at:self.value+=' --user-edit'
        return {**asdict(self.binding),'appid':appid,'launch_options':self.value}
    def compare_and_set_app(self,request):
        assert set(request)=={'protocol','steam_id64','client_instance_id','steam_build','peer_user_id','appid','operation_id','expected','expected_sha256','desired'}
        assert request['appid']=='123'
        assert all(request[k]==v for k,v in asdict(self.binding).items())
        assert request['expected_sha256']==hashlib.sha256(request['expected'].encode()).hexdigest()
        if request['expected']!=self.value:return {'status':'conflict'}
        self.writes.append(deepcopy(request))
        if not self.noop:self.value=request['desired']
        return {'status':'applied'}


class LiveContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.e=FixtureEngine(Path(self.temp.name).resolve())
        self.e.install_target();engine=core.load_engine()
        self.e.merge_rtxengine_launch_options=engine.merge_rtxengine_launch_options
        self.e.reconcile_rtxengine_launch_options=engine.reconcile_rtxengine_launch_options
        self.binding=Binding('76561198000000000','fixture-client','fixture-20261013','fixture-current-user')
        self.before='MANGOHUD=1 gamescope -- %command% -dx12'
        self.peer=Peer(self.binding,self.before)
        self.backend=CompanionBackend(self.e,self.peer,self.binding,[self.binding.steam_build])
        self.store=IntentStore(self.e)
        value=self.store.prepare(self.e.game,'install','WINEDLLOVERRIDES="dxgi=n,b" %command%',self.e.load_baseline(self.e.target))
        value=self.backend.bind_intent(value,self.e.game)
        self.intent=self.store.files_applied(self.e.game,value,self.e.load_baseline(self.e.target))
    def test_live_readback_preserves_wrappers_and_arguments_without_vdf(self):
        result=self.backend.apply(self.intent,self.e.game)
        self.assertEqual(result['status'],'verified');self.assertIn('restart persistence unverified',result['verification'])
        self.assertIn('MANGOHUD=1',self.peer.value);self.assertIn('gamescope -- %command% -dx12',self.peer.value)
        self.assertIn('dxgi=n,b',self.peer.value);self.assertEqual(len(self.peer.writes),1)
        saved=self.store.load(self.e.game)
        self.assertEqual(saved['live_journal']['before'],self.before)
        self.assertEqual(saved['live_journal']['state'],'live-confirmed')
        self.e.choose_steam_user_config.assert_not_called();self.e.sync_launch_options_batch.assert_not_called()
    def test_account_change_invalidates_and_performs_no_set(self):
        self.peer.binding=replace(self.binding,steam_id64='76561198000000001')
        self.assertEqual(self.backend.apply(self.intent,self.e.game)['status'],'pending')
        self.assertFalse(self.backend.capabilities.available);self.assertFalse(self.peer.writes)
    def test_client_instance_change_performs_no_set(self):
        self.peer.binding=replace(self.binding,client_instance_id='other-client')
        self.assertEqual(self.backend.apply(self.intent,self.e.game)['status'],'pending');self.assertFalse(self.peer.writes)
    def test_unknown_build_and_unauthenticated_peer_refuse(self):
        self.backend.approved_builds=frozenset()
        with self.assertRaises(t.Refusal):self.backend.bind_intent(self.intent,self.e.game)
        self.backend.approved_builds=frozenset([self.binding.steam_build]);self.peer.authenticated_current_user=False
        self.assertEqual(self.backend.apply(self.intent,self.e.game)['status'],'pending');self.assertFalse(self.peer.writes)
    def test_stale_read_before_set_preserves_user_edit(self):
        self.peer.change_at=2
        result=self.backend.apply(self.intent,self.e.game)
        self.assertEqual(result['status'],'pending');self.assertIn('changed',result['error'])
        self.assertTrue(self.peer.value.endswith('--user-edit'));self.assertFalse(self.peer.writes)
    def test_noop_setter_is_never_claimed_verified(self):
        self.peer.noop=True
        result=self.backend.apply(self.intent,self.e.game)
        self.assertEqual(result['status'],'pending');self.assertEqual(self.peer.value,self.before)
        self.assertEqual(self.store.load(self.e.game)['live_journal']['state'],'uncertain')
    def test_journal_failure_stops_before_set(self):
        original=self.e.save_json_atomic
        self.e.save_json_atomic=lambda *args:(_ for _ in ()).throw(t.Refusal('fixture journal failed'))
        with self.assertRaises(t.Refusal):self.backend.apply(self.intent,self.e.game)
        self.e.save_json_atomic=original;self.assertFalse(self.peer.writes)
    def test_rollback_refuses_later_user_edits(self):
        self.backend.apply(self.intent,self.e.game);self.peer.value+=' --later-edit'
        with self.assertRaises(t.Refusal):self.backend.rollback_owned_write(self.intent,self.e.game)
        self.assertTrue(self.peer.value.endswith('--later-edit'));self.assertEqual(len(self.peer.writes),1)
    def test_exact_owned_rollback_restores_original(self):
        self.backend.apply(self.intent,self.e.game)
        result=self.backend.rollback_owned_write(self.intent,self.e.game)
        self.assertEqual(result['status'],'rolled-back');self.assertEqual(self.peer.value,self.before)
    def test_wrong_assigned_app_and_windows_runtime_refuse(self):
        self.intent['appid']='124'
        self.assertEqual(self.backend.apply(self.intent,self.e.game)['status'],'pending')
        self.intent['appid']='123';self.intent['runtime']='windows-native'
        self.assertEqual(self.backend.apply(self.intent,self.e.game)['status'],'pending');self.assertFalse(self.peer.writes)
    def test_shortcut_setter_unverified_keeps_task_unbound(self):
        self.e.game.appid=None;self.e.game.source='Non-Steam'
        value=deepcopy(self.intent);value.pop('steam_binding');value['appid']=None
        value=self.backend.bind_intent(value,self.e.game)
        self.assertNotIn('steam_binding',value)
        self.assertEqual(self.backend.apply(value,self.e.game)['status'],'pending');self.assertFalse(self.peer.writes)


if __name__=='__main__':unittest.main()
