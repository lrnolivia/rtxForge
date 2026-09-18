#!/usr/bin/env python3
"""RTXForge — a batch installer for two explicit RTX routes, built for Linux."""
from __future__ import annotations
import argparse,pathlib,json,sys,os,uuid,datetime,shutil,subprocess,traceback
import ui,profiles,packages,planning,discovery,cleanup
import transactions as t
from storage import storage
P=pathlib.Path
ROOT=P(__file__).resolve().parent.parent

def load_provider(path=None):
    c=t.read_json(path or ROOT/'provider.json')
    t.need(c.get('schema')==1 and c.get('config_schema')=='rtxforge-v4-streamline-native-v1','Unsupported package/configuration schema')
    t.need(c['url'].startswith('https://github.com/'+c['repo']+'/releases/download/'),'Provider URL mismatch')
    return c

def normalize_targets(rows):
    t.need(isinstance(rows,list) and 0<len(rows)<=10000,'Select 1–10,000 explicit targets')
    result=[];seen=[]
    for row in rows:
        game=t.safe(row['game']);t.relative(row['exe']);t.need(row['mode'] in profiles.MODES,'Only NR + MFG or MFG Only are supported')
        t.need(all(not game.is_relative_to(p) and not p.is_relative_to(game) for p in seen),'Duplicate/overlapping targets refused');seen.append(game)
        result.append({**row,'game':str(game)})
    return result

def choose_mode():
    ui.title('Choose your stack');ui.line('1 · NR + MFG','Neural Rendering + native Streamline DLSS-G / Ada MFG');ui.line('2 · MFG Only','Native Streamline DLSS-G / Ada MFG · no NR DLLs')
    choice=ui.prompt('Route [1/2]:');t.need(choice in ('1','2'),'No route selected');return 'nr-mfg' if choice=='1' else 'mfg-only'

def select_targets(args,mode):
    if args.targets:return normalize_targets(t.read_json(args.targets))
    t.need(not args.apply,'Noninteractive apply needs --targets JSON')
    lib=discovery.choose_library(P(args.library) if args.library else None,False)
    games=ui.work('Scanning games',lambda: discovery.discover_games(lib,discovery.discover_nonsteam_roots(lib,[P(p) for p in args.nonsteam])))
    eligible=[]
    for g in games:
        native=any(P(p).name.lower() in ('nvngx_dlssg.dll','sl.dlss_g.dll') and 'optiscaler' not in [x.lower() for x in P(p).relative_to(g.root).parts] for p in g.upscalers)
        if not g.anti_cheat and native:eligible.append(g)
    ui.title('Choose games · codes separated by spaces, or ALL');ui.table([(g.code,g.name,profiles.MODES[mode]) for g in eligible])
    ui.line('Not listed',str(len(games)-len(eligible))+' titles lack native MFG evidence or have anti-cheat')
    raw=ui.prompt('Include codes (ENTER cancels):');codes=ui.selection(raw,[g.code for g in eligible]);chosen=[g for g in eligible if g.code in codes]
    targets=[{'game':g.root,'exe':P(g.exe).relative_to(g.root).as_posix(),'mode':mode,'name':g.name} for g in chosen]
    t.need(targets,'No games selected');return normalize_targets(targets)

def preview(plans,details=False):
    ui.title('Review batch · no games changed yet')
    for i,p in enumerate(plans,1):
        add=sum(r['before'] is None for r in p['changes']);remove=sum(r['after'] is None for r in p['changes']);replace=len(p['changes'])-add-remove
        ui.line(str(i)+' · '+profiles.MODES[p['mode']],p['game']);ui.line('Executable',p['exe']);ui.line('Changes',f'{add} add · {replace} replace · {remove} back up/remove')
        ui.line('MFG route',p.get('mfg_route_label','Native Streamline DLSS-G')+(' · compatibility profile' if p.get('mfg_profiled') else ''))
        if p.get('proxy'):ui.line('Proton override',P(p['proxy']).stem+'=n,b — merge manually; launch options untouched')
        if p['mode']=='nr-mfg':ui.line('NR at startup','Enabled · WorkingScale 0.70 · v3 profile')
        else:ui.line('NR components','Absent; panel hidden with RTXForge loader (stock loader keeps inactive panel)')
        for message in p['conflicts']:ui.error(message)
        if details:
            for r in p['changes']:ui.line(r['path'],str(r['before'])+' → '+str(r['after']))
    ui.line('Batch total',str(len(plans))+' games · '+str(sum(len(p['changes']) for p in plans))+' file changes')

