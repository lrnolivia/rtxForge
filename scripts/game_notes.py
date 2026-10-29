"""User-recorded test results. Never deploys, launches, or modifies game files."""
from pathlib import Path
import hashlib,json,zipfile,datetime,uuid
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
def start(config,game,checks=None,probe=None):
    """Open a test session. checks: what the host verified before launch (helper running, package files)."""
    import functional_test
    record=load(config,game['game']);t.need(not record.get('active'),'Finish the current test first')
    checks=checks if checks is not None else functional_test.preflight(game,library_media.load_settings(config))
    record['active']={'started':t.now(),'selected_package':engine_bridge.providers()[library_media.load_settings(config).get('runtime_provider','y4my')],'profile':game.get('profile'),'name':game['name'],
                      'id':uuid.uuid4().hex,'row':{k:game.get(k) for k in ('game','exe','name','appid','profile','runtime_provider')},'checks':checks,
                      'log_baseline':functional_test.log_baseline(game)}
    # Config pin is package provenance, NOT proof this DLL is installed.
    directory=functional_test.directory(game)
    record['active']['installed_proxies']={p.name:t.digest(p) for p in directory.iterdir() if p.name.lower() in {'dxgi.dll','winmm.dll','version.dll'} and p.is_file() and not p.is_symlink()}
    save(config,game['game'],record)
    if probe:functional_test.resume(config,game,record['active'],probe)
    return record

# Exact adjacent diagnostic names only, for every route: Skynizz/OptiScaler and Streamline,
# then Feeder (ReShade, dlss5-feed) and Vulkan (fgvk). No recursive home/prefix/save collection.
TEST_LOGS=('OptiScaler.log','sl.log','sl.dlss_g.log','sl.interposer.log','ReShade.log','dlss5-feed.log','dlss5-feed-host.log','fgvk.log')

def finish(config,game,samples=None,helper=None):
    """Close the session: copy this run's logs, then one result per part (functional_test.evaluate)."""
    import functional_test,runtime_diagnostics
    record=load(config,game['game']);session=record.get('active');t.need(session,'Start a test record first')
    # Bind Finish to the executable selected at Start, even if discovery changed.
    started_row=session.get('row') or game
    t.need(started_row.get('exe')==game.get('exe'),'The game executable changed. Select the executable used at Start Test to finish it.')
    if samples is None:samples=functional_test.stop(config,game,session)
    session['finished']=t.now();session['logs']=[]
    destination=root(config)/'logs'/hashlib.sha256(game['game'].encode()).hexdigest()[:24]/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    captured,logs=functional_test.session_logs(started_row,session.get('log_baseline') or {})
    # Legacy records cannot establish where this session's log bytes began.
    if 'log_baseline' not in session:logs={}
    for name,data in captured.items():
        out=destination/name;t.atomic_file(out,data,0o600);session['logs'].append(str(out))
    checks=session.get('checks') or {}
    final_checks=functional_test.preflight(started_row,library_media.load_settings(config))
    for part in ('files','settings'):
        if final_checks.get(part+'_ok') is False:
            checks[part+'_ok']=False;checks[part+'_detail']='At Finish: '+final_checks.get(part+'_detail','')
    package_changed=bool(checks.get('install_revision') and final_checks.get('install_revision')!=checks['install_revision'])
    summary=functional_test.summarize(samples)
    helper=dict(helper or {},start=checks.get('helper'),finish=(helper or {}).get('running'))
    results=functional_test.evaluate(summary,logs,helper,checks.get('pipelines'),checks)
    if package_changed:
        for result in results:
            if result['part'] in ('nr','mfg'):
                result.update(state='not-tested',summary='The installed package changed during this test.',
                              fix='Repeat the test with one installed package and feature mode.')
    session['functional']={'schema':1,'route':checks.get('route'),'summary':summary,'results':results,
                           'suggestion':functional_test.suggestion(results),'text':functional_test.result_text({'results':results})}
    session['observation']='Functional test: live in-game evidence and this session’s logs. It shows what ran, never how the picture looked.'
    record.setdefault('sessions',[]).append(session);record.pop('active',None);save(config,game['game'],record);return record

def latest_test(record):
    """The newest finished functional test in a record, or None."""
    sessions=(record or {}).get('sessions') or []
    return sessions[-1].get('functional') if sessions else None

def redact(text):
    """Best-effort redaction; the exact export is still previewed before consent."""
    import re
    text=re.sub(r'(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+',r'\1[REDACTED]',text)
    text=re.sub(r'(?i)((?:(?:access|refresh|auth|session)[_-]?)?token|api[_-]?key|password|passwd|secret)(\s*[\"\']?\s*[:=]\s*[\"\']?)[^\s,;\"\'&]+',r'\1\2[REDACTED]',text)
    text=re.sub(r'(?i)https?://[^\s\"<>]+',lambda m:m[0].split('?')[0].split('#')[0],text)
    text=re.sub(r'(?<![\w:])/(?:home|var/home|run|mnt|var/mnt|media|tmp)/[^\n\r\"<>]*','[LOCAL PATH]',text)
    text=re.sub(r'(?i)\b[A-Z]:[\\/][^\n\r\"<>]*','[WINDOWS PATH]',text)
    text=re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b','[REDACTED]',text)
    text=re.sub(r'\b7656119\d{10}\b','[STEAM ID]',text)
    text=re.sub(r'\[U:1:\d+\]','[STEAM ID]',text)
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
