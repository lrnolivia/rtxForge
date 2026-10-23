"""Serialized desktop adapter for the RC1.38-derived transaction engine."""
from pathlib import Path
import importlib.util,sys,json,hashlib,zipfile,os,contextlib
import transactions as t,packages,ui,package_catalog,proton_prefix,cross_os,skynizz_provider,ada_mfg_provider
from operation_session import Session,Cancelled
from storage import storage
ROOT=Path(__file__).resolve().parents[1]
def providers():return json.loads((ROOT/'providers/lock.json').read_text())
def module(config,provider='y4my',mode=None):
    name='rtxengine_desktop';spec=importlib.util.spec_from_file_location(name,ROOT/'engine/rtxengine.py')
    e=importlib.util.module_from_spec(spec);sys.modules[name]=e;spec.loader.exec_module(e)
    e.Y4MY_PROVIDER=providers()[provider]
    e.Y4MY_PROVIDER=e.Y4MY_PROVIDER.get('profile_pins',{}).get(mode,e.Y4MY_PROVIDER)
    e.DESKTOP_PLATFORM=cross_os.THIS_OS
    # Retain terminal edition's namespace so its original backups remain authoritative.
    e.STATE_ROOT=Path(os.environ.get('RTXFORGE_DLSS_UNLOCKED_STATE',str(Path.home()/'.local/state/rtxforge-dlss-unlocked')))
    e.Y4MY_CACHE_DIR=storage(config)/'packages'/e.Y4MY_PROVIDER['sha256']
    e.USE_COLOR=False
    return e

def payload(e,config,mode,archive=None):
    p=e.Y4MY_PROVIDER
    if p.get('id')=='skynizz':
        bridge=p.get('variant')=='nr-mfg-bridge'
        skynizz_provider.require_mode(cross_os.THIS_OS,mode,bridge=bridge)
        cache=storage(config,skynizz_provider.MAX_ARCHIVE)/'packages'/p['sha256']
        if bridge:
            source=cache/p['archive']
            if not source.is_file():
                bundled,local=skynizz_provider.bundled_bridge(p['tag'])
                t.need(bundled['sha256']==p['sha256'],'The recorded bridge is not cached or bundled; repair cannot switch versions.')
                source=packages.download(local.resolve().as_uri(),source,expected=p['sha256'],size=p['release_size'])
        else:
            source=Path(archive) if archive else packages.download(p['url'],cache/p['archive'],expected=p['sha256'],size=p['release_size'])
        data,meta=skynizz_provider.load_payload(source,p)
        if bridge:
            # Reuse only the verified private MFG runtime, never its OptiScaler loader or INI.
            donor=providers()['y4my'];companion=donor['runtime_archive']
            runtime=packages.download(companion['url'],cache/companion['archive'],expected=companion['sha256'],size=companion['release_size'])
            required=e.Y4MY_REQUIRED_FILES
            try:
                e.Y4MY_PROVIDER={**donor,**companion}
                extra,_=getattr(e,'original_archive_loader',e.load_archive_payload)(runtime)
            finally:
                e.Y4MY_PROVIDER=p;e.Y4MY_REQUIRED_FILES=required
            private={n:v for n,v in extra.items() if n.startswith('OptiScaler/streamline/') or n in ('OptiScaler/nvngx_dlss.dll','OptiScaler/nvngx_dlssd.dll','OptiScaler/nvngx_dlssg.dll')}
            t.need({'OptiScaler/streamline/sl.interposer.dll','OptiScaler/streamline/sl.dlss_g.dll'}<=private.keys(),'The MFG companion runtime is incomplete')
            for component,(filename,_) in skynizz_provider.PRODUCTION_RUNTIMES.items():
                if not p.get(component):continue
                runtime=skynizz_provider.validate_production_runtime(p[component],component)
                path=storage(config,runtime['release_size'])/'runtime-cache'/runtime['sha256']/filename
                source=packages.download(runtime['url'],path,expected=runtime['sha256'],size=runtime['release_size'])
                private['OptiScaler/'+filename]=skynizz_provider.load_production_runtime(source,runtime,component)
                meta[component]=runtime
            data.update(private);meta['mfg_runtime']={**companion,'repository':donor['repo']}
            if p.get('mfg_component'):
                owner=skynizz_provider.mfg_component_module(p['mfg_component'])
                component=owner.validate(p['mfg_component'])
                data.update(owner.load_payload(config,component))
                meta['mfg_component']=component
        return data,meta
    if p.get('custom'):
        data,meta=package_catalog.load_custom_payload(p)
        if mode=='mfg-only':
            data={n:v for n,v in data.items() if Path(n).name.lower() not in {'nvngx_dlssnr.dll','nvngx.dll_dlssnr.dll','sl.dlss_nr.dll'}}
        return data,meta
    cache=storage(config,2*1024**3)/'packages'/p['sha256']
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
        if p.name.lower() in set(e.PROXY_NAMES)|{'optiscaler.ini','nvngx_dlssnr.dll','reshade.ini','reshade64.dll','renodx-mfgunlock.addon64'} or p==g.exe:
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

def prefix_state(e,g):
    """Where the record of a game's prefix overrides lives (outside the engine's target state)."""
    return e.STATE_ROOT/'prefix-overrides'/e.target_key(g.target_dir)

