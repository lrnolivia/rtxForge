"""Per-game compatibility: the shipped list, your own results, and Try anyway.

Never deploys, launches, sends, or modifies game files. Try anyway only lifts
capability checks (a game without the DLSS route a package expects); missing
executables, anti-cheat and installs that need attention stay blocked. A shared
result is a prefilled beta-report issue the user reviews and posts in their browser;
reviewed reports join the shipped list through `add-report` (docs/COMPATIBILITY.md).
"""
import json,os,re
from pathlib import Path
import transactions as t
import game_notes

ROOT=Path(__file__).resolve().parents[1]
ISSUES='https://github.com/lrnolivia/rtxForge/issues/new'
VERDICTS=('Working','Problem')
BLOCK_KEYS=('blocked','package_blocked','skynizz_blocked')
# Capability checks, not safety checks: the install review and restore still apply.
SOFT=(
    'No native DLSS-G detected',
    'Skynizz needs a native DLSS Super Resolution route',
    'The combined NR + MFG bridge requires game-native DLSS Frame Generation',
)


# Graphics APIs each soft check's package hooks. Try anyway is offered only when the
# game renders with one of them: an unsupported renderer would never engage.
RENDERERS={'d3d9':'d3d9.dll','d3d11':'d3d11.dll','d3d12':'d3d12.dll','vulkan':'vulkan-1.dll','opengl':'opengl32.dll'}
LABELS={'d3d9':'DirectX 9','d3d11':'DirectX 11','d3d12':'DirectX 12','vulkan':'Vulkan','opengl':'OpenGL'}
# Every NR package behind these checks hooks DirectX 12 only (upstream, 2026-10-23).
# Universal MFG and MFG Unlock have experimental Vulkan paths, but only beside one of
# them. Feeder NR's upstream also covers Vulkan; the pinned recipe loads as dxgi.dll,
# so DirectX 11 and 12 only (feeder_provider.eligible).
PACKAGE_APIS={
    'No native DLSS-G detected':('d3d12',),
    'Skynizz needs a native DLSS Super Resolution route':('d3d12',),
    'The combined NR + MFG bridge requires game-native DLSS Frame Generation':('d3d12',),
}


def soft(reason):
    reason=str(reason or '')
    return bool(reason) and any(reason.startswith(prefix) for prefix in SOFT)


def renderers(exe,e=None,limit=2*1024**3):
    """The graphics APIs an executable loads; empty when unknown.

    Import and delay-import tables first. Packed executables hide their imports
    until launch, so fall back to the DLL names the file mentions."""
    import feeder_provider
    exe=Path(exe)
    def probe():
        names={name.lower() for name in (*(e.pe_imported_dlls(exe) if e else ()),*feeder_provider.delay_imported_dlls(exe))}
        found={api for api,dll in RENDERERS.items() if dll in names}
        if found:return found
        import mmap
        try:
            with open(exe,'rb') as file:
                if not 0<os.fstat(file.fileno()).st_size<=limit:return set()
                with mmap.mmap(file.fileno(),0,access=mmap.ACCESS_READ) as data:
                    return {api for api,dll in RENDERERS.items() if re.search(rb'(?i)'+re.escape(dll.encode()),data)}
        except (OSError,ValueError):
            return set()
    # Unchanged executables keep their answer between library scans.
    return feeder_provider.cached_probe('renderers' if e else 'renderers-delay',exe,probe)


def renderer_refusal(reason,apis):
    """A hard block when the game renders only with APIs this soft check's package can't hook."""
    supported=next((value for prefix,value in PACKAGE_APIS.items() if str(reason or '').startswith(prefix)),None)
    if not apis or supported is None or apis & set(supported):return ''
    names=' and '.join(LABELS[api] for api in sorted(apis))
    return f"This game renders with {names}, which this package doesn't support yet."


LIST=ROOT/'providers/compatibility.json'
SCHEMAS=(1,2)
# What a listed report keeps from a beta report: setup and results, never a GPU model,
# driver, path or note that could identify someone's machine or library.
REPORT_FIELDS={'platform':'os','distribution':'distribution','gpu-series':'gpu_series','app-build':'app',
               'feature-package':'package','features':'features','nr-result':'nr','mfg-result':'mfg'}


def shipped():
    """Reviewed results shipped with rtxForge, keyed by Steam app id or exe name."""
    try:data=json.loads(LIST.read_text(encoding='utf-8'))
    except (OSError,ValueError):return []
    if data.get('schema') not in SCHEMAS:return []
    return [entry for entry in data.get('games',[]) if isinstance(entry,dict) and entry.get('verdict') in VERDICTS]


