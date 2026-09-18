"""Explicit global DLSS5 cleanup with a fully verified recovery copy, never an uninstall side effect."""
import pathlib,os,stat,shutil,uuid,datetime,json
import transactions as t
from storage import storage
P=pathlib.Path
NAMES={'nvngx_dlssnr.dll','nvngx.dll_dlssnr.dll'}
def snapshot(path):
    path=t.safe(path)
    if path.is_file():return {'kind':'file','files':{'':t.digest(path)},'modes':{'':stat.S_IMODE(path.stat().st_mode)},'dirs':{}}
    files=t.files(path);dirs={'':stat.S_IMODE(path.stat().st_mode)}
    for base,names,_ in os.walk(path):
        for name in names:
            p=t.safe(P(base)/name);dirs[p.relative_to(path).as_posix()]=stat.S_IMODE(p.stat().st_mode)
    return {'kind':'directory','files':{r:t.digest(path/r) for r in files.values()},'modes':{r:stat.S_IMODE((path/r).stat().st_mode) for r in files.values()},'dirs':dirs}

def discover(roots,c):
    state=storage(c);candidates=[];seen=[]
    for raw in roots:
        root=t.safe(raw);t.need(root.is_dir() and root!=P('/'),'Choose an actual library/mount root, not /')
        if any(root.is_relative_to(p) for p in seen):continue
        seen.append(root)
        for base,dirs,names in os.walk(root,followlinks=False):
            folder=P(base)
            dirs[:]=[n for n in dirs if not (folder/n).is_symlink() and not (folder/n).is_relative_to(state)]
            if folder.is_relative_to(state):dirs[:]=[];continue
            for name in list(dirs):
                if name.lower()=='_dlss5_backup':candidates.append(folder/name);dirs.remove(name)
            for name in names:
                if name.lower() in NAMES:
                    p=folder/name;t.need(not p.is_symlink(),'Cleanup target is a symlink; review explicitly: '+str(p));candidates.append(p)
    paths=[]
    for p in sorted(set(candidates),key=lambda p:len(p.parts)):
        if not any(p.is_relative_to(q) for q in paths):paths.append(p)
    return [{'path':str(p),**snapshot(p)} for p in paths]

def apply(c,items):
    root=storage(c);total=sum((P(row['path'])/r if r else P(row['path'])).stat().st_size for row in items for r in row['files']);storage(c,total*2)
    root.mkdir(parents=True,exist_ok=True)
    with t.transaction_lock(root/'cleanup-context'):
        dest=root/'cleanup'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]);dest.mkdir(parents=True)
        record={'schema':1,'status':'backing-up','created':t.now(),'items':items};t.save_new(dest/'cleanup.json',record)
        # Complete and verify EVERY backup before removing the first original.
        for i,row in enumerate(items):
            path=P(row['path']);t.need(snapshot(path)=={k:row[k] for k in ('kind','files','modes','dirs')},'Cleanup target drift: '+str(path))
            for rel,h in row['files'].items():
                src=path/rel if rel else path;backup=dest/'copies'/str(i)/(rel or 'file');backup.parent.mkdir(parents=True,exist_ok=True)
                with src.open('rb') as f,backup.open('xb') as out:shutil.copyfileobj(f,out);out.flush();os.fsync(out.fileno())
                t.need(t.digest(backup)==h,'Cleanup backup failed verification')
        record['status']='removing';t.record_write(dest/'cleanup.json',record)
        try:
            for row in items:
                path=P(row['path']);t.need(snapshot(path)=={k:row[k] for k in ('kind','files','modes','dirs')},'Cleanup target changed during backup')
                for rel,h in row['files'].items():
                    p=t.safe(path/rel if rel else path);t.need(t.digest(p)==h,'Concurrent cleanup drift');p.unlink()
                if row['kind']=='directory':
                    for rel in sorted(row['dirs'],key=lambda r:len(P(r).parts),reverse=True):
                        p=path/rel if rel else path;p.rmdir()
            record['status']='complete';t.record_write(dest/'cleanup.json',record)
        except BaseException:
            record['status']='interrupted';t.record_write(dest/'cleanup.json',record);print('Cleanup interrupted; recovery record:',dest/'cleanup.json');raise
    return dest/'cleanup.json'

def restore(c,record_path,write=False):
    root=storage(c);record_path=t.safe(record_path);t.need(record_path.is_relative_to(root/'cleanup'),'Recovery record outside configured cleanup storage')
    record=t.read_json(record_path);t.need(record['status'] in ('complete','removing','interrupted'),'Cleanup does not need restoration')
    todo=[]
    for i,row in enumerate(record['items']):
        path=t.safe(row['path'])
        for rel,h in row['files'].items():
            if rel:t.relative(rel)
            dest=t.safe(path/rel if rel else path);backup=t.safe(record_path.parent/'copies'/str(i)/(rel or 'file'))
            t.need(t.digest(backup)==h,'Damaged cleanup backup')
            t.need(not dest.exists() or dest.is_file() and t.digest(dest)==h,'New content occupies cleanup destination; preserve/reconcile it first: '+str(dest))
            if not dest.exists():todo.append((dest,backup,row['modes'][rel]))
        for rel in row['dirs']:
            if rel:t.relative(rel)
            p=t.safe(path/rel if rel else path);t.need(not p.exists() or p.is_dir(),'Directory restore conflict')
    if not write:return len(todo)
    storage(c,sum(p.stat().st_size for _,p,_ in todo))
    with t.transaction_lock(root/'cleanup-context'):
        for dest,backup,mode in todo:
            t.need(not t.safe(dest).exists(),'Concurrent restore conflict');t.atomic_file(dest,backup.read_bytes(),mode)
        for row in record['items']:
            for rel,mode in sorted(row['dirs'].items(),key=lambda x:len(P(x[0]).parts)):
                p=t.safe(P(row['path'])/rel if rel else row['path']);p.mkdir(parents=True,exist_ok=True);os.chmod(p,mode)
        record['status']='restored';record['restored']=t.now();t.record_write(record_path,record)
    return len(todo)
