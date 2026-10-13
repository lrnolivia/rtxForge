"""Read-only batch preflight, exact paths and fingerprints. No game mutation here."""
import pathlib,json,re
import transactions as t
import profiles
import pipeline
import compatibility
from ownership import import_record
P=pathlib.Path
NR={'nvngx_dlssnr.dll','nvngx.dll_dlssnr.dll'}
MARKERS={'optiscaler_nr_mfg_bazzite.txt','optiscaler_dlss5_mfg_autoinstall.txt'}
def native_debug_helper(path):
    # Identification for preserving a game dependency, never permission to overwrite it.
    if path.name.lower()!='dbghelp.dll' or path.stat().st_size>20*1024**2:return False
    data=path.read_bytes()
    fields=[v.decode('utf-16le') for v in re.findall(rb'(?:[\x20-\x7e]\x00){5,}',data)]
    pairs=dict(zip(fields,fields[1:]))
    return pairs.get('CompanyName')=='Microsoft Corporation' and pairs.get('OriginalFilename','').lower()=='dbghelp.dll' and pairs.get('FileDescription')=='Windows Image Helper'

def history(state,game,all_status=False):
    root=state/'transactions'/t.sha(str(game).encode())[:20]
    return sorted((p for p in root.glob('*/transaction.json') if all_status or t.read_json(p).get('status')=='complete'),reverse=True)

def owned_files(target,state,game,exe):
    if target.get('manifest'):
        path=t.safe(target['manifest']);return import_record(path,game,exe,target.get('record')),path
    recent=history(state,game)
    if recent:return import_record(recent[0],game,exe),recent[0]
    for parent in list(game.parents)[:5]:
        for path in sorted((parent/'_OptiScaler_MFG_Backups').glob('*/manifest.json'),reverse=True):
            try:return import_record(path,game,exe,target.get('record')),path
            except (t.Refusal,ValueError,KeyError):pass
    return {},None

def finalize(plan):
    plan['plan_sha256']=t.sha(json.dumps(plan,sort_keys=True).encode());return plan