def reports(row,listed=None):
    """The reviewed beta reports behind this game's listed verdict, newest first."""
    entry=next((entry for entry in (shipped() if listed is None else listed) if _match(entry,row)),None)
    return sorted((entry or {}).get('reports') or [],key=lambda r:str(r.get('date','')),reverse=True)


def summary(entry):
    """One line per OS: how many reviewed reports saw NR and MFG working."""
    lines=[]
    for system in ('Linux','Windows'):
        rows=[r for r in entry.get('reports') or [] if r.get('os')==system]
        if not rows:continue
        parts=[f"{name} working in {sum(r.get(key)=='Working in-game' for r in rows)} of {len(rows)}"
               for key,name in (('nr','NR'),('mfg','MFG')) if any(r.get(key) not in ('Not installed','',None) for r in rows)]
        lines.append(f"{system}: "+(' · '.join(parts) or f"{len(rows)} report{'s' if len(rows)!=1 else ''}"))
    return lines


def parse_issue(body):
    """Beta-report fields from an issue body as GitHub renders its form ('### Label' then the answer)."""
    import beta_report
    ids={name.casefold():key for key,name in beta_report.FIELDS}
    fields={}
    for heading,value in re.findall(r'(?m)^###[ \t]+(.+?)[ \t]*\n(.*?)(?=^###[ \t]|\Z)',str(body),re.S):
        key=ids.get(heading.strip().casefold())
        if key:fields[key]='' if value.strip()=='_No response_' else value.strip()
    return fields


def add_report(data,fields,issue,verdict,appid='',exe='',name='',note='',date=None):
    """Add one reviewed beta report to the list. A curator chooses the verdict; reports never set it."""
    import beta_report
    t.need(verdict in VERDICTS,'Verdict must be Working or Problem.')
    t.need(isinstance(issue,int) and issue>0,'Name the GitHub issue the report came from.')
    t.need(str(appid).isdigit() or exe,'Name the game by Steam app id or executable.')
    missing=[key for key in REPORT_FIELDS if not fields.get(key)]
    t.need(not missing,'The issue is missing: '+', '.join(beta_report.LABELS[key] for key in missing))
    row={'appid':str(appid) if str(appid).isdigit() else '','exe':Path(str(exe)).name}
    data['schema']=2
    games=data.setdefault('games',[])
    entry=next((entry for entry in games if _match(entry,row)),None)
    if entry is None:
        entry={key:value for key,value in row.items() if value};games.append(entry)
    entry.update(verdict=verdict,name=name or entry.get('name') or str(fields.get('game','')).split(' · ')[0])
    if note:entry['note']=note
    listed=entry.setdefault('reports',[])
    t.need(all(r.get('issue')!=issue for r in listed),f'Issue #{issue} is already listed.')
    report={'issue':issue,'date':date or t.now()[:10]}
    report.update({out:str(fields[key])[:120] for key,out in REPORT_FIELDS.items()})
    listed.append(report)
    return entry


def _match(entry,row):
    if entry.get('appid') and str(entry['appid'])==str(row.get('appid') or ''):return True
    exe=Path(str(row.get('exe') or '')).name.casefold()
    return bool(exe) and str(entry.get('exe','')).casefold()==exe


def verdict(row,record=None,listed=None):
    """Your own result first, then the shipped list. None when nothing is known."""
    record=record if record is not None else row.get('test_record') or {}
    if record.get('status') in VERDICTS:
        return {'verdict':record['status'],'source':'you','note':''}
    for entry in shipped() if listed is None else listed:
        if _match(entry,row):
            return {'verdict':entry['verdict'],'source':'list','note':str(entry.get('note',''))}
    return None


def set_try_anyway(config,game,on,reason=''):
    record=game_notes.load(config,game)
    if on:
        t.need(soft(reason),'Only capability checks can be skipped. This game stays blocked.')
        record['try_anyway']={'reason':str(reason),'at':t.now()}
    else:
        record.pop('try_anyway',None)
    game_notes.save(config,game,record);return record


