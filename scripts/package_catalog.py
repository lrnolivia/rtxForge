"""Toolkit-independent package discovery. Inspection never executes archive content.

All results are untrusted suggestions until reviewed. Only known payload layouts
can enter an existing deployment adapter; unknown packages remain inspect-only.
"""
from __future__ import annotations
import configparser
import hashlib
import json
import platform
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MAX_ARCHIVE = 2 * 1024**3
MAX_EXPANDED = 4 * 1024**3
MAX_FILES = 4096
MAX_TEXT = 128 * 1024
PARAMETERS = {
    ('DLSSG', 'OverrideInterpolationCount'): ('MFG multiplier', 'auto'),
    ('DlssNr', 'Intensity'): ('NR strength', '2.0'),
    ('Sharpness', 'Sharpness'): ('Sharpening', '0.5'),
}

class PackageError(ValueError):
    pass


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative(name):
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or '\\' in name or ':' in name
            or any(ord(c)<32 or ord(c)==127 for c in name)
            or any(x in ('', '.', '..') or x.endswith((' ', '.'))
                   or re.match(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', x)
                   for x in name.split('/'))):
        raise PackageError('The archive contains an unsafe path: ' + name)
    return p


def catalog(host=None):
    host = host or {'system': platform.system(), 'architecture': platform.machine(), 'ready': False}
    locks = json.loads((ROOT / 'providers/lock.json').read_text())
    supported = (host.get('system') == 'Linux'
                 and host.get('architecture', '').lower() in ('x86_64', 'amd64')
                 and host.get('ready') is True)
    rows = []
    for key in ('dlss-unlocked', 'y4my'):
        record = locks[key]
        rows.append({
            'id': key, 'name': record['name'], 'version': record['tag'],
            'url': 'https://github.com/' + record['repo'],
            'sha256': record['sha256'], 'available': supported,
            'reason': ('Ready to review for your system' if supported else
                       host.get('reason') or 'Verify a supported NVIDIA system first'),
            'summary': ('Native MFG path; NR needs per-game verification' if key == 'dlss-unlocked'
                        else 'Alternative OptiScaler package; a local NR model may be needed'),
            'recommended': key == 'dlss-unlocked' and supported,
        })
    return rows


def inspect_archive(path):
    path = Path(path).absolute()
    if path.is_symlink() or path != path.resolve() or not path.is_file():
        raise PackageError('Choose a regular local archive, not a linked file.')
    if path.stat().st_size > MAX_ARCHIVE:
        raise PackageError('This archive exceeds the 2 GiB inspection limit.')
    if not zipfile.is_zipfile(path):
        raise PackageError('Custom import currently supports ZIP. Curated packages retain their native archive support.')
    before = digest(path)
    warnings = ['Custom source: verify its author before using it. Instructions are read, never executed.']
    entries, texts, seen = [], {}, set()
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > MAX_FILES:
            raise PackageError('Too many files in this archive.')
        total = 0
        for member in members:
            name = member.filename.rstrip('/') if member.is_dir() else member.filename
            relative(name)
            folded = name.casefold()
            if folded in seen:
                raise PackageError('Duplicate or case-colliding archive path: ' + name)
            seen.add(folded)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise PackageError('Archive links and special files are not supported.')
            if member.flag_bits & 1:
                raise PackageError('Encrypted archives cannot be reviewed.')
            if member.file_size > 16*1024**2 and member.file_size/max(1,member.compress_size)>300:
                raise PackageError('Unusually high archive compression ratio; package refused.')
            total += member.file_size
            if total > MAX_EXPANDED or member.file_size > MAX_ARCHIVE:
                raise PackageError('Expanded package exceeds the safety limit.')
            if member.is_dir():
                continue
            entries.append({'path': name, 'bytes': member.file_size})
            leaf = PurePosixPath(name).name.lower()
            is_text = leaf.startswith(('readme', 'install', 'license')) or leaf.endswith('.ini')
            if is_text and member.file_size <= MAX_TEXT:
                texts[name] = archive.read(member).decode('utf-8-sig', errors='replace')
        # A single wrapper directory is common. Do not guess between several payloads.
        ini_paths = [x['path'] for x in entries if PurePosixPath(x['path']).name.casefold() == 'optiscaler.ini']
        prefix = ''
        family, confidence = 'unknown', 'Needs review'
        if len(ini_paths) == 1:
            parent = str(PurePosixPath(ini_paths[0]).parent)
            prefix = '' if parent == '.' else parent + '/'
            names = {x['path'][len(prefix):].casefold() for x in entries if x['path'].startswith(prefix)}
            if {'dxgi.dll', 'optiscaler.ini', 'optiscaler/streamline/sl.interposer.dll', 'optiscaler/streamline/sl.dlss_g.dll'} <= names:
                family, confidence = 'dlss-unlocked', 'Recognized layout; compatibility still needs review'
            elif {'optiscaler.dll', 'optiscaler.ini'} <= names:
                family, confidence = 'optiscaler', 'Suggested from files; adapter review required'
        elif len(ini_paths) > 1:
            warnings.append('Multiple payloads found. Choose a package containing one build.')
        params = []
        if len(ini_paths) == 1 and ini_paths[0] in texts:
            parser = configparser.ConfigParser(interpolation=None, strict=True)
            try:
                parser.read_string(texts[ini_paths[0]])
                for (section, key), (label, default) in PARAMETERS.items():
                    value = parser.get(section, key, fallback=default)
                    params.append({'section': section, 'key': key, 'label': label, 'value': value,
                                   'origin': 'Package config' if parser.has_option(section, key) else 'Suggested default'})
            except configparser.Error:
                warnings.append('The configuration could not be parsed cleanly. Defaults are not assumed.')
        instructions = [{'path': name, 'text': text} for name, text in texts.items()
                        if PurePosixPath(name).name.lower().startswith(('readme', 'install'))]
        commands = sum(bool(re.search(r'(?im)(sudo |curl |wget |powershell|\.\/(?:install|setup)|\.bat\b)', x['text'])) for x in instructions)
        if commands:
            warnings.append('Instructions mention commands. These are informational and will not be run.')
    if digest(path) != before:
        raise PackageError('The archive changed while it was being inspected. Choose it again.')
    return {'schema': 1, 'path': str(path), 'name': path.name, 'sha256': before,
            'archive_bytes': path.stat().st_size, 'expanded_bytes': total, 'files': entries,
            'family': family, 'confidence': confidence, 'prefix': prefix,
            'parameters': params, 'instructions': instructions, 'warnings': warnings,
            'deployable': False}


