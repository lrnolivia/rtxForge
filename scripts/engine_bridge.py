"""Serialized desktop adapter for the RC1.38-derived transaction engine."""
from pathlib import Path
import importlib.util,sys,json,hashlib,zipfile,os
import transactions as t,packages,ui
from operation_session import Session,Cancelled
from storage import storage
ROOT=Path(__file__).resolve().parents[1]
def providers():return json.loads((ROOT/'providers/lock.json').read_text())
def module(config,provider='y4my',mode=None):
    name='rtxengine_desktop';spec=importlib.util.spec_from_file_location(name,ROOT/'engine/rtxengine.py')
    e=importlib.util.module_from_spec(spec);sys.modules[name]=e;spec.loader.exec_module(e)
    e.Y4MY_PROVIDER=providers()[provider]
    e.Y4MY_PROVIDER=e.Y4MY_PROVIDER.get('profile_pins',{}).get(mode,e.Y4MY_PROVIDER)
    # Retain terminal edition's namespace so its original backups remain authoritative.
    e.STATE_ROOT=Path(os.environ.get('RTXFORGE_DLSS_UNLOCKED_STATE',str(Path.home()/'.local/state/rtxforge-dlss-unlocked')))
    e.Y4MY_CACHE_DIR=storage(config)/'packages'/e.Y4MY_PROVIDER['sha256']
    e.USE_COLOR=False
    return e

def payload(e,config,mode,archive=None):
    p=e.Y4MY_PROVIDER;cache=storage(config,2*1024**3)/'packages'/p['sha256']
    archive=Path(archive) if archive else packages.download(p['url'],cache/p['archive'],expected=p['sha256'],size=p['release_size'])
    t.need(not archive.is_symlink() and t.digest(archive)==p['sha256'],'Provider archive hash mismatch')
    if p['id']=='y4my':
        companion=p.get('runtime_archive')
        required=e.Y4MY_REQUIRED_FILES
        try:
            if companion:e.Y4MY_REQUIRED_FILES=required[:3]
            data,meta=getattr(e,'original_archive_loader',e.load_archive_payload)(archive)
        finally:e.Y4MY_REQUIRED_FILES=required
        if companion:
            runtime=packages.download(companion['url'],cache/companion['archive'],expected=companion['sha256'],size=companion['release_size'])
            try:
                e.Y4MY_PROVIDER={**p,**companion}
                extra,_=getattr(e,'original_archive_loader',e.load_archive_payload)(runtime)
            finally:e.Y4MY_PROVIDER=p
            # Same-provider private NVIDIA runtime; never replace the nightly loader.
            for name,value in extra.items():
                if name.startswith('OptiScaler/streamline/') or name in ('OptiScaler/nvngx_dlss.dll','OptiScaler/nvngx_dlssd.dll','OptiScaler/nvngx_dlssg.dll'):
                    data[name]=value
            meta['runtime_archive']=companion

    else:
        names=packages.entries(archive)
        with zipfile.ZipFile(archive) as z:data={n:z.read(n) for n in names}
        t.need('dxgi.dll' in data and 'OptiScaler.ini' in data and 'OptiScaler/streamline/sl.interposer.dll' in data and 'OptiScaler/streamline/sl.dlss_g.dll' in data,'Unsupported DLSS-Unlocked package layout')
        t.need(hashlib.sha256(archive.read_bytes()).hexdigest()==p['sha256'],'Provider changed during extraction')
        meta={**p,'name':p['archive'],'path':str(archive),'provider':p['name']}
    # Alternate frame-generation backends are not installed or silently enabled.
    forbidden={'dlss-enabler-headless.dll','dlssg_to_fsr3_amd_is_better.dll'}
    data={n:v for n,v in data.items() if Path(n).name.lower() not in forbidden and '/dlssg_sm86/' not in n.lower()}
    if mode=='mfg-only':data={n:v for n,v in data.items() if Path(n).name.lower() not in {'nvngx_dlssnr.dll','nvngx.dll_dlssnr.dll','sl.dlss_nr.dll'}}
    # Root native runtime replacement would affect ordinary DLSS/2x after uninstall.
    t.need(not any('/' not in n and (n.lower() in {'nvngx_dlss.dll','nvngx_dlssd.dll','nvngx_dlssg.dll','nvapi64.dll'} or n.lower().startswith('sl.')) for n in data),'Provider contains native root runtime replacements; refusing')
    return data,meta

def game(e,row):
    root=Path(row['game']);exe=root/row['exe'];g=e.Game('',row['name'],root,row.get('source','Folder'),appid=row.get('appid'),exe=exe,target_dir=exe.parent)
    g=e.inspect_game(g)
    t.need(g.exe==exe,'Executable selection changed; refresh the library')
    return g

