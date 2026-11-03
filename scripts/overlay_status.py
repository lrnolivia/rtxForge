"""Read-only managed-overlay inventory and successful-update timestamps."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[1]


def _json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024**2:
        raise ValueError('Invalid overlay receipt: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _digest(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024**2:
        return None
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _key(path):
    return os.path.normcase(str(Path(path).resolve()))


def record_updates(state, plans):
    """Called only after the reviewed overlay operation completed successfully."""
    import transactions as t
    path = Path(state) / 'overlay-update-dates.json'
    previous = _json(path, {})
    if not isinstance(previous, dict):
        raise ValueError('Overlay update dates are unreadable.')
    when = datetime.now(timezone.utc).isoformat()
    for plan in plans:
        previous[_key(plan['target'])] = when
    path.parent.mkdir(parents=True, exist_ok=True)
    t.atomic_file(path, (json.dumps(previous, sort_keys=True) + '\n').encode(), 0o600)


def _available(root, provider):
    glass = _json(root / 'providers/glass-overlay/package.json', {})
    files = glass.get('files', {}) if isinstance(glass, dict) else {}
    expected = {}
    for name, item in files.items():
        if name == 'rtxforge-glass.dll' and isinstance(item, dict) and _digest(root / 'providers/glass-overlay' / name) == item.get('sha256'):
            expected[name] = item['sha256']
    folder = root / 'providers' / ('feeder-panel' if provider == 'feeder' else 'skynizz-bridge')
    receipt = _json(folder / 'package.json', {})
    receipt_files = receipt.get('files', {}) if isinstance(receipt, dict) else {}
    if not isinstance(receipt_files, dict):
        raise ValueError('The current overlay build receipt is unreadable.')
    for name, item in receipt_files.items():
        if isinstance(item, dict) and re.fullmatch(r'[a-fA-F0-9]{64}', str(item.get('sha256', ''))):
            if name.lower().endswith(('.addon64', '.addon32')) or name.lower() == 'optiscaler.dll':
                expected[name] = item['sha256'].lower()
    return glass, expected


def collect(root, state, rows=None, additional_states=()):
    root, state = Path(root), Path(state)
    version_file = root / 'VERSION'
    version = version_file.read_text(encoding='utf-8').strip() if version_file.is_file() else None
    warnings = []
    try:
        dates = _json(state / 'overlay-update-dates.json', {})
        if not isinstance(dates, dict):
            raise ValueError('Overlay update dates are unreadable.')
    except (OSError, ValueError) as error:
        dates = {}; warnings.append(str(error))
    names = {_key(row['game']): row.get('name') for row in rows or [] if row.get('game')}
    candidates = []
    for base in (state, *map(Path, additional_states)):
        for namespace in ('targets', 'feeder-targets'):
            candidates.extend((base / namespace).glob('*/baseline.json'))
    if len(candidates) > 1000:
        raise ValueError('Too many overlay installation records. Refresh your library.')
    games = {}; bundles = {}
    for path in sorted(candidates):
        try:
            record = _json(path)
            if not isinstance(record, dict) or record.get('status') != 'active':
                continue
            current = record.get('current') or {}
            target = Path(record.get('target_dir') or record.get('target') or '')
            if not target.is_absolute() or target.is_symlink():
                raise ValueError('Invalid overlay installation target.')
            game = record.get('game') or record.get('game_dir') or str(target)
            provider = record.get('provider_id') or current.get('provider_id') or 'native'
            owned = current.get('installed_hashes') or record.get('installed_hashes') or record.get('installed') or {}
            if not isinstance(owned, dict):
                raise ValueError('Overlay file ownership is unreadable.')
            release = (current.get('archive') or {}).get('release') or {}
            if provider not in bundles:
                bundles[provider] = _available(root, provider)
            receipt, available = bundles[provider]
            installed = {name: digest for name, digest in owned.items()
                         if PurePosixPath(name.replace('\\', '/')).name.lower() == 'rtxforge-glass.dll'}
            details = []
            status = 'unknown'
            installed_version = None
            if installed:
                revision = release.get('glass_revision') or record.get('glass_revision')
                source = release.get('glass_source') or record.get('glass_source')
                if revision:
                    installed_version = 'Revision ' + str(revision) + (' · ' + source[:12] if isinstance(source, str) else '')
                checks = dict(installed)
                for name, expected in available.items():
                    actual_name = current.get('proxy') if name.lower() == 'optiscaler.dll' else name
                    if actual_name and actual_name in owned:
                        checks[actual_name] = owned[actual_name]
                observed = {}
                for name, digest in checks.items():
                    relative = PurePosixPath(name.replace('\\', '/'))
                    if relative.is_absolute() or '..' in relative.parts or ':' in name:
                        raise ValueError('Invalid owned overlay file path.')
                    member = target.joinpath(*relative.parts)
                    if any(parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)() for parent in (member, *member.parents)):
                        raise ValueError('Linked overlay files cannot be verified.')
                    observed[name] = _digest(member)
                    if observed[name] != digest:
                        status = 'needs-attention'; details.append('An installed overlay file is missing or changed. Review Repair Features.')
                if status != 'needs-attention' and available.get('rtxforge-glass.dll'):
                    expected = dict(available)
                    if 'OptiScaler.dll' in expected and current.get('proxy'):
                        expected[current['proxy']] = expected.pop('OptiScaler.dll')
                    status = 'current' if all(observed.get(name) == digest for name, digest in expected.items()) else 'update-available'
                    if status == 'current':
                        installed_version = version or ('Revision ' + str(receipt.get('revision', '?')))
                elif status == 'unknown':
                    details.append('The current app bundle has no verified overlay receipt.')
            else:
                details.append('Native or older overlay; glass version provenance is not recorded.')
                installed_version = release.get('tag') or record.get('version')
            if not target.is_dir():
                status = 'unavailable'; details = ['The game folder is unavailable.']
            key = _key(target)
            last_updated = dates.get(key)
            games[key] = dict(game=str(game), target=str(target), name=names.get(_key(game)) or record.get('name') or target.name,
                              installedVersion=installed_version, currentVersion=version if available else None,
                              status=status, lastUpdated=last_updated, provider=provider, detail=' '.join(details))
        except (OSError, ValueError, KeyError, TypeError) as error:
            warnings.append(str(error))
    return dict(schema=1, currentVersion=version, checkedAt=datetime.now(timezone.utc).isoformat(),
                games=sorted(games.values(), key=lambda item: item['name'].casefold()), warnings=warnings)


def snapshot(config, rows=None):
    import engine_bridge
    import vulkan_app
    engine = engine_bridge.module(config)
    return collect(ROOT, engine.STATE_ROOT, rows, (vulkan_app.state_root(config),))
