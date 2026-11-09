"""Install and restore a game's DLSS5 NR add-on setup (Lecram, ShortFuse, GITC Uplift).

nr_addons.plan() decides what a setup needs; this module makes it so, through
the same reviewed-transaction path as RenoDX HDR:
- Each archive, add-on file and NR model is checked against providers/nr-addons.json.
- The ReShade host is loaded the way HDR loads it: OptiScaler's LoadReShade when
  OptiScaler owns the game, an existing ReShade, or a fresh ReShade proxy.
- A receipt in the game's .rtxforge folder lists every file this owns and the
  previous value of every ReShade.ini key it set, so restore puts back exactly
  what was there and keeps everything ReShade or the user changed since.
- Where OptiScaler runs its own NR (Skynizz), that NR is the Environment and its
  model is shared: only a Character add-on that works beside it is installed,
  without a model. An NR model owned by another tool is never overwritten.
Games without their own DLSS use Feeder NR for Lecram; this module refuses them.
"""
from __future__ import annotations

import configparser
import io
import json
import os
import re
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import engine_bridge
import nr_addons
import packages
import renodx_hdr as hdr
import storage as state_storage
import transactions as t

MODEL = 'nvngx_dlssnr.dll'
SHADER_DIR = 'reshade-shaders/Shaders'
SEARCH_PATHS = '.\\reshade-shaders\\Shaders\\**'
NOTICE = ('Each Split Render pass runs neural rendering. Expect a large GPU cost, '
          'more so with frame generation on.')
MEMORY_NOTE = ("With Skynizz's NR and multi-frame generation, a second NR pass runs close to the GPU's "
               'video-memory limit on 12 GB cards. Switching windows can stall the game; lower Character '
               'detail resolution if it does.')
LOAD_EARLY = ('ADDON', 'LoadFromDllMain')


def _receipt(row):
    root = t.safe(row['game'])
    return t.safe(root / '.rtxforge' / ('nr-' + t.sha(row['exe'].encode())[:16] + '.json'))


def _read_receipt(root, path):
    t.need(path.stat().st_size < 1024**2, 'NR add-on record is too large.')
    record = t.read_json(path)
    t.need(record.get('schema') == 1 and isinstance(record.get('files'), dict) and isinstance(record.get('ini'), dict)
           and record.get('route') in ('reshade', 'existing-reshade', 'optiscaler') and isinstance(record.get('setup'), dict),
           'Invalid NR add-on record.')
    for name, digest in record['files'].items():
        t.relative(name); t.safe(root / name)
        t.need(isinstance(digest, str) and re.fullmatch('[a-f0-9]{64}', digest), 'Invalid NR add-on record member.')
    early = record.get('load_early') or []
    t.need(isinstance(early, list) and all(isinstance(n, str) and re.fullmatch(r'[\w.-]+\.addon(?:32|64)', n) for n in early),
           'Invalid NR add-on record.')
    return record


def status(row):
    try:
        root = t.safe(row['game']); path = _receipt(row)
        world = nr_addons.runtime_nr(row)
        if not path.exists():
            return {'installed': False, 'default': nr_addons.default_setup(row), 'runtime_nr': world}
        record = _read_receipt(root, path)
        changed = [n for n, h in record['files'].items() if not (root / n).is_file() or t.digest(t.safe(root / n)) != h]
        setup = dict(record['setup'])
        if record['route'] == 'optiscaler' and not setup.get('environment') and world:
            setup['environment'] = {'addon': nr_addons.RUNTIME}  # installed before Skynizz was shown as the world
        return {'installed': True, 'setup': setup, 'changed': changed, 'runtime_nr': world}
    except (t.Refusal, OSError, ValueError) as error:
        return {'installed': False, 'error': str(error)}


