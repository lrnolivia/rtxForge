"""Beta reports: one game and setup per report, in the website's and the GitHub form's fields.

Never deploys, launches, uploads or posts. Host facts come from what this machine
can verify; anything else stays Not sure for the user to correct. Logs are opt-in,
read only from fixed names beside the game's executable, redacted, and exported
exactly as previewed. Shared by the Linux and Windows apps; no toolkit imports.
"""
import datetime,hashlib,json,os,platform,re,secrets,sys,urllib.parse,zipfile
from pathlib import Path
import transactions as t
import game_notes

REPOSITORY='lrnolivia/rtxForge'
ISSUES=f'https://github.com/{REPOSITORY}/issues'
TEMPLATE='beta-report.yml'
UNKNOWN='Not sure'
RESULTS=('Working in-game','Not working in-game','Installed, not tested','Could not install','Not installed','Not sure')
# Ids, labels, choices and lengths exactly as website/public/report.html and
# .github/ISSUE_TEMPLATE/beta-report.yml name them: one report reads the same everywhere.
FIELDS=(
    ('platform','Operating system'),
    ('distribution','Distro / OS version'),
    ('gpu-series','RTX series'),
    ('gpu','GPU model and driver'),
    ('app-format','rtxForge app format'),
    ('app-build','rtxForge version / channel'),
    ('game','Game and version'),
    ('feature-package','Game package'),
    ('features','Features attempted'),
    ('nr-result','NR result'),
    ('mfg-result','MFG result'),
    ('observations','What happened?'),
)
LABELS=dict(FIELDS)
# As on the website: everything else is "fill in what you know".
REQUIRED=('platform','observations')
CHOICES={
    'platform':('Linux','Windows'),
    'gpu-series':('RTX 20','RTX 30','RTX 40','RTX 50','Not sure'),
    'app-format':('Flatpak','AppImage','Windows installer','Windows portable ZIP','Source / Other','Not sure'),
    'features':('NR only','MFG only','NR + MFG','Not reached / Not sure'),
    'nr-result':RESULTS,
    'mfg-result':RESULTS,
}
LENGTHS={'distribution':100,'gpu':150,'app-build':150,'game':150,'feature-package':200,'observations':1500}
# Where each value came from, shown beside it so a correction is easy to spot.
SOURCES={'detected':'Detected on this computer','recorded':'From rtxForge’s install record',
         'selected':'Selected in Packages, not installed','yours':'Yours','unknown':'Please check'}
SERIES={'turing':'RTX 20','ampere':'RTX 30','ada':'RTX 40','blackwell':'RTX 50'}
MODES={'nr-mfg':'NR + MFG','nr-only':'NR only','mfg-only':'MFG only','NR + MFG':'NR + MFG','NR Only':'NR only','MFG Only':'MFG only'}
# Exact diagnostic names beside the executable; the MFG plugin's own run logs share a prefix.
LOGS=('OptiScaler.log','sl.log','sl.dlss_g.log','sl.interposer.log')
# Extra names for the routes that write them, in their known folders only (as the Windows host scans).
PROVIDER_LOGS={
    'feeder':('ReShade.log','dlss5-feed.log','dlss5-feed-host.log','host64/dlss5-feed-host.log','host64/ReShade.log'),
    'vulkan-native':('fgvk.log','NativeMods/fgvk.log'),
}
RUN_LOG_PREFIX='rtxmfg-'
RUN_LOGS=4
LOG_LIMIT=4*1024**2      # newest bytes kept from each log
TOTAL_LIMIT=64*1024**2   # every previewed file together, before compression
ZIP_LIMIT=20*1024**2     # under GitHub's 25 MB attachment limit
URL_LIMIT=7000           # a prefilled issue link longer than this is cut; the full text is copied instead
LINK_SCHEME='rtxforge'


def new_id():
    return 'r'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+secrets.token_hex(3)


# ---------- what this computer can verify ----------

def os_release(path):
    data={}
    try:
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            key,_,value=line.partition('=')
            if value:data[key.strip()]=value.strip().strip('"\'')
    except (OSError,UnicodeDecodeError):pass
    return data


