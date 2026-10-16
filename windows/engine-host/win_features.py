"""rtxForge for Windows: the engine features beyond install / restore / update.

The same scripts/ modules the Linux GTK app calls (steam_artwork,
artwork_overrides, steamgrid_client, runtime_diagnostics, runtime_updates,
game_notes, extra_tools, package_catalog, desktop_service recoveries), with
the Windows adapters they need:

  os.open        O_NOFOLLOW / O_NONBLOCK do not exist on Windows; linked files
                 are refused explicitly and every descriptor is binary
  credentials    SteamGridDB key in Windows Credential Manager (never settings)
  images         dimensions read from PNG / JPEG / WebP headers (no GdkPixbuf);
                 the app converts WebP to PNG before storing it
  packages       the catalog's support rule accepts 64-bit Windows
  updates        GitHub releases tagged windows-v<VERSION> (Inno Setup installer)

Every write is reviewed first: a review is kept here by token and `run`
executes exactly that review once.
"""
from __future__ import annotations

import copy
import ctypes
import errno
import hashlib
import json
import os
import platform
import re
import stat
import struct
import threading
import urllib.request
import uuid
from pathlib import Path

import transactions as t

# ---------- os.open: POSIX flags the engine passes ----------

_NOFOLLOW = 0x40000000  # above every MSVCRT O_ flag


def _windows_open(path, flags, mode=0o777, *, dir_fd=None):
    if flags & _NOFOLLOW:
        flags &= ~_NOFOLLOW
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:  # reparse point
            raise OSError(errno.ELOOP, "Linked file refused", str(path))
    flags |= getattr(os, "O_BINARY", 0)  # text-mode descriptors would translate CRLF and stop at ^Z
    return _real_open(path, flags, mode) if dir_fd is None else _real_open(path, flags, mode, dir_fd=dir_fd)


_real_open = os.open
if not hasattr(os, "O_NOFOLLOW"):
    os.O_NOFOLLOW = _NOFOLLOW
    os.O_NONBLOCK = 0
    os.open = _windows_open

import artwork_overrides  # noqa: E402
import desktop_service  # noqa: E402
import engine_bridge  # noqa: E402
import extra_tools  # noqa: E402
import game_notes  # noqa: E402
import library_media  # noqa: E402
import package_catalog  # noqa: E402
import runtime_diagnostics  # noqa: E402
import runtime_updates  # noqa: E402
import sl_override  # noqa: E402
import steam_artwork  # noqa: E402
import steamgrid_client  # noqa: E402
import steamgrid_credentials  # noqa: E402
import ui  # noqa: E402

# ---------- SteamGridDB key: Windows Credential Manager ----------

CREDENTIAL_TARGET = os.environ.get("RTXFORGE_CREDENTIAL_TARGET") or "rtxForge/SteamGridDB"


class _FILETIME(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", ctypes.c_uint32), ("Type", ctypes.c_uint32), ("TargetName", ctypes.c_wchar_p),
                ("Comment", ctypes.c_wchar_p), ("LastWritten", _FILETIME), ("CredentialBlobSize", ctypes.c_uint32),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", ctypes.c_uint32),
                ("AttributeCount", ctypes.c_uint32), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", ctypes.c_wchar_p), ("UserName", ctypes.c_wchar_p)]


def _advapi():
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredReadW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
    api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), ctypes.c_uint32]
    api.CredDeleteW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
    api.CredFree.argtypes = [ctypes.c_void_p]
    return api


_GENERIC, _PERSIST_LOCAL_MACHINE, _NOT_FOUND = 1, 2, 1168
_WALLET_ERROR = "Could not access Windows Credential Manager. Sign in to Windows normally, then try again."


