"""Linux runtime API for the GTK app: Proton readiness, panel preferences and MFG observations.

Every function takes a library row ({'game', 'exe', 'appid', 'name', ...}) and
returns plain JSON-able data. Nothing here launches a game or changes Steam.
Writes (overlay_apply / overlay_restore) are reviewed first and refuse a busy
prefix or a registry that changed since review.
"""
from pathlib import Path
import hashlib
import importlib
import importlib.util
import json
import os
import stat
import sys

import proton_mfg
import proton_overlay
import proton_prefix
import proton_stack


def _prefix(row):
    try:
        return proton_prefix.find_prefix(row['game'], row.get('appid'))
    except proton_prefix.PrefixError:
        return None


def _target(row):
    return (Path(row['game']) / row['exe']).parent if row.get('exe') else Path(row['game'])


def proton_report(row, mode='nr-mfg', launch_options=''):
    """Read-only readiness of this game's Proton setup for native NR/MFG (see proton_stack.REASONS)."""
    report = proton_stack.detect(_prefix(row), mode, launch_options,
                                 native_dlssg=row.get('native_dlssg') if mode != 'nr-only' else None)
    report['user_reasons'] = [proton_stack.REASONS[code] for code in report['reasons']]
    return report


def overlay_state(e, row):
    return e.STATE_ROOT / 'prefix-overlay' / e.target_key(_target(row))


def overlay_review(row, settings, accent=None):
    """What Settings → Overlay would write into this game's prefix (nothing is written)."""
    prefix = _prefix(row)
    if prefix is None:
        raise proton_overlay.OverlayError('This game has not been started with Proton yet. Play it once, quit, then try again.')
    exe = Path(row['game']) / row['exe'] if row.get('exe') else None
    return proton_overlay.plan(prefix, settings, exe, row.get('name'), accent)


def overlay_apply(e, row, reviewed):
    return proton_overlay.apply(reviewed, overlay_state(e, row))


def overlay_restore(e, row):
    return proton_overlay.restore(overlay_state(e, row))


def mfg_observation(row):
    """What the Universal plugin wrote on its last run. Observation only; never verification."""
    return proton_mfg.runtime_report(_target(row))


# --- What Set Up for Linux writes besides the DLL override ---------------------------------

def _poster_pixels(path, size=64):
    """RGBA samples of a poster, sampled as the GTK app samples it (rtxforge_gtk.artwork_pixels)."""
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, False)
    if not pix.get_has_alpha():
        pix = pix.add_alpha(False, 0, 0, 0)
    data, stride = pix.get_pixels(), pix.get_rowstride()
    return [tuple(data[y * stride + x * 4:y * stride + x * 4 + 4]) for y in range(pix.get_height()) for x in range(pix.get_width())]


def game_accent(config, row, settings):
    """The accent the app shows for this game: the user's pick, else the Steam poster's signature colour."""
    import ui_colors
    custom = (settings.get('game_accents') or {}).get(row.get('game'))
    if custom:
        return custom
    try:
        import library_media
        poster = row.get('poster') or library_media.LibraryMedia(config, settings).steam_art(row).get('poster')
        return (poster and ui_colors.signature_color(_poster_pixels(poster))) or ui_colors.NO_ARTWORK
    except Exception:  # no GdkPixbuf, no poster or an unreadable image: the panel still opens, in grey
        return ui_colors.NO_ARTWORK


def cuda_state(e):
    return e.STATE_ROOT / 'proton-cuda'


def _overlay_state(e, target_dir):
    return e.STATE_ROOT / 'prefix-overlay' / e.target_key(target_dir)


