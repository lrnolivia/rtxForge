# Audited discovery helpers derived from the supplied v3.0 base. No installer/cleanup code.
"""
OptiScaler NR + RTX 40 MFG — Bazzite package v2.5.2 CLASSIC PROTON

Linux/Bazzite-native sibling of the Windows v6.4.2 package.

Design goals:
- Discover Steam libraries through Steam's own libraryfolders.vdf/appmanifest data first.
- Fall back to mounted shared-library discovery under /run/media, /mnt, /var/mnt, /media.
- Pin the original y4my4my4m v4 loader + DLSS-G 310.9 path that was Proton-verified.
- Use the exact Streamline 2.14 set bundled with y4my4my4m v4 privately under OptiScaler for MFG output; never replace game-native Streamline DLLs.
- Offer Homebrew `sevenzip` installation when 7zz/7z is missing.
- Scan Steam and known Non-Steam roots.
- Keep Control DX12 and Halo Meteorite executable overrides.
- Block anti-cheat titles by default.
- Move old OptiScaler/ReShade/DLSS5/MFG stack to timestamped backups.
- Never overwrite native game DLSS or Streamline DLLs. v2.5.2 also restores game-native Streamline files previously replaced by v2.1-v2.5.1 when a safe historical backup exists.
- For NR routes, reuse a compatible Ada-patched DLSS-NR runtime when available; otherwise download the verified Linux/Proton standalone source from ShyVortex/dlss-unlocked and extract only its patched nvngx_dlssnr.dll.
- Offer two explicit feature modes: NR + MFG and MFG Only. Both require native DLSS-G evidence.
- Stage NR + MFG at 70% model working scale with moderate OptiScaler RCAS sharpening and enable NR for the next launch.
- Keep OptiScaler.ini writable on Bazzite/Proton and verify direct file + directory write access.
- Default MFG routing is native Streamline DLSS-G input -> private y4my DLSS-G output, with Ada MFG unlock and Blackwell kernels. Enabler remains only as a compatibility fallback.
- Record the exact WINEDLLOVERRIDES line for the actual proxy selected per game.
- Keep manifest-driven rollback/uninstall semantics.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import textwrap
import urllib.request
import zipfile
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable, Optional
VERSION = '3.0'
UPSTREAM_REPO = 'y4my4my4m/OptiScaler_DLSSNR_Multipass_MFG'
UPSTREAM_TAG = 'v10.0.0-dev-fork-y4my4my4m-v4'
UPSTREAM_ASSET = 'OptiScaler_v10.0.0-dev-fork-y4my4my4m-v4_20260905_with_DLSS.7z'
UPSTREAM_ASSET_SHA256 = '9d7824cc9cfb15265bc6438b4638aad74ff9cd6d1d3488ab73724affb386a8b0'
DLSS_UNLOCKED_REPO = 'ShyVortex/dlss-unlocked'
DLSS_UNLOCKED_TAG = 'v0.3.0'
DLSS_UNLOCKED_ASSET = 'dlss-unlocked-standalone-v0.3.0.zip'
DLSS_UNLOCKED_ASSET_SHA256 = 'adf6b2cdcb0b57f3d04fae095135615c9c9f8c6fc8b2bdeccf01cf62672c5183'
HEADLESS_SOURCE_PATH = 'Dll version/dlss-enabler.asi'
HEADLESS_SOURCE_SIZE = 30712320
HEADLESS_SOURCE_GIT_BLOB_SHA1 = '5779bc2d752d6e971015604f2a954f23ffed0fd6'
HEADLESS_NVNGX_INI_PATH = 'Dll version/nvngx.ini'
HEADLESS_NVNGX_INI_SIZE = 14246
HEADLESS_NVNGX_INI_GIT_BLOB_SHA1 = '58925054494eb293d07892f457c262b4b6caaa87'
HEADLESS_ROUTE_ID = 'native-streamline-dlssg-ada-v4'  # legacy constant name; value is the active native route
NR_PROFILE_ID = 'nr70-v1'
NR_STOCK_3108_SHA256 = 'e16bcf15e16e13f527491cdf7845b2fe6521a738d8f7c9c721866a8496e1fc8e'
NR_MIN_SIZE = 100000000
NR_MAX_SIZE = 250000000
NR_CACHE_NAME = 'nvngx_dlssnr.dll'
NR_META_NAME = 'nvngx_dlssnr.source.json'
PREPARATION_POLICY = 'stable-v4-y4my-v4-native-streamline-dlssg-ada-private-sl214'
STREAMLINE_TAG = 'bundled-2.14'
STREAMLINE_LABEL = 'y4my v4 private bundled Streamline 2.14 (game-native Streamline untouched)'
PROXY_PREFERENCE = ['dxgi.dll', 'winmm.dll', 'version.dll', 'dbghelp.dll', 'd3d12.dll', 'wininet.dll', 'winhttp.dll']
KNOWN_PROXY_NAMES = {'dxgi.dll', 'd3d9.dll', 'd3d10.dll', 'd3d11.dll', 'd3d12.dll', 'opengl32.dll', 'winmm.dll', 'version.dll', 'dbghelp.dll', 'wininet.dll', 'winhttp.dll', 'dinput8.dll', 'dsound.dll'}
PROTECTED_NATIVE_NAMES = {'nvngx_dlss.dll', 'nvngx_dlssg.dll', 'nvngx_dlssd.dll'}
NON_STEAM_RELATIVES = [Path('Non-Steam Games'), Path('Non Steam Games'), Path('NonSteam Games'), Path('Games') / 'Non-Steam Games', Path('Games') / 'Non Steam Games', Path('Games') / 'NonSteam Games']
MOUNT_FALLBACKS = [Path('/run/media'), Path('/mnt'), Path('/var/mnt'), Path('/media')]
ANTI_CHEAT_PATTERNS = ['easyanticheat*.exe', 'eanticheat*.exe', 'beservice*.exe', 'bedaisy*.sys', 'start_protected_game.exe', 'ace-*.exe']
ANTI_CHEAT_DIR_NAMES = {'easyanticheat', 'battleye', 'eaanticheat', 'anticheatexpert'}
UPSCALE_NAMES = {'nvngx_dlss.dll', 'nvngx_dlssg.dll', 'nvngx_dlssd.dll', 'libxess.dll', 'libxess_fg.dll', 'amd_fidelityfx_dx12.dll', 'ffx_fsr2_api_dx12_x64.dll', 'ffx_fsr3upscaler_x64.dll'}
IGNORE_DIR_NAMES = {'.git', '.svn', '__pycache__', 'redist', 'redistributables', '_commonredist', 'crashpad', 'crashreportclient', 'digitalextras'}
EXE_BAD_RE = re.compile('(vc_redist|vcredist|redistribut|crashreport|crashpad|unins|setup|installer|bootstrap|easyanticheat|eanticheat|battleye|beservice)', re.I)
LEGACY_FILE_RE = re.compile('(?:dlss5|rtx40mfg|mfg[-_ ]?unlock|renodx[-_ ]?dlss5|dlss5[-_ ]?feed|multipass.*mfg)', re.I)
OPTISCALER_FILE_RE = re.compile('^optiscaler\\.(?:ini|log|asi|dll)$', re.I)
RESH_FILE_RE = re.compile('^reshade', re.I)
LEGACY_DIR_RE = re.compile('^(?:optiscaler|rtx40mfg.*|dlss[-_ ]?5.*)$', re.I)
RESH_DIR_RE = re.compile('^reshade(?:$|[-_ ].*)', re.I)
ANSI = {'red': '\x1b[31m', 'green': '\x1b[32m', 'yellow': '\x1b[33m', 'cyan': '\x1b[36m', 'dim': '\x1b[2m', 'bold': '\x1b[1m', 'reset': '\x1b[0m'}

def color(text: str, name: str) -> str:
    if not sys.stdout.isatty() or os.environ.get('NO_COLOR'):
        return text
    return f"{ANSI[name]}{text}{ANSI['reset']}"

def info(msg: str) -> None:
    print(color(msg, 'cyan'))

def ok(msg: str) -> None:
    print(color(msg, 'green'))

def warn(msg: str) -> None:
    print(color(msg, 'yellow'))

def err(msg: str) -> None:
    print(color(msg, 'red'), file=sys.stderr)

def now_stamp() -> str:
    return dt.datetime.now().strftime('%Y%m%d-%H%M%S')

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def _containment_view(path: Path, root: Path) -> tuple[Path, Path]:
    """Return a containment-safe view without dereferencing the final entry.

    The parent directory is resolved so a symlinked directory cannot escape the
    game root, but the final filename itself is kept lexical.  This matters for
    proxy DLLs that are symlinks: backing up the link is safe even when its
    target lives elsewhere.
    """
    root_real = root.resolve(strict=False)
    parent_real = path.parent.resolve(strict=False)
    candidate = parent_real / path.name
    return (candidate, root_real)

def is_inside(path: Path, root: Path) -> bool:
    try:
        candidate, root_real = _containment_view(path, root)
        candidate.relative_to(root_real)
        return True
    except ValueError:
        return False

def rel_safe(path: Path, root: Path) -> Path:
    candidate, root_real = _containment_view(path, root)
    return candidate.relative_to(root_real)

def human_size(n: int) -> str:
    for unit in ['B', 'KiB', 'MiB', 'GiB']:
        if n < 1024 or unit == 'GiB':
            return f'{n:.1f} {unit}' if isinstance(n, float) else f'{n} {unit}'
        n = n / 1024
    return str(n)

def code_for_index(i: int) -> str:
    out = ''
    n = i + 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out

def iter_walk(root: Path, max_files: int=300000):
    count = 0
    for cur, dirs, files in os.walk(root):
        curp = Path(cur)
        dirs[:] = [d for d in dirs if d.lower() not in IGNORE_DIR_NAMES and (not d.startswith('_OptiScaler_MFG_Backup')) and (not d.startswith('_TRUE_UNINSTALL'))]
        for name in files:
            count += 1
            if count > max_files:
                return
            yield (curp / name)

def parse_vdf_paths(path: Path) -> list[Path]:
    """Extract Steam library paths from modern/legacy libraryfolders.vdf."""
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []
    paths: list[Path] = []
    for m in re.finditer('"path"\\s+"([^"]+)"', text, re.I):
        raw = m.group(1).replace('\\\\', '\\')
        paths.append(Path(raw))
    for m in re.finditer('^\\s*"\\d+"\\s+"([^"]+)"\\s*$', text, re.M):
        paths.append(Path(m.group(1).replace('\\\\', '\\')))
    return paths

def parse_appmanifest(path: Path) -> Optional[dict]:
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None

    def one(key: str) -> Optional[str]:
        m = re.search(f'"{re.escape(key)}"\\s+"([^"]*)"', text, re.I)
        return m.group(1) if m else None
    appid = one('appid')
    name = one('name')
    installdir = one('installdir')
    if not (appid and installdir):
        return None
    return {'appid': appid, 'name': name or installdir, 'installdir': installdir, 'manifest': str(path)}

def steam_roots() -> list[Path]:
    home = Path.home()
    candidates = [home / '.local/share/Steam', home / '.steam/root', home / '.steam/steam', home / '.var/app/com.valvesoftware.Steam/.local/share/Steam']
    out: list[Path] = []
    seen = set()
    for p in candidates:
        try:
            rp = p.resolve(strict=False)
        except OSError:
            rp = p
        if p.exists() and str(rp) not in seen:
            seen.add(str(rp))
            out.append(p)
    return out

def count_manifests(library_root: Path) -> int:
    apps = library_root / 'steamapps'
    if not apps.is_dir():
        return 0
    try:
        return sum((1 for _ in apps.glob('appmanifest_*.acf')))
    except OSError:
        return 0

def candidate_libraries(explicit: Optional[Path]=None) -> list[Path]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
    for sr in steam_roots():
        candidates.append(sr)
        vdf = sr / 'steamapps/libraryfolders.vdf'
        for p in parse_vdf_paths(vdf):
            candidates.append(p.expanduser())
    user = os.environ.get('USER', '')
    fallbacks = list(MOUNT_FALLBACKS)
    if user:
        fallbacks.extend([Path('/run/media') / user, Path('/media') / user])
    for base in fallbacks:
        if not base.is_dir():
            continue
        try:
            for cur, dirs, _files in os.walk(base):
                cp = Path(cur)
                try:
                    depth = len(cp.relative_to(base).parts)
                except ValueError:
                    continue
                if depth >= 5:
                    dirs[:] = []
                if cp.name.lower() == 'steamapps' and (cp / 'common').is_dir():
                    candidates.append(cp.parent)
                    dirs[:] = []
        except (OSError, PermissionError):
            pass
    out: list[Path] = []
    seen = set()
    for p in candidates:
        try:
            rp = p.expanduser().resolve(strict=False)
        except OSError:
            continue
        if not (rp / 'steamapps/common').is_dir():
            continue
        key = str(rp)
        if key not in seen:
            seen.add(key)
            out.append(rp)
    return out

def choose_library(explicit: Optional[Path], assume_yes: bool=False) -> Path:
    import ui
    libs = ui.work("Finding game libraries", candidate_libraries, explicit)
    if not libs:
        raise RuntimeError('No Steam library was found from Steam libraryfolders.vdf or the mounted-library fallbacks.\nUse --library-root /path/to/SteamLibrary to point at it explicitly.')
    scored = sorted(libs, key=lambda p: (count_manifests(p), 'SteamLibrary' in p.name, os.access(p, os.W_OK)), reverse=True)
    if explicit:
        return scored[0]
    shared = [p for p in scored if str(p).startswith(('/run/media/', '/mnt/', '/var/mnt/', '/media/'))]
    if len(shared) == 1:
        return shared[0]
    if len(scored) == 1:
        return scored[0]
    print('\nSteam libraries discovered:')
    for i, p in enumerate(scored, 1):
        tag = 'shared/mounted' if str(p).startswith(('/run/media/', '/mnt/', '/var/mnt/', '/media/')) else 'local'
        print(f'  {i}. {p}  [{count_manifests(p)} manifests, {tag}]')
    default = shared[0] if shared else scored[0]
    if assume_yes or not sys.stdin.isatty():
        ok(f'Using: {default}')
        return default
    raw = input(f'Choose library [default {scored.index(default) + 1}]: ').strip()
    if not raw:
        return default
    try:
        idx = int(raw) - 1
        return scored[idx]
    except Exception:
        raise RuntimeError('Invalid library selection.')

def shared_base_for_library(library: Path) -> Path:
    if library.name.lower() in {'steamlibrary', 'steam'} and str(library).startswith(('/run/media/', '/mnt/', '/var/mnt/', '/media/')):
        return library.parent
    if str(library).startswith(('/run/media/', '/mnt/', '/var/mnt/', '/media/')):
        return library.parent if library.name.lower() != 'common' else library.parent.parent
    return Path.home() / '.local/share/OptiScaler-NR-MFG'

def discover_nonsteam_roots(library: Path, explicit_roots: list[Path]) -> list[Path]:
    roots: list[Path] = []
    base = shared_base_for_library(library)
    for r in explicit_roots:
        if r.is_dir():
            roots.append(r.resolve())
    for rel in NON_STEAM_RELATIVES:
        p = base / rel
        if p.is_dir():
            roots.append(p.resolve())
    for parent in {library.parent, library.parent.parent if library.parent.parent != library.parent else library.parent}:
        for rel in NON_STEAM_RELATIVES:
            p = parent / rel
            if p.is_dir():
                roots.append(p.resolve())
    out, seen = ([], set())
    for p in roots:
        if str(p) not in seen:
            seen.add(str(p))
            out.append(p)
    return out

@dataclass
class Game:
    code: str
    name: str
    root: str
    type: str
    appid: Optional[str] = None
    manifest: Optional[str] = None
    exe: Optional[str] = None
    target_dir: Optional[str] = None
    has_mfg: bool = False
    anti_cheat: Optional[str] = None
    mode: str = 'DLSS NR'
    upscalers: list[str] = field(default_factory=list)

def scan_files(root: Path) -> tuple[list[Path], list[Path], Optional[Path]]:
    upscalers: list[Path] = []
    exes: list[Path] = []
    anti: Optional[Path] = None
    for p in iter_walk(root):
        name = p.name.lower()
        if name in UPSCALE_NAMES or name.startswith('sl.dlss_g'):
            upscalers.append(p)
        if p.suffix.lower() == '.exe' and (not EXE_BAD_RE.search(name)):
            exes.append(p)
        if anti is None:
            for pat in ANTI_CHEAT_PATTERNS:
                if fnmatch.fnmatch(name, pat):
                    anti = p
                    break
            if anti is None and any((part.lower() in ANTI_CHEAT_DIR_NAMES for part in p.parts)):
                anti = p
    return (upscalers, exes, anti)

def score_exe(exe: Path, upscalers: list[Path]) -> int:
    name = exe.name.lower()
    s = str(exe).replace('\\', '/')
    d = exe.parent
    dirs = {str(x.parent.resolve()).lower() for x in upscalers}
    score = 0
    if str(d.resolve()).lower() in dirs:
        score += 5000
    if re.search('(?:-win64-shipping|-wingdk-shipping)\\.exe$', name):
        score += 2500
    if re.search('/Binaries/Win64(?:/|$)', s, re.I):
        score += 1500
    if re.search('/bin/x64(?:/|$)', s, re.I):
        score += 1300
    if re.search('/bin64(?:/|$)', s, re.I):
        score += 1300
    if re.search('/Retail(?:/|$)', s, re.I):
        score += 1000
    if (d / 'nvngx_dlssg.dll').is_file():
        score += 2000
    if (d / 'nvngx_dlss.dll').is_file():
        score += 1500
    if (d / 'sl.dlss_g.dll').is_file():
        score += 1500
    try:
        score += min(250, int(exe.stat().st_size / (1024 * 1024)))
    except OSError:
        pass
    if re.search('launcher|helper|benchmark|report|updater', name, re.I):
        score -= 4000
    if re.search('/Engine/Binaries/ThirdParty/', s, re.I):
        score -= 6000
    if re.search('/DigitalExtras/', s, re.I):
        score -= 10000
    return score

def choose_exe(root: Path, name: str, upscalers: list[Path], exes: list[Path]) -> Optional[Path]:
    control = root / 'Control_DX12.exe'
    if (root.name.lower() == 'control' or 'control' == name.strip().lower()) and control.is_file():
        return control
    if root.name.lower() == 'halo campaign evolved' or 'halo campaign evolved' in name.lower():
        halo = root / 'Meteorite/Binaries/Win64/HaloCampaignEvolved.exe'
        if halo.is_file():
            return halo
        halo_exes = [e for e in exes if e.name.lower() == 'halocampaignevolved.exe' and 'digitalextras' not in str(e).lower()]
        if halo_exes:
            return max(halo_exes, key=lambda e: score_exe(e, upscalers))
    if not exes:
        return None
    return max(exes, key=lambda e: score_exe(e, upscalers))

def inspect_game(game: Game) -> Game:
    root = Path(game.root)
    up, exes, anti = scan_files(root)
    game.upscalers = [str(p) for p in up]
    game.anti_cheat = str(anti) if anti else None
    exe = choose_exe(root, game.name, up, exes)
    if exe:
        game.exe = str(exe)
        game.target_dir = str(exe.parent)
    game.has_mfg = any((p.name.lower() in {'nvngx_dlssg.dll', 'sl.dlss_g.dll'} for p in up))
    game.mode = 'Native DLSS-G detected · Ada MFG capable' if game.has_mfg else 'No native DLSS-G detected'
    return game

def is_library_tool(name, appid=None):
    """Conservative local exclusions; do not require network metadata to scan."""
    if str(appid) in {'993090', '431960', '250820', '228980', '1070560', '1391110', '1628350', '1493710'}:
        return True
    name = name.casefold().strip()
    return bool(re.match(r'^(?:proton(?:\s|$|[-_])|steam linux runtime(?:\s|$)|steamworks shared(?:\s|$)|steamworks common redistributables$|steam runtime(?:\s|$)|soldier$|sniper$)', name)) or name in {
        'lossless scaling', 'wallpaper engine', 'steamvr', 'retroarch',
        'obs studio', 'blender', 'fps monitor', 'displayfusion', 'borderless gaming',
    }

def discover_games(library: Path, nonsteam_roots: list[Path], include_unavailable: bool=False) -> list[Game]:
    games: list[Game] = []
    steamapps = library / 'steamapps'
    common = steamapps / 'common'
    for mf in sorted(steamapps.glob('appmanifest_*.acf')):
        data = parse_appmanifest(mf)
        if not data or is_library_tool(data['name'], data['appid']):
            continue
        root = common / data['installdir']
        if root.is_dir():
            games.append(Game('', data['name'], str(root), 'Steam', data['appid'], str(mf)))
    for nsroot in nonsteam_roots:
        try:
            for child in sorted(nsroot.iterdir(), key=lambda p: p.name.lower()):
                if child.is_dir() and (not child.name.startswith('.')) and not is_library_tool(child.name):
                    games.append(Game('', child.name, str(child), 'Non-Steam'))
        except (OSError, PermissionError):
            pass
    inspected: list[Game] = []
    for g in games:
        g = inspect_game(g)
        if include_unavailable or (g.exe and g.upscalers):
            inspected.append(g)
    inspected.sort(key=lambda g: (g.type != 'Steam', g.name.lower()))
    for i, g in enumerate(inspected):
        g.code = code_for_index(i)
    return inspected

def print_games(games: list[Game]) -> None:
    print('\nEligible game scan:')
    for g in games:
        blocked = f" {color('[BLOCKED: anti-cheat]', 'red')}" if g.anti_cheat else ''
        mfg = 'MFG' if g.has_mfg else 'NR'
        aid = f' / AppID {g.appid}' if g.appid else ''
        print(f'  {g.code:>3}  {g.name} [{g.type}{aid}] [{mfg}]{blocked}')
        print(color(f'       EXE: {g.exe}', 'dim'))
        if g.anti_cheat:
            print(color(f'       Anti-cheat evidence: {g.anti_cheat}', 'dim'))

def get_ini_section(path: Path, section: str) -> dict[str, str]:
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return {}
    current = None
    out: dict[str, str] = {}
    for line in lines:
        s = line.strip()
        m = re.match('^\\[([^\\]]+)\\]$', s)
        if m:
            current = m.group(1)
            continue
        if current and current.lower() == section.lower() and ('=' in s) and (not s.startswith((';', '#'))):
            k, v = s.split('=', 1)
            out[k.strip()] = v.strip()
    return out

def get_ini_values_all(path: Path) -> dict[str, dict[str, str]]:
    """Return every ordinary key/value in an INI, grouped by section.

    This intentionally ignores comments and formatting.  On an upstream update we
    use the newest upstream INI as the template, then overlay the user's saved
    values so newly-added upstream settings/comments arrive without discarding
    menu changes the user already saved.
    """
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return {}
    current: Optional[str] = None
    out: dict[str, dict[str, str]] = {}
    for line in lines:
        s = line.strip()
        m = re.match('^\\[([^\\]]+)\\]$', s)
        if m:
            current = m.group(1)
            out.setdefault(current, {})
            continue
        if current and '=' in s and (not s.startswith((';', '#'))):
            k, v = s.split('=', 1)
            out.setdefault(current, {})[k.strip()] = v.strip()
    return out