def _credential_invoke(method, *args, cancel=None):
    """steamgrid_credentials._invoke for Windows: lookup, store and clear one generic credential."""
    try:
        api = _advapi()
    except (OSError, AttributeError):
        raise steamgrid_credentials.CredentialError(_WALLET_ERROR) from None
    if method == "password_lookup_sync":
        found = ctypes.POINTER(_CREDENTIAL)()
        if not api.CredReadW(CREDENTIAL_TARGET, _GENERIC, 0, ctypes.byref(found)):
            if ctypes.get_last_error() == _NOT_FOUND:
                return None
            raise steamgrid_credentials.CredentialError(_WALLET_ERROR)
        try:
            item = found.contents
            return bytes(item.CredentialBlob[:item.CredentialBlobSize]).decode("utf-8")
        finally:
            api.CredFree(found)
    if method == "password_store_sync":
        _collection, label, key = args
        blob = key.encode("utf-8")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = _CREDENTIAL(Type=_GENERIC, TargetName=CREDENTIAL_TARGET, Comment=label,
                                 CredentialBlobSize=len(blob), CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
                                 Persist=_PERSIST_LOCAL_MACHINE, UserName="steamgriddb")
        if not api.CredWriteW(ctypes.byref(credential), 0):
            raise steamgrid_credentials.CredentialError(_WALLET_ERROR)
        return True
    if method == "password_clear_sync":
        if not api.CredDeleteW(CREDENTIAL_TARGET, _GENERIC, 0) and ctypes.get_last_error() != _NOT_FOUND:
            raise steamgrid_credentials.CredentialError(_WALLET_ERROR)
        return True
    raise steamgrid_credentials.CredentialError(_WALLET_ERROR)


steamgrid_credentials._invoke = _credential_invoke

# ---------- image dimensions (artwork_overrides.dimensions without GdkPixbuf) ----------


def image_dimensions(data: bytes) -> tuple[int, int]:
    width = height = 0
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
    elif data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
                i += 1 if marker == 0xFF else 2
                continue
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                break
            i += 2 + length
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            width, height = (struct.unpack("<H", data[26:28])[0] & 0x3FFF, struct.unpack("<H", data[28:30])[0] & 0x3FFF)
        elif chunk == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        elif chunk == b"VP8X":
            width, height = int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    else:
        raise ValueError("Choose a PNG, JPEG, or WebP image.")
    if width <= 0 or height <= 0:
        raise ValueError("This image could not be read. Choose another PNG or JPEG image.")
    if width * height > 40_000_000:
        raise ValueError("Choose an image smaller than 40 megapixels.")
    return width, height


artwork_overrides.dimensions = image_dimensions

# ---------- package catalog: 64-bit Windows is a supported host ----------

_catalog = package_catalog.catalog


def _windows_catalog(host=None):
    host = dict(host or {"system": platform.system(), "architecture": platform.machine(), "ready": False})
    if host.get("system") == "Windows":
        host["system"] = "Linux"  # the rule is "x86-64 and a ready NVIDIA host"; Windows loads the same DLLs natively
    return _catalog(host)


package_catalog.catalog = _windows_catalog

# ---------- shared state ----------

ROOT = Path(os.environ.get("RTXFORGE_ROOT") or Path(__file__).resolve().parents[2])
LOCAL = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "rtxForge"
service: desktop_service.DesktopService = None  # set by install()
_steam_engine = None
_settings_lock = threading.RLock()
_reviews: dict[str, dict] = {}
_packages: dict[str, dict] = {}


def install(desktop: desktop_service.DesktopService, steam_engine) -> dict:
    """Binds the host's service and Steam-config engine; returns the request methods."""
    global service, _steam_engine
    service, _steam_engine = desktop, steam_engine
    return dict(METHODS)


def _config():
    return service.config


def _settings() -> dict:
    return library_media.load_settings(_config())


def _review(kind: str, title: str, items: list, *, blocked=(), summary="", action="Apply", trust=None, note=None, payload=None) -> dict:
    """A review the app shows as-is; `run` executes the stored payload once."""
    token = uuid.uuid4().hex
    _reviews[token] = {"kind": kind, "payload": payload}
    return {"token": token, "kind": kind, "title": title, "summary": summary, "action": action,
            "items": list(items), "blocked": list(blocked), "trust": trust, "note": note}


