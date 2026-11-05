"""Presentation facts derived from a game's scan or saved library record."""

PACKAGES = {
    'skynizz': 'Skynizz', 'y4my': 'y4my Multipass', 'dlss-unlocked': 'DLSS-Unlocked',
    'feeder': 'Feeder NR', 'vulkan-native': 'Native Vulkan', 'custom': 'Custom package',
}
INJECTORS = {"skynizz": "OptiScaler", "y4my": "OptiScaler", "dlss-unlocked": "OptiScaler",
             "feeder": "Feeder", "vulkan-native": "Native Vulkan"}
MODES = {'nr-only': 'NR only', 'nr-mfg': 'NR + MFG', 'mfg-only': 'MFG only'}


def cards(row):
    installed = row.get('installed') is True
    mode = row.get('feature_mode') if installed else None
    provider = row.get('runtime_provider') if installed else row.get('install_provider')
    package = PACKAGES.get(provider) or provider
    injector = row.get('injector') or INJECTORS.get(provider)
    capability = row.get('features') or {}
    available = ('nr-mfg' if capability.get('mfg') is True else 'nr-only') if capability.get('nr') is True else (
        'mfg-only' if capability.get('mfg') is True else None)
    version = row.get('installed_package_version') or row.get('installed_package_archive')
    if installed:
        features = [injector or 'Injector not identified', MODES.get(mode)]
    elif row.get('installed') is False:
        features = ['Not installed', injector, MODES.get(available) if not row.get('blocked') else None]
    else:
        features = ['Not checked']

    compat = row.get('compat') or {}
    verdict = compat.get('verdict')
    out = [('Features', features),
           ('Compatibility', [verdict, 'rtxForge list' if compat.get('source') == 'list' else 'Your result']
            if verdict else ['No compatibility result'])]
    if mode in ('nr-only', 'nr-mfg') or installed and provider == 'feeder':
        enabled = row.get('nr_enabled')
        out.append(('Neural rendering', [package, f'Package {version}' if version else 'Package version unavailable',
            'Enabled' if enabled is True else 'Disabled' if enabled is False else 'Setting not recorded']))
    if installed and mode in ('nr-mfg', 'mfg-only'):
        ratio = row.get('mfg_multiplier')
        route = row.get('mfg_route')
        if row.get('mfg_enabled') is False or ratio == 0:
            setting = 'Off'
        elif row.get('dynamic_mfg') == 1:
            setting = f'Dynamic · up to {ratio}×' if type(ratio) is int and 2 <= ratio <= 6 else 'Dynamic'
        elif type(ratio) is int and 2 <= ratio <= 6:
            setting = f'{ratio}×'
        elif ratio == 'auto':
            setting = 'Automatic'
        else:
            setting = 'Setting not recorded'
        out.append(('Multi-Frame Generation', [route if route and route != 'Not installed' else package,
            f'Package {version}' if version and (not route or version not in route) else None, setting]))
    drift = (row.get('feeder_drift') or row.get('package_drift')) if installed else None
    if isinstance(drift, dict) and drift.get('summary'):
        # A changed managed file: still installed, one Repair away from matching its record.
        out.append(('Files', ['Repair recommended', drift['summary']]))
    return [dict(title=title, values=[str(value) for value in values if value]) for title, values in out]


def installed_details(row, engine=None):
    """Read the package version from the recorded install beside its executable."""
    from pathlib import Path
    import transactions as t
    import cross_os
    result = dict(row)
    try:
        root = t.safe(row['game'])
        exe = t.safe(root / t.relative(row['exe']))
        if not exe.is_file():
            return result
        directory = exe.parent
        marker = t.safe(directory / cross_os.MARKER)
        if marker.is_file() and marker.stat().st_size <= 1024**2:
            receipt = cross_os.read(directory) or {}
            provider = receipt.get('provider') or {}
            if isinstance(provider, dict) and provider.get('id') == row.get('runtime_provider'):
                result['installed_package_version'] = provider.get('tag') or provider.get('version') or result.get('installed_package_version')
        if engine is not None and row.get('installed') is True and not result.get('installed_package_version'):
            try:
                current = (engine.load_baseline(directory, readonly=True) or {}).get('current') or {}
                archive = current.get('archive') or {}
                release = archive.get('release') or {}
                if current.get('provider_id') == row.get('runtime_provider'):
                    result['installed_package_version'] = release.get('tag') or release.get('version')
                    result['installed_package_archive'] = archive.get('name')
            except (engine.Stop, OSError, ValueError):
                pass
    except (KeyError, OSError, ValueError, TypeError, t.Refusal):
        pass
    return result