def _fetch(config, archive, name):
    """A pinned archive from the shared cache, downloaded on first use."""
    cache = state_storage.storage(config, archive['size'] * 2) / 'nr-cache'
    try:
        request = urllib.request.Request(archive['url'], headers={'User-Agent': 'rtxForge/1.0'})
        path = packages.download(request, cache / archive['sha256'] / name, expected=archive['sha256'], size=archive['size'])
    except urllib.error.HTTPError as error:
        if error.code in (404, 410):
            raise t.Refusal(f'{name} is no longer published at its pinned address. Update rtxForge, then retry.') from error
        raise t.Refusal(f'Could not download {name}. Try again later. {error}') from error
    except (OSError, urllib.error.URLError) as error:
        raise t.Refusal(f'Could not download {name}. Check your connection and retry. {error}') from error
    return path.read_bytes()


def _members(data, pins):
    """The pinned files inside a verified archive, each checked against its own hash."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member, pin in pins.items():
            entries = [m for m in archive.infolist() if m.filename == member]
            t.need(len(entries) == 1, f'The verified archive lacks {member}.')
            blob = archive.read(entries[0])
            t.need(t.sha(blob) == pin['sha256'] and pin.get('size', len(blob)) == len(blob), f'{member} failed verification.')
            out[member] = blob
    return out


def _model(data, pin):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = [m for m in archive.infolist() if PurePosixPath(m.filename).name.casefold() == MODEL]
        t.need(len(entries) == 1, 'The verified NR model archive does not contain exactly one NR model.')
        blob = archive.read(entries[0])
    if pin.get('verified'):
        t.need(t.sha(blob) == pin['sha256'] and len(blob) == pin['size'], 'The NR model failed verification.')
    t.need(len(blob) > 32 * 1024**2 and blob[:2] == b'MZ', 'The NR model is not a valid Windows library.')
    return blob


def _model_build(model, gpu):
    """The pinned build of the Old or New model for this GPU family (hardware.family)."""
    models = nr_addons.catalog()['models']
    for build_id, build in models[model]['builds'].items():
        if gpu in build['for']:
            return build_id, build
    raise t.Refusal(f'{models[model]["label"]} has no pinned build for this GPU yet.')


def _payload(config, plan, model):
    """Every file the setup installs, relative to the game's executable folder."""
    catalog = nr_addons.catalog()
    files = {}
    for item in plan['install']:
        addon = catalog['addons'][item['addon']]
        build = addon['builds'][item['build']]
        t.need('archive' in build, f'{addon["name"]} {build["label"]} is installed through Feeder NR.')
        members = _members(_fetch(config, build['archive'], Path(build['archive']['url']).name), build['members'])
        for member, blob in members.items():
            path = PurePosixPath(member)
            if path.suffix in ('.fx', '.fxh'):
                files[f'{SHADER_DIR}/{path.name}'] = blob
            elif path.name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
                files[f'rtxForge-NR-Licenses/{item["addon"]}-{path.name}'] = blob
            else:
                files[path.name] = blob
    if model is None:
        return files  # OptiScaler's NR brings the model
    _, build = model
    model = _model(_fetch(config, build['archive'], Path(build['archive']['url']).name), build.get('file', {}))
    gitc = any(i['addon'] == 'gitc' for i in plan['install'])
    files['GITC-Uplift/' + MODEL if gitc else MODEL] = model
    return files


def _value(value):
    if isinstance(value, float):
        return f'{value:.2f}'
    return str(value)


def _target(row, exe, e, projection=None):
    t.need(not _receipt(row).exists(), 'A Split Render setup is already installed. Remove it before choosing another.')
    arch = hdr.architecture(exe)
    route, host, optiscaler_ini = hdr._route(e, exe, arch, projection=projection)
    # The game folder, not the library row, says whether OptiScaler is here and runs its own NR.
    baseline = projection.baseline() if projection else hdr._managed(e, exe.parent)
    current = (baseline or {}).get('current') or {}
    provider = current.get('provider_id') or (current.get('archive') or {}).get('family')
    optiscaler = route == 'optiscaler' or provider in nr_addons.RUNTIME_NAMES
    mode = (current.get('feature_mode') or 'unknown') if optiscaler else None
    game = dict(row, arch=arch, optiscaler_mode=mode)
    if provider:
        game['runtime_provider'] = provider
    return game, route, host, optiscaler_ini