def _item(title, detail="", badge="", game=None, details=None) -> dict:
    return {"title": str(title), "detail": str(detail), "badge": badge, "game": game, "details": details}


def run(params):
    review = _reviews.pop(params["token"], None)
    t.need(review is not None, "This review has expired. Review the changes again.")
    return RUNNERS[review["kind"]](review["payload"])


def discard(params):
    _reviews.pop(params.get("token", ""), None)
    _packages.pop(params.get("token", ""), None)
    return {}


# ---------- library rows: custom artwork and test records ----------


def decorate(rows: list[dict]) -> list[dict]:
    """Scan rows as Linux shows them: your chosen artwork over Steam's, and the saved test record."""
    settings = _settings()
    for row in rows:
        row["art"] = artwork_overrides.apply(settings, row, row.get("art") or {})
        row["test_record"] = game_notes.load(_config(), row["game"])
    return rows


def media(params):
    """LibraryMedia.enrich per game (Settings › Refresh artwork; cached for offline use)."""
    settings = {**_settings(), **{k: v for k, v in (params.get("settings") or {}).items()
                                  if k in ("online_art", "steam_metadata", "network_timeout")}}
    library = library_media.LibraryMedia(_config(), settings)
    rows, out = params.get("rows") or [], []
    for index, row in enumerate(rows):
        ui.progress(f"Updating artwork · {row.get('name', '')}", current=index + 1, total=len(rows))
        try:
            metadata = dict(row, appid=row['metadata_appid']) if row.get('metadata_appid') else row
            data = library.enrich(metadata, bool(params.get("refresh")))
        except Exception as error:  # one game's artwork never stops the rest
            data = {"media_note": str(error)}
        keep = ("poster", "capsule", "hero", "art_credit", "capsule_credit", "hero_credit", "description",
                "developers", "release", "metadata_source", "media_note")
        out.append({"game": row["game"], **{k: data[k] for k in keep if data.get(k)}})
    return out


# ---------- Steam artwork profile ----------


def art_profiles(_params):
    selected = _settings().get("steam_artwork_profile") or {}
    rows = steam_artwork.profiles(_config(), engine=_steam_engine())
    return [{"root": p["root"], "userid": p["userid"],
             "selected": p["root"] == selected.get("root") and p["userid"] == str(selected.get("userid"))} for p in rows]


def art_set_profile(params):
    matches = [p for p in steam_artwork.profiles(_config(), engine=_steam_engine())
               if p["root"] == params.get("root") and p["userid"] == str(params.get("userid"))]
    t.need(len(matches) == 1, "That Steam profile is no longer available. Open Steam once, then choose again.")
    with _settings_lock:
        settings = _settings()
        settings["steam_artwork_profile"] = {"root": matches[0]["root"], "userid": matches[0]["userid"]}
        library_media.save_settings(_config(), settings)
    return {}


# ---------- custom artwork: stored in rtxForge, synced to Steam after review ----------


def art_store(params):
    row, role = params["row"], params["role"]
    path = t.safe(Path(params["path"]))
    t.need(path.is_file(), "Choose a regular image file.")
    with path.open("rb") as stream:
        data = stream.read(artwork_overrides.MAX_BYTES + 1)
    t.need(not (data[:4] == b"RIFF" and data[8:12] == b"WEBP"), "Convert this WebP image to PNG first.")
    with _settings_lock:
        settings = _settings()
        stored = artwork_overrides.store(_config(), settings, row, role, data, credit=params.get("credit") or "Your artwork",
                                         link=params.get("link") or "", validate=image_dimensions)
    return {"path": stored}


def art_reset(params):
    with _settings_lock:
        artwork_overrides.reset(_config(), _settings(), params["row"], params["role"])
    return {}


ROLE_TITLES = {"poster": "Poster", "capsule": "Wide capsule", "hero": "Hero", "logo": "Logo"}


