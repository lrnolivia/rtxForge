"""NVIDIA App "DLSS Override" check: which Streamline a game really loads.

With DLSS Override – Frame Generation on, Streamline loads the NVIDIA App's
OTA plugins from %ProgramData%\\NVIDIA\\NGX\\models\\sl_*_override_0 and ignores
the game's own sl.*.dll as duplicates. The installed provider ships its own
Streamline under OptiScaler\\streamline; a newer OTA set replaces it and MFG
can crash inside sl_dlss_g_override.

Read only: the game's OptiScaler.log, PE version resources, folder listings.
Nothing here loads a DLL or changes NVIDIA profiles or ProgramData files.
"""
from __future__ import annotations

import os
import re
import stat
import struct
from pathlib import Path

ADVICE = ("Turn off DLSS Override – Frame Generation for this game in "
          "NVIDIA App → Graphics → Program Settings.")
_PLUGINS = ("sl.dlss_g.dll", "sl.interposer.dll", "sl.common.dll")
_FIXED_INFO = struct.pack("<I", 0xFEEF04BD)  # VS_FIXEDFILEINFO signature
_MAX_DLL = 128 * 1024 * 1024
_MAX_LOG = 4 * 1024 * 1024


def models_root() -> Path:
    if os.environ.get("RTXFORGE_NGX_MODELS"):
        return Path(os.environ["RTXFORGE_NGX_MODELS"])
    return Path(os.environ.get("ProgramData") or r"C:\ProgramData") / "NVIDIA" / "NGX" / "models"


def version_key(text: str | None) -> tuple:
    return tuple(int(p) for p in re.findall(r"\d+", text or "")[:4])


def short(text: str | None) -> str:
    """2.14.16.0 and 2.14.16.98614dad6 both read as 2.14.16."""
    parts = re.findall(r"\d+", text or "")[:3]
    return ".".join(parts)


def _read(path: Path, limit: int, tail=False) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Not a regular file")
        if tail:
            source.seek(max(0, info.st_size - limit))
        return source.read(limit)


def pe_version(data: bytes) -> str | None:
    """FileVersion from VS_FIXEDFILEINFO, found in the bytes (no LoadLibrary)."""
    if data[:2] != b"MZ":
        return None
    at = data.rfind(_FIXED_INFO)
    if at < 0 or at + 16 > len(data):
        return None
    ms, ls = struct.unpack_from("<II", data, at + 8)
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def file_version(path: Path) -> str | None:
    try:
        return pe_version(_read(path, _MAX_DLL))
    except (OSError, ValueError):
        return None


def provider_streamline(directory: Path, payload: dict | None = None) -> str | None:
    """Streamline version the installed (or reviewed) provider ships."""
    for name in _PLUGINS:
        if payload is not None:
            data = payload.get("OptiScaler/streamline/" + name)
            if isinstance(data, (bytes, bytearray)):
                found = pe_version(data)
            else:  # a large provider file the engine keeps on disk (FileBlob)
                found = file_version(data.path) if isinstance(getattr(data, "path", None), Path) else None
        else:
            found = file_version(directory / "OptiScaler" / "streamline" / name)
        if found:
            return short(found)
    return None


def override_plugins(root: Path | None = None) -> list[dict]:
    """Newest downloaded version per sl_*_override_0 feature, by PE FileVersion."""
    root = root or models_root()
    found = []
    try:
        features = sorted(p for p in root.iterdir() if re.fullmatch(r"sl_.+_override_0", p.name, re.I))
    except OSError:
        return []
    for feature in features:
        best = None
        try:
            for dll in (feature / "versions").glob("*/files/*.dll"):
                version = file_version(dll)
                if version and (best is None or version_key(version) > version_key(best["version"])):
                    best = {"feature": feature.name, "version": short(version), "path": str(dll)}
        except OSError:
            continue
        if best:
            found.append(best)
    return found


def newest_log(directory: Path, root: Path | None = None) -> Path | None:
    """The game's most recent OptiScaler.log (beside the exe first, else below the game folder)."""
    candidates = [directory / "OptiScaler.log"]
    if root is not None:
        for depth in ("*", "*/*", "*/*/*"):
            candidates += root.glob(depth + "/OptiScaler.log")
    best = None
    for path in candidates:
        try:
            info = os.stat(path)
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode) and (best is None or info.st_mtime > best[0]):
            best = (info.st_mtime, path)
    return best[1] if best else None


