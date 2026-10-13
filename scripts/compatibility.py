"""Small, auditable per-game MFG route policy.

Native Streamline DLSS-G is the default. Rules here exist only for titles with
reproduced route-specific failures; they never change game-native DLSS/SL DLLs.
"""
import re

DEFAULT_ROUTE = 'native-streamline'

ROUTES = {
    'native-streamline': {
        'id': 'native-streamline-dlssg-ada-v5',
        'label': 'Native Streamline DLSS-G',
        'fg_input': 'dlssg',
        'fg_output': 'dlssg',
        'nvngx_replacement': 'none',
        'provider': 'y4my-native-dlssg',
    },

}

# Only reproduced exceptions belong here. Keep matching conservative.
_RULES = [
    {
        'route': 'native-streamline',
        'patterns': (r'\bcyberpunk 2077\b', r'\bcyberpunk2077\b'),
        'reason': 'Native Streamline DLSS-G reproduced with normal performance; Enabler MFG reproduced severe performance loss.',
    },
]


# Exact game-side proxy DLLs that are known to coexist with RTXForge.
#
# These are NOT adopted, overwritten, or treated as OptiScaler.
# Matching is intentionally conservative: game identity + filename + SHA256.
_PRESERVED_PROXY_RULES = [
    {
        'patterns': (
            r'\bforza horizon 6\b',
            r'\bforzahorizon6\b',
        ),
        'filename': 'winmm.dll',
        'sha256': 'bfe362f716b95b830206a1b986e2e94735691e8d7dd71f9148f7b9cfd3c5f435',
        'reason': (
            'Known Forza Horizon 6 game-side winmm.dll; preserve it and '
            'use a separate RTXForge proxy.'
        ),
    },
]


def preserved_proxy_reason(target, relpath, sha256):
    """Return why an exact known game-side proxy should be preserved."""
    text = ' '.join(
        str(target.get(k, ''))
        for k in ('name', 'game', 'exe')
    ).casefold()

    compact = re.sub(r'[^a-z0-9]+', '', text)
    searchable = text + ' ' + compact

    filename = str(relpath).replace('\\', '/').rsplit('/', 1)[-1].casefold()
    digest = str(sha256).casefold()

    for rule in _PRESERVED_PROXY_RULES:
        if filename != rule['filename']:
            continue
        if digest != rule['sha256']:
            continue
        if not any(re.search(pattern, searchable, re.I)
                   for pattern in rule['patterns']):
            continue
        return rule['reason']

    return None



def route_for(target):
    """Return route metadata for a target without mutating it."""
    text = ' '.join(str(target.get(k, '')) for k in ('name', 'game', 'exe')).casefold()
    compact = re.sub(r'[^a-z0-9]+', '', text)
    searchable = text + ' ' + compact
    for rule in _RULES:
        if any(re.search(pattern, searchable, re.I) for pattern in rule['patterns']):
            return {**ROUTES[rule['route']], 'key': rule['route'], 'reason': rule['reason'], 'profiled': True}
    route = ROUTES[DEFAULT_ROUTE]
    return {**route, 'key': DEFAULT_ROUTE, 'reason': 'Default RTXForge MFG route.', 'profiled': False}