def distribution(system=None,root=Path('/'),sandboxed=None):
    """The host OS and version. Inside a Flatpak /etc/os-release names the runtime, not the host."""
    system=system or platform.system()
    if system=='Windows':
        build=sys.getwindowsversion().build if hasattr(sys,'getwindowsversion') else 0
        name='Windows 11' if build>=22000 else 'Windows 10' if build else 'Windows'
        return (f'{name} (build {build})' if build else name),'detected'
    if sandboxed is None:
        import flatpak_host
        sandboxed=flatpak_host.sandboxed()
    paths=(root/'run/host/os-release',) if sandboxed else (root/'etc/os-release',root/'usr/lib/os-release')
    for path in paths:
        release=os_release(path)
        name=release.get('PRETTY_NAME') or ' '.join(filter(None,(release.get('NAME'),release.get('VERSION_ID'))))
        if name:return name[:LENGTHS['distribution']],'detected'
    return UNKNOWN,'unknown'


def gpu(info):
    """(series, model and driver) from the app's hardware check."""
    import hardware
    name=str((info or {}).get('gpu') or '').strip()
    if not name or name=='Not detected':return ((UNKNOWN,'unknown'),(UNKNOWN,'unknown'))
    driver=str(info.get('driver') or '').strip()
    model=name+(f' · driver {driver}' if driver and driver!='Unknown' else '')
    series=SERIES.get(hardware.family(name))
    return ((series,'detected') if series else (UNKNOWN,'detected')),(model[:LENGTHS['gpu']],'detected')


def app_format(system=None,environ=None,sandboxed=None,windows_format=None):
    """Flatpak or AppImage from the running build. Windows passes only verified package metadata."""
    system=system or platform.system();environ=os.environ if environ is None else environ
    if system=='Windows':
        return (windows_format,'detected') if windows_format in CHOICES['app-format'] else (UNKNOWN,'unknown')
    if sandboxed is None:
        import flatpak_host
        sandboxed=flatpak_host.sandboxed()
    if sandboxed:return 'Flatpak','detected'
    if environ.get('APPIMAGE'):return 'AppImage','detected'
    return 'Source / Other','detected'


def app_build(version,channel=''):
    version=str(version or '').strip()
    if not version or version=='Unknown':return UNKNOWN,'unknown'
    channel=str(channel or '').strip()
    return (version+(f' · {channel.title()}' if channel else ''))[:LENGTHS['app-build']],'detected'


def context(info,version,channel='',selected='',windows_format=None,system=None):
    """Facts shared by every report from this computer, gathered once per scan."""
    system=system or platform.system()
    series,model=gpu(info)
    return {'platform':('Windows' if system=='Windows' else 'Linux','detected'),
            'distribution':distribution(system),'gpu-series':series,'gpu':model,
            'app-format':app_format(system,windows_format=windows_format),
            'app-build':app_build(version,channel),'selected':str(selected or '')}


# ---------- one game ----------

def game_dir(row):
    relative=Path(str(row.get('exe') or ''))
    t.need(not relative.is_absolute() and '..' not in relative.parts,'Unsafe executable path')
    return Path(row['game'])/relative.parent


def installed(row):
    """The shared install record beside the game's files, with whether those files still match it."""
    import cross_os
    try:target=game_dir(row)
    except t.Refusal:return None
    record=cross_os.read(target)
    if not record:return None
    provider=record.get('provider') or {}
    return {'os':record['os'],'package':' '.join(filter(None,(provider.get('name') or provider.get('id'),provider.get('version')))),
            'feature_mode':record.get('feature_mode',''),'installed_at':record.get('installed_at',''),
            'app_version':record.get('app_version',''),'intact':cross_os.intact(target,record)}


def draft(row,facts,record=None):
    """A report for one game, filled from verified facts. Results the user saw stay theirs to choose."""
    record=record if record is not None else row.get('test_record') or {}
    fields={};sources={}
    def put(key,value):fields[key],sources[key]=value
    for key in ('platform','distribution','gpu-series','gpu','app-format','app-build'):put(key,facts[key])
    put('game',(str(row.get('name') or '')[:LENGTHS['game']],'detected'))
    install=installed(row)
    if install:
        note='' if install['intact'] else '; files changed since'
        put('feature-package',(f"{install['package'] or 'Unrecorded package'} (installed on {install['os'].title()}{note})"[:LENGTHS['feature-package']],'recorded'))
        mode=MODES.get(install['feature_mode'])
    elif row.get('installed'):
        put('feature-package',(UNKNOWN,'unknown'));mode=MODES.get(row.get('profile'))
    elif facts.get('selected'):
        put('feature-package',(f"{facts['selected']} (selected, not installed)"[:LENGTHS['feature-package']],'selected'));mode=None
    else:
        put('feature-package',('Not reached','unknown'));mode=None
    put('features',(mode,'recorded') if mode else ('Not reached / Not sure','unknown'))
    # Installed files say what is there, never what it looked like in game.
    untested=record.get('status','Untested')=='Untested'
    for key,feature in (('nr-result','NR'),('mfg-result','MFG')):
        if mode and untested:put(key,('Installed, not tested' if feature in mode else 'Not installed','recorded'))
        elif mode and feature not in mode:put(key,('Not installed','recorded'))
        else:put(key,(UNKNOWN,'unknown'))
    put('observations',('','unknown'))
    evidence={'test_status':record.get('status','Untested'),'install_record':install,
              'graphics_apis':list(row.get('graphics_apis') or []),
              'tried_anyway':(record.get('try_anyway') or {}).get('reason','')}
    appid=str(row.get('appid') or '')
    return {'schema':1,'id':new_id(),'created':t.now(),'name':str(row.get('name') or ''),
            'appid':appid if appid.isdigit() else '','exe':Path(str(row.get('exe') or '')).name,
            'fields':fields,'sources':sources,'evidence':evidence}


