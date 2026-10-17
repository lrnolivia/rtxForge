"""Pinned, separately owned Ada MFG addon hosted by Skynizz's ReShade loader."""
from pathlib import Path
import copy
import configparser
import hashlib
import json
import urllib.request
import zipfile

import packages
import skynizz_provider
import transactions as t
from storage import storage

ROOT = Path(__file__).resolve().parents[1]
ID = 'mfg-unlock'
REPO = 'mavismmg/MFGAdaUnlock-RenoDx'
SECTION = 'RenoDX.MFGUnlock'
KNOWN = {
    '1.4.4': ('3e898157fd59ed9eef65c181619060ddb305c6bd',
              '5a193d86c6f60a7f0f275799d66eef7f14bd0946cdbefd48a3237506c747d5cd', 1199104),
}
HOST = ('afe4c8f13048306307983b8b3d41d5bf00a86820440b0e57dea10950e1176445', 4318424,
        '0cee63f9c9f13f3ac909c5b4903f4dbb4b719a7ab3b4f13b0deaf83c814b94f7', 5592064)


def pinned():
    return validate(json.loads((ROOT / 'providers/lock.json').read_text(encoding='utf-8'))[ID])


def validate(record):
    t.need(isinstance(record, dict) and record.get('version') in KNOWN, 'Unsupported Ada MFG component')
    version = record['version']
    commit, digest, size = KNOWN[version]
    t.need(record.get('id') == ID and record.get('repo') == REPO
           and record.get('commit') == commit and record.get('sha256') == digest
           and record.get('release_size') == size
           and record.get('archive') == 'renodx-mfgunlock.addon64'
           and record.get('url') == f'https://github.com/{REPO}/releases/download/{version}/renodx-mfgunlock.addon64',
           'Untrusted Ada MFG release identity')
    host = record.get('host') or {}
    t.need(host.get('version') == '6.8.0' and host.get('archive') == 'ReShade_Setup_6.8.0_Addon.exe'
           and host.get('url') == 'https://reshade.me/downloads/ReShade_Setup_6.8.0_Addon.exe'
           and (host.get('sha256'), host.get('release_size'), host.get('dll_sha256'), host.get('dll_size')) == HOST,
           'Untrusted addon-enabled ReShade host identity')
    notices = record.get('notices') or {}
    expected = {'MFG-Unlock-LICENSE.txt': f'https://raw.githubusercontent.com/{REPO}/{commit}/LICENSE',
                'ReShade-LICENSE.txt': 'https://raw.githubusercontent.com/crosire/reshade/v6.8.0/LICENSE.md'}
    t.need(set(notices) == set(expected), 'MFG component license notices are incomplete')
    for name, url in expected.items():
        notice = notices[name]
        t.need(notice.get('url') == url and isinstance(notice.get('sha256'), str)
               and len(notice['sha256']) == 64 and type(notice.get('release_size')) is int
               and 0 < notice['release_size'] < 65536, 'Untrusted MFG license notice identity')
    return copy.deepcopy(record)


def _read(path, digest, size, *, binary=False):
    path = Path(path)
    t.need(path.is_file() and not path.is_symlink() and path.absolute() == path.resolve()
           and path.stat().st_size == size, 'MFG component size/type mismatch')
    data = path.read_bytes()
    t.need(hashlib.sha256(data).hexdigest() == digest, 'MFG component SHA-256 mismatch')
    t.need(not binary or skynizz_provider.amd64(data), 'MFG component is not Windows x64')
    return data


def load_payload(config, record):
    record = validate(record)
    cache = storage(config, 16 * 1024**2) / 'packages' / record['sha256']
    addon = packages.download(record['url'], cache / record['archive'], expected=record['sha256'], size=record['release_size'])
    host = record['host']
    # ReShade's server rejects Python's default user agent. Identify the app
    # while retaining the same exact URL, size and SHA-256 checks.
    request = urllib.request.Request(host['url'], headers={'User-Agent': 'rtxForge/1.0'})
    setup = packages.download(request, cache / host['archive'], expected=host['sha256'], size=host['release_size'])
    # The official setup is a self-extracting ZIP. Never execute it, and read
    # only the exact pinned DLL member rather than extracting arbitrary paths.
    _read(setup, host['sha256'], host['release_size'])
    with zipfile.ZipFile(setup) as archive:
        members = [info for info in archive.infolist() if info.filename == 'ReShade64.dll']
        t.need(len(members) == 1 and members[0].file_size == host['dll_size'], 'ReShade x64 host member mismatch')
        dll = archive.read(members[0])
    t.need(skynizz_provider.amd64(dll) and hashlib.sha256(dll).hexdigest() == host['dll_sha256'],
           'ReShade x64 host architecture/hash mismatch')
    data = {'ReShade64.dll': dll, record['archive']: _read(addon, record['sha256'], record['release_size'], binary=True)}
    for name, notice in record['notices'].items():
        path = packages.download(notice['url'], cache / name, expected=notice['sha256'], size=notice['release_size'])
        data['OptiScaler/licenses/' + name] = _read(path, notice['sha256'], notice['release_size'])
    return data


