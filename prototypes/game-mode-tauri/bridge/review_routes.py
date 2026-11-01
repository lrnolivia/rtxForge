"""Consecutive exact reviews and explicit supported-feature subsets.

This ports the native shell's orchestration. Every file plan and write remains
in the existing prepare/execute methods; the aggregate only owns their tokens.
"""
import threading
import uuid
import os
from pathlib import Path


def identity(path):
    return os.path.normcase(str(Path(path).resolve()))


class ReviewedRoutes:
    def __init__(self, prepare, execute, cancel, discard, settings, defaults=None):
        self._prepare, self._execute = prepare, execute
        self._cancel, self._discard, self._settings = cancel, discard, settings
        self._defaults = defaults
        self.reviews, self.running = {}, {}

    @staticmethod
    def feeder(row):
        return row.get('runtime_provider') == 'feeder' or row.get('install_provider') == 'feeder' and row.get('feeder_available') is True

    def route(self, row, operation, mode, settings):
        if operation == 'install' and row.get('adoption_available'):
            return 'adopt', settings.get('runtime_provider', 'y4my')
        if row.get('runtime_provider') == 'vulkan-native' or row.get('install_provider') == 'vulkan-native' and mode != 'nr-only':
            return operation, 'vulkan-native'
        if self.feeder(row):
            return operation, 'feeder'
        if operation == 'repair' and row.get('installed') and row.get('runtime_provider'):
            return operation, row['runtime_provider']
        choices = settings.get('game_packages') or {}
        chosen = next((value for path, value in choices.items() if identity(path) == identity(row['game'])), None)
        return operation, chosen or settings.get('runtime_provider', 'y4my')

    def prepare(self, params):
        rows = sorted(params.get('rows') or [], key=lambda row: row['name'].casefold())
        defaults = params.get('defaults')
        if defaults is not None:
            allowed = {'nr_strength', 'sharpening_strength', 'mfg_multiplier', 'dynamic_mfg',
                       'mfg_saved_mode', 'mfg_saved_multiplier', 'nr_on_launch', 'feature_controls'}
            if not self._defaults or not isinstance(defaults, dict) or not defaults or set(defaults) - allowed:
                raise ValueError('Choose supported library tuning defaults.')
        if not rows and defaults is None:
            raise ValueError('Choose one or more exact installations.')
        operation, mode = params['operation'], params['mode']
        settings = self._settings() | (params.get('settings') or {})
        groups = []
        for row in rows:
            route = self.route(row, operation, mode, settings) if operation in ('install', 'repair') else (operation, row.get('runtime_provider') or settings.get('runtime_provider', 'y4my'))
            if groups and groups[-1][0] == route:
                groups[-1][1].append(row)
            else:
                groups.append((route, [row]))
        primary, offers, blocked, warnings, all_tokens = [], [], [], [], []

        def make(group, selected_mode, selected_operation, provider, subset=False):
            values = dict(settings, runtime_provider=provider)
            if subset:
                values['prefer_bundled_nr_only'] = selected_mode == 'nr-only'
            review = self._prepare({'rows': group, 'mode': selected_mode, 'operation': selected_operation, 'settings': values, 'save_defaults': False})
            all_tokens.append(review['token'])
            return review

        try:
            for (selected_operation, provider), group in groups:
                review = make(group, mode, selected_operation, provider)
                ready_paths = {identity(row['game']) for row in review.get('rows', []) if row.get('game')}
                if not ready_paths:
                    ready_names = {row.get('name') for row in review.get('rows', [])}
                    ready_paths = {identity(row['game']) for row in group if row.get('name') in ready_names}
                if review.get('rows'):
                    if operation == 'install' and mode == 'nr-mfg' and provider == 'feeder':
                        offers.append({'review': review, 'nr': True, 'mfg': False, 'reason': 'Feeder provides NR. MFG is unavailable for this route.'})
                    else:
                        primary.append(review)
                warnings += review.get('warnings', [])
                candidates = [row for row in group if identity(row['game']) not in ready_paths and not row.get('anti_cheat') and row.get('exe')]
                subsets = []
                if operation == 'install' and mode in ('nr-mfg', 'nr-only'):
                    subsets.append(('nr-only', [row for row in candidates if self.feeder(row)], 'Feeder supports NR for these games.'))
                    if mode == 'nr-mfg' and provider == 'skynizz':
                        subsets.append(('nr-only', [row for row in candidates if not self.feeder(row) and row.get('native_dlss') and not row.get('native_dlssg')], 'NR is supported; native frame generation is unavailable.'))
                        missing = {row.get('name') for row in review.get('blocked', []) if any(word in str(row.get('reason', '')).casefold() for word in ('nr runtime', 'nr model', 'nvngx_dlssnr'))}
                        subsets.append(('mfg-only', [row for row in candidates if not self.feeder(row) and row.get('native_dlssg') and row.get('name') in missing], 'MFG is supported; the selected NR runtime could not be prepared.'))
                offered = set()
                for subset_mode, subset, reason in subsets:
                    subset = [row for row in subset if identity(row['game']) not in offered]
                    if not subset:
                        continue
                    try:
                        result = make(subset, subset_mode, selected_operation, 'feeder' if all(self.feeder(row) for row in subset) else provider, True)
                    except (ValueError, OSError, RuntimeError):
                        continue
                    if result.get('rows'):
                        offers.append({'review': result, 'nr': subset_mode != 'mfg-only', 'mfg': subset_mode != 'nr-only', 'reason': reason})
                        warnings += result.get('warnings', [])
                        names = {row.get('name') for row in result['rows']}
                        offered.update(identity(row['game']) for row in subset if row['name'] in names)
                offered_names = {row.get('name') for offer in offers for row in offer['review'].get('rows', [])}
                blocked += [item for item in review.get('blocked', []) if item.get('name') not in offered_names]
            retained = {review['token'] for review in primary} | {offer['review']['token'] for offer in offers}
            unused = [token for token in all_tokens if token not in retained]
            if unused:
                self._discard({'tokens': unused})
            token = uuid.uuid4().hex
            default_review = self._defaults[0]({'changes': defaults}) if defaults is not None else None
            if default_review:
                all_tokens.append(default_review['token'])
            self.reviews[token] = {'primary': primary, 'offers': offers, 'defaults': default_review, 'cancel': threading.Event()}
            trusts = list(dict.fromkeys(review['trust'] for review in [*primary, *[offer['review'] for offer in offers]] if review.get('trust')))
            return {'token': token, 'title': 'Review selected changes', 'action': 'Apply reviewed changes',
                    'rows': [row for review in primary for row in review.get('rows', [])] +
                            ([{'name': 'Library defaults', 'detail': 'Keep these tuning values for new installs: ' +
                               ', '.join(key.replace('_', ' ') + ': ' + str(value) for key, value in defaults.items())}]
                             if default_review else []), 'blocked': blocked, 'warnings': warnings,
                    'trust': '\n'.join(trusts) or None,
                    'supported': [{'token': offer['review']['token'], 'nr': offer['nr'], 'mfg': offer['mfg'], 'reason': offer['reason'], 'rows': offer['review']['rows']} for offer in offers]}
        except Exception:
            if all_tokens:
                self._discard({'tokens': all_tokens})
            raise

    def execute(self, params):
        token = params['token']
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
            self.running.pop(token, None)
            self._discard({'tokens': self.tokens(record)})

    @staticmethod
    def tokens(record):
        return ([review['token'] for review in record['primary']] +
                [offer['review']['token'] for offer in record['offers']] +
                ([record['defaults']['token']] if record.get('defaults') else []))

    def cancel(self, params):
        record = self.reviews.get(params['token']) or self.running.get(params['token'])
        if record:
            record['cancel'].set()
            for review in record['primary'] + [offer['review'] for offer in record['offers']]:
                self._cancel({'token': review['token']})
        return {}

    def discard(self, params):
        for token in params.get('tokens', [params.get('token')]):
            record = self.reviews.pop(token, None)
            if record:
                self._discard({'tokens': self.tokens(record)})
        return {}
