"""Read-only package assessment, independent of installed package ownership.

Installation still performs the provider's full review, including architecture,
conflicting hooks, model and original-file recovery requirements.
"""
from pathlib import Path
import feeder_provider as feeder
import feeder_legacy
import transactions as t


def assess(e, row):
    if not row.get('exe') or row.get('executable_error'):
        return []
    exe = Path(row['game']) / row['exe']
    apis = feeder.graphics_apis(e, exe)
    machine = feeder_legacy.machine(exe)
    feeder_owned = row.get('runtime_provider') == 'feeder' and row.get('installed')
    native = bool(machine == 0x8664 and not feeder_owned and row.get('native_dlss') and (not apis or 'd3d12' in apis))
    baseline = e.load_baseline(exe.parent, readonly=True)
    native_owned = bool(baseline and baseline.get('status') == 'active')
    legacy = feeder_legacy.route(e, row)
    feed = bool(feeder_owned or legacy or machine == 0x8664 and apis & {'d3d11', 'd3d12'})
    if not feeder_owned and apis == {'d3d12'} and row.get('native_dlss'):
        feed = False
    candidates = []
    def add(key, name, compatible, ready, reason, nr, mfg):
        if compatible and row.get('installed') and row.get('managed') and row.get('runtime_provider') not in (None, key):
            ready = False
            reason = 'Restore the installed package before switching to ' + name + '.'
        candidates.append(dict(id=key, name=name, compatible=bool(compatible), ready=bool(ready),
                               reason=reason, features={'nr':bool(nr), 'mfg':bool(mfg)}))
    add('skynizz', 'Skynizz', native, native,
        ('Native DLSS route' if apis else 'Native DLSS files found; renderer validation pending.') if native
        else 'Requires a DirectX 12 game with native DLSS; DirectX 11 alone does not qualify.',
        native, native and bool(row.get('native_dlssg')))
    for key, name in (('y4my', 'y4my Multipass'), ('dlss-unlocked', 'DLSS-Unlocked')):
        available = native and bool(row.get('native_dlssg'))
        add(key, name, available, available,
            'Native DLSS + Frame Generation route' if available else 'Requires native DLSS and DLSS Frame Generation on a supported renderer.',
            available, available)
    ready = False
    reason = 'Requires a supported DirectX 9, 10, 11 or 12 executable.'
    if feed:
        try:
            feeder.eligible(e, row, existing=bool(feeder_owned), check_running=False)
            ready = True
            reason = feeder.route_note(e, row)
        except (t.Refusal, getattr(e, 'Stop', RuntimeError), OSError, ValueError) as error:
            reason = str(error)
        if native_owned:
            reason = 'Restore the installed OptiScaler package first, then install Feeder NR.'
    add('feeder', 'Feeder NR', feed, ready, reason, feed, False)
    vulkan = row.get('vulkan_available') is True
    add('vulkan-native', 'Vulkan', vulkan, vulkan,
        'Confirmed Vulkan route' if vulkan else 'No confirmed Vulkan route for this executable.', vulkan, vulkan)
    return candidates


def decorate(e, rows):
    for row in rows:
        try:
            candidates = assess(e, row)
            row['provider_candidates'] = candidates
            native = next((p for p in candidates if p['id']=='skynizz'), None)
            feed = next((p for p in candidates if p['id']=='feeder'), None)
            preferred = next((p for p in candidates if p['compatible'] and p['ready']), None)
            if preferred:
                row['recommended_provider'] = preferred['id']
            if (feed and feed['compatible'] and not feed['ready'] and native and not native['compatible']
                    and row.get('managed') and row.get('runtime_provider') != 'feeder'):
                row['feeder_restore_first'] = True
                row['recommended_provider'] = 'feeder'
                row['blocked'] = feed['reason']
                row['package_blocked'] = row['skynizz_blocked'] = row['blocked']
            elif feed and feed['ready'] and native and not native['compatible'] and not row.get('installed'):
                row.update(install_provider='feeder', feeder_available=True, blocked='',
                           nr_route_note=feed['reason'], features={'nr':True, 'mfg':False})
                row['package_blocked'] = row['skynizz_blocked'] = ''
        except (t.Refusal, getattr(e, 'Stop', RuntimeError), OSError, ValueError, KeyError):
            row['provider_candidates'] = []
    return rows
