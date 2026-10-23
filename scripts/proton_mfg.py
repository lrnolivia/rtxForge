"""Universal MFG Unlocker 1.6.1 under Proton: review, gate and post-install checks.

The Windows route (universal_mfg_provider) is reused byte for byte: the pinned
DLL becomes OptiScaler/plugins/MFGUnlocker.asi beside the Skynizz bridge, with
[Plugins] LoadAsiPlugins=true and the bridge's integrated Ada unlock off. The
game's own Streamline DLSS Frame Generation stays the FG path. The engine
already places, backs up and restores those files (install_target /
restore_target); this module adds what only Linux needs:

* a per-game gate: the experimental "Skynizz on Proton" opt-in, the Universal
  component (the only MFG owner offered on Linux), and every Proton
  prerequisite from proton_stack. Anything missing refuses with reason codes.
* the Proton DLL override for the bridge's proxy: WINEDLLOVERRIDES in Steam's
  launch options with Steam closed, or the prefix's DllOverrides with Steam
  open (engine_bridge.steam_open_route / proton_prefix).
* singular MFG ownership: refuse any competing unlock in the game folder or
  the INI before install, and check it again after install (verify()).
* runtime_report(): what the plugin itself wrote on its last run. It is shown
  as an observation; a human-confirmed real session is the only evidence
  (proton_stack.record_evidence).

Nothing here launches a game. RTX 40 is the only GPU prepared on Linux.
"""
from pathlib import Path
import hashlib
import json

import transactions as t
import proton_stack
import universal_mfg_provider as universal

REASONS = {
    'opt-in-required': 'Turn on Skynizz on Proton (experimental) in Settings to try this under Proton.',
    'component-unsupported-linux': 'Only the Universal MFG Unlocker is offered under Proton. Choose Universal MFG.',
    'mode-unsupported': 'Choose NR + MFG, MFG Only or NR Only.',
    'competing-unlock': 'Another MFG unlock is installed in this game. Remove it first so only one component owns MFG.',
    'competing-unlock-ini': 'The OptiScaler settings still turn on the integrated Ada unlock. Repair the game so the plugin owns MFG.',
    'plugin-missing': 'The MFG Unlocker plugin is missing. Repair the game.',
    'plugin-changed': 'The MFG Unlocker plugin changed since install. Repair the game.',
    'plugin-not-loaded': 'OptiScaler is not set to load plugins. Repair the game.',
}
# Files that mean another component owns MFG in this folder.
COMPETING_FILES = ('renodx-mfgunlock.addon64', 'dlss-enabler.dll', 'dlss-enabler-upscaler.dll',
                   'dlssg_to_fsr3_amd_is_better.dll', 'nvngx-wrapper.dll')
LABEL = 'Experimental under Proton · Linux runtime not yet verified'


def _refuse(code, detail=''):
    raise t.Refusal(REASONS[code] + (' (' + detail + ')' if detail else ''))


def competing(target, managed=()):
    """Names in the game folder that would make MFG ownership ambiguous."""
    target = Path(target)
    managed = {Path(name).as_posix().casefold() for name in managed}
    found = []
    for path in sorted(target.iterdir()) if target.is_dir() else ():
        name = path.name.casefold()
        if name in managed:
            continue
        if name.startswith('rtxmfg-') and name.endswith(('.log', '.status.json')):
            continue  # the plugin's own run reports outlive a restore
        if name in COMPETING_FILES or name.startswith(universal.FOREIGN_PREFIXES):
            found.append(path.name)
    plugin = target / universal.PLUGIN
    if plugin.exists() and universal.PLUGIN.casefold() not in managed:
        found.append(universal.PLUGIN)
    return found