def steam_open_route(e,g,operation,baseline):
    """With Steam running, a game's Proton setting goes in its own prefix.

    Returns the prefix to use, or None when Steam is closed (LaunchOptions route).
    Raises a per-game reason when the change cannot be made with Steam open.
    """
    if not getattr(e,'steam_running',lambda:False)():return None
    if operation in ('install','repair'):
        prefix=proton_prefix.find_prefix(g.root,g.appid)
        t.need(not proton_prefix.prefix_in_use(prefix),'This game is running. Quit it, then try again.')
        return prefix
    if operation=='uninstall':
        t.need(not (baseline and isinstance(baseline.get('steam_launch'),dict)),"This game's launch setting is saved in Steam. Close Steam to restore it.")
        record=proton_prefix.load_record(prefix_state(e,g))
        if record:t.need(not proton_prefix.prefix_in_use(Path(record['prefix'])),'This game is running. Quit it, then try again.')
    return None

def windows_install(e,g,baseline):
    """An intact schema-1 install (no shared state) made by rtxForge on the other OS, with no local baseline."""
    if baseline:return None
    record=cross_os.other_install(g.target_dir,cross_os.THIS_OS)
    return None if record and record.get('shared_state') else record

OS_NAMES={'linux':'Linux','windows':'Windows'}

def shared_baseline(g):
    """The other OS's shared baseline as written (placeholders, not this OS's paths)."""
    return json.loads((cross_os.shared_state(g.target_dir)/'baseline.json').read_text(encoding='utf-8'))

def retire(e,g):
    """Move this OS's state for a game aside (kept, never deleted) so adopted or fresh state can replace it."""
    state=e.state_dir_for(g.target_dir)
    if state.exists():
        retired=e.STATE_ROOT/'cross-os-retired'/(e.target_key(g.target_dir)+'-'+e.now_stamp())
        retired.parent.mkdir(parents=True,exist_ok=True)
        os.replace(state,retired)

def adopt(e,g,record):
    """Take over the other OS's install of this game: its baseline and original-file backups become ours."""
    target=g.target_dir;state=e.state_dir_for(target)
    retire(e,g)
    baseline=cross_os.import_state(target,state,record['revision'])
    mine=(baseline.get('cross_os_extras') or {}).get(cross_os.THIS_OS) or {}
    baseline.pop('steam_launch',None)
    if mine.get('steam_launch'):baseline['steam_launch']=mine['steam_launch']
    current=baseline.get('current')
    if current:
        # Launch options are per OS: Proton overrides on Linux, nothing on Windows.
        same=mine.get('launch_options') and mine.get('proxy')==current.get('proxy')
        current['launch_options']=mine['launch_options'] if same else e.build_launch_options(current.get('proxy',''),current.get('reshade') or {'detected':False})
    baseline['cross_os_revision']=record['revision']
    e.verify_baseline_integrity(target,baseline,adopt_legacy=False)
    e.save_json_atomic(e.baseline_path(target),baseline)
    return baseline

def restored_elsewhere(e,g,baseline):
    """This OS's shared install was restored by the other OS: no record and none of its files remain as installed."""
    if not baseline or not baseline.get('cross_os_revision') or cross_os.read(g.target_dir):return False
    hashes=(baseline.get('current') or {}).get('installed_hashes') or {}
    def kept(rel):
        path=g.target_dir/rel
        return path.is_file() and not path.is_symlink() and e.sha256_file(path)==hashes[rel]
    return bool(hashes) and not any(kept(rel) for rel in hashes)

class _without_baseline:
    """Plan a fresh install over state that is about to be retired."""
    def __init__(self,e,g):self.e,self.g=e,g
    def __enter__(self):
        load=self.original=self.e.load_baseline;target=str(self.g.target_dir)
        self.e.load_baseline=lambda path,*a,**kw:None if str(path)==target else load(path,*a,**kw)
    def __exit__(self,*exc):self.e.load_baseline=self.original

def operations_root():
    """Where desktop operation sessions live (the engine's STATE_ROOT, see module())."""
    return Path(os.environ.get('RTXFORGE_DLSS_UNLOCKED_STATE',str(Path.home()/'.local/state/rtxforge-dlss-unlocked')))/'desktop-operations'

def installed_package(baseline):
    """What a baseline has actually installed (its 'current' record), or None.

    An install cut off before its first success has no current record: there is
    nothing installed to switch away from, and installing again finishes it.
    """
    current=(baseline or {}).get('current')
    return current if isinstance(current,dict) and current else None

def interrupted_install(baseline):
    """A first install that stopped partway (crash, forced shutdown, stalled drive)."""
    return bool(baseline) and not installed_package(baseline) and bool(baseline.get('pending_install')) and baseline.get('status') in ('applying','interrupted')

def check_switch(e,current,mode):
    """Refuse switching mode or package over an installed one; its originals must be restored first."""
    if not current:return
    t.need(current.get('feature_mode',mode)==mode,'Uninstall before changing feature profiles so original runtime files are restored')
    t.need(current.get('provider_id','y4my')==e.Y4MY_PROVIDER['id'],'Uninstall the current provider before switching providers; its original backups must be restored first')

STEAM_OWNED=('localconfig.vdf','shortcuts.vdf','user.reg')

