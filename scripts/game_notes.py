"""User-recorded test results. Never deploys, launches, or modifies game files."""
from pathlib import Path
import hashlib,json,zipfile,datetime,stat
import transactions as t
import engine_bridge,library_media
from storage import storage
STATES=('Untested','Working','Problem','Bench')
def root(config):return storage(config)/'desktop/reports'
def path(config,game):return root(config)/'games'/(hashlib.sha256(str(game).encode()).hexdigest()[:24]+'.json')
def load(config,game):
    try:return json.loads(path(config,game).read_text())
    except (OSError,ValueError):return {'status':'Untested','notes':'','sessions':[]}
def save(config,game,record):
    t.need(record.get('status') in STATES,'Unknown test status')
    t.atomic_file(path(config,game),json.dumps(record,indent=2).encode(),0o600)
def start(config,game):
    record=load(config,game['game']);t.need(not record.get('active'),'Finish the current test first')
    record['active']={'started':t.now(),'selected_package':engine_bridge.providers()[library_media.load_settings(config).get('runtime_provider','y4my')],'profile':game.get('profile'),'name':game['name']}
    # Config pin is package provenance, NOT proof this DLL is installed.
    directory=Path(game['game'])/Path(game['exe']).parent
    record['active']['installed_proxies']={p.name:t.digest(p) for p in directory.iterdir() if p.name.lower() in {'dxgi.dll','winmm.dll','version.dll'} and p.is_file() and not p.is_symlink()}
    save(config,game['game'],record);return record

def finish(config,game):
    record=load(config,game['game']);session=record.get('active');t.need(session,'Start a test record first')
    session['finished']=t.now();session['logs']=[]
    destination=root(config)/'logs'/hashlib.sha256(game['game'].encode()).hexdigest()[:24]/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory=Path(game['game'])/Path(game['exe']).parent
    # Exact adjacent diagnostic names only; no recursive home/prefix/save collection.
    for name in ('OptiScaler.log','sl.log','sl.dlss_g.log','sl.interposer.log'):
        p=directory/name
        try:
            import os
            fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as source:
                st=os.fstat(source.fileno())
                if not stat.S_ISREG(st.st_mode):continue
                source.seek(max(0,st.st_size-4*1024**2));data=source.read(4*1024**2)
            out=destination/name;t.atomic_file(out,data,0o600);session['logs'].append(str(out))
        except OSError:continue
    session['observation']='User test record; captured logs may include earlier runs. No automatic runtime success inference.'
    record.setdefault('sessions',[]).append(session);record.pop('active',None);save(config,game['game'],record);return record

def redact(text):
    """Best-effort redaction; the exact export is still previewed before consent."""
    import re
    text=re.sub(r'(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+',r'\1[REDACTED]',text)
    text=re.sub(r'(?i)((?:access[_-]?token|api[_-]?key|password|secret)\s*[\"\']?\s*[:=]\s*[\"\']?)[^\s,;\"\']+',r'\1[REDACTED]',text)
    text=re.sub(r'(?i)https?://[^\s\"<>]+',lambda m:m[0].split('?')[0].split('#')[0],text)
    text=re.sub(r'(?<![\w:])/(?:home|var/home|run|mnt|var/mnt|media|tmp)/[^\n\r\"<>]*','[LOCAL PATH]',text)
    text=re.sub(r'(?i)\b[A-Z]:[\\/][^\n\r\"<>]*','[WINDOWS PATH]',text)
    text=re.sub(r'\b7656119\d{10}\b','[STEAM ID]',text)
    text=re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b','[EMAIL]',text)
    return text


def preview(config,games,include_logs=False,include_notes=False):
    import runtime_diagnostics
    records=[];files={}
    for index,game in enumerate(games):
        record=load(config,game['game'])
        item={'name':game['name'],'status':record.get('status','Untested'),
              'diagnostics':runtime_diagnostics.inspect(game)}
        if include_notes:item['notes']=redact(str(record.get('notes','')))
        records.append(item)
        if include_logs:
            # One latest captured session per game, bounded regular files only.
            for value in (record.get('sessions') or [{}])[-1].get('logs',[]):
                p=Path(value)
                if p.is_symlink() or not p.resolve().is_relative_to((root(config)/'logs').resolve()):continue
                try:data,_=runtime_diagnostics.read_regular(p,512*1024,tail=True)
                except (OSError,ValueError):continue
                files[f'logs/{index}/{p.name}']=redact(data.decode('utf-8',errors='replace'))
    files['library.json']=redact(json.dumps(records,indent=2))
    files['README.txt']='rtxForge support export. Paths and common secrets are redacted on a best-effort basis. Runtime diagnostics do not establish visual correctness. Nothing was uploaded.\n'
    return files


def export_preview(config,files):
    """Write exactly the preview the user approved, without re-reading game files."""
    out=root(config)/('rtxForge-report-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.zip')
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():
            t.relative(name);z.writestr(name,data)
    out.chmod(0o600);return out


def export(config,games):
    return export_preview(config,preview(config,games))