def setup_review(config, row, settings, prefix, exe, mode, universal_mfg=None):
    """Reviewed plans for what makes Skynizz work under Proton beyond the proxy override.

    MFG modes with the Universal plugin get Proton's working CUDA library (see
    proton_cuda); every setup gets the in-game panel preferences and the game's
    identity (accent and title) in its prefix. Nothing is written here.
    universal_mfg -- the install carries the Universal plugin; None reads the game folder.

    setup_apply must run before anything else writes the prefix's user.reg:
    the panel plan refuses a registry that changed since review.
    """
    import proton_cuda
    import universal_mfg_provider as universal
    plans, notes = {}, []
    exe = Path(exe)
    if universal_mfg is None:
        universal_mfg = (exe.parent / universal.PLUGIN).is_file()
    if mode in ('nr-mfg', 'mfg-only') and universal_mfg:
        tool = proton_stack.compat_tool(Path(prefix).parent)
        plans['cuda'] = proton_cuda.plan(tool['lib_dir'])
        notes.append(plans['cuda']['summary'])
    overlay = proton_overlay.plan(prefix, settings, exe, row.get('name'), game_accent(config, row, settings))
    if not overlay['unchanged']:
        plans['overlay'] = overlay
        notes.append(overlay['summary'])
    return plans, notes


def setup_paths(e, target_dir, plans):
    """Everything setup_apply or setup_restore may write, for the operation's undo checkpoint."""
    import proton_cuda
    paths = [cuda_state(e), _overlay_state(e, target_dir)]
    paths.extend(Path(plan[key]) for plan, key in ((plans.get('cuda'), 'path'), (plans.get('overlay'), 'registry')) if plan)
    record = cuda_state(e) / proton_cuda.RECORD_NAME
    if record.is_file():
        paths.extend(Path(name) for name, entry in json.loads(record.read_text(encoding='utf-8')).items()
                     if e.target_key(target_dir) in entry['games'])
    return paths


def setup_apply(e, target_dir, plans):
    import proton_cuda
    result = {}
    if plans.get('cuda'):
        result['cuda'] = proton_cuda.apply(plans['cuda'], cuda_state(e), e.target_key(target_dir))
    if plans.get('overlay'):
        proton_overlay.apply(plans['overlay'], _overlay_state(e, target_dir))
        result['overlay'] = 'written'
    return result


def setup_restore(e, target_dir):
    """Undo setup_apply for one game; values and files edited since are kept."""
    import proton_cuda
    return {'cuda': proton_cuda.restore(cuda_state(e), e.target_key(target_dir)),
            'overlay': proton_overlay.restore(_overlay_state(e, target_dir))}


def record_runtime_evidence(e, row, report, observed, confirmed_by):
    """Store a human-confirmed real in-game session for this exact game/Proton build/GPU/component."""
    component = report.get('component') or {}
    return proton_stack.record_evidence(e.STATE_ROOT / 'proton-evidence', row.get('appid'), report['tool']['version'],
                                        (report.get('gpu') or {}).get('model'),
                                        f"{component.get('id', 'nr-only')}-{component.get('version', '')}".rstrip('-'),
                                        observed, confirmed_by)


# --- One-time Global review and game-menu review (shared with Windows) -----------------------

HOST = Path(__file__).resolve().parents[1] / 'windows' / 'engine-host'


def _shared(name):
    """The reviewed bulk modules the Windows host uses. They are platform-neutral Python
    over the same engine records; appended to the path so scripts/ always wins on names."""
    if str(HOST) not in sys.path:
        sys.path.append(str(HOST))
    return importlib.import_module(name)


def global_review(e, params):
    """ONE-TIME reviewed NR on/off and MFG (-1 auto, 0 off, 2..6) for installed packages.

    Never a persistent override: each game's INI changes once, with running,
    anti-cheat, drift and ownership checks; Feeder games take NR only.
    """
    return _shared('global_controls').prepare(e, e.STATE_ROOT, params)


def menus_review(e, params):
    """Reviewed OptiScaler/ReShade menu and intro changes for installed games (config only)."""
    return _shared('overlay_ui').prepare(e, params)


def overlay_packages_review(e, params):
    """The same owned package/menu update review used by the Windows app."""
    return _shared('overlay_packages').prepare(e, e.STATE_ROOT, params)


def apply_review(review):
    """Apply a global_review or menus_review result; every file is re-checked first."""
    return _shared('global_controls').execute(review)


