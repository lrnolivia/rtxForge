"""Per-game compatibility: the shipped list, your own results, and Try anyway.

Never deploys, launches, sends, or modifies game files. Try anyway only lifts
capability checks (a game without the DLSS route a package expects); missing
executables, anti-cheat and installs that need attention stay blocked. A shared
result is a prefilled issue the user reviews and posts in their browser.
"""
import json,re,urllib.parse
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


def soft(reason):
    reason=str(reason or '')
    return bool(reason) and any(reason.startswith(prefix) for prefix in SOFT)


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


def apply(config,rows):
    """Mark soft blocks, lift the ones you chose to try anyway, and attach each verdict."""
    listed=shipped()
    for row in rows:
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
    return rows


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