def _steam_paths() -> list[Path]:
    return [Path(r).resolve() for r in _steam_engine().steam_roots_for_config()]


def _plan_artwork(settings, row, refresh, engine, steam_roots):
    grid, appid = steam_artwork.target(_config(), settings, row, engine=engine)
    selected = dict(settings.get("game_artwork", {}).get(row["game"], {}))
    pending = settings.get("steam_artwork_pending", {}).get(row["game"], {})
    if not refresh:
        # Linux include_displayed: artwork rtxForge shows (downloaded media). Steam's own
        # cache and grid files are already what Steam shows, so they are not copied back.
        for role, value in (row.get("displayed") or {}).items():
            path = Path(value) if value else None
            if role in steam_artwork.SUFFIX and role not in selected and path and path.is_file() \
                    and not any(path.resolve().is_relative_to(r) for r in steam_roots):
                selected[role] = {"path": str(path)}
    roles = []
    for role, suffix in steam_artwork.SUFFIX.items():
        before = steam_artwork.slot_hashes(grid, appid, role)
        if pending.get(role) == "reset":
            roles.append({"role": role, "action": "reset", "before": before, "status": "reset"})
        elif role in selected:
            path = t.safe(Path(selected[role]["path"]))
            t.need(path.stat().st_size <= steam_artwork.MAX_BYTES, "Artwork exceeds the safe Steam sync size.")
            data = path.read_bytes()
            desired = {appid + suffix + steam_artwork.image_extension(data): hashlib.sha256(data).hexdigest()}
            status = "unchanged" if before == desired else "replace" if before else "add"
            if status != "unchanged":
                roles.append({"role": role, "action": "set", "path": str(path), "sha256": desired.popitem()[1],
                              "before": before, "status": status})
    return {"game": row["game"], "name": row.get("name", ""), "grid": str(grid), "appid": appid, "roles": roles}


def art_sync_review(params):
    settings = _settings()
    engine = _steam_engine()
    refresh = bool(params.get("refresh"))
    rows = params.get("rows") or []
    if not params.get("single"):
        rows = [r for r in rows if settings.get("game_artwork", {}).get(r["game"]) or settings.get("steam_artwork_pending", {}).get(r["game"])
                or any(r.get("displayed", {}).get(role) for role in steam_artwork.SUFFIX)]
    roots = _steam_paths()
    plans, items, blocked = [], [], []
    words = {"add": "add", "replace": "replace (backed up)", "reset": "restore your original Steam image"}
    for row in rows:
        try:
            plan = _plan_artwork(settings, row, refresh, engine, roots)
        except Exception as error:
            blocked.append(_item(row.get("name", "Game"), desktop_service.friendly(str(error)), "Skipped", row["game"]))
            continue
        if plan["roles"]:
            plans.append(plan)
            items.append(_item(plan["name"], " · ".join(f"{ROLE_TITLES[r['role']]}: {words[r['status']]}" for r in plan["roles"]),
                               "Sync", plan["game"]))
        elif settings.get("steam_artwork_pending", {}).get(row["game"]):
            plans.append(plan)  # nothing to write; clears the pending marker
    profile = settings.get("steam_artwork_profile")
    account = f"Steam account {profile['userid']}" if profile else "The signed-in Steam account"
    return _review("art-sync", "Sync artwork to Steam", items, blocked=blocked, action="Sync artwork",
                   summary=f"{account} · only grid artwork changes. Replaced images are backed up; Reset restores them.",
                   note="Restart Steam if its cached images have not refreshed.", payload=plans)


