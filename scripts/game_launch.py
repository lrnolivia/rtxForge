"""Resolve an installed game's existing launcher without changing its configuration."""
from pathlib import Path
from types import SimpleNamespace
import engine_bridge


def steam_uri(appid, *, shortcut=False):
    try:
        value = int(str(appid))
    except (TypeError, ValueError):
        raise ValueError('This game has no valid Steam launch ID.') from None
    if shortcut:
        if not -(2**31) <= value < 2**32:
            raise ValueError('This shortcut has an invalid Steam launch ID.')
        value = ((value & 0xffffffff) << 32) | 0x02000000
    elif not 0 < value < 2**32:
        raise ValueError('This game has an invalid Steam launch ID.')
    return f'steam://rungameid/{value}'


def resolve(config, row, *, engine=None):
    """Use Steam's recorded shortcut, preserving its Proton version and launch flags.

    Store-enrichment IDs are never used to launch a non-Steam installation.
    Unknown launchers and ambiguous accounts fail explicitly rather than running
    a Windows executable with a guessed prefix or command.
    """
    if row.get('source') == 'Steam':
        return steam_uri(row.get('appid'))
    e = engine if engine is not None else engine_bridge.module(config)
    root = Path(row['game']).expanduser().resolve()
    executable = (root / row.get('exe', '')).resolve()
    if not executable.is_relative_to(root) or executable == root:
        raise ValueError('Refresh this game’s executable before launching it.')
    game = SimpleNamespace(root=root, exe=executable, name=row['name'], appid=None)
    account = e.choose_steam_user_config([game], assume_yes=True)
    if not account or not Path(account['shortcuts']).is_file():
        raise ValueError('No configured launcher was found for this game. Add its existing launcher to Steam, then try Play again.')
    shortcuts = e.parse_shortcuts_spans(Path(account['shortcuts']).read_bytes())
    match = e.match_shortcut_span(game, shortcuts)
    if match is None:
        raise ValueError('No unique Steam shortcut matches this installation. Check the shortcut’s executable path, then try Play again.')
    return steam_uri(e._shortcut_int(match, 'appid'), shortcut=True)


def record_launch(config, event):
    """Keep bounded local diagnostics; never record credentials or launch flags."""
    import datetime,json,os
    import transactions
    from storage import storage
    folder=transactions.safe(storage(config)/'desktop'/'launch-logs')
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=transactions.safe(folder/'requests.jsonl')
    if path.exists() and path.stat().st_size>=1024*1024:
        previous=transactions.safe(folder/'requests.previous.jsonl')
        os.replace(path,previous)
    payload={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),**event}
    fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a',encoding='utf-8') as output:
        output.write(json.dumps(payload,ensure_ascii=False)+'\n')


def _report(config,event,recorder):
    try:(recorder or record_launch)(config,event)
    except Exception:
        import ui
        ui.emit('Could not save launch diagnostics; the launch request will continue.')


def prepare_launch(config,row,*,engine=None,recorder=None):
    import uuid
    context={'request_id':uuid.uuid4().hex,'game':row.get('name',''),'source':row.get('source',''),'installation':row.get('game','')}
    _report(config,{**context,'phase':'resolving'},recorder)
    try:uri=resolve(config,row,engine=engine)
    except Exception as error:
        _report(config,{**context,'phase':'resolution-failed','error':str(error)[:1024]},recorder)
        raise
    _report(config,{**context,'phase':'resolved','uri':uri},recorder)
    return {'uri':uri,'context':context}


def dispatch_launch(config,request,dispatch,*,recorder=None):
    """Record URI handoff, without claiming Steam started the game successfully."""
    context={**request['context'],'uri':request['uri']}
    try:dispatch(request['uri'])
    except Exception as error:
        _report(config,{**context,'phase':'dispatch-failed','error':str(error)[:1024]},recorder)
        raise
    _report(config,{**context,'phase':'submitted'},recorder)
