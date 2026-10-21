"""Game Details Overview facts shared by Desktop and Game Mode.

Mirrors the Windows shared Overview model: short facts the hero does not
already show, grouped on responsive rows, then the full game folder.
Developer, release, source and Steam status live in the hero instead.
"""

PROVIDERS = {
    'y4my': 'y4my Multipass',
    'dlss-unlocked': 'DLSS-Unlocked',
    'custom': 'Custom package',
    'skynizz': 'Skynizz NR + Universal MFG',
    'feeder': 'DLSS5 Feeder (NR only)',
}


def compact_facts(game):
    """[(title, value)] for short facts; omits anything unknown."""
    facts = []
    installed = bool(game.get('installed'))
    provider = game.get('runtime_provider')
    if installed and provider:
        facts.append(('Package', PROVIDERS.get(provider, str(provider))))
    if game.get('profile') and installed:
        facts.append(('Features', game['profile']))
    if 'native_dlss' in game:
        facts.append(('DLSS', 'Found in game files' if game.get('native_dlss') else 'Not found'))
    if game.get('mfg_route'):
        facts.append(('Frame generation route', game['mfg_route']))
    if installed and 'nr_enabled' in game:
        facts.append(('NR at launch', 'On' if game.get('nr_enabled') else 'Off'))
    if installed and game.get('installed_on') in ('linux', 'windows'):
        facts.append(('Installed on', game['installed_on'].title()))
    if game.get('source') != 'Steam' and game.get('library'):
        facts.append(('Library', game['library']))
    return facts


def folder(game):
    return game.get('game') or game.get('path')