def _run_art_sync(plans):
    images, errors, done = 0, [], []
    for plan in plans:
        try:
            for role in plan["roles"]:
                if role["action"] == "reset":
                    result = steam_artwork.write_slot(_config(), plan["grid"], plan["appid"], role["role"], reset=True,
                                                      expected_before=role["before"])
                else:
                    data = t.safe(Path(role["path"])).read_bytes()
                    t.need(hashlib.sha256(data).hexdigest() == role["sha256"], "Artwork changed since your review. Review it again.")
                    result = steam_artwork.write_slot(_config(), plan["grid"], plan["appid"], role["role"], data,
                                                      expected_before=role["before"])
                images += bool(result.get("changed"))
            done.append(plan["game"])
        except Exception as error:
            errors.append(plan["name"] + ": " + desktop_service.friendly(str(error)))
    with _settings_lock:
        settings = _settings()
        for game in done:
            settings.setdefault("steam_artwork_pending", {}).pop(game, None)
        library_media.save_settings(_config(), settings)
    message = (f"{images} Steam image{'s' if images != 1 else ''} updated. Restart Steam if its cached images have not refreshed."
               if not errors else f"{images} Steam images updated. Some artwork still needs syncing.")
    return {"message": message, "errors": errors}


# ---------- SteamGridDB ----------


def sgdb_status(_params):
    try:
        connected, problem = bool(steamgrid_credentials.load_key()), None
    except steamgrid_credentials.CredentialError as error:
        connected, problem = False, str(error)
    return {"connected": connected, "problem": problem, "styles": steamgrid_client.STYLES,
            "dimensions": steamgrid_client.DIMENSIONS, "mimes": steamgrid_client.MIMES}


def sgdb_connect(params):
    key = steamgrid_credentials.normalize_key(params.get("key"))
    steamgrid_client.Client(key).validate()
    steamgrid_credentials.save_key(key)
    return {}


def sgdb_disconnect(_params):
    return {"external": steamgrid_credentials.clear_key()}


def sgdb_search(params):
    return [{"id": m.get("id"), "name": m.get("name", "Unknown game")} for m in steamgrid_client.Client().search(params.get("term", ""))]


def sgdb_artwork(params):
    assets = steamgrid_client.Client().artwork(
        params["game_id"], params["role"], page=int(params.get("page", 0)), style=params.get("style") or "",
        dimensions=params.get("dimensions") or "", mime=params.get("mime") or "", humor=bool(params.get("humor")))
    keep = ("id", "url", "thumb", "width", "height", "mime", "style")
    return [{**{k: a.get(k) for k in keep}, "author": (a.get("author") or {}).get("name") or "Community artist"}
            for a in assets if isinstance(a, dict) and a.get("url")]


def sgdb_download(params):
    """Full-size image into rtxForge's preview cache (the API key never follows CDN requests)."""
    asset = params["asset"]
    data = steamgrid_client.Client.download({"url": asset["url"]})
    width, height = image_dimensions(data)
    extension = ".png" if data.startswith(b"\x89PNG") else ".jpg" if data.startswith(b"\xff\xd8") else ".webp"
    folder = LOCAL / "state" / "desktop" / "steamgrid-preview"
    path = folder / (hashlib.sha256(data).hexdigest() + extension)
    t.atomic_file(path, data, 0o600)
    return {"path": str(path), "width": width, "height": height}


# ---------- Diagnose NR ----------


def provider_name(provider_id) -> str:
    try:
        return json.loads((ROOT / "providers" / "lock.json").read_text())[provider_id]["name"]
    except (OSError, ValueError, KeyError, TypeError):
        return "the installed provider"


def streamline_override(row, *, provider=None, payload=None) -> dict:
    """sl_override.check for a scan row (read only)."""
    root = Path(row["game"])
    relative = Path(row.get("exe", ""))
    t.need(not relative.is_absolute() and ".." not in relative.parts, "Unsafe executable path")
    return sl_override.check(root / relative.parent, root, payload=payload,
                             provider=provider or provider_name(row.get("runtime_provider") or "y4my"))


def diagnose(params):
    report = runtime_diagnostics.inspect(params["row"])
    try:
        override = streamline_override(params["row"])
    except (OSError, ValueError, t.Refusal) as error:
        override = {"warning": None, "notes": ["DLSS Override check unavailable: " + type(error).__name__]}
    report["streamline_override"] = override
    report["warnings"] = [override["warning"]] if override.get("warning") else []
    report["observations"] = override.get("notes", []) + report["observations"]
    return report