def _resolved(game, setup, gpu, *, adapt=False):
    if adapt:
        setup = nr_addons.combo_setup(game, setup)
    plan = nr_addons.install_plan(game, setup)
    model = _model_build(plan['model'], gpu) if plan['model'] is not None else None
    return setup, plan, model


def _choose(game, choice, gpu):
    if choice.get('auto') is not True:
        return _resolved(game, choice['setup'], gpu, adapt=choice['adapt'])
    if nr_addons.runtime_nr(game):
        return _resolved(game, nr_addons.builtin_combos()['characters-and-world'], gpu, adapt=True)
    # Start with a single pass. Where Lecram cannot run, try the next standalone provider.
    reasons = []
    for addon in ('lecram', 'shortfuse', 'gitc'):
        try:
            return _resolved(game, {'environment': {'addon': addon, 'model': choice['model']}}, gpu)
        except t.Refusal as error:
            reasons.append(str(error))
    raise t.Refusal(reasons[0])


def prepare(config, row, setup, gpu='ada', *, adapt=False):
    return _prepare_choice(config, row, {'setup': setup, 'adapt': adapt}, gpu)


def _prepare_choice(config, row, choice, gpu, projection=None):
    root, exe, _, e = hdr._eligible(config, row)
    game, route, host, optiscaler_ini = _target(row, exe, e, projection)
    if projection:
        t.need(route in ('optiscaler', 'existing-reshade'),
               'The main package cannot provide a reviewed Split Render loader.')
    digest = projection.digest if projection else lambda path: t.digest(path) if path.exists() else None
    read_text = projection.read_text if projection else lambda path: path.read_text(encoding='utf-8-sig')
    receipt = _receipt(row)
    setup, plan, model = _choose(game, choice, gpu)
    directory = exe.parent
    files = _payload(config, plan, model)
    model_build = model[0] if model else None
    writes, checks, owned = {}, {str(exe): t.digest(exe)}, {}
    if projection:
        # Confirm the exact reviewed loader and any ReShade hook we are borrowing.
        proxy = directory / projection.planned['proxy']
        checks[str(proxy)] = digest(proxy)
        if route == 'existing-reshade':
            borrowed_host = directory / host
            checks[str(borrowed_host)] = digest(borrowed_host)
    for rel, data in files.items():
        path = t.safe(directory / t.relative(rel))
        if (before := digest(path)) is not None:
            t.need(before == t.sha(data), f'Another tool owns {rel}; its file was kept.')
            checks[str(path)] = before
            continue
        writes[path] = data
        owned[path.relative_to(root).as_posix()] = t.sha(data)
    record = {'schema': 1, 'setup': setup, 'route': route, 'host': host, 'model_build': model_build,
              'files': owned, 'ini': {}, 'plugin': None, 'settings_created': None}
    if route in ('reshade', 'optiscaler'):
        # Plain games load ReShade as a proxy; OptiScaler loads ReShade64.dll when LoadReShade is on.
        data = _reshade_host(config, game['arch'])
        path = t.safe(directory / host)
        if (before := digest(path)) is not None:
            t.need(route == 'optiscaler' and before == t.sha(data), 'Another graphics tool uses ' + host + '. Its files have been kept.')
            checks[str(path)] = before
        else:
            writes[path] = data; owned[path.relative_to(root).as_posix()] = t.sha(data)
    if optiscaler_ini:
        text = read_text(t.safe(optiscaler_ini))
        record['plugin'] = {'path': optiscaler_ini.relative_to(root).as_posix(),
                            'value': t.ini(text).get('Plugins', 'LoadReShade', fallback=None)}
        writes[optiscaler_ini] = t.setvalue(text, 'Plugins', 'LoadReShade', 'true').encode('utf-8')
        checks[str(optiscaler_ini)] = digest(optiscaler_ini)
    settings = t.safe(directory / 'ReShade.ini')
    if (before := digest(settings)) is not None:
        text = read_text(settings)
        checks[str(settings)] = before
    elif any(rel.startswith(SHADER_DIR + '/') for rel in files):
        # Only GITC ships shaders; a search path to a missing folder makes ReShade log warnings.
        text = '[GENERAL]\nEffectSearchPaths=' + SEARCH_PATHS + '\n'
    else:
        text = ''
    try:
        parsed = t.ini(text) if text.strip() else None
    except (configparser.Error, ValueError, KeyError) as error:
        raise t.Refusal('ReShade settings in this game could not be read safely; they were kept. ' + str(error)) from error
    for section, values in plan['ini'].items():
        for key, value in values.items():
            before = parsed.get(section, key, fallback=None) if parsed else None
            record['ini'].setdefault(section, {})[key] = before
            text = t.setvalue(text, section, key, _value(value))
    if plan['load_early']:
        # ShortFuse must load while ReShade starts, or Streamline games crash during startup.
        # LoadFromDllMain is a list shared with other add-ons: add ours, and remove only ours later.
        listed = _names(parsed.get(*LOAD_EARLY, fallback='') if parsed else '')
        added = [n for n in plan['load_early'] if n.casefold() not in {x.casefold() for x in listed}]
        record['load_early'] = added
        if added:
            text = t.setvalue(text, *LOAD_EARLY, ','.join(listed + added))
    writes[settings] = text.encode('utf-8')
    if not checks.get(str(settings)):
        record['settings_created'] = t.sha(writes[settings])
    writes[receipt] = (json.dumps(record, indent=2) + '\n').encode()
    review = hdr._plan(row, root, writes, action='install', checks=checks, projection=projection)
    review.update(kind='nr-addons', route=route, prefix=hdr._prefix_review(config, row, route, host),
                  notes=[NOTICE, *([] if plan['verified'] else ['This pairing has not been verified on a test copy yet.']),
                         *([MEMORY_NOTE] if plan['optiscaler_nr'] else [])],
                  setup=setup, skipped=plan['skipped'],
                  selection=selection(plan, model_build))
    if projection:
        review['after_package'] = dict(provider=game.get('runtime_provider'), mode=game.get('optiscaler_mode'), host=host)
    return hdr._freeze(config, review)


