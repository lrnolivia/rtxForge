"""Fresh Windows library discovery, including collections and Steam pinned builds."""
from pathlib import Path
import re
import discovery
import executable_selection


def key(path):
    return str(Path(path).resolve()).casefold()


def scan(service, game_folders=(), library_folders=()):
    libraries = [Path(path) for path in service.libraries()]
    manifests = {}
    for library in libraries:
        for path in (library / 'steamapps').glob('appmanifest_*.acf'):
            data = discovery.parse_appmanifest(path)
            if data:
                manifests[(key(library), data['installdir'].casefold())] = data

    explicit = [Path(path).resolve() for path in game_folders]
    collections = [Path(path).resolve() for path in library_folders]
    collections += [library / 'PinnedBuilds' for library in libraries]
    games = []
    for path in explicit:
        # Old Add Folder allowed a collection and its child to be registered
        # together. Do not represent that parent as one enormous game.
        is_parent = any(other != path and other.is_relative_to(path) for other in explicit)
        if is_parent or path.name.casefold() in {'pinnedbuilds', 'games', 'non-steam games', 'nonsteam', 'common'}:
            collections.append(path)
        else:
            games.append(path)
    for parent in collections:
        try:
            games.extend(child for child in sorted(parent.iterdir())
                         if child.is_dir() and not child.is_symlink() and not child.name.startswith('.')
                         and not discovery.is_library_tool(child.name))
        except OSError:
            continue

    result, seen = [], set()
    def add(rows):
        for row in rows:
            if not Path(row['game']).is_dir(): continue
            executable_selection.decorate(row)
            identity = key(row['game'])
            if identity not in seen:
                seen.add(identity)
                result.append(row)
    for library in libraries:
        add(service.scan(library))
    unique = {key(path): path for path in games if path.is_dir()}
    add(service.scan(None, [str(path) for path in unique.values()]))

    for row in result:
        path = Path(row['game'])
        match = re.fullmatch(r'(.+)-(\d+)', path.name)
        if path.parent.name.casefold() != 'pinnedbuilds' or not match:
            continue
        data = manifests.get((key(path.parent.parent), match[1].casefold()))
        if data:
            # This ID is for presentation only. Engine ownership, launch and
            # installation identity continue to use the pinned copy's path.
            row['metadata_appid'] = data['appid']
            row['name'] = f"{data['name']} (Build {match[2]})"
    return sorted(result, key=lambda row: (row['name'].casefold(), key(row['game'])))
