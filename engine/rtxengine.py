#!/usr/bin/env python3
"""
rtxEngine · Terminal Edition v13
===================================================

Linux/Bazzite-first terminal engine.

What this terminal engine does:
- scans the mounted Windows G: game drive automatically
- discovers Steam libraries from appmanifest files
- discovers known and fallback non-Steam game roots
- scores/selects the likely game executable automatically
- shows ALL discovered games in one table
- installs the pinned y4my OptiScaler Multipass MFG v4 stack to many games or ALL eligible games at once
- restores/uninstalls many games or ALL installed games at once
- audits many games or ALL installed games at once
- refuses anti-cheat titles
- treats the pinned y4my v4 with-DLSS release as ONE integrated Proton stack
- keeps a verified baseline backup per target
- repairs permissions only on conflicting old mod paths it must replace
- records interrupted installs as recovery state instead of installed state
- self-heals stale v2/v3/v4/v5 baseline-backup directories after uninstall/failed backup
- can baseline permission-locked old OptiScaler trees via sudo tar before repairing them
- can baseline permission-locked root package files (such as OptiScaler.ini) via sudo tar before repair
- preserves ReShade and uses version.dll for the rtxEngine-managed stack when needed
- on RTX 40/Ada, uses y4my v4 native Ada MFG and DLSS Neural Rendering from the same OptiScaler build
- writes a batch launch-options report
- can safely merge rtxEngine-owned launch options directly into Steam and non-Steam shortcuts
- preserves each game's previous LaunchOptions and restores them on uninstall
- validates the y4my release archive by the publisher-provided GitHub SHA-256 before mutation
- offers a destructive Deep Clean mode for graphics-mod debris with thin receipts
- preserves NVIDIA/Streamline runtime DLLs that DLSS Updater may maintain
- can launch Steam file verification after a Steam-game deep clean
- offers an exact Steam Pristine Reset that wipes a validated Steam install tree and rebuilds it through Steam verification

It deliberately does NOT ask the user to browse to individual .exe files.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import datetime as _dt
import fnmatch
import fcntl
import functools
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import time
import subprocess
import sys
import tarfile
import tempfile
import zipfile
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Optional

APP_NAME = "rtxEngine · Terminal Edition"
ENGINE_SCHEMA = 13
HOME = Path.home()

# Windows G: on the user's shared BTRFS games volume under Bazzite.
DRIVE_CANDIDATES = (
    Path("/var/mnt/Games"),
    Path("/run/media") / os.environ.get("USER", "") / "Games",
    Path("/mnt/Games"),
    Path("/media") / os.environ.get("USER", "") / "Games",
)
DEFAULT_DOWNLOAD_DIR = HOME / "Downloads" / "Compressed"
STATE_ROOT = Path(
    os.environ.get(
        "RTXFORGE_DLSS_UNLOCKED_STATE",
        str(HOME / ".local" / "state" / "rtxforge-dlss-unlocked"),
    )
)

SCRIPT_DIR = Path(__file__).resolve().parent

Y4MY_PROVIDER = {
    "name": "y4my OptiScaler Multipass MFG v4",
    "tag": "v10.0.0-dev-fork-y4my4my4m-v4",
    "commit": "7b7220bbb4994a9c8ae60cfc75a44cb67995efb8",
    "archive": "OptiScaler_v10.0.0-dev-fork-y4my4my4m-v4_20260905_with_DLSS.7z",
    "sha256": "9d7824cc9cfb15265bc6438b4638aad74ff9cd6d1d3488ab73724affb386a8b0",
    "url": "https://github.com/y4my4my4m/OptiScaler_DLSSNR_Multipass_MFG/releases/download/v10.0.0-dev-fork-y4my4my4m-v4/OptiScaler_v10.0.0-dev-fork-y4my4my4m-v4_20260905_with_DLSS.7z",
    "asset_id": 546163906,
    "release_size": 117366545,
}
Y4MY_CACHE_DIR = HOME / ".cache" / "rtxEngine" / "providers" / "y4my-v4"

# y4my deliberately does not redistribute NVIDIA's Neural Rendering model DLL.
# rtxEngine therefore keeps the runtime OUT of this package and bootstraps a
# family-specific, version- and SHA-pinned archive only when no explicit/local
# copy is available. These are community compatibility builds mirrored by RHI,
# not official NVIDIA distribution assets; archive bytes are never accepted by
# version/name alone. Existing game-local copies still take precedence later in
# install_target, and --nr-runtime remains a strict user override.
NR_RUNTIME_NAME = "nvngx_dlssnr.dll"
NR_RUNTIME_MIN_BYTES = 32 * 1024 * 1024
NR_RUNTIME_PROVIDERS = {
    "ada": {
        "name": "DLSS NR 310.8.0-RTX40",
        "tag": "dlssnr-310.8.0-RTX40",
        "archive": "nvngx_dlssnr_310.8.0-RTX40.zip",
        "sha256": "46124cfaef532ad5f6da07494772ea8c1b3e719f934e254385697f38d1289e3f",
        "url": "https://github.com/RankFTW/rhi-repo/releases/download/dlssnr-310.8.0-RTX40/nvngx_dlssnr_310.8.0-RTX40.zip",
        "release_size": 110604522,
    },
    "sm86": {
        "name": "DLSS NR 310.8.SF-v2",
        "tag": "dlssnr-310.8.SF-v2",
        "archive": "nvngx_dlssnr_310.8.SF-v2.zip",
        "sha256": "1da35941894994eb087e017577829e492454e9bae3a6a9397027069ceb74955c",
        "url": "https://github.com/RankFTW/rhi-repo/releases/download/dlssnr-310.8.SF-v2/nvngx_dlssnr_310.8.SF-v2.zip",
        "release_size": 116693212,
    },
}

# The release archive contains OptiScaler.dll and its companion tree. rtxEngine
# renames only OptiScaler.dll to the selected Wine proxy, matching y4my/upstream
# Linux setup guidance. The NVIDIA DLSS/Streamline stack stays under OptiScaler/.
Y4MY_REQUIRED_FILES = (
    "OptiScaler.dll",
    "OptiScaler.ini",
    "nvngx.dll_dlssnr.dll",
    "OptiScaler/nvngx_dlss.dll",
    "OptiScaler/nvngx_dlssd.dll",
    "OptiScaler/nvngx_dlssg.dll",
    "OptiScaler/streamline/sl.interposer.dll",
    "OptiScaler/streamline/sl.common.dll",
    "OptiScaler/streamline/sl.dlss_g.dll",
)

# Legacy provider metadata retained only for state recovery compatibility.
RTXMFG_PROVIDER = {
    "version": "v1.3.2",
    "archive": "RTXMFG-v1.3.2.zip",
    "sha256": "7baec084500bcc806be488c17b4822fdef0ecc802fd7d23c5be8184fbe660811",
    "url": "https://github.com/dashdogy/RTX40MFG-Unlock/releases/download/v1.3.2/RTXMFG-v1.3.2.zip",
}
RTXMFG_CACHE_DIR = HOME / ".cache" / "rtxforge" / "providers"

# OptiScaler officially supports these proxy filenames.  RC2 uses actual PE
# import evidence to prefer a loader name the game is guaranteed to request,
# while retaining dxgi/version fallbacks for titles that load them dynamically.
OPTISCALER_SUPPORTED_PROXY_NAMES = (
    # Prefer ordinary imported Win32 loaders before graphics-system DLLs.
    # They give Proton a deterministic early load while reducing DXGI/D3D12
    # loader collisions. Cyberpunk, for example, officially supports wininet.
    "wininet.dll",
    "winhttp.dll",
    "winmm.dll",
    "dbghelp.dll",
    "dxgi.dll",
    "version.dll",
    "d3d12.dll",
)

# Legacy external RTXMFG helpers are retained for recovery/testing only.
RTXMFG_SUPPORTED_PROXY_NAMES = (
    "version.dll",
    "winmm.dll",
    "dinput8.dll",
    "winhttp.dll",
    "wininet.dll",
    "dsound.dll",
    "xinput1_4.dll",
    "xinput1_3.dll",
    "xinput1_2.dll",
    "xinput1_1.dll",
    "xinput9_1_0.dll",
    "d3d11.dll",
    "d3d10.dll",
    "d3d9.dll",
    "d3d12.dll",
    "dxgi.dll",
)

CORE_ROOT = {
    "dxgi.dll",  # normalized placeholder for the release's OptiScaler.dll
    "OptiScaler.ini",
    "nvngx.dll_dlssnr.dll",
}
REQUIRED_PREFIXES = {
    "OptiScaler/",
    "OptiScaler/streamline/",
    "Licenses/",
}
PROXY_NAMES = OPTISCALER_SUPPORTED_PROXY_NAMES


ANTI_CHEAT_PATTERNS = (
    "easyanticheat*.exe",
    "eanticheat*.exe",
    "beservice*.exe",
    "bedaisy*.sys",
    "start_protected_game.exe",
    "ace-*.exe",
)
ANTI_CHEAT_DIRS = {
    "easyanticheat",
    "battleye",
    "eaanticheat",
    "anticheatexpert",
}
IGNORE_DIRS = {
    ".git", ".svn", "__pycache__", "redist", "redistributables",
    "_commonredist", "crashpad", "crashreportclient", "digitalextras",
    "ada-lab", "_optiscaler_mfg_backups", "_true_uninstall",
    "system volume information", "$recycle.bin",
}
EXE_BAD_RE = re.compile(
    r"(vc_redist|vcredist|redistribut|crashreport|crashpad|unins|setup|installer|"
    r"bootstrap|easyanticheat|eanticheat|battleye|beservice|updater|"
    r"benchmark|helper)",
    re.I,
)

NONSTEAM_NAMES = (
    "Non-Steam Games",
    "Non Steam Games",
    "NonSteam Games",
    "Non-Steam",
    "Non Steam",
)
TOOLS_APPIDS = {
    "993090", "431960", "250820", "228980", "1070560",
    "1391110", "1628350", "1493710",
}

# Deep Clean -----------------------------------------------------------------
#
# Deep Clean is intentionally narrower than "delete every unknown file".  Steam
# verification repairs missing/changed official files, but it does not provide a
# trustworthy local list of every non-shipped extra file for us to compare
# against.  We therefore remove known graphics-mod families and strong binary
# signatures, while preserving NVIDIA/Streamline runtime DLLs that the game may
# ship or DLSS Updater may have refreshed.
DEEP_CLEAN_DIR_NAMES = {
    "optiscaler",
    "reshade",
    "reshade-shaders",
    "renodx",
    "dlss-enabler",
    "dlssenabler",
    "dlsstweaks",
    "_dlss5_backup",
    "_optiscaler_mfg_backups",
    "_true_uninstall",
}

DEEP_CLEAN_FILE_PREFIXES = (
    "optiscaler",
    "rtxmfg",
    "renodx",
    "dlss5-feed",
    "dlss-enabler",
    "dlssenabler",
    "dlsstweaks",
    "dlssg_to_fsr3",
    "dlssg-to-fsr3",
    "fsr2fsr3",
    "uniscaler",
)

DEEP_CLEAN_EXACT_FILES = {
    "optiscaler.ini",
    "optiscaler.log",
    "optiscaler.log.bak",
    "rtxmfg-universal.json",
    "rtxmfg.log",
    "rtxmfg-universal.log",
    "nvngx_dlssnr.dll",
    "nvngx.dll_dlssnr.dll",
    "renodx-dlss5.addon64",
    "renodx-dlss5.addon32",
    "renodx-dlss5.addon",
    "dlss5-feed.addon64",
    "dlss5-feed.addon32",
    "dlss5-feed-host64.exe",
    "dlss5-feed.cfg",
    "dlss5_feed.fx",
    "reshade64.dll",
    "reshade32.dll",
}

DEEP_CLEAN_PROXY_NAMES = {
    *{name.casefold() for name in OPTISCALER_SUPPORTED_PROXY_NAMES},
    *{name.casefold() for name in RTXMFG_SUPPORTED_PROXY_NAMES},
    "opengl32.dll",
    # DLSSTweaks can also wrap through these names. They are only removed
    # when binary signature evidence identifies a graphics injector.
    "nvngx.dll",
    "xapofx1_5.dll",
    "x3daudio1_7.dll",
}

DEEP_CLEAN_BINARY_MARKERS = (
    b"optiscaler",
    b"reshade",
    b"rtxmfg",
    b"rtx40mfg",
    b"dlss enabler",
    b"dlss-enabler",
    b"dlsstweaks",
    b"uniscaler",
    b"dlssg_to_fsr3",
    b"dlssg-to-fsr3",
    b"dlssgtofsr3",
    b"fsr2fsr3",
    b"renodx",
)

# Preserve the ordinary NVIDIA/Streamline runtime family outside known mod
# directories.  This is the compatibility boundary for DLSS Updater.
DEEP_CLEAN_EXPLICIT_NR_FILES = {"nvngx_dlssnr.dll", "nvngx.dll_dlssnr.dll"}

# ANSI -----------------------------------------------------------------------

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

def _ansi(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s

def bold(s: str) -> str: return _ansi("1", s)
def cyan(s: str) -> str: return _ansi("38;2;93;220;232", s)
def green(s: str) -> str: return _ansi("38;2;118;185;0", s)
def yellow(s: str) -> str: return _ansi("38;2;255;200;87", s)
def red(s: str) -> str: return _ansi("38;2;255;111;105", s)
def dim(s: str) -> str: return _ansi("2", s)

def clear() -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")

def banner() -> None:
    print()
    print("  " + bold("rtxEngine") + "  " + green("TERMINAL EDITION · DLSS UNLOCKED v13"))
    print("  " + dim("DLSS NR + NATIVE ADA MFG · y4my v4 UNIFIED ENGINE"))
    print("  " + green("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"))
    print("  Scan G:. Pick games. Install or restore as one batch.")
    print()

def heading(s: str) -> None:
    print("\n  " + cyan(s))

def kv(k: str, v: object, width: int = 21) -> None:
    print("  " + dim(k.ljust(width)) + str(v))

def ok(s: str) -> None:
    print("  " + green("✓ ") + s)

def warn(s: str) -> None:
    print("  " + yellow("! ") + s)

def fail(s: str) -> None:
    print("  " + red("STOP  ") + s, file=sys.stderr)

def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"  {prompt}{suffix}: ").strip()
    return value or (default or "")

def confirm(prompt: str, default: bool = False) -> bool:
    tail = " [Y/n]" if default else " [y/N]"
    raw = input(f"  {prompt}{tail}: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}

class Stop(RuntimeError):
    pass

def require(cond: bool, message: str) -> None:
    if not cond:
        raise Stop(message)

# Generic helpers ------------------------------------------------------------

def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")

def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def human_size(n: int) -> str:
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"

def safe_rel(name: str) -> str:
    name = name.replace("\\", "/")
    p = PurePosixPath(name)
    require(name and not p.is_absolute(), f"Unsafe archive path: {name!r}")
    require(all(part not in {"", ".", ".."} for part in p.parts), f"Unsafe archive path: {name!r}")
    require(":" not in name, f"Unsafe archive path: {name!r}")
    return p.as_posix()

def target_key(target_dir: Path) -> str:
    return hashlib.sha256(str(target_dir.resolve()).encode("utf-8")).hexdigest()[:20]

def _fsync_dir(path: Path) -> None:
    """Best-effort directory durability barrier for recovery/state boundaries."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def _mkdir_durable(path: Path, mode: int = 0o755) -> None:
    """Create a directory chain and durably commit every new parent entry."""
    path = Path(path)
    missing = []
    cur = path
    while not cur.exists():
        missing.append(cur)
        parent = cur.parent
        require(parent != cur, f"Could not find existing parent for directory: {path}")
        cur = parent
    require(cur.is_dir(), f"Directory parent is not a directory: {cur}")
    for directory in reversed(missing):
        directory.mkdir(mode=mode)
        _fsync_dir(directory)
        _fsync_dir(directory.parent)

def _fsync_file(path: Path) -> None:
    require(path.is_file() and not path.is_symlink(), f"Cannot fsync unsafe file: {path}")
    with path.open("rb") as f:
        os.fsync(f.fileno())

def _fsync_tree(root: Path) -> None:
    """Flush a recovery-critical ordinary tree before state depends on it."""
    require(root.is_dir() and not root.is_symlink(), f"Cannot fsync unsafe tree: {root}")
    dirs = [root]
    for path in sorted(root.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        require(not path.is_symlink(), f"Symlink inside fsync tree refused: {path}")
        if path.is_file():
            _fsync_file(path)
        elif path.is_dir():
            dirs.append(path)
    for directory in sorted(set(dirs), key=lambda x: len(x.parts), reverse=True):
        _fsync_dir(directory)
    _fsync_dir(root.parent)

def _sync_filesystem(path: Path) -> None:
    """Flush privileged restore output when individual files may be unreadable."""
    sync_bin = shutil.which("sync")
    if sync_bin:
        subprocess.run([sync_bin, "-f", str(path)], check=True)
    elif hasattr(os, "sync"):
        os.sync()

def durable_replace(src: Path, dst: Path) -> None:
    """Rename/replace and make the resulting directory entry crash-durable."""
    src_parent = src.parent
    dst_parent = dst.parent
    os.replace(src, dst)
    _fsync_dir(dst_parent)
    if src_parent != dst_parent:
        _fsync_dir(src_parent)

def durable_unlink(path: Path, *, missing_ok: bool = False) -> None:
    """Unlink a state/transaction name and durably commit that deletion."""
    try:
        path.unlink()
    except FileNotFoundError:
        if not missing_ok:
            raise
        return
    _fsync_dir(path.parent)

_MUTATION_LOCK_FD: Optional[int] = None
_MUTATION_LOCK_DEPTH = 0

@contextmanager
def mutation_lock():
    """Serialize rtxEngine writers across processes, reentrantly in-process."""
    global _MUTATION_LOCK_FD, _MUTATION_LOCK_DEPTH
    if _MUTATION_LOCK_DEPTH:
        _MUTATION_LOCK_DEPTH += 1
        try:
            yield
        finally:
            _MUTATION_LOCK_DEPTH -= 1
        return

    _mkdir_durable(STATE_ROOT)
    lock_path = STATE_ROOT / ".writer.lock"
    require(not lock_path.is_symlink(), f"rtxEngine writer lock symlink refused: {lock_path}")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(lock_path, flags, 0o600)
    acquired = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError as exc:
            owner = ""
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                owner = os.read(fd, 256).decode("utf-8", errors="replace").strip()
            except OSError:
                pass
            detail = f" ({owner})" if owner else ""
            raise Stop(f"Another rtxEngine mutating operation is already running{detail}") from exc

        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, f"pid={os.getpid()} started={now_iso()}\n".encode("utf-8"))
        os.fsync(fd)
        _fsync_dir(lock_path.parent)
        _MUTATION_LOCK_FD = fd
        _MUTATION_LOCK_DEPTH = 1
        try:
            yield
        finally:
            _MUTATION_LOCK_DEPTH = 0
            _MUTATION_LOCK_FD = None
    finally:
        if acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)

def serialized_mutation(fn):
    """Decorator for top-level state/game/Steam mutation workflows."""
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        with mutation_lock():
            return fn(*args, **kwargs)
    return wrapped

def atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
    _mkdir_durable(path.parent)
    tmp = path.with_name(f".{path.name}.rtxforge-new")
    if tmp.exists():
        tmp.unlink()
    with tmp.open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, mode)
    durable_replace(tmp, path)

def copy_verified(src: Path, dst: Path) -> None:
    """Copy recovery-critical bytes, verify them, then flush bytes + name."""
    _mkdir_durable(dst.parent)
    tmp = dst.with_name(f".{dst.name}.rtxforge-copy-{os.getpid()}-{time.time_ns()}")
    require(not tmp.exists(), f"Temporary recovery copy already exists: {tmp}")
    try:
        shutil.copy2(src, tmp)
        require(sha256_file(src) == sha256_file(tmp), f"Backup verification failed: {src}")
        _fsync_file(tmp)
        durable_replace(tmp, dst)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    require(sha256_file(src) == sha256_file(dst), f"Backup verification failed after commit: {src}")

def directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for p in path.rglob("*"):
        if p.is_file() and not p.is_symlink():
            total += p.stat().st_size
    return total

def code_for_index(index: int) -> str:
    out = ""
    n = index + 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out

# Drive / Steam discovery ----------------------------------------------------

def detect_drive(explicit: Optional[str] = None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        require(p.is_dir(), f"Game drive not found: {p}")
        return p
    for p in DRIVE_CANDIDATES:
        if str(p).endswith("/Games") and p.is_dir():
            return p.resolve()
    raise Stop(
        "Could not find the mounted G: games drive. "
        "Run with --drive /path/to/mounted/Games if its mount changed."
    )

def parse_vdf_one(text: str, key: str) -> Optional[str]:
    m = re.search(rf'"{re.escape(key)}"\s+"([^"]*)"', text, re.I)
    return m.group(1) if m else None

def parse_appmanifest(path: Path) -> Optional[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    appid = parse_vdf_one(text, "appid")
    name = parse_vdf_one(text, "name")
    installdir = parse_vdf_one(text, "installdir")
    if not appid or not installdir:
        return None
    return {
        "appid": appid,
        "name": name or installdir,
        "installdir": installdir,
        "manifest": str(path),
    }

def safe_steam_installdir(value: object) -> Optional[str]:
    """Return a canonical direct steamapps/common child name or None."""
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    if value in {".", ".."} or "/" in value or "\\" in value:
        return None
    if PurePosixPath(value).name != value:
        return None
    return value

def is_tool(name: str, appid: Optional[str] = None) -> bool:
    if appid in TOOLS_APPIDS:
        return True
    low = name.casefold().strip()
    if re.match(
        r"^(?:proton(?:\s|$|[-_])|steam linux runtime(?:\s|$)|"
        r"steamworks shared(?:\s|$)|steamworks common redistributables$|"
        r"steam runtime(?:\s|$)|soldier$|sniper$)",
        low,
    ):
        return True
    return low in {
        "lossless scaling", "wallpaper engine", "steamvr", "retroarch",
        "obs studio", "blender", "fps monitor", "displayfusion",
        "borderless gaming",
    }

def find_steam_libraries(drive: Path) -> list[Path]:
    """Find every Steam library actually present anywhere on G:."""
    out: list[Path] = []
    seen = set()

    # Fast likely locations first.
    likely = [
        drive,
        drive / "SteamLibrary",
        drive / "Steam Library",
        drive / "Steam",
        drive / "Games" / "SteamLibrary",
    ]
    for p in likely:
        if (p / "steamapps" / "common").is_dir():
            rp = p.resolve()
            if str(rp) not in seen:
                seen.add(str(rp))
                out.append(rp)

    # Then shallow-search G: for any other steamapps/common.
    for cur, dirs, _files in os.walk(drive):
        cp = Path(cur)
        try:
            depth = len(cp.relative_to(drive).parts)
        except ValueError:
            continue

        dirs[:] = [
            d for d in dirs
            if d.casefold() not in IGNORE_DIRS
            and not d.startswith(".")
        ]
        if depth >= 5:
            dirs[:] = []

        if cp.name.casefold() == "steamapps" and (cp / "common").is_dir():
            lib = cp.parent.resolve()
            if str(lib) not in seen:
                seen.add(str(lib))
                out.append(lib)
            dirs[:] = []

    return sorted(out, key=lambda p: str(p).casefold())

def find_nonsteam_roots(drive: Path, steam_libs: list[Path]) -> list[Path]:
    roots: list[Path] = []
    seen = set()

    possible_bases = {drive}
    for lib in steam_libs:
        possible_bases.add(lib.parent)
        possible_bases.add(lib)

    for base in possible_bases:
        for name in NONSTEAM_NAMES:
            p = base / name
            if p.is_dir():
                rp = p.resolve()
                if str(rp) not in seen:
                    seen.add(str(rp))
                    roots.append(rp)

    return sorted(roots, key=lambda p: str(p).casefold())

def iter_game_files(root: Path, max_files: int = 250000, max_depth: Optional[int] = None):
    """Yield ordinary files inside one game without crossing filesystem boundaries.

    Discovery evidence must belong to the selected game. Symlink files, special
    nodes, directory symlinks, and nested mount points are therefore excluded
    from the evidence walk. The game root itself may be a mount; only nested
    boundaries are pruned.
    """
    root = root.resolve()
    count = 0
    for cur, dirs, files in os.walk(root, followlinks=False):
        cp = Path(cur)
        try:
            depth = len(cp.relative_to(root).parts)
        except ValueError:
            dirs[:] = []
            continue

        safe_dirs: list[str] = []
        if max_depth is None or depth < max_depth:
            for d in dirs:
                low = d.casefold()
                if (
                    low in IGNORE_DIRS
                    or low.startswith("_optiscaler")
                    or low.startswith("_true_uninstall")
                ):
                    continue
                child = cp / d
                try:
                    if child.is_symlink() or _path_is_mount(child):
                        continue
                except OSError:
                    continue
                safe_dirs.append(d)
        dirs[:] = safe_dirs

        for name in files:
            p = cp / name
            try:
                mode = p.lstat().st_mode
            except OSError:
                continue
            if not stat.S_ISREG(mode):
                continue
            count += 1
            if count > max_files:
                return
            yield p

@dataclass
class Game:
    code: str
    name: str
    root: Path
    source: str
    appid: Optional[str] = None
    manifest: Optional[Path] = None
    exe: Optional[Path] = None
    target_dir: Optional[Path] = None
    dlss: bool = False
    dlssg: bool = False
    anti_cheat: Optional[Path] = None
    installed: bool = False
    baseline: Optional[Path] = None
    reason: str = ""
    evidence: list[Path] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return bool(self.exe and self.dlss and self.dlssg and not self.anti_cheat)

def scan_game_files(root: Path) -> tuple[list[Path], list[Path], Optional[Path]]:
    exes: list[Path] = []
    evidence: list[Path] = []
    anti: Optional[Path] = None

    for p in iter_game_files(root):
        low = p.name.casefold()

        if low in {"nvngx_dlss.dll", "nvngx_dlssg.dll", "sl.dlss_g.dll"}:
            evidence.append(p)

        if p.suffix.casefold() == ".exe" and not EXE_BAD_RE.search(low):
            exes.append(p)

        if anti is None:
            if any(fnmatch.fnmatch(low, pat) for pat in ANTI_CHEAT_PATTERNS):
                anti = p
            elif any(part.casefold() in ANTI_CHEAT_DIRS for part in p.parts):
                anti = p

    return exes, evidence, anti

def score_exe(exe: Path, evidence: list[Path]) -> int:
    name = exe.name.casefold()
    normalized = str(exe).replace("\\", "/")
    parent = exe.parent.resolve()
    evidence_dirs = {p.parent.resolve() for p in evidence}

    score = 0
    if parent in evidence_dirs:
        score += 6000
    if re.search(r"(?:-win64-shipping|-wingdk-shipping)\.exe$", name):
        score += 3000
    if re.search(r"/Binaries/Win64(?:/|$)", normalized, re.I):
        score += 1800
    if re.search(r"/bin/x64(?:/|$)", normalized, re.I):
        score += 1500
    if re.search(r"/bin64(?:/|$)", normalized, re.I):
        score += 1500
    if re.search(r"/Retail(?:/|$)", normalized, re.I):
        score += 1200
    if (parent / "nvngx_dlssg.dll").is_file():
        score += 2400
    if (parent / "nvngx_dlss.dll").is_file():
        score += 2000
    if (parent / "sl.dlss_g.dll").is_file():
        score += 1800
    try:
        score += min(300, int(exe.stat().st_size / (1024 * 1024)))
    except OSError:
        pass
    if re.search(r"launcher|helper|benchmark|report|updater", name, re.I):
        score -= 5000
    if re.search(r"/Engine/Binaries/ThirdParty/", normalized, re.I):
        score -= 7000
    if re.search(r"/DigitalExtras/", normalized, re.I):
        score -= 10000
    return score

def choose_game_exe(root: Path, name: str, exes: list[Path], evidence: list[Path]) -> Optional[Path]:
    # Known cases from rtxEngine's existing scanner.
    control = root / "Control_DX12.exe"
    if name.casefold().strip() == "control" and control.is_file():
        return control

    if root.name.casefold() == "halo campaign evolved" or "halo campaign evolved" in name.casefold():
        halo = root / "Meteorite" / "Binaries" / "Win64" / "HaloCampaignEvolved.exe"
        if halo.is_file():
            return halo

    if not exes:
        return None
    return max(exes, key=lambda p: score_exe(p, evidence))

def inspect_game(game: Game) -> Game:
    exes, evidence, anti = scan_game_files(game.root)
    game.evidence = evidence
    game.anti_cheat = anti
    game.dlss = any(p.name.casefold() == "nvngx_dlss.dll" for p in evidence)
    game.dlssg = any(p.name.casefold() in {"nvngx_dlssg.dll", "sl.dlss_g.dll"} for p in evidence)
    game.exe = choose_game_exe(game.root, game.name, exes, evidence)
    game.target_dir = game.exe.parent.resolve() if game.exe else None

    if game.target_dir:
        state = baseline_path(game.target_dir)
        game.installed = state.is_file()
        game.baseline = state if state.is_file() else None

    if game.anti_cheat:
        game.reason = "ANTI-CHEAT"
    elif not game.exe:
        game.reason = "NO GAME EXE"
    elif not game.dlss:
        game.reason = "NO DLSS"
    elif not game.dlssg:
        game.reason = "NO DLSS-G"
    else:
        game.reason = "INSTALLED" if game.installed else "READY"
    return game

def discover_fallback_nonsteam_games(
    drive: Path,
    already_roots: set[Path],
    steam_libs: list[Path],
) -> list[Game]:
    """
    Conservative fallback for games not stored under the conventional Non-Steam
    folders. We do NOT call every folder a game: it must contain DLSS evidence.
    """
    games: list[Game] = []
    steam_common = [(lib / "steamapps" / "common").resolve() for lib in steam_libs]

    # Candidate containers likely to contain direct game directories.
    containers = [drive, drive / "Games"]
    for container in containers:
        if not container.is_dir():
            continue

        try:
            children = sorted(container.iterdir(), key=lambda p: p.name.casefold())
        except OSError:
            continue

        for child in children:
            if not child.is_dir() or child.name.startswith("."):
                continue
            low = child.name.casefold()
            if low in IGNORE_DIRS or low in {n.casefold() for n in NONSTEAM_NAMES}:
                continue
            if any(child.resolve() == lib.resolve() for lib in steam_libs):
                continue
            if any(
                child.resolve() == common or common.is_relative_to(child.resolve())
                for common in steam_common
            ):
                continue
            rp = child.resolve()
            if rp in already_roots:
                continue

            # Quick bounded evidence check before expensive full inspection. Use
            # the same filesystem-boundary rules as the full game scanner so a
            # symlink/mount outside this game cannot manufacture eligibility.
            found = any(
                p.name.casefold() in {"nvngx_dlss.dll", "nvngx_dlssg.dll", "sl.dlss_g.dll"}
                for p in iter_game_files(rp, max_files=50000, max_depth=5)
            )

            if found:
                games.append(Game("", child.name, rp, "Non-Steam"))

    return games

def discover_games(drive: Path) -> list[Game]:
    heading("Scanning G: game library")
    kv("Drive", drive)

    steam_libs = find_steam_libraries(drive)
    nonsteam_roots = find_nonsteam_roots(drive, steam_libs)
    kv("Steam libraries", len(steam_libs))
    kv("Non-Steam roots", len(nonsteam_roots))

    games: list[Game] = []
    known_roots: set[Path] = set()

    for lib in steam_libs:
        steamapps = lib / "steamapps"
        common = steamapps / "common"
        for manifest in sorted(steamapps.glob("appmanifest_*.acf")):
            data = parse_appmanifest(manifest)
            if not data or is_tool(data["name"], data["appid"]):
                continue
            installdir = safe_steam_installdir(data.get("installdir"))
            if installdir is None:
                warn(f"Skipping unsafe Steam installdir in {manifest.name}")
                continue
            root = (common / installdir).resolve()
            if root.is_dir() and root not in known_roots:
                known_roots.add(root)
                games.append(
                    Game(
                        "",
                        data["name"],
                        root,
                        "Steam",
                        data["appid"],
                        manifest,
                    )
                )

    for nsroot in nonsteam_roots:
        try:
            children = sorted(nsroot.iterdir(), key=lambda p: p.name.casefold())
        except OSError:
            continue
        for child in children:
            if not child.is_dir() or child.name.startswith(".") or is_tool(child.name):
                continue
            root = child.resolve()
            if root not in known_roots:
                known_roots.add(root)
                games.append(Game("", child.name, root, "Non-Steam"))

    games.extend(discover_fallback_nonsteam_games(drive, known_roots, steam_libs))

    # Inspection is the slow part; show simple progress without dependencies.
    inspected: list[Game] = []
    total = len(games)
    for i, game in enumerate(games, 1):
        width = 48
        name = game.name[:width]
        print(f"\r  {cyan('Scanning')} {i:>3}/{total:<3} {name:<48}", end="", flush=True)
        try:
            inspected.append(inspect_game(game))
        except (OSError, PermissionError):
            game.reason = "UNREADABLE"
            inspected.append(game)
    if total:
        print("\r" + " " * 90 + "\r", end="")

    # Keep all discovered game entries so the UI can explain why something is skipped.
    inspected.sort(key=lambda g: (g.source != "Steam", g.name.casefold()))
    for i, game in enumerate(inspected):
        game.code = code_for_index(i)
    return inspected

# Selection UI ---------------------------------------------------------------

def status_label(game: Game) -> str:
    if game.reason == "READY":
        return green("READY")
    if game.reason == "INSTALLED":
        return cyan("INSTALLED")
    if game.reason == "RECOVERY":
        return yellow("RECOVERY")
    return red(game.reason)

def print_games(games: list[Game], mode: str) -> None:
    heading("Game library")
    header = f"{'CODE':<6}{'GAME':<37}{'SOURCE':<12}{'STATUS':<14}TARGET"
    print("  " + dim(header))
    print("  " + dim("─" * min(118, shutil.get_terminal_size((120, 30)).columns - 4)))

    for g in games:
        if mode == "uninstall" and not g.installed:
            continue
        if mode == "audit" and not g.installed:
            continue
        source = f"Steam {g.appid}" if g.appid else g.source
        target = str(g.target_dir) if g.target_dir else "—"
        print(
            "  "
            + green(g.code.ljust(6))
            + g.name[:35].ljust(37)
            + source[:10].ljust(12)
            + status_label(g).ljust(23 if USE_COLOR else 14)
            + target
        )

    if mode == "install":
        ready = sum(g.eligible for g in games)
        blocked = len(games) - ready
        print()
        kv("Eligible", ready)
        kv("Skipped/blocked", blocked)
        kv("ALL means", "every eligible game only")
    elif mode == "clean":
        steam = sum(bool(g.appid) for g in games)
        nonsteam = len(games) - steam
        print()
        kv("Steam games", steam)
        kv("Non-Steam games", nonsteam)
        kv("ALL means", "every discovered game; destructive preview still shown")
    elif mode == "pristine":
        steam = sum(bool(g.appid and g.manifest and g.root.is_dir()) for g in games)
        print()
        kv("Steam games", steam)
        kv("Non-Steam games", "NOT SUPPORTED")
        kv("ALL means", "every validated Steam install; full install contents will be deleted")
    else:
        installed = sum(g.installed for g in games)
        print()
        kv("Installed targets", installed)
        kv("ALL means", "every rtxEngine-managed DLSS Unlocked install")

def parse_selection(raw: str, games: list[Game], mode: str) -> list[Game]:
    raw = raw.strip().upper()
    require(raw, "No games selected")

    if mode == "install":
        selectable = [g for g in games if g.eligible]
    elif mode == "clean":
        selectable = [g for g in games if g.root.is_dir()]
    elif mode == "pristine":
        selectable = [g for g in games if g.appid and g.manifest and g.root.is_dir()]
    else:
        selectable = [g for g in games if g.installed]

    by_code = {g.code.upper(): g for g in selectable}

    if raw == "ALL":
        require(selectable, "No selectable games")
        return selectable

    if raw == "NEW" and mode == "install":
        result = [g for g in selectable if not g.installed]
        require(result, "No new eligible games")
        return result

    requested: list[str] = []
    for token in re.split(r"[\s,;]+", raw):
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            require(a in by_code and b in by_code, f"Invalid range: {token}")
            ordered = [g.code for g in selectable]
            ia, ib = ordered.index(a), ordered.index(b)
            if ia > ib:
                ia, ib = ib, ia
            requested.extend(ordered[ia:ib + 1])
        else:
            requested.append(token)

    unknown = [c for c in requested if c not in by_code]
    require(not unknown, "Not selectable: " + ", ".join(unknown))

    out: list[Game] = []
    seen = set()
    for code in requested:
        if code not in seen:
            seen.add(code)
            out.append(by_code[code])
    require(out, "No games selected")
    return out

# Archive --------------------------------------------------------------------

def _y4my_archive_candidates() -> list[Path]:
    name = Y4MY_PROVIDER["archive"]
    return [
        DEFAULT_DOWNLOAD_DIR / name,
        HOME / "Downloads" / name,
        Y4MY_CACHE_DIR / name,
        SCRIPT_DIR / name,
    ]


def find_default_archive() -> Optional[Path]:
    """Return a local pinned y4my v4 provider, never an arbitrary newer build."""
    expected = Y4MY_PROVIDER["sha256"]
    for candidate in _y4my_archive_candidates():
        if not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            if sha256_file(candidate) == expected:
                return candidate.resolve()
        except OSError:
            continue
    return None


def _download_y4my_archive() -> Path:
    _mkdir_durable(Y4MY_CACHE_DIR)
    final = Y4MY_CACHE_DIR / Y4MY_PROVIDER["archive"]
    tmp = final.with_name(f".{final.name}.part-{os.getpid()}-{time.time_ns()}")
    warn(f"Downloading pinned {Y4MY_PROVIDER['name']} from GitHub…")
    try:
        req = urllib.request.Request(
            Y4MY_PROVIDER["url"],
            headers={"User-Agent": "rtxEngine-Terminal/13"},
        )
        with urllib.request.urlopen(req, timeout=120) as response, tmp.open("wb") as f:
            shutil.copyfileobj(response, f)
    except Exception as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise Stop(
            f"Could not download {Y4MY_PROVIDER['name']}: {exc}. "
            f"Download {Y4MY_PROVIDER['archive']} manually and pass --archive."
        ) from exc

    try:
        digest = sha256_file(tmp)
        require(
            digest == Y4MY_PROVIDER["sha256"],
            f"Downloaded y4my provider SHA256 mismatch ({digest}); refusing it.",
        )
        if Y4MY_PROVIDER.get("release_size"):
            require(
                tmp.stat().st_size == int(Y4MY_PROVIDER["release_size"]),
                "Downloaded y4my provider size differs from the pinned GitHub release asset.",
            )
        durable_replace(tmp, final)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return final.resolve()


def choose_archive(arg_archive: Optional[str] = None) -> Path:
    if arg_archive:
        return Path(arg_archive).expanduser().resolve()
    local = find_default_archive()
    if local is not None:
        return local
    return _download_y4my_archive()


def _archive_payload_libarchive(archive: Path) -> dict[str, bytes]:
    """Read a 7z/zip archive into memory through system libarchive, fail closed.

    Bazzite already uses libarchive in its base image. Keeping extraction here
    avoids requiring a mutable Python environment or silently shelling out to a
    different 7z implementation. A CLI fallback remains for unusual systems.
    """
    libname = ctypes.util.find_library("archive")
    if not libname:
        raise OSError("libarchive is not available")
    lib = ctypes.CDLL(libname)
    archive_p = ctypes.c_void_p
    entry_p = ctypes.c_void_p
    lib.archive_read_new.restype = archive_p
    lib.archive_read_support_filter_all.argtypes = [archive_p]
    lib.archive_read_support_format_all.argtypes = [archive_p]
    lib.archive_read_open_filename.argtypes = [archive_p, ctypes.c_char_p, ctypes.c_size_t]
    lib.archive_read_open_filename.restype = ctypes.c_int
    lib.archive_read_next_header.argtypes = [archive_p, ctypes.POINTER(entry_p)]
    lib.archive_read_next_header.restype = ctypes.c_int
    lib.archive_entry_pathname.argtypes = [entry_p]
    lib.archive_entry_pathname.restype = ctypes.c_char_p
    lib.archive_entry_filetype.argtypes = [entry_p]
    lib.archive_entry_filetype.restype = ctypes.c_uint
    lib.archive_entry_size.argtypes = [entry_p]
    lib.archive_entry_size.restype = ctypes.c_longlong
    lib.archive_read_data.argtypes = [archive_p, ctypes.c_void_p, ctypes.c_size_t]
    lib.archive_read_data.restype = ctypes.c_ssize_t
    lib.archive_error_string.argtypes = [archive_p]
    lib.archive_error_string.restype = ctypes.c_char_p
    lib.archive_read_free.argtypes = [archive_p]

    a = lib.archive_read_new()
    require(bool(a), "libarchive could not allocate a reader")
    payload: dict[str, bytes] = {}
    total = 0
    try:
        lib.archive_read_support_filter_all(a)
        lib.archive_read_support_format_all(a)
        rc = lib.archive_read_open_filename(a, os.fsencode(archive), 1024 * 64)
        if rc != 0:
            err = lib.archive_error_string(a)
            raise Stop(f"Could not open provider archive: {(err or b'unknown error').decode(errors='replace')}")

        while True:
            ent = entry_p()
            rc = lib.archive_read_next_header(a, ctypes.byref(ent))
            if rc == 1:  # ARCHIVE_EOF
                break
            if rc < 0:
                err = lib.archive_error_string(a)
                raise Stop(f"Provider archive read failed: {(err or b'unknown error').decode(errors='replace')}")
            raw_name = lib.archive_entry_pathname(ent)
            require(raw_name, "Provider archive contains an unnamed entry")
            rel = safe_rel(os.fsdecode(raw_name).replace("\\", "/"))
            ftype = int(lib.archive_entry_filetype(ent)) & 0o170000
            if ftype == stat.S_IFDIR:
                continue
            require(ftype == stat.S_IFREG, f"Provider archive non-regular entry refused: {rel}")
            size = int(lib.archive_entry_size(ent))
            require(0 <= size <= 1024 * 1024 * 1024, f"Provider archive entry has unsafe size: {rel}")
            chunks: list[bytes] = []
            remaining = size
            while remaining > 0:
                nbuf = min(1024 * 1024, remaining)
                buf = ctypes.create_string_buffer(nbuf)
                got = int(lib.archive_read_data(a, buf, nbuf))
                if got < 0:
                    err = lib.archive_error_string(a)
                    raise Stop(f"Provider archive data read failed for {rel}: {(err or b'unknown error').decode(errors='replace')}")
                if got == 0:
                    break
                chunks.append(buf.raw[:got])
                remaining -= got
            data = b"".join(chunks)
            require(len(data) == size, f"Provider archive entry truncated: {rel}")
            key = rel.casefold()
            require(key not in {x.casefold() for x in payload}, f"Case-colliding provider path: {rel}")
            payload[rel] = data
            total += size
            require(total <= 2 * 1024 * 1024 * 1024, "Provider archive expands beyond the safety limit")
            require(len(payload) <= 20000, "Provider archive contains too many files")
    finally:
        lib.archive_read_free(a)
    return payload


def _archive_payload_cli(archive: Path) -> dict[str, bytes]:
    tool = shutil.which("7zz") or shutil.which("7z") or shutil.which("bsdtar")
    require(tool is not None, "Neither libarchive nor 7z/7zz/bsdtar is available to extract the y4my .7z provider")
    with tempfile.TemporaryDirectory(prefix="rtxengine-y4my-") as td:
        root = Path(td)
        if Path(tool).name == "bsdtar":
            cmd = [tool, "-xf", str(archive), "-C", str(root)]
        else:
            cmd = [tool, "x", "-y", f"-o{root}", str(archive)]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        require(proc.returncode == 0, f"Provider extraction failed: {proc.stdout[-1200:]}")
        payload: dict[str, bytes] = {}
        for current, dirs, files in os.walk(root, followlinks=False):
            base = Path(current)
            for d in list(dirs):
                p = base / d
                require(not p.is_symlink(), f"Provider archive symlink refused: {p.relative_to(root)}")
            for name in files:
                p = base / name
                require(p.is_file() and not p.is_symlink(), f"Provider archive non-regular file refused: {p.relative_to(root)}")
                rel = safe_rel(p.relative_to(root).as_posix())
                key = rel.casefold()
                require(key not in {x.casefold() for x in payload}, f"Case-colliding provider path: {rel}")
                payload[rel] = p.read_bytes()
        return payload


def _read_provider_archive(archive: Path) -> dict[str, bytes]:
    try:
        return _archive_payload_libarchive(archive)
    except OSError:
        return _archive_payload_cli(archive)


def _strip_provider_root(payload: dict[str, bytes]) -> dict[str, bytes]:
    loaders = [rel for rel in payload if PurePosixPath(rel).name.casefold() == "optiscaler.dll"]
    require(len(loaders) == 1, "y4my provider must contain exactly one OptiScaler.dll")
    parent = PurePosixPath(loaders[0]).parent
    prefix = "" if str(parent) == "." else parent.as_posix().rstrip("/") + "/"
    out: dict[str, bytes] = {}
    for rel, data in payload.items():
        if prefix:
            require(rel.startswith(prefix), "Provider archive contains files outside its package root")
            rel = rel[len(prefix):]
        rel = safe_rel(rel)
        out[rel] = data
    return out


def _load_validated_archive(archive: Path) -> tuple[dict[str, bytes], dict]:
    """Read the exact pinned provider once and prove the file stayed stable.

    Hashing a pathname and then reopening it for extraction creates a TOCTOU
    window: another process can replace/modify that file after the pinned hash
    check.  Keep the extracted payload in memory and re-hash the archive before
    trusting those bytes.  This also avoids decompressing the 117 MB provider
    twice on every install.
    """
    require(archive.is_file() and not archive.is_symlink(), f"Provider archive not found/unsafe: {archive}")
    digest_before = sha256_file(archive)
    require(
        digest_before == Y4MY_PROVIDER["sha256"],
        f"Unpinned y4my provider refused: {archive.name} ({digest_before[:12]}…). Expected the exact v4 with-DLSS release asset.",
    )

    raw = _strip_provider_root(_read_provider_archive(archive))
    digest_after = sha256_file(archive)
    require(
        digest_after == digest_before == Y4MY_PROVIDER["sha256"],
        "y4my provider archive changed while it was being read; refusing raced payload bytes.",
    )
    lowered = {rel.casefold(): rel for rel in raw}

    # The forwarder is packaged by filename; tolerate a package subdirectory
    # and normalize it beside the game executable, as the NR README requires.
    forwarders = [rel for rel in raw if PurePosixPath(rel).name.casefold() == "nvngx.dll_dlssnr.dll"]
    require(len(forwarders) == 1, "y4my provider must contain exactly one nvngx.dll_dlssnr.dll forwarder")

    for required in Y4MY_REQUIRED_FILES:
        if required.casefold() == "nvngx.dll_dlssnr.dll":
            continue
        require(required.casefold() in lowered, f"y4my provider missing {required}")

    loader = raw[lowered["optiscaler.dll"]]
    require(len(loader) > 64 * 1024 and loader[:2] == b"MZ", "y4my OptiScaler.dll is not a valid PE DLL")
    return raw, {
        "path": str(archive.resolve()),
        "name": archive.name,
        "sha256": digest_before,
        "provider": Y4MY_PROVIDER["name"],
        "tag": Y4MY_PROVIDER["tag"],
        "commit": Y4MY_PROVIDER["commit"],
        "asset_id": Y4MY_PROVIDER["asset_id"],
        "file_count": len(raw),
    }


def validate_archive(archive: Path) -> dict:
    _payload, meta = _load_validated_archive(archive)
    return meta


def load_archive_payload(archive: Path):
    payload, meta = _load_validated_archive(archive)

    # Normalize the y4my loader into the historical placeholder expected by
    # install_target; it is renamed to the selected supported proxy later.
    loader_key = next(k for k in payload if k.casefold() == "optiscaler.dll")
    loader = payload.pop(loader_key)
    payload["dxgi.dll"] = loader

    # The NR forwarder must sit beside the game executable. Normalize it there
    # even if the release package happens to place it in a subdirectory.
    forwarders = [k for k in payload if PurePosixPath(k).name.casefold() == "nvngx.dll_dlssnr.dll"]
    require(len(forwarders) == 1, "y4my provider forwarder missing after extraction")
    forwarder = payload.pop(forwarders[0])
    payload["nvngx.dll_dlssnr.dll"] = forwarder

    # Setup scripts are installer tooling, not runtime payload. rtxEngine owns
    # backup/restore and must not drop a second uninstaller into each game.
    for rel in list(payload):
        name = PurePosixPath(rel).name.casefold()
        if name in {"setup_linux.sh", "setup_windows.bat", "remove_optiscaler.sh", "remove optiscaler.bat"}:
            payload.pop(rel, None)
        elif name.startswith("!! extract all files"):
            payload.pop(rel, None)

    return payload, meta


def _nr_runtime_candidates(explicit: Optional[str] = None) -> list[Path]:
    out: list[Path] = []
    if explicit:
        out.append(Path(explicit).expanduser())
    out.extend([
        DEFAULT_DOWNLOAD_DIR / NR_RUNTIME_NAME,
        HOME / "Downloads" / NR_RUNTIME_NAME,
    ])
    return out


def _nr_runtime_provider(family: str) -> dict:
    provider = NR_RUNTIME_PROVIDERS.get(family)
    require(provider is not None, f"No pinned Neural Rendering runtime provider for GPU family: {family}")
    return provider


def _nr_runtime_cache_dir(family: str) -> Path:
    return HOME / ".cache" / "rtxEngine" / "providers" / "dlssnr" / family


def _nr_runtime_archive_candidates(family: str) -> list[Path]:
    provider = _nr_runtime_provider(family)
    name = provider["archive"]
    return [
        DEFAULT_DOWNLOAD_DIR / name,
        HOME / "Downloads" / name,
        _nr_runtime_cache_dir(family) / name,
        SCRIPT_DIR / name,
    ]


def _valid_nr_runtime_archive(path: Path, provider: dict) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        if provider.get("release_size") and path.stat().st_size != int(provider["release_size"]):
            return False
        return sha256_file(path) == provider["sha256"]
    except OSError:
        return False


def _download_nr_runtime_archive(family: str) -> Path:
    provider = _nr_runtime_provider(family)
    cache_dir = _nr_runtime_cache_dir(family)
    _mkdir_durable(cache_dir)
    final = cache_dir / provider["archive"]
    tmp = final.with_name(f".{final.name}.part-{os.getpid()}-{time.time_ns()}")
    warn(
        f"Downloading pinned {provider['name']} NR compatibility runtime from "
        "RankFTW/rhi-repo (community mirror)…"
    )
    try:
        req = urllib.request.Request(
            provider["url"],
            headers={"User-Agent": "rtxEngine-Terminal/13"},
        )
        with urllib.request.urlopen(req, timeout=120) as response, tmp.open("wb") as f:
            shutil.copyfileobj(response, f)
    except Exception as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise Stop(
            f"Could not download pinned {provider['name']} NR runtime: {exc}. "
            f"You may place the exact {provider['archive']} release asset in Downloads "
            "or pass a trusted DLL explicitly with --nr-runtime."
        ) from exc

    try:
        digest = sha256_file(tmp)
        require(
            digest == provider["sha256"],
            f"Downloaded {provider['name']} archive SHA256 mismatch ({digest}); refusing it.",
        )
        if provider.get("release_size"):
            require(
                tmp.stat().st_size == int(provider["release_size"]),
                f"Downloaded {provider['name']} archive size differs from the pinned release asset.",
            )
        durable_replace(tmp, final)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return final.resolve()


def ensure_nr_runtime_archive(family: str) -> Path:
    """Return only the exact family-pinned DLSSNR release asset.

    Local copies are accepted solely when their size/hash matches the pinned
    release metadata. A stale/corrupt cache cannot become install authority.
    """
    provider = _nr_runtime_provider(family)
    for candidate in _nr_runtime_archive_candidates(family):
        if _valid_nr_runtime_archive(candidate, provider):
            return candidate.resolve()
    return _download_nr_runtime_archive(family)


def load_pinned_nr_runtime(family: str) -> tuple[bytes, dict]:
    """Load one exact nvngx_dlssnr.dll from a SHA-pinned provider archive."""
    provider = _nr_runtime_provider(family)
    archive = ensure_nr_runtime_archive(family)
    payload = _safe_zip_payload_single_file(archive, NR_RUNTIME_NAME, provider["sha256"])
    require(
        len(payload) > NR_RUNTIME_MIN_BYTES and payload[:2] == b"MZ",
        f"Pinned {NR_RUNTIME_NAME} payload is invalid; refusing it.",
    )
    return payload, {
        "name": NR_RUNTIME_NAME,
        "path": str(archive),
        "sha256": sha256_bytes(payload),
        "ownership": "pinned community DLSSNR runtime (downloaded, not bundled)",
        "provider": provider["name"],
        "provider_tag": provider["tag"],
        "provider_archive": provider["archive"],
        "provider_archive_sha256": provider["sha256"],
        "provider_url": provider["url"],
        "gpu_family": family,
    }


def load_user_nr_runtime(
    explicit: Optional[str] = None,
    family: Optional[str] = None,
) -> tuple[Optional[bytes], Optional[dict]]:
    """Resolve NR runtime authority without poisoning discovery.

    Precedence is strict explicit DLL -> valid local user DLL -> exact pinned
    family provider. An explicit ``--nr-runtime`` never falls back if invalid.
    Auto-discovery tolerates stale/corrupt local copies, then uses the
    cryptographically pinned compatibility provider when ``family`` is known.
    """
    candidates = _nr_runtime_candidates(explicit)
    diagnostics: list[str] = []
    for i, path in enumerate(candidates):
        is_explicit = explicit is not None and i == 0
        if not path.is_file() or path.is_symlink():
            if is_explicit:
                raise Stop(f"NR runtime not found/unsafe: {path}")
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            if is_explicit:
                raise Stop(f"Could not read NR runtime {path}: {exc}") from exc
            diagnostics.append(f"{path}: unreadable")
            continue
        valid_size = len(data) > NR_RUNTIME_MIN_BYTES
        valid_pe = data[:2] == b"MZ"
        if not (valid_size and valid_pe):
            detail = (
                "unexpectedly small" if not valid_size
                else "not a Windows PE DLL"
            )
            if is_explicit:
                raise Stop(f"{NR_RUNTIME_NAME} is {detail}: {path}")
            diagnostics.append(f"{path}: {detail}")
            continue
        return data, {
            "name": NR_RUNTIME_NAME,
            "path": str(path.resolve()),
            "sha256": sha256_bytes(data),
            "ownership": "user-supplied NVIDIA runtime",
            "skipped_auto_candidates": diagnostics,
        }

    if family is not None:
        payload, meta = load_pinned_nr_runtime(family)
        meta["skipped_auto_candidates"] = diagnostics
        return payload, meta

    # Discovery-only callers without a resolved GPU family retain the old
    # non-networking behavior so a valid per-game copy can still be preserved.
    return None, None


# Legacy RTX 40 MFG provider -------------------------------------------------

def _safe_zip_payload_single_file(archive: Path, wanted_name: str, expected_sha256: str) -> bytes:
    require(archive.is_file(), f"Provider archive not found: {archive}")
    require(zipfile.is_zipfile(archive), f"Not a valid ZIP: {archive}")
    require(
        sha256_file(archive) == expected_sha256,
        f"{archive.name} SHA256 mismatch. Refusing modified/corrupt provider archive.",
    )

    with zipfile.ZipFile(archive) as zf:
        files = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            require(not stat.S_ISLNK(unix_mode), f"Provider archive symlink refused: {info.filename}")
            rel = safe_rel(info.filename)
            files.append((info, rel))

        matches = [(info, rel) for info, rel in files if PurePosixPath(rel).name.casefold() == wanted_name.casefold()]
        require(len(matches) == 1, f"Provider archive must contain exactly one {wanted_name}")
        info, _ = matches[0]
        payload = zf.read(info)
        require(len(payload) > 64 * 1024, f"{wanted_name} payload is unexpectedly small")
        require(payload[:2] == b"MZ", f"{wanted_name} is not a Windows PE DLL")
        return payload


def load_integrated_ada_runtime() -> tuple[bytes, dict]:
    """Legacy Handoff-187 API retained only so old callers fail explicitly.

    Handoff 188 removed the separate RTXForge NativeMFG v3e runtime. New
    installs must use the pinned y4my v4 provider for both NR and native Ada
    MFG, so there is intentionally no payload to return here.
    """
    raise Stop(
        "RTXForge NativeMFG v3e was retired by Handoff 188; use the unified y4my v4 provider instead."
    )

def _rtxmfg_archive_candidates() -> list[Path]:
    return [
        DEFAULT_DOWNLOAD_DIR / RTXMFG_PROVIDER["archive"],
        HOME / "Downloads" / RTXMFG_PROVIDER["archive"],
        RTXMFG_CACHE_DIR / RTXMFG_PROVIDER["archive"],
    ]


def find_local_rtxmfg_archive() -> Optional[Path]:
    """Return only a local archive whose bytes match the pinned provider."""
    expected = RTXMFG_PROVIDER["sha256"]
    for path in _rtxmfg_archive_candidates():
        if not path.is_file():
            continue
        try:
            if sha256_file(path) == expected:
                return path.resolve()
        except OSError:
            continue
    return None


def ensure_rtxmfg_archive(allow_download: bool = True) -> Path:
    local = find_local_rtxmfg_archive()
    if local is not None:
        return local.resolve()

    require(allow_download, "Universal RTXMFG provider archive is not available locally.")
    _mkdir_durable(RTXMFG_CACHE_DIR)
    final = RTXMFG_CACHE_DIR / RTXMFG_PROVIDER["archive"]
    tmp = final.with_name(f".{final.name}.part-{os.getpid()}-{time.time_ns()}")

    warn(f"Downloading pinned Universal RTXMFG {RTXMFG_PROVIDER['version']} from GitHub…")
    try:
        req = urllib.request.Request(
            RTXMFG_PROVIDER["url"],
            headers={"User-Agent": "rtxEngine-Terminal/13"},
        )
        with urllib.request.urlopen(req, timeout=60) as response, tmp.open("wb") as f:
            shutil.copyfileobj(response, f)
    except Exception as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise Stop(f"Could not download Universal RTXMFG: {exc}") from exc

    if sha256_file(tmp) != RTXMFG_PROVIDER["sha256"]:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise Stop("Downloaded Universal RTXMFG SHA256 mismatch; refusing it.")
    durable_replace(tmp, final)
    return final.resolve()


def load_rtxmfg_payload(allow_download: bool = True) -> tuple[bytes, dict]:
    archive = ensure_rtxmfg_archive(allow_download=allow_download)
    payload = _safe_zip_payload_single_file(
        archive,
        "RTXMFG.dll",
        RTXMFG_PROVIDER["sha256"],
    )
    return payload, {
        "name": archive.name,
        "path": str(archive),
        "version": RTXMFG_PROVIDER["version"],
        "sha256": RTXMFG_PROVIDER["sha256"],
        "dll_sha256": sha256_bytes(payload),
    }


def _pe_rva_to_offset(data: bytes, sections: list[tuple[int, int, int, int]], rva: int) -> Optional[int]:
    for virtual_address, virtual_size, raw_offset, raw_size in sections:
        span = max(virtual_size, raw_size)
        if virtual_address <= rva < virtual_address + span:
            offset = raw_offset + (rva - virtual_address)
            if 0 <= offset < len(data):
                return offset
    return None


def pe_imported_dlls(exe: Path) -> set[str]:
    """
    Dependency-free PE import-table reader.

    We use the target EXE's normal import table only. A supported proxy is
    considered safe for automatic RTXMFG deployment only when the EXE actually
    imports that DLL and the game directory does not already own the filename.
    """
    try:
        data = exe.read_bytes()
    except OSError:
        return set()

    try:
        require(len(data) >= 0x40 and data[:2] == b"MZ", "not PE")
        pe_off = struct.unpack_from("<I", data, 0x3C)[0]
        require(pe_off + 24 <= len(data) and data[pe_off:pe_off + 4] == b"PE\0\0", "bad PE")

        coff = pe_off + 4
        number_of_sections = struct.unpack_from("<H", data, coff + 2)[0]
        size_optional = struct.unpack_from("<H", data, coff + 16)[0]
        opt = coff + 20
        require(opt + size_optional <= len(data), "truncated optional header")
        magic = struct.unpack_from("<H", data, opt)[0]

        if magic == 0x20B:      # PE32+
            data_dir = opt + 112
        elif magic == 0x10B:    # PE32
            data_dir = opt + 96
        else:
            return set()

        require(data_dir + 16 <= opt + size_optional, "missing import directory")
        import_rva, import_size = struct.unpack_from("<II", data, data_dir + 8)
        if not import_rva or not import_size:
            return set()

        section_table = opt + size_optional
        sections = []
        for i in range(number_of_sections):
            off = section_table + i * 40
            require(off + 40 <= len(data), "truncated section table")
            virtual_size = struct.unpack_from("<I", data, off + 8)[0]
            virtual_address = struct.unpack_from("<I", data, off + 12)[0]
            raw_size = struct.unpack_from("<I", data, off + 16)[0]
            raw_offset = struct.unpack_from("<I", data, off + 20)[0]
            sections.append((virtual_address, virtual_size, raw_offset, raw_size))

        desc = _pe_rva_to_offset(data, sections, import_rva)
        if desc is None:
            return set()

        names = set()
        max_desc = min(4096, import_size // 20 + 2)
        for _ in range(max_desc):
            require(desc + 20 <= len(data), "truncated import descriptor")
            original, timestamp, chain, name_rva, first_thunk = struct.unpack_from("<IIIII", data, desc)
            if original == timestamp == chain == name_rva == first_thunk == 0:
                break
            name_off = _pe_rva_to_offset(data, sections, name_rva)
            if name_off is not None:
                end = data.find(b"\0", name_off, min(len(data), name_off + 512))
                if end > name_off:
                    name = data[name_off:end].decode("ascii", errors="ignore").strip().casefold()
                    if name:
                        names.add(name)
            desc += 20
        return names
    except Exception:
        return set()


def choose_rtxmfg_proxy(
    game: "Game",
    reserved_names: set[str],
    managed_existing: Optional[set[str]] = None,
) -> Optional[str]:
    require(game.exe is not None and game.target_dir is not None, "Missing game EXE/target")
    imports = pe_imported_dlls(game.exe)
    reserved = {name.casefold() for name in reserved_names}
    managed = {name.casefold() for name in (managed_existing or set())}

    for name in RTXMFG_SUPPORTED_PROXY_NAMES:
        low = name.casefold()
        if low in reserved or low not in imports:
            continue
        dst = game.target_dir / name
        if dst.exists() and low not in managed:
            # Never overwrite a game/mod-owned DLL automatically.
            continue
        return name
    return None


# GPU / ReShade / INI --------------------------------------------------------

def nvidia_gpu_name() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return out.strip().splitlines()[0].strip() or None
    except Exception:
        return None

def gpu_family(name: Optional[str]) -> str:
    if not name:
        return "unknown"
    low = name.casefold()
    if re.search(r"\brtx\s*40\d\d\b", low) or "ada" in low:
        return "ada"
    if re.search(r"\brtx\s*(20|30)\d\d\b", low) or "ampere" in low or "turing" in low:
        return "sm86"
    return "unknown"

def file_contains_any(
    path: Path,
    needles: tuple[bytes, ...] | list[bytes],
    max_bytes: int = 64 * 1024 * 1024,
    chunk_size: int = 1024 * 1024,
) -> bool:
    """Case-insensitive streaming binary signature scan.

    Each candidate file is opened/read once regardless of marker count. Carrying
    ``max_marker_len - 1`` bytes between chunks preserves matches that straddle
    a read boundary without loading a large DLL into memory.
    """
    markers = tuple(bytes(n).lower() for n in needles if n)
    if not markers:
        return False
    require(chunk_size > 0, "Binary scan chunk size must be positive")
    try:
        if not path.is_file() or path.is_symlink():
            return False
        size = path.stat().st_size
        if size > max_bytes:
            return False
        overlap = max(len(n) for n in markers) - 1
        carry = b""
        with path.open("rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    return False
                hay = (carry + chunk).lower()
                if any(marker in hay for marker in markers):
                    return True
                carry = hay[-overlap:] if overlap > 0 else b""
    except OSError:
        return False


def file_contains(path: Path, needle: bytes, max_bytes: int = 64 * 1024 * 1024) -> bool:
    return file_contains_any(path, (needle,), max_bytes=max_bytes)

def detect_reshade(target: Path) -> dict:
    """
    Detect a real ReShade installation without mistaking OptiScaler's own proxy
    for ReShade merely because the DLL contains ReShade compatibility strings.

    A root dxgi.dll + ReShade config/shader markers is authoritative for this
    workflow. Binary strings are retained only as diagnostic evidence.
    """
    dxgi = target / "dxgi.dll"
    markers = (
        (target / "ReShade.ini").exists()
        or (target / "reshade-shaders").exists()
        or any(target.glob("ReShade*.ini"))
    )
    binary = dxgi.is_file() and file_contains(dxgi, b"reshade")
    detected = bool(dxgi.is_file() and markers)
    return {
        "detected": detected,
        "binary": binary,
        "markers": markers,
    }

def looks_like_old_graphics_proxy(path: Path) -> bool:
    return file_contains_any(path, (b"optiscaler", b"dlss enabler", b"dlss-enabler"))


def _optiscaler_proxy_is_safe(
    target: Path,
    name: str,
    prior_proxy: Optional[str],
    prior_hashes: dict,
) -> bool:
    path = target / name
    if not path.exists():
        return True
    if not path.is_file() or path.is_symlink():
        return False
    expected = prior_hashes.get(name) if prior_proxy == name else None
    if expected and sha256_file(path) == expected:
        return True
    return looks_like_old_graphics_proxy(path)


def choose_optiscaler_proxy(
    target: Path,
    reshade: dict,
    existing_baseline: Optional[dict] = None,
    exe: Optional[Path] = None,
    *,
    prefer_imported: bool = False,
    preserve_prior: bool = False,
) -> Optional[str]:
    """Choose a validated OptiScaler proxy without stealing DLL ownership.

    ``prefer_imported`` is the RC2 integrated-Ada hardening policy.  It ranks
    officially supported proxy names present in the selected EXE's normal PE
    import table ahead of the generic DXGI fallback, fixing the real-library
    class where files installed cleanly but OptiScaler never loaded.  When
    ``preserve_prior`` is true, a proxy with already-observed MFG execution is
    kept ahead of alternative imports. Legacy external/test routes retain the
    stricter RC1 dxgi/version behavior.
    """
    prior = (existing_baseline or {}).get("current") or {}
    prior_proxy = prior.get("proxy")
    prior_hashes = prior.get("installed_hashes") or {}
    imports = pe_imported_dlls(exe) if exe else set()

    if not prefer_imported:
        candidates = ["version.dll"] if reshade.get("detected") else ["dxgi.dll"]
        if not reshade.get("detected") and "version.dll" in imports:
            candidates.append("version.dll")
        for name in candidates:
            if _optiscaler_proxy_is_safe(target, name, prior_proxy, prior_hashes):
                return name
        return None

    supported = list(OPTISCALER_SUPPORTED_PROXY_NAMES)
    if reshade.get("detected"):
        supported = [name for name in supported if name.casefold() != "dxgi.dll"]

    imported = [name for name in supported if name.casefold() in imports]
    ordered: list[str] = []
    if preserve_prior and prior_proxy in imported:
        ordered.append(prior_proxy)
    ordered.extend(name for name in imported if name not in ordered)

    # Dynamic-load fallback.  ReShade coexistence historically uses version;
    # otherwise DXGI is the only unproven fallback we accept.  An unimported
    # version.dll must not become a way around an unknown game-owned dxgi.dll.
    if prior_proxy in supported and prior_proxy not in ordered and (preserve_prior or not imported):
        ordered.append(prior_proxy)
    fallback = "version.dll" if reshade.get("detected") else "dxgi.dll"
    if fallback in supported and fallback not in ordered:
        ordered.append(fallback)

    for name in ordered:
        if _optiscaler_proxy_is_safe(target, name, prior_proxy, prior_hashes):
            return name
    return None

def _section_span(text: str, section: str):
    m = re.search(
        rf"(?im)^[ \t]*\[{re.escape(section)}\][ \t]*(?:\r?\n|$)",
        text,
    )
    if not m:
        return None
    next_m = re.search(
        r"(?im)^[ \t]*\[[^\]]+\][ \t]*(?:\r?\n|$)",
        text[m.end():],
    )
    end = m.end() + next_m.start() if next_m else len(text)
    return m.start(), end

def set_ini_value(text: str, section: str, key: str, value: str) -> str:
    span = _section_span(text, section)
    newline = "\r\n" if "\r\n" in text else "\n"

    if not span:
        if not text.endswith(("\n", "\r")):
            text += newline
        return text + f"{newline}[{section}]{newline}{key}={value}{newline}"

    start, end = span
    block = text[start:end]
    key_re = re.compile(rf"(?im)^[ \t]*{re.escape(key)}[ \t]*=.*$")
    replacement = f"{key}={value}"
    if key_re.search(block):
        block = key_re.sub(replacement, block, count=1)
    else:
        block = block.rstrip("\r\n") + newline + replacement + newline
    return text[:start] + block + text[end:]


def remove_ini_key(text: str, section: str, key: str) -> str:
    span = _section_span(text, section)
    if not span:
        return text
    start, end = span
    block = text[start:end]
    key_re = re.compile(rf"(?im)^[ \t]*{re.escape(key)}[ \t]*=.*(?:\r?\n)?")
    block = key_re.sub("", block)
    return text[:start] + block + text[end:]


def detect_eos_overlay(root: Path, max_dirs: int = 12000) -> bool:
    """Detect the Epic/EOS overlay without following directory symlinks.

    OptiScaler documents EOS/EGS overlays as a startup-crash source when frame
    generation is active.  We enable its built-in overlay blocker only when the
    game actually carries an EOS overlay, avoiding a global Steam Input side
    effect on unrelated titles.
    """
    wanted = {"eosovh-win64-shipping.dll", "eosovh-win32-shipping.dll"}
    seen = 0
    try:
        for current, dirs, files in os.walk(root, followlinks=False):
            seen += 1
            if seen > max_dirs:
                return False
            base = Path(current)
            dirs[:] = [d for d in dirs if not (base / d).is_symlink()]
            if any(name.casefold() in wanted for name in files):
                return True
    except OSError:
        return False
    return False

def patch_optiscaler_ini(raw: bytes, family: str, ada_mfg_mode: str = "integrated", *, disable_overlays: bool = False) -> bytes:
    """Apply the single y4my-v4 Proton policy used by Handoff 188 RC1.

    This deliberately does not combine the old RTXForge v3e loader, Universal
    RTXMFG, or DLSS-Unlocked's OptiScaler build. MFG and NR are owned by the
    exact y4my v4 loader and its bundled Streamline/DLSS companion tree.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    # Remove settings from the superseded DLSS-Unlocked/older experimental NR
    # profile so a preserved user INI cannot silently keep a second NR policy.
    for obsolete in ("RunBeforeSR", "DeferredDLSS", "ResidualFG"):
        text = remove_ini_key(text, "DlssNr", obsolete)
    text = remove_ini_key(text, "FrameGen", "External")
    text = remove_ini_key(text, "DLSSG", "AmpereMfgUnlock")

    # Keep the exact provider pinned, but do not force the experimental overlay
    # renderer on every Proton title.  Upstream defaults this to auto, which is
    # deliberately less invasive and preserves the menu where compatible.
    # Alt+Insert remains the documented keyboard-layout fallback.
    text = set_ini_value(text, "Menu", "OverlayMenu", "auto")
    text = set_ini_value(text, "Menu", "ShortcutKey", "0x2D")
    text = set_ini_value(text, "Menu", "UseHQFont", "false")
    text = set_ini_value(text, "Menu", "DisableSplash", "true")
    text = set_ini_value(text, "Hotfix", "CheckForUpdate", "false")
    text = set_ini_value(text, "Log", "LogToFile", "true")
    text = set_ini_value(text, "Log", "LogLevel", "2")
    text = set_ini_value(text, "Log", "SingleFile", "true")

    # Native NVIDIA under Proton does not need whole-game DXGI/Vulkan identity
    # spoofing. These are the conservative y4my/upstream Linux settings and also
    # avoid the DXGI<->Vulkan re-entry class called out in the v4 release notes.
    text = set_ini_value(text, "Spoofing", "Dxgi", "false")
    text = set_ini_value(text, "Spoofing", "Vulkan", "false")

    # y4my's NR DualFeature arrangement runs the model after temporal settling
    # at render resolution, then enlarges with DLSS. Keep the runtime and the
    # intended profile installed, but DO NOT execute the experimental NR path
    # during process startup. Upstream/y4my leaves NR off by default and expects
    # the user to enable it from the overlay after the title reaches 3D. This is
    # especially important for the small-matrix rollout: a batch install must not
    # turn one compatibility failure into a launch crash across every title.
    # Keep the normal NVIDIA/upstream auto route on the first launch.  Forcing
    # an upscaler globally before we have one successful per-title launch is
    # another unnecessary compatibility variable.  NR still requires DLSS when
    # the user enables it.
    text = set_ini_value(text, "Upscalers", "Dx12Upscaler", "auto")
    text = set_ini_value(text, "DlssNr", "Enabled", "false")
    text = set_ini_value(text, "DlssNr", "DualFeature", "true")
    text = set_ini_value(text, "DlssNr", "DualEnlarger", "dlss")
    text = set_ini_value(text, "DlssNr", "PreUpscale", "false")
    text = set_ini_value(text, "DlssNr", "WorkingScale", "1.0")
    text = set_ini_value(text, "DlssNr", "Passes", "1")
    text = set_ini_value(text, "DlssNr", "TransferStrength", "1.0")
    text = set_ini_value(text, "DlssNr", "ColourStrength", "1.0")
    text = set_ini_value(text, "DlssNr", "AutoCapture", "false")

    # RC1.39: native game FG stays native. Selecting dlssg here initializes a
    # second output at D3D12 device creation even with Enabled=false.
    # nofg disables OptiScaler replacement, not the game's own DLSS-G.
    text = set_ini_value(text, "FrameGen", "Enabled", "false")
    text = set_ini_value(text, "FrameGen", "FGInput", "nofg")
    text = set_ini_value(text, "FrameGen", "FGOutput", "nofg")
    text = set_ini_value(text, "FrameGen", "FGNvngxReplacement", "None")

    if family == "ada":
        text = set_ini_value(text, "DLSSG", "AdaMfgUnlock", "false")
        text = set_ini_value(text, "DLSSG", "AdaBlackwellKernels", "auto")
        text = set_ini_value(text, "DLSSG", "InterpolationCount", "auto")
        text = set_ini_value(text, "DLSSG", "OverrideInterpolationCount", "auto")
        text = set_ini_value(text, "DLSSG", "OverrideForceDMFG", "false")
        text = set_ini_value(text, "DLSSG", "ForceDMFG", "false")
        # Do not globally change NVAPI pacing/reflex behavior before native MFG
        # is actually enabled for this title.
        text = set_ini_value(text, "NvApi", "DisableFlipMetering", "auto")
        text = set_ini_value(text, "NvApi", "DisableReflexSync", "auto")
    else:
        # Handoff 188 product decision: sm86 is an NR-only compatibility path.
        # Do not inherit the old experimental Ampere MFG unlock implicitly.
        text = set_ini_value(text, "FrameGen", "Enabled", "false")
        text = set_ini_value(text, "DLSSG", "AdaMfgUnlock", "false")
        text = set_ini_value(text, "DLSSG", "AdaBlackwellKernels", "auto")

    if disable_overlays:
        # Do not enable globally: y4my notes that this also blocks Steam Input.
        # Only an explicit caller may opt into it.
        text = set_ini_value(text, "Hotfix", "DisableOverlays", "true")

    return text.encode("utf-8")


# Surgical permission recovery -----------------------------------------------

def _can_mutate_dir(path: Path) -> bool:
    """
    Test whether the current user can create/remove a tiny file in this exact
    directory. This is stronger than os.access() on ACL/mounted filesystems.
    """
    if not path.is_dir():
        return False
    probe = path / f".rtxforge-write-probe-{os.getpid()}"
    try:
        with probe.open("xb") as f:
            f.write(b"x")
        probe.unlink()
        return True
    except OSError:
        try:
            if probe.exists():
                probe.unlink()
        except OSError:
            pass
        return False

def _tree_mutation_ready(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_dir() or path.is_symlink():
        return False
    if not _can_mutate_dir(path):
        return False
    try:
        for p in path.rglob("*"):
            if p.is_symlink():
                return False
            if p.is_dir() and not _can_mutate_dir(p):
                return False
            if p.is_file() and not os.access(p, os.W_OK):
                return False
    except OSError:
        return False
    return True

def _chmod_user_writable(path: Path) -> None:
    """
    First repair pass: preserve all existing mode bits and only add the owning
    user's read/write (and directory execute) permissions.
    """
    paths = [path]
    if path.is_dir():
        paths.extend(path.rglob("*"))

    # Children first is not required for chmod, but ensure directories become
    # traversable as soon as encountered.
    for p in paths:
        if p.is_symlink():
            raise Stop(f"Symlink inside managed path refused: {p}")
        try:
            mode = stat.S_IMODE(p.stat().st_mode)
            if p.is_dir():
                wanted = mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
            else:
                wanted = mode | stat.S_IRUSR | stat.S_IWUSR
            if wanted != mode:
                os.chmod(p, wanted)
        except OSError:
            # Caller will decide whether elevation is needed.
            pass

def _sudo_available() -> bool:
    return shutil.which("sudo") is not None

def _sudo_repair(path: Path, recursive: bool) -> None:
    """
    Escalation is intentionally narrow: ONLY the exact conflicting path the
    engine is about to replace. Never chmod/chown the game root or G: recursively.
    """
    require(_sudo_available(), f"Need ownership repair but sudo is unavailable: {path}")
    uid = os.getuid()
    gid = os.getgid()

    chown = ["sudo", "chown"]
    chmod = ["sudo", "chmod"]
    if recursive:
        chown.append("-R")
        chmod.append("-R")
    chown += [f"{uid}:{gid}", "--", str(path)]
    chmod += ["u+rwX", "--", str(path)]

    subprocess.run(chown, check=True)
    subprocess.run(chmod, check=True)

def ensure_tree_replaceable(path: Path, label: str) -> bool:
    """
    Make an existing mod tree replaceable, using the smallest possible scope.
    Returns True when a permission repair was necessary.
    """
    if not path.exists():
        return False
    require(path.is_dir() and not path.is_symlink(), f"{label} is not a normal directory: {path}")

    if _tree_mutation_ready(path):
        return False

    warn(f"{label} is not writable; repairing that directory only")
    _chmod_user_writable(path)
    if _tree_mutation_ready(path):
        ok(f"Permission repair complete: {path}")
        return True

    warn(f"{label} needs elevated ownership repair: {path}")
    _sudo_repair(path, recursive=True)
    require(_tree_mutation_ready(path), f"Permission repair did not make {label} replaceable: {path}")
    ok(f"Ownership repair complete: {path}")
    return True

def ensure_file_replaceable(path: Path, label: str) -> bool:
    """
    Narrow repair for one root file rtxEngine is explicitly replacing/removing.
    """
    if not path.exists():
        return False
    require(path.is_file() and not path.is_symlink(), f"{label} is not a normal file: {path}")

    if os.access(path, os.W_OK) and _can_mutate_dir(path.parent):
        return False

    warn(f"{label} is not writable; repairing that file only")
    _chmod_user_writable(path)
    if os.access(path, os.W_OK) and _can_mutate_dir(path.parent):
        return True

    _sudo_repair(path, recursive=False)
    require(os.access(path, os.W_OK), f"Permission repair failed: {path}")
    return True

# State / restore ------------------------------------------------------------

def state_dir_for(target: Path) -> Path:
    return STATE_ROOT / "targets" / target_key(target)

def _validated_state_namespace(name: str) -> Path:
    require(re.fullmatch(r"[A-Za-z0-9._-]+", name or "") is not None, f"Invalid state namespace: {name!r}")
    root = STATE_ROOT / name
    require(not root.is_symlink(), f"State namespace symlink refused: {root}")
    state_root = STATE_ROOT.resolve(strict=False)
    try:
        root.resolve(strict=False).relative_to(state_root)
    except (OSError, ValueError):
        raise Stop(f"State namespace escapes STATE_ROOT: {root}")
    return root

def _validated_targets_root() -> Path:
    return _validated_state_namespace("targets")

def _validated_state_child_dir(root: Path, *parts: str) -> Path:
    """Build a state child directory path without allowing symlink pivots.

    STATE_ROOT itself may intentionally resolve through another filesystem, but
    once a protected namespace root is chosen, every generated directory
    component beneath it must be a literal directory entry rather than a link.
    """
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), f"Unsafe state child root: {root}")
    root_resolved = root.resolve(strict=False)
    current = root
    for part in parts:
        require(re.fullmatch(r"[A-Za-z0-9._-]+", part or "") is not None, f"Invalid state child name: {part!r}")
        current = current / part
        require(not current.is_symlink(), f"State child directory symlink refused: {current}")
        if current.exists():
            require(current.is_dir(), f"State child path is not a directory: {current}")
        try:
            current.resolve(strict=False).relative_to(root_resolved)
        except (OSError, ValueError):
            raise Stop(f"State child directory escapes namespace: {current}")
    return current


def _validated_state_dir(target: Path, *, require_exists: bool = False) -> Path:
    targets = _validated_targets_root()
    state_dir = targets / target_key(target)
    require(not state_dir.is_symlink(), f"Per-target state directory symlink refused: {state_dir}")
    try:
        state_dir.resolve(strict=False).relative_to(targets.resolve(strict=False))
    except (OSError, ValueError):
        raise Stop(f"Per-target state directory escapes targets root: {state_dir}")
    if require_exists:
        require(state_dir.is_dir(), f"Per-target state directory missing: {state_dir}")
    return state_dir

def baseline_path(target: Path) -> Path:
    return _validated_state_dir(target) / "baseline.json"

def save_json_atomic(path: Path, data: dict) -> None:
    atomic_write(
        path,
        (json.dumps(data, indent=2, sort_keys=True) + "\n").encode(),
        0o600,
    )

def _normalize_state_rel(rel: str, *, allow_dir_marker: bool = True) -> str:
    """Validate a persisted target-relative path before it is trusted."""
    require(isinstance(rel, str), "State path is not a string")
    require(rel and "\x00" not in rel, "State path is empty or contains NUL")
    require("\\" not in rel and ":" not in rel, f"Unsafe persisted path: {rel!r}")
    dir_marker = allow_dir_marker and rel.endswith("/")
    raw = rel[:-1] if dir_marker else rel
    require(raw, f"Unsafe persisted path: {rel!r}")
    pp = PurePosixPath(raw)
    require(not pp.is_absolute(), f"Absolute persisted path refused: {rel!r}")
    require(all(part not in {"", ".", ".."} for part in pp.parts), f"Traversal persisted path refused: {rel!r}")
    normalized = pp.as_posix()
    require(normalized == raw, f"Non-canonical persisted path refused: {rel!r}")
    return normalized + ("/" if dir_marker else "")

def _target_member_path(target: Path, rel: str) -> Path:
    """Resolve a persisted relative game path without allowing symlink escape."""
    normalized = _normalize_state_rel(rel).rstrip("/")
    root = target.resolve()
    parts = PurePosixPath(normalized).parts
    candidate = root.joinpath(*parts)
    try:
        candidate.resolve(strict=False).relative_to(root)
    except (OSError, ValueError):
        raise Stop(f"Persisted path escapes target: {rel!r}")

    cur = root
    for part in parts:
        cur = cur / part
        if cur.is_symlink():
            raise Stop(f"Persisted path crosses symlink: {rel!r}")
    return candidate

def _validated_baseline_backup_root(target: Path, *, require_exists: bool = False) -> Path:
    """Return the active baseline payload root without following a pivot."""
    state_dir = _validated_state_dir(target, require_exists=True)
    root = state_dir / "baseline-backup"
    require(not root.is_symlink(), f"Baseline backup root symlink refused: {root}")
    try:
        root.resolve(strict=False).relative_to(state_dir.resolve(strict=False))
    except (OSError, ValueError):
        raise Stop(f"Baseline backup root escapes target state: {root}")
    if root.exists():
        require(root.is_dir(), f"Baseline backup root is not a directory: {root}")
    elif require_exists:
        raise Stop(f"Baseline backup root missing: {root}")
    return root


def _no_follow_child_path(root: Path, rel: str) -> Path:
    """Return a lexical child path while refusing existing symlink pivots."""
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), f"Unsafe child-path root: {root}")
    normalized = safe_rel(rel)
    parts = PurePosixPath(normalized).parts
    candidate = root.joinpath(*parts)
    cur = root
    for part in parts:
        cur = cur / part
        require(not cur.is_symlink(), f"Child path crosses symlink: {cur}")
    root_resolved = root.resolve(strict=False)
    try:
        candidate.resolve(strict=False).relative_to(root_resolved)
    except (OSError, ValueError):
        raise Stop(f"Child path escapes protected root: {rel!r}")
    return candidate


def _baseline_backup_member(target: Path, raw: str) -> Path:
    """Require persisted backup artifacts to stay inside this target's active backup slot."""
    require(isinstance(raw, str) and raw, "Baseline backup path missing")
    backup_root_path = _validated_baseline_backup_root(target, require_exists=True)
    backup_root = backup_root_path.resolve(strict=False)
    path = Path(raw).expanduser()
    require(path.is_absolute(), f"Baseline backup path is not absolute: {raw!r}")
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(backup_root)
    except (OSError, ValueError):
        raise Stop(f"Baseline backup path escapes state backup: {raw!r}")
    cur = backup_root
    try:
        rel = resolved.relative_to(backup_root)
    except ValueError:
        raise Stop(f"Baseline backup path escapes state backup: {raw!r}")
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise Stop(f"Baseline backup path crosses symlink: {raw!r}")
    return resolved

def _validate_restore_recovery_dir(target: Path, raw: str, *, require_exists: bool = True) -> Path:
    """Validate the baseline-bound recovery slot used across restore retries."""
    require(isinstance(raw, str) and raw, "Restore recovery path missing")
    state_dir = _validated_state_dir(target, require_exists=True)
    root_path = state_dir / "recovery-before-restore"
    require(not root_path.is_symlink(), f"Restore recovery root symlink refused: {root_path}")
    root = root_path.resolve(strict=False)
    try:
        root.relative_to(state_dir.resolve(strict=False))
    except ValueError:
        raise Stop(f"Restore recovery root escapes target state: {root_path}")
    path = Path(raw).expanduser()
    require(path.is_absolute(), f"Restore recovery path is not absolute: {raw!r}")
    require(not path.is_symlink(), f"Restore recovery path symlink refused: {raw!r}")
    try:
        resolved = path.resolve(strict=False)
        rel = resolved.relative_to(root)
    except (OSError, ValueError):
        raise Stop(f"Restore recovery path escapes state root: {raw!r}")
    require(len(rel.parts) == 1, f"Restore recovery path must be one state slot: {raw!r}")
    cur = root / rel.parts[0]
    require(not cur.is_symlink(), f"Restore recovery slot symlink refused: {raw!r}")
    if require_exists:
        require(cur.is_dir(), f"Recorded restore recovery slot is missing: {cur}")
    return cur


def _tree_manifest_data(root: Path) -> dict:
    require(root.is_dir() and not root.is_symlink(), f"Unsafe baseline tree: {root}")
    rows = []
    total = 0
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda x: x.relative_to(root).as_posix()):
        require(not path.is_symlink(), f"Symlink inside baseline tree refused: {path}")
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        sha = sha256_file(path)
        size = path.stat().st_size
        total += size
        rows.append({"path": rel, "bytes": size, "sha256": sha})
        digest.update(rel.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(str(size).encode())
        digest.update(b"\0")
        digest.update(sha.encode())
        digest.update(b"\n")
    return {
        "version": 1,
        "file_count": len(rows),
        "bytes": total,
        "tree_sha256": digest.hexdigest(),
        "files": rows,
    }

def _write_tree_manifest(backup_root: Path, name: str, tree: Path) -> dict:
    manifest = _tree_manifest_data(tree)
    path = _no_follow_child_path(backup_root, f"manifests/{name}.json")
    save_json_atomic(path, manifest)
    return {
        "manifest": str(path),
        "manifest_sha256": sha256_file(path),
        "tree_sha256": manifest["tree_sha256"],
        "file_count": manifest["file_count"],
        "bytes": manifest["bytes"],
    }

def _verify_tree_manifest(target: Path, info: dict, tree: Path) -> None:
    manifest_path = _baseline_backup_member(target, info.get("manifest", ""))
    require(manifest_path.is_file(), f"Baseline tree manifest missing: {manifest_path}")
    require(sha256_file(manifest_path) == info.get("manifest_sha256"), "Baseline tree manifest hash mismatch")
    try:
        expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Stop(f"Baseline tree manifest is corrupt: {manifest_path}: {exc}") from exc
    actual = _tree_manifest_data(tree)
    require(actual.get("tree_sha256") == expected.get("tree_sha256") == info.get("tree_sha256"), "Baseline tree integrity mismatch")
    require(actual.get("file_count") == expected.get("file_count"), "Baseline tree file-count mismatch")

def _validate_tar_members(members, *, expected_top: str, exact_file: bool = False, label: str = "baseline tar") -> None:
    require(members, f"Baseline tar archive is empty: {label}")
    saw_expected = False
    seen_members: set[str] = set()
    for member in members:
        raw = member.name
        while raw.startswith("./"):
            raw = raw[2:]
        require(raw not in seen_members, f"Duplicate tar member refused: {member.name!r}")
        seen_members.add(raw)
        pp = PurePosixPath(raw)
        require(raw and not pp.is_absolute(), f"Unsafe tar member: {member.name!r}")
        require(all(part not in {"", ".", ".."} for part in pp.parts), f"Unsafe tar member: {member.name!r}")
        require(not (member.issym() or member.islnk() or member.isdev()), f"Unsafe tar member type: {member.name!r}")
        require(member.isfile() or member.isdir(), f"Unsupported tar member type: {member.name!r}")
        if exact_file:
            require(raw == expected_top, f"Unexpected file tar member: {member.name!r}")
            saw_expected = member.isfile()
        else:
            require(raw == expected_top or raw.startswith(expected_top + "/"), f"Tar member escapes expected tree: {member.name!r}")
            if raw == expected_top:
                require(member.isdir(), f"Expected tar tree root is not a directory: {member.name!r}")
                saw_expected = True
            elif raw.startswith(expected_top + "/"):
                saw_expected = True
    require(saw_expected, f"Expected tar payload missing: {expected_top}")

def _validate_tar_archive(archive: Path, *, expected_top: str, exact_file: bool = False) -> None:
    require(archive.is_file() and not archive.is_symlink(), f"Baseline tar archive missing/unsafe: {archive}")
    try:
        with tarfile.open(archive, "r:*") as tf:
            _validate_tar_members(tf.getmembers(), expected_top=expected_top, exact_file=exact_file, label=str(archive))
    except (tarfile.TarError, OSError) as exc:
        raise Stop(f"Baseline tar archive is corrupt: {archive}: {exc}") from exc

@contextmanager
def _validated_tar_snapshot(archive: Path, expected_sha256: str, *, expected_top: str, exact_file: bool = False):
    """Stage, hash, and validate the exact tar bytes later consumed by sudo tar.

    The baseline tar is user-owned so validating its pathname and reopening that
    pathname later creates a TOCTOU window.  Copy it once into an anonymous
    TemporaryFile, bind the copy to the persisted SHA-256, validate its members,
    then hand that same open file descriptor to the privileged extractor.
    """
    require(archive.is_file() and not archive.is_symlink(), f"Baseline tar archive missing/unsafe: {archive}")
    require(isinstance(expected_sha256, str) and len(expected_sha256) == 64, "Baseline tar hash is corrupt")
    snap = tempfile.TemporaryFile(mode="w+b")
    try:
        digest = hashlib.sha256()
        with archive.open("rb") as src:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                snap.write(chunk)
        require(digest.hexdigest() == expected_sha256, f"Baseline tar hash mismatch: {archive}")
        snap.flush()
        snap.seek(0)
        try:
            with tarfile.open(fileobj=snap, mode="r:*") as tf:
                _validate_tar_members(tf.getmembers(), expected_top=expected_top, exact_file=exact_file, label=str(archive))
        except (tarfile.TarError, OSError) as exc:
            raise Stop(f"Baseline tar archive is corrupt: {archive}: {exc}") from exc
        snap.seek(0)
        yield snap
    finally:
        snap.close()

def _adopt_legacy_integrity_metadata(target: Path, baseline: dict) -> bool:
    """Add integrity metadata to pre-hardening baselines without touching live game files."""
    changed = False
    backup_root = _validated_baseline_backup_root(target, require_exists=False)
    for rel, info in baseline.get("originals", {}).items():
        if not isinstance(info, dict) or not info.get("existed"):
            continue
        kind = info.get("kind")
        backup = _baseline_backup_member(target, info.get("backup", ""))
        if kind == "tree" and "manifest" not in info:
            require(backup.is_dir(), f"Legacy baseline tree missing: {rel}")
            meta = _write_tree_manifest(backup_root, "legacy-" + hashlib.sha256(rel.encode()).hexdigest()[:12], backup)
            info.update(meta)
            info["integrity_adopted_utc"] = now_iso()
            changed = True
        elif kind in {"tar_tree", "tar_file"} and "archive_sha256" not in info:
            require(backup.is_file(), f"Legacy baseline archive missing: {rel}")
            info["archive_sha256"] = sha256_file(backup)
            info["integrity_adopted_utc"] = now_iso()
            changed = True
    if changed:
        warn(f"Adopted integrity metadata for legacy baseline: {target}")
        save_json_atomic(baseline_path(target), baseline)
    return changed

def verify_baseline_integrity(target: Path, baseline: dict, *, adopt_legacy: bool = True) -> None:
    """Validate the complete persisted restore plan before any live game mutation."""
    require(isinstance(baseline, dict), "Baseline state is not an object")
    require(Path(baseline.get("target_dir", "")).resolve() == target.resolve(), "State target mismatch")
    originals = baseline.get("originals")
    managed = baseline.get("managed_paths", [])
    require(isinstance(originals, dict), "Baseline originals map is missing/corrupt")
    require(isinstance(managed, list), "Baseline managed_paths is missing/corrupt")

    # Track the exact normalized spelling bound to each case-folded key. A
    # path may legitimately appear once in originals and again in managed_paths,
    # but a differently-cased spelling must never borrow that exception.
    normalized_seen: dict[str, str] = {}
    original_keys: dict[str, str] = {}
    for rel in originals:
        normalized = _normalize_state_rel(rel)
        key = normalized.casefold()
        prior = normalized_seen.get(key)
        require(prior is None or prior == normalized, f"Case-colliding persisted path: {rel!r}")
        normalized_seen[key] = normalized
        original_keys[key] = rel
        _target_member_path(target, rel)
    for rel in managed:
        normalized = _normalize_state_rel(rel)
        key = normalized.casefold()
        prior = normalized_seen.get(key)
        require(prior is None or prior == normalized, f"Case-colliding persisted path: {rel!r}")
        normalized_seen[key] = normalized
        _target_member_path(target, rel)

    # A root-level managed file is a deletion/restore ownership claim. Never
    # honor that claim unless the baseline explicitly captured what existed
    # before rtxEngine touched the filename. OptiScaler descendants are covered
    # by the single OptiScaler/ tree baseline and are intentionally exempt.
    for rel in managed:
        normalized = _normalize_state_rel(rel)
        key = normalized.casefold()
        # On Linux, only the exact canonical OptiScaler/ subtree is covered
        # by the single tree baseline. A differently-cased path such as
        # optiscaler/foo.dll is a distinct filesystem object and must carry
        # its own original baseline before restore may delete it.
        if normalized.startswith("OptiScaler/") and normalized != "OptiScaler/":
            continue
        require(
            key in original_keys,
            f"Managed root path is missing its recovery baseline: {rel}",
        )

    if adopt_legacy:
        _adopt_legacy_integrity_metadata(target, baseline)

    for rel, info in originals.items():
        require(isinstance(info, dict), f"Corrupt baseline entry: {rel}")
        existed = info.get("existed")
        require(isinstance(existed, bool), f"Baseline existed flag invalid: {rel}")
        if not existed:
            continue
        kind = info.get("kind")
        require(kind in {"file", "tree", "tar_file", "tar_tree"}, f"Unknown baseline kind for {rel}: {kind!r}")

        # Bind recovery payload type to the exact destination it represents.
        # OptiScaler/ is the one canonical tree baseline; every other original
        # is a single-file baseline. Without this binding, a corrupt root DLL
        # entry recorded as tar_tree can pass preflight and later be restored
        # as the tar archive bytes themselves after the live DLL was deleted.
        if rel == "OptiScaler/":
            require(kind in {"tree", "tar_tree"}, f"OptiScaler baseline kind is not a tree: {kind!r}")
        else:
            require(kind in {"file", "tar_file"}, f"File baseline kind is not a file for {rel}: {kind!r}")

        backup = _baseline_backup_member(target, info.get("backup", ""))
        if kind == "file":
            require(backup.is_file() and not backup.is_symlink(), f"Baseline file missing: {rel}")
            require(isinstance(info.get("sha256"), str) and len(info["sha256"]) == 64, f"Baseline file hash missing: {rel}")
            mode = info.get("mode")
            require(
                type(mode) is int and 0 <= mode <= 0o7777,
                f"Baseline file mode invalid: {rel}",
            )
            require(sha256_file(backup) == info["sha256"], f"Baseline file hash mismatch: {rel}")
        elif kind == "tree":
            require(backup.is_dir() and not backup.is_symlink(), f"Baseline tree missing: {rel}")
            _verify_tree_manifest(target, info, backup)
        elif kind == "tar_file":
            require(sha256_file(backup) == info.get("archive_sha256"), f"Baseline tar hash mismatch: {rel}")
            member = _normalize_state_rel(info.get("member", ""), allow_dir_marker=False)
            restore_parent = info.get("restore_parent", ".")
            if restore_parent == ".":
                restore_rel = member
            else:
                restore_parent = _normalize_state_rel(restore_parent, allow_dir_marker=False)
                _target_member_path(target, restore_parent)
                restore_rel = f"{restore_parent}/{member}"
            expected_rel = _normalize_state_rel(rel, allow_dir_marker=False)
            require(
                restore_rel == expected_rel,
                f"Baseline tar restore destination mismatch: {rel}",
            )
            _validate_tar_archive(backup, expected_top=member, exact_file=True)
        elif kind == "tar_tree":
            require(sha256_file(backup) == info.get("archive_sha256"), f"Baseline tar hash mismatch: {rel}")
            expected = _normalize_state_rel(rel).rstrip("/")
            _validate_tar_archive(backup, expected_top=expected, exact_file=False)

    _validate_provider_relinquish_state(target, baseline)

    recovery_slot = baseline.get("restore_recovery_dir")
    if recovery_slot is not None:
        _validate_restore_recovery_dir(target, recovery_slot, require_exists=True)

    steam_launch = baseline.get("steam_launch")
    if steam_launch is not None:
        _validate_steam_launch_record(steam_launch)

    current = baseline.get("current") or {}
    hashes = current.get("installed_hashes") or {}
    require(isinstance(hashes, dict), "Baseline installed_hashes is corrupt")
    for rel, digest in hashes.items():
        _normalize_state_rel(rel)
        require(isinstance(digest, str) and len(digest) == 64, f"Invalid installed hash for {rel}")

def load_baseline(target: Path, *, readonly: bool = False) -> Optional[dict]:
    path = _validated_state_dir(target) / "baseline.json"
    require(not path.is_symlink(), f"Baseline state file symlink refused: {path}")
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Stop(f"Corrupt rtxEngine state: {path}: {exc}") from exc
    require(isinstance(data, dict), f"Corrupt rtxEngine state object: {path}")
    schema = data.get("schema")
    require(
        type(schema) is int and schema in {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, ENGINE_SCHEMA},
        "Unsupported rtxEngine/legacy rtxForge state",
    )
    require(isinstance(data.get("target_dir"), str) and data["target_dir"], "State target missing")
    require(Path(data["target_dir"]).resolve() == target.resolve(), "State target mismatch")
    if schema in {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}:
        # Normalize older prototype state into v6.
        data["schema"] = ENGINE_SCHEMA
        data["status"] = data.get("status") or ("active" if data.get("current") else "interrupted")
    return data

def quarantine_orphan_baseline_backup(target: Path) -> Optional[Path]:
    """
    Recover the canonical backup slot left by old prototype runs.

    If baseline.json is absent but baseline-backup/ remains, preserve that
    directory under a timestamped history name instead of deleting it.
    """
    state_dir = _validated_state_dir(target)
    backup = state_dir / "baseline-backup"
    baseline = state_dir / "baseline.json"

    if baseline.exists() or not backup.exists():
        return None

    require(
        backup.is_dir() and not backup.is_symlink(),
        f"Unsafe orphan baseline backup: {backup}",
    )

    stamp = now_stamp()
    archived = state_dir / f"baseline-backup-orphan-{stamp}"
    counter = 1
    while archived.exists():
        archived = state_dir / f"baseline-backup-orphan-{stamp}-{counter}"
        counter += 1

    durable_replace(backup, archived)
    # This newly quarantined slot may be the only surviving recovery source for
    # the interrupted install. Never let generic mtime retention choose an
    # older orphan over the one we just recovered.
    other_orphans = [
        p for p in state_dir.glob("baseline-backup-orphan-*")
        if p != archived
    ]
    _prune_paths(other_orphans, keep=0)
    warn(f"Recovered stale baseline state: {archived.name}")
    return archived


def _prune_paths(paths: list[Path], keep: int) -> None:
    """Keep only the newest N historical paths; never touches active state slots."""
    rows = []
    for path in paths:
        try:
            rows.append((path.stat().st_mtime_ns, path))
        except OSError:
            continue
    rows.sort(reverse=True)
    for _mtime, path in rows[max(0, keep):]:
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
        except OSError:
            pass


def prune_target_history(target: Path, protected_recovery: Optional[Path] = None) -> None:
    """Cap non-active recovery history without discarding the restore just made.

    A baseline-bound recovery slot outranks mtime. User/runtime drift preserved
    during the just-completed restore must never lose to older history merely
    because timestamps are skewed or manipulated.
    """
    state_dir = _validated_state_dir(target)
    if not state_dir.is_dir():
        return
    _prune_paths(list(state_dir.glob("baseline-restored-*.json")), keep=1)
    _prune_paths(list(state_dir.glob("baseline-backup-restored-*")), keep=0)
    _prune_paths(list(state_dir.glob("baseline-backup-orphan-*")), keep=1)
    recovery = state_dir / "recovery-before-restore"
    if recovery.is_dir():
        entries = [p for p in recovery.iterdir() if p.is_dir() or p.is_file()]
        protected: Optional[Path] = None
        if protected_recovery is not None:
            protected = _validate_restore_recovery_dir(
                target, str(protected_recovery), require_exists=True
            )
            # Empty slots carry no preserved user/runtime bytes and need not be
            # retained after a successful restore.
            try:
                has_payload = protected.is_file() or any(protected.iterdir())
            except OSError:
                has_payload = True  # fail safe: preserve ambiguous recovery
            if not has_payload:
                protected = None

        if protected is not None:
            _prune_paths([p for p in entries if p != protected], keep=0)
        elif protected_recovery is not None:
            # Caller explicitly identified the just-completed slot, but it was
            # empty. There is no current recovery payload worth retaining.
            _prune_paths(entries, keep=0)
        else:
            # Generic maintenance (no current restore context) keeps one thin
            # historical recovery generation, preserving established behavior.
            _prune_paths(entries, keep=1)
        try:
            if not any(recovery.iterdir()):
                recovery.rmdir()
                _fsync_dir(recovery.parent)
        except OSError:
            pass


def _active_steam_backup_generations(root: Path) -> Optional[set[Path]]:
    """Return backup generations referenced by live Steam transaction journals.

    None means transaction state could not be trusted, in which case retention
    pruning must fail safe and preserve every backup generation.
    """
    tx_root = _steam_transaction_root()
    protected: set[Path] = set()
    if not tx_root.is_dir():
        return protected
    try:
        journals = list(tx_root.glob("*.json"))
    except OSError:
        return None
    root_resolved = root.resolve(strict=False)
    for journal in journals:
        try:
            if journal.is_symlink():
                return None
            data = json.loads(journal.read_text(encoding="utf-8"))
            raw = data.get("file_backup")
            if not isinstance(raw, str) or not raw:
                return None
            backup = Path(raw).expanduser().resolve(strict=False)
            rel = backup.relative_to(root_resolved)
            require(len(rel.parts) >= 2, "Steam transaction backup path is malformed")
            generation = (root / rel.parts[0]).resolve(strict=False)
            generation.relative_to(root_resolved)
            protected.add(generation)
        except Exception:
            return None
    return protected

def prune_steam_config_backups(keep: int = 2, extra_protected: Optional[set[Path]] = None) -> None:
    root = _validated_state_namespace("steam-config-backups")
    if not root.is_dir():
        return
    protected = _active_steam_backup_generations(root)
    if protected is None:
        # A corrupt/ambiguous transaction journal is exactly when deleting old
        # Steam config backups would be least defensible. Recovery state wins
        # over retention until the journal is repaired or removed.
        return
    if extra_protected:
        root_resolved = root.resolve(strict=False)
        for path in extra_protected:
            try:
                resolved = Path(path).resolve(strict=False)
                resolved.relative_to(root_resolved)
                protected.add(resolved)
            except (OSError, ValueError):
                raise Stop(f"Protected Steam backup generation escapes backup root: {path}")
    candidates = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            continue
        if resolved in protected:
            continue
        candidates.append(path)
    _prune_paths(candidates, keep=keep)


def _cleanup_state_trash() -> int:
    """Best-effort cleanup of previously retired state without crossing hazards."""
    root = _state_trash_root()
    if not root.exists():
        return 0
    require(root.is_dir() and not root.is_symlink(), f"Unsafe state-trash root: {root}")
    removed = 0
    for child in list(root.iterdir()):
        try:
            if child.is_symlink() or child.is_file():
                durable_unlink(child)
                removed += 1
                continue
            if not child.is_dir():
                warn(f"Unknown state-trash entry preserved: {child}")
                continue
            hazards = _pristine_tree_hazards(child)
            if hazards:
                warn(f"State-trash entry preserved because cleanup found a filesystem hazard: {child}: {hazards[0]}")
                continue
            shutil.rmtree(child)
            _fsync_dir(root)
            removed += 1
        except OSError as exc:
            warn(f"Could not clean retired state trash entry: {child}: {exc}")
    return removed

def _retire_state_tree(path: Path, label: str) -> Optional[Path]:
    """Atomically move inactive state out of its live namespace before cleanup."""
    require(re.fullmatch(r"[A-Za-z0-9._-]+", label or "") is not None, f"Invalid state-trash label: {label!r}")
    require(path.is_dir() and not path.is_symlink(), f"Unsafe state tree retirement: {path}")
    trash_root = _state_trash_root()
    _mkdir_durable(trash_root)
    _cleanup_state_trash()
    tombstone = trash_root / f"{label}-{now_stamp()}-{time.time_ns()}"
    durable_replace(path, tombstone)
    try:
        hazards = _pristine_tree_hazards(tombstone)
        if hazards:
            warn(f"Retired state remains in trash because cleanup found a filesystem hazard: {tombstone}: {hazards[0]}")
            return tombstone
        shutil.rmtree(tombstone)
        _fsync_dir(trash_root)
        return None
    except OSError as exc:
        warn(f"Retired state remains in trash for later cleanup: {tombstone}: {exc}")
        return tombstone


def discard_consumed_baseline_backup(target: Path) -> int:
    """Retire payload backup after a fully verified successful restore.

    The original bytes are already back in the game at this point. Move the
    consumed payload out of the active ``baseline-backup`` name atomically
    before recursive garbage collection so a crash cannot make a half-deleted
    payload look like a fresh orphan recovery source on the next install.
    """
    backup = _validated_baseline_backup_root(target, require_exists=False)
    if not backup.exists():
        return 0
    require(backup.is_dir() and not backup.is_symlink(), f"Unsafe baseline backup: {backup}")
    size = directory_size(backup)
    try:
        _retire_state_tree(backup, f"consumed-{target_key(target)}")
    except OSError as exc:
        # Restore is already complete and its compact receipt is committed.
        # Cleanup failure is retention hygiene, not a reason to misreport the
        # game as still unrestored.
        warn(f"Could not retire consumed baseline backup: {backup}: {exc}")
        return 0
    return size


def _backup_file_tar(src: Path, backup_root: Path, rel: str) -> dict:
    """
    Privileged read-only backup for a single pre-existing root/package file.

    This is used when the current user cannot read the original file before
    mutation. The live file is not chmod/chowned until AFTER baseline.json exists.
    """
    require(shutil.which("sudo") is not None, "sudo is required for privileged baseline backup")
    require(shutil.which("tar") is not None, "tar is required for privileged baseline backup")

    rel_posix = PurePosixPath(rel)
    archive = _no_follow_child_path(backup_root, f"file-tars/{rel_posix.as_posix()}.tar")
    _mkdir_durable(archive.parent)
    require(not archive.exists(), f"Backup archive already exists: {archive}")

    # Refuse symlink without needing to open/read the file.
    out = subprocess.check_output(
        ["sudo", "find", str(src), "-maxdepth", "0", "-type", "l", "-print"],
        text=True,
        stderr=subprocess.STDOUT,
    )
    require(not out.strip(), f"Symlink baseline source refused: {src}")

    uid, gid = os.getuid(), os.getgid()
    subprocess.run([
        "sudo", "tar",
        "--acls", "--xattrs", "--numeric-owner",
        "-cpf", str(archive),
        "-C", str(src.parent),
        src.name,
    ], check=True)
    subprocess.run(["sudo", "chown", f"{uid}:{gid}", "--", str(archive)], check=True)
    os.chmod(archive, 0o600)
    _fsync_file(archive)
    _fsync_dir(archive.parent)

    require(archive.is_file() and archive.stat().st_size > 0, f"Privileged file backup failed: {src}")
    listing = subprocess.check_output(["tar", "-tf", str(archive)], text=True)
    members = [line.strip().lstrip("./") for line in listing.splitlines() if line.strip()]
    require(src.name in members, f"Unexpected privileged file backup contents: {archive}")

    return {
        "kind": "tar_file",
        "existed": True,
        "backup": str(archive),
        "member": src.name,
        "restore_parent": "." if str(rel_posix.parent) == "." else rel_posix.parent.as_posix(),
        "bytes": archive.stat().st_size,
        "archive_sha256": sha256_file(archive),
        "preserves_numeric_owner": True,
    }


def backup_file(src: Path, backup_root: Path, rel: str) -> dict:
    dst = _no_follow_child_path(backup_root, f"files/{_normalize_state_rel(rel)}")
    try:
        copy_verified(src, dst)
        return {
            "kind": "file",
            "existed": True,
            "backup": str(dst),
            "sha256": sha256_file(src),
            "mode": stat.S_IMODE(src.stat().st_mode),
        }
    except PermissionError:
        # The baseline must precede mutation. Use privileged READ access to
        # archive the exact file, then repair the live file later.
        try:
            if dst.exists():
                dst.unlink()
        except OSError:
            pass
        warn(f"Baseline needs privileged read access: {src}")
        return _backup_file_tar(src, backup_root, rel)


def _sudo_capture(args: list[str]) -> str:
    require(shutil.which("sudo") is not None, "sudo is required for privileged baseline backup")
    return subprocess.check_output(["sudo", *args], text=True, stderr=subprocess.STDOUT)

def _privileged_tree_has_symlink(src: Path) -> bool:
    out = _sudo_capture(["find", str(src), "-type", "l", "-print", "-quit"])
    return bool(out.strip())

def _backup_tree_tar(src: Path, backup_root: Path, name: str) -> dict:
    """
    Backup an unreadable/untraversable source tree WITHOUT changing it first.

    GNU tar runs through sudo and preserves the source ownership/mode metadata
    inside the archive. The tar file itself is then handed back to the user.
    """
    require(shutil.which("tar") is not None, "tar is required for privileged baseline backup")
    require(not _privileged_tree_has_symlink(src), f"Symlink inside existing {name}/ refused")

    archive = _no_follow_child_path(backup_root, f"trees/{name}.tar")
    _mkdir_durable(archive.parent)
    require(not archive.exists(), f"Backup archive already exists: {archive}")

    uid, gid = os.getuid(), os.getgid()
    cmd = [
        "sudo", "tar",
        "--acls", "--xattrs", "--numeric-owner",
        "-cpf", str(archive),
        "-C", str(src.parent),
        src.name,
    ]
    subprocess.run(cmd, check=True)

    # Root created the archive; make only the archive container user-owned.
    subprocess.run(["sudo", "chown", f"{uid}:{gid}", "--", str(archive)], check=True)
    os.chmod(archive, 0o600)
    _fsync_file(archive)
    _fsync_dir(archive.parent)

    require(archive.is_file() and archive.stat().st_size > 0, f"Privileged backup failed: {src}")

    # Verify the archive is readable and actually contains the expected top-level tree.
    listing = subprocess.check_output(["tar", "-tf", str(archive)], text=True)
    first = next((line.strip().lstrip("./") for line in listing.splitlines() if line.strip()), "")
    require(first == name or first.startswith(name + "/"), f"Unexpected privileged backup contents: {archive}")

    return {
        "kind": "tar_tree",
        "existed": True,
        "backup": str(archive),
        "bytes": archive.stat().st_size,
        "archive_sha256": sha256_file(archive),
        "preserves_numeric_owner": True,
    }

def backup_tree(src: Path, backup_root: Path, name: str) -> dict:
    """
    Prefer an ordinary copytree. If the current Bazzite user cannot traverse
    the old OptiScaler tree, fall back to a read-only privileged tar backup.

    Crucially, permission/ownership repair of the LIVE game tree happens only
    AFTER this baseline exists.
    """
    dst = _no_follow_child_path(backup_root, f"trees/{name}")
    require(not dst.exists(), f"Backup destination already exists: {dst}")
    _mkdir_durable(dst.parent)
    hazards = _pristine_tree_hazards(src)
    require(
        not hazards,
        f"Existing {name}/ has an unsafe filesystem boundary: {hazards[0] if hazards else 'unknown'}",
    )

    try:
        # Prove the readable source did not change underneath the backup. A
        # copy can otherwise be internally valid while representing a mixture
        # of two source states.
        source_before = _tree_manifest_data(src)
        shutil.copytree(src, dst, symlinks=True)
        for p in dst.rglob("*"):
            require(not p.is_symlink(), f"Symlink inside existing {name}/ refused: {p}")
        source_after = _tree_manifest_data(src)
        backup_snapshot = _tree_manifest_data(dst)
        require(
            source_before["tree_sha256"] == source_after["tree_sha256"],
            f"Existing {name}/ changed while baseline backup was being captured",
        )
        require(
            backup_snapshot["tree_sha256"] == source_after["tree_sha256"],
            f"Baseline tree copy does not match stable source: {name}",
        )
        _fsync_tree(dst)
        meta = _write_tree_manifest(backup_root, name, dst)
        return {
            "kind": "tree",
            "existed": True,
            "backup": str(dst),
            "bytes": directory_size(dst),
            **meta,
        }
    except (PermissionError, shutil.Error) as exc:
        # copytree may aggregate nested EACCES failures into shutil.Error.
        # Preserve the partial destination nowhere; the privileged tar becomes
        # the authoritative read-only baseline.
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        warn(f"Baseline needs privileged read access: {src}")
        return _backup_tree_tar(src, backup_root, name)


def create_baseline(
    game: Game,
    payload_paths: set[str],
    chosen_proxy: str,
    stale_proxies: list[str],
) -> dict:
    target = game.target_dir
    require(target is not None, "Game has no target directory")

    state_dir = _validated_state_dir(target)
    _mkdir_durable(state_dir)

    # v6 self-heals stale v2/v3 baseline-backup directories. Since game mutation
    # only begins AFTER create_baseline returns, a no-baseline orphan cannot be
    # the sole record of a completed mutation.
    quarantine_orphan_baseline_backup(target)

    backup_root = _validated_baseline_backup_root(target, require_exists=False)
    require(not backup_root.exists(), "Active baseline backup already exists unexpectedly")
    _mkdir_durable(backup_root)

    originals = {}

    opti = target / "OptiScaler"
    if opti.exists():
        require(opti.is_dir() and not opti.is_symlink(), "Existing OptiScaler is unsafe")
        originals["OptiScaler/"] = backup_tree(opti, backup_root, "OptiScaler")
    else:
        originals["OptiScaler/"] = {"kind": "tree", "existed": False}

    roots_to_track = {
        p for p in payload_paths
        if not p.casefold().startswith("optiscaler/")
    }
    roots_to_track.add(chosen_proxy)
    roots_to_track.update(stale_proxies)

    for rel in sorted(roots_to_track, key=str.casefold):
        rel = _normalize_state_rel(rel)
        src = _target_member_path(target, rel)
        if src.exists():
            require(src.is_file() and not src.is_symlink(), f"Existing path is unsafe: {src}")
            originals[rel] = backup_file(src, backup_root, rel)
        else:
            originals[rel] = {"kind": "file", "existed": False}

    baseline = {
        "schema": ENGINE_SCHEMA,
        "status": "prepared",
        "created_utc": now_iso(),
        "name": game.name,
        "source": game.source,
        "appid": game.appid,
        "exe": str(game.exe.resolve()) if game.exe else None,
        "target_dir": str(target),
        "originals": originals,
        "managed_paths": [],
        "history": [],
        "current": None,
    }
    save_json_atomic(baseline_path(target), baseline)
    return baseline

def extend_baseline_for_new_paths(
    baseline: dict,
    target: Path,
    paths: set[str],
) -> dict:
    """
    A refresh may change proxy choice (e.g. dxgi -> version after ReShade).
    Before rtxEngine manages any newly encountered root file, capture its
    pre-rtxEngine/current external bytes so uninstall remains reversible.
    """
    backup_root = _validated_baseline_backup_root(target, require_exists=False)
    _mkdir_durable(backup_root)
    originals = baseline.setdefault("originals", {})

    for rel in sorted(paths, key=str.casefold):
        rel = _normalize_state_rel(rel)
        if rel in originals or rel.casefold().startswith("optiscaler/"):
            continue
        src = _target_member_path(target, rel)
        if src.exists():
            require(src.is_file() and not src.is_symlink(), f"New managed path is unsafe: {src}")
            originals[rel] = backup_file(src, backup_root, rel)
        else:
            originals[rel] = {"kind": "file", "existed": False}

    save_json_atomic(baseline_path(target), baseline)
    return baseline

def adopt_external_file_as_original(
    baseline: dict,
    target: Path,
    rel: str,
) -> dict:
    """
    A managed proxy can be replaced by an external mod between rtxEngine
    installs (for example, the user adds ReShade to dxgi.dll). If rtxEngine is
    about to stop owning that filename, preserve the external bytes as the new
    restore baseline instead of later deleting them on uninstall.
    """
    rel = _normalize_state_rel(rel)
    src = _target_member_path(target, rel)
    require(src.is_file() and not src.is_symlink(), f"External replacement is unsafe: {src}")

    backup_root = _validated_baseline_backup_root(target, require_exists=False)
    _mkdir_durable(backup_root)
    originals = baseline.setdefault("originals", {})
    previous = originals.get(rel) if isinstance(originals.get(rel), dict) else None
    dst = _no_follow_child_path(backup_root, f"external-adopted/{now_stamp()}/{rel}")
    # now_stamp() has one-second resolution. A repeated adoption in the same
    # second must still receive a distinct durable path before the old one can
    # be retired.
    if dst.exists():
        dst = dst.with_name(f"{dst.stem}-{time.time_ns()}{dst.suffix}")
    _mkdir_durable(dst.parent)
    copy_verified(src, dst)

    originals[rel] = {
        "kind": "file",
        "existed": True,
        "backup": str(dst),
        "sha256": sha256_file(src),
        "mode": stat.S_IMODE(src.stat().st_mode),
        "adopted_external": True,
        "adopted_utc": now_iso(),
    }
    # Commit the new recovery source first. Cleanup is deliberately after the
    # atomic baseline write so a crash can at worst leave one harmless orphan,
    # never leave the baseline pointing at bytes we already removed.
    save_json_atomic(baseline_path(target), baseline)

    if previous and previous.get("adopted_external") and previous.get("backup"):
        adopted_root = (backup_root / "external-adopted").resolve(strict=False)
        try:
            old = Path(str(previous["backup"])).expanduser().resolve(strict=False)
            old.relative_to(adopted_root)
            if old != dst.resolve(strict=False) and old.is_file() and not old.is_symlink():
                old.unlink()
                parent = old.parent
                while parent != adopted_root:
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
        except (OSError, ValueError):
            # Superseded-copy pruning is retention hygiene, not part of the
            # recovery transaction. Never weaken a successful adoption because
            # stale/malformed historical cleanup could not be completed.
            pass
    return baseline


def _capture_restore_drift_once(recovery: Path, rel: str, src: Path) -> Path:
    """Preserve the first pre-restore drift bytes for a path across retries.

    A later failed restore may already have recreated the original game file.
    Retrying must never overwrite the earlier user/runtime drift copy with those
    engine-produced restore bytes.
    """
    dst = _no_follow_child_path(recovery, _normalize_state_rel(rel))
    if dst.exists() or dst.is_symlink():
        require(
            dst.is_file() and not dst.is_symlink(),
            f"Restore recovery drift path changed filesystem type: {dst}",
        )
        return dst
    _mkdir_durable(dst.parent)
    copy_verified(src, dst)
    return dst

def _mark_restore_pending(target: Path, baseline: dict, *, batch_id: Optional[str] = None) -> dict:
    """Durably transition an install baseline into restore-recovery state."""
    if baseline.get("status") == "restore-pending":
        pending = baseline.get("restore_pending")
        require(isinstance(pending, dict), "Restore-pending state metadata is corrupt")
        if batch_id and not pending.get("batch_id"):
            pending["batch_id"] = batch_id
            save_json_atomic(baseline_path(target), baseline)
        return baseline
    baseline["restore_pending"] = {
        "started_utc": now_iso(),
        "previous_status": baseline.get("status"),
        **({"batch_id": batch_id} if batch_id else {}),
    }
    baseline["status"] = "restore-pending"
    save_json_atomic(baseline_path(target), baseline)
    return baseline

def verify_native_restore(baseline: dict) -> None:
    for rel in baseline.get("managed_paths", []):
        if "/" not in rel and (rel.lower() in {"nvngx_dlssg.dll", "nvngx_dlss.dll", "nvngx_dlssd.dll", "nvapi64.dll"} or rel.lower().startswith("sl.")):
            require(baseline["originals"].get(rel, {}).get("existed") is True,
                    f"Refusing to remove native NVIDIA/Streamline file without its original backup: {rel}")


def restore_target(game: Game) -> dict:
    target = game.target_dir
    require(target is not None, "Game has no target directory")
    running = _running_processes_under_root(game.root.resolve())
    require(not running, f"Game process still using {game.root}: {', '.join(running[:5])}")
    baseline = load_baseline(target)
    require(baseline is not None, f"No rtxEngine install state: {game.name}")

    # Hard boundary: prove the entire persisted recovery plan before touching
    # a single live game file. Legacy baselines receive integrity metadata now.
    verify_baseline_integrity(target, baseline, adopt_legacy=True)

    # Managed root/package entries are file ownership claims. If one has become
    # a directory or special node, that is external structural drift—not a
    # successful uninstall condition. Refuse before creating recovery state or
    # deleting any other managed file. Symlink traversal is rejected by
    # _target_member_path itself.
    for rel in baseline.get("managed_paths", []):
        if rel == "OptiScaler/" or rel.startswith("OptiScaler/"):
            continue
        current_path = _target_member_path(target, rel)
        if current_path.exists():
            require(
                current_path.is_file() and not current_path.is_symlink(),
                f"Managed path changed filesystem type externally: {current_path}",
            )

    verify_native_restore(baseline)

    raw_recovery = baseline.get("restore_recovery_dir")
    if raw_recovery is not None:
        recovery = _validate_restore_recovery_dir(target, raw_recovery, require_exists=True)
    else:
        recovery_root = _validated_state_dir(target, require_exists=True) / "recovery-before-restore"
        _mkdir_durable(recovery_root)
        recovery = recovery_root / f"{now_stamp()}-{time.time_ns()}"
        _mkdir_durable(recovery, mode=0o700)
        baseline["restore_recovery_dir"] = str(recovery.resolve(strict=False))
        # The slot identity must survive any later restore failure so a retry
        # never abandons user/runtime drift preserved by an earlier attempt.
        save_json_atomic(baseline_path(target), baseline)

    current = baseline.get("current") or {}
    installed_hashes = dict(current.get("installed_hashes", {}) or {})
    pending = baseline.get("pending_install") or {}
    if isinstance(pending, dict) and pending:
        pending_hashes = pending.get("installed_hashes") or {}
        require(isinstance(pending_hashes, dict), "Pending install hash state is corrupt")
        installed_hashes.update(pending_hashes)

    # Persist recovery-only state BEFORE any live permission repair/removal or
    # original-file restore. A hard crash during ordinary uninstall must never
    # leave a partially restored game advertising itself as an active install.
    baseline = _mark_restore_pending(target, baseline)

    # Preserve user/runtime drift before deleting the managed stack. This also
    # covers runtime-created or user-edited files *inside* OptiScaler/, which
    # older v13 restore code skipped wholesale before removing the tree.
    for rel in baseline.get("managed_paths", []):
        if rel == "OptiScaler/" or rel.startswith("OptiScaler/"):
            continue
        p = _target_member_path(target, rel)
        if p.is_file():
            expected = installed_hashes.get(rel)
            if expected is None or sha256_file(p) != expected:
                _capture_restore_drift_once(recovery, rel, p)

    opti = target / "OptiScaler"
    if opti.exists():
        require(opti.is_dir() and not opti.is_symlink(), "Current OptiScaler is unsafe")
        hazards = _pristine_tree_hazards(opti)
        require(
            not hazards,
            f"Current OptiScaler has an unsafe filesystem boundary: {hazards[0] if hazards else 'unknown'}",
        )
        for p in sorted(opti.rglob("*"), key=lambda x: x.as_posix().casefold()):
            require(not p.is_symlink(), f"Live OptiScaler symlink refused before restore: {p}")
            if not p.is_file():
                continue
            rel = p.relative_to(target).as_posix()
            expected = installed_hashes.get(rel)
            if expected is None or sha256_file(p) != expected:
                _capture_restore_drift_once(recovery, rel, p)

    if opti.exists():
        ensure_tree_replaceable(opti, f"{game.name} OptiScaler")
        shutil.rmtree(opti)
        _sync_filesystem(target)

    for rel in sorted(baseline.get("managed_paths", []), reverse=True):
        if rel == "OptiScaler/" or rel.startswith("OptiScaler/"):
            continue
        p = _target_member_path(target, rel)
        if p.is_file() and not p.is_symlink():
            ensure_file_replaceable(p, f"{game.name} managed file")
            durable_unlink(p)

    for rel, info in baseline["originals"].items():
        if rel == "OptiScaler/":
            if info["existed"]:
                src = _baseline_backup_member(target, info["backup"])
                if info.get("kind") == "tar_tree":
                    require(src.is_file(), "Baseline OptiScaler tar backup missing")
                    # Restore the exact archived ownership/modes/xattrs/ACLs.
                    require(shutil.which("sudo") is not None and shutil.which("tar") is not None,
                            "sudo + tar are required to restore this privileged baseline")
                    with _validated_tar_snapshot(
                        src, info["archive_sha256"], expected_top="OptiScaler", exact_file=False
                    ) as tar_snapshot:
                        subprocess.run([
                            "sudo", "tar",
                            "--acls", "--xattrs", "--numeric-owner",
                            "-xpf", "-",
                            "-C", str(target),
                        ], stdin=tar_snapshot, check=True)
                    require(opti.is_dir(), "Privileged OptiScaler restore did not recreate the tree")
                    _sync_filesystem(target)
                else:
                    require(src.is_dir(), "Baseline OptiScaler backup missing")
                    shutil.copytree(src, opti)
                    _verify_tree_manifest(target, info, opti)
                    _fsync_tree(opti)
            continue

        dst = _target_member_path(target, rel)
        if info["existed"]:
            src = _baseline_backup_member(target, info["backup"])
            require(src.is_file(), f"Baseline backup missing: {rel}")
            _mkdir_durable(dst.parent)

            if info.get("kind") == "tar_file":
                require(shutil.which("sudo") is not None and shutil.which("tar") is not None,
                        "sudo + tar are required to restore this privileged file baseline")
                restore_parent = info.get("restore_parent", ".")
                restore_dir = target if restore_parent == "." else _target_member_path(target, restore_parent)
                _mkdir_durable(restore_dir)
                with _validated_tar_snapshot(
                    src, info["archive_sha256"], expected_top=info["member"], exact_file=True
                ) as tar_snapshot:
                    subprocess.run([
                        "sudo", "tar",
                        "--acls", "--xattrs", "--numeric-owner",
                        "-xpf", "-",
                        "-C", str(restore_dir),
                    ], stdin=tar_snapshot, check=True)
                require(dst.is_file(), f"Privileged restore failed: {rel}")
                _sync_filesystem(restore_dir)
            else:
                copy_verified(src, dst)
                os.chmod(dst, info.get("mode", 0o644))
                _fsync_file(dst)
                _fsync_dir(dst.parent)
                require(sha256_file(dst) == info["sha256"], f"Restore failed: {rel}")

    stamp = now_stamp()
    archived = _validated_state_dir(target, require_exists=True) / f"baseline-restored-{stamp}.json"
    # Move active state out of the active slot first, then compact it to a
    # provenance/restore receipt. Backup payload paths are intentionally not
    # retained after successful restore because those bytes are now live again.
    durable_replace(baseline_path(target), archived)
    receipt = json.loads(json.dumps(baseline))
    receipt["status"] = "restored"
    receipt["restored_utc"] = now_iso()
    receipt["baseline_payload_retained"] = False
    for info in (receipt.get("originals") or {}).values():
        if isinstance(info, dict):
            info.pop("backup", None)
            info.pop("manifest", None)
    save_json_atomic(archived, receipt)

    discarded_backup_bytes = discard_consumed_baseline_backup(target)
    prune_target_history(target, protected_recovery=recovery)

    return {
        "game": game.name,
        "target": str(target),
        "recovery": str(recovery),
        "archived_state": str(archived),
        "archived_backup": None,
        "discarded_backup_bytes": discarded_backup_bytes,
    }

# Install / audit ------------------------------------------------------------

def stale_owned_proxies(target: Path, chosen_proxy: str, reshade: dict) -> list[str]:
    stale = []
    for name in PROXY_NAMES:
        if name == chosen_proxy:
            continue
        p = target / name
        if not p.is_file():
            continue
        if name == "dxgi.dll" and reshade["detected"]:
            continue
        if looks_like_old_graphics_proxy(p):
            stale.append(name)
    return stale

def _refresh_expected_file_hashes(baseline: dict) -> dict[str, set[str]]:
    """Hashes rtxEngine may have written during the current/prior install attempt."""
    out: dict[str, set[str]] = {}
    for record in (baseline.get("current") or {}, baseline.get("pending_install") or {}):
        hashes = record.get("installed_hashes") or {}
        if not isinstance(hashes, dict):
            continue
        for rel, digest in hashes.items():
            if isinstance(rel, str) and isinstance(digest, str) and len(digest) == 64:
                out.setdefault(rel.casefold(), set()).add(digest)
    return out

def _verify_optiscaler_tree_refresh_safe(target: Path, baseline: dict) -> None:
    """Refuse refresh if the managed OptiScaler binary tree acquired drift.

    Refresh intentionally replaces this whole provider-owned subtree. Anything
    not provably written by the current/prior rtxEngine install is therefore an
    ownership conflict, not something an ordinary refresh may erase.
    """
    tree = target / "OptiScaler"
    if not tree.exists() and not tree.is_symlink():
        return
    require(tree.is_dir() and not tree.is_symlink(), f"Managed OptiScaler tree changed filesystem type externally: {tree}")
    hazards = _pristine_tree_hazards(tree)
    require(
        not hazards,
        f"Managed OptiScaler tree has an unsafe filesystem boundary: {hazards[0] if hazards else 'unknown'}",
    )

    # Interrupted first install before tree replacement: if the original tree
    # is still byte-for-byte the baseline source we already backed up, deleting
    # it remains recoverable and is safe to resume.
    if not baseline.get("current"):
        original = (baseline.get("originals") or {}).get("OptiScaler/")
        if isinstance(original, dict) and original.get("existed") and original.get("kind") == "tree":
            expected_tree = original.get("tree_sha256")
            if isinstance(expected_tree, str) and _tree_manifest_data(tree).get("tree_sha256") == expected_tree:
                return

    expected = _refresh_expected_file_hashes(baseline)
    for path in sorted(tree.rglob("*"), key=lambda p: p.as_posix().casefold()):
        if path.is_dir():
            continue
        require(path.is_file() and not path.is_symlink(), f"Unsafe entry inside managed OptiScaler tree: {path}")
        rel = path.relative_to(target).as_posix()
        allowed = expected.get(rel.casefold())
        require(allowed, f"Unexpected file inside managed OptiScaler tree; refusing refresh: {rel}")
        require(sha256_file(path) in allowed, f"Managed OptiScaler tree file changed externally; refusing refresh: {rel}")

def _verify_root_payload_refresh_safe(target: Path, baseline: dict, payload: dict[str, bytes], ini_key: str) -> None:
    """Refuse to overwrite externally changed files rtxEngine already owns.

    OptiScaler.ini is intentionally excluded because it is a user-editable
    config and is merged separately. New payload paths are also excluded here:
    baseline extension captures any pre-existing bytes before first ownership.
    """
    expected = _refresh_expected_file_hashes(baseline)
    for rel in sorted(payload, key=str.casefold):
        if rel.casefold().startswith("optiscaler/") or rel.casefold() == ini_key.casefold():
            continue
        allowed = expected.get(rel.casefold())
        if not allowed:
            continue
        path = target / rel
        if not path.exists() and not path.is_symlink():
            continue
        require(path.is_file() and not path.is_symlink(), f"Managed payload path changed filesystem type externally: {path}")
        require(
            sha256_file(path) in allowed,
            f"Managed payload file changed externally; refusing refresh: {rel}",
        )


def _managed_file_hash(path: Path) -> str:
    """Hash a managed file, falling back to sudo after privileged restore."""
    try:
        return sha256_file(path)
    except PermissionError:
        require(shutil.which("sudo") is not None, f"Need elevated read access to verify managed file: {path}")
        out = subprocess.check_output(
            ["sudo", "sha256sum", "--", str(path)],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
        digest = out.split(None, 1)[0] if out else ""
        require(re.fullmatch(r"[0-9a-fA-F]{64}", digest) is not None, f"Could not hash managed file: {path}")
        return digest.lower()


def _baseline_original_file_hash(target: Path, rel: str, info: dict) -> str:
    """Return the exact original file hash for normal or privileged baselines.

    Privileged tar-backed baselines are hashed from the same integrity-bound
    snapshot primitive used for extraction, so provider-relinquishment checks
    never trust a pathname reopened after an earlier validation pass.
    """
    kind = info.get("kind")
    if kind == "file":
        digest = info.get("sha256")
        require(isinstance(digest, str) and len(digest) == 64, f"Baseline file hash missing: {rel}")
        return digest
    require(kind == "tar_file", f"Provider ownership transfer supports file baselines only: {rel}")
    archive = _baseline_backup_member(target, info.get("backup", ""))
    member_name = _normalize_state_rel(info.get("member", ""), allow_dir_marker=False)
    try:
        with _validated_tar_snapshot(
            archive, info.get("archive_sha256", ""), expected_top=member_name, exact_file=True
        ) as snap:
            with tarfile.open(fileobj=snap, mode="r:*") as tf:
                matches = []
                for member in tf.getmembers():
                    raw = member.name
                    while raw.startswith("./"):
                        raw = raw[2:]
                    if raw == member_name and member.isfile():
                        matches.append(member)
                require(len(matches) == 1, f"Baseline tar member missing/ambiguous: {rel}")
                src = tf.extractfile(matches[0])
                require(src is not None, f"Baseline tar member unreadable: {rel}")
                h = hashlib.sha256()
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
                return h.hexdigest()
    except (tarfile.TarError, OSError) as exc:
        raise Stop(f"Could not verify privileged baseline payload for {rel}: {exc}") from exc


def _restore_baseline_file(target: Path, rel: str, info: dict) -> None:
    """Restore one original baseline file without consuming the baseline payload."""
    dst = _target_member_path(target, rel)
    require(info.get("existed") is True, f"No original file exists to restore: {rel}")
    src = _baseline_backup_member(target, info.get("backup", ""))
    require(src.is_file() and not src.is_symlink(), f"Baseline backup missing: {rel}")
    _mkdir_durable(dst.parent)

    if info.get("kind") == "tar_file":
        require(
            shutil.which("sudo") is not None and shutil.which("tar") is not None,
            "sudo + tar are required to restore this privileged file baseline",
        )
        restore_parent = info.get("restore_parent", ".")
        restore_dir = target if restore_parent == "." else _target_member_path(target, restore_parent)
        _mkdir_durable(restore_dir)
        member_name = _normalize_state_rel(info.get("member", ""), allow_dir_marker=False)
        with _validated_tar_snapshot(
            src, info.get("archive_sha256", ""), expected_top=member_name, exact_file=True
        ) as tar_snapshot:
            # Derive the post-restore verification hash from these exact staged
            # bytes before rewinding the same snapshot into privileged tar.
            with tarfile.open(fileobj=tar_snapshot, mode="r:*") as tf:
                member = tf.getmember(member_name)
                member_src = tf.extractfile(member)
                require(member_src is not None, f"Baseline tar member unreadable: {rel}")
                h = hashlib.sha256()
                while True:
                    chunk = member_src.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
                expected_restored_hash = h.hexdigest()
            tar_snapshot.seek(0)
            subprocess.run([
                "sudo", "tar",
                "--acls", "--xattrs", "--numeric-owner",
                "-xpf", "-",
                "-C", str(restore_dir),
            ], stdin=tar_snapshot, check=True)
        require(dst.is_file() and not dst.is_symlink(), f"Privileged restore failed: {rel}")
        _sync_filesystem(restore_dir)
    else:
        require(info.get("kind") == "file", f"Unsupported baseline file kind for {rel}: {info.get('kind')!r}")
        copy_verified(src, dst)
        os.chmod(dst, info.get("mode", 0o644))
        _fsync_file(dst)
        _fsync_dir(dst.parent)
        expected_restored_hash = _baseline_original_file_hash(target, rel, info)

    require(
        _managed_file_hash(dst) == expected_restored_hash,
        f"Provider ownership transfer restore verification failed: {rel}",
    )


def _validate_provider_relinquish_state(target: Path, baseline: dict) -> None:
    plan = baseline.get("provider_relinquish")
    if plan is None:
        return
    require(isinstance(plan, dict), "Provider relinquishment state is corrupt")
    require(
        baseline.get("status") in {"applying", "interrupted", "restore-pending"},
        "Provider relinquishment state cannot be advertised as an active install",
    )
    digest = plan.get("archive_sha256")
    require(
        isinstance(digest, str) and re.fullmatch(r"[0-9a-fA-F]{64}", digest) is not None,
        "Provider relinquishment archive hash is corrupt",
    )
    paths = plan.get("paths")
    require(isinstance(paths, dict) and paths, "Provider relinquishment path plan is corrupt")
    originals = baseline.get("originals") or {}
    managed = baseline.get("managed_paths") or []
    require(isinstance(originals, dict), "Provider relinquishment originals state is corrupt")
    require(isinstance(managed, list), "Provider relinquishment managed state is corrupt")
    managed_keys = {rel.casefold() for rel in managed if isinstance(rel, str)}
    original_by_key = {rel.casefold(): rel for rel in originals if isinstance(rel, str)}

    for rel, entry in paths.items():
        normalized = _normalize_state_rel(rel, allow_dir_marker=False)
        _target_member_path(target, rel)
        require(normalized.casefold() in managed_keys, f"Provider relinquishment path is no longer managed: {rel}")
        require(isinstance(entry, dict), f"Provider relinquishment entry is corrupt: {rel}")
        action = entry.get("action")
        require(action in {"restore-original", "remove-engine-file"}, f"Unknown provider relinquishment action: {rel}")
        require(entry.get("phase") in {"pending", "applied"}, f"Unknown provider relinquishment phase: {rel}")
        hashes = entry.get("engine_hashes")
        require(isinstance(hashes, list) and hashes, f"Provider relinquishment hashes are corrupt: {rel}")
        for value in hashes:
            require(
                isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None,
                f"Provider relinquishment hash is corrupt: {rel}",
            )

        original_key = entry.get("original_key")
        require(isinstance(original_key, str), f"Provider relinquishment original key is corrupt: {rel}")
        normalized_original = _normalize_state_rel(original_key, allow_dir_marker=False)
        require(
            normalized_original.casefold() == normalized.casefold(),
            f"Provider relinquishment original key mismatch: {rel}",
        )
        canonical_original = original_by_key.get(normalized.casefold())
        require(canonical_original is not None, f"Provider relinquishment recovery baseline is missing: {rel}")
        info = originals.get(canonical_original)
        require(isinstance(info, dict), f"Provider relinquishment recovery baseline is corrupt: {rel}")
        require(info.get("kind") in {"file", "tar_file"}, f"Provider relinquishment recovery kind is invalid: {rel}")

        if action == "restore-original":
            require(info.get("existed") is True, f"Provider relinquishment restore source is missing: {rel}")
            original_hash = entry.get("original_sha256")
            require(
                isinstance(original_hash, str) and re.fullmatch(r"[0-9a-fA-F]{64}", original_hash) is not None,
                f"Provider relinquishment original hash is corrupt: {rel}",
            )
            require(
                original_hash.casefold() == _baseline_original_file_hash(target, canonical_original, info).casefold(),
                f"Provider relinquishment original hash does not match baseline recovery payload: {rel}",
            )
        else:
            require(info.get("existed") is False, f"Provider relinquishment remove action conflicts with original state: {rel}")


def _provider_relinquish_live_state(target: Path, rel: str, entry: dict) -> str:
    """Return 'engine' or 'final'; any third-party drift is refused."""
    path = _target_member_path(target, rel)
    action = entry["action"]
    engine_hashes = set(entry["engine_hashes"])

    if not path.exists() and not path.is_symlink():
        if action == "remove-engine-file":
            return "final"
        raise Stop(f"Managed provider payload disappeared externally; refusing ownership transfer: {rel}")

    require(
        path.is_file() and not path.is_symlink(),
        f"Managed provider payload changed filesystem type externally: {path}",
    )
    digest = _managed_file_hash(path)
    if action == "restore-original" and digest == entry.get("original_sha256"):
        return "final"
    if digest in engine_hashes:
        return "engine"
    raise Stop(f"Managed provider payload changed externally; refusing ownership transfer: {rel}")


def _cleanup_relinquished_backup_payloads(target: Path, infos: list[dict]) -> None:
    """Best-effort retention cleanup after ownership state is already committed."""
    try:
        backup_root = _validated_baseline_backup_root(target, require_exists=False)
    except Stop:
        return
    for info in infos:
        if not isinstance(info, dict) or not info.get("existed") or not info.get("backup"):
            continue
        try:
            old = _baseline_backup_member(target, info["backup"])
            if old.is_file() and not old.is_symlink():
                durable_unlink(old)
            parent = old.parent
            while parent != backup_root:
                try:
                    parent.rmdir()
                    _fsync_dir(parent.parent)
                except OSError:
                    break
                parent = parent.parent
        except (OSError, Stop):
            # Ownership transfer is already committed. Orphaned recovery bytes
            # are retention hygiene, never a reason to roll ownership backward.
            pass


def _relinquish_removed_provider_paths(
    target: Path,
    baseline: dict,
    payload: dict[str, bytes],
    archive_meta: dict,
    protected_paths: set[str],
) -> tuple[dict, list[str]]:
    """Relinquish files a newer provider no longer ships, crash-safely.

    The plan is persisted before the first live mutation. A retry accepts only
    either the prior rtxEngine-written bytes or the exact already-applied final
    state, so a crash cannot turn later third-party drift into something we
    silently delete or overwrite.
    """
    archive_sha = archive_meta.get("sha256")
    require(isinstance(archive_sha, str) and len(archive_sha) == 64, "Provider archive hash missing")
    _validate_provider_relinquish_state(target, baseline)

    plan = baseline.get("provider_relinquish")
    if plan is not None:
        require(
            plan.get("archive_sha256") == archive_sha,
            "A provider ownership transfer is pending for different provider bytes. Retry the same pinned provider first.",
        )
    else:
        current = baseline.get("current") or {}
        prior_hashes = current.get("installed_hashes") or {}
        require(isinstance(prior_hashes, dict), "Baseline installed_hashes is corrupt")
        next_paths = {rel.casefold() for rel in payload}
        protected = {rel.casefold() for rel in protected_paths if isinstance(rel, str) and rel}
        expected = _refresh_expected_file_hashes(baseline)
        managed = baseline.get("managed_paths") or []
        originals = baseline.get("originals") or {}
        managed_by_key = {rel.casefold(): rel for rel in managed if isinstance(rel, str)}
        original_by_key = {rel.casefold(): rel for rel in originals if isinstance(rel, str)}
        paths: dict[str, dict] = {}

        for prior_rel, prior_digest in sorted(prior_hashes.items(), key=lambda item: str(item[0]).casefold()):
            if not isinstance(prior_rel, str) or not isinstance(prior_digest, str):
                continue
            key = prior_rel.casefold()
            if key.startswith("optiscaler/") or key in next_paths or key in protected:
                continue
            require(key in managed_by_key, f"Provider-owned path is missing from managed state: {prior_rel}")
            require(key in original_by_key, f"Provider-owned path is missing its recovery baseline: {prior_rel}")
            rel = managed_by_key[key]
            original_key = original_by_key[key]
            info = originals[original_key]
            require(isinstance(info, dict), f"Corrupt recovery baseline for provider path: {rel}")
            require(info.get("kind") in {"file", "tar_file"}, f"Provider ownership transfer supports files only: {rel}")
            hashes = sorted(expected.get(key) or {prior_digest})
            entry = {
                "action": "restore-original" if info.get("existed") else "remove-engine-file",
                "phase": "pending",
                "engine_hashes": hashes,
                "original_key": original_key,
            }
            if info.get("existed"):
                entry["original_sha256"] = _baseline_original_file_hash(target, original_key, info)
            paths[rel] = entry

        if not paths:
            return baseline, []

        # Preflight every candidate before persisting recovery state or touching
        # the first file. External drift leaves a healthy active baseline alone.
        for rel, entry in paths.items():
            _provider_relinquish_live_state(target, rel, entry)

        plan = {
            "started_utc": now_iso(),
            "archive_sha256": archive_sha,
            "paths": paths,
        }
        baseline["provider_relinquish"] = plan
        baseline["status"] = "applying"
        baseline["last_attempt_utc"] = now_iso()
        save_json_atomic(baseline_path(target), baseline)

    originals = baseline.get("originals") or {}
    for rel in sorted(plan["paths"], key=str.casefold):
        entry = plan["paths"][rel]
        state = _provider_relinquish_live_state(target, rel, entry)
        if state == "engine":
            path = _target_member_path(target, rel)
            if ensure_file_replaceable(path, f"provider ownership transfer {rel}"):
                pass
            if entry["action"] == "remove-engine-file":
                durable_unlink(path)
            else:
                info = originals.get(entry.get("original_key"))
                require(isinstance(info, dict) and info.get("existed"), f"Original recovery source missing: {rel}")
                _restore_baseline_file(target, rel, info)
            require(_provider_relinquish_live_state(target, rel, entry) == "final", f"Provider ownership transfer did not reach final state: {rel}")

        if entry.get("phase") != "applied":
            entry["phase"] = "applied"
            save_json_atomic(baseline_path(target), baseline)

    relinquished = sorted(plan["paths"], key=str.casefold)
    relinquished_keys = {rel.casefold() for rel in relinquished}
    removed_infos: list[dict] = []

    baseline["managed_paths"] = [
        rel for rel in baseline.get("managed_paths", [])
        if not (isinstance(rel, str) and rel.casefold() in relinquished_keys)
    ]
    originals = baseline.get("originals") or {}
    for key in list(originals):
        if isinstance(key, str) and key.casefold() in relinquished_keys:
            info = originals.pop(key)
            if isinstance(info, dict):
                removed_infos.append(info)

    for record_name in ("current", "pending_install"):
        record = baseline.get(record_name)
        if not isinstance(record, dict):
            continue
        hashes = record.get("installed_hashes")
        if isinstance(hashes, dict):
            for key in list(hashes):
                if isinstance(key, str) and key.casefold() in relinquished_keys:
                    hashes.pop(key, None)

    baseline.pop("provider_relinquish", None)
    baseline["status"] = "applying"
    baseline["last_attempt_utc"] = now_iso()
    save_json_atomic(baseline_path(target), baseline)
    _cleanup_relinquished_backup_payloads(target, removed_infos)
    return baseline, relinquished


def build_launch_options(chosen_proxy: str, reshade: dict, mfg_proxy: Optional[str] = None) -> str:
    overrides = [chosen_proxy]
    if reshade["detected"] and chosen_proxy.casefold() != "dxgi.dll":
        # ReShade owns dxgi while OptiScaler uses a distinct proxy. Proton must
        # native-override both loader names.
        overrides.insert(0, "dxgi.dll")
    if mfg_proxy and mfg_proxy.casefold() not in {x.casefold() for x in overrides}:
        overrides.append(mfg_proxy)
    override_value = ";".join(f"{name[:-4]}=n,b" for name in overrides)
    # Keep the launch contract minimal. PROTON_NVIDIA_NVCUDA is an optional
    # alternate CUDA-library path in some Proton forks and is unrelated to
    # DLSS-G injection; RC1/RC2 incorrectly forced it globally.
    # Match y4my/upstream Linux guidance: the renamed OptiScaler proxy is the
    # only launch override rtxEngine owns. Do not force CUDA/NVAPI environment
    # variables globally; modern Proton/dxvk-nvapi handles the native NVIDIA
    # path and extra flags changed compatibility in the RC2 library matrix.
    return f'WINEDLLOVERRIDES="{override_value}" %command%'

def install_target(
    game: Game,
    base_payload: dict[str, bytes],
    archive_meta: dict,
    family: str,
    rtxmfg_payload: Optional[bytes] = None,
    rtxmfg_meta: Optional[dict] = None,
    *,
    ada_mfg_mode: str = "integrated",
    ada_runtime_payload: Optional[bytes] = None,  # legacy API, ignored
    ada_runtime_meta: Optional[dict] = None,      # legacy API, ignored
    nr_runtime_payload: Optional[bytes] = None,
    nr_runtime_meta: Optional[dict] = None,
    feature_mode: str = "nr-mfg",
    enable_effects: bool = True,
    native_mfg_fallback: bool = False,
    native_mfg_multiplier: str = "auto",
    dry_run: bool = False,
) -> dict:
    require(game.eligible, f"Game is not eligible: {game.name} ({game.reason})")
    require(game.target_dir is not None and game.exe is not None, "Missing game target")
    running = _running_processes_under_root(game.root.resolve())
    require(not running, f"Game process still using {game.root}: {', '.join(running[:5])}")
    if family == "ada":
        require(ada_mfg_mode == "integrated", "Handoff 188 uses only the integrated y4my v4 Ada MFG route")

    target = game.target_dir
    existing_baseline = load_baseline(target)
    if existing_baseline:
        status = existing_baseline.get("status")
        require(
            status != "destructive-pending",
            f"Previous destructive cleanup is still pending for {game.name}. "
            "Finish/retry Deep Clean or Pristine Reset, or restore/uninstall the recovery state before installing again.",
        )
        require(
            status != "restore-pending",
            f"Previous restore/uninstall is still pending for {game.name}. "
            "Retry restore/uninstall before installing again.",
        )
        verify_baseline_integrity(target, existing_baseline, adopt_legacy=not dry_run)
        _verify_optiscaler_tree_refresh_safe(target, existing_baseline)
    if existing_baseline and Y4MY_PROVIDER.get("id") == "dlss-unlocked":
        prior_mode = (existing_baseline.get("current") or {}).get("feature_mode")
        require(prior_mode in (None, feature_mode), "Uninstall before changing DLSS-Unlocked pipelines")
    reshade = detect_reshade(target)
    # Keep y4my's overlay behavior unchanged by default. Its global overlay
    # blocker also disables Steam Input, so RC1 does not infer a per-game route.
    eos_overlay = False

    # Preserve the same-name external-drift invariant before considering any
    # fallback proxy. If another mod/user replaced the currently managed proxy,
    # an ordinary refresh must not silently route around that conflict.
    if existing_baseline:
        prior = existing_baseline.get("current") or {}
        prior_proxy = prior.get("proxy")
        prior_hash = (prior.get("installed_hashes") or {}).get(prior_proxy) if prior_proxy else None
        if prior_proxy and prior_hash:
            prior_path = target / prior_proxy
            if prior_path.exists() or prior_path.is_symlink():
                require(
                    prior_path.is_file() and not prior_path.is_symlink(),
                    f"Managed OptiScaler proxy changed filesystem type externally: {prior_path}",
                )
            if (
                prior_path.is_file()
                and sha256_file(prior_path) != prior_hash
                and not reshade.get("detected")
            ):
                raise Stop(
                    f"Managed OptiScaler proxy changed externally: {prior_path}. "
                    "rtxEngine refuses to overwrite or route around it; uninstall/restore or resolve that proxy first."
                )

    prior_runtime_evidence = (
        inspect_optiscaler_runtime_log(target)
        if existing_baseline and family == "ada" and ada_mfg_mode == "integrated"
        else {"mfg_applied": False}
    )
    chosen_proxy = choose_optiscaler_proxy(
        target, reshade, existing_baseline, game.exe,
        prefer_imported=(family == "ada" and ada_mfg_mode == "integrated"),
        preserve_prior=bool(prior_runtime_evidence.get("mfg_applied")),
    )
    require(
        chosen_proxy is not None,
        f"No safe OptiScaler proxy is available for {game.name}. "
        "rtxEngine refuses to overwrite an existing game/mod DLL.",
    )

    # ReShade may legitimately replace the old dxgi proxy while ownership moves
    # to version.dll. If ownership would stay on the externally changed proxy,
    # still refuse rather than overwrite it.
    if existing_baseline:
        prior = existing_baseline.get("current") or {}
        prior_proxy = prior.get("proxy")
        prior_hash = (prior.get("installed_hashes") or {}).get(prior_proxy) if prior_proxy else None
        if prior_proxy == chosen_proxy and prior_hash:
            prior_path = target / prior_proxy
            if prior_path.is_file() and sha256_file(prior_path) != prior_hash:
                raise Stop(
                    f"Managed OptiScaler proxy changed externally: {prior_path}. "
                    "rtxEngine refuses to overwrite it; uninstall/restore or resolve that proxy first."
                )

    mfg_proxy: Optional[str] = None
    previous_mfg_proxy: Optional[str] = None
    managed_existing_mfg: set[str] = set()
    if existing_baseline:
        previous_mfg_proxy = (
            ((existing_baseline.get("current") or {}).get("mfg_provider") or {}).get("proxy")
        )
        # A 186 -> 187 refresh may retire a separate RTXMFG proxy. Validate its
        # filesystem type before any unrelated payload mutation. File-content
        # drift is handled later by the existing external-adoption path.
        if previous_mfg_proxy:
            prior = existing_baseline.get("current") or {}
            prior_hash = (prior.get("installed_hashes") or {}).get(previous_mfg_proxy)
            prior_path = target / previous_mfg_proxy
            if prior_path.exists() or prior_path.is_symlink():
                require(
                    prior_path.is_file() and not prior_path.is_symlink(),
                    f"Managed RTXMFG proxy changed filesystem type externally: {prior_path}",
                )
            if prior_hash and prior_path.is_file() and sha256_file(prior_path) == prior_hash:
                managed_existing_mfg.add(previous_mfg_proxy)

    if family == "ada":
        # No second MFG DLL/provider in Handoff 188. y4my v4 owns both the
        # native Ada unlock and the Streamline/DLSS-G companion stack.
        mfg_proxy = None

    payload = dict(base_payload)
    dxgi_key = next(k for k in payload if k.casefold() == "dxgi.dll")
    proxy_bytes = payload.pop(dxgi_key)
    # base_payload's normalized dxgi.dll is the exact y4my OptiScaler.dll.
    payload[chosen_proxy] = proxy_bytes

    # Neural Rendering's NVIDIA model DLL is intentionally not redistributed
    # by the pinned y4my archive. A caller may still inject one into a prepared
    # payload (used by deterministic tests/offline packaging), while normal live
    # installs use --nr-runtime, Downloads discovery, the family-pinned DLSSNR
    # bootstrap, or an existing game-local copy. Existing game-local bytes win
    # so refresh never replaces them merely
    # because a global runtime was supplied for other games in the batch.
    # Frozen DLSS-Unlocked MFG recipe: update only existing native runtime files.
    # create_baseline below backs up every replacement before the first write.
    require(feature_mode != "nr-only" or Y4MY_PROVIDER.get("id") == "dlss-unlocked",
            "NR Only is currently available with DLSS-Unlocked")
    if Y4MY_PROVIDER.get("id") == "dlss-unlocked" and feature_mode == "mfg-only" and native_mfg_fallback:
        # Explicit, opt-in fallback only (never the default mfg-only route): the
        # game-owned native Streamline path is preferred. This promotes
        # DLSS-Unlocked's private OptiScaler/streamline/ runtime into the game
        # root and must be requested and recorded, never silent.
        require((target / "nvngx_dlssg.dll").is_file(), "MFG runtime deployment requires game-native nvngx_dlssg.dll")
        for rel, content in list(payload.items()):
            name = PurePosixPath(rel).name
            if rel.startswith("OptiScaler/streamline/") and (name.startswith("sl.") or name in {"nvngx_dlss.dll", "nvngx_dlssd.dll", "nvngx_dlssg.dll", "nvngx_deepdvc.dll"}):
                dest = target / name
                if dest.exists():
                    require(dest.is_file() and not dest.is_symlink(), f"Linked/non-file native runtime refused: {name}")
                    payload[name] = content
    selected_nr_meta = None
    require(feature_mode in {"nr-mfg", "nr-only", "mfg-only"}, "Unknown feature mode")
    if feature_mode in {"nr-mfg", "nr-only"}:
        embedded_nr_key = next((k for k in payload if k.casefold() == NR_RUNTIME_NAME.casefold()), None)
        embedded_nr_payload = payload.pop(embedded_nr_key) if embedded_nr_key else None
        selected_nr_payload = nr_runtime_payload
        selected_nr_meta = nr_runtime_meta
        if selected_nr_payload is None and embedded_nr_payload is not None:
            selected_nr_payload = embedded_nr_payload
            selected_nr_meta = {
                "name": NR_RUNTIME_NAME,
                "path": "prepared-payload",
                "sha256": sha256_bytes(embedded_nr_payload),
                "ownership": "caller-supplied NVIDIA runtime",
            }
        live_nr = target / NR_RUNTIME_NAME
        if live_nr.is_file() and not live_nr.is_symlink() and Y4MY_PROVIDER.get("id") != "dlss-unlocked":
            live_bytes = live_nr.read_bytes()
            require(len(live_bytes) > NR_RUNTIME_MIN_BYTES and live_bytes[:2] == b"MZ", f"Existing {NR_RUNTIME_NAME} is invalid")
            selected_nr_payload = live_bytes
            selected_nr_meta = {
                "name": NR_RUNTIME_NAME,
                "path": str(live_nr),
                "sha256": sha256_bytes(live_bytes),
                "ownership": "existing game-local NVIDIA runtime",
            }
        require(
            selected_nr_payload is not None and selected_nr_meta is not None,
            f"{NR_RUNTIME_NAME} is required for Neural Rendering. Select a suitable local model in Settings, "
            "put a trusted copy beside the game executable, or pass --nr-runtime.",
        )
        require(len(selected_nr_payload) > NR_RUNTIME_MIN_BYTES and selected_nr_payload[:2] == b"MZ", f"Invalid {NR_RUNTIME_NAME}")
        payload[NR_RUNTIME_NAME] = selected_nr_payload

    else:
        payload = {k:v for k,v in payload.items() if PurePosixPath(k).name.casefold() not in {"nvngx_dlssnr.dll", "nvngx.dll_dlssnr.dll", "sl.dlss_nr.dll"}}

    ini_key = next(k for k in payload if k.casefold() == "optiscaler.ini")
    ini_source = payload[ini_key]
    if existing_baseline:
        live_ini = target / ini_key
        current_hash = ((existing_baseline.get("current") or {}).get("installed_hashes") or {}).get(ini_key)
        if current_hash is None:
            # Path casing may differ between archive revisions; state keys are
            # semantically case-insensitive on the Windows game namespace.
            for rel, digest in (((existing_baseline.get("current") or {}).get("installed_hashes") or {}).items()):
                if isinstance(rel, str) and rel.casefold() == ini_key.casefold():
                    current_hash = digest
                    break
        if (
            isinstance(current_hash, str)
            and live_ini.is_file()
            and not live_ini.is_symlink()
            and sha256_file(live_ini) != current_hash
        ):
            # OptiScaler.ini is expected to change when the user saves settings
            # in-game. Preserve those settings, then reassert only rtxEngine's
            # policy-owned keys instead of replacing the whole config.
            ini_source = live_ini.read_bytes()
    payload[ini_key] = patch_optiscaler_ini(ini_source, family, ada_mfg_mode=ada_mfg_mode, disable_overlays=eos_overlay)

    # Preserve the game-native DLSS-G path. Ada unlock is independent of OptiFG.
    text = payload[ini_key].decode("utf-8")
    is_dlss_unlocked = Y4MY_PROVIDER.get("id") == "dlss-unlocked"
    ada_active = enable_effects and family == "ada" and feature_mode != "nr-only"
    text = set_ini_value(text, "DLSSG", "AdaMfgUnlock", "true" if ada_active else "false")
    text = set_ini_value(
        text, "DLSSG", "AdaBlackwellKernels",
        # DLSS-Unlocked's own Ada configuration keeps this false as the safe
        # baseline; the Blackwell kernel retarget path is experimental and not
        # required for the architecture-gate unlock.
        "false" if is_dlss_unlocked else ("true" if ada_active else "auto"),
    )
    text = set_ini_value(text, "DLSSG", "AmpereMfgUnlock", "false")
    if is_dlss_unlocked and family == "ada":
        # DLSS-Unlocked's documented Ada route: the game owns native
        # Streamline/DLSS-G by default and OptiScaler only applies the Ada
        # capability unlock. Do not force OptiScaler-owned FrameGen routing
        # on top of that -- leave it at the package's own auto defaults.
        text = set_ini_value(text, "FrameGen", "External", "false")
        text = set_ini_value(text, "FrameGen", "Enabled", "auto")
        text = set_ini_value(text, "FrameGen", "FGInput", "auto")
        text = set_ini_value(text, "FrameGen", "FGOutput", "auto")
        text = set_ini_value(text, "FrameGen", "FGNvngxReplacement", "auto")
        # Disable the unstable overlay menu hotkey without touching the NR
        # toggle, which is handled separately via DlssNr.ToggleKey below.
        text = set_ini_value(text, "Menu", "OverlayMenu", "false")
        text = set_ini_value(text, "Menu", "ShortcutKey", "-1")
        if native_mfg_multiplier not in (None, "auto"):
            require(str(native_mfg_multiplier) in {"2", "3", "4", "5", "6"}, "Unsupported native_mfg_multiplier")
            text = set_ini_value(text, "DLSSG", "OverrideInterpolationCount", str(int(native_mfg_multiplier) - 1))
    nr_selected = feature_mode in {"nr-mfg", "nr-only"}
    text = set_ini_value(
        text, "DlssNr", "Enabled",
        # DLSS-Unlocked's NR always starts off; F10 (DlssNr.ToggleKey, set
        # below) is the documented way to turn it on in-session. This is
        # independent of enable_effects, which only gates whether the
        # capability is provisioned at all, not its boot-time state.
        "false" if is_dlss_unlocked else ("true" if enable_effects and nr_selected else "false"),
    )
    if is_dlss_unlocked:
        for key in ("DualFeature", "DualEnlarger", "PreUpscale"):
            text = remove_ini_key(text, "DlssNr", key)
        text = set_ini_value(text, "DlssNr", "RunBeforeSR", "true")
        text = set_ini_value(text, "DlssNr", "DeferredDLSS", "false")
        if feature_mode in {"nr-mfg", "nr-only"}:
            # F10, independent of the OptiScaler overlay menu hotkey above.
            text = set_ini_value(text, "DlssNr", "ToggleKey", "0x79")
    nr_tuning = {
        "WorkingScale": "0.75", "SkinStructure": "1.00", "Intensity": "1.50",
        "TransferStrength": "1.00", "ColourStrength": "1.00",
        "SkinProtection": "auto", "SkinToneEnabled": "auto", "SkinDetail": "auto",
        "SkinColour": "auto", "EnvironmentDetail": "auto", "EnvironmentColour": "auto",
        "FinishedPicture": "auto",
    }
    if feature_mode in {"nr-only", "nr-mfg"}:
        # Defaults for fresh deployments; retain explicit tuning on repair.
        old_nr = re.search(r"(?ims)^\[DlssNr\][^\n]*\n(.*?)(?=^\[|\Z)", ini_source.decode("utf-8"))
        for key, default in nr_tuning.items():
            match = re.search(r"(?im)^\s*" + key + r"\s*=\s*([^;\r\n]+)", old_nr.group(1)) if existing_baseline and old_nr else None
            value = match.group(1).strip() if match and match.group(1).strip().lower() != "auto" else default
            nr_tuning[key] = value
            text = set_ini_value(text, "DlssNr", key, value)
    payload[ini_key] = text.encode("utf-8")

    if mfg_proxy:
        payload[mfg_proxy] = rtxmfg_payload

    if existing_baseline:
        _verify_root_payload_refresh_safe(target, existing_baseline, payload, ini_key)

    if dry_run:
        stale = stale_owned_proxies(target, chosen_proxy, reshade)
        return {"proxy":chosen_proxy, "files":sorted(payload), "remove":stale,
                "launch_options":build_launch_options(chosen_proxy,reshade),
                "feature_mode":feature_mode, "effects_enabled":enable_effects,
                "provider":dict(Y4MY_PROVIDER)}

    # If a previously-owned proxy was externally replaced between installs and
    # ownership is changing now, adopt those current bytes as the restore
    # baseline. This prevents a later uninstall from deleting a newly-added
    # ReShade/other mod.
    adopted_external: set[str] = set()
    if existing_baseline:
        prior = existing_baseline.get("current") or {}
        prior_hashes = prior.get("installed_hashes") or {}
        prior_proxy = prior.get("proxy")
        ownership_changes = []
        if prior_proxy and prior_proxy != chosen_proxy:
            ownership_changes.append(prior_proxy)
        if previous_mfg_proxy and previous_mfg_proxy != mfg_proxy:
            ownership_changes.append(previous_mfg_proxy)

        for rel in sorted(set(ownership_changes), key=str.casefold):
            current_path = target / rel
            expected = prior_hashes.get(rel)
            if current_path.is_file() and expected and sha256_file(current_path) != expected:
                existing_baseline = adopt_external_file_as_original(existing_baseline, target, rel)
                adopted_external.add(rel.casefold())

    stale_proxies = [
        rel for rel in stale_owned_proxies(target, chosen_proxy, reshade)
        if rel.casefold() not in adopted_external
    ]
    if (
        previous_mfg_proxy
        and previous_mfg_proxy != mfg_proxy
        and previous_mfg_proxy.casefold() not in adopted_external
    ):
        stale_proxies.append(previous_mfg_proxy)
    stale_proxies = sorted(set(stale_proxies), key=str.casefold)

    relinquished_provider_paths: list[str] = []
    if existing_baseline:
        prior_proxy = ((existing_baseline.get("current") or {}).get("proxy"))
        protected_paths = {
            rel for rel in (prior_proxy, chosen_proxy, previous_mfg_proxy, mfg_proxy, *stale_proxies)
            if isinstance(rel, str) and rel
        }
        existing_baseline, relinquished_provider_paths = _relinquish_removed_provider_paths(
            target, existing_baseline, payload, archive_meta, protected_paths
        )

    payload_paths = set(payload)
    # RTXMFG creates this at runtime. Track its pre-install existence so
    # uninstall can remove/restore it even though rtxEngine does not create it.
    extra_runtime_paths = {"RTXMFG-Universal.json"} if mfg_proxy else set()
    baseline_paths = payload_paths | extra_runtime_paths
    installed_hashes = {rel: sha256_bytes(data) for rel, data in payload.items()}

    baseline = existing_baseline
    if baseline is None:
        baseline = create_baseline(game, baseline_paths, chosen_proxy, stale_proxies)
    else:
        root_managed_now = {
            p for p in baseline_paths
            if not p.casefold().startswith("optiscaler/")
        }
        root_managed_now.update(stale_proxies)
        root_managed_now.add(chosen_proxy)
        baseline = extend_baseline_for_new_paths(baseline, target, root_managed_now)

    # Persist the COMPLETE ownership/recovery plan BEFORE the first live game
    # mutation. A failed fresh install used to leave managed_paths empty until
    # the final success commit, which meant root payload files written before a
    # crash could survive uninstall. The pending hashes also let restore avoid
    # treating known partial rtxEngine bytes as user drift.
    managed = set(baseline.get("managed_paths", []))
    managed.update(payload_paths)
    managed.update(extra_runtime_paths)
    managed.update(stale_proxies)
    managed = {rel for rel in managed if rel.casefold() not in adopted_external}
    managed.add("OptiScaler/")
    baseline["managed_paths"] = sorted(managed, key=str.casefold)
    baseline["pending_install"] = {
        "started_utc": now_iso(),
        "archive_sha256": archive_meta.get("sha256"),
        "gpu_family": family,
        "proxy": chosen_proxy,
        "mfg_proxy": mfg_proxy,
        "installed_hashes": installed_hashes,
    }
    baseline["status"] = "applying"
    baseline["last_attempt_utc"] = now_iso()
    save_json_atomic(baseline_path(target), baseline)

    repaired = []
    try:
        opti = target / "OptiScaler"
        if opti.exists():
            require(opti.is_dir() and not opti.is_symlink(), "Current OptiScaler path is unsafe")
            hazards = _pristine_tree_hazards(opti)
            require(
                not hazards,
                f"Current OptiScaler has an unsafe filesystem boundary: {hazards[0] if hazards else 'unknown'}",
            )
            if ensure_tree_replaceable(opti, f"{game.name} OptiScaler"):
                repaired.append(str(opti))
            shutil.rmtree(opti)
            _sync_filesystem(target)

        for name in stale_proxies:
            p = target / name
            if p.is_file() and not p.is_symlink():
                if ensure_file_replaceable(p, f"{game.name} stale proxy"):
                    repaired.append(str(p))
                durable_unlink(p)

        # Root package files can also be inherited from old Windows-side mods.
        # Repair only the exact existing files this archive will overwrite.
        for rel in sorted(payload, key=str.casefold):
            if rel.casefold().startswith("optiscaler/"):
                continue
            dst = target / rel
            if dst.is_file() and not dst.is_symlink():
                if ensure_file_replaceable(dst, f"{game.name} package file"):
                    repaired.append(str(dst))

        for rel, data in sorted(payload.items(), key=lambda item: item[0].casefold()):
            dst = target / rel
            dst.resolve().relative_to(target.resolve())
            atomic_write(dst, data, 0o644)
            require(sha256_file(dst) == installed_hashes[rel], f"Write verification failed: {rel}")

        launch = build_launch_options(chosen_proxy, reshade, mfg_proxy)

        record = {
            "installed_utc": now_iso(),
            "archive": archive_meta,
            "gpu_family": family,
            "reshade": reshade,
            "proxy": chosen_proxy,
            # Compatibility field retained for old audit/report readers, but the
            # active provider is now the same y4my OptiScaler proxy as NR.
            "mfg_provider": (
                {
                    "name": Y4MY_PROVIDER["name"],
                    "version": Y4MY_PROVIDER["tag"],
                    "commit": Y4MY_PROVIDER["commit"],
                    "shared_proxy": chosen_proxy,
                    "menu_key": "Alt+Insert / Insert",
                    "ownership": "integrated",
                    "enabled": enable_effects and feature_mode != "nr-only",
                    "activation": "startup" if enable_effects else "dormant",
                }
                if family == "ada" else None
            ),
            "nr_runtime": dict(selected_nr_meta or {}),
            "provider_id": Y4MY_PROVIDER.get("id", "y4my"),
            "feature_mode": feature_mode,
            "nr_profile": {
                "enabled": False if is_dlss_unlocked else (enable_effects and feature_mode in {"nr-mfg", "nr-only"}),
                "activation": "toggle-key-f10" if (is_dlss_unlocked and feature_mode in {"nr-mfg", "nr-only"}) else ("startup" if enable_effects else "dormant"),
                "dual_feature": Y4MY_PROVIDER.get("id") != "dlss-unlocked",
                "dual_enlarger": "dlss" if Y4MY_PROVIDER.get("id") != "dlss-unlocked" else None,
                "run_before_sr": Y4MY_PROVIDER.get("id") == "dlss-unlocked",
                "pre_upscale": False,
                "passes": 1,
                "working_scale": float(nr_tuning["WorkingScale"]),
                "skin_structure": float(nr_tuning["SkinStructure"]),
                "intensity": float(nr_tuning["Intensity"]),
                "menu_key": "F10 (NR toggle) / overlay menu disabled" if is_dlss_unlocked else "Alt+Insert / Insert",
            },
            "compatibility_policy": {
                "proxy_imports": sorted(pe_imported_dlls(game.exe)),
                "proxy_selected": chosen_proxy,
                "eos_overlay_detected": eos_overlay,
                "overlay_blocker_enabled": eos_overlay,
                "dxgi_spoofing": False,
                "vulkan_spoofing": False,
                "upscaler_route": "auto-first-launch",
                "mfg_route": "native-ada-y4my-v4-armed" if family == "ada" else "disabled-sm86",
                "prior_runtime_status": prior_runtime_evidence.get("status") if existing_baseline else None,
                "preserved_proven_proxy": bool(prior_runtime_evidence.get("mfg_applied")),
            },
            "launch_options": launch,
            "installed_hashes": installed_hashes,
            "stale_proxies_removed": stale_proxies,
            "provider_paths_relinquished": relinquished_provider_paths,
            "permission_repairs": repaired,
        }

        baseline["current"] = record
        baseline["status"] = "active"
        baseline["last_error"] = None
        baseline.pop("pending_install", None)
        history = baseline.setdefault("history", [])
        history.append(
            {
                "installed_utc": record["installed_utc"],
                "archive_sha256": archive_meta["sha256"],
                "proxy": chosen_proxy,
                "mfg_proxy": mfg_proxy,
                "gpu_family": family,
                "provider_paths_relinquished": relinquished_provider_paths,
                "permission_repairs": repaired,
            }
        )
        if len(history) > 10:
            del history[:-10]
        save_json_atomic(baseline_path(target), baseline)
        return record

    except BaseException as exc:
        # The baseline remains intentionally available for "Uninstall/restore".
        # Never mislabel a partial target as a successful active install.
        baseline["status"] = "interrupted"
        baseline["last_error"] = str(exc)
        baseline["failed_utc"] = now_iso()
        save_json_atomic(baseline_path(target), baseline)
        raise

def inspect_optiscaler_runtime_log(target: Path, max_bytes: int = 8 * 1024 * 1024) -> dict:
    """Return runtime evidence without treating overlay visibility as health.

    Expedition 33 proved that native MFG may work while the OptiScaler menu is
    unavailable, so RC2 keys live validation to execution markers in the log.
    """
    path = target / "OptiScaler.log"
    if not path.is_file() or path.is_symlink():
        return {"status": "not-observed", "log_present": False, "mfg_applied": False}
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            data = f.read(max_bytes).lower()
    except OSError:
        return {"status": "unreadable", "log_present": True, "mfg_applied": False}

    applied = b"rtxforge.nativemfgmenu.v3e: applied native interpolation request" in data
    bridge = b"rtxforge.nativemfgmenu" in data
    setoptions_error = b"dlss-g setoptions" in data and b"error" in data
    status = "mfg-applied" if applied else ("native-bridge-seen" if bridge else "log-present")
    if setoptions_error:
        status = "runtime-error"
    return {
        "status": status,
        "log_present": True,
        "native_bridge_seen": bridge,
        "mfg_applied": applied,
        "setoptions_error_seen": setoptions_error,
    }

def audit_target(game: Game) -> dict:
    require(game.target_dir is not None, "Missing target")
    baseline = load_baseline(game.target_dir)
    require(baseline is not None and baseline.get("current"), "No active install")
    status = baseline.get("status")
    if baseline.get("schema") in {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}:
        status = status or ("active" if baseline.get("current") else "interrupted")
    require(
        status == "active",
        f"Install state is {status or 'unknown'}, not active; resolve recovery state before audit",
    )
    verify_baseline_integrity(game.target_dir, baseline, adopt_legacy=True)

    current = baseline["current"]
    missing = []
    changed = []

    for rel, digest in current.get("installed_hashes", {}).items():
        p = _target_member_path(game.target_dir, rel)
        if not p.is_file():
            missing.append(rel)
        elif sha256_file(p) != digest:
            changed.append(rel)

    return {
        "game": game.name,
        "target": str(game.target_dir),
        "missing": missing,
        "changed": changed,
        "proxy": current.get("proxy"),
        "mfg_provider": current.get("mfg_provider"),
        "nr_profile": current.get("nr_profile"),
        "compatibility_policy": current.get("compatibility_policy"),
        "runtime_evidence": inspect_optiscaler_runtime_log(game.target_dir),
        "launch_options": current.get("launch_options"),
    }

def write_batch_report(
    action: str,
    results: list[dict],
    drive: Path,
    archive_meta: Optional[dict] = None,
) -> Path:
    require(re.fullmatch(r"[A-Za-z0-9._-]+", action or "") is not None, f"Invalid report action: {action!r}")
    _mkdir_durable(STATE_ROOT)
    stamp = now_stamp()
    report = STATE_ROOT / f"{action}-{stamp}.md"
    counter = 1
    while report.exists() or report.is_symlink():
        report = STATE_ROOT / f"{action}-{stamp}-{counter}.md"
        counter += 1

    lines = [
        f"# rtxEngine {action.title()} Batch · Terminal Edition v13",
        "",
        f"- Time: `{now_iso()}`",
        f"- Drive: `{drive}`",
    ]
    if archive_meta:
        lines += [
            f"- Archive: `{archive_meta['name']}`",
            f"- Archive SHA256: `{archive_meta['sha256']}`",
        ]

    lines += ["", "## Results", ""]

    for row in results:
        lines.append(f"### {row.get('game', 'Unknown')}")
        for key in ("status", "target", "proxy", "mfg_proxy", "error"):
            if row.get(key):
                label = "MFG Proxy" if key == "mfg_proxy" else key.title()
                lines.append(f"- {label}: `{row[key]}`")
        provider = row.get("mfg_provider")
        if provider:
            lines.append(
                f"- MFG provider: `{provider.get('name', 'Unknown')} {provider.get('version', '')}` "
                f"(`{provider.get('ownership', 'unknown')}` owner)"
            )
            if provider.get("dll_sha256"):
                lines.append(f"- MFG DLL SHA256: `{provider['dll_sha256']}`")
            if provider.get("menu_key"):
                lines.append(f"- MFG menu key: `{provider['menu_key']}`")
        runtime = row.get("runtime_evidence")
        if runtime:
            lines.append(
                f"- Runtime evidence: `{runtime.get('status', 'unknown')}` · "
                f"MFG applied=`{runtime.get('mfg_applied', False)}`"
            )
        compat = row.get("compatibility_policy")
        if compat:
            lines.append(
                f"- Injection policy: proxy=`{compat.get('proxy_selected')}` · "
                f"EOS blocker=`{compat.get('overlay_blocker_enabled')}` · "
                f"spoofing=`{compat.get('streamline_spoofing')}`"
            )
        nr = row.get("nr_profile")
        if nr:
            lines.append(
                f"- NR profile: enabled=`{nr.get('enabled')}` · pre-SR=`{nr.get('run_before_sr')}` · "
                f"passes=`{nr.get('passes')}` · working scale=`{nr.get('working_scale')}`"
            )
            if nr.get("menu_key"):
                lines.append(f"- OptiScaler/NR menu key: `{nr['menu_key']}`")
        if row.get("permission_repairs"):
            lines.append(f"- Permission repairs: `{len(row['permission_repairs'])}`")
        if row.get("removed_count") is not None:
            lines.append(f"- Removed artifacts: `{row['removed_count']}`")
            lines.append(f"- Removed bytes: `{row.get('removed_bytes', 0)}`")
            if row.get("receipt"):
                lines.append(f"- Thin receipt: `{row['receipt']}`")
            if row.get("state_dirs_purged") is not None:
                lines.append(f"- Purged rtxEngine state directories: `{row['state_dirs_purged']}`")
        if row.get("launch_options"):
            lines += [
                "- Proton launch options:",
                "",
                "```bash",
                row["launch_options"],
                "```",
            ]
        if row.get("missing") is not None:
            lines.append(f"- Missing: {len(row['missing'])}")
            lines.append(f"- Changed: {len(row['changed'])}")
        lines.append("")

    atomic_write(report, ("\n".join(lines) + "\n").encode("utf-8"), 0o600)
    # Batch reports are diagnostics, not backups. Keep a short per-action tail
    # so routine scans/cleans do not turn STATE_ROOT into an unbounded log pile.
    _prune_paths(list(STATE_ROOT.glob(f"{action}-*.md")), keep=5)
    return report

# Installed-state discovery independent of current scan ----------------------

def load_installed_states_under_drive(drive: Path) -> list[Game]:
    out = []
    targets = _validated_targets_root()
    if not targets.is_dir():
        return out

    for state_dir in targets.iterdir():
        if state_dir.is_symlink():
            warn(f"Corrupt/unreadable install state surfaced: symlink state directory refused: {state_dir}")
            continue
        if not state_dir.is_dir():
            continue
        baseline = state_dir / "baseline.json"
        if not baseline.is_file() or baseline.is_symlink():
            continue
        try:
            raw = json.loads(baseline.read_text(encoding="utf-8"))
            require(isinstance(raw, dict) and isinstance(raw.get("target_dir"), str), "State target missing")
            target = Path(raw["target_dir"]).resolve()
            target.relative_to(drive.resolve())
            require(state_dir == _validated_state_dir(target), "State directory hash/target mismatch")
            data = load_baseline(target)
            require(data is not None, "State disappeared during discovery")
            exe = Path(data["exe"]).resolve() if data.get("exe") else None
            if exe is not None:
                exe.relative_to(drive.resolve())
            status = data.get("status")
            if data.get("schema") in {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}:
                status = data.get("status") or ("active" if data.get("current") else "interrupted")
            game = Game(
                "",
                data.get("name") or (exe.stem if exe else target.name),
                Path(data.get("target_dir", target)).resolve(),
                data.get("source") or "Recorded",
                data.get("appid"),
                None,
                exe,
                target,
                True,
                True,
                None,
                True,
                baseline,
                "INSTALLED" if status == "active" else "RECOVERY",
            )
            out.append(game)
        except Exception as exc:
            warn(f"Corrupt/unreadable install state surfaced: {baseline}: {exc}")
            continue

    out.sort(key=lambda g: (g.source != "Steam", g.name.casefold()))
    for i, g in enumerate(out):
        g.code = code_for_index(i)
    return out


def orphan_state_count_under_drive(drive: Path) -> int:
    targets = _validated_targets_root()
    if not targets.is_dir():
        return 0
    count = 0
    for state_dir in targets.iterdir():
        if state_dir.is_symlink() or not state_dir.is_dir():
            continue
        if (state_dir / "baseline.json").exists():
            continue
        backup = state_dir / "baseline-backup"
        if backup.is_symlink() or not backup.is_dir():
            continue
        # We cannot map opaque target hashes back to G: without a baseline JSON,
        # but these are historical v2/v3 state entries and are safe to quarantine
        # lazily when that target is selected for install.
        count += 1
    return count


# Steam LaunchOptions integration --------------------------------------------

STEAM_ROOT_CANDIDATES = (
    HOME / ".local" / "share" / "Steam",
    HOME / ".steam" / "root",
    HOME / ".steam" / "steam",
    HOME / ".steam" / "debian-installation",
    HOME / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
)

# Keep the removable LaunchOptions ownership surface deliberately tiny.
# rtxEngine owns only its Wine proxy override. NVIDIA capability/runtime flags
# are preserve-only: older builds may have added them, but refresh/uninstall
# must not delete them because some Proton/title combinations still depend on
# explicit native NVIDIA exposure for ordinary DLSS-G / 2x Frame Generation.
MANAGED_LAUNCH_VARS = (
    "WINEDLLOVERRIDES",
)

PRESERVED_NATIVE_NVIDIA_LAUNCH_VARS = (
    "PROTON_ENABLE_NVAPI",
    "PROTON_FORCE_NVAPI",
    "DXVK_ENABLE_NVAPI",
    "PROTON_NVIDIA_NVCUDA",
    "PROTON_NVIDIA_LIBS",
    "PROTON_NVIDIA_LIBS_NO_32BIT",
)

ACTIVE_LAUNCH_VARS = (
    "WINEDLLOVERRIDES",
)

@dataclass
class TextVdfToken:
    kind: str
    value: str
    start: int
    end: int

@dataclass
class TextVdfNode:
    key: str
    value_kind: str
    key_token: TextVdfToken
    value_token: Optional[TextVdfToken] = None
    children: list["TextVdfNode"] = field(default_factory=list)
    open_token: Optional[TextVdfToken] = None
    close_token: Optional[TextVdfToken] = None


def _vdf_unescape(raw: str) -> str:
    out = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            if nxt == "n":
                out.append("\n")
            elif nxt == "t":
                out.append("\t")
            elif nxt == "r":
                out.append("\r")
            elif nxt in {'"', "\\"}:
                out.append(nxt)
            else:
                # Valve files sometimes contain literal Windows-style backslashes.
                out.append("\\")
                out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)

def _vdf_quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'

def _text_vdf_tokens(text: str) -> list[TextVdfToken]:
    tokens: list[TextVdfToken] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i + 2)
            i = n if j < 0 else j + 1
            continue
        if ch in "{}":
            tokens.append(TextVdfToken(ch, ch, i, i + 1))
            i += 1
            continue
        if ch == '"':
            start = i
            i += 1
            raw = []
            while i < n:
                if text[i] == "\\" and i + 1 < n:
                    raw.append(text[i])
                    raw.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                raw.append(text[i])
                i += 1
            else:
                raise Stop("Malformed Steam localconfig.vdf: unterminated quoted string")
            tokens.append(TextVdfToken("string", _vdf_unescape("".join(raw)), start, i))
            continue

        start = i
        while i < n and (not text[i].isspace()) and text[i] not in "{}":
            if text.startswith("//", i):
                break
            i += 1
        if i == start:
            i += 1
            continue
        tokens.append(TextVdfToken("bare", text[start:i], start, i))
    return tokens

def _parse_text_vdf_scope(tokens: list[TextVdfToken], pos: int = 0, expect_close: bool = False):
    nodes: list[TextVdfNode] = []
    while pos < len(tokens):
        tok = tokens[pos]
        if tok.kind == "}":
            if not expect_close:
                raise Stop("Malformed Steam localconfig.vdf: unexpected closing brace")
            return nodes, pos + 1, tok
        if tok.kind in {"{", "}"}:
            raise Stop("Malformed Steam localconfig.vdf: expected a key")

        key_tok = tok
        pos += 1
        if pos >= len(tokens):
            raise Stop("Malformed Steam localconfig.vdf: key without value")
        val_tok = tokens[pos]

        if val_tok.kind == "{":
            children, pos, close_tok = _parse_text_vdf_scope(tokens, pos + 1, True)
            nodes.append(
                TextVdfNode(
                    key_tok.value,
                    "object",
                    key_tok,
                    children=children,
                    open_token=val_tok,
                    close_token=close_tok,
                )
            )
        elif val_tok.kind in {"string", "bare"}:
            nodes.append(
                TextVdfNode(
                    key_tok.value,
                    "scalar",
                    key_tok,
                    value_token=val_tok,
                )
            )
            pos += 1
        else:
            raise Stop("Malformed Steam localconfig.vdf: invalid value")

    if expect_close:
        raise Stop("Malformed Steam localconfig.vdf: missing closing brace")
    return nodes, pos, None

def parse_text_vdf(text: str) -> list[TextVdfNode]:
    tokens = _text_vdf_tokens(text)
    nodes, pos, _ = _parse_text_vdf_scope(tokens)
    require(pos == len(tokens), "Malformed Steam localconfig.vdf")
    return nodes

def _node_ci(nodes: list[TextVdfNode], key: str, object_only: bool = False) -> Optional[TextVdfNode]:
    low = key.casefold()
    for node in nodes:
        if node.key.casefold() == low and (not object_only or node.value_kind == "object"):
            return node
    return None

def _localconfig_apps_node(nodes: list[TextVdfNode]) -> TextVdfNode:
    path = ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps")
    current = nodes
    node = None
    for key in path:
        node = _node_ci(current, key, object_only=True)
        require(node is not None, f"Steam localconfig.vdf is missing {'/'.join(path)}")
        current = node.children
    return node

def _indent_before(text: str, pos: int) -> str:
    line_start = text.rfind("\n", 0, pos) + 1
    m = re.match(r"[ \t]*", text[line_start:pos])
    return m.group(0) if m else ""

def update_localconfig_launch_options(path: Path, updates: dict[str, Optional[str]]) -> dict[str, Optional[str]]:
    """
    Surgically edit only per-app LaunchOptions. The rest of localconfig.vdf is
    byte-for-byte preserved.
    """
    raw = path.read_text(encoding="utf-8", errors="strict")
    nodes = parse_text_vdf(raw)
    apps = _localconfig_apps_node(nodes)
    require(apps.close_token is not None, "Steam apps object has no closing brace")

    edits: list[tuple[int, int, str]] = []
    insertions: list[str] = []
    originals: dict[str, Optional[str]] = {}

    apps_indent = _indent_before(raw, apps.close_token.start)
    app_indent = apps_indent + "\t"
    field_indent = app_indent + "\t"

    for appid, new_value in updates.items():
        app = _node_ci(apps.children, str(appid), object_only=True)
        if app is None:
            originals[str(appid)] = None
            if new_value is None:
                continue
            insertions.append(
                f'\n{app_indent}"{appid}"\n'
                f'{app_indent}{{\n'
                f'{field_indent}"LaunchOptions"\t\t{_vdf_quote(new_value)}\n'
                f'{app_indent}}}'
            )
            continue

        lo = _node_ci(app.children, "LaunchOptions")
        if lo is not None:
            require(lo.value_kind == "scalar" and lo.value_token is not None,
                    f"Steam app {appid} LaunchOptions is not a scalar")
            originals[str(appid)] = lo.value_token.value
            if new_value is None:
                # Exact absence restoration: remove the key/value tokens rather
                # than leaving an empty LaunchOptions value behind.
                edits.append((lo.key_token.start, lo.value_token.end, ""))
            else:
                edits.append((lo.value_token.start, lo.value_token.end, _vdf_quote(new_value)))
        else:
            originals[str(appid)] = None
            if new_value is None:
                continue
            require(app.close_token is not None, f"Steam app {appid} object is malformed")
            indent = _indent_before(raw, app.close_token.start) + "\t"
            edits.append(
                (
                    app.close_token.start,
                    app.close_token.start,
                    f'{indent}"LaunchOptions"\t\t{_vdf_quote(new_value)}\n',
                )
            )

    if insertions:
        edits.append(
            (
                apps.close_token.start,
                apps.close_token.start,
                "".join(insertions) + "\n" + apps_indent,
            )
        )

    new_raw = raw
    for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
        new_raw = new_raw[:start] + replacement + new_raw[end:]

    # Parse before touching disk.
    verify_nodes = parse_text_vdf(new_raw)
    verify_apps = _localconfig_apps_node(verify_nodes)
    for appid, expected in updates.items():
        app = _node_ci(verify_apps.children, str(appid), object_only=True)
        if expected is None:
            if app is None:
                continue
            lo = _node_ci(app.children, "LaunchOptions")
            require(lo is None, f"Verification failed: Steam app {appid} LaunchOptions still present")
            continue
        require(app is not None, f"Verification failed: Steam app {appid} missing")
        lo = _node_ci(app.children, "LaunchOptions")
        require(
            lo is not None and lo.value_token is not None and lo.value_token.value == expected,
            f"Verification failed: Steam app {appid} LaunchOptions",
        )

    atomic_write(path, new_raw.encode("utf-8"), stat.S_IMODE(path.stat().st_mode))
    return originals

def read_localconfig_launch_options(path: Path, appid: str) -> Optional[str]:
    nodes = parse_text_vdf(path.read_text(encoding="utf-8", errors="strict"))
    apps = _localconfig_apps_node(nodes)
    app = _node_ci(apps.children, str(appid), object_only=True)
    if app is None:
        return None
    lo = _node_ci(app.children, "LaunchOptions")
    if lo is None or lo.value_token is None:
        return None
    return lo.value_token.value


@dataclass
class ShortcutFieldSpan:
    typ: int
    key: str
    value_start: int
    value_end: int
    value: object

@dataclass
class ShortcutObjectSpan:
    key: str
    fields: list[ShortcutFieldSpan]
    start: int
    end: int

def _read_cstr_span(data: bytes, pos: int) -> tuple[str, int, int, int]:
    start = pos
    end = data.find(b"\x00", pos)
    require(end >= 0, "Malformed shortcuts.vdf: unterminated string")
    value = data[pos:end].decode("utf-8", errors="surrogateescape")
    return value, end + 1, start, end

def _scan_binary_map(
    data: bytes,
    pos: int,
    *,
    capture_fields: bool = False,
) -> tuple[list[ShortcutFieldSpan], int]:
    """
    Scan one Valve binary KeyValues map without reserializing it.

    We only need the data types Steam actually uses in shortcuts.vdf:
      0x00 nested object
      0x01 NUL-terminated UTF-8 string
      0x02 signed int32
      0x03 float32
      0x07 uint64
      0x08 end-of-map

    Unknown types abort the write path before anything on disk changes.
    """
    fields: list[ShortcutFieldSpan] = []

    while pos < len(data):
        typ = data[pos]
        pos += 1

        if typ == 0x08:
            return fields, pos

        require(
            typ in {0x00, 0x01, 0x02, 0x03, 0x07},
            f"Unsupported shortcuts.vdf binary type 0x{typ:02x}; refusing rewrite",
        )

        key, pos, _ks, _ke = _read_cstr_span(data, pos)

        if typ == 0x00:
            nested_start = pos
            _nested, pos = _scan_binary_map(data, pos, capture_fields=False)
            if capture_fields:
                fields.append(
                    ShortcutFieldSpan(
                        typ=typ,
                        key=key,
                        value_start=nested_start,
                        value_end=pos,
                        value=None,
                    )
                )
            continue

        if typ == 0x01:
            value, next_pos, value_start, value_end = _read_cstr_span(data, pos)
            if capture_fields:
                fields.append(
                    ShortcutFieldSpan(
                        typ=typ,
                        key=key,
                        value_start=value_start,
                        value_end=value_end,
                        value=value,
                    )
                )
            pos = next_pos
            continue

        if typ in {0x02, 0x03}:
            require(pos + 4 <= len(data), "Malformed shortcuts.vdf fixed-width value")
            raw_start = pos
            raw_end = pos + 4
            if typ == 0x02:
                value = struct.unpack_from("<i", data, pos)[0]
            else:
                value = struct.unpack_from("<f", data, pos)[0]
            if capture_fields:
                fields.append(
                    ShortcutFieldSpan(
                        typ=typ,
                        key=key,
                        value_start=raw_start,
                        value_end=raw_end,
                        value=value,
                    )
                )
            pos = raw_end
            continue

        if typ == 0x07:
            require(pos + 8 <= len(data), "Malformed shortcuts.vdf uint64 value")
            raw_start = pos
            raw_end = pos + 8
            value = struct.unpack_from("<Q", data, pos)[0]
            if capture_fields:
                fields.append(
                    ShortcutFieldSpan(
                        typ=typ,
                        key=key,
                        value_start=raw_start,
                        value_end=raw_end,
                        value=value,
                    )
                )
            pos = raw_end
            continue

    raise Stop("Malformed shortcuts.vdf: missing final 0x08 terminator")

def parse_shortcuts_spans(data: bytes) -> list[ShortcutObjectSpan]:
    """
    Strictly parse the real shortcuts.vdf framing and return spans for shortcut
    objects. The root and `shortcuts` object must both have explicit 0x08
    terminators, and the parser must consume the file exactly.
    """
    require(data, "shortcuts.vdf is empty")

    pos = 0

    # Root: 0x00 "shortcuts" <map> 0x08
    require(data[pos] == 0x00, "shortcuts.vdf root is not an object")
    pos += 1
    root_key, pos, _s, _e = _read_cstr_span(data, pos)
    require(root_key.casefold() == "shortcuts", "shortcuts.vdf root key is not `shortcuts`")

    shortcuts: list[ShortcutObjectSpan] = []

    while pos < len(data):
        typ = data[pos]
        pos += 1

        if typ == 0x08:
            # This closes the `shortcuts` object. Real shortcuts.vdf then has
            # one more 0x08 closing the binary-KV root.
            require(pos < len(data), "shortcuts.vdf missing root terminator")
            require(data[pos] == 0x08, "shortcuts.vdf missing final root 0x08")
            pos += 1
            require(pos == len(data), "shortcuts.vdf has trailing bytes after root terminator")
            return shortcuts

        require(typ == 0x00, "shortcuts.vdf contains a non-object shortcut entry")
        obj_key, pos, _ks, _ke = _read_cstr_span(data, pos)
        obj_start = pos
        fields, pos = _scan_binary_map(data, pos, capture_fields=True)
        shortcuts.append(
            ShortcutObjectSpan(
                key=obj_key,
                fields=fields,
                start=obj_start,
                end=pos,
            )
        )

    raise Stop("shortcuts.vdf missing shortcuts/root terminators")

def _shortcut_field(obj: ShortcutObjectSpan, key: str) -> Optional[ShortcutFieldSpan]:
    low = key.casefold()
    for field in obj.fields:
        if field.key.casefold() == low:
            return field
    return None

def _shortcut_string(obj: ShortcutObjectSpan, key: str) -> str:
    field = _shortcut_field(obj, key)
    if field is None or field.typ != 0x01:
        return ""
    return str(field.value)

def _shortcut_int(obj: ShortcutObjectSpan, key: str) -> Optional[int]:
    field = _shortcut_field(obj, key)
    if field is None or field.typ != 0x02:
        return None
    return int(field.value)

def _shortcut_match_score(game: Game, shortcut: ShortcutObjectSpan) -> int:
    appname = _shortcut_string(shortcut, "AppName")
    exe = _unquote_path(_shortcut_string(shortcut, "exe"))
    startdir = _unquote_path(_shortcut_string(shortcut, "StartDir"))
    # Names and executable basenames are not installation identity: lab copies,
    # duplicate libraries and renamed games can share both. Require a path in
    # the selected game tree before scoring display-name preferences.
    if not exe or not Path(exe).is_absolute():
        return 0
    try:
        candidate=Path(exe).expanduser().resolve(strict=False)
        root=game.root.resolve(strict=False)
        if not candidate.is_relative_to(root):
            return 0
    except (OSError,ValueError):
        return 0
    score=100
    if game.exe and candidate == game.exe.resolve(strict=False):
        score+=160
    if appname.casefold().strip() == game.name.casefold().strip():
        score+=120
    return score

def match_shortcut_span(game: Game, shortcuts: list[ShortcutObjectSpan]) -> Optional[ShortcutObjectSpan]:
    candidates = []
    for obj in shortcuts:
        score = _shortcut_match_score(game, obj)
        if score:
            candidates.append((score, obj))

    if not candidates:
        return None

    candidates.sort(key=lambda row: row[0], reverse=True)
    best_score = candidates[0][0]
    best = [obj for score, obj in candidates if score == best_score]
    if len(best) != 1 or best_score < 100:
        return None
    return best[0]

def _encode_shortcut_string_value(value: str) -> bytes:
    raw = value.encode("utf-8", errors="surrogateescape")
    require(b"\x00" not in raw, "NUL is not allowed in Steam LaunchOptions")
    return raw

def patch_shortcuts_launch_options(path: Path, updates: list[tuple[Game, str]]):
    """
    Patch ONLY the bytes occupied by existing LaunchOptions string values.

    We never reconstruct shortcuts.vdf, never renumber shortcut objects, never
    touch tags, AppIDs, executable paths, or unknown fields. If a shortcut
    lacks a LaunchOptions string field, it is skipped rather than modifying
    the binary structure.
    """
    original = path.read_bytes()
    shortcuts = parse_shortcuts_spans(original)

    edits: list[tuple[int, int, bytes]] = []
    results = {}

    for game, new_value in updates:
        obj = match_shortcut_span(game, shortcuts)
        if obj is None:
            results[game.name] = {
                "status": "unmatched",
                "error": "No unique Steam non-Steam shortcut match",
            }
            continue

        launch = _shortcut_field(obj, "LaunchOptions")
        if launch is None or launch.typ != 0x01:
            results[game.name] = {
                "status": "unmatched",
                "error": "Shortcut has no existing LaunchOptions string field; refusing structural rewrite",
            }
            continue

        new_bytes = _encode_shortcut_string_value(new_value)
        edits.append((launch.value_start, launch.value_end, new_bytes))
        results[game.name] = {
            "status": "updated",
            "original": str(launch.value),
            "shortcut_appid": _shortcut_int(obj, "appid"),
            "shortcut_appname": _shortcut_string(obj, "AppName"),
            "shortcut_exe": _shortcut_string(obj, "exe"),
        }

    new_data = original
    for start, end, replacement in sorted(edits, key=lambda row: row[0], reverse=True):
        new_data = new_data[:start] + replacement + new_data[end:]

    # Strictly validate the new real-world binary framing before disk write.
    verify_shortcuts = parse_shortcuts_spans(new_data)

    for game, expected in updates:
        row = results.get(game.name, {})
        if row.get("status") != "updated":
            continue
        obj = match_shortcut_span(game, verify_shortcuts)
        require(obj is not None, f"Verification failed: non-Steam shortcut {game.name}")
        launch = _shortcut_field(obj, "LaunchOptions")
        require(
            launch is not None and launch.typ == 0x01 and launch.value == expected,
            f"Verification failed: {game.name} LaunchOptions",
        )

    # If no edits were needed, leave the file byte-for-byte untouched.
    if edits:
        atomic_write(path, new_data, stat.S_IMODE(path.stat().st_mode))
        require(path.read_bytes() == new_data, "shortcuts.vdf post-write byte verification failed")

    return results

def read_shortcut_launch_option(path: Path, locator: dict) -> str:
    """Read one existing Non-Steam LaunchOptions value using the persisted locator."""
    data = path.read_bytes()
    shortcuts = parse_shortcuts_spans(data)

    wanted_appid = locator.get("shortcut_appid")
    wanted_name = (locator.get("shortcut_appname") or "").casefold()
    wanted_exe = _unquote_path(locator.get("shortcut_exe") or "").casefold()

    matched = None
    for obj in shortcuts:
        appid = _shortcut_int(obj, "appid")
        appname = _shortcut_string(obj, "AppName").casefold()
        exe = _unquote_path(_shortcut_string(obj, "exe")).casefold()
        if wanted_appid is not None and appid == wanted_appid:
            matched = obj
            break
        if wanted_name and appname == wanted_name and (not wanted_exe or exe == wanted_exe):
            matched = obj
            break

    require(matched is not None, f"Could not relocate non-Steam shortcut {locator.get('shortcut_appname')}")
    launch = _shortcut_field(matched, "LaunchOptions")
    require(
        launch is not None and launch.typ == 0x01,
        f"Shortcut {locator.get('shortcut_appname')} has no LaunchOptions string field",
    )
    return str(launch.value)


def restore_shortcut_launch_option(path: Path, locator: dict, original: str) -> None:
    data = path.read_bytes()
    shortcuts = parse_shortcuts_spans(data)

    wanted_appid = locator.get("shortcut_appid")
    wanted_name = (locator.get("shortcut_appname") or "").casefold()
    wanted_exe = _unquote_path(locator.get("shortcut_exe") or "").casefold()

    matched = None
    for obj in shortcuts:
        appid = _shortcut_int(obj, "appid")
        appname = _shortcut_string(obj, "AppName").casefold()
        exe = _unquote_path(_shortcut_string(obj, "exe")).casefold()

        if wanted_appid is not None and appid == wanted_appid:
            matched = obj
            break
        if wanted_name and appname == wanted_name and (not wanted_exe or exe == wanted_exe):
            matched = obj
            break

    require(matched is not None, f"Could not relocate non-Steam shortcut {locator.get('shortcut_appname')}")
    launch = _shortcut_field(matched, "LaunchOptions")
    require(
        launch is not None and launch.typ == 0x01,
        f"Shortcut {locator.get('shortcut_appname')} has no LaunchOptions string field",
    )

    replacement = _encode_shortcut_string_value(original)
    new_data = data[:launch.value_start] + replacement + data[launch.value_end:]
    verify = parse_shortcuts_spans(new_data)

    # Locate again after replacement because offsets may have changed.
    found = None
    for obj in verify:
        appid = _shortcut_int(obj, "appid")
        appname = _shortcut_string(obj, "AppName").casefold()
        exe = _unquote_path(_shortcut_string(obj, "exe")).casefold()
        if wanted_appid is not None and appid == wanted_appid:
            found = obj
            break
        if wanted_name and appname == wanted_name and (not wanted_exe or exe == wanted_exe):
            found = obj
            break

    require(found is not None, "Non-Steam shortcut restore verification could not relocate shortcut")
    verify_launch = _shortcut_field(found, "LaunchOptions")
    require(
        verify_launch is not None and verify_launch.value == original,
        "Non-Steam LaunchOptions restore verification failed",
    )

    atomic_write(path, new_data, stat.S_IMODE(path.stat().st_mode))
    require(path.read_bytes() == new_data, "shortcuts.vdf restore post-write verification failed")

def _unquote_path(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value.replace("\\", "/")


_LEADING_ASSIGNMENT_RE = re.compile(
    r"\s*[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|\S+)"
)

def _launch_env_prefix_end(text: str) -> int:
    """Return the end of the leading shell-assignment segment.

    NAME=value is an environment assignment only while it belongs to the
    leading assignment list. A lookalike after gamescope/env/another wrapper
    is an argument to that wrapper and must not be rewritten.
    """
    text = text or ""
    pos = 0
    while pos < len(text):
        match = _LEADING_ASSIGNMENT_RE.match(text, pos)
        if not match:
            break
        pos = match.end()
    return pos

def _assignment_matches(text: str, name: str):
    prefix = (text or "")[:_launch_env_prefix_end(text or "")]
    pattern = re.compile(
        rf'(?<!\S){re.escape(name)}=(?:"([^"]*)"|\'([^\']*)\'|(\S+))'
    )
    return list(pattern.finditer(prefix))

def _managed_assignment_lookalikes_outside_prefix(text: str) -> list[str]:
    """Find managed NAME=value tokens before %command% outside the env prefix."""
    text = text or ""
    cmd = text.find("%command%")
    end = len(text) if cmd < 0 else cmd
    start = _launch_env_prefix_end(text)
    tail = text[start:end]
    found = []
    for name in MANAGED_LAUNCH_VARS:
        pattern = re.compile(
            rf'(?<!\S){re.escape(name)}=(?:"[^"]*"|\'[^\']*\'|\S+)'
        )
        if pattern.search(tail):
            found.append(name)
    return found

def _assignment_value(match: re.Match) -> str:
    for i in (1, 2, 3):
        value = match.group(i)
        if value is not None:
            return value
    return ""

def _merge_dll_overrides(existing_values: list[str], required_value: str) -> str:
    ordered: list[tuple[str, str]] = []
    index: dict[str, int] = {}

    def add_piece(piece: str, replace: bool):
        piece = piece.strip()
        if not piece:
            return
        dll = piece.split("=", 1)[0].strip().casefold()
        if not dll:
            return
        if dll in index:
            if replace:
                ordered[index[dll]] = (dll, piece)
            return
        index[dll] = len(ordered)
        ordered.append((dll, piece))

    for value in existing_values:
        for piece in value.split(";"):
            add_piece(piece, False)
    for piece in required_value.split(";"):
        add_piece(piece, True)

    return ";".join(piece for _dll, piece in ordered)

def merge_rtxengine_launch_options(existing: Optional[str], required: str) -> str:
    """Merge the minimal rtxEngine launch delta while preserving command structure.

    `required` is authoritative: scalar variables are copied only when the
    current runtime requests them. Legacy variables from older builds are
    removed but never re-added implicitly.
    """
    existing = existing or ""

    ambiguous = _managed_assignment_lookalikes_outside_prefix(existing)
    require(
        not ambiguous,
        "Managed launch variable appears after a launcher/wrapper command; refusing unsafe automatic rewrite: "
        + ", ".join(sorted(ambiguous)),
    )

    required_win = ""
    req_matches = _assignment_matches(required, "WINEDLLOVERRIDES")
    if req_matches:
        required_win = _assignment_value(req_matches[-1])

    existing_win = [_assignment_value(m) for m in _assignment_matches(existing, "WINEDLLOVERRIDES")]
    stripped = _remove_launch_assignments(existing, set(MANAGED_LAUNCH_VARS)).strip()

    if "%command%" not in stripped:
        stripped = ("%command% " + stripped).strip()

    prefix: list[str] = []
    merged_win = _merge_dll_overrides(existing_win, required_win)
    if merged_win:
        require('"' not in merged_win, "Unsafe quote in WINEDLLOVERRIDES")
        prefix.append(f'WINEDLLOVERRIDES="{merged_win}"')

    for name in ACTIVE_LAUNCH_VARS:
        if name == "WINEDLLOVERRIDES":
            continue
        matches = _assignment_matches(required, name)
        if not matches:
            continue
        value = _assignment_value(matches[-1])
        require('"' not in value, f"Unsafe quote in {name}")
        prefix.append(f"{name}={value}")

    return " ".join(prefix + [stripped]).strip()


def _override_pieces_from_launch_options(text: str) -> list[str]:
    pieces: list[str] = []
    for match in _assignment_matches(text or "", "WINEDLLOVERRIDES"):
        for piece in _assignment_value(match).split(";"):
            piece = piece.strip()
            if piece:
                pieces.append(piece)
    return pieces

def _override_piece_key(piece: str) -> str:
    return piece.split("=", 1)[0].strip().casefold()

def _effective_override_map(text: str) -> dict[str, str]:
    """Match merge semantics: the first pre-existing entry for a DLL wins."""
    out: dict[str, str] = {}
    for piece in _override_pieces_from_launch_options(text):
        key = _override_piece_key(piece)
        if key and key not in out:
            out[key] = piece
    return out

def _last_assignment(text: str, name: str) -> tuple[Optional[str], Optional[str]]:
    matches = _assignment_matches(text or "", name)
    if not matches:
        return None, None
    match = matches[-1]
    return _assignment_value(match), match.group(0)

def _remove_launch_assignments(text: str, names: set[str]) -> str:
    end = _launch_env_prefix_end(text or "")
    prefix = (text or "")[:end]
    suffix = (text or "")[end:]
    for name in names:
        prefix = re.sub(
            rf'(?<!\S){re.escape(name)}=(?:"[^"]*"|\'[^\']*\'|\S+)',
            "",
            prefix,
        )
    prefix = prefix.strip()
    suffix = suffix.lstrip()
    if prefix and suffix:
        return f"{prefix} {suffix}"
    return prefix or suffix

def reconcile_rtxengine_launch_options(
    current: Optional[str],
    original: Optional[str],
    applied: str,
) -> Optional[str]:
    """Remove only the LaunchOptions delta that rtxEngine actually introduced.

    Unrelated edits made after install are preserved. Direct edits to a value
    that rtxEngine itself changed remain ambiguous and are refused. This keeps
    uninstall useful without turning LaunchOptions restore into a shell parser
    that guesses at user intent.
    """
    require(current is None or isinstance(current, str), "Current LaunchOptions value is invalid")
    require(original is None or isinstance(original, str), "Original LaunchOptions value is invalid")
    require(isinstance(applied, str), "Applied LaunchOptions value is invalid")

    if current == original:
        return original

    # Never fast-path `current == applied` back to the historical original.
    # Older rtxEngine builds could add native NVIDIA capability variables that
    # are no longer engine-owned. A wholesale restore would delete them along
    # with our proxy override and can disable ordinary native DLSS-G / 2x FG.
    # Always reconcile the semantic proxy delta so preserve-only flags survive.
    current_text = current or ""
    original_text = original or ""
    applied_text = applied or ""

    original_overrides = _effective_override_map(original_text)
    applied_overrides = _effective_override_map(applied_text)
    owned_override_keys = {
        key for key in set(original_overrides) | set(applied_overrides)
        if (original_overrides.get(key) or "").casefold() != (applied_overrides.get(key) or "").casefold()
    }

    # Preserve the current override ordering for everything rtxEngine did not
    # own. For owned DLL names, current must still contain either the value
    # rtxEngine applied or the pre-rtxEngine value (idempotent partial restore).
    current_win_matches = _assignment_matches(current_text, "WINEDLLOVERRIDES")
    if owned_override_keys:
        require(
            len(current_win_matches) <= 1,
            "LaunchOptions has multiple WINEDLLOVERRIDES assignments while rtxEngine-owned overrides are active; refusing ambiguous restore",
        )
    current_pieces = _override_pieces_from_launch_options(current_text)
    adjusted_pieces = list(current_pieces)
    if owned_override_keys:
        seen: dict[str, list[int]] = {}
        for idx, piece in enumerate(current_pieces):
            seen.setdefault(_override_piece_key(piece), []).append(idx)

        replacements: dict[int, Optional[str]] = {}
        for key in owned_override_keys:
            indexes = seen.get(key, [])
            require(
                len(indexes) <= 1,
                f"LaunchOptions has duplicate entries for rtxEngine-owned override {key}; refusing ambiguous restore",
            )
            original_piece = original_overrides.get(key)
            applied_piece = applied_overrides.get(key)
            if not indexes:
                # Missing is safe only when absence is the original state. In
                # that case the user/another tool has already removed our delta.
                require(
                    original_piece is None,
                    f"rtxEngine-owned override {key} changed outside rtxEngine; refusing to guess",
                )
                continue
            idx = indexes[0]
            current_piece = current_pieces[idx]
            if applied_piece is not None and current_piece.casefold() == applied_piece.casefold():
                replacements[idx] = original_piece
            elif original_piece is not None and current_piece.casefold() == original_piece.casefold():
                replacements[idx] = current_piece
            else:
                raise Stop(f"rtxEngine-owned override {key} changed outside rtxEngine; refusing to guess")

        adjusted_pieces = []
        for idx, piece in enumerate(current_pieces):
            if idx in replacements:
                replacement = replacements[idx]
                if replacement:
                    adjusted_pieces.append(replacement)
            else:
                adjusted_pieces.append(piece)

    owned_scalar_names: set[str] = set()
    restored_scalar_literals: list[str] = []
    for name in MANAGED_LAUNCH_VARS:
        if name == "WINEDLLOVERRIDES":
            continue
        original_value, original_literal = _last_assignment(original_text, name)
        applied_value, _applied_literal = _last_assignment(applied_text, name)
        if original_value == applied_value:
            continue
        owned_scalar_names.add(name)
        current_matches = _assignment_matches(current_text, name)
        require(
            len(current_matches) <= 1,
            f"LaunchOptions has duplicate rtxEngine-owned assignment {name}; refusing ambiguous restore",
        )
        if not current_matches:
            require(
                original_value is None,
                f"rtxEngine-owned assignment {name} changed outside rtxEngine; refusing to guess",
            )
            continue
        current_match = current_matches[0]
        current_value = _assignment_value(current_match)
        if current_value == applied_value:
            if original_literal:
                restored_scalar_literals.append(original_literal)
        elif original_value is not None and current_value == original_value:
            restored_scalar_literals.append(current_match.group(0))
        else:
            raise Stop(f"rtxEngine-owned assignment {name} changed outside rtxEngine; refusing to guess")

    # If rtxEngine did not actually alter any managed semantic value, there is
    # no owned delta to remove; preserve the user's current string untouched.
    if not owned_override_keys and not owned_scalar_names:
        return current

    names_to_strip = set(owned_scalar_names)
    if owned_override_keys:
        names_to_strip.add("WINEDLLOVERRIDES")
    body = _remove_launch_assignments(current_text, names_to_strip)

    prefix: list[str] = []
    if owned_override_keys and adjusted_pieces:
        merged_value = ";".join(adjusted_pieces)
        require('"' not in merged_value, "Unsafe quote in WINEDLLOVERRIDES during restore")
        prefix.append(f'WINEDLLOVERRIDES="{merged_value}"')
    prefix.extend(restored_scalar_literals)

    restored = " ".join(prefix + ([body] if body else [])).strip()
    if not restored and original is None:
        return None
    return restored

def _steam_process_names() -> list[str]:
    names = []
    uid = os.getuid()
    proc = Path("/proc")
    if not proc.is_dir():
        return names
    for child in proc.iterdir():
        if not child.name.isdigit():
            continue
        try:
            if child.stat().st_uid != uid:
                continue
            comm = (child / "comm").read_text(errors="ignore").strip()
            if comm in {"steam", "steamwebhelper"}:
                names.append(comm)
        except (OSError, PermissionError):
            continue
    return names

def steam_running() -> bool:
    return bool(_steam_process_names())

def ensure_steam_stopped_for_write(assume_yes: bool = False) -> bool:
    if not steam_running():
        return True

    warn("Steam is running. Steam can overwrite localconfig.vdf/shortcuts.vdf while open.")
    if assume_yes:
        warn("Launch-option sync skipped in non-interactive mode; use --sync-launch-options after closing Steam.")
        return False

    if confirm("Ask Steam to exit cleanly now?", True):
        steam_cmd = shutil.which("steam")
        if steam_cmd:
            try:
                subprocess.run(
                    [steam_cmd, "-shutdown"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
            except Exception:
                pass

        for _ in range(60):
            if not steam_running():
                ok("Steam exited")
                return True
            time.sleep(0.5)

    if steam_running():
        warn("Steam is still running. Close Steam completely, then retry launch-option sync.")
        return False
    return True

def steam_roots_for_config() -> list[Path]:
    out = []
    seen = set()
    for p in STEAM_ROOT_CANDIDATES:
        try:
            rp = p.expanduser().resolve(strict=False)
        except OSError:
            continue
        if not (rp / "userdata").is_dir():
            continue
        if str(rp) not in seen:
            seen.add(str(rp))
            out.append(rp)
    return out

def _most_recent_account_ids(root: Path) -> set[str]:
    login = root / "config" / "loginusers.vdf"
    if not login.is_file():
        return set()
    try:
        nodes = parse_text_vdf(login.read_text(encoding="utf-8", errors="strict"))
        users = _node_ci(nodes, "users", object_only=True)
        if users is None:
            return set()
        out = set()
        for user in users.children:
            if user.value_kind != "object":
                continue
            recent = _node_ci(user.children, "MostRecent")
            if recent and recent.value_token and recent.value_token.value == "1":
                try:
                    out.add(str(int(user.key) & 0xFFFFFFFF))
                except ValueError:
                    pass
        return out
    except Exception as exc:
        # MostRecent is account-selection evidence. Losing it should not make
        # config discovery fatal because stronger per-game evidence may still
        # identify one account, but never pretend a malformed loginusers.vdf
        # was simply absent.
        warn(f"Could not read Steam MostRecent account metadata from {login}: {exc}")
        return set()

def choose_steam_user_config(games: list[Game], assume_yes: bool = False) -> Optional[dict]:
    candidates = []
    steam_appids = [str(g.appid) for g in games if g.appid]
    roots = steam_roots_for_config()

    for root in roots:
        recent_ids = _most_recent_account_ids(root)
        userdata = root / "userdata"
        try:
            userdirs = list(userdata.iterdir())
        except OSError:
            continue

        for userdir in userdirs:
            if not userdir.is_dir() or not userdir.name.isdigit() or userdir.name == "0":
                continue
            config = userdir / "config"
            localconfig = config / "localconfig.vdf"
            shortcuts = config / "shortcuts.vdf"
            if not localconfig.is_file() and not shortcuts.is_file():
                continue

            score = 1000 if userdir.name in recent_ids else 0
            mtime = 0.0
            if localconfig.is_file():
                try:
                    raw = localconfig.read_text(encoding="utf-8", errors="ignore")
                    score += sum(20 for appid in steam_appids if f'"{appid}"' in raw)
                    mtime = max(mtime, localconfig.stat().st_mtime)
                except OSError:
                    pass
            if shortcuts.is_file():
                try:
                    mtime = max(mtime, shortcuts.stat().st_mtime)
                    score += 5
                except OSError:
                    pass

            candidates.append({
                "root": root,
                "userid": userdir.name,
                "config": config,
                "localconfig": localconfig,
                "shortcuts": shortcuts,
                "score": score,
                "mtime": mtime,
            })

    if not candidates:
        return None

    candidates.sort(key=lambda c: (c["score"], c["mtime"]), reverse=True)
    if len(candidates) == 1:
        return candidates[0]

    top = candidates[0]
    second = candidates[1]
    if top["score"] > second["score"]:
        return top

    if assume_yes or not sys.stdin.isatty():
        raise Stop(
            "Multiple Steam userdata accounts are equally plausible; refusing to guess in non-interactive mode. "
            "Run the sync interactively and choose the intended Steam account."
        )

    heading("Steam accounts")
    for i, c in enumerate(candidates, 1):
        print(f"  {i}. Userdata {c['userid']}  score={c['score']}  {c['root']}")
    raw = ask("Choose Steam userdata account", "1")
    try:
        return candidates[int(raw) - 1]
    except Exception:
        raise Stop("Invalid Steam account selection")

def backup_steam_config(path: Path, userid: str) -> Path:
    stamp = now_stamp()
    backup_root = _validated_state_namespace("steam-config-backups")
    _mkdir_durable(backup_root)
    root = _validated_state_child_dir(backup_root, stamp, str(userid))
    _mkdir_durable(root)
    dst = root / path.name
    counter = 1
    while dst.exists():
        dst = root / f"{path.stem}-{counter}{path.suffix}"
        counter += 1
    copy_verified(path, dst)
    # Protect this generation during the pre-journal retention pass. Once the
    # transaction journal exists, _active_steam_backup_generations() owns that
    # protection instead.
    prune_steam_config_backups(keep=2, extra_protected={root.parent})
    return dst

def _steam_transaction_root() -> Path:
    return _validated_state_namespace("steam-transactions")

def _steam_batch_commit_marker(batch_id: str) -> Path:
    require(re.fullmatch(r"[A-Za-z0-9._-]+", batch_id or "") is not None, "Invalid Steam batch id")
    return _steam_transaction_root() / f"batch-{batch_id}.commit"

STEAM_BATCH_COMMIT_MARKER_LEGACY_BYTES = b"rtxEngine Steam restore batch committed\n"
STEAM_BATCH_COMMIT_MARKER_SCHEMA = 2

def _steam_batch_commit_marker_bytes(batch_id: str, transaction_ids: list[str]) -> bytes:
    """Build durable commit evidence bound to one batch and its exact journals."""
    require(re.fullmatch(r"[A-Za-z0-9._-]+", batch_id or "") is not None, "Invalid Steam batch id")
    require(isinstance(transaction_ids, list) and transaction_ids, "Steam batch commit marker requires transaction ids")
    require(all(isinstance(txid, str) and re.fullmatch(r"[A-Za-z0-9._-]+", txid) for txid in transaction_ids), "Invalid Steam transaction id in batch marker")
    require(len(set(transaction_ids)) == len(transaction_ids), "Duplicate Steam transaction id in batch marker")
    payload = {
        "schema": STEAM_BATCH_COMMIT_MARKER_SCHEMA,
        "batch_id": batch_id,
        "transaction_ids": sorted(transaction_ids),
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def _validate_steam_batch_commit_marker(raw: str) -> Path:
    require(isinstance(raw, str) and raw, "Steam batch commit marker missing")
    root = _steam_transaction_root().resolve(strict=False)
    path = Path(raw).expanduser()
    require(path.is_absolute(), "Steam batch commit marker must be absolute")
    require(not path.is_symlink(), f"Steam batch commit marker symlink refused: {path}")
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError):
        raise Stop(f"Steam batch commit marker escapes transaction root: {path}")
    # rtxEngine creates commit markers only as direct children of the transaction
    # namespace. Merely being somewhere below that namespace is not sufficient
    # commit authority: a persisted journal must not be able to nominate a
    # same-named marker from an attacker/corruption-created nested directory.
    require(resolved.parent == root, f"Steam batch commit marker is not a direct transaction-root child: {path}")
    require(re.fullmatch(r"batch-[A-Za-z0-9._-]+\.commit", resolved.name) is not None, f"Invalid Steam batch marker name: {resolved.name}")
    return resolved

def _require_valid_steam_batch_commit_marker(path: Path, *, allow_legacy_orphan: bool = False) -> set[str]:
    """Validate commit evidence and return the exact transaction ids it authorizes."""
    require(not path.is_symlink(), f"Steam batch commit marker symlink refused: {path}")
    require(path.is_file(), f"Steam batch commit marker missing: {path}")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise Stop(f"Steam batch commit marker unreadable: {path}: {exc}") from exc
    if payload == STEAM_BATCH_COMMIT_MARKER_LEGACY_BYTES:
        require(allow_legacy_orphan, f"Legacy Steam batch commit marker is not bound to transaction journals: {path}")
        return set()
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Stop(f"Steam batch commit marker contents are invalid: {path}: {exc}") from exc
    require(isinstance(data, dict), f"Steam batch commit marker contents are invalid: {path}")
    require(type(data.get("schema")) is int and data.get("schema") == STEAM_BATCH_COMMIT_MARKER_SCHEMA, f"Steam batch commit marker schema is invalid: {path}")
    name = path.name
    require(name.startswith("batch-") and name.endswith(".commit"), f"Invalid Steam batch marker name: {name}")
    expected_batch_id = name[len("batch-"):-len(".commit")]
    require(data.get("batch_id") == expected_batch_id, f"Steam batch commit marker batch id does not match filename: {path}")
    txids = data.get("transaction_ids")
    require(isinstance(txids, list) and txids, f"Steam batch commit marker transaction ids are invalid: {path}")
    require(all(isinstance(txid, str) and re.fullmatch(r"[A-Za-z0-9._-]+", txid) for txid in txids), f"Steam batch commit marker transaction id is invalid: {path}")
    require(len(set(txids)) == len(txids), f"Steam batch commit marker contains duplicate transaction ids: {path}")
    return set(txids)

def _validate_steam_config_path(path: Path, kind: str) -> Path:
    expected = "localconfig.vdf" if kind == "steam" else "shortcuts.vdf"
    require(path.name.casefold() == expected, f"Unexpected Steam config filename: {path}")
    resolved = path.expanduser().resolve(strict=False)
    require(not path.is_symlink(), f"Steam config symlink refused: {path}")
    allowed = False
    for root in STEAM_ROOT_CANDIDATES:
        userdata = (root.expanduser().resolve(strict=False) / "userdata")
        try:
            rel = resolved.relative_to(userdata)
        except ValueError:
            continue
        # Steam per-user metadata lives only at:
        #   userdata/<numeric-userid>/config/{localconfig.vdf,shortcuts.vdf}
        # Merely being somewhere below userdata is not enough for a recovery
        # target because a forged journal must not gain write authority over an
        # unrelated same-named file in another userdata subdirectory.
        if (
            len(rel.parts) == 3
            and rel.parts[0].isdigit()
            and rel.parts[0] != "0"
            and rel.parts[1].casefold() == "config"
            and rel.parts[2].casefold() == expected
        ):
            allowed = True
            break
    require(allowed, f"Steam config path is not a canonical userdata/<userid>/config target: {path}")
    return resolved

def _validate_steam_launch_record(rec: dict) -> None:
    require(isinstance(rec, dict), "Steam LaunchOptions state is corrupt")
    kind = rec.get("kind")
    require(kind in {"steam", "shortcut"}, f"Invalid Steam LaunchOptions state kind: {kind!r}")
    raw_path = rec.get("config_path")
    require(isinstance(raw_path, str) and raw_path, "Steam LaunchOptions config path missing")
    _validate_steam_config_path(Path(raw_path), kind)
    original = rec.get("original")
    applied = rec.get("applied")
    required = rec.get("required")
    require(required is None or isinstance(required, str), "Steam LaunchOptions required value is invalid")
    if kind == "steam":
        appid = rec.get("appid")
        require(isinstance(appid, str) and appid.isdigit(), "Steam LaunchOptions AppID is invalid")
        require(original is None or isinstance(original, str), "Steam LaunchOptions original value is invalid")
    else:
        appid = rec.get("shortcut_appid")
        require(appid is None or type(appid) is int, "Non-Steam shortcut AppID is invalid")
        require(isinstance(rec.get("shortcut_appname"), str), "Non-Steam shortcut name is invalid")
        require(isinstance(rec.get("shortcut_exe"), str), "Non-Steam shortcut executable is invalid")
        require(isinstance(original, str), "Non-Steam LaunchOptions original value is invalid")
    require(isinstance(applied, str), "Steam LaunchOptions applied value is invalid")

def begin_steam_transaction(
    kind: str,
    config_path: Path,
    steam_userid: str,
    file_backup: Path,
    entries: list[dict],
) -> tuple[Path, dict]:
    require(kind in {"steam", "shortcut"}, f"Unknown Steam transaction kind: {kind}")
    config = _validate_steam_config_path(config_path, kind)
    require(entries, "Refusing empty Steam transaction")
    root = _steam_transaction_root()
    _mkdir_durable(root)
    txid = f"{now_stamp()}-{os.getpid()}-{time.time_ns()}"
    path = root / f"{txid}.json"
    data = {
        "schema": 1,
        "id": txid,
        "phase": "prepared",
        "kind": kind,
        "created_utc": now_iso(),
        "steam_userid": str(steam_userid),
        "config_path": str(config),
        "file_backup": str(file_backup),
        "entries": entries,
        "baseline_commits": [],
    }
    save_json_atomic(path, data)
    return path, data

def update_steam_transaction(path: Path, data: dict, *, phase: Optional[str] = None) -> None:
    root = _steam_transaction_root().resolve(strict=False)
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError:
        raise Stop(f"Steam transaction path escapes state root: {path}")
    if phase is not None:
        data["phase"] = phase
        data["updated_utc"] = now_iso()
    save_json_atomic(path, data)

def complete_steam_transaction(path: Path, data: dict) -> None:
    update_steam_transaction(path, data, phase="committed")
    durable_unlink(path, missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass
    prune_steam_config_backups(keep=2)

def load_pending_steam_transactions() -> list[tuple[Path, dict]]:
    root = _steam_transaction_root()
    if not root.is_dir():
        return []
    out = []
    for path in sorted(root.glob("*.json")):
        require(not path.is_symlink(), f"Steam transaction journal symlink refused: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Stop(f"Corrupt Steam transaction journal: {path}: {exc}") from exc
        require(isinstance(data, dict) and type(data.get("schema")) is int and data.get("schema") == 1, f"Unsupported Steam transaction journal: {path}")
        phase = data.get("phase")
        require(
            phase in {
                "prepared", "config_written", "baseline_committing", "interrupted",
                "rolling_back", "rollback_metadata_error", "rolled_back", "committed",
            },
            f"Invalid Steam transaction journal phase: {path}",
        )
        require(data.get("kind") in {"steam", "shortcut"}, f"Invalid Steam transaction journal kind: {path}")
        raw_config = data.get("config_path")
        require(isinstance(raw_config, str) and raw_config, f"Invalid Steam transaction journal config path: {path}")
        # Validate the persisted target semantically before either rollback
        # admission or terminal-journal cleanup. A forged/corrupt journal must
        # never be silently retired merely because its phase is terminal.
        _validate_steam_config_path(Path(raw_config), data.get("kind"))
        entries = data.get("entries")
        require(isinstance(entries, list) and entries, f"Invalid Steam transaction journal entries: {path}")
        for entry in entries:
            require(isinstance(entry, dict), f"Invalid Steam transaction journal entry: {path}")
            before = entry.get("before")
            if data.get("kind") == "steam":
                appid = entry.get("appid")
                require(isinstance(appid, str) and appid.isdigit(), f"Invalid Steam transaction AppID in journal: {path}")
                require(before is None or isinstance(before, str), f"Invalid Steam transaction original LaunchOptions in journal: {path}")
            else:
                require(isinstance(before, str), f"Invalid Non-Steam transaction original LaunchOptions in journal: {path}")
                locator = entry.get("locator")
                require(isinstance(locator, dict), f"Invalid Non-Steam transaction locator in journal: {path}")
                shortcut_appid = locator.get("shortcut_appid")
                require(shortcut_appid is None or type(shortcut_appid) is int, f"Invalid Non-Steam shortcut AppID in journal: {path}")
                require(isinstance(locator.get("shortcut_appname"), str), f"Invalid Non-Steam shortcut name in journal: {path}")
                require(isinstance(locator.get("shortcut_exe"), str), f"Invalid Non-Steam shortcut executable in journal: {path}")
        if phase == "rolled_back":
            # Rollback is terminal and cannot be authorized by a batch commit
            # marker. Preserve the existing idempotent cleanup behavior after
            # full envelope validation.
            durable_unlink(path, missing_ok=True)
            continue
        # Keep `committed` journals visible to the recovery coordinator. Batch
        # commit authority lives in a separate durable marker, so deleting a
        # committed journal here would erase one side of that two-sided state
        # before marker/journal coherence can be checked. The coordinator below
        # retires ordinary committed journals only after the global marker scan.
        out.append((path, data))
    return out

def _restore_baseline_steam_metadata(entry: dict, transaction_id: str) -> None:
    """Undo baseline metadata only when this transaction demonstrably wrote it.

    Journal ``target_dir`` is persisted recovery input and therefore cannot by
    itself authorize mutation of another managed target's baseline. Normal
    LaunchOptions sync writes ``transaction_id`` into the new ``steam_launch``
    record before committing that baseline. Recovery only reverses that metadata
    when the currently persisted record still carries this exact transaction id.
    Restore-batch journals do not write baseline metadata and intentionally do
    not carry such a record, so their rollback remains a metadata no-op.
    """
    raw_target = entry.get("target_dir")
    if not isinstance(raw_target, str) or not raw_target:
        return
    if not isinstance(transaction_id, str) or not transaction_id:
        return
    target = Path(raw_target)
    baseline = load_baseline(target)
    if not baseline:
        return
    current = baseline.get("steam_launch")
    if not isinstance(current, dict) or current.get("transaction_id") != transaction_id:
        return
    previous = entry.get("previous_steam_launch")
    if isinstance(previous, dict):
        baseline["steam_launch"] = previous
    else:
        baseline.pop("steam_launch", None)
    save_json_atomic(baseline_path(target), baseline)

def rollback_steam_transaction(path: Path, data: dict) -> dict:
    kind = data.get("kind")
    require(kind in {"steam", "shortcut"}, f"Invalid Steam transaction kind: {kind!r}")
    config = _validate_steam_config_path(Path(data.get("config_path", "")), kind)
    require(config.is_file(), f"Steam transaction config missing: {config}")
    entries = data.get("entries")
    require(isinstance(entries, list) and entries, "Steam transaction entries are corrupt")

    # Preserve the current config immediately before rollback. This stays thin
    # under the existing two-generation Steam config retention policy.
    backup_steam_config(config, str(data.get("steam_userid") or "unknown"))
    update_steam_transaction(path, data, phase="rolling_back")

    if kind == "steam":
        updates: dict[str, Optional[str]] = {}
        for entry in entries:
            appid = entry.get("appid")
            require(isinstance(appid, str) and appid.isdigit(), "Steam transaction AppID is invalid")
            before = entry.get("before")
            require(before is None or isinstance(before, str), "Steam transaction original LaunchOptions is invalid")
            updates[appid] = before
        update_localconfig_launch_options(config, updates)
    else:
        for entry in entries:
            before = entry.get("before")
            require(isinstance(before, str), "Non-Steam transaction original LaunchOptions is invalid")
            locator = entry.get("locator")
            require(isinstance(locator, dict), "Non-Steam transaction locator is invalid")
            restore_shortcut_launch_option(config, locator, before)

    metadata_errors = []
    for entry in entries:
        try:
            _restore_baseline_steam_metadata(entry, str(data.get("id") or ""))
        except Exception as exc:
            metadata_errors.append(f"{entry.get('game', 'unknown')}: {exc}")

    data["rolled_back_utc"] = now_iso()
    if metadata_errors:
        data["metadata_errors"] = metadata_errors
        update_steam_transaction(path, data, phase="rollback_metadata_error")
        raise Stop("Steam config rollback succeeded but baseline metadata recovery needs attention: " + "; ".join(metadata_errors))

    update_steam_transaction(path, data, phase="rolled_back")
    durable_unlink(path, missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass
    prune_steam_config_backups(keep=2)
    return {"id": data.get("id"), "kind": kind, "entries": len(entries), "status": "rolled_back"}

@serialized_mutation
def recover_pending_steam_transactions(assume_yes: bool = False) -> list[dict]:
    pending = load_pending_steam_transactions()
    if not pending:
        # A crash can land after the final committed journal was removed but
        # before its batch marker was unlinked. With no journals left, such
        # markers cannot authorize rollback or cleanup for anything and are
        # safe to retire idempotently.
        root = _steam_transaction_root()
        if root.is_dir():
            for marker in root.glob("batch-*.commit"):
                require(not marker.is_symlink(), f"Steam batch commit marker symlink refused: {marker}")
                # Even an orphan marker is persisted commit authority. Validate
                # it before retirement so malformed/corrupt recovery evidence is
                # never silently erased merely because journal cleanup finished.
                _require_valid_steam_batch_commit_marker(marker, allow_legacy_orphan=True)
                durable_unlink(marker, missing_ok=True)
            try:
                root.rmdir()
                _fsync_dir(root.parent)
            except OSError:
                pass
        return []

    # A batch commit marker is written only after every config in that restore
    # batch has been successfully written. If the process crashed during journal
    # cleanup, finish cleanup without rolling any of those successful writes back.
    #
    # Commit authority is two-sided persisted state: the marker names the exact
    # transaction ids it commits, and each surviving journal names that marker.
    # Validate that relationship globally before deciding that any journal is a
    # rollback candidate. Otherwise a damaged journal that merely loses its
    # batch_commit_marker field could roll back a config that the durable marker
    # proves was already committed.
    pending_by_id: dict[str, tuple[Path, dict]] = {}
    for path, data in pending:
        txid = data.get("id")
        require(
            isinstance(txid, str)
            and re.fullmatch(r"[A-Za-z0-9._-]+", txid) is not None
            and path.name == f"{txid}.json",
            f"Steam transaction journal id does not match filename: {path}",
        )
        require(txid not in pending_by_id, f"Duplicate Steam transaction id: {txid}")
        pending_by_id[txid] = (path, data)

    marker_for_txid: dict[str, Path] = {}
    root = _steam_transaction_root()
    for marker in root.glob("batch-*.commit"):
        canonical = _validate_steam_batch_commit_marker(str(marker.resolve(strict=False)))
        authorized_txids = _require_valid_steam_batch_commit_marker(canonical)
        for txid in authorized_txids:
            if txid not in pending_by_id:
                continue
            prior = marker_for_txid.get(txid)
            require(prior is None or prior == canonical, f"Steam transaction is authorized by multiple batch markers: {txid}")
            marker_for_txid[txid] = canonical

    for txid, (path, data) in pending_by_id.items():
        authoritative_marker = marker_for_txid.get(txid)
        if authoritative_marker is None:
            continue
        raw_marker = data.get("batch_commit_marker")
        require(isinstance(raw_marker, str) and raw_marker, f"Committed Steam transaction journal lost its batch marker binding: {path}")
        journal_marker = _validate_steam_batch_commit_marker(raw_marker)
        require(journal_marker == authoritative_marker, f"Steam transaction journal marker binding disagrees with durable commit authority: {path}")

    committed_groups: dict[Path, list[tuple[Path, dict]]] = {}
    rollback_pending: list[tuple[Path, dict]] = []
    terminal_cleanup: list[tuple[Path, dict]] = []
    for path, data in pending:
        phase = data.get("phase")
        raw_marker = data.get("batch_commit_marker")
        if isinstance(raw_marker, str) and raw_marker:
            marker = _validate_steam_batch_commit_marker(raw_marker)
            if marker.exists():
                authorized_txids = _require_valid_steam_batch_commit_marker(marker)
                txid = data.get("id")
                require(txid in authorized_txids, f"Steam batch commit marker does not authorize transaction journal: {path}")
                require(phase != "rolled_back", f"Rolled-back Steam transaction is contradicted by durable batch commit authority: {path}")
                committed_groups.setdefault(marker, []).append((path, data))
                continue
            if phase == "committed":
                # Batch commits record their marker before any journal reaches
                # `committed`. A surviving committed journal that still names a
                # now-missing marker has lost its durable commit authority and
                # must not be silently retired or rolled back.
                raise Stop(f"Committed Steam transaction batch marker is missing: {path}")
        if phase in {"committed", "rolled_back"}:
            terminal_cleanup.append((path, data))
            continue
        rollback_pending.append((path, data))

    results: list[dict] = []
    for path, data in terminal_cleanup:
        durable_unlink(path, missing_ok=True)
        results.append({
            "id": data.get("id"), "kind": data.get("kind"),
            "entries": len(data.get("entries") or []),
            "status": "terminal-cleanup-completed",
        })
    for marker, group in committed_groups.items():
        for path, data in group:
            durable_unlink(path, missing_ok=True)
            results.append({
                "id": data.get("id"), "kind": data.get("kind"),
                "entries": len(data.get("entries") or []),
                "status": "commit-cleanup-completed",
            })
        durable_unlink(marker, missing_ok=True)
        ok(f"Completed committed Steam metadata batch cleanup: {marker.name}")

    pending = rollback_pending
    if not pending:
        try:
            _steam_transaction_root().rmdir()
        except OSError:
            pass
        return results

    warn(f"Found {len(pending)} interrupted Steam metadata transaction(s).")
    if not assume_yes and not confirm("Roll them back before continuing?", True):
        raise Stop("Interrupted Steam transaction recovery is required before further Steam metadata writes")
    if not ensure_steam_stopped_for_write(assume_yes=assume_yes):
        raise Stop("Steam must be closed to recover interrupted metadata transactions")
    for path, data in pending:
        results.append(rollback_steam_transaction(path, data))
        ok(f"Recovered Steam metadata transaction: {data.get('id')}")
    return results


def _launch_record_for_game(game: Game) -> Optional[dict]:
    if not game.target_dir:
        return None
    baseline = load_baseline(game.target_dir)
    if not baseline:
        return None
    current = baseline.get("current") or {}
    required = current.get("launch_options")
    if not required:
        return None
    return {"baseline": baseline, "required": required}

@serialized_mutation
def sync_launch_options_batch(
    games: list[Game],
    assume_yes: bool = False,
    prompt: bool = True,
) -> list[dict]:
    active = [g for g in games if _launch_record_for_game(g)]
    if not active:
        warn("No active rtxEngine-managed installs have launch options to sync.")
        return []

    recover_pending_steam_transactions(assume_yes=assume_yes)

    if prompt and not assume_yes:
        heading("Steam LaunchOptions sync")
        kv("Games", len(active))
        kv("Behavior", "Merge rtxEngine-owned variables; preserve existing options")
        kv("Reversible", "Original LaunchOptions saved per game")
        if not confirm("Write these launch options directly into Steam?", True):
            return []

    if not ensure_steam_stopped_for_write(assume_yes=assume_yes):
        return [{"game": g.name, "status": "pending", "error": "Steam is running"} for g in active]

    account = choose_steam_user_config(active, assume_yes=assume_yes)
    require(account is not None, "No Steam userdata account/config was found")

    localconfig: Path = account["localconfig"]
    shortcuts_path: Path = account["shortcuts"]
    userid = account["userid"]

    results: list[dict] = []
    steam_games = [g for g in active if g.appid]
    nonsteam_games = [g for g in active if not g.appid]

    # --- Installed Steam games / localconfig.vdf ---
    if steam_games:
        if not localconfig.is_file():
            for g in steam_games:
                results.append({"game": g.name, "status": "failed", "error": "localconfig.vdf missing"})
        else:
            updates: dict[str, str] = {}
            old_by_game: dict[str, Optional[str]] = {}
            baselines_by_name: dict[str, dict] = {}
            for g in steam_games:
                record = _launch_record_for_game(g)
                assert record is not None
                existing = read_localconfig_launch_options(localconfig, str(g.appid))
                merged = merge_rtxengine_launch_options(existing, record["required"])
                updates[str(g.appid)] = merged
                old_by_game[g.name] = existing
                baselines_by_name[g.name] = record["baseline"]

            file_backup = backup_steam_config(localconfig, userid)
            tx_entries = []
            for g in steam_games:
                baseline = baselines_by_name[g.name]
                existing_record = baseline.get("steam_launch")
                original = (
                    existing_record.get("original")
                    if isinstance(existing_record, dict) and "original" in existing_record
                    else old_by_game[g.name]
                )
                merged = updates[str(g.appid)]
                tx_entries.append({
                    "game": g.name,
                    "target_dir": str(g.target_dir),
                    "appid": str(g.appid),
                    "before": old_by_game[g.name],
                    "previous_steam_launch": existing_record if isinstance(existing_record, dict) else None,
                    "new_record": {
                        "kind": "steam",
                        "config_path": str(localconfig),
                        "steam_userid": userid,
                        "appid": str(g.appid),
                        "original": original,
                        "applied": merged,
                        "required": record["required"],
                        "file_backup": str(file_backup),
                        "synced_utc": now_iso(),
                    },
                })

            tx_path, tx = begin_steam_transaction("steam", localconfig, userid, file_backup, tx_entries)
            for entry in tx_entries:
                entry["new_record"]["transaction_id"] = tx["id"]
            update_steam_transaction(tx_path, tx)
            try:
                originals = update_localconfig_launch_options(localconfig, updates)
                for entry in tx_entries:
                    require(
                        originals.get(entry["appid"]) == entry["before"],
                        f"Steam LaunchOptions changed during transaction for AppID {entry['appid']}",
                    )
                update_steam_transaction(tx_path, tx, phase="config_written")

                for entry in tx_entries:
                    target = Path(entry["target_dir"])
                    baseline = load_baseline(target)
                    require(baseline is not None, f"Baseline disappeared during Steam sync: {entry['game']}")
                    baseline["steam_launch"] = entry["new_record"]
                    save_json_atomic(baseline_path(target), baseline)
                    tx["baseline_commits"].append(entry["game"])
                    update_steam_transaction(tx_path, tx, phase="baseline_committing")

                complete_steam_transaction(tx_path, tx)
                for entry in tx_entries:
                    results.append({
                        "game": entry["game"],
                        "status": "written",
                        "kind": "Steam",
                        "launch_options": entry["new_record"]["applied"],
                    })
            except Exception as exc:
                tx["error"] = str(exc)
                try:
                    update_steam_transaction(tx_path, tx, phase="interrupted")
                    rollback_steam_transaction(tx_path, tx)
                except Exception as rollback_exc:
                    raise Stop(
                        f"Steam LaunchOptions transaction interrupted and automatic rollback was incomplete. "
                        f"Run Steam transaction recovery before continuing. Original error: {exc}; "
                        f"rollback error: {rollback_exc}"
                    ) from exc
                raise Stop(f"Steam LaunchOptions transaction rolled back safely: {exc}") from exc

    # --- Non-Steam games / shortcuts.vdf ---
    if nonsteam_games:
        if not shortcuts_path.is_file():
            for g in nonsteam_games:
                results.append({
                    "game": g.name,
                    "status": "unmatched",
                    "error": "shortcuts.vdf missing",
                })
        else:
            shortcut_spans = parse_shortcuts_spans(shortcuts_path.read_bytes())
            pending = []
            pending_meta = {}

            for g in nonsteam_games:
                entry = match_shortcut_span(g, shortcut_spans)
                if entry is None:
                    results.append({
                        "game": g.name,
                        "status": "unmatched",
                        "error": "No unique Steam non-Steam shortcut match",
                    })
                    continue
                launch_field = _shortcut_field(entry, "LaunchOptions")
                if launch_field is None or launch_field.typ != 0x01:
                    results.append({
                        "game": g.name,
                        "status": "unmatched",
                        "error": "Shortcut has no existing LaunchOptions string field",
                    })
                    continue
                existing = str(launch_field.value)
                record = _launch_record_for_game(g)
                assert record is not None
                merged = merge_rtxengine_launch_options(existing, record["required"])
                locator = {
                    "shortcut_appid": _shortcut_int(entry, "appid"),
                    "shortcut_appname": _shortcut_string(entry, "AppName"),
                    "shortcut_exe": _shortcut_string(entry, "exe"),
                }
                pending.append((g, merged))
                pending_meta[g.name] = {
                    "before": existing,
                    "locator": locator,
                    "baseline": record["baseline"],
                }

            if pending:
                file_backup = backup_steam_config(shortcuts_path, userid)
                tx_entries = []
                for g, merged in pending:
                    meta = pending_meta[g.name]
                    baseline = meta["baseline"]
                    existing_record = baseline.get("steam_launch")
                    original = (
                        existing_record.get("original")
                        if isinstance(existing_record, dict) and "original" in existing_record
                        else meta["before"]
                    )
                    locator = meta["locator"]
                    tx_entries.append({
                        "game": g.name,
                        "target_dir": str(g.target_dir),
                        "before": meta["before"],
                        "locator": locator,
                        "previous_steam_launch": existing_record if isinstance(existing_record, dict) else None,
                        "new_record": {
                            "kind": "shortcut",
                            "config_path": str(shortcuts_path),
                            "steam_userid": userid,
                            **locator,
                            "original": original or "",
                            "applied": merged,
                            "required": record["required"],
                            "file_backup": str(file_backup),
                            "synced_utc": now_iso(),
                        },
                    })

                tx_path, tx = begin_steam_transaction("shortcut", shortcuts_path, userid, file_backup, tx_entries)
                for entry in tx_entries:
                    entry["new_record"]["transaction_id"] = tx["id"]
                update_steam_transaction(tx_path, tx)
                try:
                    shortcut_results = patch_shortcuts_launch_options(shortcuts_path, pending)
                    for entry in tx_entries:
                        row = shortcut_results.get(entry["game"], {"status": "unmatched"})
                        require(row.get("status") == "updated", f"Shortcut changed before write: {entry['game']}")
                        require(row.get("original") == entry["before"], f"Shortcut LaunchOptions changed during transaction: {entry['game']}")
                    update_steam_transaction(tx_path, tx, phase="config_written")

                    for entry in tx_entries:
                        target = Path(entry["target_dir"])
                        baseline = load_baseline(target)
                        require(baseline is not None, f"Baseline disappeared during shortcut sync: {entry['game']}")
                        baseline["steam_launch"] = entry["new_record"]
                        save_json_atomic(baseline_path(target), baseline)
                        tx["baseline_commits"].append(entry["game"])
                        update_steam_transaction(tx_path, tx, phase="baseline_committing")

                    complete_steam_transaction(tx_path, tx)
                    for entry in tx_entries:
                        results.append({
                            "game": entry["game"],
                            "status": "written",
                            "kind": "Non-Steam",
                            "launch_options": entry["new_record"]["applied"],
                        })
                except Exception as exc:
                    tx["error"] = str(exc)
                    try:
                        update_steam_transaction(tx_path, tx, phase="interrupted")
                        rollback_steam_transaction(tx_path, tx)
                    except Exception as rollback_exc:
                        raise Stop(
                            f"Non-Steam LaunchOptions transaction interrupted and automatic rollback was incomplete. "
                            f"Run Steam transaction recovery before continuing. Original error: {exc}; "
                            f"rollback error: {rollback_exc}"
                        ) from exc
                    raise Stop(f"Non-Steam LaunchOptions transaction rolled back safely: {exc}") from exc

    heading("LaunchOptions sync")
    kv("Written", sum(r["status"] == "written" for r in results))
    kv("Unmatched", sum(r["status"] == "unmatched" for r in results))
    kv("Failed/pending", sum(r["status"] in {"failed", "pending"} for r in results))
    for row in results:
        if row["status"] in {"unmatched", "failed", "pending"}:
            warn(f"{row['game']}: {row.get('error', row['status'])}")

    return results

@serialized_mutation
def restore_launch_options_batch(games: list[Game], assume_yes: bool = False) -> list[dict]:
    """Restore pre-rtxEngine LaunchOptions as one rollback-safe metadata batch.

    All config-file journals are prepared before the first write. If any later
    config write fails, every prepared/written config is rolled back to the
    exact value observed before this restore attempt. Game files are therefore
    still untouched and Steam metadata is returned to the managed state.

    Unrelated LaunchOptions edits made after sync are preserved by removing only
    the semantic delta rtxEngine introduced. Direct edits to an rtxEngine-owned
    override/assignment remain ambiguous and abort before metadata mutation.
    """
    recover_pending_steam_transactions(assume_yes=assume_yes)

    records: list[tuple[Game, dict]] = []
    for g in games:
        if not g.target_dir:
            continue
        baseline = load_baseline(g.target_dir)
        if baseline and isinstance(baseline.get("steam_launch"), dict):
            _validate_steam_launch_record(baseline["steam_launch"])
            records.append((g, baseline["steam_launch"]))

    if not records:
        return []

    if not ensure_steam_stopped_for_write(assume_yes=assume_yes):
        raise Stop("Steam must be closed to restore LaunchOptions safely")

    # Validate current metadata and detect external/user drift before making a
    # backup, journal, or write. Already-restored values are accepted as a safe
    # idempotent state (for example after an older interrupted uninstall).
    planned: dict[tuple[str, str], list[dict]] = {}
    results: list[dict] = []
    for g, rec in records:
        kind = str(rec["kind"])
        path = _validate_steam_config_path(Path(rec["config_path"]), kind)
        require(path.is_file(), f"Steam config missing during restore: {path}")
        original = rec.get("original")
        applied = rec.get("applied")

        if kind == "steam":
            appid = str(rec["appid"])
            current = read_localconfig_launch_options(path, appid)
            desired = reconcile_rtxengine_launch_options(current, original, applied)
            if current == desired:
                results.append({"game": g.name, "status": "restored", "kind": "Steam", "already_restored": True})
                continue
            entry = {
                "game": g.name,
                "target_dir": str(g.target_dir),
                "appid": appid,
                "before": current,
                "desired": desired,
                "previous_steam_launch": rec,
            }
        else:
            original = original or ""
            current = read_shortcut_launch_option(path, rec)
            desired = reconcile_rtxengine_launch_options(current, original, applied)
            require(isinstance(desired, str), f"Non-Steam LaunchOptions restore produced invalid value for {g.name}")
            if current == desired:
                results.append({"game": g.name, "status": "restored", "kind": "Non-Steam", "already_restored": True})
                continue
            locator = {
                "shortcut_appid": rec.get("shortcut_appid"),
                "shortcut_appname": rec.get("shortcut_appname") or "",
                "shortcut_exe": rec.get("shortcut_exe") or "",
            }
            entry = {
                "game": g.name,
                "target_dir": str(g.target_dir),
                "before": current,
                "desired": desired,
                "locator": locator,
                "previous_steam_launch": rec,
            }
        planned.setdefault((kind, str(path)), []).append(entry)

    if not planned:
        return results

    # Back up each config and prepare every rollback journal BEFORE first write.
    prepared: list[dict] = []
    for (kind, path_s), entries in planned.items():
        path = Path(path_s)
        userid = "unknown"
        for _g, rec in records:
            if str(Path(rec["config_path"]).expanduser().resolve(strict=False)) == path_s:
                userid = str(rec.get("steam_userid") or "unknown")
                break
        file_backup = backup_steam_config(path, userid)
        tx_path, tx = begin_steam_transaction(kind, path, userid, file_backup, entries)
        prepared.append({"kind": kind, "path": path, "entries": entries, "tx_path": tx_path, "tx": tx})

    batch_id = f"restore-{now_stamp()}-{os.getpid()}-{time.time_ns()}"
    batch_marker = _steam_batch_commit_marker(batch_id).resolve(strict=False)
    for item in prepared:
        item["tx"]["batch_commit_marker"] = str(batch_marker)
        update_steam_transaction(item["tx_path"], item["tx"])

    batch_committed = False
    try:
        for item in prepared:
            kind = item["kind"]
            path = item["path"]
            entries = item["entries"]
            tx_path = item["tx_path"]
            tx = item["tx"]

            if kind == "steam":
                updates = {entry["appid"]: entry["desired"] for entry in entries}
                observed = update_localconfig_launch_options(path, updates)
                for entry in entries:
                    require(
                        observed.get(entry["appid"]) == entry["before"],
                        f"Steam LaunchOptions changed during restore transaction: {entry['game']}",
                    )
            else:
                for entry in entries:
                    restore_shortcut_launch_option(path, entry["locator"], entry["desired"])

            update_steam_transaction(tx_path, tx, phase="config_written")

        # Atomically record that EVERY config write succeeded before deleting
        # any individual journal. Recovery treats this marker as authoritative
        # commit evidence if the process dies during journal cleanup.
        atomic_write(
            batch_marker,
            _steam_batch_commit_marker_bytes(batch_id, [item["tx"]["id"] for item in prepared]),
            0o600,
        )
        batch_committed = True
        for item in prepared:
            complete_steam_transaction(item["tx_path"], item["tx"])
            for entry in item["entries"]:
                results.append({
                    "game": entry["game"],
                    "status": "restored",
                    "kind": "Steam" if item["kind"] == "steam" else "Non-Steam",
                })
        durable_unlink(batch_marker, missing_ok=True)
        try:
            _steam_transaction_root().rmdir()
        except OSError:
            pass
    except Exception as exc:
        if batch_committed:
            # Every config write is already durably committed. Rolling back only
            # journals that remain would split the batch if cleanup failed after
            # one earlier journal was deleted. Preserve marker + remaining
            # journals and let transaction recovery finish cleanup idempotently.
            raise Stop(
                "LaunchOptions restore committed successfully, but transaction cleanup was incomplete. "
                "Do not roll back this batch; rerun Steam transaction recovery to finish journal cleanup. "
                f"Cleanup error: {exc}"
            ) from exc

        rollback_errors = []
        for item in reversed(prepared):
            tx_path = item["tx_path"]
            if not tx_path.exists():
                # A transaction should not have been committed before the whole
                # batch succeeds; retain this guard for future refactors.
                continue
            try:
                item["tx"]["error"] = str(exc)
                update_steam_transaction(tx_path, item["tx"], phase="interrupted")
                rollback_steam_transaction(tx_path, item["tx"])
            except Exception as rollback_exc:
                rollback_errors.append(f"{item['path']}: {rollback_exc}")
        if rollback_errors:
            raise Stop(
                "LaunchOptions restore failed and automatic rollback was incomplete. "
                f"Original error: {exc}; rollback errors: {'; '.join(rollback_errors)}"
            ) from exc
        raise Stop(f"LaunchOptions restore rolled back safely: {exc}") from exc

    return results


# Deep Clean implementation --------------------------------------------------

def deep_clean_proxy_override_names(candidates: list["DeepCleanCandidate"]) -> set[str]:
    """Return DLL basenames whose actual proxy artifacts are scheduled for deletion."""
    out = set()
    for item in candidates:
        name = item.path.name.casefold()
        if name in DEEP_CLEAN_PROXY_NAMES:
            out.add(name)
    return out

def scrub_deep_clean_launch_options(existing: Optional[str], proxy_dll_names: set[str]) -> str:
    """
    Remove only WINEDLLOVERRIDES entries whose corresponding proxy DLL is
    positively scheduled for Deep Clean. Preserve unrelated overrides,
    MangoHud/gamescope wrappers, environment variables, and game arguments.
    """
    text = existing or ""
    targets = set()
    for name in proxy_dll_names:
        low = name.casefold().strip()
        if low.endswith(".dll"):
            low = low[:-4]
        if low:
            targets.add(low)
    if not targets:
        return text

    edits = []
    for match in _assignment_matches(text, "WINEDLLOVERRIDES"):
        value = _assignment_value(match)
        kept = []
        removed = False
        for piece in value.split(";"):
            piece = piece.strip()
            if not piece:
                continue
            dll = piece.split("=", 1)[0].strip().casefold()
            if dll.endswith(".dll"):
                dll = dll[:-4]
            if dll in targets:
                removed = True
                continue
            kept.append(piece)
        if not removed:
            continue
        replacement = f'WINEDLLOVERRIDES="{";".join(kept)}"' if kept else ""
        edits.append((match.start(), match.end(), replacement))

    if not edits:
        return text
    for start, end, replacement in sorted(edits, key=lambda x: x[0], reverse=True):
        text = text[:start] + replacement + text[end:]
    # Only normalize horizontal whitespace created by removing assignments.
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return text

def scrub_deep_clean_launch_options_batch(
    plans: list[tuple[Game, list["DeepCleanCandidate"]]],
    assume_yes: bool = False,
) -> list[dict]:
    """Surgically remove stale proxy overrides for DLLs this Deep Clean will delete."""
    affected = []
    proxies_by_game: dict[int, set[str]] = {}
    for game, candidates in plans:
        proxies = deep_clean_proxy_override_names(candidates)
        if proxies:
            affected.append(game)
            proxies_by_game[id(game)] = proxies
    if not affected:
        return []

    recover_pending_steam_transactions(assume_yes=assume_yes)
    if not ensure_steam_stopped_for_write(assume_yes=assume_yes):
        raise Stop("Steam must be closed to scrub stale graphics-proxy LaunchOptions safely")
    account = choose_steam_user_config(affected, assume_yes=assume_yes)
    require(account is not None, "No Steam userdata account/config was found for Deep Clean LaunchOptions scrub")
    localconfig: Path = account["localconfig"]
    shortcuts_path: Path = account["shortcuts"]
    userid = account["userid"]
    results = []

    steam_games = [g for g in affected if g.appid]
    if steam_games and localconfig.is_file():
        updates: dict[str, str] = {}
        before_by_appid: dict[str, Optional[str]] = {}
        game_by_appid = {}
        for game in steam_games:
            appid = str(game.appid)
            before = read_localconfig_launch_options(localconfig, appid)
            after = scrub_deep_clean_launch_options(before, proxies_by_game[id(game)])
            if (before or "") == after:
                continue
            updates[appid] = after
            before_by_appid[appid] = before
            game_by_appid[appid] = game

        if updates:
            backup = backup_steam_config(localconfig, userid)
            entries = []
            for appid, after in updates.items():
                game = game_by_appid[appid]
                baseline = load_baseline(game.target_dir) if game.target_dir else None
                previous = baseline.get("steam_launch") if baseline and isinstance(baseline.get("steam_launch"), dict) else None
                entries.append({
                    "game": game.name,
                    "target_dir": str(game.target_dir) if game.target_dir else "",
                    "appid": appid,
                    "before": before_by_appid[appid],
                    "previous_steam_launch": previous,
                })
            tx_path, tx = begin_steam_transaction("steam", localconfig, userid, backup, entries)
            try:
                observed = update_localconfig_launch_options(localconfig, updates)
                for entry in entries:
                    require(observed.get(entry["appid"]) == entry["before"], f"Steam LaunchOptions changed during Deep Clean scrub: {entry['game']}")
                update_steam_transaction(tx_path, tx, phase="config_written")
                complete_steam_transaction(tx_path, tx)
                for appid, after in updates.items():
                    results.append({"game": game_by_appid[appid].name, "kind": "Steam", "status": "scrubbed", "launch_options": after})
            except Exception as exc:
                tx["error"] = str(exc)
                try:
                    update_steam_transaction(tx_path, tx, phase="interrupted")
                    rollback_steam_transaction(tx_path, tx)
                except Exception as rollback_exc:
                    raise Stop(f"Deep Clean Steam LaunchOptions scrub failed and rollback was incomplete: {exc}; {rollback_exc}") from exc
                raise Stop(f"Deep Clean Steam LaunchOptions scrub rolled back safely: {exc}") from exc

    nonsteam_games = [g for g in affected if not g.appid]
    if nonsteam_games and shortcuts_path.is_file():
        spans = parse_shortcuts_spans(shortcuts_path.read_bytes())
        pending = []
        meta = {}
        for game in nonsteam_games:
            obj = match_shortcut_span(game, spans)
            if obj is None:
                warn(f"Deep Clean could not uniquely match Non-Steam shortcut for LaunchOptions scrub: {game.name}")
                continue
            launch = _shortcut_field(obj, "LaunchOptions")
            if launch is None or launch.typ != 0x01:
                continue
            before = str(launch.value)
            after = scrub_deep_clean_launch_options(before, proxies_by_game[id(game)])
            if before == after:
                continue
            locator = {
                "shortcut_appid": _shortcut_int(obj, "appid"),
                "shortcut_appname": _shortcut_string(obj, "AppName"),
                "shortcut_exe": _shortcut_string(obj, "exe"),
            }
            pending.append((game, after))
            meta[game.name] = {"before": before, "locator": locator}

        if pending:
            backup = backup_steam_config(shortcuts_path, userid)
            entries = []
            for game, _after in pending:
                baseline = load_baseline(game.target_dir) if game.target_dir else None
                previous = baseline.get("steam_launch") if baseline and isinstance(baseline.get("steam_launch"), dict) else None
                entries.append({
                    "game": game.name,
                    "target_dir": str(game.target_dir) if game.target_dir else "",
                    "before": meta[game.name]["before"],
                    "locator": meta[game.name]["locator"],
                    "previous_steam_launch": previous,
                })
            tx_path, tx = begin_steam_transaction("shortcut", shortcuts_path, userid, backup, entries)
            try:
                rows = patch_shortcuts_launch_options(shortcuts_path, pending)
                for entry in entries:
                    row = rows.get(entry["game"], {})
                    require(row.get("status") == "updated" and row.get("original") == entry["before"], f"Non-Steam shortcut changed during Deep Clean scrub: {entry['game']}")
                update_steam_transaction(tx_path, tx, phase="config_written")
                complete_steam_transaction(tx_path, tx)
                for game, after in pending:
                    results.append({"game": game.name, "kind": "Non-Steam", "status": "scrubbed", "launch_options": after})
            except Exception as exc:
                tx["error"] = str(exc)
                try:
                    update_steam_transaction(tx_path, tx, phase="interrupted")
                    rollback_steam_transaction(tx_path, tx)
                except Exception as rollback_exc:
                    raise Stop(f"Deep Clean Non-Steam LaunchOptions scrub failed and rollback was incomplete: {exc}; {rollback_exc}") from exc
                raise Stop(f"Deep Clean Non-Steam LaunchOptions scrub rolled back safely: {exc}") from exc

    return results

@dataclass
class DeepCleanCandidate:
    path: Path
    kind: str
    reason: str
    size: int = 0
    sha256: Optional[str] = None


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _lexical_path_within(path: Path, root: Path) -> bool:
    """Containment check that does not follow the final symlink target."""
    try:
        path.absolute().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _path_is_mount(path: Path) -> bool:
    """Small indirection so destructive traversal boundaries are testable."""
    return path.is_mount()


def _is_dlss_updater_runtime(path: Path) -> bool:
    """Preserve normal NVIDIA/Streamline runtime DLLs outside mod containers."""
    low = path.name.casefold()
    if low in DEEP_CLEAN_EXPLICIT_NR_FILES:
        return False
    return (
        (low.startswith("nvngx_") and low.endswith(".dll"))
        or (low.startswith("sl.") and low.endswith(".dll"))
    )


def _deep_clean_mod_binary(path: Path) -> bool:
    return file_contains_any(
        path, DEEP_CLEAN_BINARY_MARKERS, max_bytes=96 * 1024 * 1024,
    )


def _deep_clean_named_symlink_artifact(name: str, *, reshade_context: bool = False) -> bool:
    """Classify a symlink by its lexical mod identity without following it.

    Generic proxy names such as dxgi.dll are not sufficient on their own: a
    game may legitimately ship a symlink with that basename. rtxEngine-managed
    proxies are already authoritative through baseline state, and ReShade proxy
    names become strong evidence only when ReShade markers are present nearby.
    """
    low = name.casefold()
    suffixes = (".ini", ".log", ".bak", ".json", ".dll", ".exe", ".cfg", ".addon", ".addon64", ".addon32")
    if low in DEEP_CLEAN_EXACT_FILES:
        return True
    if low.startswith(DEEP_CLEAN_FILE_PREFIXES) and low.endswith(suffixes):
        return True
    if low.startswith("optiscaler") and low.endswith((".ini", ".log", ".bak", ".json")):
        return True
    if low.startswith("rtxmfg") and low.endswith((".dll", ".json", ".log", ".ini")):
        return True
    if low.startswith("reshade") and low.endswith((".ini", ".log", ".dll", ".json")):
        return True
    if low.startswith(("renodx", "dlss5-feed")) and low.endswith((".addon64", ".addon32", ".addon", ".dll", ".exe", ".cfg", ".ini", ".log")):
        return True
    if reshade_context and low.endswith((".addon64", ".addon32", ".addon")):
        return True
    if reshade_context and low in {"dxgi.dll", "d3d9.dll", "d3d10.dll", "d3d11.dll", "d3d12.dll", "opengl32.dll"}:
        return True
    return False


def _candidate_size(path: Path) -> int:
    try:
        if path.is_symlink():
            return 0
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            return directory_size(path)
    except OSError:
        pass
    return 0


def deep_clean_scan_game(game: Game) -> list[DeepCleanCandidate]:
    """
    Find strong graphics-mod debris evidence across the whole game root.

    NVIDIA/Streamline runtime DLLs are intentionally preserved unless they are
    inside a known mod directory. Steam verification is the authoritative repair
    step for official files after deletion; it is not used as permission to
    delete arbitrary unknown files.
    """
    root = game.root.resolve()
    require(root.is_dir(), f"Game root missing: {root}")

    found: dict[str, DeepCleanCandidate] = {}

    def add(path: Path, kind: str, reason: str) -> None:
        is_link = path.is_symlink() or kind == "symlink"
        contained = _lexical_path_within(path, root) if is_link else _path_within(path, root)
        require(contained, f"Deep Clean candidate escaped game root: {path}")
        identity = path.absolute() if is_link else path.resolve(strict=False)
        key = str(identity)
        # Compare candidate locations lexically so an outside-pointing symlink
        # can be safely unlinked without treating its target as game content.
        for existing in list(found.values()):
            if existing.kind == "dir":
                try:
                    path.absolute().relative_to(existing.path.absolute())
                    return
                except ValueError:
                    pass
        if kind == "dir":
            for old_key, existing in list(found.items()):
                try:
                    existing.path.absolute().relative_to(path.absolute())
                    del found[old_key]
                except ValueError:
                    pass
        fingerprint = None
        if kind == "file":
            try:
                if path.is_file() and not path.is_symlink():
                    fingerprint = sha256_file(path)
            except OSError:
                fingerprint = None
        found[key] = DeepCleanCandidate(path, kind, reason, _candidate_size(path), fingerprint)

    # Existing rtxEngine state is authoritative evidence of files the engine
    # itself managed, but preserve normal NVIDIA/Streamline runtime DLLs.
    if game.target_dir:
        baseline = load_baseline(game.target_dir)
        if baseline:
            target = game.target_dir.resolve()
            managed_paths = baseline.get("managed_paths", [])
            require(isinstance(managed_paths, list), f"Corrupt managed path list for {game.name}")
            for rel in managed_paths:
                rel = _normalize_state_rel(rel)
                member_rel = "OptiScaler" if rel == "OptiScaler/" or rel.casefold().startswith("optiscaler/") else rel.rstrip("/")
                parts = PurePosixPath(member_rel).parts
                lexical = target.joinpath(*parts)
                require(_lexical_path_within(lexical, target), f"Managed Deep Clean path escaped target: {rel}")
                if lexical.is_symlink():
                    add(lexical, "symlink", "rtxEngine-managed graphics symlink")
                    continue
                p = _target_member_path(target, member_rel)
                if rel == "OptiScaler/" or rel.casefold().startswith("optiscaler/"):
                    if p.exists():
                        add(p, "dir", "rtxEngine-managed OptiScaler tree")
                    continue
                if p.exists() and not _is_dlss_updater_runtime(p):
                    add(p, "dir" if p.is_dir() else "file", "rtxEngine-managed graphics payload")

    for cur, dirs, files in os.walk(root):
        cp = Path(cur)
        # Refuse to walk through symlinked directories.
        safe_dirs = []
        for d in dirs:
            dp = cp / d
            low = d.casefold()
            if dp.is_symlink():
                if low in DEEP_CLEAN_DIR_NAMES or low.startswith(("_optiscaler", "_dlss5", "_true_uninstall")):
                    add(dp, "symlink", "graphics-mod symlink")
                continue
            try:
                if _path_is_mount(dp):
                    warn(f"Deep Clean skipped nested mount point: {dp}")
                    continue
            except OSError:
                warn(f"Deep Clean skipped unclassifiable directory: {dp}")
                continue
            if low in DEEP_CLEAN_DIR_NAMES or low.startswith(("_optiscaler", "_dlss5", "_true_uninstall")):
                add(dp, "dir", "known graphics-mod directory")
                continue
            safe_dirs.append(d)
        dirs[:] = safe_dirs

        reshade_context = (
            (cp / "ReShade.ini").exists()
            or (cp / "reshade-shaders").exists()
            or any(cp.glob("ReShade*.ini"))
        )

        # Preserve game INIs generally, but remove an arbitrary ReShade preset
        # when ReShade.ini explicitly points at it.
        reshade_cfg = cp / "ReShade.ini"
        if reshade_cfg.is_file():
            try:
                cfg_text = reshade_cfg.read_text(encoding="utf-8", errors="replace")
                for match in re.finditer(r"(?im)^\s*PresetPath\s*=\s*(.+?)\s*$", cfg_text):
                    raw = match.group(1).strip().strip('"').replace("\\", "/")
                    if not raw:
                        continue
                    lexical_preset = cp / raw
                    if lexical_preset.is_symlink():
                        if _lexical_path_within(lexical_preset, root):
                            add(lexical_preset, "symlink", "ReShade configured preset symlink")
                        continue
                    preset = lexical_preset.resolve(strict=False)
                    if _path_within(preset, root) and preset.is_file():
                        add(preset, "file", "ReShade configured preset")
            except OSError:
                pass

        for name in files:
            path = cp / name
            low = name.casefold()
            if path.is_symlink():
                if _deep_clean_named_symlink_artifact(low, reshade_context=reshade_context):
                    add(path, "symlink", "graphics-mod symlink")
                continue

            if low in DEEP_CLEAN_EXACT_FILES:
                add(path, "file", "known graphics-mod artifact")
                continue
            if low.startswith(DEEP_CLEAN_FILE_PREFIXES) and low.endswith((".ini", ".log", ".bak", ".json", ".dll", ".exe", ".cfg", ".addon", ".addon64", ".addon32")):
                add(path, "file", "known graphics-mod family")
                continue
            if low.startswith("optiscaler") and low.endswith((".ini", ".log", ".bak", ".json")):
                add(path, "file", "OptiScaler metadata/log")
                continue
            if low.startswith("rtxmfg") and low.endswith((".dll", ".json", ".log", ".ini")):
                add(path, "file", "RTXMFG artifact")
                continue
            if low.startswith("reshade") and low.endswith((".ini", ".log", ".dll", ".json")):
                add(path, "file", "ReShade artifact")
                continue
            if low.startswith(("renodx", "dlss5-feed")) and low.endswith((".addon64", ".addon32", ".addon", ".dll", ".exe", ".cfg", ".ini", ".log")):
                add(path, "file", "RenoDX/DLSS5 injector artifact")
                continue
            if reshade_context and low.endswith((".addon64", ".addon32", ".addon")):
                add(path, "file", "ReShade add-on")
                continue
            if reshade_context and low in {"dxgi.log", "d3d9.log", "d3d10.log", "d3d11.log", "d3d12.log", "opengl32.log"}:
                add(path, "file", "ReShade proxy log")
                continue

            # Never classify normal NVIDIA/Streamline runtime DLLs as debris.
            if _is_dlss_updater_runtime(path):
                continue

            if low in DEEP_CLEAN_PROXY_NAMES and _deep_clean_mod_binary(path):
                add(path, "file", "graphics injector/proxy signature")
                continue
            # Generic game DLLs are NOT safe to delete merely because they
            # mention ReShade/OptiScaler compatibility strings. Restrict
            # free-form signature classification to mod-specific extensions;
            # DLL wrappers must use an explicit known proxy/family name above.
            if low.endswith((".asi", ".addon", ".addon64", ".addon32")) and _deep_clean_mod_binary(path):
                add(path, "file", "graphics-mod binary signature")

    return sorted(found.values(), key=lambda c: (str(c.path).casefold(), c.kind))


def _thin_clean_receipt(
    game: Game,
    candidates: list[DeepCleanCandidate],
    removed: list[dict],
    *,
    status: str = "cleaned",
    error: Optional[str] = None,
) -> Path:
    root = _validated_state_namespace("deep-clean-receipts")
    _mkdir_durable(root)
    receipt = root / f"{target_key(game.root)}.json"
    save_json_atomic(receipt, {
        "schema": 1,
        "time_utc": now_iso(),
        "game": game.name,
        "source": game.source,
        "appid": game.appid,
        "root": str(game.root),
        "mode": "destructive-no-payload-backup",
        "status": status,
        "error": error,
        "preserved_policy": "nvngx_*.dll and sl.*.dll outside known mod directories",
        "planned_count": len(candidates),
        "removed": removed,
    })
    return receipt


def _state_trash_root() -> Path:
    return _validated_state_namespace("state-trash")

def _mark_game_rtxengine_state_destructive_pending(game: Game, mode: str) -> int:
    """Durably mark matching managed state as recovery-only before deletion.

    Destructive modes intentionally retire/purge state after successful cleanup,
    but a hard power loss can occur between the first game-file mutation and
    that purge. Marking the baseline first prevents a partially deleted game
    from still advertising an ordinary active install on the next run while
    preserving its recovery payload until cleanup actually commits.
    """
    require(mode in {"deep-clean", "pristine-reset"}, f"Invalid destructive mode: {mode}")
    targets = _validated_targets_root()
    if not targets.is_dir():
        return 0
    root = game.root.resolve()
    known_state_dir = None
    if game.target_dir is not None:
        # The currently discovered target is authoritative enough to fail closed:
        # destructive cleanup must not proceed past state we know belongs to this
        # game but cannot safely read/retire.
        known_state_dir = _validated_state_dir(game.target_dir.resolve())
    marked = 0
    for state_dir in list(targets.iterdir()):
        if state_dir.is_symlink() or not state_dir.is_dir():
            if known_state_dir is not None and state_dir == known_state_dir:
                raise Stop(f"Known per-target state is unsafe during destructive prepare: {state_dir}")
            if state_dir.is_symlink():
                warn(f"Refusing symlinked per-target state during destructive prepare: {state_dir}")
            continue
        baseline_file = state_dir / "baseline.json"
        if baseline_file.is_symlink():
            if known_state_dir is not None and state_dir == known_state_dir:
                raise Stop(f"Known baseline state file symlink refused during destructive prepare: {baseline_file}")
            continue
        if not baseline_file.is_file():
            continue
        try:
            raw = json.loads(baseline_file.read_text(encoding="utf-8"))
            require(isinstance(raw, dict) and isinstance(raw.get("target_dir"), str), "State target missing")
            target = Path(raw["target_dir"]).resolve()
        except Exception as exc:
            if known_state_dir is not None and state_dir == known_state_dir:
                raise Stop(
                    f"Known rtxEngine state could not be prepared for destructive cleanup: {baseline_file}: {exc}"
                ) from exc
            warn(f"Could not prepare rtxEngine state for destructive cleanup: {baseline_file}: {exc}")
            continue

        try:
            target.relative_to(root)
        except ValueError:
            continue

        try:
            require(state_dir == _validated_state_dir(target, require_exists=True), "State directory hash/target mismatch")
            data = load_baseline(target)
            require(data is not None, "State disappeared during destructive prepare")
        except Exception as exc:
            if known_state_dir is not None and state_dir == known_state_dir:
                raise Stop(
                    f"Known rtxEngine state could not be prepared for destructive cleanup: {baseline_file}: {exc}"
                ) from exc
            warn(f"Could not prepare rtxEngine state for destructive cleanup: {baseline_file}: {exc}")
            continue

        prior = data.get("destructive_pending") if isinstance(data.get("destructive_pending"), dict) else None
        previous_status = (
            prior.get("previous_status") if prior and prior.get("previous_status") is not None
            else data.get("status")
        )
        data["status"] = "destructive-pending"
        data["destructive_pending"] = {
            "mode": mode,
            "started_utc": now_iso(),
            "game_root": str(root),
            "previous_status": previous_status,
        }
        save_json_atomic(baseline_file, data)
        marked += 1
    return marked

def _purge_game_rtxengine_state(game: Game) -> int:
    """Atomically retire per-target state after a destructive clean.

    Never rmtree an active state directory in place. First rename it into an
    inert trash namespace and fsync both parent directories; only then perform
    best-effort recursive cleanup. A crash can therefore leave stale trash,
    but cannot leave a half-deleted active baseline.
    """
    targets = _validated_targets_root()
    if not targets.is_dir():
        return 0
    root = game.root.resolve()
    removed = 0
    for state_dir in list(targets.iterdir()):
        if state_dir.is_symlink() or not state_dir.is_dir():
            if state_dir.is_symlink():
                warn(f"Refusing symlinked per-target state during destructive purge: {state_dir}")
            continue
        baseline = state_dir / "baseline.json"
        if not baseline.is_file() or baseline.is_symlink():
            continue
        try:
            data = json.loads(baseline.read_text(encoding="utf-8"))
            require(isinstance(data, dict) and isinstance(data.get("target_dir"), str), "baseline target missing")
            target = Path(data["target_dir"]).resolve()
        except Exception as exc:
            warn(f"Could not classify rtxEngine state during Deep Clean purge: {baseline}: {exc}")
            continue
        try:
            target.relative_to(root)
        except ValueError:
            continue
        try:
            require(
                baseline.resolve() == baseline_path(target).resolve(),
                "state directory hash/target mismatch",
            )
        except Exception as exc:
            warn(f"Could not classify rtxEngine state during Deep Clean purge: {baseline}: {exc}")
            continue
        require(state_dir.is_dir() and not state_dir.is_symlink(), f"Unsafe state directory: {state_dir}")

        _retire_state_tree(state_dir, f"target-{state_dir.name}")
        removed += 1
    return removed


def deep_clean_apply_game(game: Game, candidates: list[DeepCleanCandidate]) -> dict:
    root = game.root.resolve()
    running = _running_processes_under_root(root)
    require(not running, f"Game process still using {root}: {', '.join(running[:5])}")
    removed: list[dict] = []
    # Leave a durable breadcrumb before the first destructive write. A hard
    # power loss cannot run our exception handler, so without this marker a
    # partial Deep Clean could otherwise have no per-game evidence at all.
    _thin_clean_receipt(game, candidates, removed, status="in-progress")
    _mark_game_rtxengine_state_destructive_pending(game, "deep-clean")
    try:
        for item in sorted(candidates, key=lambda c: len(c.path.parts), reverse=True):
            path = item.path
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise Stop(f"Could not reclassify Deep Clean candidate before deletion: {path}: {exc}") from exc

            if stat.S_ISLNK(mode):
                actual_kind = "symlink"
            elif stat.S_ISDIR(mode):
                actual_kind = "dir"
            elif stat.S_ISREG(mode):
                actual_kind = "file"
            else:
                raise Stop(f"Deep Clean candidate became a special filesystem node: {path}")
            require(
                actual_kind == item.kind,
                f"Deep Clean candidate type changed after preview: {path} ({item.kind} -> {actual_kind})",
            )
            if actual_kind == "file" and item.sha256:
                try:
                    current_hash = sha256_file(path)
                except OSError as exc:
                    raise Stop(f"Could not fingerprint Deep Clean candidate before deletion: {path}: {exc}") from exc
                require(
                    current_hash == item.sha256,
                    f"Deep Clean candidate bytes changed after preview: {path}",
                )

            if actual_kind == "symlink":
                require(_lexical_path_within(path, root), f"Refusing out-of-root symlink deletion: {path}")
                rel = str(path.absolute().relative_to(root))
            else:
                require(_path_within(path, root), f"Refusing out-of-root deletion: {path}")
                rel = str(path.resolve(strict=False).relative_to(root))
            entry = {"path": rel, "kind": item.kind, "reason": item.reason, "size": item.size}
            if actual_kind == "symlink":
                durable_unlink(path)
            elif actual_kind == "dir":
                hazards = _pristine_tree_hazards(path)
                require(
                    not hazards,
                    f"Deep Clean filesystem hazard under {path}: {hazards[0] if hazards else 'unknown'}",
                )
                ensure_tree_replaceable(path, f"{game.name} Deep Clean directory")
                shutil.rmtree(path)
                _sync_filesystem(root)
            else:
                ensure_file_replaceable(path, f"{game.name} Deep Clean file")
                durable_unlink(path)
            removed.append(entry)
    except BaseException as exc:
        receipt = _thin_clean_receipt(
            game, candidates, removed, status="partial-failed", error=str(exc),
        )
        if isinstance(exc, Exception):
            raise Stop(f"{exc} · partial Deep Clean receipt: {receipt}") from exc
        raise

    receipt = _thin_clean_receipt(game, candidates, removed, status="cleaned")
    purged_states = _purge_game_rtxengine_state(game)
    return {
        "game": game.name,
        "status": "cleaned",
        "target": str(game.root),
        "removed_count": len(removed),
        "removed_bytes": sum(int(x.get("size") or 0) for x in removed),
        "receipt": str(receipt),
        "state_dirs_purged": purged_states,
    }


def _steam_command() -> Optional[str]:
    return shutil.which("steam")


def launch_steam_verify(appid: str) -> None:
    steam = _steam_command()
    require(steam is not None, "Steam executable not found; cannot start verification")
    uri = f"steam://validate/{appid}"
    subprocess.Popen(
        [steam, uri],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _verify_queue_path() -> Path:
    return STATE_ROOT / "steam-verify-queue.json"

def _load_verify_queue() -> tuple[Path, dict]:
    path = _verify_queue_path()
    require(not path.is_symlink(), f"Steam verification queue symlink refused: {path}")
    require(path.is_file(), "No pending Steam verification queue")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Stop(f"Steam verification queue is corrupt: {path}: {exc}") from exc
    require(isinstance(data, dict), "Steam verification queue is corrupt")
    schema = data.get("schema")
    require(type(schema) is int and schema in {1, 2}, f"Unsupported Steam verification queue schema: {schema!r}")
    if schema == 1:
        data["schema"] = 2
        data.setdefault("in_flight", None)
        data.setdefault("completed", [])
        save_json_atomic(path, data)
    remaining = data.get("remaining")
    require(isinstance(remaining, list), "Steam verification queue remaining list is corrupt")
    for row in remaining:
        require(isinstance(row, dict), "Steam verification queue row is corrupt")
        require(str(row.get("appid", "")).isdigit(), "Steam verification queue AppID is invalid")
    completed = data.get("completed")
    require(isinstance(completed, list), "Steam verification queue completed list is corrupt")
    for row in completed:
        require(isinstance(row, dict), "Steam verification queue completed row is corrupt")
        require(str(row.get("appid", "")).isdigit(), "Steam verification queue completed AppID is invalid")
    inflight = data.get("in_flight")
    require(inflight is None or isinstance(inflight, dict), "Steam verification in-flight state is corrupt")
    if isinstance(inflight, dict):
        require(str(inflight.get("appid", "")).isdigit(), "Steam verification in-flight AppID is invalid")
        phase = inflight.get("phase", "launched")  # backward-compatible with pre-phase queues
        require(phase in {"launch-intent", "launched"}, f"Steam verification in-flight phase is invalid: {phase!r}")
        offset = inflight.get("start_offset")
        require(type(offset) is int and offset >= 0, "Steam verification in-flight offset is corrupt")
        log_path = inflight.get("log_path")
        require(isinstance(log_path, str) and log_path, "Steam verification in-flight log path is invalid")
        _validate_steam_content_log_path(Path(log_path))
        for identity_key in ("log_dev", "log_ino"):
            identity_value = inflight.get(identity_key)
            require(
                identity_value is None or (type(identity_value) is int and identity_value >= 0),
                f"Steam verification in-flight {identity_key} is corrupt",
            )
        anchor_len = inflight.get("log_anchor_len")
        anchor_sha = inflight.get("log_anchor_sha256")
        require(
            anchor_len is None or (type(anchor_len) is int and 0 <= anchor_len <= offset),
            "Steam verification in-flight log anchor length is corrupt",
        )
        require(
            anchor_sha is None or (isinstance(anchor_sha, str) and re.fullmatch(r"[0-9a-f]{64}", anchor_sha) is not None),
            "Steam verification in-flight log anchor hash is corrupt",
        )
        require(
            (anchor_len is None and anchor_sha is None) or (anchor_len is not None and anchor_sha is not None),
            "Steam verification in-flight log anchor metadata is incomplete",
        )
    return path, data

@serialized_mutation
def save_verify_queue(games: list[Game]) -> Optional[Path]:
    """Create or extend the serialized Steam verification queue safely.

    A new Deep Clean must never overwrite an older in-flight/pending verify.
    If an active queue exists, append only newly requested AppIDs after it. If
    the old queue is already finished, start a fresh queue/history.
    """
    steam_games = [g for g in games if g.appid]
    if not steam_games:
        return None
    path = _verify_queue_path()
    new_rows = [
        {"name": g.name, "appid": str(g.appid), "root": str(g.root)}
        for g in steam_games
    ]

    if path.is_file():
        _existing_path, data = _load_verify_queue()
        remaining = list(data.get("remaining") or [])
        inflight = data.get("in_flight")
        active_ids = {str(row.get("appid")) for row in remaining if isinstance(row, dict)}
        if isinstance(inflight, dict):
            active_ids.add(str(inflight.get("appid")))
        if remaining or isinstance(inflight, dict):
            for row in new_rows:
                if row["appid"] not in active_ids:
                    remaining.append(row)
                    active_ids.add(row["appid"])
            data["remaining"] = remaining
            data["updated_utc"] = now_iso()
            save_json_atomic(path, data)
            return path

    save_json_atomic(path, {
        "schema": 2,
        "created_utc": now_iso(),
        "remaining": new_rows,
        "in_flight": None,
        "completed": [],
    })
    return path

def steam_content_log_path() -> Optional[Path]:
    candidates = []
    for root in steam_roots_for_config():
        path = root / "logs" / "content_log.txt"
        try:
            mtime = path.stat().st_mtime_ns if path.is_file() else -1
        except OSError:
            mtime = -1
        candidates.append((mtime, path))
    if not candidates:
        return None
    candidates.sort(key=lambda row: row[0], reverse=True)
    return candidates[0][1]

def _validate_steam_content_log_path(path: Path) -> Path:
    """Pin verification monitoring to Steam's canonical content_log.txt.

    Persisted queue state is durable across runs, so treat its log path as
    untrusted input.  Merely being *under* a Steam ``logs`` directory is not
    sufficient: a nested or symlink-retargeted ``content_log.txt`` could feed
    synthetic validation markers to the queue and falsely advance it.  Require
    the resolved path itself to be exactly ``<known Steam root>/logs/content_log.txt``.
    """
    require(path.name == "content_log.txt", f"Unexpected Steam content log path: {path}")
    resolved = path.expanduser().resolve(strict=False)
    allowed = False
    for root in STEAM_ROOT_CANDIDATES:
        logs = root.expanduser().resolve(strict=False) / "logs"
        canonical = logs / "content_log.txt"
        if resolved == canonical:
            allowed = True
            break
    require(allowed, f"Steam verification log path is not the canonical content_log.txt for a known Steam root: {path}")
    return resolved

def _steam_log_anchor(log_path: Path, end_offset: int, max_bytes: int = 4096) -> tuple[Optional[int], Optional[str]]:
    """Fingerprint bytes immediately before a persisted content-log offset.

    Device/inode + size detect ordinary rotation/truncation, but Steam can also
    truncate a log *in place* and regrow it past the old byte offset before our
    next poll.  In that case inode and size look valid while the offset now
    points into unrelated bytes.  A small immutable-prefix anchor makes that
    continuity check fail closed without hashing the whole log.
    """
    require(type(end_offset) is int and end_offset >= 0, "Steam verification log offset is invalid")
    if end_offset == 0:
        return None, None
    length = min(int(max_bytes), end_offset)
    try:
        with _validate_steam_content_log_path(log_path).open("rb") as f:
            f.seek(end_offset - length)
            raw = f.read(length)
    except OSError as exc:
        raise Stop(f"Could not fingerprint Steam content log before verification: {log_path}: {exc}") from exc
    require(
        len(raw) == length,
        f"Steam content log changed while preparing verification: {log_path}",
    )
    return length, sha256_bytes(raw)


def _steam_log_slice(
    log_path: Path,
    start_offset: int,
    *,
    expected_dev: Optional[int] = None,
    expected_ino: Optional[int] = None,
    expected_anchor_len: Optional[int] = None,
    expected_anchor_sha256: Optional[str] = None,
) -> tuple[str, int, bool]:
    """Read a Steam content-log slice using a byte offset, not a text cookie.

    ``Path.stat().st_size`` is a byte count. Feeding that value to a text-mode
    ``seek`` is not portable when the log contains non-ASCII text. Read bytes,
    then decode, so queue offsets always mean exactly what we persisted.

    Never silently rebase an in-flight job after Steam rotates or truncates its
    content log. Doing that can expose older/newer records for the same AppID
    and falsely attribute completion to the current queue row. Instead report a
    reset condition so the queue stops safely and the same AppID can be retried.
    """
    log_path = _validate_steam_content_log_path(log_path)
    require(type(start_offset) is int and start_offset >= 0, "Steam verification log offset is invalid")
    try:
        st = log_path.stat()
    except OSError:
        # If we recorded an identity at launch, disappearance/replacement is a
        # reset. For legacy queues without identity metadata, preserve the old
        # wait behavior until a file appears.
        return "", start_offset, expected_dev is not None or expected_ino is not None

    if expected_dev is not None and int(st.st_dev) != int(expected_dev):
        return "", start_offset, True
    if expected_ino is not None and int(st.st_ino) != int(expected_ino):
        return "", start_offset, True
    if st.st_size < start_offset:
        return "", start_offset, True

    if expected_anchor_len is not None or expected_anchor_sha256 is not None:
        if not (
            type(expected_anchor_len) is int
            and 0 < expected_anchor_len <= start_offset
            and isinstance(expected_anchor_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", expected_anchor_sha256) is not None
        ):
            return "", start_offset, True
        try:
            with log_path.open("rb") as f:
                f.seek(start_offset - expected_anchor_len)
                anchor = f.read(expected_anchor_len)
        except OSError:
            return "", start_offset, False
        if len(anchor) != expected_anchor_len or sha256_bytes(anchor) != expected_anchor_sha256:
            return "", start_offset, True

    try:
        with log_path.open("rb") as f:
            f.seek(start_offset)
            raw = f.read()
    except OSError:
        return "", start_offset, False
    return raw.decode("utf-8", errors="replace"), start_offset, False


def _steam_appid_line(line: str, appid: str) -> bool:
    """Match exactly one Steam AppID token; never prefix-match another AppID."""
    return re.search(rf"(?i)\bAppID\s+{re.escape(str(appid))}(?!\d)", line) is not None


def _steam_validation_start_line(line: str, appid: str) -> bool:
    """Require Steam's explicit user-validation marker for this exact AppID.

    Ordinary Steam update jobs also emit ``Running Update,Verifying Installed``
    and end with the same scheduler-finished line as a file-integrity check.
    Treating that generic phase as our launch confirmation can therefore attach
    the queue to an unrelated update for the same game. Steam integrity checks
    emit the distinct ``Start validating appID N`` marker; only that marker is
    strong enough to prove the ``steam://validate/N`` request was accepted.
    """
    return re.search(
        rf"(?i)\bStart\s+validating\s+appID\s+{re.escape(str(appid))}(?!\d)",
        line,
    ) is not None


def steam_validation_status(
    appid: str,
    log_path: Path,
    start_offset: int,
    *,
    expected_dev: Optional[int] = None,
    expected_ino: Optional[int] = None,
    expected_anchor_len: Optional[int] = None,
    expected_anchor_sha256: Optional[str] = None,
) -> dict:
    """Inspect one AppID's post-launch content-log slice without guessing.

    The parser is deliberately AppID-exact. A queue entry for AppID ``123``
    must never consume lines for ``1234``. It also requires AppID-specific
    validation-start evidence before any terminal scheduler result can count.
    """
    empty = {
        "started": False, "completed": False, "failed": False,
        "detail": None, "log_reset": False,
    }
    text, _effective_offset, log_reset = _steam_log_slice(
        log_path, start_offset, expected_dev=expected_dev, expected_ino=expected_ino,
        expected_anchor_len=expected_anchor_len, expected_anchor_sha256=expected_anchor_sha256,
    )
    if log_reset:
        out = dict(empty)
        out["log_reset"] = True
        out["detail"] = "Steam content_log.txt rotated, was replaced, or was truncated during verification"
        return out
    if not text:
        return dict(empty)

    started = False
    failure_detail: Optional[str] = None
    for line in text.splitlines():
        if _steam_validation_start_line(line, appid):
            started = True

        # Steam may refuse a validate request before it emits the normal
        # ``Start validating appID N`` marker.  An AppID-exact scheduler
        # blocker is nevertheless definitive evidence that this request cannot
        # proceed, so fail immediately instead of leaving a launch-intent stuck
        # until its confirmation timeout.
        if _steam_appid_line(line, appid):
            low = line.casefold()
            if "blocking attempt" in low and "updates disabled" in low:
                return {
                    "started": started, "completed": False, "failed": True,
                    "detail": line.strip(), "log_reset": False,
                }
        else:
            continue

        if not started:
            continue

        low = line.casefold()
        if "update canceled" in low or "update failed" in low:
            failure_detail = line.strip()

        if "scheduler finished" in low:
            # Steam can emit a non-terminal scheduler-finished event while the
            # same AppID remains queued ("staying in schedule"). Advancing on
            # that line desynchronizes a multi-game queue. Modern validation
            # completion is explicit: the AppID is *removed from schedule*.
            if "removed from schedule" not in low:
                continue
            if "result no error" in low:
                return {"started": True, "completed": True, "failed": False, "detail": line.strip(), "log_reset": False}
            if "result " in low:
                return {"started": True, "completed": False, "failed": True, "detail": line.strip(), "log_reset": False}
            if failure_detail:
                return {"started": True, "completed": False, "failed": True, "detail": failure_detail, "log_reset": False}
            # A removed-from-schedule terminal line after an AppID-exact
            # validation start is accepted even if this client omitted result=.
            return {"started": True, "completed": True, "failed": False, "detail": line.strip(), "log_reset": False}

    return {"started": started, "completed": False, "failed": False, "detail": failure_detail, "log_reset": False}


def wait_for_steam_validation_start(
    appid: str,
    log_path: Path,
    start_offset: int,
    timeout_seconds: float = 45.0,
    poll_seconds: float = 0.25,
    *,
    expected_dev: Optional[int] = None,
    expected_ino: Optional[int] = None,
    expected_anchor_len: Optional[int] = None,
    expected_anchor_sha256: Optional[str] = None,
) -> dict:
    """Wait briefly for AppID-specific evidence that Steam accepted the URI.

    This is intentionally separate from the hours-long validation wait. A sent
    ``steam://validate`` URI is not proof that Steam actually started that job.
    """
    deadline = time.monotonic() + timeout_seconds
    last = {"started": False, "completed": False, "failed": False, "detail": None}
    while time.monotonic() < deadline:
        last = steam_validation_status(
            appid, log_path, start_offset,
            expected_dev=expected_dev, expected_ino=expected_ino,
            expected_anchor_len=expected_anchor_len, expected_anchor_sha256=expected_anchor_sha256,
        )
        if last.get("log_reset"):
            raise Stop(
                f"Steam verification log changed while AppID {appid} was in flight; "
                "refusing to guess completion. Retry this AppID only."
            )
        if last.get("started") or last.get("completed") or last.get("failed"):
            return last
        time.sleep(poll_seconds)
    return last


def wait_for_steam_validation(
    appid: str,
    log_path: Path,
    start_offset: int,
    timeout_seconds: int = 6 * 60 * 60,
    poll_seconds: float = 1.0,
    *,
    expected_dev: Optional[int] = None,
    expected_ino: Optional[int] = None,
    expected_anchor_len: Optional[int] = None,
    expected_anchor_sha256: Optional[str] = None,
) -> bool:
    """Wait until AppID-specific log evidence proves verification completed."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = steam_validation_status(
            appid, log_path, start_offset,
            expected_dev=expected_dev, expected_ino=expected_ino,
            expected_anchor_len=expected_anchor_len, expected_anchor_sha256=expected_anchor_sha256,
        )
        if status.get("log_reset"):
            raise Stop(
                f"Steam verification log changed while AppID {appid} was in flight; "
                "refusing to guess completion. Retry this AppID only."
            )
        if status.get("failed"):
            raise Stop(
                f"Steam verification failed for AppID {appid}: "
                f"{status.get('detail') or 'Steam reported a failed content job'}"
            )
        if status["completed"]:
            return True
        time.sleep(poll_seconds)
    return False


def _finish_verify_inflight(path: Path, data: dict) -> dict:
    row = data.get("in_flight")
    require(isinstance(row, dict), "No Steam verification is currently in flight")
    completed_row = {k: row.get(k) for k in ("name", "appid", "root")}
    data.setdefault("completed", []).append(completed_row)
    data["last_completed_utc"] = now_iso()
    data["in_flight"] = None
    save_json_atomic(path, data)
    return completed_row


def _resolve_verify_inflight_if_complete(path: Path, data: dict) -> Optional[dict]:
    row = data.get("in_flight")
    if not isinstance(row, dict):
        return None
    log_path = Path(str(row.get("log_path") or ""))
    start_offset = row.get("start_offset")
    require(type(start_offset) is int and start_offset >= 0, "Steam verification in-flight offset is corrupt")
    status = steam_validation_status(
        str(row.get("appid")), log_path, start_offset,
        expected_dev=row.get("log_dev"), expected_ino=row.get("log_ino"),
        expected_anchor_len=row.get("log_anchor_len"), expected_anchor_sha256=row.get("log_anchor_sha256"),
    )
    if status.get("log_reset"):
        raise Stop(
            f"Steam verification log changed while {row.get('name')} ({row.get('appid')}) was in flight; "
            "refusing to advance the queue. Retry the current AppID."
        )
    if status.get("failed"):
        raise Stop(
            f"Steam verification failed for {row.get('name')} ({row.get('appid')}): "
            f"{status.get('detail') or 'Steam reported a failed content job'}"
        )
    if status["completed"]:
        return _finish_verify_inflight(path, data)
    if row.get("phase", "launched") == "launch-intent" and status.get("started"):
        row["phase"] = "launched"
        row["launch_confirmed_utc"] = now_iso()
        data["in_flight"] = row
        save_json_atomic(path, data)
    return None


@serialized_mutation
def start_next_steam_verify() -> dict:
    path, data = _load_verify_queue()
    if data.get("in_flight") is not None:
        finished = _resolve_verify_inflight_if_complete(path, data)
        if finished is None:
            row = data["in_flight"]
            raise Stop(
                f"Steam verification is still in flight for {row.get('name')} ({row.get('appid')}); "
                "refusing to overlap another validation. Use the sequential queue monitor."
            )
        path, data = _load_verify_queue()

    remaining = data.get("remaining") or []
    require(remaining, "Steam verification queue is empty")
    row = dict(remaining[0])
    log_path = steam_content_log_path()
    require(log_path is not None, "Steam content log location could not be resolved")
    try:
        log_stat = log_path.stat() if log_path.is_file() else None
        offset = log_stat.st_size if log_stat is not None else 0
        log_dev = int(log_stat.st_dev) if log_stat is not None else None
        log_ino = int(log_stat.st_ino) if log_stat is not None else None
        log_anchor_len, log_anchor_sha256 = _steam_log_anchor(log_path, int(offset)) if log_stat is not None else (None, None)
    except OSError:
        offset = 0
        log_dev = None
        log_ino = None
        log_anchor_len = None
        log_anchor_sha256 = None

    # Persist ownership before sending the URI. Crucially, keep the phase as
    # launch-intent until the content log proves *this AppID* actually started.
    # URI dispatch is asynchronous and Steam can ignore/defer it while settling
    # a previous content job.
    data["remaining"] = remaining[1:]
    data["in_flight"] = {
        **row,
        "log_path": str(log_path),
        "start_offset": int(offset),
        "log_dev": log_dev,
        "log_ino": log_ino,
        "log_anchor_len": log_anchor_len,
        "log_anchor_sha256": log_anchor_sha256,
        "phase": "launch-intent",
        "launch_recorded_utc": now_iso(),
    }
    save_json_atomic(path, data)
    try:
        launch_steam_verify(str(row["appid"]))
    except Exception:
        current_path, current = _load_verify_queue()
        current["remaining"] = [row] + (current.get("remaining") or [])
        current["in_flight"] = None
        save_json_atomic(current_path, current)
        raise

    # Record that the URI send call returned, but do NOT call the job launched.
    # Only AppID-specific content-log evidence may promote launch-intent.
    current_path, current = _load_verify_queue()
    current_row = current.get("in_flight")
    if isinstance(current_row, dict) and str(current_row.get("appid")) == str(row["appid"]):
        current_row["uri_sent_utc"] = now_iso()
        current["in_flight"] = current_row
        save_json_atomic(current_path, current)
    return row


@serialized_mutation
def retry_failed_steam_verify() -> dict:
    """Re-launch only the current AppID after failure or unconfirmed dispatch."""
    path, data = _load_verify_queue()
    row = data.get("in_flight")
    require(isinstance(row, dict), "No failed Steam verification is currently in flight")
    log_path = Path(str(row.get("log_path") or ""))
    start_offset = row.get("start_offset")
    require(type(start_offset) is int and start_offset >= 0, "Steam verification in-flight offset is corrupt")
    status = steam_validation_status(
        str(row.get("appid")), log_path, start_offset,
        expected_dev=row.get("log_dev"), expected_ino=row.get("log_ino"),
        expected_anchor_len=row.get("log_anchor_len"), expected_anchor_sha256=row.get("log_anchor_sha256"),
    )
    launch_unconfirmed = (
        row.get("phase", "launched") == "launch-intent"
        and not status.get("started")
        and not status.get("completed")
        and not status.get("failed")
    )
    require(
        status.get("failed") or status.get("log_reset") or launch_unconfirmed,
        "Current Steam verification has neither failed, lost its log continuity, nor remained as an unconfirmed launch-intent; refusing to restart it blindly",
    )

    clean_row = {k: row.get(k) for k in ("name", "appid", "root")}
    data["remaining"] = [clean_row] + list(data.get("remaining") or [])
    data["in_flight"] = None
    data["last_retry_utc"] = now_iso()
    data["last_retry_from_error"] = status.get("detail")
    save_json_atomic(path, data)
    return start_next_steam_verify()


@serialized_mutation
def run_steam_verify_queue_sequential(
    timeout_seconds: int = 6 * 60 * 60,
    launch_confirm_seconds: float = 45.0,
) -> dict:
    path, data = _load_verify_queue()
    completed_this_run = []

    while True:
        path, data = _load_verify_queue()
        inflight = data.get("in_flight")
        remaining = data.get("remaining") or []
        if inflight is None and not remaining:
            return {
                "completed": completed_this_run,
                "pending": 0,
                "completed_total": len(data.get("completed") or []),
            }

        if inflight is None:
            row = start_next_steam_verify()
            ok(f"Steam verification requested: {row['name']} ({row['appid']})")
            path, data = _load_verify_queue()
            inflight = data.get("in_flight")
            remaining = data.get("remaining") or []

        require(isinstance(inflight, dict), "Steam verification in-flight state disappeared")
        log_path = Path(str(inflight.get("log_path") or ""))
        start_offset = inflight.get("start_offset")
        require(type(start_offset) is int and start_offset >= 0, "Steam verification in-flight offset is corrupt")

        if inflight.get("phase", "launched") == "launch-intent":
            status = wait_for_steam_validation_start(
                str(inflight["appid"]),
                log_path,
                start_offset,
                timeout_seconds=launch_confirm_seconds,
                expected_dev=inflight.get("log_dev"),
                expected_ino=inflight.get("log_ino"),
                expected_anchor_len=inflight.get("log_anchor_len"),
                expected_anchor_sha256=inflight.get("log_anchor_sha256"),
            )
            if status.get("completed"):
                finished = _finish_verify_inflight(path, data)
                completed_this_run.append(finished)
                ok(f"Steam verification completed: {finished['name']}")
                continue
            if status.get("failed"):
                raise Stop(
                    f"Steam verification failed for AppID {inflight['appid']}: "
                    f"{status.get('detail') or 'Steam reported a failed content job'}"
                )
            if status.get("started"):
                inflight["phase"] = "launched"
                inflight["launch_confirmed_utc"] = now_iso()
                data["in_flight"] = inflight
                save_json_atomic(path, data)
            else:
                pending = len(remaining) + 1
                warn(
                    f"Steam did not confirm a validation start for {inflight['name']} ({inflight['appid']}) "
                    f"within {launch_confirm_seconds:g}s. No later game was started."
                )
                return {
                    "completed": completed_this_run,
                    "pending": pending,
                    "unconfirmed_launch": {k: inflight.get(k) for k in ("name", "appid", "root")},
                    "log": str(log_path),
                }

        if not wait_for_steam_validation(
            str(inflight["appid"]),
            log_path,
            start_offset,
            timeout_seconds=timeout_seconds,
            expected_dev=inflight.get("log_dev"),
            expected_ino=inflight.get("log_ino"),
            expected_anchor_len=inflight.get("log_anchor_len"),
            expected_anchor_sha256=inflight.get("log_anchor_sha256"),
        ):
            path, current = _load_verify_queue()
            pending = len(current.get("remaining") or []) + (1 if current.get("in_flight") else 0)
            warn(
                f"Could not prove Steam verification completed for {inflight['name']}; "
                "the game remains marked in-flight and no later validation will be started."
            )
            return {
                "completed": completed_this_run,
                "pending": pending,
                "stopped_on": {k: inflight.get(k) for k in ("name", "appid", "root")},
                "log": str(log_path),
            }

        path, current = _load_verify_queue()
        finished = _finish_verify_inflight(path, current)
        completed_this_run.append(finished)
        ok(f"Steam verification completed: {finished['name']}")

@serialized_mutation
def batch_deep_clean(
    games: list[Game],
    drive: Path,
    assume_yes: bool = False,
    include_nonsteam: bool = False,
    auto_verify: bool = False,
) -> None:
    print_games(games, "clean")
    raw = "ALL" if assume_yes else ask("Deep Clean codes, range, or ALL")
    selected = parse_selection(raw, games, "clean")

    plans: list[tuple[Game, list[DeepCleanCandidate]]] = []
    heading("DEEP CLEAN preview")
    warn("DEStructive mode: removed graphics-mod payloads are NOT backed up.")
    warn("NVIDIA/Streamline runtime DLLs are preserved for DLSS Updater compatibility.")
    nonsteam = [g for g in selected if not g.appid]
    if nonsteam:
        warn(f"{len(nonsteam)} Non-Steam game(s) have no automatic authoritative repair source.")

    total_files = 0
    total_bytes = 0
    for game in selected:
        candidates = deep_clean_scan_game(game)
        plans.append((game, candidates))
        total_files += len(candidates)
        total_bytes += sum(c.size for c in candidates)
        print(f"  {game.code:<5} {game.name[:42]:<42} remove={len(candidates):<4} {human_size(sum(c.size for c in candidates))}")
        for c in candidates[:8]:
            try:
                rel = c.path.relative_to(game.root)
            except ValueError:
                rel = c.path
            print("       " + dim(f"{c.kind:<7} {rel} · {c.reason}"))
        if len(candidates) > 8:
            print("       " + dim(f"… {len(candidates) - 8} more"))

    kv("Candidates", total_files)
    kv("Estimated removal", human_size(total_bytes))
    kv("Payload backups", "NONE (thin receipt only)")

    if not total_files:
        ok("No known graphics-mod debris found in the selected games.")
    if not assume_yes:
        phrase = ask('Type CLEAN to delete these artifacts', '')
        if phrase != "CLEAN":
            print("  Cancelled.")
            return
        if nonsteam:
            phrase = ask('Non-Steam repair is manual. Type NONSTEAM to include them', '')
            include_nonsteam = phrase == "NONSTEAM"
    if nonsteam and not include_nonsteam:
        warn("Non-Steam games excluded from this run.")
        selected_ids = {id(g) for g in nonsteam}
        plans = [(g, c) for g, c in plans if id(g) not in selected_ids]

    # Restore exact rtxEngine-owned Steam metadata while state still exists.
    managed = [g for g, _ in plans if g.target_dir and baseline_path(g.target_dir).is_file()]
    if managed:
        try:
            restore_launch_options_batch(managed, assume_yes=assume_yes)
        except Exception as exc:
            raise Stop(f"Deep Clean stopped before file deletion because LaunchOptions restore failed: {exc}") from exc

    # After exact rtxEngine-owned metadata restoration, remove any remaining
    # stale proxy overrides only for proxy DLLs positively scheduled for this
    # destructive cleanup. Unrelated wrappers/arguments are preserved.
    try:
        scrubbed_launch = scrub_deep_clean_launch_options_batch(plans, assume_yes=assume_yes)
        if scrubbed_launch:
            kv("LaunchOptions scrubbed", len(scrubbed_launch))
    except Exception as exc:
        raise Stop(f"Deep Clean stopped before file deletion because stale LaunchOptions scrub failed: {exc}") from exc

    results = []
    cleaned_games = []
    # Every selected Steam game must already have a durable repair intent before
    # the FIRST destructive write. A hard power loss cannot run our exception
    # handler; committing the queue after deletion would allow a partially
    # cleaned Steam game to survive with only an in-progress receipt and no
    # repair scheduled. An unnecessary verify is safe; missing a required one is
    # not.
    steam_verify_games = [game for game, _candidates in plans if game.appid]
    queue = save_verify_queue(steam_verify_games)
    for i, (game, candidates) in enumerate(plans, 1):
        print(f"  [{i:>2}/{len(plans):<2}] {game.name[:48]:<48}", end=" ")
        try:
            row = deep_clean_apply_game(game, candidates)
            print(green("✓"))
            results.append(row)
            cleaned_games.append(game)
        except Exception as exc:
            print(red("FAILED"))
            results.append({"game": game.name, "status": "failed", "target": str(game.root), "error": str(exc)})

    report = write_batch_report("deep-clean", results, drive)
    heading("Deep Clean complete")
    kv("Cleaned", sum(r["status"] == "cleaned" for r in results))
    kv("Failed", sum(r["status"] == "failed" for r in results))
    kv("Report", report)

    # Steam Support explicitly warns against validating multiple games at once.
    # The repair queue was committed before destructive work; now consume it one
    # validation at a time. Existing active queues are extended rather than
    # overwritten.
    if queue and steam_verify_games:
        run_auto = auto_verify
        if not assume_yes and not auto_verify:
            run_auto = confirm("Run Steam verifications sequentially now?", True)
        if run_auto:
            try:
                summary = run_steam_verify_queue_sequential()
                kv("Steam verifies completed", len(summary.get("completed", [])))
                kv("Steam verifies pending", summary.get("pending", 0))
            except Exception as exc:
                warn(f"Automatic verification queue stopped safely: {exc}")
                warn("No additional Steam validation was started; queue state was preserved.")
        else:
            row = start_next_steam_verify()
            ok(f"Requested Steam verification: {row['name']} ({row['appid']})")
            remaining = len(steam_verify_games) - 1
            if remaining:
                kv("Verify queue", f"{remaining} remaining · use menu option 7 or 8")
                kv("Queue file", queue)
    if any(not g.appid for g in cleaned_games):
        warn("Non-Steam games were cleaned but cannot be automatically restored/verified. Keep installer/original files.")


# Exact Steam Pristine Reset -------------------------------------------------

def _validate_pristine_steam_game(game: Game) -> tuple[Path, Path, dict]:
    """Prove that a Steam game root belongs to its exact appmanifest.

    Pristine Reset intentionally deletes every child of the install directory,
    so this validation is stricter than ordinary discovery. The root must be a
    direct, non-symlink child of that manifest's steamapps/common directory and
    the manifest AppID/install-dir must match the selected Game object.
    """
    require(bool(game.appid), f"Pristine Reset is Steam-only: {game.name}")
    require(game.manifest is not None, f"Steam appmanifest missing for {game.name}")
    manifest = Path(game.manifest).expanduser()
    require(manifest.is_file() and not manifest.is_symlink(), f"Unsafe/missing Steam appmanifest: {manifest}")
    data = parse_appmanifest(manifest)
    require(data is not None, f"Could not parse Steam appmanifest: {manifest}")
    require(str(data.get("appid")) == str(game.appid), f"Steam AppID mismatch for {game.name}")

    raw_installdir = data.get("installdir")
    installdir = safe_steam_installdir(raw_installdir)
    require(installdir is not None, f"Unsafe/missing Steam installdir for {game.name}: {raw_installdir!r}")

    steamapps = manifest.parent
    require(steamapps.name.casefold() == "steamapps", f"Appmanifest is not under steamapps: {manifest}")
    common = steamapps / "common"
    require(common.is_dir(), f"Steam common directory missing: {common}")
    expected_lexical = common / installdir
    require(not expected_lexical.is_symlink(), f"Symlink Steam game root refused: {expected_lexical}")
    require(expected_lexical.is_dir(), f"Steam game root missing: {expected_lexical}")

    expected = expected_lexical.resolve()
    actual = game.root.resolve()
    require(actual == expected, f"Steam game root/appmanifest mismatch: {actual} != {expected}")
    require(expected.parent == common.resolve(), f"Steam game root is not a direct common/ child: {expected}")
    return expected, manifest.resolve(), data


def _pristine_tree_hazards(root: Path) -> list[str]:
    """Refuse filesystem boundaries/special nodes a recursive wipe must not cross."""
    hazards: list[str] = []
    root = root.resolve()
    try:
        if _path_is_mount(root):
            hazards.append(f"game root is a mount point: {root}")
    except OSError:
        hazards.append(f"could not classify game root mount status: {root}")

    for cur, dirnames, filenames in os.walk(root, followlinks=False):
        cp = Path(cur)
        safe_dirs = []
        for name in list(dirnames):
            p = cp / name
            if p.is_symlink():
                # os.walk(followlinks=False) should already avoid following it,
                # but pruning makes the boundary explicit.
                continue
            try:
                if _path_is_mount(p):
                    hazards.append(f"nested mount point: {p}")
                    continue
            except OSError:
                hazards.append(f"could not classify directory: {p}")
                continue
            safe_dirs.append(name)
        dirnames[:] = safe_dirs
        for name in filenames:
            p = cp / name
            try:
                mode = p.lstat().st_mode
            except OSError:
                hazards.append(f"could not stat filesystem entry: {p}")
                continue
            if stat.S_ISREG(mode) or stat.S_ISLNK(mode):
                continue
            hazards.append(f"special filesystem node: {p}")
    return hazards


def _proc_link_under_root(link: Path, root: Path) -> bool:
    try:
        raw = os.readlink(link)
        raw = raw.removesuffix(" (deleted)")
        Path(raw).resolve(strict=False).relative_to(root)
        return True
    except (OSError, PermissionError, ValueError):
        return False


def _process_references_root(proc_dir: Path, root: Path) -> Optional[str]:
    """Return why a process appears to be using files under ``root``.

    Proton/Wine processes commonly have an executable outside the game tree, so
    checking only /proc/PID/exe misses live games. CWD, command line, memory
    maps, and file descriptors provide conservative additional evidence.
    """
    if _proc_link_under_root(proc_dir / "exe", root):
        return "exe"
    if _proc_link_under_root(proc_dir / "cwd", root):
        return "cwd"

    root_s = root.as_posix().rstrip("/")
    needles = (root_s, root_s + "/")
    try:
        cmd = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace")
        normalized = cmd.replace("\\", "/")
        if any(needle in normalized for needle in needles):
            return "cmdline"
    except (OSError, PermissionError):
        pass

    try:
        maps = (proc_dir / "maps").read_text(encoding="utf-8", errors="replace")
        if any(needle in maps for needle in needles):
            return "maps"
    except (OSError, PermissionError):
        pass

    fd_dir = proc_dir / "fd"
    try:
        # A game can keep content open without mapping it. Cap the scan so one
        # pathological process cannot make a destructive preflight unbounded.
        for idx, fd in enumerate(fd_dir.iterdir()):
            if idx >= 512:
                break
            if _proc_link_under_root(fd, root):
                return "fd"
    except (OSError, PermissionError):
        pass
    return None


def _running_processes_under_root(root: Path) -> list[str]:
    """Return user-owned processes that appear to be using this game root."""
    out: list[str] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return out
    resolved_root = root.resolve()
    uid = os.getuid()
    for child in proc.iterdir():
        if not child.name.isdigit():
            continue
        try:
            if child.stat().st_uid != uid:
                continue
        except (OSError, PermissionError):
            continue
        reason = _process_references_root(child, resolved_root)
        if not reason:
            continue
        try:
            comm = (child / "comm").read_text(errors="ignore").strip()
        except (OSError, PermissionError):
            comm = "process"
        out.append(f"{child.name}:{comm or 'process'}[{reason}]")
    return out


def _ensure_steam_stopped_for_pristine(assume_yes: bool = False) -> None:
    if not steam_running():
        return
    if assume_yes:
        raise Stop("Steam is running. Pristine Reset refuses unattended deletion while Steam is open; close Steam and retry.")
    warn("Steam must be completely stopped before Pristine Reset deletes an install tree.")
    if confirm("Ask Steam to exit cleanly now?", True):
        steam_cmd = shutil.which("steam")
        if steam_cmd:
            try:
                subprocess.run(
                    [steam_cmd, "-shutdown"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
            except Exception:
                pass
        for _ in range(60):
            if not steam_running():
                ok("Steam exited")
                return
            time.sleep(0.5)
    require(not steam_running(), "Steam is still running; Pristine Reset cancelled before deletion.")


def _tree_inventory_thin(root: Path) -> dict:
    """Count install payload without retaining a huge per-file receipt.

    Never descend across a mount boundary while producing a destructive-mode
    preview. The actual delete path performs its own hazard recheck.
    """
    files = 0
    dirs = 0
    symlinks = 0
    total = 0
    for cur, dirnames, filenames in os.walk(root, followlinks=False):
        cp = Path(cur)
        safe_dirs = []
        for name in list(dirnames):
            p = cp / name
            if p.is_symlink():
                symlinks += 1
                continue
            try:
                if _path_is_mount(p):
                    continue
            except OSError:
                continue
            dirs += 1
            safe_dirs.append(name)
        dirnames[:] = safe_dirs
        for name in filenames:
            p = cp / name
            try:
                if p.is_symlink():
                    symlinks += 1
                else:
                    files += 1
                    total += p.stat().st_size
            except OSError:
                files += 1
    return {"files": files, "dirs": dirs, "symlinks": symlinks, "bytes": total}


def _pristine_receipt(game: Game, inventory: dict, *, status: str, error: Optional[str] = None,
                      removed_top_level: int = 0, state_dirs_purged: int = 0,
                      state_purge_error: Optional[str] = None) -> Path:
    root = _validated_state_namespace("pristine-reset-receipts")
    _mkdir_durable(root)
    receipt = root / f"steam-{game.appid}.json"
    save_json_atomic(receipt, {
        "schema": 1,
        "time_utc": now_iso(),
        "mode": "steam-pristine-reset-no-payload-backup",
        "game": game.name,
        "appid": str(game.appid),
        "root": str(game.root),
        "manifest": str(game.manifest) if game.manifest else None,
        "status": status,
        "error": error,
        "inventory_before": inventory,
        "removed_top_level": int(removed_top_level),
        "state_dirs_purged": int(state_dirs_purged),
        "state_purge_error": state_purge_error,
        "repair_source": "Steam file verification/redownload",
    })
    return receipt


def pristine_steam_reset_apply_game(game: Game) -> dict:
    """Delete the complete validated Steam install payload, leaving only the root.

    No payload backup is created. This is intentionally stronger than Deep
    Clean: even NVIDIA DLLs previously updated by DLSS Updater are removed and
    Steam is expected to redownload its own current depot payload afterward.
    """
    root, manifest, _data = _validate_pristine_steam_game(game)
    require(not steam_running(), "Steam restarted before Pristine Reset deletion; refusing to touch the install tree.")
    hazards = _pristine_tree_hazards(root)
    if hazards:
        raise Stop(f"Pristine Reset filesystem hazard for {game.name}: {hazards[0]}")
    running = _running_processes_under_root(root)
    require(not running, f"Game process still running under {root}: {', '.join(running[:5])}")
    inventory = _tree_inventory_thin(root)
    removed_top = 0
    mutation_attempted = False
    # Durable breadcrumb before destructive work. Batch mode already commits
    # the Steam repair queue first; this adds per-game crash visibility.
    _pristine_receipt(game, inventory, status="in-progress")
    _mark_game_rtxengine_state_destructive_pending(game, "pristine-reset")
    try:
        for child in list(root.iterdir()):
            # Once a destructive filesystem call begins, assume the managed
            # baseline no longer describes the live tree even if that call
            # later raises. shutil.rmtree can delete children before failing.
            mutation_attempted = True
            # Root identity was already proven. Never follow a top-level symlink.
            if child.is_symlink():
                durable_unlink(child)
            elif child.is_dir():
                # Re-check immediately before recursive deletion so a mount or
                # special node introduced after the root preflight cannot turn
                # into an accidental cross-filesystem wipe.
                child_hazards = _pristine_tree_hazards(child)
                require(
                    not child_hazards,
                    f"Pristine Reset filesystem hazard under {child}: {child_hazards[0] if child_hazards else 'unknown'}",
                )
                # Pristine mode deliberately does not broad-chown/chmod a game
                # tree. If normal deletion is blocked, fail visibly and let the
                # receipt + Steam repair queue describe the partial state.
                shutil.rmtree(child)
                _sync_filesystem(root)
            else:
                durable_unlink(child)
            removed_top += 1
        require(not any(root.iterdir()), f"Steam install root was not emptied completely: {root}")
        _sync_filesystem(root)
    except BaseException as exc:
        purged_states = 0
        purge_error = None
        if mutation_attempted:
            try:
                purged_states = _purge_game_rtxengine_state(game)
            except Exception as purge_exc:
                purge_error = str(purge_exc)
                warn(f"Pristine Reset could not fully retire stale rtxEngine state for {game.name}: {purge_exc}")
        receipt = _pristine_receipt(
            game, inventory, status="partial-failed", error=str(exc), removed_top_level=removed_top,
            state_dirs_purged=purged_states, state_purge_error=purge_error,
        )
        if isinstance(exc, Exception):
            raise Stop(f"{exc} · partial Pristine Reset receipt: {receipt}") from exc
        raise

    purged_states = 0
    purge_error = None
    try:
        purged_states = _purge_game_rtxengine_state(game)
    except Exception as purge_exc:
        purge_error = str(purge_exc)
        warn(f"Pristine Reset wiped {game.name}, but stale rtxEngine state could not be fully retired: {purge_exc}")
    receipt = _pristine_receipt(
        game, inventory, status="wiped-pending-steam-verify", removed_top_level=removed_top,
        state_dirs_purged=purged_states, state_purge_error=purge_error,
    )
    return {
        "game": game.name,
        "appid": str(game.appid),
        "status": "wiped",
        "target": str(root),
        "manifest": str(manifest),
        "removed_files": int(inventory.get("files") or 0),
        "removed_dirs": int(inventory.get("dirs") or 0),
        "removed_symlinks": int(inventory.get("symlinks") or 0),
        "removed_bytes": int(inventory.get("bytes") or 0),
        "state_dirs_purged": purged_states,
        "receipt": str(receipt),
    }


@serialized_mutation
def batch_pristine_steam_reset(
    games: list[Game],
    drive: Path,
    assume_yes: bool = False,
    auto_verify: bool = True,
) -> None:
    print_games(games, "pristine")
    raw = "ALL" if assume_yes else ask("Pristine Reset Steam codes, range, or ALL")
    selected = parse_selection(raw, games, "pristine")
    require(selected, "No Steam games selected for Pristine Reset")

    # Prove every root before touching Steam metadata or game files.
    previews = []
    heading("STEAM PRISTINE RESET preview")
    warn("EXTREME destructive mode: EVERY file inside each selected Steam install directory will be deleted.")
    warn("No payload backup is created. DLSS Updater replacements, in-folder configs, mods, screenshots, and in-folder saves are removed too.")
    warn("Steam verification/redownload is the authoritative repair source. Non-Steam games are not supported.")
    total_bytes = 0
    for game in selected:
        root, _manifest, _data = _validate_pristine_steam_game(game)
        hazards = _pristine_tree_hazards(root)
        if hazards:
            raise Stop(f"Pristine Reset filesystem hazard for {game.name}: {hazards[0]}")
        running = _running_processes_under_root(root)
        require(not running, f"Game process still running for {game.name}: {', '.join(running[:5])}")
        inventory = _tree_inventory_thin(root)
        previews.append((game, inventory))
        total_bytes += int(inventory.get("bytes") or 0)
        print(
            f"  {game.code:<5} {game.name[:42]:<42} "
            f"files={inventory['files']:<7} size={human_size(inventory['bytes'])}"
        )
    kv("Selected Steam games", len(selected))
    kv("Installed payload to delete", human_size(total_bytes))
    kv("Payload backups", "NONE")
    kv("Repair", "serialized Steam verify/redownload")

    if not assume_yes:
        phrase = ask('Type PRISTINE to wipe these Steam install directories', '')
        if phrase != "PRISTINE":
            print("  Cancelled.")
            return

    _ensure_steam_stopped_for_pristine(assume_yes=assume_yes)

    # Restore exact rtxEngine-owned LaunchOptions while its state still exists,
    # then scrub only positively identified graphics-proxy overrides. Unrelated
    # launch arguments remain untouched.
    managed = [g for g in selected if g.target_dir and baseline_path(g.target_dir).is_file()]
    if managed:
        try:
            restore_launch_options_batch(managed, assume_yes=assume_yes)
        except Exception as exc:
            raise Stop(f"Pristine Reset stopped before deletion because LaunchOptions restore failed: {exc}") from exc

    scrub_plans = []
    for game in selected:
        try:
            scrub_plans.append((game, deep_clean_scan_game(game)))
        except Exception as exc:
            raise Stop(f"Pristine Reset stopped before deletion because graphics override inventory failed for {game.name}: {exc}") from exc
    try:
        scrubbed = scrub_deep_clean_launch_options_batch(scrub_plans, assume_yes=assume_yes)
        if scrubbed:
            kv("LaunchOptions scrubbed", len(scrubbed))
    except Exception as exc:
        raise Stop(f"Pristine Reset stopped before deletion because LaunchOptions scrub failed: {exc}") from exc

    # Commit the repair queue BEFORE the first destructive file operation. If
    # rtxEngine/host crashes mid-wipe, the next run still knows every selected
    # AppID needs authoritative Steam repair. A false-positive verification is
    # harmless; an erased game with no repair record is not.
    verify_games = list(selected)
    queue = save_verify_queue(verify_games)
    require(queue is not None, "Could not persist Steam repair queue before Pristine Reset")

    results = []
    for i, game in enumerate(selected, 1):
        print(f"  [{i:>2}/{len(selected):<2}] {game.name[:48]:<48}", end=" ")
        try:
            row = pristine_steam_reset_apply_game(game)
            print(green("✓"))
            results.append(row)
        except Exception as exc:
            print(red("FAILED"))
            results.append({"game": game.name, "appid": str(game.appid), "status": "failed", "target": str(game.root), "error": str(exc)})

    report = write_batch_report("pristine-steam-reset", results, drive)
    heading("Pristine Reset deletion phase complete")
    kv("Wiped", sum(r.get("status") == "wiped" for r in results))
    kv("Failed/partial", sum(r.get("status") == "failed" for r in results))
    kv("Report", report)

    if queue and verify_games:
        if auto_verify:
            try:
                summary = run_steam_verify_queue_sequential()
                kv("Steam rebuilds completed", len(summary.get("completed", [])))
                kv("Steam rebuilds pending", summary.get("pending", 0))
            except Exception as exc:
                warn(f"Automatic Steam rebuild queue stopped safely: {exc}")
                warn("Queue state was preserved; no later validation was overlapped.")
        else:
            row = start_next_steam_verify()
            ok(f"Requested Steam rebuild/verification: {row['name']} ({row['appid']})")
            kv("Queue file", queue)


# Batch actions --------------------------------------------------------------

def resolve_family(override: Optional[str] = None) -> tuple[str, Optional[str]]:
    gpu = nvidia_gpu_name()
    family = override or gpu_family(gpu)
    require(
        family in {"ada", "sm86"},
        "Could not determine RTX generation. Use --gpu-family ada or --gpu-family sm86.",
    )
    return family, gpu

@serialized_mutation
def batch_install(
    games: list[Game],
    drive: Path,
    archive: Path,
    family_override: Optional[str] = None,
    assume_yes: bool = False,
    nr_runtime_explicit: Optional[str] = None,
) -> None:
    base_payload, archive_meta = load_archive_payload(archive)
    family, gpu = resolve_family(family_override)

    # Handoff 188 has one active OptiScaler provider: y4my v4. Legacy
    # RTXMFG/v3e loaders remain only for interpreting/restoring old state. The
    # separate DLSSNR model runtime is resolved once per batch and never turns
    # into an alternate MFG provider/path.
    nr_runtime_payload, nr_runtime_meta = load_user_nr_runtime(
        nr_runtime_explicit, family=family
    )

    print_games(games, "install")
    raw = "ALL" if assume_yes else ask("Install codes, range, NEW, or ALL")
    selected = parse_selection(raw, games, "install")

    heading("Batch preview")
    kv("Selected games", len(selected))
    kv("Archive", archive_meta["name"])
    kv("GPU", gpu or family)
    kv("MFG route", "y4my v4 native Ada MFG · startup disabled · enable per-title" if family == "ada" else "NR-only on sm86")
    kv("Reversible", "Yes · baseline per game")
    kv("NR", "installed/armed · startup disabled · enable per-title in overlay")
    kv("NR runtime", nr_runtime_meta.get("provider") or nr_runtime_meta.get("path") if nr_runtime_meta else "per-game existing copy")
    kv("Controls", "OptiScaler panel: Alt+Insert / Insert")
    kv("Launch options", "Written to Steam after install when approved")

    if not assume_yes and not confirm(f"Install to {len(selected)} game(s)?"):
        print("  Cancelled.")
        return

    results = []
    for i, game in enumerate(selected, 1):
        print(f"  [{i:>2}/{len(selected):<2}] {game.name[:48]:<48}", end=" ")
        try:
            record = install_target(
                game, base_payload, archive_meta, family,
                ada_mfg_mode="integrated",
                nr_runtime_payload=nr_runtime_payload,
                nr_runtime_meta=nr_runtime_meta,
            )
            print(green("✓"))
            results.append({
                "game": game.name,
                "status": "installed",
                "target": str(game.target_dir),
                "proxy": record["proxy"],
                "mfg_proxy": (
                    (record.get("mfg_provider") or {}).get("shared_proxy")
                    or (record.get("mfg_provider") or {}).get("proxy")
                ),
                "mfg_provider": record.get("mfg_provider"),
                "nr_profile": record.get("nr_profile"),
                "launch_options": record["launch_options"],
                "permission_repairs": record.get("permission_repairs", []),
            })
        except Exception as e:
            print(red("FAILED"))
            results.append({
                "game": game.name,
                "status": "failed",
                "target": str(game.target_dir or game.root),
                "error": str(e),
            })

    report = write_batch_report("install", results, drive, archive_meta)
    heading("Batch complete")
    kv("Succeeded", sum(r["status"] == "installed" for r in results))
    kv("Failed", sum(r["status"] == "failed" for r in results))
    kv("Report", report)

    successful_games = [
        game for game, row in zip(selected, results)
        if row.get("status") == "installed"
    ]
    if successful_games:
        sync_launch_options_batch(
            successful_games,
            assume_yes=assume_yes,
            prompt=not assume_yes,
        )

@serialized_mutation
def batch_uninstall(
    games: list[Game],
    drive: Path,
    assume_yes: bool = False,
) -> None:
    print_games(games, "uninstall")
    raw = "ALL" if assume_yes else ask("Uninstall codes, range, or ALL")
    selected = parse_selection(raw, games, "uninstall")

    heading("Batch restore preview")
    kv("Selected games", len(selected))
    kv("Action", "Restore each game's pre-rtxEngine baseline")
    kv("Changed files", "Preserved to recovery-before-restore first")

    if not assume_yes and not confirm(f"Restore/uninstall {len(selected)} game(s)?"):
        print("  Cancelled.")
        return

    # Treat live-game detection as a batch preflight. No Steam metadata or game
    # files are touched until every selected root is confirmed inactive.
    for game in selected:
        running = _running_processes_under_root(game.root.resolve())
        require(not running, f"Game process still using {game.root}: {', '.join(running[:5])}")

    # The batch intent must be durable before Steam metadata changes. A crash
    # after LaunchOptions commits but before the first file restore must not
    # leave an rtxEngine stack labeled active even though its launch contract
    # has already been removed. Validate every recovery plan first, then mark
    # every selected baseline recovery-only before starting the Steam batch.
    prepared_restore_states = []
    for game in selected:
        require(game.target_dir is not None, f"Missing target for {game.name}")
        baseline = load_baseline(game.target_dir)
        require(baseline is not None, f"No rtxEngine install state: {game.name}")
        verify_baseline_integrity(game.target_dir, baseline, adopt_legacy=True)
        prepared_restore_states.append((game.target_dir, baseline))
    restore_batch_id = f"uninstall-{now_stamp()}-{os.getpid()}-{time.time_ns()}"
    for target, baseline in prepared_restore_states:
        _mark_restore_pending(target, baseline, batch_id=restore_batch_id)

    # Restore Steam metadata while the baseline records still exist.
    # This completes before ANY game files are removed. If it fails, abort the
    # uninstall with every rtxEngine game install still intact.
    try:
        restore_launch_options_batch(selected, assume_yes=assume_yes)
    except Exception as e:
        raise Stop(
            "LaunchOptions restore failed before uninstall began; no game files "
            f"were removed. {e}"
        ) from e

    results = []
    for i, game in enumerate(selected, 1):
        print(f"  [{i:>2}/{len(selected):<2}] {game.name[:48]:<48}", end=" ")
        try:
            restored = restore_target(game)
            print(green("✓"))
            results.append({
                "game": game.name,
                "status": "restored",
                "target": restored["target"],
            })
        except Exception as e:
            print(red("FAILED"))
            results.append({
                "game": game.name,
                "status": "failed",
                "target": str(game.target_dir or game.root),
                "error": str(e),
            })

    report = write_batch_report("uninstall", results, drive)
    heading("Batch complete")
    kv("Restored", sum(r["status"] == "restored" for r in results))
    kv("Failed", sum(r["status"] == "failed" for r in results))
    kv("Report", report)

@serialized_mutation
def batch_audit(
    games: list[Game],
    drive: Path,
    assume_yes: bool = False,
) -> None:
    print_games(games, "audit")
    raw = "ALL" if assume_yes else ask("Audit codes, range, or ALL")
    selected = parse_selection(raw, games, "audit")

    results = []
    heading("Audit")
    for i, game in enumerate(selected, 1):
        try:
            row = audit_target(game)
            row["status"] = "clean" if not row["missing"] and not row["changed"] else "drift"
            results.append(row)
            print(
                f"  [{i:>2}/{len(selected):<2}] "
                f"{game.name[:42]:<42} "
                f"missing={len(row['missing']):<3} changed={len(row['changed']):<3} "
                f"runtime={row.get('runtime_evidence', {}).get('status', 'n/a')}"
            )
        except Exception as e:
            results.append({
                "game": game.name,
                "status": "failed",
                "target": str(game.target_dir or game.root),
                "error": str(e),
            })

    report = write_batch_report("audit", results, drive)
    kv("Report", report)
    warn("Changed OptiScaler.ini is usually normal after saving settings in-game.")

# Interactive ---------------------------------------------------------------

def scan_for_install(drive: Path) -> list[Game]:
    games = discover_games(drive)
    require(games, "No games discovered on the drive")
    return games

def interactive_main(
    drive_override: Optional[str] = None,
    *,
    archive_override: Optional[str] = None,
    nr_runtime_explicit: Optional[str] = None,
    family_override: Optional[str] = None,
) -> int:
    drive = detect_drive(drive_override)
    cached_scan: Optional[list[Game]] = None

    while True:
        clear()
        banner()
        kv("Game drive", drive)
        default_archive = find_default_archive()
        kv(
            "y4my v4",
            default_archive.name if default_archive else "not cached · downloads automatically on install",
        )
        kv("RTX 40 MFG", "Native Ada MFG · unified y4my v4 stack")
        orphan_count = orphan_state_count_under_drive(drive)
        if orphan_count:
            kv("Legacy state", f"{orphan_count} stale baseline backup(s) · auto-recover on install")
        print()
        kv("1", "Scan G: + install/update multiple games")
        kv("2", "Uninstall/restore multiple installed games")
        kv("3", "Audit multiple installed games")
        kv("4", "Rescan G:")
        kv("5", "Sync launch options into Steam")
        kv("6", "Deep Clean graphics mods + start Steam verification")
        kv("7", "Request next Steam verify from queue")
        kv("8", "Run Steam verify queue sequentially")
        kv("9", "Recover interrupted Steam metadata transaction")
        kv("10", "Pristine Steam Reset (wipe full install + rebuild from Steam)")
        kv("11", "Retry current failed/unconfirmed Steam verification")
        kv("0", "Exit")
        print()

        choice = ask("Choose", "1")
        try:
            if choice == "0":
                return 0

            if choice in {"1", "4"}:
                cached_scan = scan_for_install(drive)
                if choice == "4":
                    print_games(cached_scan, "install")
                else:
                    archive = choose_archive(archive_override)
                    batch_install(
                        cached_scan, drive, archive,
                        family_override=family_override,
                        nr_runtime_explicit=nr_runtime_explicit,
                    )

            elif choice == "2":
                installed = load_installed_states_under_drive(drive)
                require(installed, "No active rtxEngine-managed DLSS Unlocked installs on G:")
                batch_uninstall(installed, drive)

            elif choice == "3":
                installed = load_installed_states_under_drive(drive)
                require(installed, "No active rtxEngine-managed DLSS Unlocked installs on G:")
                batch_audit(installed, drive)

            elif choice == "5":
                installed = load_installed_states_under_drive(drive)
                active = [g for g in installed if g.reason == "INSTALLED"]
                require(active, "No active rtxEngine-managed DLSS Unlocked installs on G:")
                sync_launch_options_batch(active, assume_yes=False, prompt=True)

            elif choice == "6":
                cached_scan = scan_for_install(drive)
                batch_deep_clean(cached_scan, drive, assume_yes=False)

            elif choice == "7":
                row = start_next_steam_verify()
                ok(f"Requested Steam verification: {row['name']} ({row['appid']})")

            elif choice == "8":
                summary = run_steam_verify_queue_sequential()
                kv("Steam verifies completed", len(summary.get("completed", [])))
                kv("Steam verifies pending", summary.get("pending", 0))

            elif choice == "9":
                recovered = recover_pending_steam_transactions(assume_yes=False)
                kv("Transactions recovered", len(recovered))

            elif choice == "10":
                cached_scan = scan_for_install(drive)
                batch_pristine_steam_reset(cached_scan, drive, assume_yes=False, auto_verify=True)

            elif choice == "11":
                row = retry_failed_steam_verify()
                ok(f"Retried Steam verification: {row['name']} ({row['appid']})")

            else:
                warn("Unknown menu choice")

        except Stop as e:
            fail(str(e))
        except KeyboardInterrupt:
            print("\n  Cancelled.")
        except Exception as e:
            fail(f"Unexpected error: {e}")

        print()
        input("  Press ENTER to return to rtxEngine…")

def cli_main(argv=None) -> int:
    p = argparse.ArgumentParser(description="rtxEngine Terminal Edition v13")
    actions = p.add_mutually_exclusive_group()
    actions.add_argument("--scan", action="store_true")
    actions.add_argument("--install-all", action="store_true")
    actions.add_argument("--uninstall-all", action="store_true")
    actions.add_argument("--audit-all", action="store_true")
    actions.add_argument("--sync-launch-options", action="store_true")
    actions.add_argument("--deep-clean-all", action="store_true", help="destructively remove known graphics-mod debris; no payload backup")
    actions.add_argument("--pristine-steam-all", action="store_true", help="EXTREME: wipe every discovered Steam install directory and rebuild through Steam verification")
    actions.add_argument("--verify-next", action="store_true", help="request the next queued Steam file verification")
    actions.add_argument("--verify-queue-auto", action="store_true", help="run queued Steam verifications sequentially")
    actions.add_argument("--verify-retry-failed", action="store_true", help="relaunch only the current AppID after explicit failure or an unconfirmed launch-intent")
    actions.add_argument("--recover-steam-transactions", action="store_true", help="roll back interrupted Steam LaunchOptions transactions")
    p.add_argument("--include-nonsteam", action="store_true", help="allow destructive Deep Clean on Non-Steam games")
    p.add_argument("--confirm-pristine", action="store_true", help="required with --pristine-steam-all; acknowledges full Steam install deletion/redownload")
    verify_behavior = p.add_mutually_exclusive_group()
    verify_behavior.add_argument(
        "--auto-verify", action="store_true",
        help="after Deep Clean/Pristine Reset, sequentially verify every selected Steam game (default for destructive CLI actions)",
    )
    verify_behavior.add_argument(
        "--no-auto-verify", action="store_true",
        help="after Deep Clean/Pristine Reset, retain/start the serialized Steam verify queue instead of waiting through it",
    )
    p.add_argument("--drive", help="mounted Windows G: root; defaults to /var/mnt/Games")
    p.add_argument("--archive", help="pinned y4my v4 with-DLSS .7z archive (auto-downloads if omitted)")
    p.add_argument("--nr-runtime", help="strict user-supplied nvngx_dlssnr.dll override; otherwise use local copy or the SHA-pinned family runtime")
    p.add_argument("--gpu-family", choices=("ada", "sm86"))
    args = p.parse_args(argv)

    try:
        drive = detect_drive(args.drive)

        if args.scan:
            games = scan_for_install(drive)
            print_games(games, "install")
            return 0

        if args.install_all:
            games = scan_for_install(drive)
            batch_install(
                games,
                drive,
                choose_archive(args.archive),
                family_override=args.gpu_family,
                assume_yes=True,
                nr_runtime_explicit=args.nr_runtime,
            )
            return 0

        if args.uninstall_all:
            games = load_installed_states_under_drive(drive)
            require(games, "No active installs on G:")
            batch_uninstall(games, drive, assume_yes=True)
            return 0

        if args.audit_all:
            games = load_installed_states_under_drive(drive)
            require(games, "No active installs on G:")
            batch_audit(games, drive, assume_yes=True)
            return 0

        if args.sync_launch_options:
            games = load_installed_states_under_drive(drive)
            active = [g for g in games if g.reason == "INSTALLED"]
            require(active, "No active installs on G:")
            sync_launch_options_batch(active, assume_yes=False, prompt=True)
            return 0

        if args.deep_clean_all:
            games = scan_for_install(drive)
            batch_deep_clean(
                games, drive, assume_yes=True,
                include_nonsteam=args.include_nonsteam,
                auto_verify=not args.no_auto_verify,
            )
            return 0

        if args.pristine_steam_all:
            require(
                args.confirm_pristine,
                "--pristine-steam-all deletes EVERY file inside every selected Steam install. "
                "Re-run with --confirm-pristine only if that full redownload is intended.",
            )
            games = scan_for_install(drive)
            batch_pristine_steam_reset(
                games, drive, assume_yes=True, auto_verify=not args.no_auto_verify,
            )
            return 0

        if args.verify_next:
            row = start_next_steam_verify()
            ok(f"Requested Steam verification: {row['name']} ({row['appid']})")
            return 0

        if args.verify_queue_auto:
            summary = run_steam_verify_queue_sequential()
            kv("Steam verifies completed", len(summary.get("completed", [])))
            kv("Steam verifies pending", summary.get("pending", 0))
            return 0

        if args.verify_retry_failed:
            row = retry_failed_steam_verify()
            ok(f"Retried Steam verification: {row['name']} ({row['appid']})")
            return 0

        if args.recover_steam_transactions:
            recovered = recover_pending_steam_transactions(assume_yes=True)
            kv("Transactions recovered", len(recovered))
            return 0

        return interactive_main(
            args.drive,
            archive_override=args.archive,
            nr_runtime_explicit=args.nr_runtime,
            family_override=args.gpu_family,
        )

    except Stop as e:
        fail(str(e))
        return 2
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130

if __name__ == "__main__":
    raise SystemExit(cli_main())