def installed_extras(game):
    """Read bounded evidence next to the selected executable; never scan the game tree."""
    from itertools import islice
    from pathlib import Path
    import transactions as t
    import renodx_hdr
    import reshade_import

    def entries(directory, limit):
        try:
            path = t.safe(directory)
            if path.is_dir():
                yield from islice(path.iterdir(), limit)
        except (t.Refusal, OSError):
            return

    def read(path, limit):
        try:
            path = t.safe(path)
            if path.is_file() and path.stat().st_size <= limit:
                with path.open('rb') as stream:
                    data = stream.read(limit + 1)
                if len(data) <= limit:
                    return data
        except (t.Refusal, OSError):
            pass
        return b''

    try:
        root = t.safe(game['game'])
        exe = t.safe(root / t.relative(game['exe']))
        if not exe.is_file():
            return []
    except (KeyError, TypeError, t.Refusal, OSError):
        return []
    directory = exe.parent
    items = list(entries(directory, 512))
    names = {item.name.casefold(): item for item in items}
    hosts = (*renodx_hdr.PROXIES, 'reshade64.dll', 'reshade32.dll', 'reshade.dll')
    reshade = any(reshade_import._is_reshade(read(names[name], 32 * 1024**2))
                  for name in hosts if name in names)
    addons = []
    for item in items:
        if item.suffix.lower() not in ('.addon64', '.addon32', '.addon') or item.name.casefold().startswith('rtxforge'):
            continue
        try:
            if t.safe(item).is_file():
                addons.append(item)
        except (t.Refusal, OSError):
            continue
    hdr_addons = {item for item in addons if 'renodx' in item.name.casefold()}
    try:
        _, _, receipt = renodx_hdr._location(game)
        if receipt.is_file() and receipt.stat().st_size <= 1024**2:
            record = renodx_hdr._record(root, receipt, directory)
            for name in record['files']:
                if Path(name).suffix.lower() in ('.addon64', '.addon32'):
                    target = t.safe(root / t.relative(name))
                    if target.is_file():
                        hdr_addons.add(target)
    except (t.Refusal, OSError, ValueError, KeyError, TypeError):
        pass
    shader_root = names.get('reshade-shaders', directory / 'reshade-shaders')
    shaders = any(item.suffix.lower() == '.fx' and not item.is_symlink() and item.is_file()
                  for child in entries(shader_root, 32) if child.name.casefold() == 'shaders'
                  for item in entries(child, 128))
    presets = False
    preset_dirs = [item for item in items if item.name.casefold() == 'presets']
    candidates = (*items, *(item for path in preset_dirs for item in entries(path, 64)))
    for item in islice((p for p in candidates if p.suffix.lower() == '.ini'
                        and p.name.casefold() != 'reshade.ini'), 32):
        try:
            if reshade_import._preset_ini(read(item, 256 * 1024)):
                presets = True
                break
        except UnicodeError:
            pass
    return [label for present, label in (
        (bool(hdr_addons), 'RenoDX'), (reshade, 'ReShade'), (shaders, 'Filters'),
        (presets, 'Presets'), (any(item not in hdr_addons for item in addons), 'Add-ons'),
    ) if present]


def compact_facts(game):
    """[(title, value)] for callers that don't show glyphs."""
    return [(title, value) for title, value, _icon in facts(game)]


def folder(game):
    return game.get('game') or game.get('path')


def installed_oses(game):
    """Which rtxForge installs this game is set up for: ['windows'], ['linux'] or both."""
    if not game.get('installed'):
        return []
    oses = [name for name in game.get('installed_oses') or [] if name in ('windows', 'linux')]
    if not oses and game.get('installed_on') in ('windows', 'linux'):
        oses = [game['installed_on']]
    return oses


def os_tooltip(oses):
    names = ' and '.join(name.title() for name in oses)
    return 'Installed with rtxForge on ' + names if len(oses) == 1 else 'Set up for ' + names


def inspect(row, engine=None):
    return dict(cards=cards(installed_details(row, engine)), extras=installed_extras(row))