# ---------- DLSS files ----------


def dlss_inventory(params):
    row = params["row"]
    found = runtime_updates.inspect(_config(), [row])[0]
    backups = runtime_updates.game_recoveries(_config(), row["game"])
    files = [{**f, "title": runtime_updates.COMPONENTS.get(f["component"], f["component"])} for f in found["files"]]
    return {"files": files, "blocked": found["blocked"], "backups": backups}


def dlss_restore_review(params):
    row = params["row"]
    records = runtime_updates.game_recoveries(_config(), row["game"])
    t.need(records, "No DLSS file backups for this game")
    state = records[0]["path"]
    view = runtime_updates.restore(_config(), state, False)
    items = [_item(path, "Restore the previous copy", "Restore", row["game"]) for path in view["files"]]
    return _review("dlss-restore", "Restore original DLSS files", items, action="Restore",
                   summary=f"{row.get('name', '')} · update from {records[0]['date']}. Close the game first.",
                   payload={"state": state, "game": row["game"]})


def _run_dlss_restore(payload):
    runtime_updates.restore(_config(), payload["state"], True)
    return {"message": "Original DLSS files restored."}


# ---------- Notes and test records ----------


def notes_save(params):
    record = game_notes.load(_config(), params["game"])
    record.update(status=params.get("status") or record.get("status", "Untested"), notes=str(params.get("notes", "")))
    game_notes.save(_config(), params["game"], record)
    return record


def test_start(params):
    return game_notes.start(_config(), params["row"])


def test_finish(params):
    return game_notes.finish(_config(), params["row"])


def report_preview(params):
    files = game_notes.preview(_config(), params.get("rows") or [], bool(params.get("logs")), bool(params.get("notes")))
    items = [_item(name, "Review the exact report contents", "Report", details=text) for name, text in files.items()]
    return _review("report", "Review Support Report", items, action="Export this preview",
                   summary="Review the exact text below. Redaction is best effort. Export saves this preview locally; nothing is submitted.",
                   payload=files)


def _run_report(files):
    path = game_notes.export_preview(_config(), files)
    return {"message": f"Saved {path}", "path": str(path)}


# ---------- Recovery: previous changes and old NR files ----------


def recoveries(_params):
    return service.recoveries()


def recovery_review(params):
    review = service.review_recovery(params["record"])
    items = [_item(r["name"], r["detail"], "Backup") for r in review["rows"]]
    return _review("service", review["title"], items, action="Restore", payload=review,
                   summary="Only files rtxForge recorded are restored. Changed files are refused.")


def cleanup_review(_params):
    review = service.review_cleanup()
    items = [_item(r["name"], r["detail"], "Remove") for r in review["rows"]]
    return _review("service", "Remove old NR files", items, action="Back up and remove", payload=review,
                   summary="Every file is copied to a verified recovery record before the first one is removed.")


def _run_service(review):
    return {"message": "Done.", "report": service.execute(review)}


# ---------- Extras: ReShade and add-ons ----------


def extras_list(params):
    return [{**r, "title": extra_tools.KINDS[r["kind"]]} for r in extra_tools.recoveries(_config(), params["row"])]


def extra_review(params):
    plan = extra_tools.prepare(_config(), params["row"], params["path"], params["kind"])
    kind = extra_tools.KINDS[plan["kind"]]
    changes = "\n".join("Add " + c["path"] + "\nSHA-256: " + c["after"] for c in plan["changes"])
    return _review("extra", "Review " + kind, [_item(plan["name"], "Add " + kind, "Install", plan["game"], changes)],
                   action="Install Tool", trust="I trust the source of this exact file", payload=plan,
                   note="This native code will run inside the game. The hash identifies the selected file; it does not establish its publisher or safety.")


def _run_extra(plan):
    extra_tools.apply(_config(), plan)
    return {"message": "Tool installed. Recovery is available in Tools."}


