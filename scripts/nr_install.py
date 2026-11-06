"""Install and restore a game's DLSS5 NR add-on setup (Lecram, ShortFuse, GITC Uplift).

nr_addons.plan() decides what a setup needs; this module makes it so, through
the same reviewed-transaction path as RenoDX HDR:
- Each archive, add-on file and NR model is checked against providers/nr-addons.json.
- The ReShade host is loaded the way HDR loads it: OptiScaler's LoadReShade when
  OptiScaler owns the game, an existing ReShade, or a fresh ReShade proxy.
- A receipt in the game's .rtxforge folder lists every file this owns and the
  previous value of every ReShade.ini key it set, so restore puts back exactly
  what was there and keeps everything ReShade or the user changed since.
- It never processes a frame twice: OptiScaler must be in MFG Only (its NR off),
  and an NR model owned by another tool is never overwritten.
Games without their own DLSS use Feeder NR for Lecram; this module refuses them.
"""
from __future__ import annotations

import configparser
import io
import json
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
NOTICE = ('Each NR add-on adds a full neural-rendering pass. Expect a large GPU cost, '
          'more so with frame generation on.')


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
    return record


def status(row):
    try:
        root = t.safe(row['game']); path = _receipt(row)
        if not path.exists():
            return {'installed': False}
        record = _read_receipt(root, path)
        changed = [n for n, h in record['files'].items() if not (root / n).is_file() or t.digest(t.safe(root / n)) != h]
        return {'installed': True, 'setup': record['setup'], 'changed': changed}
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


def _payload(config, plan, gpu):
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
    build_id, build = _model_build(plan['model'], gpu)
    model = _model(_fetch(config, build['archive'], Path(build['archive']['url']).name), build.get('file', {}))
    gitc = any(i['addon'] == 'gitc' for i in plan['install'])
    files['GITC-Uplift/' + MODEL if gitc else MODEL] = model
    return files, build_id


def _value(value):
    if isinstance(value, float):
        return f'{value:.2f}'
    return str(value)


def prepare(config, row, setup, gpu='ada'):
    root, exe, _, e = hdr._eligible(config, row)
    receipt = _receipt(row)
    t.need(not receipt.exists(), 'An NR add-on setup is already installed. Remove it before choosing another.')
    arch = hdr.architecture(exe)
    plan = nr_addons.plan(dict(row, arch=arch), setup)
    t.need(not plan['feeder'], 'This game has no DLSS of its own, so Lecram runs through Feeder NR. Choose Feeder NR for it.')
    route, host, optiscaler_ini = hdr._route(e, exe, arch)
    if route == 'optiscaler':
        current = (hdr._managed(e, exe.parent) or {}).get('current') or {}
        t.need(current.get('feature_mode') == 'mfg-only', 'OptiScaler is running its own NR here. Switch it to MFG Only first, '
               'so two NR tools never process the same frame.')
    directory = exe.parent
    files, model_build = _payload(config, plan, gpu)
    writes, checks, owned = {}, {str(exe): t.digest(exe)}, {}
    for rel, data in files.items():
        path = t.safe(directory / t.relative(rel))
        if path.exists():
            t.need(t.digest(path) == t.sha(data), f'Another tool owns {rel}; its file was kept.')
            checks[str(path)] = t.digest(path)
            continue
        writes[path] = data
        owned[path.relative_to(root).as_posix()] = t.sha(data)
    record = {'schema': 1, 'setup': setup, 'route': route, 'host': host, 'model_build': model_build,
              'files': owned, 'ini': {}, 'plugin': None, 'settings_created': None}
    if route in ('reshade', 'optiscaler'):
        # Plain games load ReShade as a proxy; OptiScaler loads ReShade64.dll when LoadReShade is on.
        data = _reshade_host(config, arch)
        path = t.safe(directory / host)
        if path.exists():
            t.need(route == 'optiscaler' and t.digest(path) == t.sha(data), 'Another graphics tool uses ' + host + '. Its files have been kept.')
            checks[str(path)] = t.digest(path)
        else:
            writes[path] = data; owned[path.relative_to(root).as_posix()] = t.sha(data)
    if optiscaler_ini:
        text = t.safe(optiscaler_ini).read_text(encoding='utf-8-sig')
        record['plugin'] = {'path': optiscaler_ini.relative_to(root).as_posix(),
                            'value': t.ini(text).get('Plugins', 'LoadReShade', fallback=None)}
        writes[optiscaler_ini] = t.setvalue(text, 'Plugins', 'LoadReShade', 'true').encode('utf-8')
        checks[str(optiscaler_ini)] = t.digest(optiscaler_ini)
    settings = t.safe(directory / 'ReShade.ini')
    text = settings.read_text(encoding='utf-8-sig') if settings.exists() else ''
    if settings.exists():
        checks[str(settings)] = t.digest(settings)
    elif any(rel.startswith(SHADER_DIR + '/') for rel in files):
        # Only GITC ships shaders; a search path to a missing folder makes ReShade log warnings.
        text = '[GENERAL]\nEffectSearchPaths=' + SEARCH_PATHS + '\n'
    try:
        parsed = t.ini(text) if text.strip() else None
    except (configparser.Error, ValueError, KeyError) as error:
        raise t.Refusal('ReShade settings in this game could not be read safely; they were kept. ' + str(error)) from error
    for section, values in plan['ini'].items():
        for key, value in values.items():
            before = parsed.get(section, key, fallback=None) if parsed else None
            record['ini'].setdefault(section, {})[key] = before
            text = t.setvalue(text, section, key, _value(value))
    writes[settings] = text.encode('utf-8')
    if not checks.get(str(settings)):
        record['settings_created'] = t.sha(writes[settings])
    writes[receipt] = (json.dumps(record, indent=2) + '\n').encode()
    review = hdr._plan(row, root, writes, action='install', checks=checks)
    review.update(kind='nr-addons', route=route, prefix=hdr._prefix_review(config, row, route, host),
                  notes=[NOTICE, *([] if plan['verified'] else ['This pairing has not been verified on a test copy yet.']),
                         *plan['manual']],
                  setup=setup, skipped=plan['skipped'])
    return hdr._freeze(config, review)


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
    t.need(receipt.is_file(), 'No NR add-on setup was found for this game.')
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
                   'Files changed since review; review the NR add-on change again.')
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
            'message': 'NR add-ons removed.' if review['action'] == 'remove' else 'NR add-ons installed.'}