def validate_parameters(values):
    result = {}
    allowed = {key for _, key in PARAMETERS}
    if set(values) - allowed:
        raise PackageError('Unsupported configuration field.')
    for key, value in values.items():
        if key == 'OverrideInterpolationCount':
            if str(value) not in ('auto', '0', '1', '2', '3', '4', '5'):
                raise PackageError('Choose Auto or an interpolation count from 0 to 5.')
            result[key] = str(value)
        else:
            try:
                number = float(value)
            except (ValueError, TypeError):
                raise PackageError('Enter a number for ' + key) from None
            maximum = 2 if key == 'Intensity' else 1
            if not 0 <= number <= maximum:
                raise PackageError(key + ' must be between 0 and ' + str(maximum))
            result[key] = number
    return result


def custom_record(inspection, values, trusted=False):
    """Bind an explicit review to immutable local bytes, never to README commands."""
    if not trusted:
        raise PackageError('Confirm that you trust the package source before preparing deployment.')
    fresh = inspect_archive(inspection['path'])
    if fresh['sha256'] != inspection['sha256']:
        raise PackageError('Package changed since review; inspect it again.')
    if fresh['family'] != 'dlss-unlocked':
        raise PackageError('This layout has no verified deployment adapter yet. Nothing will be installed.')
    parameters = validate_parameters(values)
    return {'id': 'custom-' + fresh['sha256'][:16], 'family': fresh['family'],
            'name': fresh['name'], 'archive': fresh['name'], 'path': fresh['path'],
            'sha256': fresh['sha256'], 'release_size': fresh['archive_bytes'],
            'tag': 'custom', 'commit': fresh['sha256'], 'asset_id': 0,
            'parameters': parameters, 'trusted': True, 'custom': True}


def load_custom_payload(record):
    """Return bounded, reviewed DLL/config bytes to the existing transaction engine."""
    if record.get('trusted') is not True or record.get('family') != 'dlss-unlocked':
        raise PackageError('Custom package has not been reviewed for this adapter.')
    inspection = inspect_archive(record['path'])
    if inspection['sha256'] != record['sha256'] or inspection['family'] != record['family']:
        raise PackageError('Custom package bytes or layout changed; review again.')
    if record.get('id') != 'custom-' + inspection['sha256'][:16]:
        raise PackageError('Custom package identity mismatch.')
    data = {}
    prefix = inspection['prefix']
    native = {'nvngx_dlss.dll', 'nvngx_dlssd.dll', 'nvngx_dlssg.dll', 'nvapi64.dll'}
    forbidden = {'dlss-enabler-headless.dll', 'dlssg_to_fsr3_amd_is_better.dll'}
    root_allowed = {'dxgi.dll', 'optiscaler.dll', 'optiscaler.ini', 'nvngx_dlssnr.dll', 'nvngx.dll_dlssnr.dll'}
    canonical = {'dxgi.dll':'dxgi.dll', 'optiscaler.dll':'OptiScaler.dll', 'optiscaler.ini':'OptiScaler.ini',
                 'optiscaler':'OptiScaler'}
    with zipfile.ZipFile(record['path']) as archive:
        for entry in inspection['files']:
            source = entry['path']
            if not source.startswith(prefix):
                continue
            rel = source[len(prefix):]
            low = rel.casefold()
            leaf = PurePosixPath(low).name
            if leaf in forbidden or '/dlssg_sm86/' in '/' + low:
                continue
            if '/' not in rel and (leaf in native or leaf.startswith('sl.')):
                raise PackageError('Package replaces native game runtimes at the root; this adapter refuses that layout.')
            allowed = low in root_allowed or (low.startswith('optiscaler/') and low.endswith(('.dll', '.ini', '.json')))
            if not allowed and low.endswith(('.dll','.asi','.addon32','.addon64')):
                raise PackageError('Unrecognized plugin file needs a deployment adapter: '+rel)
            if not allowed:
                continue  # Scripts, executables and other files are never deployed.
            content = archive.read(source)
            if low.endswith('.dll') and content[:2] != b'MZ':
                raise PackageError('A DLL is not a Windows binary: ' + rel)
            parts = rel.split('/')
            parts[0] = canonical.get(parts[0].casefold(), parts[0])
            destination = '/'.join(parts)
            data[destination] = content
    required = {'dxgi.dll','OptiScaler.ini','OptiScaler/streamline/sl.interposer.dll','OptiScaler/streamline/sl.dlss_g.dll'}
    if not required <= set(data):
        raise PackageError('Required files are missing or have unsupported casing.')
    if digest(record['path']) != record['sha256']:
        raise PackageError('Package changed during preparation.')
    return data, {**record, 'provider':record['name'], 'instruction_policy':'read-only'}
