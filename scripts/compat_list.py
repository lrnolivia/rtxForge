"""Per-game compatibility: the shipped list, your own results, and Try anyway.

Never deploys, launches, sends, or modifies game files. Try anyway only lifts
capability checks (a game without the DLSS route a package expects); missing
executables, anti-cheat and installs that need attention stay blocked. A shared
result is a prefilled issue the user reviews and posts in their browser.
"""
import json,os,re,urllib.parse
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


def renderer_refusal(reason,apis):
    """A hard block when the game renders only with APIs this soft check's package can't hook."""
    supported=next((value for prefix,value in PACKAGE_APIS.items() if str(reason or '').startswith(prefix)),None)
    if not apis or supported is None or apis & set(supported):return ''
    names=' and '.join(LABELS[api] for api in sorted(apis))
    return f"This game renders with {names}, which this package doesn't support yet."


def shipped():
    """Reviewed results shipped with rtxForge, keyed by Steam app id or exe name."""
    try:data=json.loads((ROOT/'providers/compatibility.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return []
    return [entry for entry in data.get('games',[]) if isinstance(entry,dict) and entry.get('verdict') in VERDICTS]


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


def share(row,record,package,host,version,include_notes=False):
    """The exact issue text and the prefilled URL. Nothing is sent from here."""
    status=record.get('status','Untested')
    t.need(status in VERDICTS,'Record Working or Problem for this game first.')
    appid=str(row.get('appid') or '')
    lines=[
        f"**Game:** {row.get('name','')}",
        f"**Steam app ID:** {appid if appid.isdigit() else 'Non-Steam'}",
        f"**Executable:** {Path(str(row.get('exe') or '')).name or 'Unknown'}",
        f"**Result:** {status}",
        f"**Package:** {package or 'Unknown'}",
        f"**Mode:** {row.get('profile') or row.get('feature_mode') or 'Unknown'}",
    ]
    if record.get('try_anyway'):lines.append(f"**Tried anyway:** {record['try_anyway'].get('reason','')}")
    lines+=[
        f"**GPU:** {host.get('gpu','Unknown')} · driver {host.get('driver','Unknown')}",
        f"**OS:** {host.get('system','Unknown')}",
        f"**rtxForge:** {version}",
    ]
    notes=game_notes.redact(str(record.get('notes','')).strip())[:1500] if include_notes else ''
    if notes:lines+=['','**Notes**','',notes]
    body='\n'.join(lines)+'\n'
    title=f"[Compatibility] {row.get('name','')} · {status}"
    url=ISSUES+'?'+urllib.parse.urlencode({'title':title,'body':body,'labels':'compatibility'})
    return {'title':title,'body':body,'url':url}


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