class PackageProjection:
    """Read the expected files after the exact main-package review runs."""
    def __init__(self, directory, planned):
        self.directory, self.planned = t.safe(directory), planned
        self.payload = {os.path.normcase(name): data for name, data in planned['payload'].items()}
        self.removed = {os.path.normcase(name) for name in planned['remove']}

    def key(self, path):
        return os.path.normcase(path.relative_to(self.directory).as_posix()) if path.is_relative_to(self.directory) else None

    def exists(self, path):
        key = self.key(path)
        return key in self.payload or key not in self.removed and path.exists()

    def digest(self, path):
        path = t.safe(path)
        key = self.key(path)
        if key in self.payload:
            return t.sha(self.payload[key])
        if key not in self.removed and path.exists():
            return t.digest(path)
        return None

    def read_text(self, path):
        key = self.key(path)
        if key in self.payload:
            return self.payload[key].decode('utf-8-sig')
        t.need(key not in self.removed, 'The main package removes a file needed by Split Render.')
        return path.read_text(encoding='utf-8-sig')

    def baseline(self):
        proxy = self.planned['proxy']
        return {'status': 'active', 'current': {
            'provider_id': self.planned['provider'], 'feature_mode': self.planned['mode'], 'proxy': proxy,
            'installed_hashes': {proxy: self.digest(self.directory / proxy)},
        }}