def configure(e, game, baseline, multiplier):
    """Initialize a fixed multiplier; repair preserves the addon's complete preset."""
    path = game.target_dir / 'ReShade.ini'
    t.need(not path.is_symlink() and (not path.exists() or path.is_file()), 'Unsafe ReShade.ini path')
    raw = path.read_bytes() if path.is_file() else b''
    text = raw.decode('utf-8-sig')
    installed = ((baseline or {}).get('current') or {}).get('archive') or {}
    owned = bool((installed.get('release') or {}).get('mfg_component'))
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(text)
    except configparser.Error as error:
        raise t.Refusal('ReShade configuration could not be parsed: ' + str(error)) from error
    if not owned:
        t.need(not parser.has_section(SECTION), 'Existing MFG Unlock settings are unmanaged; restore that installation first.')
    elif path.is_file():
        # Preserve BOM, line endings, comments and every user-controlled field.
        return raw
    if not owned or not path.is_file():
        t.need(multiplier == 'auto' or type(multiplier) is int and multiplier in (0, 2, 3, 4, 5, 6), 'Invalid MFG multiplier')
        for key, value in {'Enabled': '0' if multiplier == 0 else '1', 'ForceMultiplier': '0' if multiplier == 'auto' else str(multiplier),
                           'DynamicMFG': '0', 'MaxCount': '5', 'RuntimeSelectionMode': '0'}.items():
            text = e.set_ini_value(text, SECTION, key, value)
        # This host supplies no shader effects or in-game control panel.
        text = e.set_ini_value(text, 'GENERAL', 'PerformanceMode', '1')
    return text.encode('utf-8')


def reset_multiplier(e, raw, multiplier):
    t.need(multiplier == 'auto' or type(multiplier) is int and multiplier in (0, 2, 3, 4, 5, 6), 'Invalid MFG multiplier')
    text = raw.decode('utf-8-sig')
    for key, value in {'Enabled': '0' if multiplier == 0 else '1',
                       'ForceMultiplier': '0' if multiplier == 'auto' else str(multiplier), 'DynamicMFG': '0'}.items():
        text = e.set_ini_value(text, SECTION, key, value)
    return text.encode('utf-8')


def configured_state(target, record):
    """Saved settings only; never treat an INI request as runtime verification."""
    record = validate(record)
    path = Path(target) / 'ReShade.ini'
    t.need(path.is_file() and not path.is_symlink(), 'MFG configuration is missing or linked')
    parser = configparser.ConfigParser(interpolation=None, strict=True, inline_comment_prefixes=(';', '#'))
    try:
        parser.read_string(path.read_text(encoding='utf-8-sig'))
        enabled = parser.getint(SECTION, 'Enabled', fallback=1) != 0
        force = parser.getint(SECTION, 'ForceMultiplier', fallback=0)
    except configparser.Error as error:
        raise t.Refusal('MFG configuration could not be parsed') from error
    t.need(force in (0, 2, 3, 4, 5, 6), 'Unsupported saved MFG multiplier')
    return {'mfg_provider': ID, 'mfg_multiplier': 0 if not enabled else 'auto' if force == 0 else force,
            'mfg_enabled': enabled, 'mfg_route': 'Native DLSS-G · MFG Unlock ' + record['version'] + ' (configured)'}


def check_target(e, game, baseline):
    """Do not replace an unmanaged host/addon or switch a recorded MFG recipe."""
    record = validate(e.Y4MY_PROVIDER['mfg_component'])
    # The 1.4.4 + ReShade 6.8 composition hangs at inZOI's first Present,
    # before NR starts. The same NR/bridge build boots with integrated MFG.
    # Keep this failed composition out of fresh installs and repairs.
    inzoi = (str(getattr(game, 'appid', '')) == '2456740'
             or str(getattr(game, 'exe', '')).replace('\\', '/').rsplit('/', 1)[-1].casefold()
             == 'inzoi-win64-shipping.exe')
    t.need(not (record['version'] == '1.4.4' and inzoi),
           'MFG Unlock 1.4.4 with Skynizz NR currently fails inZOI startup. '
           'Choose Integrated Ada MFG for this game; restore first if already installed.')
    current = (baseline or {}).get('current') or {}
    installed = ((current.get('archive') or {}).get('release') or {}).get('mfg_component')
    t.need(not current or installed == record, 'Restore before changing MFG components.')
    if not installed:
        for name in ('ReShade64.dll', 'renodx-mfgunlock.addon64'):
            t.need(not (game.target_dir / name).exists(), 'Unmanaged MFG host/addon already exists: ' + name)
        t.need(not e.detect_reshade(game.target_dir)['detected'], 'An unmanaged ReShade proxy is present; restore it before using this MFG package.')
