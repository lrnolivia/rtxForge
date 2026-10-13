import pathlib,re
import transactions as t
P=pathlib.Path
def win_rel(path, root):
    p = pathlib.PureWindowsPath(path)
    r = pathlib.PureWindowsPath(root)
    t.need(p.is_absolute() and r.is_absolute(), 'Windows manifest paths must be absolute')
    try:
        result = p.relative_to(r).as_posix()
    except ValueError:
        raise t.Refusal('Manifest path outside recorded game root')
    t.relative(result)
    return result
def import_record(path, game, exe, code=None):
    doc = t.read_json(path)
    owned = {}
    if 'plan' in doc:
        t.need(doc.get('status') == 'complete' and P(doc['plan']['game']) == game, 'Invalid portable ownership record')
        return {r['path']: r['after'] for r in doc['plan']['managed'] if r['after'] is not None}
    rows = doc.get('games', doc.get('Games', []))
    matches = []
    for row in rows:
        win = 'Root' in row
        root = row.get('Root', row.get('root', ''))
        if code and str(row.get('Code', row.get('code'))) != code:
            continue
        if win:
            if not code and pathlib.PureWindowsPath(root).name.casefold() != game.name.casefold():
                continue
            try:
                rel = win_rel(row['Exe'], root)
            except (KeyError, t.Refusal):
                continue
        else:
            if P(root).resolve() != game:
                continue
            try:
                rel = P(row['exe']).relative_to(game).as_posix()
            except (KeyError, ValueError):
                continue
        if rel.casefold() == exe.casefold():
            matches.append(row)
    t.need(len(matches) == 1, 'Manifest must map exactly one selected game/executable; specify --record CODE for Windows')
    row = matches[0]
    t.need(row.get('Status', 'SUCCESS') == 'SUCCESS', 'Failed Windows deployment cannot be adopted')
    for it in row.get('Installs', row.get('installed', [])):
        if 'Path' in it:
            rel = win_rel(it['Path'], row['Root'])
            h = it.get('SHA256', '')
        else:
            try:
                rel = P(it['path']).relative_to(game).as_posix()
            except ValueError:
                raise t.Refusal('Manifest file outside selected game')
            h = it.get('sha256', '')
        t.relative(rel)
        t.need(re.fullmatch('[a-fA-F0-9]{64}', h or ''), 'Manifest lacks file hash: ' + rel)
        t.need(rel.casefold() not in {n.casefold() for n in owned}, 'Duplicate manifest file')
        owned[rel] = h.lower()
    return owned