def make(target,state,sources,operation='install',adopt=False):
    game=t.safe(target['game']);exe=target['exe'];t.relative(exe);t.executable_check(game/exe)
    mode=target['mode'];t.need(mode in profiles.MODES,'Unsupported route')
    files=t.files(game);directory=P(exe).parent;prefix='' if str(directory)=='.' else directory.as_posix()+'/'
    for p in history(state,game,True):t.need(t.read_json(p).get('status') not in ('applying','interrupted'),'Recover interrupted transaction first: '+str(p.parent))
    owned,origin=owned_files(target,state,game,exe);owned={files.get(r.casefold(),r):h for r,h in owned.items()}
    native=[r for r in files.values() if P(r).name.lower() in ('nvngx_dlssg.dll','sl.dlss_g.dll') and 'optiscaler' not in [part.lower() for part in P(r).parts]]
    t.need(native,'No native DLSS-G evidence; NR-only fallback has been removed')
    for r in files:
        t.need(not any(name in r for name in ('easyanticheat','battleye','eaanticheat','anticheatexpert','start_protected_game')),'Anti-cheat evidence: '+r)
    proxies=[r for r in files.values() if P(r).parent==directory and P(r).name.lower() in t.PROXIES]
    preserved_helpers={r for r in proxies if r not in owned and native_debug_helper(game/r)}

    # Preserve exact game-side proxy-shaped DLLs that have been explicitly
    # compatibility-profiled. They remain external inputs and are never
    # adopted or overwritten by RTXForge.
    for r in proxies:
        if r in owned or r in preserved_helpers:
            continue
        reason=compatibility.preserved_proxy_reason(
            target,
            r,
            t.digest(game/r),
        )
        if reason:
            preserved_helpers.add(r)

    proxies=[r for r in proxies if r not in preserved_helpers]
    proxy=target.get('proxy') or (P(proxies[0]).name.lower() if len(proxies)==1 else 'dxgi.dll')
    t.need(proxy in t.SUPPORTED_PROXIES,'Unsupported existing alias; select dxgi/winmm/version explicitly')
    t.need(target.get('api','dx12')!='vulkan' or proxy!='dxgi.dll','Native Vulkan needs an imported winmm/version alias')
    ini_rel=files.get((prefix+'OptiScaler.ini').casefold(),prefix+'OptiScaler.ini');ini=game/ini_rel
    wanted={prefix+(proxy if n=='OptiScaler.dll' else n):{'source':str(p),'hash':h} for n,(p,h) in sources.items()}
    if mode=='mfg-only':
        wanted={r:row for r,row in wanted.items() if P(r).name.lower() not in NR}
    else:t.need(prefix+'nvngx_dlssnr.dll' in wanted and prefix+'nvngx.dll_dlssnr.dll' in wanted,'NR + MFG needs both NR components')
    adopted=False
    if adopt:
        recognized=[r for r in proxies if (game/r).stat().st_size<100*1024**2 and b'optiscaler' in (game/r).read_bytes().lower()]
        # Adoption is only for an external install that exists right now. A historical
        # RTXForge record or a clean post-uninstall game must fall through to Fresh Install.
        if len(recognized)==1 and ini.is_file():
            adopted=True
            for rel in list(wanted)+recognized+[prefix+n for n in MARKERS]:
                actual=files.get(rel.casefold())
                if actual:owned[actual]=t.digest(game/actual)
    conflicts=[];inputs={str(game/exe):t.digest(game/exe)}
    if origin:inputs[str(origin)]=t.digest(origin)
    for r in native:inputs[str(game/r)]=t.digest(game/r)
    for rel in preserved_helpers:inputs[str(game/rel)]=t.digest(game/rel)
    for rel in files.values():
        n=P(rel).name.lower()
        # Only active binaries beside this executable participate in proxy conflicts.
        # Licenses, other executables and engine redistributables are not injectors.
        if P(rel).parent!=directory or rel in preserved_helpers:continue
        if n in {'dlssg_to_fsr3_amd_is_better.dll','dlss-enabler-headless.dll'} and rel.casefold()!=(prefix+'OptiScaler/dlss-enabler-headless.dll').casefold():
            conflicts.append('Competing frame-generation provider: '+rel)
        provider=n in t.PROXIES|{'nvngx.dll','nvapi64.dll','optiscaler.dll'} or n.endswith(('.asi','.addon32','.addon64')) or (n.endswith('.dll') and 'renodx' in n)
        if provider and (rel not in owned or n not in t.PROXIES|{'optiscaler.dll'}):conflicts.append('Competing/unowned graphics file: '+rel)
    template=P(sources['OptiScaler.ini'][0]).read_text(encoding='utf-8-sig');old=ini.read_text(encoding='utf-8-sig') if ini.is_file() else None
    mfg=compatibility.route_for(target)
    text=profiles.render(template,old,mode,mfg['key']);wanted[prefix+'OptiScaler.ini']={'text':text,'hash':t.sha(text.encode())}
    # Preserve the user's Artur configuration after initial seeding.
    artur=files.get((prefix+'OptiScaler/nvngx.ini').casefold())
    if artur and prefix+'OptiScaler/nvngx.ini' in wanted:
        p=game/artur;wanted[prefix+'OptiScaler/nvngx.ini']={'source':str(p),'hash':t.digest(p)}
    changes=[];managed=[]
    for rel,item in wanted.items():
        actual=files.get(rel.casefold(),rel);p=game/actual;before=t.digest(p) if p.exists() else None
        if before and before!=item['hash'] and actual not in owned:conflicts.append('Unowned replacement: '+actual+'; provide manifest or explicitly adopt recognized files')
        if actual in owned and before and before!=owned[actual] and p.suffix.lower()!='.ini' and operation!='repair':conflicts.append('Owned binary drift: '+actual+'; repair preserves and replaces changed owned bytes')
        # Newly supplied files and already owned files stay manageable. Unchanged external files stay external.
        if actual in owned or before!=item['hash']:managed.append({'path':actual,'after':item['hash']})
        if before!=item['hash'] or (p.name.lower()=='optiscaler.ini' and p.exists() and not p.stat().st_mode&0o200):
            changes.append({'path':actual,'before':before,'after':item['hash'],'write_mode':0o664 if p.name.lower()=='optiscaler.ini' else 0o644,**{k:v for k,v in item.items() if k!='hash'}})
        if 'source' in item:inputs[item['source']]=item['hash']
    wanted_keys={r.casefold() for r in wanted}
    for rel,h in owned.items():
        if rel.casefold() in wanted_keys:continue
        n=P(rel).name.lower();p=game/rel
        obsolete=P(rel).parent==directory and n in t.PROXIES|MARKERS|{'optiscaler.dll'}
        if (mode=='mfg-only' and n in pipeline.NR_NAMES) or (n in pipeline.LEGACY_NAMES and (directory/'OptiScaler') in P(rel).parents) or obsolete:
            if p.exists():changes.append({'path':rel,'before':t.digest(p),'after':None})
        else:managed.append({'path':rel,'after':h})
    # Switching to MFG Only explicitly removes the two exact NR files beside the selected exe,
    # even when an old installer reused (and never registered) the NR runtime. Both are backed up.
    if mode=='mfg-only':
        changed={r['path'].casefold() for r in changes}
        for n in NR:
            actual=files.get((prefix+n).casefold())
            if actual and actual.casefold() not in changed:changes.append({'path':actual,'before':t.digest(game/actual),'after':None})
    return finalize({'schema':1,'pipeline':pipeline.PIPELINE,'migration_advice':'Fully uninstall the previous package before changing providers or deployment methods.','observed_utc':t.now(),'game':str(game),'exe':exe,'mode':mode,'operation':operation,'listing':files,'inputs':inputs,'changes':changes,'managed':managed,'conflicts':conflicts,'proxy':proxy,'adopted':adopted,'mfg_route':mfg['key'],'mfg_route_label':mfg['label'],'mfg_route_reason':mfg['reason'],'mfg_profiled':mfg['profiled'],'nr_panel':'visible' if mode=='nr-mfg' else 'hidden with RTXForge loader'})

def remove(target,state):
    game=t.safe(target['game']);exe=target['exe'];t.relative(exe);owned,origin=owned_files(target,state,game,exe);t.need(owned,'No ownership record; no broad cleanup is performed')
    changes=[];conflicts=[];prefix=P(exe).parent
    for rel,h in owned.items():
        t.relative(rel);p=t.safe(game/rel);n=p.name.lower()
        # Private bundled NVIDIA modules are ours only when recorded; native game files are never removed.
        private=(prefix/'OptiScaler') in P(rel).parents
        if (n in t.NATIVE or n.startswith('sl.')) and not private:continue
        if p.exists():
            before=t.digest(p)
            if before!=h and p.suffix.lower()!='.ini':conflicts.append('Changed owned file: '+rel)
            changes.append({'path':rel,'before':before,'after':None})
    return finalize({'schema':1,'observed_utc':t.now(),'game':str(game),'exe':exe,'mode':target.get('mode','mfg-only'),'operation':'uninstall','listing':t.files(game),'inputs':{str(origin):t.digest(origin)},'changes':changes,'managed':[],'conflicts':conflicts})