def prepare_after_packages(config, reviews, choice, gpu='ada'):
    """Freeze Split Render against planned main-package files, before confirmation."""
    if choice is not None:
        _validate_choice(choice)
    staged, summary, seen = [], [], set()

    def visit(review):
        for item in review.get('plans', ()):
            staged.append((item, None))
            projection = item.get('package_projection')
            if choice is None or projection is None:
                continue
            row, game = item['row'], item['game']
            result = {'game': row['game'], 'name': row['name']}
            seen.add(row['game'])
            try:
                expected = PackageProjection(game.target_dir, projection)
                target = dict(row, exe=Path(game.exe).relative_to(game.root).as_posix())
                plan = _prepare_choice(config, target, choice, gpu, expected)
            except (t.Refusal, OSError, ValueError, configparser.Error) as error:
                summary.append(dict(result, reason=str(error)))
            else:
                staged[-1] = (item, (config, plan))
                summary.append(dict(result, summary=plan['selection'], details=describe_changes(plan)))
        for companion in review.get('companions') or ():
            visit(companion)
        if choice is not None:
            for row in review.get('rows', ()):
                if row.get('game') and row['game'] not in seen:
                    seen.add(row['game'])
                    summary.append({'game': row['game'], 'name': row['name'],
                                    'reason': 'Split Render is unavailable with this main package route.'})

    for review in reviews:
        visit(review)
    return staged, summary


def attach_after_packages(staged):
    for item, setup in staged:
        item.pop('split_render', None)
        if setup is not None:
            item['split_render'] = setup


def apply_after_package(config, planned):
    """Apply only the already-reviewed paths and payloads after the main install."""
    plan = dict(planned)
    digest = plan.pop('plan_sha256')
    t.need(digest == t.sha(json.dumps(plan, sort_keys=True).encode()), 'Split Render plan changed since review.')
    expected = plan.pop('after_package')
    root, exe, _, e = hdr._eligible(config, plan)
    game, route, host, _ = _target(plan, exe, e)
    actual = dict(provider=game.get('runtime_provider'), mode=game.get('optiscaler_mode'), host=host)
    t.need(route == plan['route'] and actual == expected, 'The installed package differs from the Split Render review.')
    # The main package changes the directory listing. Every Split Render path
    # still has to match its projected before hash and its frozen payload.
    plan['listing'] = t.files(root)
    plan['plan_sha256'] = t.sha(json.dumps(plan, sort_keys=True).encode())
    return apply(config, plan)


def selection(plan, model_build):
    roles = {'environment': 'Environment', 'character': 'Character detail'}
    parts = [f'Environment: {plan["world"]} (shared model)'] if plan['optiscaler_nr'] else []
    parts.extend(f'{roles[slot["slot"]]}: {slot["name"]} {slot["build"]}' for slot in plan['slots'])
    if model_build:
        parts.append(f'Model: {model_build}')
    return ' · '.join(parts)


def _validate_choice(choice):
    t.need(isinstance(choice, dict), 'Choose a Split Render setup.')
    if choice.get('auto') is True:
        t.need(choice.get('model') in nr_addons.MODELS, 'Choose the Old or New DLSS 5 model.')
    else:
        t.need(isinstance(choice.get('setup'), dict) and type(choice.get('adapt')) is bool,
               'Choose a Split Render setup.')


def match_batch(config, rows, choice, gpu='ada'):
    """Preview compatible library rows without downloads. Review rechecks live safety and file ownership."""
    _validate_choice(choice)
    e = engine_bridge.module(config)
    matches = []
    for index, row in enumerate(rows):
        try:
            t.need(row.get('exe') and not row.get('anti_cheat'), 'This title cannot use Split Render.')
            _, exe, _ = hdr._location(row)
            game, _, _, _ = _target(row, exe, e)
            _, plan, model = _choose(game, choice, gpu)
        except (t.Refusal, OSError, ValueError, configparser.Error):
            continue
        matches.append({'index': index, 'summary': selection(plan, model[0] if model else None)})
    return matches