def parse_log(text: str) -> dict:
    """Streamline's own log lines, from the last OptiScaler run only."""
    starts = list(re.finditer(r"^.*OptiScaler v[^\n]+loaded.*$", text, re.M))
    if starts:
        text = text[starts[-1].start():]
    drs = re.findall(r"Read SL_DLSS_OVERRIDE DRS key[^:\n]*:\s*(\d+)", text)
    loaded = {m[0]: short(m[1]) for m in re.findall(r"Loaded plugin '([^']+)' - version (\S+)", text)}
    ignored = [{"line": m.group(0).strip()[-240:], "version": short(m.group(1))}
               for m in re.finditer(r"^.*Ignoring plugin.*?duplicate of already[- ]loaded.*?v(\d+(?:\.\d+)+).*$", text, re.M | re.I)]
    return {
        "drs_override": drs[-1] != "0" if drs else None,
        "features": sorted(set(re.findall(r"using override feature name: (\S+_override_0)", text))),
        "aborted": bool(re.search(r"Not all override plugins available|OTA'd plugins will not be loaded", text)),
        "manifest": {k: short(v) for k, v in re.findall(r"OTA feature (\S+_override_0) version (\S+)", text)},
        "loaded": loaded,
        "ignored": ignored,
        "host_sdk": short((re.findall(r"host SDK v(\S+)", text) or [""])[-1]) or None,
    }


def _newest(versions) -> str | None:
    versions = [v for v in versions if v]
    return max(versions, key=version_key) if versions else None


def check(directory: Path, root: Path | None = None, *, provider="the installed provider",
          payload: dict | None = None, models: Path | None = None) -> dict:
    """{'warning', 'notes', ...evidence}. A warning only when evidence shows a version mismatch."""
    verified = provider_streamline(directory, payload)
    plugins = override_plugins(models)
    result = {"provider_streamline": verified, "override_plugins": plugins, "log": None,
              "loading": None, "warning": None, "notes": []}
    log_path = newest_log(directory, root)
    if log_path:
        try:
            result["log"] = {"path": str(log_path), **parse_log(_read(log_path, _MAX_LOG, tail=True).decode("utf-8", "replace"))}
        except (OSError, ValueError):
            pass
    log = result["log"]
    downloaded = _newest(p["version"] for p in plugins)
    if log and ((log["features"] and not log["aborted"]) or log["ignored"]):
        # Override plugins were loaded: they are what the game runs, whatever its own files say.
        loading = _newest([i["version"] for i in log["ignored"]] + list(log["loaded"].values())) or _newest(log["manifest"].values())
        result["loading"] = loading
        if verified and loading and version_key(loading) != version_key(verified):
            result["warning"] = (f"NVIDIA App's DLSS Override is loading Streamline {loading} for this game; "
                                 f"{provider} was verified with {verified}. {ADVICE}")
        elif not verified:
            result["notes"].append(f"NVIDIA App's DLSS Override is loading Streamline {loading or 'override plugins'} for this game "
                                   "instead of the game's own Streamline files.")
    elif log and log["features"] and log["aborted"]:
        offered = _newest(log["manifest"].values())
        result["notes"].append("NVIDIA App's DLSS Override is on, but its Streamline plugins were incomplete on the last run, "
                               f"so the game used its own Streamline{' ' + verified if verified else ''}. "
                               f"If NVIDIA App downloads them again{' (Streamline ' + offered + ')' if offered else ''} "
                               f"they will replace it. {ADVICE}")
    elif verified and downloaded and version_key(downloaded) > version_key(verified) and (not log or log["drs_override"]):
        # No run evidence yet (or none since the override was set): a heads-up, not a finding.
        result["warning"] = (f"NVIDIA App has downloaded Streamline {downloaded} override plugins. If DLSS Override – Frame Generation "
                             f"is on for this game, they replace the Streamline {verified} that {provider} was verified with "
                             f"and Frame Generation may crash. {ADVICE}")
    return result
