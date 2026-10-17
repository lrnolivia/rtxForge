"""Windows NR-only policy and verified release adapter for Skynizz OptiScaler."""
from pathlib import Path
import hashlib
import configparser
import json
import re
import stat
import struct
import urllib.request
import zipfile

import transactions as t
import package_catalog

REPO = 'Skynizz/optiscaler-dlss5'
API = 'https://api.github.com/repos/' + REPO
MAX_ARCHIVE = 128 * 1024**2
MAX_EXPANDED = 256 * 1024**2
FILES = {'OptiScaler.dll': 'dxgi.dll', 'OptiScaler.ini': 'OptiScaler.ini',
         'nvngx.dll_dlssnr.dll': 'nvngx.dll_dlssnr.dll'}
DEFAULTS = {
    'Upscalers': {'Dx12Upscaler': 'dlss'},
    'Log': {'LogToFile': 'true', 'LogLevel': '2'},
    'DlssNr': {'Enabled': 'true', 'CacheEnabled': 'true', 'CacheInterval': '1',
               'PreSr': 'true', 'WorkingScale': '0.67', 'JbuUpsample': 'true',
               'CacheRefreshBlend': '1.0', 'WhitePointSource': '3'},
}


def require_mode(system, mode, fallback=False):
    t.need(system == 'windows', 'Skynizz is Windows-only in this release; Proton support is not verified.')
    t.need(mode == 'nr-only' and not fallback,
           'Skynizz currently supports NR Only. Its composition with rtxForge MFG is not verified; use the existing MFG package for MFG.')


def get_json(url):
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'rtxForge'})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(2 * 1024**2 + 1)
    t.need(len(raw) <= 2 * 1024**2, 'Release metadata exceeds the limit')
    return json.loads(raw)


def validate_release(record):
    """Also validate saved releases before repair; never turn state into arbitrary URLs."""
    tag = record.get('tag', '')
    t.need(bool(re.fullmatch(r'v\d+\.\d+\.\d+', tag)), 'Choose latest or a stable Skynizz version such as v1.2.1.')
    name = 'OptiScaler-DLSS5-' + tag[1:] + '-win-x64.zip'
    t.need(record.get('repo') == REPO and record.get('archive') == name
           and record.get('url') == f'https://github.com/{REPO}/releases/download/{tag}/{name}',
           'Untrusted Skynizz release identity')
    t.need(bool(re.fullmatch(r'[0-9a-f]{64}', record.get('sha256', ''))), 'Skynizz release has no verified SHA-256 digest')
    t.need(type(record.get('release_size')) is int and 0 < record['release_size'] <= MAX_ARCHIVE,
           'Skynizz archive size is invalid')
    t.need(bool(re.fullmatch(r'[0-9a-f]{40}', record.get('commit', ''))), 'Skynizz release commit is missing')
    return dict(record, id='skynizz', family='skynizz', name='Skynizz DLSS 5 NR', runtime_verified=False)


def resolve(selection='latest'):
    t.need(isinstance(selection, str) and (selection == 'latest' or re.fullmatch(r'v\d+\.\d+\.\d+', selection)),
           'Choose latest or a stable Skynizz version such as v1.2.1.')
    release = get_json(API + ('/releases/latest' if selection == 'latest' else '/releases/tags/' + selection))
    tag = release.get('tag_name', '')
    t.need(not release.get('draft') and not release.get('prerelease')
           and re.fullmatch(r'v\d+\.\d+\.\d+', tag), 'A stable Skynizz release is required')
    t.need(selection == 'latest' or tag == selection, 'Release tag changed')
    name = f'OptiScaler-DLSS5-{tag[1:]}-win-x64.zip'
    assets = [asset for asset in release.get('assets', []) if asset.get('name') == name]
    t.need(len(assets) == 1, 'No unique supported Windows x64 Skynizz asset in this release')
    asset = assets[0]
    digest = asset.get('digest') or ''
    t.need(re.fullmatch(r'sha256:[0-9a-f]{64}', digest), 'GitHub did not publish a SHA-256 digest for this asset')
    ref = get_json(API + '/git/ref/tags/' + tag).get('object', {})
    if ref.get('type') == 'tag':
        ref = get_json(API + '/git/tags/' + ref['sha']).get('object', {})
    t.need(ref.get('type') == 'commit', 'Release tag does not resolve to a commit')
    return validate_release({'repo': REPO, 'tag': tag, 'archive': name, 'url': asset.get('browser_download_url'),
                             'sha256': digest[7:], 'release_size': asset.get('size'), 'asset_id': asset.get('id'),
                             'commit': ref.get('sha'), 'selected_source': selection})