def extra_restore_review(params):
    records = [r for r in extra_tools.recoveries(_config()) if r["path"] == params.get("path")]
    t.need(len(records) == 1, "This tool recovery record is no longer available.")
    record = records[0]
    item = _item(record["name"], "Restore this tool’s original files", "Restore",
                 details="Changed files will be refused. Game saves and other tools are preserved.")
    return _review("extra-restore", "Restore Tool", [item], action="Restore", payload=record["path"])


def _run_extra_restore(path):
    extra_tools.restore(_config(), path)
    return {"message": "Tool restored."}


# ---------- Packages ----------


def packages(_params):
    host = service.hardware()
    settings = _settings()
    custom = settings.get("custom_package") or None
    return {"host": host, "catalog": package_catalog.catalog(host), "community": package_catalog.community_sources(),
            "custom": {"name": custom.get("name"), "sha256": custom.get("sha256")} if isinstance(custom, dict) else None}


def package_inspect(params):
    result = package_catalog.inspect_archive(params["path"])
    token = uuid.uuid4().hex
    _packages[token] = result
    return {"token": token, "name": result["name"], "family": result["family"], "confidence": result["confidence"],
            "file_count": len(result["files"]), "expanded_bytes": result["expanded_bytes"], "sha256": result["sha256"],
            "parameters": result["parameters"], "warnings": result["warnings"],
            "instructions": [{"path": i["path"], "text": i["text"][:4000]} for i in result["instructions"][:8]],
            "deployable": result["family"] == "dlss-unlocked"}


def package_use(params):
    inspection = _packages.get(params["token"])
    t.need(inspection is not None, "Inspect the package again.")
    record = package_catalog.custom_record(inspection, params.get("values") or {}, trusted=params.get("trusted") is True,
                                           review_notes=params.get("notes") or "")
    _packages.pop(params["token"], None)
    parsed = record["parameters"]
    count = parsed.get("OverrideInterpolationCount", "auto")
    with _settings_lock:
        settings = _settings()
        settings["custom_package"] = record
        settings["runtime_provider"] = "custom"
        library_media.save_settings(_config(), settings)
    return {"name": record["name"], "nr_strength": float(parsed.get("Intensity", 2.0)),
            "sharpening_strength": float(parsed.get("Sharpness", 0.5)),
            "mfg_multiplier": "auto" if count == "auto" else "0" if count == "0" else str(int(count) + 1)}


# ---------- Application updates: GitHub releases windows-v<VERSION> ----------

RELEASES = "https://api.github.com/repos/lrnolivia/rtxForge/releases?per_page=50"
DOWNLOAD_PREFIX = "https://github.com/lrnolivia/rtxForge/releases/download/"


def _version_key(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)*)(?:-rc\.(\d+))?", str(value).strip().lstrip("v"))
    t.need(match, f"Invalid application version: {value}")
    core = tuple(int(p) for p in match[1].split("."))
    core += (0,) * max(0, 3 - len(core))
    return core, (0, int(match[2])) if match[2] is not None else (1, 0)