def fingerprint(e,g):
    # Snapshot only installer inputs, not the whole game or saves.
    target=g.target_dir;result={}
    for p in target.iterdir():
        if p.name.lower() in set(e.PROXY_NAMES)|{'optiscaler.ini','nvngx_dlssnr.dll'} or p==g.exe:
            t.need(not p.is_symlink(),'Linked installer input refused: '+str(p))
            if p.is_file():result[p.name]=e.sha256_file(p)
    opti=target/'OptiScaler'
    if opti.exists():result['OptiScaler/']=e._tree_manifest_data(opti)
    bp=e.baseline_path(target)
    result['baseline']=e.sha256_file(bp) if bp.is_file() else None
    return result

def desktop_mode(e):
    """Keep interactive/elevated terminal operations out of desktop operations."""
    def refuse(*args,**kwargs):
        raise e.Stop('This operation needs terminal interaction; use RTXForge --cli to resolve it.')
    e.ask=e.confirm=refuse
    def steam_closed(*args,**kwargs):
        if e.steam_running():raise e.Stop('Close Steam before applying changes.')
        return True
    e.ensure_steam_stopped_for_write=steam_closed
    original=e.subprocess
    class DesktopProcesses:
        def __getattr__(self,name):return getattr(original,name)
        def run(self,args,*a,**kw):
            if args and Path(args[0]).name=='sudo':refuse()
            return original.run(args,*a,**kw)
        def check_output(self,args,*a,**kw):
            if args and Path(args[0]).name=='sudo':refuse()
            return original.check_output(args,*a,**kw)
    e.subprocess=DesktopProcesses()

def prepare(config,rows,mode,operation,settings):
    e=module(config,settings.get('runtime_provider','y4my'),mode);data={};meta={};nr=None;nrmeta=None
    if operation in ('install','repair'):
        data,meta=ui.work('Verifying '+e.Y4MY_PROVIDER['name'],payload,e,config,mode)
        if mode in ('nr-mfg','nr-only') and 'nvngx_dlssnr.dll' not in data:
            # Local-only for y4my; missing per-game model is a per-target refusal.
            nr,nrmeta=e.load_user_nr_runtime(settings.get('nr_runtime') or None,family=None)
    strength=settings.get('nr_strength','strong');multiplier=settings.get('mfg_multiplier',2);sharpening=settings.get('sharpening_strength','strong')
    t.need(sharpening in e.NR_STRENGTH_PRESETS,'Unknown sharpening strength')
    t.need(type(multiplier) is int and multiplier in (0,2,3,4,5,6),'MFG multiplier must be Off or 2x through 6x')
    t.need(strength in e.NR_STRENGTH_PRESETS,'Unknown NR strength; choose Light, Medium or Strong in Settings')
    desktop_mode(e)
    ready=[];blocked=[];seen=[]
    for row in rows:
        try:
            g=game(e,row)
            t.need(not any(g.root.resolve().is_relative_to(p) or p.is_relative_to(g.root.resolve()) for p in seen),'Duplicate or overlapping game selection; refresh the library')
            seen.append(g.root.resolve())
            baseline=e.load_baseline(g.target_dir)
            if baseline:
                t.need(not any(v.get('kind') in ('tar_tree','tar_file') for v in baseline.get('originals',{}).values()),'Privileged backup requires terminal restore before desktop management')
            if operation=='reset':
                preview=e.reset_visual_settings(g,dry_run=True,nr_strength=strength,mfg_multiplier=multiplier,sharpening_strength=sharpening)
            elif operation=='uninstall':
                t.need(baseline,'No terminal-engine baseline; use legacy Undo for an older app install')
                e.verify_baseline_integrity(g.target_dir,baseline,adopt_legacy=False)
                e.verify_native_restore(baseline)
                preview={'files':baseline['managed_paths'],'proxy':(baseline.get('current') or {}).get('proxy',''),'launch_options':'Restore only recorded proxy override; preserve NVIDIA capability flags'}
            else:
                t.need(not row.get('blocked'),row.get('blocked',''))
                account=e.choose_steam_user_config([g],assume_yes=True)
                t.need(account is not None,'No Steam launch settings found; add the game to Steam before desktop installation')
                if not g.appid:
                    shortcuts=account['shortcuts']
                    match=e.match_shortcut_span(g,e.parse_shortcuts_spans(shortcuts.read_bytes())) if shortcuts.is_file() else None
                    t.need(match is not None,'No unique Steam shortcut targets this game directory. Add this copy as a separate Non-Steam game before desktop installation')

                if baseline:
                    old=(baseline.get('current') or {}).get('provider_id','y4my')
                    t.need((baseline.get('current') or {}).get('feature_mode',mode)==mode,'Uninstall before changing feature profiles so original runtime files are restored')
                    t.need(old==e.Y4MY_PROVIDER['id'],'Uninstall the current provider before switching providers; its original backups must be restored first')
                preview=e.install_target(g,data,meta,'ada',nr_runtime_payload=nr,nr_runtime_meta=nrmeta,feature_mode=mode,enable_effects=True,native_mfg_fallback=bool(settings.get('native_mfg_fallback',False)),nr_strength=strength,mfg_multiplier=multiplier,sharpening_strength=sharpening,dry_run=True)
            ready.append({'game':g,'row':row,'preview':preview,'fingerprint':fingerprint(e,g)})
        except (e.Stop,t.Refusal,OSError,ValueError) as ex:blocked.append({'name':row['name'],'reason':str(ex)})
    return {'kind':'engine','operation':operation,'title':operation.title(),'rows':[{'name':p['row']['name'],'detail':p['preview']['launch_options'] if operation=='reset' else f"{e.Y4MY_PROVIDER['name']} · {len(p['preview']['files'])} managed files · "+p['preview']['launch_options']} for p in ready],
            'blocked':blocked,'plans':ready,'engine':e,'payload':data,'meta':meta,'nr':nr,'nrmeta':nrmeta,'mode':mode,'enable_effects':True,'native_mfg_fallback':bool(settings.get('native_mfg_fallback',False)),'nr_strength':strength,'mfg_multiplier':multiplier,'sharpening_strength':sharpening}

