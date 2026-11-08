"""One review plan for install, repair, adopt, uninstall, reset and apply.

Windows Desktop, Game Mode on Windows and Game Mode on Linux plan a reviewed
operation the same way, from here:

  route()    which route each game takes: Adoption, the Vulkan package,
             Feeder NR, or a DLSS package (each game may choose its own);
  batches()  consecutive games on the same route, in name order, so one
             prepare call shares its verified payload and model checks;
  prefetch() the downloads those routes need, fetched before any game is
             checked, so the review shows one "Downloading packages/files"
             phase instead of downloads hidden inside each check;
  offers     opt-in second reviews for games that support only NR or only
             MFG. Each is its own review over exactly its games, applied
             only when chosen.

plan() runs a review with a host's own prepare and discard; ReviewedRoutes
keeps the result behind one token for hosts that execute it as a whole.
Every file plan and write stays in each host's existing prepare and execute.
"""
from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

# Packages a game can choose for itself (Settings.GamePackageChoices on Windows).
GAME_PACKAGES = ('skynizz', 'dlss-unlocked')

# Second-review offers when a game supports only part of NR + MFG (reason code -> user text).
REASONS = {
    'feeder-nr-only': 'Feeder provides neural rendering. Frame generation is unavailable for this route.',
    'no-native-dlssg': 'Use DirectX 12 and enable DLSS in the game for NR. Native frame generation is unavailable.',
    'nr-runtime-unavailable': 'Frame generation is supported. Neural rendering could not be prepared with the selected NR runtime.',
}
NR_MISSING = ('nr runtime', 'nr model', 'nvngx_dlssnr')


def identity(path):
    return os.path.normcase(str(Path(path).resolve()))


def uses_feeder(row):
    """An installed Feeder setup, or a fresh target the scan admitted to Feeder NR."""
    return row.get('runtime_provider') == 'feeder' or (row.get('install_provider') == 'feeder' and row.get('feeder_available') is True)


def uses_vulkan(row):
    """A Vulkan installation, or a confirmed Vulkan game the scan routes to the bundled Vulkan package."""
    return (row.get('runtime_provider') == 'vulkan-native' and bool(row.get('installed'))
            or row.get('install_provider') == 'vulkan-native' and row.get('vulkan_available') is True)


def package_for(row, operation, settings):
    """The DLSS package a game installs or repairs with: a repair keeps the installed one."""
    default = settings.get('runtime_provider') or 'y4my'
    if uses_vulkan(row) and row.get('installed'):
        return 'vulkan-native'
    if uses_feeder(row):
        return default
    if operation == 'repair' and row.get('installed') and row.get('runtime_provider') in GAME_PACKAGES:
        return row['runtime_provider']
    choices = settings.get('game_packages') or {}
    chosen = choices.get(row.get('game'))
    if chosen is None and row.get('game'):
        key = identity(row['game'])
        chosen = next((value for path, value in choices.items() if identity(path) == key), None)
    return chosen if chosen in GAME_PACKAGES else default


def route(row, operation, mode, settings):
    """'adopt', 'vulkan-native', 'feeder' or a DLSS package id."""
    if operation == 'install' and row.get('adoption_available'):
        return 'adopt'
    if uses_vulkan(row) and (row.get('installed') or mode != 'nr-only'):
        return 'vulkan-native'
    if uses_feeder(row):
        return 'feeder'
    if operation in ('install', 'repair'):
        return package_for(row, operation, settings)
    return settings.get('runtime_provider') or 'y4my'


def step(route_name, operation, settings):
    """(operation, runtime_provider) a route prepares with. Feeder and Adoption keep the
    selected package setting: the engine routes a selection of only Feeder games itself."""
    provider = (settings.get('runtime_provider') or 'y4my') if route_name in ('feeder', 'adopt') else route_name
    if route_name == 'adopt':
        return 'adopt', provider
    # Applying presets: Feeder saves them to the game's ReShade.ini ('apply'); the
    # DLSS packages re-apply them with the engine's preset reset ('reset'), never a reinstall.
    if operation == 'apply' and route_name != 'feeder':
        return 'reset', provider
    return operation, provider