def _get(url, limit=4 * 1024**2):
    request = urllib.request.Request(url, headers={"User-Agent": "rtxForge-Windows-Updater/1", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(limit + 1)
    t.need(len(data) <= limit, "Update response is too large.")
    return data


def update_check(params):
    current = str(params.get("version") or (ROOT / "VERSION").read_text(encoding="utf-8")).strip()
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    best = None
    for release in json.loads(_get(RELEASES)):
        tag = str(release.get("tag_name", ""))
        if release.get("draft") or not tag.startswith("windows-v"):
            continue
        try:
            key = _version_key(tag.removeprefix("windows-v"))
        except t.Refusal:
            continue
        if best is None or key > best[0]:
            best = (key, release)
    current_key = _version_key(current) if current != "dev" else ((0, 0, 0), (0, 0))
    if best is None or best[0] <= current_key:
        return _review("update", "rtxForge is up to date", [], summary=f"rtxForge {current} is up to date.", action="Install update")
    release = best[1]
    version = release["tag_name"].removeprefix("windows-v")
    assets = {a["name"]: a for a in release.get("assets", [])}
    name = f"rtxForge-Setup-{version}-{arch}.exe"
    setup, digest = assets.get(name), assets.get(name + ".sha256")
    t.need(setup and digest, f"The rtxForge {version} release has no verified {arch} installer yet.")
    for asset in (setup, digest):
        t.need(str(asset["browser_download_url"]).startswith(DOWNLOAD_PREFIX), "Refusing an unexpected update download address.")
    sha = re.search(r"\b[0-9a-fA-F]{64}\b", _get(digest["browser_download_url"], 4096).decode("ascii", "replace"))
    t.need(sha, "The update checksum file is invalid.")
    size = int(setup["size"])
    items = [_item("Installed", current), _item("Available", f"{version} · {release.get('published_at', '')[:10]}", "New"),
             _item("Download", f"{name} · {size / 1024**2:.1f} MB · SHA-256 {sha[0][:12]}… checked after download")]
    return _review("update", f"rtxForge {version}", items, action="Download and install",
                   summary="A newer rtxForge for Windows build is ready. The installer opens after the download is verified; rtxForge closes so it can update.",
                   note="The installer is not code-signed. Windows SmartScreen may ask you to confirm (More info › Run anyway).",
                   payload={"url": setup["browser_download_url"], "name": name, "size": size, "sha256": sha[0].lower(), "version": version})


def _run_update(info):
    folder = LOCAL / "updates"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / info["name"]
    stage = folder / (info["name"] + "." + uuid.uuid4().hex + ".part")
    digest, received = hashlib.sha256(), 0
    try:
        request = urllib.request.Request(info["url"], headers={"User-Agent": "rtxForge-Windows-Updater/1"})
        with urllib.request.urlopen(request, timeout=60) as response, stage.open("xb") as out:
            while block := response.read(1024 * 1024):
                received += len(block)
                t.need(received <= info["size"], "The update download is larger than the release says.")
                digest.update(block)
                out.write(block)
                ui.progress(f"Downloading · {received / 1024**2:.1f} / {info['size'] / 1024**2:.1f} MB",
                            fraction=received / info["size"])
        t.need(received == info["size"], "The update download size does not match the release.")
        t.need(digest.hexdigest() == info["sha256"], "Update checksum verification failed. Nothing was installed.")
        os.replace(stage, target)
    finally:
        stage.unlink(missing_ok=True)
    return {"message": f"rtxForge {info['version']} downloaded and verified.", "path": str(target)}


RUNNERS = {"art-sync": _run_art_sync, "dlss-restore": _run_dlss_restore, "report": _run_report, "service": _run_service,
           "extra": _run_extra, "extra-restore": _run_extra_restore, "update": _run_update}

METHODS = {
    "run": run, "discard": discard, "media": media,
    "art_profiles": art_profiles, "art_set_profile": art_set_profile, "art_store": art_store, "art_reset": art_reset,
    "art_sync_review": art_sync_review,
    "sgdb_status": sgdb_status, "sgdb_connect": sgdb_connect, "sgdb_disconnect": sgdb_disconnect,
    "sgdb_search": sgdb_search, "sgdb_artwork": sgdb_artwork, "sgdb_download": sgdb_download,
    "diagnose": diagnose, "dlss_inventory": dlss_inventory, "dlss_restore_review": dlss_restore_review,
    "notes_save": notes_save, "test_start": test_start, "test_finish": test_finish, "report_preview": report_preview,
    "recoveries": recoveries, "recovery_review": recovery_review, "cleanup_review": cleanup_review,
    "extras_list": extras_list, "extra_review": extra_review, "extra_restore_review": extra_restore_review,
    "packages": packages, "package_inspect": package_inspect, "package_use": package_use,
    "update_check": update_check,
}