def correct(report,key,value):
    """A user's correction always wins and is marked as theirs."""
    t.need(key in LABELS,'Unknown report field')
    report['fields'][key]=str(value or '').strip();report['sources'][key]='yours'
    return report


def problems(report):
    """What still needs an answer before the report can be shared; empty when ready."""
    out=[]
    for key,name in FIELDS:
        value=str(report['fields'].get(key) or '').strip()
        if not value:
            if key in REQUIRED:out.append(f'{name} is empty.')
        elif key in CHOICES and value not in CHOICES[key]:out.append(f'{name}: choose one of the listed answers.')
        elif len(value)>LENGTHS.get(key,10**6):out.append(f'{name} is longer than {LENGTHS[key]} characters.')
    return out


# ---------- sharing ----------

def details(report):
    """Facts rtxForge read itself, kept apart from what the user observed."""
    evidence=report.get('evidence') or {};lines=[]
    if evidence.get('graphics_apis'):lines.append('Graphics API: '+', '.join(evidence['graphics_apis']))
    if evidence.get('tried_anyway'):lines.append('Tried anyway: '+evidence['tried_anyway'])
    install=evidence.get('install_record')
    if install:lines.append(f"Install record: {install['os'].title()}, {install['installed_at'][:10]}"+('' if install['intact'] else ', files changed since'))
    if report.get('appid'):lines.append('Steam app ID: '+report['appid'])
    elif report.get('exe'):lines.append('Executable: '+report['exe'])
    lines.append('Report ID: '+report['id'])
    return lines


def text(report):
    """The issue body as GitHub renders the form, so every report parses the same way."""
    fields=report['fields']
    blocks=[f'### {name}\n\n{str(fields.get(key) or "").strip() or "_No response_"}' for key,name in FIELDS]
    blocks.append('### Detected by rtxForge\n\n'+'\n'.join('- '+line for line in details(report)))
    return game_notes.redact('\n\n'.join(blocks)+'\n')


def title(report):
    return f"[Beta report] {report['fields'].get('game') or report['name']} · {report['fields'].get('platform') or UNKNOWN}"


def issue_url(report):
    """The prefilled GitHub form, and whether every field fit. Nothing is sent from here."""
    fields={key:game_notes.redact(str(value)) for key,value in report['fields'].items()}
    fields['observations']=(fields.get('observations','').rstrip()+'\n\n'+'\n'.join(details(report))).strip()
    def build(observations):
        query={'template':TEMPLATE,'title':game_notes.redact(title(report))}
        query.update({key:fields.get(key,'') for key,_ in FIELDS})
        query['observations']=observations
        return ISSUES+'/new?'+urllib.parse.urlencode(query)
    url=build(fields['observations'])
    if len(url)<=URL_LIMIT:return {'url':url,'complete':True}
    cut=fields['observations']
    while cut and len(build(cut+' […]'))>URL_LIMIT:cut=cut[:-200]
    return {'url':build(cut+' […]'),'complete':False}


def existing_issue(value):
    """A rtxForge issue to add logs to: '#123', '123' or its GitHub link. Anything else is refused."""
    value=str(value or '').strip()
    match=re.fullmatch(r'#?(\d{1,7})',value)
    if not match:
        parts=urllib.parse.urlsplit(value)
        path=re.fullmatch(rf'/{re.escape(REPOSITORY)}/issues/(\d{{1,7}})/?',parts.path,re.I)
        t.need(parts.scheme=='https' and parts.netloc.lower() in ('github.com','www.github.com') and path,
               f'Paste a link to an issue in github.com/{REPOSITORY}.')
        match=path
    number=int(match[1]);t.need(number>0,'That issue number is not valid.')
    return {'number':number,'url':f'{ISSUES}/{number}'}