def batches(rows, operation, mode, settings):
    """[(route, [rows])], consecutive games on the same route, in name order."""
    groups = []
    for row in sorted(rows, key=lambda item: str(item.get('name', '')).casefold()):
        name = route(row, operation, mode, settings)
        if groups and groups[-1][0] == name:
            groups[-1][1].append(row)
        else:
            groups.append((name, [row]))
    return groups


def prefetch(groups, operation, mode, settings):
    """Download batches for the routes an install or repair takes (Adoption downloads nothing)."""
    if operation not in ('install', 'repair'):
        return []
    seen = []
    for name, _ in groups:
        if name != 'adopt' and name not in seen:
            seen.append(name)
    return [{'mode': mode, 'settings': dict(settings, runtime_provider=name)} for name in seen]


def offer_groups(operation, mode, provider, rows, ready, blocked):
    """[(reason_code, subset_mode, rows)] to review again for only NR or only MFG.

    ready is the identities of games the main review admitted; blocked maps a
    game's name to its refusal. Hard blockers (anti-cheat, no executable) are
    never offered."""
    if operation != 'install' or mode not in ('nr-mfg', 'nr-only'):
        return []
    candidates = [row for row in rows if identity(row['game']) not in ready and not row.get('anti_cheat') and row.get('exe')]
    groups = [('feeder-nr-only', 'nr-only', [row for row in candidates if uses_feeder(row)])]
    if mode == 'nr-mfg' and provider == 'skynizz':
        groups.append(('no-native-dlssg', 'nr-only', [row for row in candidates if not uses_feeder(row)
                                                      and row.get('native_dlss') and not row.get('native_dlssg')]))
        missing = lambda reason: any(word in str(reason or '').casefold() for word in NR_MISSING)
        groups.append(('nr-runtime-unavailable', 'mfg-only', [row for row in candidates if not uses_feeder(row)
                                                              and row.get('native_dlssg') and missing(blocked.get(row.get('name')))]))
    return [group for group in groups if group[2]]