def apply(config,rows,e=None):
    """Mark soft blocks, lift the ones you chose to try anyway, and attach each verdict."""
    listed=shipped()
    for row in rows:
        # A soft check on a renderer its package can't hook would never engage: block it.
        if any(soft(row.get(key)) for key in BLOCK_KEYS) and row.get('exe'):
            apis=renderers(Path(row['game'])/row['exe'],e)
            row['graphics_apis']=sorted(apis)
            for key in BLOCK_KEYS:
                if soft(row.get(key)) and (refusal:=renderer_refusal(row[key],apis)):row[key]=refusal
        # Fresh from disk: a review must see a Try anyway choice made after the scan.
        record=game_notes.load(config,row['game'])
        row['test_record']=record
        # Each package keeps its own verdict, so list every skippable one.
        row['soft_reasons']=sorted({row[key] for key in BLOCK_KEYS if soft(row.get(key))})
        if record.get('try_anyway') and row['soft_reasons']:
            row['try_anyway']=row['soft_reasons'][0]
            for key in BLOCK_KEYS:
                if soft(row.get(key)):row[key]=''
            row['nr_route_note']='Not verified · '+row['try_anyway']
            row['soft_reasons']=[]
        row['compat']=verdict(row,record,listed)
        row['features']=features(row)
    return rows


def features(row):
    """What this game can get before any review: {'nr': bool, 'mfg': bool}.

    A Feeder route offers MFG only when its provider says so (feeder_mfg); other
    routes need the game's own DLSS for NR and its own DLSS Frame Generation for
    MFG. Try anyway offers both, unverified. Installed games keep their profile.
    """
    if row.get('installed'):
        profile=str(row.get('profile') or '').casefold()
        return {'nr':'mfg only' not in profile,'mfg':'nr only' not in profile}
    if row.get('blocked'):
        return {'nr':False,'mfg':False}
    if row.get('try_anyway'):
        return {'nr':True,'mfg':True}
    if row.get('feeder_available') is True or row.get('runtime_provider')=='feeder':
        return {'nr':True,'mfg':row.get('feeder_mfg') is True}
    return {'nr':row.get('native_dlss') is True,'mfg':row.get('native_dlssg') is True}


def share(row,record,package,host,version,include_notes=False,channel=''):
    """A beta report for this game: the issue text and the prefilled form. Nothing is sent from here.

    Untested games and failed installs can be shared too; the results stay the user's to choose."""
    import beta_report
    system='Windows' if str(host.get('system',''))=='Windows' else None
    report=beta_report.draft(row,beta_report.context(host,version,channel,package,system=system),record)
    if include_notes:
        notes=game_notes.redact(str(record.get('notes','')).strip())[:beta_report.LENGTHS['observations']]
        if notes:beta_report.correct(report,'observations',notes)
    link=beta_report.issue_url(report)
    return {'title':beta_report.title(report),'body':beta_report.text(report),'url':link['url'],
            'complete':link['complete'],'report':report}


def package_label(key):
    """A pinned package's name and version, for frontends without their own names."""
    try:
        if key=='feeder':
            record=json.loads((ROOT/'providers/feeder.json').read_text(encoding='utf-8'));return record['name']
        record=json.loads((ROOT/'providers/lock.json').read_text(encoding='utf-8'))[key]
    except (OSError,ValueError,KeyError):return str(key or '')
    return ' '.join(str(part) for part in (record.get('name',key),record.get('tag') or record.get('version')) if part)


def version():
    try:return (ROOT/'VERSION').read_text(encoding='utf-8').strip()
    except OSError:return 'Unknown'


def main(argv=None):
    """Curators add a reviewed GitHub beta report to the shipped list (docs/COMPATIBILITY.md)."""
    import argparse
    parser=argparse.ArgumentParser(description=main.__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    add=sub.add_parser('add-report',help='Add one reviewed beta-report issue to providers/compatibility.json.')
    add.add_argument('--issue',type=int,required=True,help='GitHub issue number')
    add.add_argument('--body',type=Path,required=True,help='File holding the issue body (gh issue view N --json body -q .body)')
    add.add_argument('--verdict',choices=VERDICTS,required=True)
    add.add_argument('--appid',default='');add.add_argument('--exe',default='')
    add.add_argument('--name',default='');add.add_argument('--note',default='',help='Generic note; no hardware or library specifics')
    args=parser.parse_args(argv)
    data=json.loads(LIST.read_text(encoding='utf-8'))
    entry=add_report(data,parse_issue(args.body.read_text(encoding='utf-8')),args.issue,args.verdict,
                     args.appid,args.exe,args.name,args.note)
    LIST.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f"{entry['name']}: {entry['verdict']} · {len(entry['reports'])} report{'s' if len(entry['reports'])!=1 else ''}")
    return 0


if __name__=='__main__':raise SystemExit(main())