def comment(reports,archive,issue=None):
    """What to paste with the attached ZIP when adding logs to a report that already exists."""
    names=', '.join(f"{r['fields'].get('game') or r['name']} ({r['id']})" for r in reports)
    lines=[f'Logs for {names}, reviewed and redacted in rtxForge.',f'Attached: `{Path(archive).name}`']
    if issue:lines.append(f"Follows up on #{issue['number']}.")
    return '\n'.join(lines)+'\n'


def parse_link(value):
    """rtxforge://support/logs, optionally ?issue=N. Links come from web pages, so nothing else is accepted."""
    value=str(value or '')
    if len(value)>200:return None
    parts=urllib.parse.urlsplit(value)
    if parts.scheme!=LINK_SCHEME or parts.netloc!='support' or parts.path.rstrip('/')!='/logs' or parts.fragment:return None
    try:query=urllib.parse.parse_qs(parts.query,keep_blank_values=True,strict_parsing=bool(parts.query),max_num_fields=1)
    except ValueError:return None
    if set(query)-{'issue'}:return None
    issue=None
    if 'issue' in query:
        if len(query['issue'])!=1 or not re.fullmatch(r'\d{1,7}',query['issue'][0]) or not int(query['issue'][0]):return None
        issue=int(query['issue'][0])
    return {'action':'logs','issue':issue}


# ---------- logs ----------

def _when(value):
    try:return datetime.datetime.fromisoformat(str(value))
    except ValueError:return None


def _session(modified,record):
    sessions=[s for s in (record or {}).get('sessions') or [] if _when(s.get('started'))]
    if not sessions:return 'No test recorded; may include earlier runs'
    last=sessions[-1];modified=_when(modified);finished=_when(last.get('finished'))
    if modified<_when(last['started']):return 'Older than your last test'
    if finished and modified>finished:return 'Written after your last test'
    return 'From your last test'


def collect(row,record=None,limit=LOG_LIMIT):
    """The newest bytes of each known log beside the executable, with where and when they came from.

    Read once, here: the preview and the ZIP hold these bytes, never a later copy."""
    record=record if record is not None else row.get('test_record') or {}
    try:directory=game_dir(row)
    except t.Refusal as error:return [{'name':name,'skipped':str(error)} for name in LOGS]
    names=list(LOGS)
    # Route logs are listed only where present: a game on another route never writes them.
    optional={name for name in PROVIDER_LOGS.get(row.get('runtime_provider'),()) if (directory/name).exists()}
    names+=sorted(optional)
    try:
        runs=[p for p in directory.iterdir() if p.name.startswith(RUN_LOG_PREFIX) and p.name.endswith('.log') and p.is_file() and not p.is_symlink()]
        names+=[p.name for p in sorted(runs,key=lambda p:p.stat().st_mtime,reverse=True)[:RUN_LOGS]]
    except OSError:pass
    return [_read(directory/name,name,limit,record) for name in names]


def collect_app(paths,limit=LOG_LIMIT):
    """rtxForge's own logs at fixed known paths (Windows: engine.log, crash.log), read the same way."""
    return [_read(Path(path),Path(path).name,limit,{}) for path in paths]


def _read(path,name,limit,record):
    import runtime_diagnostics
    item={'name':name}
    try:data,info=runtime_diagnostics.read_regular(path,limit,tail=True)
    except FileNotFoundError:item['skipped']='Not found';return item
    except (OSError,ValueError) as error:item['skipped']='Not read: '+(str(error) or type(error).__name__);return item
    modified=datetime.datetime.fromtimestamp(info.st_mtime,datetime.timezone.utc).isoformat()
    item.update(data=data,size=info.st_size,modified=modified,truncated=info.st_size>len(data),session=_session(modified,record))
    return item


# ---------- preview and export ----------

def _slug(name):
    return re.sub(r'[^A-Za-z0-9]+','-',str(name)).strip('-')[:48] or 'game'