def plan(prepare, discard, rows, operation, mode, settings, prefetch_files=None):
    """Prepare a reviewed operation route by route.

    prepare(rows, mode, operation, settings) returns a host review: {'token',
    'rows', 'blocked', 'warnings', 'trust'}; discard(tokens) releases ones not
    kept. Returns {'steps': [...], 'offers': [...], 'blocked': [...], 'warnings': [...]},
    each step and offer carrying its route, provider and host review."""
    groups = batches(rows, operation, mode, settings)
    downloads = prefetch(groups, operation, mode, settings)
    if downloads and prefetch_files:
        prefetch_files(downloads)
    steps, offers, blocked, warnings, tokens = [], [], [], [], []

    def review(group, selected_mode, selected_operation, provider, subset):
        values = dict(settings, runtime_provider=provider, prefer_bundled_nr_only=subset and selected_mode == 'nr-only')
        result = prepare(group, selected_mode, selected_operation, values)
        tokens.append(result['token'])
        return result

    def admitted(result, group):
        paths = {identity(row['game']) for row in result.get('rows', []) if row.get('game')}
        if not paths:
            names = {row.get('name') for row in result.get('rows', [])}
            paths = {identity(row['game']) for row in group if row.get('name') in names}
        return paths

    try:
        for name, group in groups:
            selected_operation, provider = step(name, operation, settings)
            result = review(group, mode, selected_operation, provider, False)
            ready = admitted(result, group)
            entry = {'route': name, 'operation': selected_operation, 'provider': provider, 'mode': mode, 'review': result}
            warnings += result.get('warnings', [])
            refused = list(result.get('blocked', []))
            if result.get('rows'):
                if selected_operation == 'install' and mode == 'nr-mfg' and name == 'feeder':
                    offers.append(dict(entry, code='feeder-nr-only', nr=True, mfg=False, reason=REASONS['feeder-nr-only']))
                else:
                    steps.append(entry)
            offered = set()
            reasons = {item.get('name'): item.get('reason', '') for item in refused}
            for code, subset_mode, subset in offer_groups(selected_operation, mode, provider, group, ready, reasons):
                subset = [row for row in subset if identity(row['game']) not in offered]
                if not subset:
                    continue
                try:
                    extra = review(subset, subset_mode, selected_operation, provider, subset_mode == 'nr-only')
                except (ValueError, OSError, RuntimeError):
                    continue  # keep the original refusal; no partial recipe was admitted
                # A Feeder game's own setup problem says more than the main route's refusal.
                feeder_failures = {item.get('name'): item for item in extra.get('blocked', [])
                                   if any(uses_feeder(row) and row.get('name') == item.get('name') for row in subset)}
                refused = [feeder_failures.get(item.get('name'), item) for item in refused]
                if extra.get('rows'):
                    offers.append({'route': name, 'operation': selected_operation, 'provider': provider, 'mode': subset_mode,
                                   'review': extra, 'code': code, 'nr': subset_mode != 'mfg-only',
                                   'mfg': subset_mode != 'nr-only', 'reason': REASONS[code]})
                    warnings += extra.get('warnings', [])
                    offered |= admitted(extra, subset)
            offered_names = {row.get('name') for row in group if identity(row['game']) in offered}
            blocked += [item for item in refused if item.get('name') not in offered_names]
        kept = {entry['review']['token'] for entry in steps + offers}
        unused = [token for token in tokens if token not in kept]
        if unused:
            discard(unused)
    except Exception:
        if tokens:
            discard(tokens)
        raise
    return {'steps': steps, 'offers': offers, 'blocked': blocked, 'warnings': warnings}