def steam_owned(path):
    """Files Steam or Wine own and may have rewritten since: recovery reports them instead of rewriting."""
    return Path(path).name.lower() in STEAM_OWNED

# Experimental: Linux may adopt a Windows Skynizz install under Proton (DLL override
# only, no game files change). Fresh Skynizz installs on Linux stay Windows-only.
LINUX_SKYNIZZ_REFUSAL=('Skynizz installation/adoption is not available on Linux in this release. '
                       'To try a Windows install under Proton, turn on Skynizz on Proton (experimental) in Settings.')

def skynizz_proton(settings):
    return cross_os.THIS_OS=='linux' and settings.get('skynizz_proton') is True

def adopt_plan(e,g,row,record,operation,mode):
    """Review entry for adapting the other OS's install of this game to this OS."""
    other=OS_NAMES[record['os']];here=OS_NAMES[cross_os.THIS_OS]
    data=shared_baseline(g)
    current=data.get('current') or {}
    t.need(cross_os.THIS_OS=='windows' or current.get('provider_id')!='skynizz' or operation=='uninstall'
           or getattr(e,'SKYNIZZ_PROTON',False),LINUX_SKYNIZZ_REFUSAL)
    managed=[p for p in data.get('managed_paths') or [] if isinstance(p,str)]
    mine=(data.get('cross_os_extras') or {}).get(cross_os.THIS_OS) or {}
    # What this OS saved in Steam the last time it owned the install, if anything.
    view={'steam_launch':mine['steam_launch']} if isinstance(mine.get('steam_launch'),dict) else None
    prefix=None;steam_route=False
    if operation in ('install','repair'):
        if current.get('provider_id')=='skynizz' and getattr(e,'SKYNIZZ_PROTON',False):
            # Adopting the same Windows install is not a provider switch; Linux selects no Skynizz package.
            t.need(current.get('feature_mode',mode)==mode,'Uninstall before changing feature profiles so original runtime files are restored')
        else:
            check_switch(e,current or None,mode)
        if cross_os.THIS_OS=='linux':
            prefix=steam_open_route(e,g,operation,view)
            if not prefix:
                account=e.choose_steam_user_config([g],assume_yes=True)
                t.need(account is not None,'No Steam launch settings found; add the game to Steam before desktop installation')
                if not g.appid:
                    shortcuts=account['shortcuts']
                    match=e.match_shortcut_span(g,e.parse_shortcuts_spans(shortcuts.read_bytes())) if shortcuts.is_file() else None
                    t.need(match is not None,'No unique Steam shortcut targets this game directory. Add this copy as a separate Non-Steam game before desktop installation')
                steam_route=True
            detail='adds the Proton setting'+(" in this game's prefix · Steam can stay open" if prefix else '')
        else:
            detail='it already loads here, so no game files change'
        preview={'files':[],'launch_options':f'Installed with rtxForge on {other} · adapts it for {here}: {detail}'}
    elif operation=='uninstall':
        steam_open_route(e,g,operation,view)
        steam_route=bool(view)
        preview={'files':managed,'launch_options':f'Installed with rtxForge on {other} · restores the original files it backed up'}
    else:
        preview={'files':[],'launch_options':f'Installed with rtxForge on {other} · adapts it for {here}, then saves your presets'}
    return {'game':g,'row':row,'preview':preview,'fingerprint':fingerprint(e,g),'prefix':str(prefix) if prefix else None,
            'steam_route':steam_route,'adopt':record,'paths':managed}

def proton_setup(e,g,record):
    """Prefix and DLL names that make a Windows install load under Proton."""
    prefix=proton_prefix.find_prefix(g.root,g.appid)
    t.need(not proton_prefix.prefix_in_use(prefix),'This game is running. Quit it, then try again.')
    names=list(record.get('proton_overrides') or [])
    if not names and record.get('proxy'):names=[Path(record['proxy']).stem.lower()]
    t.need(names,'The Windows install does not name its proxy DLL; restore it on Windows and install again here')
    return prefix,names

