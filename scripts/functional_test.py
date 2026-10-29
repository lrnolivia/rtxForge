"""Shared, session-bound functional tests for every package and host.

Only observed execution is a runtime pass. File ownership, requested settings and
picture quality are separate facts. Unreported telemetry always remains unknown.
"""
from collections import Counter
from pathlib import Path
import configparser
import hashlib
import math
import os
import re
import statistics
import threading
import time

PARTS = (('files', 'Package files'), ('settings', 'Saved settings'), ('shortcut', 'Panel shortcut'),
         ('proton', 'Proton / CUDA'), ('hook', 'Game hook'), ('nr', 'Neural Rendering (NR)'),
         ('mfg', 'Multi-Frame Generation (MFG)'), ('panel', 'In-game panel'), ('helper', 'Overlay helper'))
WORKING, PROBLEM, NOT_TESTED, NOT_REPORTED = 'working', 'problem', 'not-tested', 'not-reported'
PLACEMENTS = {0: 'waiting for a model result', 1: 'NR off', 2: 'before super resolution',
              3: 'after super resolution', 4: 'no model result that frame'}
SAMPLE_LIMIT = 3600
LOG_LIMIT = 4 * 1024**2
LOG_NAMES = ('OptiScaler.log', 'sl.log', 'sl.dlss_g.log', 'sl.interposer.log', 'ReShade.log',
             'dlss5-feed.log', 'dlss5-feed-host.log', 'host64/ReShade.log', 'host64/dlss5-feed-host.log',
             'fgvk.log', 'NativeMods/fgvk.log', 'RTXMFG-Universal.status.json')
STREAMLINE = {
    1: ('output resolution too low', 'Raise the game’s output resolution and test again.'),
    2: ('NVIDIA Reflex not detected', 'Turn on NVIDIA Reflex in the game’s settings.'),
    4: ('unsupported HDR format', 'Try the game’s other HDR mode or turn HDR off and test again.'),
    8: ('invalid frame data', 'Send a bug report with logs for this game integration problem.'),
    16: ('missing back buffer', 'Send a bug report with logs for this game integration problem.'),
}


def directory(row):
    import transactions as t
    root = t.safe(row['game'])
    relative = t.relative(row['exe'])
    target = t.safe(root / relative)
    t.need(target.is_relative_to(root), 'The game executable is outside its folder.')
    return target.parent


