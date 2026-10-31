"""Required managed-overlay refresh after installing a verified app bundle.

The platform adapter supplies the existing ownership-checked planner/executor.
Running games, foreign files and incomplete bundles remain pending for retry.
"""
from pathlib import Path
import hashlib
import json
import threading

import transactions as t

_lock=threading.Lock()
_workers={}
_workers_lock=threading.Lock()


def start(root,state,prepare,execute,stop=None,report=None):
    """One retry worker per installed bundle/state, independent of panel preferences."""
    key=(str(Path(root).resolve()),str(Path(state).resolve()))
    # Source checkouts and development bundles never mutate games at startup.
    if not (Path(root)/'providers/glass-overlay/rollout.json').is_file():return None
    with _workers_lock:
        existing=_workers.get(key)
        if existing and existing.is_alive():return existing
        stop=stop or threading.Event()
        def work():
            while not stop.is_set():
                try:
                    result=run(root,state,prepare,execute)
                    if report:report(result)
                    if result.get('status') in ('not-required','current','complete','newer-revision-kept'):return
                except Exception as error:
                    if report:report({'status':'pending','error':str(error)})
                stop.wait(30)
        worker=threading.Thread(target=work,name='overlay-refresh',daemon=True)
        _workers[key]=worker
        worker.start()
        return worker


def bundle(root):
    folder=Path(root)/'providers/glass-overlay'
    rollout=folder/'rollout.json'
    if not rollout.is_file():
        return None
    spec=t.read_json(t.safe(rollout))
    t.need(spec.get('schema') == 1 and type(spec.get('revision')) is int and spec['revision'] > 0,
           'Overlay refresh policy is invalid.')
    if spec.get('required') is not True:
        return None
    manifest=folder/'package.json'
    t.need(manifest.is_file(), 'The required glass overlay bundle is incomplete. Reinstall this app update.')
    raw=manifest.read_bytes()
    t.need(len(raw)<65536, 'Overlay build receipt is too large.')
    receipt=json.loads(raw)
    t.need(receipt.get('schema') == 1 and receipt.get('renderer') == 'rmlui'
           and receipt.get('revision') == spec['revision'], 'Overlay revision differs from its update policy.')
    item=(receipt.get('files') or {}).get('rtxforge-glass.dll')
    dll=t.safe(folder/'rtxforge-glass.dll')
    t.need(isinstance(item,dict) and type(item.get('size')) is int and 0<item['size']<=64*1024**2
           and dll.is_file() and dll.stat().st_size==item['size'] and t.digest(dll)==item.get('sha256'),
           'The required overlay differs from its verified app bundle. Reinstall this app update.')
    return {'revision':spec['revision'],'bundle':hashlib.sha256(raw).hexdigest()}


def run(root,state,prepare,execute):
    """Refresh eligible installed overlays; repeat safely until all are current."""
    if not _lock.acquire(blocking=False):
        return {'status':'busy'}
    try:
        required=bundle(root)
        if required is None:
            return {'status':'not-required'}
        ledger=t.safe(Path(state)/'overlay-refresh.json')
        previous=t.read_json(ledger) if ledger.is_file() else {}
        if previous.get('revision',0)>required['revision']:
            return {'status':'newer-revision-kept'}
        if previous.get('bundle')==required['bundle'] and previous.get('status')=='complete':
            return dict(previous, status='current')
        review=prepare()
        result=execute(review) if review.get('plans') else {}
        blocked=review.get('blocked') or []
        updated_games = {game['target']: game for game in previous.get('updated_games', [])
                         if previous.get('bundle') == required['bundle']}
        for plan in review.get('plans') or []:
            key = str(plan.get('target') or plan.get('game') or plan['name'])
            updated_games[key] = {'target': key, 'title': plan['name']}
        record={**required,'status':'pending' if blocked else 'complete',
                'updated':len(updated_games), 'updated_games':list(updated_games.values()), 'blocked':blocked,
                'skipped':review.get('skipped') or [],'result':result}
        ledger.parent.mkdir(parents=True,exist_ok=True)
        t.atomic_file(ledger,(json.dumps(record,sort_keys=True)+'\n').encode(),0o600)
        return record
    finally:
        _lock.release()