def prepare_batch(config, rows, choice, gpu='ada'):
    """Freeze one reviewed transaction per game, with no implicit writes to excluded games."""
    _validate_choice(choice)
    plans, blocked, roots = [], [], set()
    for row in rows:
        try:
            t.need(row.get('exe'), 'The selected game executable is unavailable.')
            root = t.safe(row['game'])
            t.need(root not in roots, 'This folder already has a Split Render setup in this review.')
            plan = _prepare_choice(config, row, choice, gpu)
        except (t.Refusal, OSError, ValueError, configparser.Error) as error:
            blocked.append({'game': row['game'], 'name': row['name'], 'reason': str(error)})
        else:
            plans.append(plan)
            roots.add(root)
    return {'plans': plans, 'blocked': blocked}


def describe_changes(plan):
    changes = [' '.join(('Remove' if c['after'] is None else 'Update' if c['before'] else 'Add', c['path']))
               + ('\nSHA-256: ' + c['after'] if c['after'] else '') for c in plan['changes']]
    return '\n'.join([*changes, *plan.get('notes', [])])


def apply_batch(config, review, progress=None):
    count, errors = 0, []
    for index, plan in enumerate(review['plans']):
        if progress:
            progress(plan['name'], index, len(review['plans']))
        try:
            apply(config, plan)
        except (t.Refusal, OSError, ValueError, configparser.Error) as error:
            errors.append(f'{plan["name"]}: {error}')
        else:
            count += 1
    return {'message': f'Split Render installed in {count} game' + ('s.' if count != 1 else '.'), 'errors': errors}


def _names(value):
    return [n.strip() for n in (value or '').split(',') if n.strip()]


def _reshade_host(config, arch):
    """The verified ReShade runtime, extracted from the pinned add-on build installer."""
    request = urllib.request.Request(hdr.HOST_URL, headers={'User-Agent': 'rtxForge/1.0'})
    cache = state_storage.storage(config, 32 * 1024**2) / 'hdr-cache'
    setup = packages.download(request, cache / hdr.HOST_ARCHIVE[0] / 'ReShade_Addon.exe', expected=hdr.HOST_ARCHIVE[0], size=hdr.HOST_ARCHIVE[1])
    name, digest, size = hdr.HOSTS[arch]
    with zipfile.ZipFile(setup) as archive:
        entries = [m for m in archive.infolist() if m.filename == name]
        t.need(len(entries) == 1 and entries[0].file_size == size, 'Unexpected ReShade runtime in the verified archive.')
        data = archive.read(entries[0])
    t.need(t.sha(data) == digest, 'ReShade runtime failed verification.')
    return data


def _other_consumers(directory, record, root):
    ours = {Path(n).name.casefold() for n in record['files']}
    return sorted(p.name for p in directory.glob('*.addon*')
                  if p.suffix.lower() in ('.addon32', '.addon64') and p.name.casefold() not in ours
                  and p.name.casefold() not in ('rtxforge-effects.addon64', 'rtxforge-quiet.addon64'))