def preflight(row, settings=None, status=None, shortcut=None):
    """Read the installed identity, not the package selected for the next install."""
    import cross_os
    import runtime_diagnostics
    import transactions as t
    settings, status = settings or {}, status or {}
    target = directory(row)
    record = cross_os.read(target)
    result = {'route': (record or {}).get('provider', {}).get('id') or row.get('runtime_provider') or 'unknown',
              'feature_mode': (record or {}).get('feature_mode') or row.get('profile'),
              'files_ok': None, 'settings_ok': None, 'shortcut_ok': shortcut,
              'detail': str(status.get('detail') or ''), 'pipelines': status.get('pipelines') or {},
              'proton_ok': None, 'platform': 'windows' if os.name == 'nt' else 'linux'}
    result['helper_required']=settings.get('overlay_renderer','game')!='optiscaler'
    if record:
        problems = []
        for name, expected in record['files'].items():
            try:
                path = t.safe(target / t.relative(name))
                # Settings are mutable; validate their values separately.
                if path.suffix.lower() in ('.ini', '.log', '.json'): continue
                if not path.is_file() or t.digest(path) != expected: problems.append(name)
            except (OSError, ValueError, t.Refusal): problems.append(name)
        result['files_ok'] = not problems
        result['files_detail'] = 'Missing or changed: ' + ', '.join(problems[:12]) if problems else 'Managed runtime files match their recorded SHA-256.'
        result['install_revision'] = record.get('revision')
    else:
        result['files_detail'] = 'No shared install record. Repair or adopt this game to verify package ownership.'
    config_names = ('OptiScaler.ini',) if result['route'] not in ('feeder', 'vulkan-native') else ('ReShade.ini', 'host64/ReShade.ini') if result['route'] == 'feeder' else ('NativeMods/fgvk.ini', 'fgvk.ini')
    errors, found = [], False
    for name in config_names:
        path = target / name
        if not path.exists(): continue
        found = True
        try:
            raw, _ = runtime_diagnostics.read_regular(path, 2 * 1024**2)
            parser = configparser.ConfigParser(interpolation=None, strict=True)
            parser.read_string(raw.decode('utf-8-sig'))
            if name == 'OptiScaler.ini':
                enabled = parser.get('DlssNr', 'Enabled', fallback='auto').lower()
                if enabled not in ('auto', 'true', 'false', '0', '1'): raise ValueError('NR enabled value is invalid')
                intensity = parser.get('DlssNr', 'Intensity', fallback='auto')
                if intensity.lower() != 'auto' and not (math.isfinite(float(intensity)) and 0 <= float(intensity) <= 2): raise ValueError('NR intensity is outside 0–2')
                count = parser.get('DLSSG', 'OverrideInterpolationCount', fallback='auto')
                if count.lower() != 'auto' and not 0 <= int(count) <= 5: raise ValueError('MFG count is outside 0–5')
                result['requested'] = None if count.lower() == 'auto' else (int(count) + 1 if int(count) else 0)
                result['nr_enabled'] = None if enabled == 'auto' else enabled in ('true', '1')
            elif name.endswith('fgvk.ini'):
                count=parser.getint('fgvk','DLSSGFrames',fallback=1)
                if not 1 <= count <= 3:raise ValueError('Vulkan generated frame count must be 1–3')
                result['requested']=count+1
        except (OSError, ValueError, configparser.Error) as error: errors.append(str(error))
    result['settings_ok'] = not errors if found else None
    result['settings_detail'] = '; '.join(errors) or ('Configuration parsed successfully; live values are checked during play.' if found else 'This package’s configuration was not found at a known location.')
    result['shortcut_detail'] = str(settings.get('overlay_panel_hotkey') or settings.get('panel_hotkey') or 'Not checked')
    if result['route']=='feeder' and found and not errors:
        try:
            import feeder_provider
            host=target/'host64' if (target/'host64/ReShade.ini').is_file() else target
            configured=feeder_provider.configured(host,target)
            result['nr_enabled']=configured['nr_enabled']
            result['settings_detail']+=' Feeder NR technique '+('enabled.' if configured['nr_enabled'] else 'disabled; enable Neural Uplift and DLSS5_Feed before testing NR.')
        except (OSError,ValueError,configparser.Error) as error:
            result['settings_ok']=False;result['settings_detail']=str(error)
    if os.name != 'nt':
        try:
            import linux_runtime
            if result['route']=='feeder':
                import proton_stack
                report=proton_stack.feeder_detect(linux_runtime._prefix(row),row.get('launch_options',''))
                report['user_reasons']=[proton_stack.REASONS[code] for code in report['reasons']]
            else:
                report = linux_runtime.proton_report(row, 'nr-only' if result['feature_mode'] in ('nr-only', 'NR Only') else 'nr-mfg', row.get('launch_options', ''))
            result['proton_ok'] = report['prerequisites_met']
            result['proton_detail'] = '; '.join(report['user_reasons']) or report['label']
        except (OSError, ValueError, RuntimeError, t.Refusal) as error: result['proton_detail'] = str(error)
    return result


def log_baseline(row):
    """Record exact end positions so an appended old log cannot become a new run."""
    import runtime_diagnostics
    found = {}
    target = directory(row)
    for name in LOG_NAMES:
        try:
            data, info = runtime_diagnostics.read_regular(target / name, LOG_LIMIT, tail=True)
            found[name] = {'size': info.st_size, 'dev': info.st_dev, 'ino': info.st_ino,
                           'tail': hashlib.sha256(data).hexdigest(), 'tail_size': len(data)}
        except (OSError, ValueError): pass
    return found