def execute(review):
    e=review['engine'];results=[]
    # Never kill Steam behind a GUI action, or wait invisibly for terminal prompts.
    if review['operation']!='reset':t.need(not e.steam_running(),'Close Steam before applying changes so launch settings can be saved safely.')
    cancel=review.get('cancel_event')
    session=Session(e.STATE_ROOT/'desktop-operations') if cancel is not None else None
    with e.mutation_lock():
        for index,item in enumerate(review['plans'],1):
            if cancel is not None and cancel.is_set():break
            g=item['game'];ui.progress(f'{index}/{len(review["plans"])} · {g.name}')
            try:
                t.need(fingerprint(e,g)==item['fingerprint'],'Game or baseline changed since preview; prepare again')
                if session:
                    baseline=e.load_baseline(g.target_dir) or {}
                    names=set(item['preview'].get('files',[]))|set(item['preview'].get('remove',[]))|set(baseline.get('managed_paths',[]))|set(baseline.get('originals',{}))
                    if review['operation']=='reset':names={p.name for p in g.target_dir.iterdir() if p.name.lower()=='optiscaler.ini'}
                    else:names.add('OptiScaler')
                    paths=[g.target_dir/name for name in names]+[e.state_dir_for(g.target_dir)]
                    if review['operation']!='reset':
                        paths.extend([e.STATE_ROOT/'steam-config-backups',e._steam_transaction_root()])
                        account=e.choose_steam_user_config([g],assume_yes=True)
                        if account:paths.extend(account[k] for k in ('localconfig','shortcuts') if account.get(k))
                    checkpoint=session.capture(paths)
                if review['operation']=='reset':
                    record=e.reset_visual_settings(g,nr_strength=review['nr_strength'],mfg_multiplier=review['mfg_multiplier'],sharpening_strength=review['sharpening_strength'])
                elif review['operation']=='uninstall':
                    e.verify_native_restore(e.load_baseline(g.target_dir))
                    e.restore_launch_options_batch([g],assume_yes=True)
                    record=e.restore_target(g)
                else:
                    record=e.install_target(g,review['payload'],review['meta'],'ada',nr_runtime_payload=review['nr'],nr_runtime_meta=review['nrmeta'],feature_mode=review['mode'],enable_effects=review['enable_effects'],native_mfg_fallback=review.get('native_mfg_fallback',False),nr_strength=review['nr_strength'],mfg_multiplier=review['mfg_multiplier'],sharpening_strength=review['sharpening_strength'])
                    synced=e.sync_launch_options_batch([g],assume_yes=True,prompt=False)
                    t.need(synced and all(r.get('status')=='written' for r in synced),'Files installed, but launch settings need attention: '+str(synced or record['launch_options']))
                results.append({'name':g.name,'status':'complete','record':record})
            except Exception as ex:results.append({'name':g.name,'status':'failed','error':str(ex)})
            finally:
                if session and 'checkpoint' in locals():session.seal(checkpoint);del checkpoint
        if session:
            if cancel.is_set():
                t.need(not any(e._running_processes_under_root(p['game'].root.resolve()) for p in review['plans']),'Close running games before recovery. Copies retained at '+str(session.root))
                if review['operation']!='reset':t.need(not e.steam_running(),'Close Steam before recovery. Copies retained at '+str(session.root))
                session.rollback()
                raise Cancelled('Changes undone.')
            session.complete()
    path=e.STATE_ROOT/('desktop-'+e.now_stamp()+'.json');e.save_json_atomic(path,{'results':results})
    failures=sum(r['status']=='failed' for r in results)
    if failures:raise t.Refusal(f'{failures} game(s) need attention. Completed games retain backups. Report: {path}')
    return str(path)