def prepare(config,rows,mode,operation,settings):
    selected=settings.get('runtime_provider','y4my')
    prefer_bundled_nr_only=settings.get('prefer_bundled_nr_only',False)
    t.need(type(prefer_bundled_nr_only) is bool,'Invalid supported-feature package selection.')
    upgrade=settings.get('upgrade_skynizz_bridge',False)
    t.need(type(upgrade) is bool,'Invalid bridge update selection.')
    t.need(not upgrade or (selected=='skynizz' and mode=='nr-mfg' and operation=='repair'),
           'A bridge update requires an existing combined NR + MFG installation.')
    t.need(not upgrade or not settings.get('apply_requested_presets',False),
           'A bridge update preserves each game preset; apply new presets separately.')
    proton=skynizz_proton(settings)
    # With the experimental opt-in, each Linux row is checked instead: adoption passes, a fresh install still refuses.
    if selected=='skynizz' and operation in ('install','repair') and not proton:
        skynizz_provider.require_mode(cross_os.THIS_OS,mode,bool(settings.get('native_mfg_fallback')),bridge=mode in ('nr-mfg','mfg-only'))
    custom=settings.get('custom_package') if selected=='custom' else None
    t.need(selected!='custom' or isinstance(custom,dict),'Choose and review a custom package first.')
    e=module(config,custom['family'] if custom else selected,mode);data={};meta={};nr=None;nrmeta=None
    e.SKYNIZZ_PROTON=proton
    import overlay_policy
    e.OVERLAY_UI = dict(settings) if overlay_policy.explicit(settings) else None
    if custom:
        # Unique package identity keeps switching providers behind existing restore checks.
        package_catalog.validate_parameters(custom.get('parameters',{}))
        e.Y4MY_PROVIDER=dict(custom)
    releases={}; payload_cache={}; model_cache={}
    if operation in ('install','repair') and selected!='skynizz':
        data,meta=ui.work('Verifying '+e.Y4MY_PROVIDER['name'],payload,e,config,mode)
        if mode in ('nr-mfg','nr-only') and 'nvngx_dlssnr.dll' not in data:
            # Local-only for y4my; missing per-game model is a per-target refusal.
            nr,nrmeta=e.load_user_nr_runtime(settings.get('nr_runtime') or None,family=None)
    strength=settings.get('nr_strength',2.0);multiplier=settings.get('mfg_multiplier','auto');sharpening=settings.get('sharpening_strength',0.5)
    controls=settings.get('feature_controls')
    if controls is not None: controls=skynizz_provider.validate_controls(controls)
    # Validate granular values before any target mutation.
    e.visual_defaults(strength,multiplier,sharpening)
    desktop_mode(e)
    selected_provider=dict(e.Y4MY_PROVIDER)
    ready=[];blocked=[];seen=[]
    for index,row in enumerate(rows,1):
        ui.progress('Checking game files',phase='review-check',game=row['name'],checked=index-1,total=len(rows))
        try:
            e.Y4MY_PROVIDER=dict(selected_provider)
            g=game(e,row)
            t.need(not any(g.root.resolve().is_relative_to(p) or p.is_relative_to(g.root.resolve()) for p in seen),'Duplicate or overlapping game selection; refresh the library')
            seen.append(g.root.resolve())
            baseline=e.load_baseline(g.target_dir)
            # Fast rejection for fresh Windows installs. Preserve established
            # repair/cross-OS adoption paths and their original checks below.
            if (cross_os.THIS_OS=='windows' and operation in ('install','repair') and not baseline
                    and not (g.target_dir/'.rtxforge-install.json').exists()):
                t.need(not row.get('blocked'),row.get('blocked',''))
            target_data,target_meta=data,meta
            installed=installed_package(baseline)
            if installed and installed.get('provider_id')=='skynizz' and operation in ('reset','uninstall'):
                t.need(cross_os.THIS_OS=='windows' or operation=='uninstall' or proton,LINUX_SKYNIZZ_REFUSAL)
                e.Y4MY_PROVIDER=skynizz_provider.validate_release((installed.get('archive') or {}).get('release') or {})
            # Installed (or last changed) with rtxForge on the other OS: adapt it for this one.
            shared=cross_os.adoptable(g.target_dir,cross_os.THIS_OS,(baseline or {}).get('cross_os_revision')) if operation in ('install','repair','uninstall','reset') else None
            if selected=='skynizz' and operation in ('install','repair') and not (proton and shared):
                current=installed_package(baseline)
                check_switch(e,current,mode)
                # Repair never silently advances a game's release or mutable latest tag.
                saved_release=(current.get('archive') or {}).get('release') if current else None
                t.need(not current or isinstance(saved_release,dict),'Installed Skynizz release provenance is missing; restore before reinstalling.')
                release=skynizz_provider.validate_release(saved_release) if current else None
                if upgrade:
                    t.need(release is not None and release.get('variant')=='nr-mfg-bridge',
                           'Install the combined NR + MFG package before updating its bridge.')
                    previous=release
                    release=dict(skynizz_provider.bundled_bridge(previous['tag'])[0])
                    # Explicitly update only the bridge. Keep the component owner,
                    # preset and production runtime identities selected for this game.
                    for key in ('mfg_component','nr_preset',*skynizz_provider.PRODUCTION_RUNTIMES):
                        if key in previous:release[key]=previous[key]
                    release=skynizz_provider.validate_release(release)
                selection=settings.get('skynizz_version','latest')
                if release is None:
                    if selection not in releases:
                        native_panel = settings.get('overlay_helper', True) and settings.get('overlay_renderer') == 'game'
                        releases[selection]=(skynizz_provider.bundled_bridge(selection)[0] if mode in ('nr-mfg','mfg-only') or prefer_bundled_nr_only or native_panel else ui.work('Resolving Skynizz release',skynizz_provider.resolve,selection))
                    release=dict(releases[selection])
                    mfg_provider=settings.get('mfg_provider','universal')
                    t.need(mfg_provider in ('universal','integrated','mfg-unlock'),'Choose a supported MFG component.')
                    if mfg_provider=='mfg-unlock':
                        t.need(mode=='nr-mfg','MFG Unlock requires the combined native FG route.')
                        release['mfg_component']=ada_mfg_provider.pinned()
                    elif mfg_provider=='universal' and mode in ('nr-mfg','mfg-only'):
                        # OptiScaler loads the Universal plugin; the game's own DLSS-G stays the FG path.
                        import universal_mfg_provider
                        release['mfg_component']=universal_mfg_provider.pinned()
                    if settings.get('nr_preset') is not None:
                        t.need(type(settings['nr_preset']) is int and settings['nr_preset'] in (0,1,2),'Choose a supported NR preset.')
                        release['nr_preset']=settings['nr_preset']
                t.need(mode not in ('nr-mfg','mfg-only') or release.get('variant')=='nr-mfg-bridge','NR + MFG requires the combined bridge; restore the stock NR-only package first.')
                e.Y4MY_PROVIDER=release
                payload_key=json.dumps(release,sort_keys=True)
                if payload_key not in payload_cache:
                    payload_cache[payload_key]=ui.work('Verifying Skynizz package',payload,e,config,mode)
                target_data,target_meta=payload_cache[payload_key]
                if upgrade and mode != 'mfg-only':
                    expected=(current.get('nr_runtime') or {}).get('sha256')
                    model_key=str(g.target_dir/'nvngx_dlssnr.dll')
                    if model_key not in model_cache:model_cache[model_key]=e.load_user_nr_runtime(model_key,family=None)
                    nr,nrmeta=model_cache[model_key]
                    t.need(expected and nrmeta.get('sha256')==expected,
                           'The installed NR model changed; repair its recorded model before updating the bridge.')
                elif mode != 'mfg-only':
                    model_key=settings.get('nr_runtime') or None
                    if model_key not in model_cache:model_cache[model_key]=e.load_user_nr_runtime(model_key,family=None)
                    nr,nrmeta=model_cache[model_key]
            if baseline:
                t.need(not any(v.get('kind') in ('tar_tree','tar_file') for v in baseline.get('originals',{}).values()),'Privileged backup requires terminal restore before desktop management')
            if shared:
                t.need(cross_os.THIS_OS=='windows' or (shared.get('provider') or {}).get('id')!='skynizz' or proton,
                       LINUX_SKYNIZZ_REFUSAL)
                ready.append(adopt_plan(e,g,row,shared,operation,mode))
                ui.progress('Game checked',phase='review-check',game=row['name'],checked=index,total=len(rows))
                continue
            retired=restored_elsewhere(e,g,baseline)
            if retired and operation=='uninstall':
                other=OS_NAMES[cross_os.OTHER_OS]
                prefix=steam_open_route(e,g,operation,baseline)
                preview={'files':[],'launch_options':f'Original files were already restored with rtxForge on {other} · clears what is left here'}
                ready.append({'game':g,'row':row,'preview':preview,'fingerprint':fingerprint(e,g),'prefix':None,'steam_route':isinstance(baseline.get('steam_launch'),dict),'retire_only':True})
                ui.progress('Game checked',phase='review-check',game=row['name'],checked=index,total=len(rows))
                continue
            if retired:baseline=None
            windows=windows_install(e,g,baseline) if operation in ('install','repair','uninstall') else None
            if windows and cross_os.THIS_OS=='windows':
                # Installed with rtxForge on Linux: Windows loads it natively, so there is nothing to add.
                t.need(False,'Installed with rtxForge on Linux. It already loads on Windows; restore its original files in rtxForge on Linux, where they are backed up.' if operation=='uninstall' else 'Installed with rtxForge on Linux. It already loads on Windows; nothing to change here.')
            if windows:
                # Installed with rtxForge on Windows: adapt it for Linux instead of reinstalling.
                if operation=='uninstall':
                    t.need(proton_prefix.load_record(prefix_state(e,g)),"Installed with rtxForge on Windows. Restore its original files in rtxForge on Windows, where they are backed up.")
                    preview={'files':[],'launch_options':'Removes the Linux setting only · restore the original files in rtxForge on Windows'}
                    ready.append({'game':g,'row':row,'preview':preview,'fingerprint':fingerprint(e,g),'prefix':None,'steam_route':False,'linux_setup_remove':True})
                else:
                    prefix,names=proton_setup(e,g,windows)
                    preview={'files':[],'launch_options':'Installed with rtxForge on Windows · adds the Proton setting only ('+', '.join(names)+')'}
                    ready.append({'game':g,'row':row,'preview':preview,'fingerprint':fingerprint(e,g),'prefix':str(prefix),'steam_route':False,'linux_setup':names})
                ui.progress('Game checked',phase='review-check',game=row['name'],checked=index,total=len(rows))
                continue
            prefix=steam_open_route(e,g,operation,baseline)
            if operation=='reset':
                preview=e.reset_visual_settings(g,dry_run=True,nr_strength=strength,mfg_multiplier=multiplier,sharpening_strength=sharpening,feature_controls=controls)
            elif operation=='uninstall':
                t.need(baseline,'No terminal-engine baseline; use legacy Undo for an older app install')
                e.verify_baseline_integrity(g.target_dir,baseline,adopt_legacy=False)
                e.verify_native_restore(baseline)
                preview={'restore_boundary':'before-adoption' if baseline.get('adoption') else 'original','files':baseline['managed_paths'],'proxy':(baseline.get('current') or {}).get('proxy',''),'launch_options':'Restore only recorded proxy override; preserve NVIDIA capability flags'}
            else:
                t.need(not row.get('blocked'),row.get('blocked',''))
                account=None if prefix else e.choose_steam_user_config([g],assume_yes=True)
                t.need(prefix or account is not None,'No Steam launch settings found; add the game to Steam before desktop installation')
                if not g.appid and not prefix:
                    shortcuts=account['shortcuts']
                    match=e.match_shortcut_span(g,e.parse_shortcuts_spans(shortcuts.read_bytes())) if shortcuts.is_file() else None
                    t.need(match is not None,'No unique Steam shortcut targets this game directory. Add this copy as a separate Non-Steam game before desktop installation')

                check_switch(e,installed_package(baseline),mode)
                with _without_baseline(e,g) if retired else contextlib.nullcontext():
                    preview=e.install_target(g,target_data,target_meta,'ada',nr_runtime_payload=nr,nr_runtime_meta=nrmeta,feature_mode=mode,enable_effects=True,nr_on_launch=settings.get('nr_on_launch',False) if operation=='install' else None,native_mfg_fallback=bool(settings.get('native_mfg_fallback',False)),nr_strength=strength,mfg_multiplier=multiplier,sharpening_strength=sharpening,feature_controls=controls,preserve_visual_settings=not settings.get("apply_requested_presets",False),dry_run=True)
                if selected=='skynizz':
                    model=preview.get('nr_runtime') or {}
                    route='Combined NR + Ada MFG bridge · target runtime validation pending' if mode=='nr-mfg' else 'MFG Only · neural rendering disabled' if mode=='mfg-only' else 'NR Only · requires D3D12/DLSS'
                    if (component:=release.get('mfg_component')) and component.get('id')=='universal':
                        lead='NR + ' if mode=='nr-mfg' else 'MFG Only · '
                        route=f"{lead}Universal MFG {component['version']} · OptiScaler plugin · SHA-256 {component['dll']['sha256']} · game-native DLSS-G · internal unlock disabled · target runtime validation pending"
                    elif component:
                        route=f"NR + {component['name']} {component['version']} · SHA-256 {component['sha256']} · ReShade {component['host']['version']} · internal unlock disabled · target runtime validation pending"
                    preview=dict(preview,launch_options=f"{release['tag']} · SHA-256 {release['sha256']} · model {model.get('path','')} · SHA-256 {model.get('sha256','')} · "+route)
                    if preview.get('restored_support_tree'):
                        preview['launch_options'] += ' · Back up the exact OptiScaler support tree retained by the previous restore; restore returns it unchanged'
                    if upgrade:
                        preview['launch_options']='Update bridge · '+str(previous.get('bridge_id','recorded build'))+' → '+str(release.get('bridge_id','bundled build'))+' · preserve game tuning and NR model · '+preview['launch_options']
                    for component,(_,label) in skynizz_provider.PRODUCTION_RUNTIMES.items():
                        if runtime:=target_meta.get(component):
                            preview['launch_options']+=f" · production {label} {runtime['version']} · SHA-256 {runtime['sha256']}"
                    if skynizz_provider.startup_overlay_disabled(g):
                        preview['launch_options']+=' · OptiScaler swapchain overlay disabled for inZOI startup'
                if interrupted_install(baseline):
                    preview=dict(preview,launch_options='Finishes an install that was interrupted · '+preview['launch_options'])
            if prefix:preview=dict(preview,launch_options="Proton setting saved in this game's prefix · Steam can stay open")
            # Which Steam-side state this game touches: its prefix, Steam's launch settings, or neither.
            steam_route=operation in ('install','repair') and not prefix or operation=='uninstall' and bool(baseline and isinstance(baseline.get('steam_launch'),dict))
            ready.append({'game':g,'row':row,'preview':preview,'fingerprint':fingerprint(e,g),'prefix':str(prefix) if prefix else None,'steam_route':steam_route,'retire':retired,
                          'provider':dict(e.Y4MY_PROVIDER),'payload':target_data,'meta':target_meta,'nr':nr,'nrmeta':nrmeta})
        except (e.Stop,t.Refusal,OSError,ValueError) as ex:blocked.append({'name':row['name'],'reason':str(ex)})
        ui.progress('Game checked',phase='review-check',game=row['name'],checked=index,total=len(rows))
    return {'kind':'engine','operation':operation,'title':'Update NR + MFG bridge' if upgrade else operation.title(),'rows':[{'name':p['row']['name'],'detail':p['preview']['launch_options'] if operation=='reset' else f"{e.Y4MY_PROVIDER['name']} · {len(p['preview']['files'])} managed files · "+p['preview']['launch_options']} for p in ready],
            'blocked':blocked,'plans':ready,'engine':e,'payload':data,'meta':meta,'nr':nr,'nrmeta':nrmeta,'mode':mode,'enable_effects':True,'nr_on_launch':settings.get('nr_on_launch',False) if operation=='install' else None,'native_mfg_fallback':bool(settings.get('native_mfg_fallback',False)),'nr_strength':strength,'mfg_multiplier':multiplier,'sharpening_strength':sharpening,'feature_controls':controls,'apply_requested_presets':bool(settings.get('apply_requested_presets',False))}

