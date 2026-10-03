"""Explicit, hash-guarded standalone tool deployment, separate from providers."""
from pathlib import Path
import json
import shutil
import uuid
import discovery
import engine_bridge
import runtime_updates
import transactions as t
from storage import storage

KINDS={'reshade':'ReShade (DirectX 10–12)', 'addon':'ReShade add-on (including RenoDX)'}


def eligibility(config,game):
    root=t.safe(game['game'])
    found=discovery.inspect_game(discovery.Game('',game['name'],str(root),game.get('source','Folder')))
    t.need(found.exe and not found.anti_cheat,'An eligible x64 game without detected anti-cheat is required')
    relative=t.relative(game['exe']);exe=t.safe(root/relative)
    t.need(exe.is_file(),'Selected executable is unavailable');t.executable_check(exe)
    engine=engine_bridge.module(config)
    t.need(not engine._running_processes_under_root(root),'Close the game before changing its tools')
    return root,exe.parent,engine


def prepare(config,game,source,kind):
    t.need(kind in KINDS,'Unsupported tool type')
    root,directory,engine=eligibility(config,game)
    source=t.safe(source);t.need(source.is_file(),'Choose a regular x64 DLL or add-on')
    t.need(source.stat().st_size<=128*1024**2,'Tool exceeds 128 MiB limit');t.executable_check(source)
    if kind=='reshade':
        data=source.read_bytes()
        t.need(b'ReShade' in data or 'ReShade'.encode('utf-16le') in data,'No ReShade identification found; choose an extracted ReShade64.dll')
        target=directory/'dxgi.dll'
    else:
        t.need(source.name.lower().endswith('.addon64'),'Only x64 .addon64 add-ons are supported')
        target=directory/source.name
        # A provider may use ReShade under a different proxy, so recognize by bytes.
        candidates=[directory/name for name in ('dxgi.dll','d3d12.dll','ReShade64.dll')]
        t.need(any(p.is_file() and not p.is_symlink() and p.stat().st_size<128*1024**2 and b'ReShade' in p.read_bytes() for p in candidates),'Install ReShade before an add-on')
    t.safe(target)
    listing=t.files(root);rel=target.relative_to(root).as_posix()
    t.need(rel.casefold() not in listing,'Target already exists; restore its owning tool first: '+rel)
    t.need(not runtime_updates._owned(engine,root,target),'Target belongs to the feature provider')
    digest=t.digest(source)
    # Freeze input outside the game; the review identifies exact content.
    cached=storage(config)/'extras-cache'/digest/source.name
    if not cached.exists():t.atomic_file(cached,source.read_bytes(),0o600)
    t.need(t.digest(cached)==digest,'Cached tool hash mismatch')
    plan={'game':str(root),'name':game['name'],'exe':game['exe'],'kind':kind,
          'listing':listing,'inputs':{str(cached):digest},'conflicts':[],
          'changes':[{'path':rel,'before':None,'after':digest,'source':str(cached)}]}
    plan['plan_sha256']=t.sha(json.dumps(plan,sort_keys=True).encode());return plan


def apply(config,plan):
    t.check_plan(plan)
    root,directory,engine=eligibility(config,plan)
    t.need(plan['kind'] in KINDS and len(plan['changes'])==1,'Invalid tool plan')
    change=plan['changes'][0];target=t.safe(root/t.relative(change['path']))
    t.need(target.parent==directory and change['before'] is None,'Invalid tool destination')
    t.need(target.name=='dxgi.dll' if plan['kind']=='reshade' else target.name.lower().endswith('.addon64'),'Invalid tool filename')
    t.need(not runtime_updates._owned(engine,root,target),'Tool ownership changed')
    t.need(shutil.disk_usage(root).free>Path(change['source']).stat().st_size+64*1024**2,'Insufficient game disk space')
    base=storage(config)/'extras-transactions';base.mkdir(parents=True,exist_ok=True)
    state=base/uuid.uuid4().hex
    try:t.apply_transaction(plan,state)
    except Exception:
        if (state/'transaction.json').exists():
            doc=t.read_json(state/'transaction.json')
            if doc['status'] in ('applying','interrupted'):t.rollback_transaction(state,True)
        raise
    return state


def recoveries(config,game=None):
    result=[]
    for record in (storage(config)/'extras-transactions').glob('*/transaction.json'):
        doc=t.read_json(record)
        if doc['status'] not in ('complete','applying','interrupted'):continue
        if game and doc['plan']['game']!=game['game']:continue
        result.append({'path':str(record.parent),'name':doc['plan']['name'],'kind':doc['plan']['kind'],'date':doc['created_utc']})
    return sorted(result,key=lambda r:r['date'],reverse=True)


def restore(config,state):
    state=t.safe(state);t.need(state.parent==storage(config)/'extras-transactions','Invalid tool recovery')
    doc=t.read_json(state/'transaction.json');root,_,engine=eligibility(config,doc['plan'])
    for change in doc['plan']['changes']:
        t.need(not runtime_updates._owned(engine,root,root/t.relative(change['path'])),'Tool now belongs to a provider; restore that provider first')
    return t.rollback_transaction(state,True)