def gate(settings, mode, mfg_provider, prefix, native_dlssg=None, launch_options='',
         driver_root=None, driver_dirs=None):
    """Per-game permission for a fresh Skynizz (+ Universal MFG) install under Proton.

    Returns the proton_stack report with 'opt_in' added; raises a Refusal
    naming every missing prerequisite otherwise.
    """
    if settings.get('skynizz_proton') is not True:
        _refuse('opt-in-required')
    if mode not in ('nr-mfg', 'mfg-only', 'nr-only'):
        _refuse('mode-unsupported')
    if mode != 'nr-only' and mfg_provider != 'universal':
        _refuse('component-unsupported-linux')
    report = proton_stack.detect(prefix, mode, launch_options, native_dlssg,
                                 driver_root=driver_root, driver_dirs=driver_dirs)
    if not report['prerequisites_met']:
        raise t.Refusal(' '.join(dict.fromkeys(proton_stack.REASONS[code] for code in report['reasons'])))
    report['opt_in'] = True
    report['component'] = universal.pinned() if mode != 'nr-only' else None
    report['label'] = LABEL
    return report


def review(target, prefix_route, proxy, mode, report, managed=()):
    """User-facing review lines for one game, plus technical details kept separate."""
    component = report.get('component')
    found = competing(target, managed)
    if found and mode != 'nr-only':
        _refuse('competing-unlock', ', '.join(found))
    override = Path(proxy).stem.lower() if proxy else 'dxgi'
    lines = [LABEL,
             ('NR + MFG' if mode == 'nr-mfg' else 'MFG Only' if mode == 'mfg-only' else 'NR Only')
             + ' · Skynizz bridge' + (' + Universal MFG ' + component['version'] if component else ''),
             f"Loads through {override}.dll · " + ("Proton setting saved in this game's prefix" if prefix_route
                                                  else 'Proton setting saved in Steam launch options')]
    details = {
        'files': ([universal.PLUGIN] + ['OptiScaler/licenses/' + name for name in universal.NOTICES.values()]) if component else [],
        'ini': {'Plugins': {'LoadAsiPlugins': 'true'},
                'DLSSG': {'AdaMfgUnlock': 'false', 'AdaBlackwellKernels': 'false', 'AmpereMfgUnlock': 'false'},
                'FrameGen': {'FGOutput': 'nofg'}} if component else {},
        'override': {override: 'n,b'},
        'plugin_sha256': component['dll']['sha256'] if component else None,
        'proton': report.get('tool'), 'components': report.get('components'), 'gpu': (report.get('gpu') or {}).get('model'),
    }
    return {'lines': lines, 'details': details}


def _ini(text):
    parser = t.ini(text)
    return {(section.casefold(), key.casefold()): value.strip().casefold()
            for section in parser.sections() for key, value in parser.items(section)}


def verify(target, baseline):
    """After install/repair: exact plugin bytes, plugin loading on, single MFG owner. Returns reason codes."""
    target = Path(target)
    current = (baseline or {}).get('current') or {}
    component = ((current.get('archive') or {}).get('release') or {}).get('mfg_component')
    if not component or component.get('id') != universal.ID:
        return []
    reasons = []
    plugin = target / universal.PLUGIN
    if not plugin.is_file() or plugin.is_symlink():
        reasons.append('plugin-missing')
    else:
        with open(plugin, 'rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') \
                else hashlib.sha256(handle.read()).hexdigest()
        if digest != component['dll']['sha256']:
            reasons.append('plugin-changed')
    ini = target / 'OptiScaler.ini'
    values = _ini(ini.read_text(encoding='utf-8-sig')) if ini.is_file() else {}
    if values.get(('plugins', 'loadasiplugins')) != 'true':
        reasons.append('plugin-not-loaded')
    if any(values.get(('dlssg', key)) == 'true' for key in ('adamfgunlock', 'adablackwellkernels', 'ampermfgunlock')):
        reasons.append('competing-unlock-ini')
    if competing(target, (baseline or {}).get('managed_paths') or ()):
        reasons.append('competing-unlock')
    return reasons


def runtime_report(target):
    """What the plugin wrote on its last run (RTXMFG-Universal.status.json), as an observation only."""
    path = Path(target) / universal.STATUS
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 ** 2:
            return None
        status = json.loads(path.read_text(encoding='utf-8-sig'))
        modified = path.stat().st_mtime
    except (OSError, ValueError):
        return None
    if not isinstance(status, dict):
        return None
    return {'observed': True, 'verified': False, 'modified': modified,
            'dynamic_supported': universal.dynamic_support(target),
            'keys': sorted(str(key) for key in status)[:64],
            'note': 'Written by the plugin during a game session. Confirm in game before recording it as evidence.'}
