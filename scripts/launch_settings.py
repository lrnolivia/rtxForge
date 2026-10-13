"""Durable launch work, separate from the game-file transaction.

No Steam process is stopped and no live setter/private client integration is
installed here. Backends declare capability; the default is Linux/offline only.
"""
from copy import deepcopy
from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path
import hashlib, json, sys, uuid
import transactions as t
from operation_session import canonical


@dataclass(frozen=True)
class Capabilities:
    name: str
    live_setter: bool = False
    available: bool = True


class LaunchBackend:
    capabilities = Capabilities('Unavailable', available=False)

    def apply(self, intent, game):
        return {'status': 'pending', 'error': 'Launch setup is unavailable on this platform.'}

    def bind_intent(self,intent,game):
        return intent

    def cached_result(self,intent,game):
        return None


class IntentStore:
    def __init__(self, engine):
        self.engine = engine
        self.root = canonical(engine.STATE_ROOT) / 'launch-intents'

    def path(self, game):
        identity = str(Path(game.target_dir).resolve())
        return self.root / (hashlib.sha256(identity.encode()).hexdigest() + '.json')

    def load(self, game):
        path = t.safe(self.path(game))
        if not path.exists():
            return None
        t.need(path.stat().st_size <= 4 * 1024**2, 'Launch intent is too large')
        value = json.loads(path.read_text())
        t.need(value.get('schema') == 1 and value.get('target') == str(Path(game.target_dir).resolve()), 'Launch intent identity changed')
        return value

    def save(self, game, value):
        t.safe(self.path(game))
        self.engine.save_json_atomic(self.path(game), value)
        return value

    def prepare(self, game, operation, required, baseline):
        previous = self.load(game)
        t.need(operation in ('install', 'repair', 'uninstall'), 'Unknown launch intent')
        value = {
            'schema': 1, 'id': uuid.uuid4().hex, 'operation': operation,
            'state': 'prepared', 'game': game.name,
            'target': str(Path(game.target_dir).resolve()), 'root': str(game.root.resolve()),
            'exe': str(game.exe.resolve()) if game.exe else None,
            'appid': game.appid, 'source': game.source, 'runtime': 'linux-proton',
            'required': required, 'baseline': deepcopy(baseline or {}),
            'created': t.now(), 'verification': None,
            'previous_intent': {k: previous.get(k) for k in ('id', 'state', 'operation', 'verification')} if previous else None,
            'owned_launch': deepcopy(previous.get('owned_launch')) if previous else None,
        }
        return self.save(game, value)

    def files_applied(self, game, value, baseline=None):
        value = deepcopy(value)
        value.update(state='pending', files='restored' if value['operation'] == 'uninstall' else 'applied')
        if baseline is not None:
            value['baseline'] = deepcopy(baseline)
        value['baseline_digest'] = hashlib.sha256(json.dumps(value['baseline'], sort_keys=True).encode()).hexdigest()
        return self.save(game, value)

    def outcome(self, game, value, result):
        value = deepcopy(value)
        value['state'] = result['status']
        value['error'] = result.get('error')
        value['verification'] = result.get('verification')
        return self.save(game, value)

    def confirm_manual(self, game, intent_id):
        with self.engine.mutation_lock():
            value = self.load(game)
            t.need(value is not None and value['id'] == intent_id and value['state'] == 'pending', 'Launch task changed; refresh before confirming')
            return self.outcome(game, value, {'status': 'user-confirmed', 'verification': 'User confirmation only; not independently verified'})


