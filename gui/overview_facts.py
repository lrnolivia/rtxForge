"""Game Details Overview facts shared by Desktop and Game Mode.

Mirrors Windows GameOverview.Facts (windows/RtxForge.Windows/Models/
GameOverview.cs): the feature package, a non-Steam library, the DLSS file
version and Feeder NR state, each with a glyph, then the full game folder.
Developer, release, source and test status live in the hero instead.
"""

PACKAGES = {
    'skynizz': 'Skynizz',
    'y4my': 'y4my Multipass',
    'dlss-unlocked': 'DLSS-Unlocked',
    'feeder': 'Feeder NR',
    'custom': 'Custom package',
    'vulkan-native': 'Vulkan NR + Universal MFG',
}

# Windows Segoe glyph -> closest Adwaita symbolic icon.
ICONS = {
    'package': 'computer-symbolic',          # E7F4
    'library': 'input-gaming-symbolic',      # E7FC
    'dlss': 'x-office-document-symbolic',    # E8A5
    'nr': 'rtx-sparkle-symbolic',            # E9E9
    'folder': 'folder-symbolic',             # E838
}

ADOPTION_NOTE = ('This package is installed. Adopt its current setup or back it up and clean install '
                 'from rtxForge.')
OFFLINE_NOTE = ('Launch here to use the reviewed offline route. The normal Steam launch is unchanged. '
                'Online play requires removing these feature files. Adoption restore returns the previous modded setup.')
# Linux has no launch-offline action yet: the Windows route starts the executable directly, which Proton does not.
LINUX_OFFLINE_NOTE = ('These features work offline only. Start the game in its offline mode as you do now. '
                      'Online play requires removing these feature files. Adoption restore returns the previous modded setup.')
OFFLINE_ADOPTION_NOTE = ('This game uses anti-cheat. Its verified offline-only route lets rtxForge adopt and manage '
                         'the setup already here. Play it offline; online play requires removing these feature files.')
WINDOWS_NOTE = ('These features were installed with rtxForge on Windows. Adapt to Linux sets this game up for '
                'Proton outside the game folder; the Windows install is not touched, and Remove Linux Setup undoes it.')


def facts(game):
    """[(title, value, icon)] in Windows order; omits anything unknown."""
    installed = bool(game.get('installed'))
    adoption = bool(game.get('adoption_available'))
    provider = game.get('runtime_provider')
    package = 'Not installed' if not installed and not adoption else PACKAGES.get(provider, 'Installed features')
    out = [('Feature package', package, ICONS['package'])]
    library = game.get('library')
    if library and library not in ('Steam', 'Folder') and game.get('source') != 'Steam':
        out.append(('Library', str(library), ICONS['library']))
    if game.get('dlss_version'):
        out.append(('DLSS file version', str(game['dlss_version']), ICONS['dlss']))
    if provider == 'feeder' and installed:
        version = (game.get('nr_runtime') or {}).get('version') if isinstance(game.get('nr_runtime'), dict) else None
        enabled = game.get('nr_enabled')
        state = ('Enabled in saved settings' if enabled else 'Disabled in saved settings') if isinstance(enabled, bool) \
            else 'Saved state unavailable'
        out.append(('Neural rendering', (f'Model {version}\n' if version else '') + state + ' · NR only', ICONS['nr']))
    elif game.get('install_provider') == 'feeder' and game.get('feeder_available'):
        out.append(('Available features', 'Feeder NR · NR only', ICONS['nr']))
    return out


def overview_cards(game, verdict=None):
    """Three stable cards for Game Details, including when no result is recorded."""
    rows = facts(game)
    compatibility = 'No compatibility result'
    if verdict:
        source = 'rtxForge list' if verdict['source'] == 'list' else 'your result'
        compatibility = f"{verdict['verdict']} · {source}"
    feature = next((row for row in rows if row[0] in ('Neural rendering', 'Available features')), None)
    title, value, icon = feature or (
        'Features', (game.get('profile') or 'Installed') if game.get('installed') else 'Not installed', ICONS['nr'],
    )
    if game.get('runtime_provider') != 'feeder' and game.get('dlss_version'):
        value += '\nDLSS ' + str(game['dlss_version'])
    package_title, package, package_icon = rows[0]
    if game.get('installed'):
        version = game.get('installed_package_version') or game.get('installed_package_archive')
        package = f'{package} · {version}' if version else f'{package} · version not recorded'
        model = game.get('nr_runtime')
        if (game.get('feature_mode') in ('nr-only', 'nr-mfg')
                and game.get('runtime_provider') != 'feeder'
                and isinstance(model, dict) and model.get('version')):
            value += '\nNR model ' + str(model['version'])
    elif game.get('adoption_available'):
        package += ' · adoption available'
    cards = [(package_title, package, package_icon), ('Compatibility', compatibility, 'emblem-ok-symbolic'),
             (title, value, icon)]
    if game.get('installed') and game.get('feature_mode') in ('nr-mfg', 'mfg-only'):
        ratio = game.get('mfg_multiplier')
        if game.get('mfg_enabled') is False or (type(ratio) is int and ratio == 0):
            mfg = 'Off'
        elif game.get('dynamic_mfg') == 1:
            mfg = 'Dynamic'
        elif type(ratio) is int and 2 <= ratio <= 6:
            mfg = f'{ratio}×'
        elif ratio == 'auto':
            mfg = 'Auto'
        else:
            mfg = 'Saved setting unavailable'
        cards.append(('Multi-Frame Generation', mfg, 'video-display-symbolic'))
    return cards


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
