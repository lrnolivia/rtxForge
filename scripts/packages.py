"""Pinned v3 runtime sourcing. Archives are never executed and payloads remain on Games."""
import pathlib,json,hashlib,urllib.request,urllib.parse,subprocess,shutil,zipfile,os
import transactions as t
import ui
import pipeline
from storage import storage
P=pathlib.Path
def download(url,path,expected=None,blob=None,size=None):
    if path.exists():
        datahash=t.digest(path)
        if expected:t.need(datahash==expected,'Cached download drift: '+str(path))
        if blob:
            h=hashlib.sha1(b'blob '+str(path.stat().st_size).encode()+b'\0');h.update(path.read_bytes());t.need(h.hexdigest()==blob,'Cached Git blob mismatch')
        return path
    part=path.with_suffix(path.suffix+'.part');t.need(not part.exists(),'Incomplete download retained: '+str(part))
    path.parent.mkdir(parents=True,exist_ok=True)
    ui.line('Downloading',path.name)
    with urllib.request.urlopen(url,timeout=120) as src,part.open('xb') as out:shutil.copyfileobj(src,out)
    if expected:t.need(t.digest(part)==expected,'Downloaded SHA256 mismatch')
    if size:t.need(part.stat().st_size==size,'Downloaded size mismatch')
    if blob:
        h=hashlib.sha1(b'blob '+str(part.stat().st_size).encode()+b'\0');h.update(part.read_bytes());t.need(h.hexdigest()==blob,'Downloaded Git blob mismatch')
    part.rename(path);return path

def entries(archive):
    if archive.suffix.lower()=='.zip':
        with zipfile.ZipFile(archive) as z:raw=[(i.filename,i.file_size, i.is_dir(),i.external_attr>>16) for i in z.infolist()]
    else:
        seven=shutil.which('7zz') or shutil.which('7z');t.need(seven,'7z/7zz required; no system packages are installed automatically')
        listing=subprocess.check_output([seven,'l','-slt',str(archive)],text=True);raw=[]
        for block in listing.split('----------\n',1)[1].strip().split('\n\n'):
            row=dict(s.split(' = ',1) for s in block.splitlines() if ' = ' in s)
            t.need(not any('Link' in k for k in row),'Archive links refused')
            raw.append((row['Path'],int(row.get('Size','0')),row.get('Folder')=='+' or row.get('Attributes','').startswith('D'),0))
    import stat
    seen=set();result=[]
    for n,size,isdir,mode in raw:
        t.relative(n.rstrip('/'));t.need(n.casefold() not in seen and not stat.S_ISLNK(mode),'Unsafe archive entry');seen.add(n.casefold());t.need(size<1024**3,'Oversized archive member')
        if not isdir:result.append(n)
    return result