def apply_batch(c,plans):
    root=storage(c,sum(sum(P(r['source']).stat().st_size if 'source' in r else len(r.get('text','').encode()) for r in p['changes']) for p in plans)+2*1024**3)
    # Every target preflights before the first mutation; each target is rechecked by the engine.
    for p in plans:
        ui.work('Checking before install · '+P(p['game']).name,t.check_plan,p)
        need_bytes=sum(P(r['source']).stat().st_size if 'source' in r else len(r.get('text','').encode()) for r in p['changes'])
        t.need(shutil.disk_usage(p['game']).free>need_bytes+64*1024**2,'Insufficient target space: '+p['game'])
        backup=sum((P(p['game'])/r['path']).stat().st_size for r in p['changes'] if r['before'] is not None)
        t.need(backup<=t.MAX_BACKUP,'Backup exceeds 1 GiB per-game limit: '+p['game'])
    root.mkdir(parents=True,exist_ok=True)
    # A single installer batch at a time, including batches covering different games.
    with t.transaction_lock(root/'batch-lock-context'):
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8];batch=root/'batches'/stamp;batch.mkdir(parents=True)
        record={'schema':1,'created':t.now(),'status':'applying','transactions':[],'plans':plans}
        t.save_new(batch/'batch.json',record)
        for index,p in enumerate(plans,1):
            if not p['changes']:continue
            folder=root/'transactions'/t.sha(p['game'].encode())[:20];folder.mkdir(parents=True,exist_ok=True);state=folder/(stamp+'-'+str(index))
            record['transactions'].append(str(state));t.record_write(batch/'batch.json',record)
            try:
                ui.work(f'Installing {index}/{len(plans)} · '+P(p['game']).name,t.apply_transaction,p,state)
            except BaseException:
                record['status']='interrupted';t.record_write(batch/'batch.json',record);ui.error('Batch stopped. Earlier completed targets are recorded; recover with '+str(batch/'batch.json'));raise
        record['status']='complete';record['completed']=t.now();t.record_write(batch/'batch.json',record)
    return batch/'batch.json'

def rollback(args,c):
    root=storage(c);path=args.batch
    if not path:
        choices=sorted((root/'batches').glob('*/batch.json'),reverse=True);t.need(choices,'No RTXForge batches recorded')
        ui.title('Recorded batches')
        for i,p in enumerate(choices,1):ui.line(str(i),p.parent.name+' · '+t.read_json(p)['status'])
        n=int(ui.prompt('Batch number:'));t.need(1<=n<=len(choices),'Invalid batch number');path=choices[n-1]
    path=t.safe(path);t.need(path.is_relative_to(root/'batches'),'Batch record outside state directory');record=t.read_json(path);states=[]
    t.need(record['status']!='rolled-back','Batch already rolled back')
    for s in reversed(record['transactions']):
        state=t.safe(s);t.need(state.is_relative_to(root/'transactions'),'Unsafe transaction reference')
        if not (state/'transaction.json').exists():continue
        status=t.read_json(state/'transaction.json')['status']
        if status in ('preparing','rolled-back'):continue
        view=ui.work('Checking recovery · '+state.name,t.rollback_transaction,state);states.append(state);ui.line(view['game'],str(len(view['files']))+' files to restore')
    if args.dry_run or not confirm(args,'ROLLBACK'):return
    with t.transaction_lock(root/'batch-lock-context'):
        for state in states:ui.work('Restoring · '+state.name,t.rollback_transaction,state,True)
        record['status']='rolled-back';record['rollback_time']=t.now();t.record_write(path,record)
    ui.line('Restored','All selected batch transactions rolled back')

def confirm(args,token):
    if args.apply:t.need(args.confirm==token,'Noninteractive confirmation must be --confirm '+token);return True
    action={'APPLY':'Apply this batch','ADOPT':'Adopt and apply this batch','ROLLBACK':'Restore this batch','CLEANUP':'Back up and remove these cleanup candidates','RESTORE':'Restore these cleanup files'}[token]
    return ui.prompt(action+'? [y/N]').lower() in ('y','yes')