# --- App Storage: inventory and exact-token cleanup of unused downloads ----------------------
#
# Linux keeps app data in two roots: the app's storage root (storage(config),
# default ~/.local/state/rtxforge: packages/, runtime-cache/, transactions/ ...)
# and the engine's state root (~/.local/state/rtxforge-dlss-unlocked: targets/,
# feeder-cache/, desktop-operations/ ...). The Windows policy is reused exactly:
# only unreferenced, single-link files in the two download caches can go; every
# JSON record in BOTH roots counts as a reference; the plan carries a token that
# is rechecked before any unlink. Restore backups are never cleanup targets.

LINUX_CACHES = {'package-downloads': ('app', 'packages'), 'dlss-downloads': ('app', 'runtime-cache')}
_LINUX_KEPT = {
    'game-backups': (('engine', 'targets'), ('engine', 'feeder-targets')),
    'feeder-restore': (('engine', 'feeder-cache'), ('engine', 'feeder-stack')),
    'operation-backups': (('engine', 'desktop-operations'), ('app', 'transactions'), ('app', 'batches'), ('app', 'cleanup')),
    'recovery': (('engine', 'cross-os-retired'), ('engine', 'steam-config-backups'), ('engine', 'prefix-overrides'),
                 ('engine', 'prefix-overlay'), ('engine', 'proton-evidence')),
}


def _storage_policy():
    """The Windows app_storage module, loaded under its own name (a scripts/ module must not shadow it)."""
    name = 'rtxforge_app_storage_policy'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, HOST / 'app_storage.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def storage_category(parts):
    for key, prefix in LINUX_CACHES.items():
        if tuple(parts[:2]) == prefix:
            return key
    for key, prefixes in _LINUX_KEPT.items():
        if tuple(parts[:2]) in prefixes:
            return key
    return 'other'


def _roots(app_root, engine_root):
    roots = {'app': Path(os.path.abspath(app_root)), 'engine': Path(os.path.abspath(engine_root))}
    if roots['app'] == roots['engine'] or roots['app'] in roots['engine'].parents or roots['engine'] in roots['app'].parents:
        raise _storage_policy().StorageError('App storage roots overlap. Cleanup was refused.')
    return roots


def _walk_roots(roots):
    policy = _storage_policy()
    for label, root in roots.items():
        if root.exists():
            for parts, info in policy._walk(root):
                yield (label, *parts), info


def storage_inventory(app_root, engine_root):
    """Fast accounting by category; never reads file contents or changes files."""
    policy = _storage_policy()
    totals = {key: dict(key=key, title=v[0], detail=v[1], cache=v[2], bytes=0, files=0) for key, v in policy.CATEGORIES.items()}
    warning = None
    try:
        roots = _roots(app_root, engine_root)
        for root in roots.values():
            if root.exists():
                policy._anchors(root)
        for parts, info in _walk_roots(roots):
            if stat.S_ISREG(info.st_mode):
                item = totals[storage_category(parts)]
                item['bytes'] += info.st_size
                item['files'] += 1
    except (OSError, policy.StorageError) as error:
        warning = f'Could not count all app data: {error}'
    return {'bytes': sum(c['bytes'] for c in totals.values()), 'categories': list(totals.values()), 'warning': warning}


