"""Library display names, independent of installation and provider identity."""
from pathlib import Path
import re


def key(path):
    return str(Path(path).resolve()).casefold()


def valid_name(value):
    return (isinstance(value, str) and 0 < len(value.strip()) <= 200
            and not any(ord(char) < 32 or ord(char) == 127 for char in value))


def legendary_number(row):
    # Require the trilogy's executable layout; original games share EXE names.
    root = Path(row['game'])
    exe = Path(row.get('exe') or '')
    target = exe if exe.is_absolute() else root / exe
    match = re.search(r'/game/me([123])/binaries/win64/masseffect\1\.exe$', target.as_posix().casefold())
    return int(match[1]) if match else None


def legendary_name(row):
    number = legendary_number(row)
    return f'Mass Effect {number} (LE)' if number else None


def legendary_metadata(row):
    """Campaign metadata is separate from the collection's launch app ID."""
    number = legendary_number(row)
    if not number or str(row.get('appid')) != '1328670':
        return None
    appid, title, year = {
        1: ('17460', 'Mass Effect', '2007'),
        2: ('24980', 'Mass Effect 2', '2010'),
        3: ('1238020', 'Mass Effect 3', '2012'),
    }[number]
    return {'appid': appid, 'title': title, 'year': year, 'edition': 'Legendary Edition'}


def legendary_shortcut_id(engine, row, account):
    """Match the separate entry by target and arguments, never its editable name."""
    number = legendary_number(row)
    if not number or str(row.get('appid')) != '1328670':
        raise ValueError('This entry is not a Legendary Edition game.')
    path = Path(account['shortcuts'])
    if not path.is_file():
        raise ValueError('Add a separate Steam shortcut for this Legendary Edition game before syncing artwork.')
    expected = key(Path(account['root']) / 'steam.exe')
    direct = key(Path(row['game']) / row.get('exe', ''))
    options = ['-applaunch', '1328670', '-game', str(number), '-autoterminate']
    matches = []
    for item in engine.parse_shortcuts_spans(path.read_bytes()):
        exe = engine._shortcut_string(item, 'exe').strip().strip('"')
        args = engine._shortcut_string(item, 'LaunchOptions').split()
        if exe and (key(exe) == direct or (key(exe) == expected and args == options)):
            matches.append(item)
    if len(matches) != 1:
        raise ValueError('No unique Steam shortcut matches this Legendary Edition game. Keep one separate shortcut before syncing artwork.')
    appid = engine._shortcut_int(matches[0], 'appid')
    if isinstance(appid, bool) or not isinstance(appid, int) or not -(2**31) <= appid < 2**32 or not appid:
        raise ValueError('The matching Steam shortcut has no valid app ID.')
    return appid & 0xffffffff


def decorate(rows, settings):
    names = settings.get('game_names')
    overrides = {key(path): name.strip() for path, name in names.items()
                 if isinstance(path, str) and valid_name(name)} if isinstance(names, dict) else {}
    for row in rows:
        detected = legendary_name(row) or row.get('detected_name') or row['name']
        row['detected_name'] = detected
        row['name'] = overrides.get(key(row['game']), detected)
    return rows