def prepare_remove(config, row):
    root, exe, _, e = hdr._eligible(config, row)
    receipt = _receipt(row)
    t.need(receipt.is_file(), 'No Split Render setup was found for this game.')
    record = _read_receipt(root, receipt)
    directory = exe.parent
    consumers = _other_consumers(directory, record, root)
    writes, checks, kept = {receipt: None}, {str(receipt): t.digest(receipt), str(exe): t.digest(exe)}, []
    for name, digest in record['files'].items():
        path = t.safe(root / name)
        if not path.exists():
            continue
        if t.digest(path) != digest:
            kept.append(name)  # changed since install: never deleted
            continue
        if consumers and path.name == record['host']:
            continue
        writes[path] = None; checks[str(path)] = digest
    settings = t.safe(directory / 'ReShade.ini')
    if settings.exists():
        current = settings.read_bytes()
        if record['settings_created'] and t.sha(current) == record['settings_created'] and not consumers:
            writes[settings] = None
        else:
            text = current.decode('utf-8-sig')
            for section, keys in record['ini'].items():
                for key, before in keys.items():
                    text = _restore_key(text, section, key, before)
            if record.get('load_early'):
                ours = {n.casefold() for n in record['load_early']}
                try:
                    listed = _names(t.ini(text).get(*LOAD_EARLY, fallback=''))
                except (configparser.Error, ValueError, KeyError) as error:
                    raise t.Refusal('ReShade settings in this game could not be read safely; they were kept. ' + str(error)) from error
                rest = [n for n in listed if n.casefold() not in ours]
                text = t.setvalue(text, *LOAD_EARLY, ','.join(rest)) if rest else _restore_key(text, *LOAD_EARLY, None)
            writes[settings] = text.encode('utf-8')
        checks[str(settings)] = t.digest(settings)
    if record.get('plugin') and not consumers:
        ini = t.safe(root / t.relative(record['plugin']['path']))
        if ini.exists():
            text = _restore_key(ini.read_text(encoding='utf-8-sig'), 'Plugins', 'LoadReShade', record['plugin']['value'])
            writes[ini] = text.encode('utf-8'); checks[str(ini)] = t.digest(ini)
    review = hdr._plan(row, root, writes, action='remove', checks=checks)
    review.update(kind='nr-addons', route=record['route'], consumers=consumers,
                  prefix=None if consumers or record['route'] != 'reshade' else hdr._prefix_review(config, row, 'reshade', record['host'], remove=True),
                  notes=([f'Changed since install, kept: {", ".join(kept)}'] if kept else [])
                  + (['ReShade stays installed for: ' + ', '.join(consumers)] if consumers else []))
    return hdr._freeze(config, review)


def _restore_key(text, section, key, before):
    if before is not None:
        return t.setvalue(text, section, key, before)
    block = t.section(text, section)
    if block is None:
        return text
    return text.replace(block, re.sub(r'(?im)^[ \t]*' + re.escape(key) + r'[ \t]*=[^\r\n]*(?:\r?\n|$)', '', block), 1)


def apply(config, review):
    t.need(review.get('kind') == 'nr-addons' and review.get('action') in ('install', 'remove'), 'Invalid NR add-on operation.')
    root, exe, _, e = hdr._eligible(config, review)
    base = state_storage.storage(config) / 'nr-transactions'; base.mkdir(parents=True, exist_ok=True)
    state = base / uuid.uuid4().hex
    with e.mutation_lock():
        hdr._eligible(config, review)
        t.check_plan(review)
        for path, digest in review['checks'].items():
            t.need(t.safe(path).is_relative_to(root) and Path(path).is_file() and t.digest(path) == digest,
                   'Files changed since review. Review the Split Render change again.')
        prefix = review.get('prefix')
        if prefix:
            import proton_prefix
            t.need(not proton_prefix.prefix_in_use(Path(prefix['prefix'])), 'The Proton session started after review. Close it and review again.')
            t.need(t.digest(t.safe(prefix['registry'])) == prefix['before'], 'Proton settings changed after review; review again.')
        result = t.apply_transaction(review, state)
        if prefix:
            try:
                if review['action'] == 'remove': proton_prefix.restore(Path(prefix['state']))
                else: proton_prefix.apply(Path(prefix['prefix']), prefix['names'], Path(prefix['state']))
            except BaseException:
                t.rollback_transaction(state, True)  # the game files go back; the prefix was not changed
                raise
    return {'status': result['status'], 'recovery': str(state),
            'message': 'Split Render removed.' if review['action'] == 'remove' else 'Split Render installed.'}


def revise_package_reviews(config, reviews, params, gpu):
    revision = params.get('revision')
    if type(revision) is not int or revision < 1:
        raise ValueError('Choose a valid Split Render review revision.')
    if not reviews or any(review.get('operation') not in ('install', 'adopt') for review in reviews):
        raise ValueError('Review the games for installation again.')
    if any(revision <= review.get('split_render_revision', 0) for review in reviews):
        raise ValueError('A newer Split Render review has already been prepared.')
    staged, rows = prepare_after_packages(config, reviews, params.get('choice'), gpu)
    attach_after_packages(staged)
    for review in reviews:
        review['split_render_revision'] = revision
    return {'rows': rows}