def _inspect_storage(roots):
    policy = _storage_policy()
    anchors = tuple(policy._anchors(root) for root in roots.values() if root.exists())
    totals = {key: dict(key=key, title=v[0], detail=v[1], cache=v[2], bytes=0, files=0, cleanable_bytes=0)
              for key, v in policy.CATEGORIES.items()}
    cache_roots = [os.path.normcase(str(roots[p[0]].joinpath(*p[1:]))) for p in LINUX_CACHES.values()]
    files, caches, references, paths, hashes = [], [], [], set(), set()
    for parts, info in _walk_roots(roots):
        key = storage_category(parts)
        regular = stat.S_ISREG(info.st_mode)
        if regular:
            totals[key]['bytes'] += info.st_size
            totals[key]['files'] += 1
        absolute = roots[parts[0]].joinpath(*parts[1:])
        if key in LINUX_CACHES:
            caches.append((parts, policy._stamp(info)))
            if regular:
                if parts[-1].endswith('.part') or parts[-1].startswith(('.download-', '.rtxforge-')):
                    raise policy.StorageError('A package download is unfinished. Finish it, then review cleanup again.')
                files.append((parts, info.st_size, info.st_nlink))
        elif regular and parts[-1].lower().endswith('.json'):
            if info.st_size > policy.MAX_JSON:
                raise policy.StorageError('A storage record is too large to check safely. Cleanup was refused.')
            data = absolute.read_bytes()
            if policy._stamp(absolute.lstat()) != policy._stamp(info):
                raise policy.StorageError('App data changed while checking it. Review cleanup again.')
            try:
                document = json.loads(data.decode('utf-8-sig'))
            except (ValueError, UnicodeError):
                raise policy.StorageError('An app storage record could not be read. Cleanup was refused.') from None
            references.append((parts, hashlib.sha256(data).hexdigest()))
            values = [document]
            while values:
                value = values.pop()
                if isinstance(value, dict):
                    values.extend(value.values())
                elif isinstance(value, list):
                    values.extend(value)
                elif isinstance(value, str):
                    if len(value) in (40, 64) and all(c in '0123456789abcdefABCDEF' for c in value):
                        hashes.add(value.lower())
                    if os.path.isabs(value):
                        candidate = os.path.normcase(os.path.abspath(value))
                        if any(candidate == c or candidate.startswith(c + os.sep) for c in cache_roots):
                            paths.add(candidate)
    selected = []
    for parts, size, links in files:
        absolute = os.path.normcase(str(roots[parts[0]].joinpath(*parts[1:])))
        referenced = any(absolute == p or absolute.startswith(p + os.sep) for p in paths)
        if links > 1 or referenced or any(part.lower() in hashes for part in parts):
            continue
        selected.append(parts)
        totals[storage_category(parts)]['cleanable_bytes'] += size
    caches, references, selected = tuple(sorted(caches)), tuple(sorted(references)), tuple(sorted(selected))
    return {'roots': {k: str(v) for k, v in roots.items()}, 'files': selected, 'caches': caches,
            'categories': list(totals.values()),
            'token': hashlib.sha256(repr((anchors, caches, references, selected)).encode()).hexdigest()}


def storage_review(app_root, engine_root):
    """Which unused downloads could be removed; nothing is removed. The plan carries its token."""
    plan = _inspect_storage(_roots(app_root, engine_root))
    plan['cleanable_bytes'] = sum(c['cleanable_bytes'] for c in plan['categories'])
    plan['summary'] = (_storage_policy().size_label(plan['cleanable_bytes']) + ' can be cleared.' if plan['files']
                       else 'No unused downloads to clear.')
    return plan


def storage_cleanup(app_root, engine_root, plan):
    """Remove exactly the reviewed files. Any change since review removes nothing."""
    policy = _storage_policy()
    roots = _roots(app_root, engine_root)
    if not isinstance(plan, dict) or plan.get('roots') != {k: str(v) for k, v in roots.items()}:
        raise policy.StorageError('This storage review does not belong to this app.')
    fresh = _inspect_storage(roots)
    if fresh['token'] != plan.get('token') or fresh['files'] != tuple(plan.get('files') or ()):
        raise policy.StorageError('App data changed since review. Nothing was removed. Review cleanup again.')
    stamps = dict(fresh['caches'])
    for parts in fresh['files']:
        if storage_category(parts) not in LINUX_CACHES or any(p in ('', '.', '..') or '/' in p for p in parts[1:]):
            raise policy.StorageError('Cleanup target is outside the download caches.')
    removed = 0
    for parts in fresh['files']:
        path = roots[parts[0]].joinpath(*parts[1:])
        policy._anchors(path.parent)
        info = path.lstat()
        if policy._linked(info) or not stat.S_ISREG(info.st_mode) or policy._stamp(info) != stamps[parts]:
            raise policy.StorageError('A download changed during cleanup. Review the remaining files again.')
        path.unlink()
        removed += stamps[parts][3]
    return {'message': f'Freed {policy.size_label(removed)} of downloaded files. Restore backups and settings were kept.',
            'bytes': removed, 'files': len(fresh['files'])}