class OfflineSteamBackend(LaunchBackend):
    def __init__(self, engine):
        self.engine = engine
        # The existing engine is Linux/Proton; never infer a Windows live backend.
        self.capabilities = Capabilities('Steam offline', available=sys.platform.startswith('linux'))

    @contextmanager
    def guarded_writer(self):
        # The engine can attempt metadata rollback after a failed write. Guard
        # every Steam VDF replacement, including rollback/recovery, so a Steam
        # restart pauses the transaction instead of overwriting its live state.
        e=self.engine;original=e.atomic_write
        def guarded(path,*args,**kwargs):
            path=Path(path)
            if path.name in ('localconfig.vdf','shortcuts.vdf') and 'userdata' in path.parts:
                t.need(not e.steam_running(),'Steam started during launch setup; metadata recovery is retained until Steam closes')
            return original(path,*args,**kwargs)
        e.atomic_write=guarded
        try:yield
        finally:e.atomic_write=original

    def cached_result(self,intent,game):
        """Read-only reuse of unchanged, owned, account-scoped saved setup.

        Steam's in-memory UI can differ from its file. This is deliberately a
        separate configured state, never a live-setter/readiness claim.
        """
        if not self.capabilities.available or intent['operation']=='uninstall':return None
        record=intent['baseline'].get('steam_launch')
        if not isinstance(record,dict) or record.get('kind')!='steam':return None
        e=self.engine
        try:
            e._validate_steam_launch_record(record)
            t.need(str(game.appid)==record['appid'],'Saved setup belongs to another app')
            account=e.choose_steam_user_config([game],assume_yes=True)
            t.need(account is not None and str(account['userid'])==record['steam_userid'] and Path(account['localconfig']).resolve()==Path(record['config_path']).resolve(),'Saved setup account changed or is ambiguous')
            observed=e.read_localconfig_launch_options(Path(record['config_path']),record['appid'])
            base=e.reconcile_rtxengine_launch_options(observed,record.get('original'),record.get('applied'))
            desired=e.merge_rtxengine_launch_options(base,intent['required'])
            if desired!=observed:return None
            return {'status':'configured','verification':'Owned launch setup matches saved Steam options for account '+record['steam_userid']+'; live client state is unverified'}
        except Exception:
            return None

    def apply(self, intent, game):
        e = self.engine
        if not self.capabilities.available:
            return {'status': 'pending', 'error': 'This platform has no verified launch-settings backend.'}
        if e.steam_running():
            return {'status': 'pending', 'error': 'Steam is running. Use its Launch Options or finish this task after closing Steam.'}
        try:
            with e.mutation_lock(),self.guarded_writer():
                # This guard precedes recovery and account/configuration access.
                if e.steam_running():
                    return {'status': 'pending', 'error': 'Steam started; launch setup remains pending.'}
                old_load = e.load_baseline
                if intent['operation'] == 'uninstall':
                    cached = intent['baseline']
                    if not isinstance(cached.get('steam_launch'), dict):
                        return {'status': 'pending', 'error': 'No verified owned launch record. Review launch-option cleanup in Steam and confirm it manually.'}
                    # restore_target has removed the game baseline. Retain the exact
                    # owned metadata record in app state; never recreate game files.
                    e._validate_steam_launch_record(cached['steam_launch'])
                    e.load_baseline = lambda target: deepcopy(cached) if Path(target).resolve() == Path(game.target_dir).resolve() else old_load(target)
                    try:
                        rows = e.restore_launch_options_batch([game], assume_yes=True)
                    finally:
                        e.load_baseline = old_load
                    record = cached['steam_launch']
                    expected = 'restored'
                else:
                    baseline = old_load(game.target_dir)
                    digest = hashlib.sha256(json.dumps(baseline, sort_keys=True).encode()).hexdigest()
                    before=deepcopy(intent['baseline']);now=deepcopy(baseline or {})
                    before.pop('steam_launch',None);now.pop('steam_launch',None)
                    # A crash after the writer committed its ownership record
                    # but before the intent result was saved is safely retryable.
                    metadata_only=before==now and isinstance((baseline or {}).get('steam_launch'),dict)
                    t.need(digest == intent['baseline_digest'] or metadata_only, 'Game install changed since launch setup was queued; prepare again')
                    owned=baseline.get('steam_launch')
                    if isinstance(owned,dict):
                        e._validate_steam_launch_record(owned)
                        account=e.choose_steam_user_config([game],assume_yes=True)
                        t.need(account and str(account['userid'])==owned['steam_userid'],'Owned launch account changed; setup requires review')
                        observed=e.read_localconfig_launch_options(Path(owned['config_path']),str(owned['appid'])) if owned['kind']=='steam' else e.read_shortcut_launch_option(Path(owned['config_path']),owned)
                        e.reconcile_rtxengine_launch_options(observed,owned.get('original'),owned.get('applied'))
                    rows = e.sync_launch_options_batch([game], assume_yes=True, prompt=False)
                    current = old_load(game.target_dir) or {}
                    record = current.get('steam_launch')
                    expected = 'written'
                if not rows or any(row.get('status') != expected for row in rows):
                    return {'status': 'pending', 'error': str(rows or 'Launch setting was not applied')}
                t.need(isinstance(record, dict), 'Launch ownership record is absent')
                if record['kind'] == 'steam':
                    observed = e.read_localconfig_launch_options(Path(record['config_path']), str(record['appid']))
                else:
                    observed = e.read_shortcut_launch_option(Path(record['config_path']), record)
                desired = record['applied'] if expected == 'written' else e.reconcile_rtxengine_launch_options(observed, record.get('original'), record.get('applied'))
                t.need(observed == desired, 'Launch settings readback differs; setup remains pending')
                return {'status': 'verified', 'verification': 'Offline Steam writer and owned-setting readback'}
        except Exception as exc:
            return {'status': 'pending', 'error': str(exc)}


def finish_pending(engine, game, intent_id, backend=None):
    """Explicit retry, not a background watcher or automatic Steam shutdown."""
    with engine.mutation_lock():
        store = IntentStore(engine)
        intent = store.load(game)
        t.need(intent is not None and intent['id'] == intent_id and intent['state'] == 'pending', 'Launch task changed; refresh before retrying')
        backend = backend or OfflineSteamBackend(engine)
        if engine.steam_running() and not backend.capabilities.live_setter:
            return intent
        result = backend.apply(intent, game)
        return store.outcome(game, intent, result)