class ReviewedRoutes:
    """A plan behind one token: executed as a whole, its optional offers only when chosen."""

    DEFAULT_KEYS = {'nr_strength', 'sharpening_strength', 'mfg_multiplier', 'dynamic_mfg',
                    'mfg_saved_mode', 'mfg_saved_multiplier', 'nr_on_launch', 'feature_controls'}

    def __init__(self, prepare, execute, cancel, discard, settings, defaults=None, prefetch=None):
        self._prepare, self._execute = prepare, execute
        self._cancel, self._discard, self._settings = cancel, discard, settings
        self._defaults, self._prefetch = defaults, prefetch
        self.reviews, self.running = {}, {}
        self._lock = threading.RLock()
        self._closing = False

    def _open(self):
        with self._lock:
            if self._closing:
                raise ValueError('The application is closing.')

    def prepare(self, params):
        self._open()
        rows = params.get('rows') or []
        defaults = params.get('defaults')
        if defaults is not None:
            if not self._defaults or not isinstance(defaults, dict) or not defaults or set(defaults) - self.DEFAULT_KEYS:
                raise ValueError('Choose supported library tuning defaults.')
        if not rows and defaults is None:
            raise ValueError('Choose one or more exact installations.')
        operation, mode = params['operation'], params['mode']
        settings = self._settings() | (params.get('settings') or {})

        def prepare(group, selected_mode, selected_operation, values):
            return self._prepare({'rows': group, 'mode': selected_mode, 'operation': selected_operation,
                                  'settings': values, 'save_defaults': False})
        prefetch_files = (lambda downloads: self._prefetch({'batches': downloads, 'manage_dlss_files': settings.get('manage_dlss_files', True)})) if self._prefetch else None
        result = plan(prepare, lambda tokens: self._discard({'tokens': tokens}), rows, operation, mode, settings, prefetch_files)
        primary = [entry['review'] for entry in result['steps']]
        offers = result['offers']
        held = [review['token'] for review in primary] + [offer['review']['token'] for offer in offers]
        try:
            default_review = self._defaults[0]({'changes': defaults}) if defaults is not None else None
            token = uuid.uuid4().hex
            with self._lock:
                if self._closing:
                    raise ValueError('The application is closing.')
                self.reviews[token] = {'primary': primary, 'offers': offers, 'defaults': default_review, 'cancel': threading.Event()}
        except Exception:
            self._discard({'tokens': held})
            raise
        trusts = list(dict.fromkeys(review['trust'] for review in [*primary, *[offer['review'] for offer in offers]] if review.get('trust')))
        rows_out = [row for review in primary for row in review.get('rows', [])]
        if default_review:
            rows_out.append({'name': 'Library defaults', 'detail': 'Keep these tuning values for new installs: ' +
                             ', '.join(key.replace('_', ' ') + ': ' + str(value) for key, value in defaults.items())})
        return {'token': token, 'title': 'Review selected changes', 'action': 'Apply reviewed changes',
                'rows': rows_out, 'blocked': result['blocked'], 'warnings': result['warnings'],
                'trust': '\n'.join(trusts) or None,
                'supported': [{'token': offer['review']['token'], 'nr': offer['nr'], 'mfg': offer['mfg'],
                               'reason': offer['reason'], 'rows': offer['review']['rows']} for offer in offers]}

    def execute(self, params):
        token = params['token']
        with self._lock:
            if self._closing:
                raise ValueError('The application is closing.')
            record = self.reviews.get(token)
            if record is None:
                raise ValueError('This review expired. Review the exact selection again.')
            chosen = params.get('supported') or []
            allowed = {offer['review']['token'] for offer in record['offers']}
            if not isinstance(chosen, list) or any(value not in allowed for value in chosen):
                raise ValueError('The supported-feature selection differs from the review.')
            selected = record['primary'] + [offer['review'] for offer in record['offers'] if offer['review']['token'] in chosen]
            if not selected and not record.get('defaults'):
                raise ValueError('Choose at least one reviewed change.')
            if any(review.get('trust') for review in selected) and params.get('offline_acknowledged') is not True:
                raise ValueError('Acknowledge the exact review notice before continuing.')
            self.reviews.pop(token)
            self.running[token] = record
        completed = []
        try:
            for review in sorted(selected, key=lambda review: min(str(row.get('name', '')).casefold() for row in review['rows'])):
                if record['cancel'].is_set():
                    break
                completed.append(self._execute({'token': review['token'], 'offline_acknowledged': params.get('offline_acknowledged') is True}))
            if record.get('defaults') and not record['cancel'].is_set():
                completed.append(self._defaults[1]({'token': record['defaults']['token']}))
            return {'completed_batches': len(completed), 'cancelled': record['cancel'].is_set(), 'reports': completed}
        except Exception as error:
            raise ValueError(f'{error} {len(completed)} review batch(es) completed; their recovery records are kept.') from error
        finally:
            with self._lock:
                self.running.pop(token, None)
            self._discard({'tokens': self.tokens(record)})

    @staticmethod
    def tokens(record):
        return ([review['token'] for review in record['primary']] +
                [offer['review']['token'] for offer in record['offers']] +
                ([record['defaults']['token']] if record.get('defaults') else []))

    def cancel(self, params):
        with self._lock:
            record = self.reviews.get(params['token']) or self.running.get(params['token'])
        if record:
            record['cancel'].set()
            for review in record['primary'] + [offer['review'] for offer in record['offers']]:
                self._cancel({'token': review['token']})
        return {}

    def discard(self, params):
        for token in params.get('tokens', [params.get('token')]):
            with self._lock:
                record = self.reviews.pop(token, None)
            if record:
                self._discard({'tokens': self.tokens(record)})
        return {}

    def shutdown(self):
        with self._lock:
            self._closing = True
            records = list(self.reviews.values()) + list(self.running.values())
            idle = list(self.reviews)
            for record in records:
                record['cancel'].set()
        for record in records:
            for token in self.tokens(record):
                self._cancel({'token': token})
        self.discard({'tokens': idle})
