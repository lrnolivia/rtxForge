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
WINDOWS_NOTE = ('These features were installed with rtxForge on Windows. Set Up for Linux hands them to '
                'rtxForge here, so you can repair, retune or restore them from Linux.')


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


def compact_facts(game):
    """[(title, value)] for callers that don't show glyphs."""
    return [(title, value) for title, value, _icon in facts(game)]


def folder(game):
    return game.get('game') or game.get('path')
