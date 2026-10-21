"""Read display-only library data; copy artwork into a private sample profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil


def read_json(path, limit=4 * 1024 * 1024):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Missing or oversized JSON input')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def export(snapshot, settings_path, destination):
    destination = Path(destination).resolve()
    allowed = Path(os.environ['LOCALAPPDATA']) / 'rtxForge-samples'
    if not destination.is_relative_to(allowed.resolve()):
        raise ValueError('Use the dedicated private samples directory')
    if destination.exists():
        raise ValueError('Preserve existing sample curation; choose a new profile')
    saved = read_json(snapshot)
    rows = saved.get('rows')
    if saved.get('schema') != 1 or not isinstance(rows, list) or not 1 <= len(rows) <= 2000:
        raise ValueError('Invalid library snapshot')
    if any(not isinstance(row, dict) or not isinstance(row.get('game'), str) or not row['game']
           or not isinstance(row.get('name'), str) or not row['name'].strip() for row in rows):
        raise ValueError('Invalid display row')
    settings = read_json(settings_path)
    media = Path(settings_path).parent / 'state/desktop/media'
    destination.mkdir(parents=True)
    (destination / 'art').mkdir()
    result, counts, assets = [], {role: 0 for role in ('poster', 'capsule', 'hero')}, {}
    def image(value):
        if not isinstance(value, str) or value.startswith(('http:', 'https:')):
            return None
        path = Path(value)
        if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024 or path.is_symlink():
            return None
        data = path.read_bytes()
        # LibraryMedia caches some real image bytes with .wide/.hero names.
        extension = ('.png' if data.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg' if data.startswith(b'\xff\xd8\xff')
                     else '.webp' if data[:4] == b'RIFF' and data[8:12] == b'WEBP'
                     else '.gif' if data[:6] in (b'GIF87a', b'GIF89a') else '.bmp' if data[:2] == b'BM' else None)
        if extension is None:
            return None
        digest = hashlib.sha256(data).hexdigest()
        relative = 'art/' + digest + extension
        target = destination / relative
        if not target.exists():
            target.write_bytes(data)
        assets[relative] = digest
        return relative
    for index, row in enumerate(rows):
        identity = hashlib.sha256((row['game'].casefold() + '\0' + str(index)).encode()).hexdigest()[:24]
        appid = str(row.get('appid') or row.get('metadata_appid') or '')
        cached = {}
        for key in (hashlib.sha256((str(row.get('appid') or '') + row['name']).encode()).hexdigest()[:24],
                    hashlib.sha256(row['game'].encode()).hexdigest()[:16]):
            try:
                cached.update(read_json(media / (key + '.json')).get('data', {}))
            except (OSError, ValueError):
                pass
        overrides = settings.get('game_artwork', {})
        normalized = row['game'].replace('/', '\\').rstrip('\\').casefold()
        matching = [value for key, value in overrides.items() if key.replace('/', '\\').rstrip('\\').casefold() == normalized]
        custom = matching[0] if matching and isinstance(matching[0], dict) else {}
        game = {'id': 'sample_' + identity, 'name': row['name'], 'source': str(row.get('source') or 'Folder'),
                'appid': appid or None, 'developer': cached.get('developers'), 'release': cached.get('release'),
                'summary': cached.get('description'), 'metadata_source': cached.get('metadata_source'),
                'blocked': row.get('blocked') if isinstance(row.get('blocked'), str) else None}
        for role in counts:
            override = custom.get(role, {})
            override_path = override.get('path') if isinstance(override, dict) else override
            local = image(override_path) or image((row.get('art') or {}).get(role)) or image(cached.get(role))
            if local:
                game[role] = local; counts[role] += 1
            elif appid.isdigit():
                filename = {'poster': 'library_600x900.jpg', 'capsule': 'header.jpg', 'hero': 'library_hero.jpg'}[role]
                game[role] = f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/{filename}'
            else:
                game[role] = None
        result.append(game)
    manifest = {'schema': 1, 'kind': 'rtxforge-private-sample', 'games': result}
    (destination / 'library.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    receipt = {'catalog_count': len(result), 'local_artwork': counts, 'unique_artwork_files': len(assets),
               'snapshot_sha256': hashlib.sha256(Path(snapshot).read_bytes()).hexdigest(),
               'live_settings_sha256': hashlib.sha256(Path(settings_path).read_bytes()).hexdigest(),
               'manifest_sha256': hashlib.sha256((destination / 'library.json').read_bytes()).hexdigest(),
               'assets': assets}
    (destination / 'export-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return {key: value for key, value in receipt.items() if key != 'assets'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--settings', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.snapshot, args.settings, args.output), indent=2))