def session_logs(row, baseline):
    """Only bytes after Start Test (or a newly created/replaced log), bounded per file."""
    import runtime_diagnostics
    captured, fresh = {}, {'_continued': []}
    for name in LOG_NAMES:
        try: data, info = runtime_diagnostics.read_regular(directory(row) / name, LOG_LIMIT, tail=True)
        except (OSError, ValueError): continue
        captured[name] = data
        previous = baseline.get(name)
        if previous and (info.st_dev, info.st_ino) == (previous['dev'], previous['ino']) and info.st_size >= previous['size']:
            # At most the newly appended tail; no earlier model/run header survives.
            added = info.st_size - previous['size']
            data = data[-min(added, len(data)):] if added else b''
            fresh['_continued'].append(name)
        fresh[name] = data.decode('utf-8', errors='replace')
    return captured, fresh


def compact(found, now):
    values = found.get('values') or {}
    def number(key):
        value = found.get(key)
        return value if type(value) in (int, float) and math.isfinite(value) else None
    return {'t': float(now), 'state': found.get('state'), 'bridge': found.get('telemetry_source') == 'skynizz-mailbox',
            'pid': number('pid'), 'sequence': number('sequence'), 'version': number('version'), 'can_nr': found.get('can_nr'), 'can_mfg': found.get('can_mfg'),
            'nr': found.get('nr_running'), 'nr_ms': number('nr_ms'),
            'place': found.get('nr_placement') if found.get('nr_placement_verified') else None,
            'fps': number('rendered_fps'), 'fresh': found.get('native_fresh') is True,
            'status': number('native_status'), 'presented': number('native_presented'),
            'generated': number('native_generated'), 'mode': number('native_mode'), 'fg': number('fg_successes'),
            'failure': str(found.get('failure') or (found.get('detail') if found.get('state')=='unavailable' else '') or '')[:160], 'nr_on': values.get('enabled'),
            'helper': found.get('helper') or {},
            'intensity': values.get('intensity'), 'mult': values.get('multiplier'),
            'dynamic': values.get('dynamic_mfg'), 'dynamic_supported': found.get('dynamic_supported')}