def amd64(data):
    if len(data) < 64 or data[:2] != b'MZ':
        return False
    offset = struct.unpack_from('<I', data, 60)[0]
    return offset <= len(data) - 6 and data[offset:offset+4] == b'PE\0\0' and data[offset+4:offset+6] == b'\x64\x86'


def load_payload(archive, record):
    record = validate_release(record)
    archive = Path(archive)
    t.need(archive.is_file() and not archive.is_symlink() and archive.absolute() == archive.resolve()
           and archive.stat().st_size == record['release_size'],
           'Skynizz archive size/type mismatch')
    t.need(t.digest(archive) == record['sha256'], 'Skynizz archive SHA-256 mismatch')
    found, seen, total = {}, set(), 0
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        t.need(len(members) <= 1024, 'Skynizz archive has too many members')
        for member in members:
            package_catalog.relative(member.orig_filename.rstrip('/') if member.is_dir() else member.orig_filename)
            name = member.filename.rstrip('/')
            package_catalog.relative(name)
            t.need(name.casefold() not in seen, 'Case-colliding Skynizz archive member')
            seen.add(name.casefold())
            mode = member.external_attr >> 16
            t.need(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR) and not member.flag_bits & 1,
                   'Linked, special or encrypted Skynizz archive member')
            total += member.file_size
            t.need(total <= MAX_EXPANDED and member.file_size <= 64 * 1024**2, 'Expanded Skynizz archive exceeds the limit')
            parts = name.split('/')
            if not member.is_dir() and len(parts) == 2 and parts[0] == 'DLSS5-Optimised' and parts[1] in FILES:
                found[parts[1]] = source.read(member)
    t.need(set(found) == set(FILES), 'Unrecognized Skynizz payload layout; required loader, INI and NR forwarder must be present')
    t.need(amd64(found['OptiScaler.dll']) and amd64(found['nvngx.dll_dlssnr.dll']), 'Skynizz requires AMD64 PE payloads')
    ini = found['OptiScaler.ini'].decode('utf-8-sig')
    t.need('[DlssNr]' in ini and 'CacheEnabled=' in ini and 'PreSr=' in ini, 'Unsupported Skynizz configuration schema')
    t.need(t.digest(archive) == record['sha256'], 'Skynizz archive changed during extraction')
    return {FILES[name]: data for name, data in found.items()}, {
        **record, 'path': str(archive), 'provider': record['name'], 'release': record,
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in found.items()},
    }


def configure(e, source, saved=None):
    """Repair retains the complete user preset, including cache/placement choices."""
    text = (saved if saved is not None else source).decode('utf-8-sig')
    if saved is None:
        for section, values in DEFAULTS.items():
            for key, value in values.items():
                text = e.set_ini_value(text, section, key, value)
    parser = configparser.ConfigParser(interpolation=None, strict=True, inline_comment_prefixes=(';', '#'))
    parser.optionxform = str
    try:
        parser.read_string(text)
    except configparser.Error as error:
        raise t.Refusal('Skynizz configuration could not be parsed: ' + str(error)) from error
    return text, dict(parser['DlssNr']) if parser.has_section('DlssNr') else {}


def check_target(e, game, baseline):
    target = game.target_dir
    t.need(not (target / 'renodx-dlss5.addon64').exists(),
           'Another NR consumer (renodx-dlss5.addon64) is present. Disable it yourself before installing Skynizz.')
    # A second OptiScaler cannot share this INI or the existing MFG hook tree.
    if not baseline:
        t.need(not (target / 'OptiScaler.ini').exists() and not (target / 'OptiScaler').exists(),
               'Existing OptiScaler configuration/runtime is unmanaged. Restore or remove it before installing Skynizz.')
        t.need(not (target / 'nvngx.dll_dlssnr.dll').exists(),
               'An unmanaged NR forwarder is already present. Restore or remove that installation before using Skynizz.')
    else:
        current = baseline.get('current') or {}
        t.need(not current or current.get('provider_id') == 'skynizz', 'Restore the existing provider before switching to Skynizz.')


def scan_rows(rows):
    for row in rows:
        if not row.get('exe'):
            row['blocked'] = 'No Windows executable found'
        elif row.get('anti_cheat'):
            row['blocked'] = 'Anti-cheat detected'
        elif not row.get('native_dlss'):
            row['blocked'] = 'Skynizz needs a native DLSS Super Resolution route; D3D12/DLSS must be used in game.'
        else:
            row['blocked'] = ''
        row['nr_route_note'] = 'NR Only · requires D3D12 with DLSS enabled · MFG composition unverified'
    return rows