def _digest(files):
    return hashlib.sha256(json.dumps(files,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def bundle(reports,logs=None,notes=None,app_logs=None):
    """The exact redacted files a ZIP will hold, with a manifest of what was left out and why.

    logs and notes are keyed by report id and only present when the user opted in;
    app_logs (collect_app) go in an app/ folder shared by every report."""
    t.need(reports,'Choose at least one game.')
    files={};manifest={'schema':1,'created':t.now(),'reports':[],'files':[],'skipped':[],
                       'note':'Redaction is best effort. Logs show runtime activity; they do not establish what NR or MFG looked like in game.'}
    for report in reports:
        folder=f"{_slug(report['fields'].get('game') or report['name'])}-{report['id'][-6:]}"
        manifest['reports'].append({'id':report['id'],'game':report['fields'].get('game') or report['name'],'folder':folder})
        files[f'{folder}/report.md']=text(report)
        public={key:report[key] for key in ('schema','id','created','name','appid','exe','fields','sources','evidence')}
        files[f'{folder}/report.json']=game_notes.redact(json.dumps(public,indent=2,ensure_ascii=False))
        note=str((notes or {}).get(report['id']) or '').strip()
        if note:files[f'{folder}/notes.txt']=game_notes.redact(note)+'\n'
        for item in (logs or {}).get(report['id'],[]):
            if 'skipped' in item:
                manifest['skipped'].append({'report':report['id'],'name':item['name'],'reason':item['skipped']});continue
            path=f"{folder}/logs/{item['name']}"
            files[path]=game_notes.redact(item['data'].decode('utf-8',errors='replace'))
            manifest['files'].append({'path':path,'size':item['size'],'modified':item['modified'],
                                      'truncated':item['truncated'],'session':item['session']})
    for item in app_logs or []:
        if 'skipped' in item:
            manifest['skipped'].append({'report':'app','name':item['name'],'reason':item['skipped']});continue
        path=f"app/{item['name']}"
        files[path]=game_notes.redact(item['data'].decode('utf-8',errors='replace'))
        manifest['files'].append({'path':path,'size':item['size'],'modified':item['modified'],
                                  'truncated':item['truncated'],'session':'rtxForge app log'})
    files['manifest.json']=json.dumps(manifest,indent=2,ensure_ascii=False)
    files['README.txt']=('rtxForge beta report. Each folder holds one game: report.md is the GitHub issue text, '
                         'report.json the same fields with where each came from, and logs/ the newest part of each log.\n'
                         'Paths, email addresses, Steam IDs and common secrets were redacted on a best-effort basis. '
                         'Check the contents before attaching. Nothing was uploaded.\n')
    size=sum(len(value.encode()) for value in files.values())
    t.need(size<=TOTAL_LIMIT,f'These logs come to {size/1024**2:.0f} MB. Choose fewer games or leave logs out.')
    return {'id':new_id(),'files':files,'digest':_digest(files),'manifest':manifest,'size':size}


def folder(config,documents=None):
    """Reports go somewhere easy to find: Documents/rtxForge Reports, else rtxForge's own state."""
    if documents and Path(documents).is_dir() and os.access(documents,os.W_OK):
        return t.safe(Path(documents)/'rtxForge Reports')
    return game_notes.root(config)/'exports'


def export(preview,destination):
    """Write exactly the previewed bytes. Nothing is read from the game again."""
    t.need(_digest(preview['files'])==preview['digest'],'The preview changed after review. Prepare the report again.')
    destination=t.safe(destination);destination.mkdir(parents=True,exist_ok=True)
    path=t.safe(destination/f"rtxForge-report-{preview['id']}.zip")
    t.need(not path.exists(),'A report with this name already exists.')
    temporary=t.safe(destination/f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        with zipfile.ZipFile(temporary,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for name,data in preview['files'].items():
                t.relative(name);archive.writestr(name,data)
        size=temporary.stat().st_size
        t.need(size<=ZIP_LIMIT,f'This report is {size/1024**2:.1f} MB compressed, over the {ZIP_LIMIT//1024**2} MB limit for GitHub attachments. Choose fewer games or leave logs out.')
        os.replace(temporary,path)
    except (OSError,zipfile.BadZipFile,zipfile.LargeZipFile) as error:
        raise t.Refusal('The report could not be saved: '+str(error)) from error
    finally:
        temporary.unlink(missing_ok=True)
    try:path.chmod(0o600)
    except OSError:pass
    manifest=preview['manifest']
    return {'path':str(path),'name':path.name,'size':path.stat().st_size,
            'included':[item['path'] for item in manifest['files']],'skipped':manifest['skipped']}