def extract(archive,member,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as out:
        if archive.suffix.lower()=='.zip':
            with zipfile.ZipFile(archive) as z,z.open(member) as src:shutil.copyfileobj(src,out)
        else:subprocess.run([shutil.which('7zz') or shutil.which('7z'),'x','-so','-mmt=1',str(archive),member],stdout=out,check=True)

def verify(folder,record):
    t.need(set(t.files(folder))=={n.casefold() for n in record['files']},'Payload listing drift')
    for n,h in record['files'].items():t.need(t.digest(folder/n)==h,'Payload hash drift: '+n)

def _discard_prepared_payload(pkg,record):
    """Remove only reconstructible extraction state; never touch the verified source archive."""
    if pkg.is_symlink():pkg.unlink()
    elif pkg.exists():
        t.safe(pkg)
        shutil.rmtree(pkg)
    if record.is_symlink():record.unlink()
    elif record.exists():
        t.safe(record)
        record.unlink()

def _extract_base_payload(c,cache,pkg,record):
    cache.mkdir(parents=True,exist_ok=True)
    archive=download(c['url'],cache/c['asset'],expected=c['sha256'])
    t.need(not pkg.exists(),'Prepared payload path still exists after cache reset: '+str(pkg))
    pkg.mkdir()
    for n in entries(archive):
        if n in ('OptiScaler.dll','OptiScaler.ini','nvngx.dll_dlssnr.dll') or n.startswith(('OptiScaler/','Licenses/')):extract(archive,n,pkg/n)
    t.need((pkg/'OptiScaler.dll').exists() and (pkg/'OptiScaler/streamline/sl.interposer.dll').exists(),'Unexpected v3 payload layout')
    manifest={'archive_sha256':c['sha256'],'files':{n:t.digest(pkg/n) for n in t.files(pkg).values()}}
    t.save_new(record,manifest)
    verify(pkg,manifest)
    return manifest

def _load_base_payload(c,cache,pkg,record,readonly=False):
    """Reuse a verified extraction, or rebuild stale/partial derived cache from the pinned archive."""
    manifest=None
    if record.is_symlink():
        if readonly:
            raise t.Refusal('Prepared payload manifest is a link; run Prepare/Install once to rebuild it')
        ui.line('Repairing cache','Unsafe prepared-payload manifest link detected; rebuilding from pinned source')
        _discard_prepared_payload(pkg,record)
    elif record.exists():
        try:
            manifest=t.read_json(record)
            t.need(isinstance(manifest,dict) and isinstance(manifest.get('files'),dict),'Payload manifest malformed')
            t.need(manifest.get('archive_sha256')==c['sha256'],'Payload manifest source drift')
            verify(pkg,manifest)
        except (t.Refusal,OSError,json.JSONDecodeError,KeyError,TypeError,ValueError) as exc:
            if readonly:
                raise t.Refusal('Prepared payload cache is invalid; run Prepare/Install once to rebuild it: '+str(exc)) from exc
            ui.line('Repairing cache','Prepared payload drift detected; rebuilding from pinned source')
            _discard_prepared_payload(pkg,record)
            manifest=None
    elif pkg.exists() or pkg.is_symlink():
        if readonly:
            raise t.Refusal('Prepared payload cache is incomplete; run Prepare/Install once to rebuild it')
        ui.line('Repairing cache','Incomplete prepared payload detected; rebuilding from pinned source')
        _discard_prepared_payload(pkg,record)
    if manifest is None:
        manifest=_extract_base_payload(c,cache,pkg,record)
    return manifest

def prepare(c,mode,readonly=False):
    root=storage(c,3*1024**3);cache=root/'packages'/c['sha256'];pkg=cache/'payload';record=cache/'files.json'
    if readonly:
        required=[record,*[root/'headless'/P(r['destination']).name for r in c['headless']]]
        if mode=='nr-mfg':required += [root/'nr'/c['nr']['sha256']/name for name in c['nr']['components']]
        t.need(all(p.is_file() for p in required),'Payload not prepared; run Prepare first. Dry-run never downloads or writes cache.')
    manifest=_load_base_payload(c,cache,pkg,record,readonly)
    sources={n:(pkg/n,h) for n,h in manifest['files'].items()}
    for row in c['headless']:
        dest=root/'headless'/P(row['destination']).name
        url='https://raw.githubusercontent.com/ShyVortex/dlss-unlocked/v0.3.0/'+urllib.parse.quote(row['path'])
        download(url,dest,blob=row['git_blob'],size=row['size']);sources[row['destination']]=(dest,t.digest(dest))
    if mode=='nr-mfg':
        n=c['nr'];folder=root/'nr';layer=folder/n['sha256']
        archive=None
        for name,expected in n['components'].items():
            t.relative(name);dest=layer/name
            valid=dest.is_file() and not dest.is_symlink() and t.digest(dest)==expected
            if not valid:
                t.need(not readonly,'NR component missing or changed; prepare the NR layer first: '+name)
                if archive is None:
                    url='https://github.com/'+n['repo']+'/releases/download/'+n['tag']+'/'+n['asset']
                    archive=download(url,folder/n['asset'],expected=n['sha256'])
                    t.need(set(n['components']).issubset(entries(archive)),'Incomplete NR source archive')
                if dest.exists() or dest.is_symlink():dest.unlink()
                extract(archive,name,dest);t.need(t.digest(dest)==expected,'NR component hash mismatch: '+name)
            sources[name]=(dest,expected)
    else:
        sources.pop('nvngx.dll_dlssnr.dll',None)
    return pipeline.compose(sources,mode,c)