def parser():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',nargs='?',choices=['install','repair','uninstall','rollback','prepare','scan','preview-ui','cleanup','restore-cleanup'],default=None)
    p.add_argument('--targets',type=P,help='JSON array: game, exe, mode; optional manifest/record/proxy/api');p.add_argument('--provider',type=P);p.add_argument('--mode',choices=list(profiles.MODES));p.add_argument('--library');p.add_argument('--nonsteam',action='append',default=[]);p.add_argument('--adopt-existing',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--apply',action='store_true');p.add_argument('--confirm');p.add_argument('--details',action='store_true');p.add_argument('--batch',type=P);p.add_argument('--roots',type=P,action='append',default=[]);p.add_argument('--cleanup-record',type=P);return p

def run(args):
    c=load_provider(args.provider);root=storage(c)
    if args.command=='cleanup':
        roots=args.roots or discovery.candidate_libraries()
        t.need(roots,'No game libraries found; pass --roots explicitly.')
        ui.title('Advanced · global DLSS5 cleanup')
        ui.line('Scan roots',', '.join(str(p) for p in roots))
        items=ui.work('Scanning cleanup candidates',cleanup.discover,roots,c)
        for row in items:ui.line(row['kind'],row['path'])
        ui.line('Recovery policy','Every candidate is copied and verified before removal; rtxForge state/recovery data is excluded.')
        ui.line('Candidates',str(len(items)))
        if items and not args.dry_run and confirm(args,'CLEANUP'):ui.line('Recovery record',ui.work('Backing up and cleaning selected files',cleanup.apply,c,items))
        return
    if args.command=='restore-cleanup':
        path=args.cleanup_record or P(ui.prompt('Cleanup recovery record path:'))
        ui.line('Files to restore',str(ui.work('Checking cleanup recovery',cleanup.restore,c,path)))
        if not args.dry_run and confirm(args,'RESTORE'):ui.work('Restoring cleanup files',cleanup.restore,c,path,True);ui.line('Recovered','Cleanup restored')
        return
    if args.command=='preview-ui':
        ui.table([('A','Example Game','NR + MFG'),('B','Another Game','MFG Only')]);return
    if args.command=='rollback':return rollback(args,c)
    mode=args.mode or (None if args.targets else choose_mode())
    if args.command=='prepare':t.need(not args.dry_run,'Prepare is an explicit cache-writing action');ui.work('Preparing and verifying payload',packages.prepare,c,mode or 'nr-mfg');ui.line('Ready','Pinned payload verified');return
    targets=select_targets(args,mode)
    if args.command=='scan':ui.table([(str(i+1),r['game'],profiles.MODES[r['mode']]) for i,r in enumerate(targets)]);return
    plans=[];sources={}
    for target in targets:
        if args.command!='uninstall' and target['mode'] not in sources:
            sources[target['mode']]=ui.work('Preparing / verifying '+profiles.MODES[target['mode']]+' payload',packages.prepare,c,target['mode'],readonly=args.dry_run)
    for index,target in enumerate(targets,1):
        try:
            label=f'Checking {index}/{len(targets)} · '+target.get('name',P(target['game']).name)
            plan=ui.work(label,planning.remove,target,root) if args.command=='uninstall' else ui.work(label,planning.make,target,root,sources[target['mode']],args.command,args.adopt_existing)
            plans.append(plan)
        except (t.Refusal,OSError,ValueError) as ex:
            ui.error(target['game']+': '+str(ex));raise t.Refusal('Batch preflight failed; no games changed')
    preview(plans,args.details)
    blocked=[p for p in plans if p['conflicts']]
    if blocked:
        ready=[p for p in plans if not p['conflicts']]
        t.need(ready and not args.apply and not args.dry_run,'Resolve conflicts or adjust the selected batch; no games changed')
        ui.line('Blocked games',str(len(blocked))+' will remain unchanged')
        ui.line('Ready games',str(len(ready)))
        for p in blocked:ui.line('Excluded',p['game'])
        plans=ready
        ui.line('Apply summary',str(len(ready))+' ready games · '+str(len(blocked))+' excluded; only ready games will change')
    if args.dry_run:return
    token='ADOPT' if args.adopt_existing and any(p.get('adopted') for p in plans) else 'APPLY'
    if confirm(args,token):ui.line('Batch record',apply_batch(c,plans))

def main(argv=None):
    args=parser().parse_args(argv);ui.banner()
    try:
        if args.command:return run(args) or 0
        while True:
            ui.title('Make it yours')
            for k,v in [('1','Install / update a batch'),('2','Repair a batch'),('3','Remove owned files'),('4','Roll back a batch'),('5','Prepare pinned payload'),('6','Advanced: global DLSS5 cleanup'),('7','Restore a global cleanup'),('0','Exit')]:ui.line(k,v)
            choice=ui.prompt('Choose:')
            if choice=='0':return 0
            if choice not in ('1','2','3','4','5','6','7'):continue
            args.command={'1':'install','2':'repair','3':'uninstall','4':'rollback','5':'prepare','6':'cleanup','7':'restore-cleanup'}[choice]
            try:run(args)
            except (t.Refusal,RuntimeError,OSError,ValueError,KeyError,subprocess.SubprocessError) as ex:ui.error(ex)
            except Exception as ex:
                ui.error('Unexpected error: '+str(ex));traceback.print_exc()
            args.command=None;ui.prompt('Press ENTER to return to the menu.')
    except (t.Refusal,RuntimeError,OSError,ValueError,KeyError,subprocess.SubprocessError) as ex:ui.error(ex);return 2
    except (KeyboardInterrupt,EOFError):print('\nCancelled.');return 130
if __name__=='__main__':sys.exit(main())