def share_install(e,g,review):
    """Tell rtxForge on the other OS what this install is, and share its state so that OS can adapt it."""
    try:
        target=g.target_dir
        baseline=e.load_baseline(target) or {}
        current=baseline.get('current') or {}
        launch=e._launch_record_for_game(g) or {}
        revision=cross_os.new_revision()
        portable=baseline.get('status')=='active' and not baseline.get('pending_install') and \
            not any(v.get('kind') in ('tar_tree','tar_file') for v in baseline.get('originals',{}).values())
        if portable:
            extras=dict(baseline.get('cross_os_extras') or {})
            extras[cross_os.THIS_OS]={'steam_launch':baseline.get('steam_launch'),'launch_options':current.get('launch_options'),'proxy':current.get('proxy')}
            cross_os.export_state(target,e.state_dir_for(target),baseline,revision,extras)
            baseline['cross_os_extras']=extras;baseline['cross_os_revision']=revision
            e.save_json_atomic(e.baseline_path(target),baseline)
        marker=cross_os.write(target,cross_os.THIS_OS,baseline.get('managed_paths',[]),dict(getattr(e,'Y4MY_PROVIDER',{}) or {}),
            current.get('feature_mode') or review.get('mode',''),current.get('proxy',''),proton_prefix.override_names(launch.get('required','')),
            app_version=getattr(e,'APP_VERSION',''),revision=revision,shared_state=portable)
        if type(current.get('nr_on_launch')) is bool:
            marker['nr_on_launch']=current['nr_on_launch']
            e.save_json_atomic(target/cross_os.MARKER,marker)
    except Exception as error:
        # The change itself succeeded; the other OS will just not be able to adapt it.
        ui.line('Install record',f'Not written: {error}')

