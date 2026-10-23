"""Pinned Universal MFG Unlocker, loaded by Skynizz's OptiScaler 10 as an ASI plugin.

The game's own Streamline DLSS Frame Generation stays the frame-generation path.
The plugin replaces the bridge's integrated Ada unlock; OptiScaler's menu and INI
own the multiplier, and the unlocker's separate menu stays hidden.
"""
from pathlib import Path
import copy
import hashlib
import json
import zipfile

import packages
import skynizz_provider
import transactions as t
from storage import storage

ROOT = Path(__file__).resolve().parents[1]
ID = 'universal'
REPO = 'dashdogy/MFG-Unlocker'
PLUGIN = 'OptiScaler/plugins/MFGUnlocker.asi'
MEMBER = 'MFGUnlocker.dll'
# version: (commit, archive sha256, archive size, dll sha256, dll size)
KNOWN = {
    '1.6.1': ('29504cdd5d209a25e3b91e809a7e0d6f9db8cbdc',
              'abe4d6ae7eab1ea4cacc4775b05521c459516ed72f434784e4420080571e87c5', 2713094,
              '24e3e6a8c07639fd9cbd79274e4eb21cc65a13f0453e1157720620c3d6286b33', 7353344),
}
# Upstream notices from the pinned commit, installed beside OptiScaler's other licenses.
NOTICES = {'LICENSE': 'MFG-Unlocker-LICENSE.txt', 'NOTICE.md': 'MFG-Unlocker-NOTICE.md'}
# A manual install hides under a proxy name; these are the files that give it away.
FOREIGN_PREFIXES = ('mfgunlocker', 'rtxmfg', 'rtx40mfg')
# Written by the plugin beside the game executable on every run.
STATUS = 'RTXMFG-Universal.status.json'


def pinned():
    source = json.loads((ROOT / 'providers/mfg-unlocker/source.json').read_text(encoding='utf-8'))
    dll = source['files'][MEMBER]
    record = {
        'id': ID, 'version': source['version'], 'repo': source['repo'], 'commit': source['commit'],
        'url': source['url'], 'archive': source['archive'], 'sha256': source['sha256'],
        'release_size': source['release_size'], 'dll': {'sha256': dll['sha256'], 'size': dll['size']},
        'notices': {name: {'url': f"https://raw.githubusercontent.com/{source['repo']}/{source['commit']}/{name}",
                           'sha256': notice['sha256'], 'release_size': notice['size']}
                    for name, notice in source['notices'].items()},
    }
    return validate(record)


def validate(record):
    t.need(isinstance(record, dict) and record.get('id') == ID and record.get('version') in KNOWN,
           'Unsupported Universal MFG component')
    version = record['version']
    commit, digest, size, dll_digest, dll_size = KNOWN[version]
    t.need(record.get('repo') == REPO and record.get('commit') == commit
           and record.get('sha256') == digest and record.get('release_size') == size
           and record.get('archive') == f'MFGUnlocker-v{version}.zip'
           and record.get('url') == f'https://github.com/{REPO}/releases/download/v{version}/MFGUnlocker-v{version}.zip'
           and record.get('dll') == {'sha256': dll_digest, 'size': dll_size},
           'Untrusted Universal MFG release identity')
    notices = record.get('notices') or {}
    t.need(set(notices) == set(NOTICES), 'Universal MFG license notices are incomplete')
    for name, notice in notices.items():
        t.need(notice.get('url') == f'https://raw.githubusercontent.com/{REPO}/{commit}/{name}'
               and isinstance(notice.get('sha256'), str) and len(notice['sha256']) == 64
               and type(notice.get('release_size')) is int and 0 < notice['release_size'] < 65536,
               'Untrusted Universal MFG license notice identity')
    return copy.deepcopy(record)


def _read(path, digest, size):
    path = Path(path)
    t.need(path.is_file() and not path.is_symlink() and path.stat().st_size == size, 'Universal MFG file size/type mismatch')
    data = path.read_bytes()
    t.need(hashlib.sha256(data).hexdigest() == digest, 'Universal MFG SHA-256 mismatch')
    return data


def load_payload(config, record):
    """The plugin from the exact release member, never by extracting arbitrary paths."""
    record = validate(record)
    cache = storage(config, 32 * 1024**2) / 'packages' / record['sha256']
    archive = packages.download(record['url'], cache / record['archive'], expected=record['sha256'], size=record['release_size'])
    _read(archive, record['sha256'], record['release_size'])
    with zipfile.ZipFile(archive) as bundle:
        members = [info for info in bundle.infolist() if info.filename == MEMBER]
        t.need(len(members) == 1 and members[0].file_size == record['dll']['size'], 'Universal MFG release member mismatch')
        dll = bundle.read(members[0])
    t.need(hashlib.sha256(dll).hexdigest() == record['dll']['sha256'] and skynizz_provider.amd64(dll),
           'Universal MFG plugin architecture/hash mismatch')
    data = {PLUGIN: dll}
    for name, notice in record['notices'].items():
        path = packages.download(notice['url'], cache / NOTICES[name], expected=notice['sha256'], size=notice['release_size'])
        data['OptiScaler/licenses/' + NOTICES[name]] = _read(path, notice['sha256'], notice['release_size'])
    return data


def configure(e, text):
    """OptiScaler loads the plugin; the bridge's integrated unlock steps aside for it."""
    for key in ('AdaMfgUnlock', 'AdaBlackwellKernels', 'AmpereMfgUnlock'):
        text = e.set_ini_value(text, 'DLSSG', key, 'false')
    return e.set_ini_value(text, 'Plugins', 'LoadAsiPlugins', 'true')


def check_target(e, game, baseline):
    """Never stack on a manual unlocker install or switch a game's recorded MFG component."""
    record = validate(e.Y4MY_PROVIDER['mfg_component'])
    current = (baseline or {}).get('current') or {}
    installed = ((current.get('archive') or {}).get('release') or {}).get('mfg_component')
    t.need(not current or installed == record, 'Restore before changing MFG components.')
    if installed:
        return
    target = game.target_dir
    t.need(not (target / PLUGIN).exists(), 'An unmanaged MFG Unlocker plugin already exists; restore it first.')
    for path in target.iterdir():
        name = path.name.casefold()
        # The plugin's own run reports outlive a restore; they are not an install.
        if name.startswith('rtxmfg-') and name.endswith(('.log', '.status.json', '-intervals.csv')):
            continue
        t.need(not name.startswith(FOREIGN_PREFIXES),
               'An unmanaged MFG Unlocker install is present (' + path.name + '); remove it before installing.')


def dynamic_support(target):
    """What the plugin reported on the game's last run: True, False, or None before any report."""
    path = Path(target) / STATUS
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024**2:
            return None
        status = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None
    if not isinstance(status, dict) or status.get('dynamicMfgSupportKnown') is not True:
        return None
    return status.get('dynamicMfgSupported') is True