def keep(samples, sample):
    samples.append(sample)
    if len(samples) > SAMPLE_LIMIT: del samples[1:1 + SAMPLE_LIMIT // 4]
    return samples


def _median(values):
    values = [v for v in values if type(v) in (int, float) and math.isfinite(v)]
    return statistics.median(values) if values else None


def summarize(samples):
    samples = list(samples or [])
    bridge = [s for s in samples if s.get('bridge') and s.get('state') in ('running', 'stalled')]
    live = [s for s in bridge if s.get('state') == 'running']
    progressing = [b for a,b in zip(live,live[1:]) if a.get('pid')==b.get('pid') and a.get('sequence') is not None and b.get('sequence') is not None and a['sequence']!=b['sequence']]
    nr = [s for s in progressing if s.get('nr') is True and (s.get('nr_ms') or 0) > 0]
    fresh = [s for s in live if s.get('fresh') and s.get('presented') is not None]
    fg = [s for s in fresh if (s.get('mode') or 0) > 0 and (s.get('generated') or 0) > 0 and (s.get('presented') or 0) >= 2]
    statuses = 0
    for s in fresh:
        if type(s.get('status')) is int and s['status'] > 0: statuses |= s['status']
    calls = sum(max(0, b['fg'] - a['fg']) for a, b in zip(live, live[1:])
                if a.get('pid') == b.get('pid') and type(a.get('fg')) is int and type(b.get('fg')) is int)
    last = (live or bridge or samples or [{}])[-1]
    return {'samples': len(samples), 'connected': len(bridge), 'live': len(live), 'stalled': len(bridge) - len(live),
            'nr_active': len(nr), 'nr_ms': _median(s.get('nr_ms') for s in nr),
            'reports_nr': any(s.get('nr') is not None for s in live), 'reports_mfg': any(s.get('presented') is not None for s in live),
            'fresh_mfg': len(fresh), 'framegen': len(fg), 'presented': _median(s.get('presented') for s in fg),
            'generated': _median(s.get('generated') for s in fg), 'streamline': statuses, 'fg_calls': calls,
            'settings_changed': len({(s.get('mult'), s.get('dynamic')) for s in live}) > 1,
            'placements': dict(Counter(PLACEMENTS.get(s['place'], 'unknown') for s in live if s.get('place') is not None)),
            'fps': _median(s.get('fps') for s in live), 'pids': sorted({s['pid'] for s in bridge if s.get('pid')}),
            'helper_running': sum(s.get('helper',{}).get('running') is True for s in samples),
            'panel_attached': sum(bool(s.get('helper',{}).get('channel_valid') is True and s.get('pid') and s['helper'].get('pid')==s['pid']) for s in bridge),
            'failures': sorted({s['failure'] for s in samples if s.get('failure')})[:5],
            **{key: last.get(key) for key in ('can_nr', 'can_mfg', 'nr_on', 'intensity', 'version', 'dynamic', 'dynamic_supported')},
            'requested': last.get('mult')}


def log_evidence(logs, route):
    """Parse actual provider messages, never settings or merely a DLL filename."""
    import runtime_diagnostics
    opti = runtime_diagnostics.parse_log(logs.get('OptiScaler.log', ''))
    windows=re.findall(r'DLSS-NR GPU window:[^\n]*',logs.get('OptiScaler.log',''))
    if 'OptiScaler.log' in logs.get('_continued',[]) and not opti['run_header_observed']:windows=windows[1:]
    timed=any(re.search(r'(?:\b([1-9]\d*)\s+samples\b|\bsamples\s*[=:]\s*([1-9]\d*)\b)',line) for line in windows)
    result = {'hook': opti['run_header_observed'], 'nr_created': opti['model_created'],
              'nr_evaluated': timed, 'warnings': opti['warnings'], 'nr_detail': opti['last_gpu_sample']}
    if route == 'feeder':
        import feeder_provider
        feed = feeder_provider.parse_logs(logs.get('dlss5-feed.log', ''), logs.get('ReShade.log', '') + '\n' + logs.get('host64/ReShade.log', ''))
        result.update(nr_created=feed['feature18_created'], nr_evaluated=feed['feature18_evaluated'] and feed['last_evaluation_count']>0,
                      nr_detail='NR feature 18 evaluations: ' + str(feed['last_evaluation_count']),
                      hook=feed['feature18_created'] or feed['feature18_evaluated'])
        result['inputs'] = feed
    if route in ('vulkan-native', 'bg3fgvk-vulkan-dlssg'):
        text = logs.get('fgvk.log', '') + '\n' + logs.get('NativeMods/fgvk.log', '')
        result['hook'] = 'fgvk log start' in text or 'FG inputs submitted ok' in text
        stats = re.findall(r'FG stats: (\d+) presents -> (\d+) frames displayed \(x([\d.]+)\) status=(\d+)', text)
        if any(name.endswith('fgvk.log') for name in logs.get('_continued',[])) and 'fgvk log start' not in text:stats=stats[1:]
        valid = [(int(a), int(b), int(b)/int(a), int(d)) for a, b, c, d in stats if int(a) > 0 and math.isfinite(float(c)) and abs(int(b)/int(a)-float(c))<.02]
        if valid:
            result['mfg_stats'] = valid[-1]
            result['hook'] = True
        nr=re.findall(r'NR stats: (\d+) native Vulkan evaluations composed, GPU ([\d.]+)ms',text)
        if nr:
            frames,ms=nr[-1]
            result['nr_evaluated']=int(frames)>0 and math.isfinite(float(ms)) and float(ms)>0
            result['nr_detail']=f'{frames} native Vulkan evaluations composed; GPU {ms} ms; placement: after super resolution.'
        result['warnings'] += [line[:250] for line in text.splitlines() if re.search(r'LOAD FAILED|required extension unavailable|NR disabled|dispatch unavailable', line)][-4:]
    return result


def _result(part, state, summary, evidence=(), fix=None):
    return {'part': part, 'title': dict(PARTS)[part], 'state': state, 'summary': summary,
            'evidence': [str(line) for line in evidence if line], 'fix': fix}


def evaluate(summary, logs=None, helper=None, pipelines=None, checks=None):
    checks, helper = checks or {}, helper or {}
    route = checks.get('route', 'unknown')
    evidence = log_evidence(logs or {}, route)
    results = []
    def add(part, state, text, lines=(), fix=None): results.append(_result(part, state, text, lines, fix))
    for part, key, fix in (('files', 'files_ok', 'Repair Feature Files for this game; check conflicting proxy DLLs.'),
                           ('settings', 'settings_ok', 'Repair the game configuration and reapply your preset.'),
                           ('shortcut', 'shortcut_ok', 'Choose an enabled panel shortcut in Settings › Overlay.'),
                           ('proton', 'proton_ok', 'Use Set Up for Linux and a Proton build with CUDA support.')):
        value = checks.get(key)
        if part == 'proton' and checks.get('platform') == 'windows':
            add(part, NOT_TESTED, 'Not applicable on Windows.'); continue
        add(part, WORKING if value is True else PROBLEM if value is False else NOT_REPORTED,
            'Preflight passed.' if value is True else 'Needs attention.' if value is False else 'Not reported by this package.',
            [checks.get(part + '_detail')], None if value is True else fix)
    connected = summary['connected']
    add('hook', WORKING if connected or evidence['hook'] else NOT_REPORTED,
        'An injected runtime answered or logged execution during this session.' if connected or evidence['hook'] else 'No injected runtime execution was observed.',
        [f"{connected} verified mailbox samples." if connected else ''],
        None if connected or evidence['hook'] else 'Play for a minute after Start Test. If the game was running, repair its files and check for a DLL hook conflict.')
    nr_evaluated = summary['nr_active'] or evidence['nr_evaluated']
    if checks.get('feature_mode') in ('mfg-only','MFG Only'):
        add('nr',NOT_TESTED,'NR is not included in this installed feature mode.')
    elif nr_evaluated:
        add('nr', WORKING, 'NR model evaluation was observed.',
            [f"Median GPU time: {summary['nr_ms']:.2f} ms." if summary['nr_ms'] else evidence.get('nr_detail'),
             'Placement: ' + ', '.join(summary['placements']) if summary['placements'] else 'Placement: not reported by this package.',
             *evidence.get('warnings', [])])
    elif summary['reports_nr'] and summary['nr_on'] != 0 or evidence['nr_created']:
        add('nr', PROBLEM, 'NR did not report a completed, timed evaluation.', evidence.get('warnings', []),
            'Raise NR intensity above 0.' if summary['intensity'] == 0 else 'Select DLSS as the game’s upscaler, check the model and CUDA prerequisites, then test in gameplay.')
    elif summary['nr_on'] == 0 or checks.get('nr_enabled') is False:
        add('nr', NOT_TESTED, 'NR was disabled.', fix='Enable NR and use a moving gameplay scene to test it.')
    else:
        add('nr', NOT_REPORTED, 'NR execution: not reported by this package in this session.',
            fix='Check DLSS / the Feeder technique, model files and the route’s logs. Submit a bug report if no evaluation appears.')
    requested = summary['requested'] if summary['requested'] is not None else checks.get('requested')
    vulkan = evidence.get('mfg_stats')
    if route == 'feeder' or checks.get('feature_mode') in ('nr-only', 'NR Only'):
        add('mfg', NOT_TESTED, 'MFG is not included in this installed route / feature mode.')
    elif summary['dynamic'] and summary['dynamic_supported'] is False:
        add('mfg', PROBLEM, 'Dynamic MFG was requested but the game reports no support.', fix='Disable Dynamic MFG and try a fixed multiplier.')
    elif summary['settings_changed']:
        add('mfg', NOT_TESTED, 'MFG settings changed; comparison is inconclusive.', fix='Repeat with one fixed setting.')
    elif requested == 0:
        add('mfg', NOT_TESTED, 'MFG was disabled.', fix='Enable frame generation in the game, then choose a multiplier.')
    elif summary['framegen'] or vulkan and vulkan[1] > vulkan[0] and vulkan[3] == 0:
        shown = summary['presented'] if summary['framegen'] else vulkan[2]
        low = type(requested) in (int, float) and requested > 1 and shown < requested and not summary['dynamic']
        add('mfg', PROBLEM if low else WORKING, f'MFG presented {shown:g}x' + ('; below the requested multiplier.' if low else '.'),
            [f'Requested: {requested}x.' if requested is not None else 'Requested multiplier: not reported.',
             f"Successful FG calls increased by {summary['fg_calls']}.",
             f"Generated frames per present: {summary['generated']}." if summary['generated'] is not None else '',
             f"Rendered FPS: {summary['fps']:.0f}." if summary['fps'] else '',
             'Dynamic MFG support: ' + str(summary['dynamic_supported'])],
            'Try a lower multiplier and check frame caps / V-Sync.' if low else None)
    elif summary['fresh_mfg'] or vulkan:
        status = summary['streamline'] or (vulkan[3] if vulkan else 0)
        flags = [STREAMLINE[b] for b in STREAMLINE if status & b]
        add('mfg', PROBLEM, 'No generated frames were observed.' + (' ' + '; '.join(r for r, _ in flags) if flags else ''),
            fix=flags[0][1] if flags else 'Enable DLSS Frame Generation and NVIDIA Reflex in the game’s own settings.')
    else:
        add('mfg', NOT_REPORTED, 'Fresh generated-frame telemetry: not reported by this package.',
            fix='Play with frame generation enabled and include the route’s logs in a bug report. A requested multiplier alone is not a pass.')
    if connected and summary['stalled'] * 2 > connected:
        add('panel', PROBLEM, 'The control bridge was stale for most of the test.', summary['failures'], 'Repeat in active gameplay, unpaused and not minimised.')
    else:
        attached = summary['panel_attached']>0 or helper.get('channel_valid') is True and helper.get('pid') in summary['pids']
        add('panel', WORKING if attached else NOT_REPORTED,
            'The helper attached to this game’s panel channel.' if attached else 'Panel attachment: not reported by this package.',
            summary['failures'], None if attached else 'Check the panel shortcut and helper, then open the panel in the game.')
    start, finish = helper.get('start'), helper.get('finish')
    problem = helper.get('problem') or helper.get('poll_error') or helper.get('target_error')
    ok = start is True and finish is True and not problem
    if checks.get('helper_required') is False:
        add('helper',NOT_TESTED,'The selected native OptiScaler menu does not require the rtxForge helper.')
        return results
    add('helper', WORKING if ok else PROBLEM if start is False or finish is False or problem else NOT_REPORTED,
        'Helper answered at Start and Finish.' if ok else 'Helper unavailable or not observed at both checkpoints.',
        [problem], None if ok else 'Enable the overlay helper in Settings › Overlay and repeat the test.')
    return results


def suggestion(results):
    if any(r['state'] == PROBLEM for r in results): return 'Problem'
    if all(r['state'] in (WORKING, NOT_TESTED) for r in results) and any(r['part'] in ('nr', 'mfg') and r['state'] == WORKING for r in results): return 'Working'
    return None


def report_answers(results):
    answers = {r['part'] + '-result': 'Working in-game' if r['state'] == WORKING else 'Not working in-game'
               for r in results if r['part'] in ('nr', 'mfg') and r['state'] in (WORKING, PROBLEM)}
    lines = [f"Test · {r['title']}: {r['summary']}" + (' Suggested fix: ' + r['fix'] if r.get('fix') else '') for r in results]
    return answers, lines


def result_text(test):
    return '\n\n'.join(r['title'] + ' · ' + r['state'].replace('-', ' ').title() + '\n' + r['summary']
                       + ('\n' + '\n'.join(r['evidence']) if r.get('evidence') else '')
                       + ('\nSuggested fix: ' + r['fix'] if r.get('fix') else '') for r in test.get('results', []))

# A sampler is tied to one persisted session ID, including after a host restart.
_samplers = {}
_lock = threading.RLock()


def _sample_path(config, row):
    import game_notes
    key = hashlib.sha256(str(row['game']).encode()).hexdigest()[:24]
    return game_notes.root(config) / 'live' / (key + '.json')


def read_samples(config, row, session):
    import json
    import runtime_diagnostics
    try:
        data, _ = runtime_diagnostics.read_regular(_sample_path(config, row), 4 * 1024**2)
        record = json.loads(data)
        if record.get('session') == session['id'] and isinstance(record.get('samples'), list):
            return record['samples'][-SAMPLE_LIMIT:]
    except (OSError, ValueError, KeyError, TypeError): pass
    return []


def resume(config, row, session, probe):
    """Resume an open session; no settings replay or game mutation is performed."""
    import json
    import transactions as t
    if not session.get('id'): return
    key = str(_sample_path(config, row))
    with _lock:
        if key in _samplers: return
        samples = read_samples(config, row, session)
        event = threading.Event()
        def persist():
            t.atomic_file(Path(key), json.dumps({'session': session['id'], 'samples': samples}).encode(), 0o600)
        def sample():
            try: found = probe(row) or {}
            except Exception as error: found = {'state': 'unavailable', 'failure': str(error)}
            keep(samples, compact(found, time.time()))
        def run():
            ticks = 0
            try:
                while not event.wait(1):
                    sample(); ticks += 1
                    if ticks % 5 == 0: persist()
            finally: persist()
        sample(); persist()
        thread = threading.Thread(target=run, daemon=True, name='functional-test')
        _samplers[key] = (event, thread, session['id'])
        thread.start()


def stop(config, row, session):
    import transactions as t
    key = str(_sample_path(config, row))
    with _lock:
        entry = _samplers.get(key)
        if entry:
            t.need(entry[2] == session.get('id'), 'The active test identity changed. Refresh the game.')
            entry[0].set()
            entry[1].join(timeout=5)
            t.need(not entry[1].is_alive(), 'The sampler is still reading. Try Finish Test again.')
            del _samplers[key]
        return read_samples(config, row, session)


def linux_probe(config, host=None):
    """Reuse the actual Proton mailbox adapter without starting preset replay."""
    if host is not None: return lambda row: dict(host.controls.status({'row': row}),helper=linux_helper(row,host))
    from linux_overlay_host import LinuxControls
    from storage import storage
    import engine_bridge
    controls = LinuxControls(storage(config))
    controls.installations = engine_bridge.module(config).STATE_ROOT / 'targets'
    return lambda row: dict(controls.status({'row': row}),helper=linux_helper(row))


def linux_helper(row, host=None):
    """Read existing host state only; do not consume panel requests or create locks."""
    import fcntl
    from linux_overlay_host import lock_path
    report = {'running': None}
    import flatpak_host
    if flatpak_host.sandboxed():
        # The sandbox's private /tmp cannot answer whether the host helper is alive.
        report['detail']='Host helper activity is not visible from the Flatpak. Check the host overlay service.'
        return report
    try:
        descriptor = os.open(lock_path(), os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                report['running'] = False
            except BlockingIOError: report['running'] = True
        finally: os.close(descriptor)
    except FileNotFoundError: report['running'] = False
    except OSError as error: report['problem'] = str(error)
    if host is not None:
        try:
            import proton_prefix
            from linux_overlay_host import mapped_process
            prefix = proton_prefix.find_prefix(row['game'], row.get('appid'))
            for path, (_, channel) in list(host.channels.items()):
                if channel.valid and mapped_process(prefix, Path(row['game']) / row['exe'], path):
                    report.update(channel_valid=True, pid=channel.header()['pid'])
                    break
        except (OSError, ValueError, RuntimeError, KeyError): pass
    return report