def release_install(g,baseline):
    """After a restore, drop the record and shared state this OS owns (or adopted)."""
    record=cross_os.read(g.target_dir)
    if record and (record['os']==cross_os.THIS_OS or record.get('revision')==(baseline or {}).get('cross_os_revision')):
        cross_os.remove(g.target_dir,record['os'])

def undo_game(e,session,checkpoint,result):
    """Put a failed game back exactly as it was before this run touched it."""
    changed=session.changed(checkpoint)
    if not changed:return True
    steam_files={str(p) for p in (e.STATE_ROOT/'steam-config-backups',e._steam_transaction_root())}
    if e.steam_running() and any(p.name in ('localconfig.vdf','shortcuts.vdf') or str(p) in steam_files for p in changed):
        result['error']+=' Close Steam, then undo it from Previous changes. Copies retained at '+str(session.root)
        return False
    try:session.undo(checkpoint)
    except Exception as ex:
        result['error']+=' Could not undo: '+str(ex)
        return False
    return True

def execute(review):
    e=review['engine'];results=[]
    # Never kill Steam behind a GUI action, or wait invisibly for terminal prompts.
    # With Steam open, installs use each game's Proton prefix (decided per game
    # in prepare); Steam-saved launch settings still need Steam closed.
    cancel=review.get('cancel_event')
    # Every game is checkpointed before it changes: Cancel undoes the whole run,
    # and a game that fails partway is put back as it was.
    session=Session(e.STATE_ROOT/'desktop-operations')
    with e.mutation_lock():
        for index,item in enumerate(review['plans'],1):
            if cancel is not None and cancel.is_set():break
            if item.get('provider'):e.Y4MY_PROVIDER=item['provider']
            g=item['game'];total=len(review['plans'])
            def report(stage,part):ui.progress(stage,game=g.name,current=index,total=total,fraction=(index-1+part)/total)
            report('Checking game files',0)
            try:
                t.need(fingerprint(e,g)==item['fingerprint'],'Game or baseline changed since preview; prepare again')
                if session:
                    baseline=e.load_baseline(g.target_dir) or {}
                    names=set(item['preview'].get('files',[]))|set(item['preview'].get('remove',[]))|set(baseline.get('managed_paths',[]))|set(baseline.get('originals',{}))|set(item.get('paths',[]))
                    if review['operation']=='reset':names={p.name for p in g.target_dir.iterdir() if p.name.lower()=='optiscaler.ini'}
                    else:names.add('OptiScaler')
                    paths=[g.target_dir/name for name in names]+[e.state_dir_for(g.target_dir),g.target_dir/cross_os.MARKER,g.target_dir/cross_os.SHARED]
                    paths.extend(item.get('extra_checkpoint_paths', []))
                    if review['operation']!='reset':
                        paths.extend([e.STATE_ROOT/'steam-config-backups',e._steam_transaction_root(),prefix_state(e,g)])
                        account=e.choose_steam_user_config([g],assume_yes=True)
                        if account:paths.extend(account[k] for k in ('localconfig','shortcuts') if account.get(k))
                        # The prefix registry is part of the undo too.
                        prefix_record=proton_prefix.load_record(prefix_state(e,g))
                        for registry in {item.get('prefix') and str(Path(item['prefix'])/'user.reg'),prefix_record and prefix_record.get('registry')}:
                            if registry:paths.append(Path(registry))
                    report('Backing up your current files',0.15)
                    checkpoint=session.capture(paths,label=g.name)
                if item.get('before_game'):
                    item['before_game']()
                if item.get('adopt'):
                    report('Adapting the install for '+OS_NAMES[cross_os.THIS_OS],0.3)
                    adopt(e,g,item['adopt'])
                elif item.get('retire'):
                    retire(e,g)
                report({'reset':'Saving your settings','uninstall':'Restoring original files','install':'Installing features','repair':'Repairing feature files'}[review['operation']],0.4)
                if item.get('retire_only'):
                    # Restored on the other OS: only this OS's own launch setting is left to undo.
                    proton_prefix.restore(prefix_state(e,g))
                    e.restore_launch_options_batch([g],assume_yes=True)
                    retire(e,g)
                    record={'retired':True}
                elif item.get('adopt') and review['operation'] in ('install','repair'):
                    report('Saving launch settings',0.85)
                    if item.get('prefix'):
                        names=proton_prefix.override_names((e._launch_record_for_game(g) or {}).get('required',''))
                        t.need(names,'No Proton setting was planned for this game; close Steam and install again')
                        proton_prefix.apply(Path(item['prefix']),names,prefix_state(e,g))
                    elif cross_os.THIS_OS=='linux':
                        synced=e.sync_launch_options_batch([g],assume_yes=True,prompt=False)
                        t.need(synced and all(r.get('status')=='written' for r in synced),'The launch settings could not be saved, so launch settings need attention: '+str(synced))
                    share_install(e,g,review)
                    record={'adopted':item['adopt']['os']}
                elif item.get('linux_setup'):
                    report('Saving the Proton setting',0.6)
                    proton_prefix.apply(Path(item['prefix']),item['linux_setup'],prefix_state(e,g))
                    record={'linux_setup':item['linux_setup']}
                elif item.get('linux_setup_remove'):
                    report('Removing the Proton setting',0.6)
                    record=proton_prefix.restore(prefix_state(e,g))
                elif review['operation']=='reset':
                    record=e.reset_visual_settings(g,nr_strength=review['nr_strength'],mfg_multiplier=review['mfg_multiplier'],sharpening_strength=review['sharpening_strength'],feature_controls=review.get('feature_controls'))
                    # OptiScaler.ini changed: share it again so the other OS still trusts the install.
                    share_install(e,g,review)
                elif review['operation']=='uninstall':
                    owned=e.load_baseline(g.target_dir)
                    e.verify_native_restore(owned)
                    proton_prefix.restore(prefix_state(e,g))
                    e.restore_launch_options_batch([g],assume_yes=True)
                    record=e.restore_target(g)
                    release_install(g,owned)
                else:
                    record=e.install_target(g,item.get('payload',review['payload']),item.get('meta',review['meta']),'ada',nr_runtime_payload=item.get('nr',review['nr']),nr_runtime_meta=item.get('nrmeta',review['nrmeta']),feature_mode=review['mode'],enable_effects=review['enable_effects'],nr_on_launch=review.get('nr_on_launch'),native_mfg_fallback=review.get('native_mfg_fallback',False),nr_strength=review['nr_strength'],mfg_multiplier=review['mfg_multiplier'],sharpening_strength=review['sharpening_strength'],feature_controls=review.get('feature_controls'),preserve_visual_settings=not review.get('apply_requested_presets',False))
                    report('Saving launch settings',0.85)
                    if item.get('prefix'):
                        launch=e._launch_record_for_game(g)
                        names=proton_prefix.override_names((launch or {}).get('required') or record.get('launch_options',''))
                        t.need(names,'No Proton setting was planned for this game; close Steam and install again')
                        proton_prefix.apply(Path(item['prefix']),names,prefix_state(e,g))
                    else:
                        synced=e.sync_launch_options_batch([g],assume_yes=True,prompt=False)
                        t.need(synced and all(r.get('status')=='written' for r in synced),'The launch settings could not be saved, so launch settings need attention: '+str(synced or record['launch_options']))
                    share_install(e,g,review)
                if item.get('after_game'):
                    item['after_game']()
                results.append({'name':g.name,'status':'complete','record':record})
            except Exception as ex:
                results.append({'name':g.name,'status':'failed','error':str(ex)})
                if 'checkpoint' in locals():
                    session.seal(checkpoint)
                    results[-1]['undone']=undo_game(e,session,checkpoint,results[-1])
                    del checkpoint
            finally:
                if 'checkpoint' in locals():session.seal(checkpoint);del checkpoint
                report('Finished this game',1)
        if review.get('on_finalizing'):
            review['on_finalizing']()
        if session:
            if cancel is not None and cancel.is_set():
                t.need(not any(e._running_processes_under_root(p['game'].root.resolve()) for p in review['plans']),'Close running games before recovery. Copies retained at '+str(session.root))
                # Only Steam's own launch settings need Steam closed to undo safely.
                if any(p.get('steam_route',review['operation']!='reset') for p in review['plans']):t.need(not e.steam_running(),'Close Steam before recovery. Copies retained at '+str(session.root))
                session.rollback()
                raise Cancelled('Changes undone.')
            session.complete()
    path=e.STATE_ROOT/('desktop-'+e.now_stamp()+'.json');e.save_json_atomic(path,{'results':results})
    failed=[r for r in results if r['status']=='failed']
    if failed:
        kept='' if all(r.get('undone') for r in failed) else ' Some changes could not be undone; see the report.'
        raise t.Refusal(f'{len(failed)} game(s) need attention. Their files were put back as they were; completed games keep their changes.{kept} Report: {path}')
    return str(path)
