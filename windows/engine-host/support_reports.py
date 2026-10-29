"""Bounded Windows log scans exported from an exact, redacted preview."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import platform
import re
import zipfile

import game_notes
import runtime_diagnostics as diagnostics
import transactions as t
import ui

LOGS = ('OptiScaler.log', 'sl.log', 'sl.dlss_g.log', 'sl.interposer.log',
        'ReShade.log', 'dlss5-feed.log', 'dlss5-feed-host.log', 'fgvk.log')
FILE_LIMIT = 256 * 1024
TOTAL_LIMIT = 16 * 1024**2
ZIP_LIMIT = 20 * 1024**2


def redact(text):
    text = game_notes.redact(text)
    return re.sub(r'(?i)(\b(?:token|session[_-]?id|cookie)\s*[:=]\s*)[^\s,;]+', r'\1[REDACTED]', text)


def preview(config, games, include_logs=False, include_notes=False, host=None, root=None, build=None):
    t.need(isinstance(games, list) and 0 < len(games) <= 1000, 'Choose one or more games for the report.')
    root = Path(root or Path(__file__).resolve().parents[2])
    import engine_bridge
    import library_media
    engine = engine_bridge.module(config)
    selected_package = library_media.load_settings(config).get('runtime_provider')
    files, manifest, records, seen = {}, [], [], set()
    remaining = TOTAL_LIMIT

    def collect(path, name, config_time=0):
        nonlocal remaining
        entry = {'name': name}
        try:
            t.need(remaining > 0, 'Report size limit reached')
            data, info = diagnostics.read_regular(path, min(FILE_LIMIT, remaining), tail=True)
            text = redact(data.decode('utf-8', errors='replace'))
            encoded = text.encode('utf-8')
            if len(encoded) > remaining:
                text = encoded[:remaining].decode('utf-8', errors='ignore')
            files[name] = text
            remaining -= len(text.encode('utf-8'))
            entry.update(included=True, original_size=info.st_size, preview_bytes=len(text.encode('utf-8')),
                         truncated=info.st_size > min(FILE_LIMIT, len(data)),
                         modified_utc=datetime.datetime.fromtimestamp(info.st_mtime, datetime.timezone.utc).isoformat(),
                         predates_settings=bool(config_time and info.st_mtime_ns < config_time))
        except (OSError, ValueError, t.Refusal) as error:
            entry.update(included=False, reason=type(error).__name__ + ': ' + redact(str(error)))
        manifest.append(entry)

    for index, game in enumerate(games):
        base = t.safe(game['game']); relative = t.relative(game.get('exe') or '')
        exe = t.safe(base / relative)
        t.need(exe.is_relative_to(base), 'Game executable leaves its folder')
        identity = os.path.normcase(str(exe))
        t.need(identity not in seen, 'A game was selected twice'); seen.add(identity)
        ui.progress('Scanning support logs', game=game.get('name', exe.stem), current=index + 1, total=len(games))
        note = game_notes.load(config, game['game'])
        item = {'name': game.get('name', exe.stem), 'appid': game.get('appid'),
                'scan_provider': game.get('runtime_provider'), 'feature_mode': game.get('feature_mode'),
                'installed_oses': game.get('installed_oses') or [], 'user_result': note.get('status', 'Untested'),
                'visible_result': 'Not established by installed files, saved settings or logs.'}
        try:
            if game.get('runtime_provider') == 'feeder':
                import feeder_provider
                record = t.read_json(feeder_provider.state_dir(engine, exe.parent) / 'baseline.json')
                item['recorded_install'] = {'provider':'feeder','legacy_recipe':record.get('legacy_recipe'),
                    'nr_runtime':{k:v for k,v in (record.get('nr_runtime') or {}).items() if k in ('version','sha256')},
                    'status':record.get('status')}
            elif game.get('runtime_provider') == 'vulkan-native':
                import vulkan_app
                record = vulkan_app.owned(game, config) or {}
                item['recorded_install'] = {'provider':record.get('provider_id'),'status':record.get('status'),
                                             'created_utc':record.get('created_utc')}
            else:
                current = (engine.load_baseline(exe.parent, readonly=True) or {}).get('current') or {}
                release = (current.get('archive') or {}).get('release') or {}
                item['recorded_install'] = {'provider':current.get('provider_id'),'mode':current.get('feature_mode'),
                    'release':{k:v for k,v in release.items() if k in ('repo','tag','commit','bridge_id','sha256')},
                    'mfg_component':{k:v for k,v in (release.get('mfg_component') or {}).items() if k in ('id','version','sha256')}}
        except (OSError, ValueError, KeyError, t.Refusal, engine.Stop) as error:
            item['recorded_install'] = {'unavailable':type(error).__name__}
        if include_notes: item['notes'] = redact(str(note.get('notes', '')))
        directory = exe.parent
        control = directory / ('ReShade.ini' if game.get('runtime_provider') == 'feeder' else 'OptiScaler.ini')
        try: config_time = control.stat().st_mtime_ns
        except OSError: config_time = 0
        if include_logs:
            directories = [directory]
            # Known helper and Vulkan runtime locations only; no recursive scan.
            if game.get('runtime_provider') == 'feeder' and (directory / 'host64').is_dir():
                directories.append(t.safe(directory / 'host64'))
            if game.get('runtime_provider') == 'vulkan-native':
                directories.append(t.safe(directory / 'NativeMods'))
            for part, folder in enumerate(directories):
                for log in LOGS: collect(folder / log, f'logs/{index:03}/{part}/{log}', config_time)
        records.append(item)
    if include_logs:
        local = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'rtxForge'
        for name in ('engine.log', 'crash.log'): collect(local / name, 'app/' + name)
    version = (root / 'VERSION').read_text(encoding='utf-8').strip() if (root / 'VERSION').is_file() else 'Unknown'
    files['report.json'] = redact(json.dumps({'schema': 1, 'created_utc': t.now(),
        'app_version': version, 'app_build': build or 'Unknown', 'selected_package_for_new_installs':selected_package,
        'system': platform.system(), 'os_version': platform.version(),
        'architecture': platform.machine(), 'hardware': host or {}, 'games': records,
        'scope': {'games': len(records), 'logs': include_logs, 'notes': include_notes},
        'evidence_note': 'Results are user observations. Log execution evidence does not prove visible correctness or FPS gains.'}, indent=2))
    files['manifest.json'] = json.dumps({'files': manifest, 'total_log_limit': TOTAL_LIMIT,
                                        'per_file_limit': FILE_LIMIT, 'remaining_bytes': remaining}, indent=2)
    files['README.txt'] = ('rtxForge support report. Review the exact redacted contents before export. '
        'Logs may be missing, truncated or from older sessions; see manifest.json. '
        'No game files were changed or games launched. Nothing was uploaded. '
        'To add logs to an existing report, open that GitHub issue and attach this ZIP to a comment.\n')
    return files


def export(files, destination=None):
    """Export only frozen preview bytes; do not rescan logs at export time."""
    destination = Path(destination or Path.home() / 'Documents/rtxForge Reports')
    destination = t.safe(destination)
    destination.mkdir(parents=True, exist_ok=True)
    out = destination / ('rtxForge-report-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.zip')
    t.need(sum(len(text.encode('utf-8')) for text in files.values()) <= ZIP_LIMIT - 1024**2,
           'The report is too large. Select fewer games or omit logs.')
    try:
        with zipfile.ZipFile(out, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, text in files.items():
                t.relative(name); archive.writestr(name, text)
        t.need(out.stat().st_size <= ZIP_LIMIT, 'The ZIP is too large. Select fewer games or omit logs.')
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    return out
