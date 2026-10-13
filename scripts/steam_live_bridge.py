"""Bounded Steam-side companion contract. No listener, CDP or plugin installer.

The supplied transport must authenticate the current OS user. A real transport
and each Steam build/setter require separate platform and persistence acceptance.
"""
from copy import deepcopy
from dataclasses import asdict,dataclass
import hashlib,re
from launch_settings import Capabilities,IntentStore,LaunchBackend
import transactions as t


@dataclass(frozen=True)
class Binding:
    steam_id64:str
    client_instance_id:str
    steam_build:str
    peer_user_id:str


class CompanionBackend(LaunchBackend):
    def __init__(self,engine,transport,binding,approved_builds):
        self.engine=engine;self.transport=transport;self.binding=binding
        self.approved_builds=frozenset(approved_builds)
        self.capabilities=Capabilities('Steam-side companion',live_setter=True,available=False)
        self.reason='No verified Steam-side session'

    def session(self):
        t.need(re.fullmatch(r'7656119\d{10}',self.binding.steam_id64 or '') is not None,'SteamID64 must be an exact string')
        t.need(bool(self.binding.client_instance_id) and len(self.binding.client_instance_id)<=128,'Client instance is absent')
        t.need(self.binding.steam_build in self.approved_builds,'Steam build is not approved for this adapter')
        t.need(getattr(self.transport,'authenticated_current_user',False),'Companion IPC is not authenticated to this OS user')
        hello=self.transport.hello()
        t.need(hello.get('protocol')==1 and all(hello.get(k)==v for k,v in asdict(self.binding).items()),'Steam account, client, build or OS peer changed; pair again')
        t.need(hello.get('app_setter_readback_verified') is True,'Steam app setter/readback capability is unverified')
        self.capabilities=Capabilities('Steam-side companion',live_setter=True,available=True)

    def bind_intent(self,intent,game):
        self.session()
        result=deepcopy(intent)
        if game.appid is None or game.source!='Steam' or not str(game.appid).isdigit() or not 0<int(game.appid)<2**32:
            result['launch_capability_error']='Steam shortcut/non-Steam setter requires separate acceptance'
            return result
        result['steam_binding']=asdict(self.binding)
        return result

    def read(self,appid):
        self.session()
        snapshot=self.transport.read_app(str(appid))
        t.need(snapshot.get('appid')==str(appid) and all(snapshot.get(k)==v for k,v in asdict(self.binding).items()),'Live readback identity does not match the assigned app/session')
        t.need(isinstance(snapshot.get('launch_options'),str) and len(snapshot['launch_options'].encode())<=65536,'Launch options are absent or too large')
        return snapshot['launch_options']

    def apply(self,intent,game):
        store=IntentStore(self.engine)
        try:
            self.session()
            t.need(intent.get('steam_binding')==asdict(self.binding),'Intent is not bound to this Steam session')
            t.need(intent.get('appid')==game.appid and intent['target']==str(game.target_dir.resolve()),'Assigned game identity changed')
            t.need(intent.get('runtime')=='linux-proton','This merger has only Linux/Proton acceptance; Windows needs its own runtime adapter')
            existing=self.read(game.appid)
            owned=intent.get('owned_launch')
            if owned:
                t.need(owned.get('steam_id64')==self.binding.steam_id64 and owned.get('appid')==str(game.appid),'Owned launch record belongs to another account/game')
                base=self.engine.reconcile_rtxengine_launch_options(existing,owned['before'],owned['applied'])
            else:
                t.need(intent['operation']!='uninstall','No owned live launch record; cleanup needs separate review')
                base=existing
            desired=base if intent['operation']=='uninstall' else self.engine.merge_rtxengine_launch_options(base,intent['required'])
            # Private setters do not guarantee atomic CAS. Detect stale edits
            # before invoking them; the companion must compare expected too.
            t.need(self.read(game.appid)==existing,'Steam launch options changed; refresh before retrying')
            journal={'operation_id':intent['id'],'steam_id64':self.binding.steam_id64,'client_instance_id':self.binding.client_instance_id,'steam_build':self.binding.steam_build,'appid':str(game.appid),'before':existing,'desired':desired,'state':'prepared','restart_persistence':'unverified'}
            intent['live_journal']=journal
            intent['owned_launch']={'steam_id64':self.binding.steam_id64,'appid':str(game.appid),'before':owned['before'] if owned else existing,'applied':desired}
            store.save(game,intent) # Durable before/after before invoking the setter.
            if desired!=existing:
                reply=self.transport.compare_and_set_app({'protocol':1,**asdict(self.binding),'appid':str(game.appid),'operation_id':intent['id'],'expected':existing,'expected_sha256':hashlib.sha256(existing.encode()).hexdigest(),'desired':desired})
                t.need(reply.get('status') in ('applied','already-applied'),'Companion refused or could not confirm the setter')
            observed=self.read(game.appid)
            t.need(observed==desired,'Setter readback differs; no blind rollback or live VDF fallback')
            journal['state']='live-confirmed';store.save(game,intent)
            return {'status':'verified','verification':'Steam live readback confirmed; restart persistence unverified'}
        except Exception as exc:
            self.reason=str(exc);self.capabilities=Capabilities('Steam-side companion',live_setter=True,available=False)
            if intent.get('live_journal'):
                intent['live_journal']['state']='uncertain';store.save(game,intent)
            return {'status':'pending','error':str(exc)}

    def rollback_owned_write(self,intent,game):
        """Explicitly reviewed metadata rollback; refuse intervening user edits."""
        journal=intent.get('live_journal')
        t.need(journal is not None and intent.get('steam_binding')==asdict(self.binding),'No matching live transaction')
        observed=self.read(game.appid)
        t.need(observed==journal['desired'],'Launch options changed after our write; rollback refused')
        reply=self.transport.compare_and_set_app({'protocol':1,**asdict(self.binding),'appid':str(game.appid),'operation_id':intent['id']+'-rollback','expected':observed,'expected_sha256':hashlib.sha256(observed.encode()).hexdigest(),'desired':journal['before']})
        t.need(reply.get('status') in ('applied','already-applied') and self.read(game.appid)==journal['before'],'Rollback readback is unverified')
        journal['state']='rolled-back';IntentStore(self.engine).save(game,intent)
        return {'status':'rolled-back','verification':'Exact owned-write rollback readback'}
