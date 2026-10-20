"""rtxForge Windows engine host.

Runs the shared rtxForge engine (engine/rtxengine.py through
scripts/desktop_service.py and scripts/engine_bridge.py) unchanged, and
supplies the Windows adapters it needs:

  storage      state under %LOCALAPPDATA%\\rtxForge instead of ~/.local/state
  fcntl        the writer lock via msvcrt byte-range locking
  discovery    Steam roots from the registry and the default install folders
  hardware     nvidia-smi from the NVIDIA driver; RTX 40-series rule kept
  launch       no Proton launch options: Windows loads OptiScaler's proxy DLL
               from the game folder natively, so Steam's config is untouched
  processes    running-game check through the Windows process list

Protocol: one JSON object per line on stdin ({"id", "method", "params"}); one
JSON object per line on stdout. Replies carry "id" with "result" or "error";
progress lines carry "event": "progress" and the request id. A prepared review
stays in this process (it holds the verified payload) and is executed by token,
so the files written are exactly the ones the user reviewed.
"""
from __future__ import annotations

import io
import configparser
import json
import os
import subprocess
import sys
import threading
import traceback
import types
import uuid
from pathlib import Path

ROOT = Path(os.environ.get("RTXFORGE_ROOT") or Path(__file__).resolve().parents[2])
LOCAL = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "rtxForge"
STATE = LOCAL / "state"

# Engine state (baselines, backups, transactions) lives beside the app's settings.
os.environ.setdefault("RTXFORGE_STATE_ROOT", str(STATE))
os.environ.setdefault("RTXFORGE_DLSS_UNLOCKED_STATE", str(LOCAL / "engine-state"))
os.environ["NO_COLOR"] = "1"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(1, str(Path(__file__).resolve().parent))  # win_features (-I leaves out the script's folder)

# Replies own stdout; anything the engine prints goes to stderr instead.
_out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n", write_through=True)
sys.stdout = sys.stderr
_write_lock = threading.Lock()
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def send(message: dict) -> None:
    with _write_lock:
        _out.write(json.dumps(message, default=str) + "\n")


# ---------- POSIX shims the engine imports ----------

def _install_fcntl() -> None:
    import msvcrt

    module = types.ModuleType("fcntl")
    module.LOCK_SH, module.LOCK_EX, module.LOCK_NB, module.LOCK_UN = 1, 2, 4, 8

    def flock(fd, operation: int) -> None:
        # fcntl.flock accepts a descriptor or any object with fileno() (steam_artwork passes the file).
        fd = fd if isinstance(fd, int) else fd.fileno()
        os.lseek(fd, 0, os.SEEK_SET)
        if operation & module.LOCK_UN:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            return
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK if operation & module.LOCK_NB else msvcrt.LK_LOCK, 1)
        except OSError as exc:
            raise BlockingIOError(str(exc)) from exc

    module.flock = flock
    sys.modules["fcntl"] = module


_install_fcntl()
for _name in ("getuid", "getgid", "geteuid"):
    if not hasattr(os, _name):
        setattr(os, _name, lambda: 0)


# ---------- storage: %LOCALAPPDATA%\rtxForge\state ----------

import transactions as t  # noqa: E402
import storage as storage_module  # noqa: E402


def windows_storage(config, required=0):
    root = Path(os.environ["RTXFORGE_STATE_ROOT"])
    t.need(root.is_absolute(), "rtxForge state root must be absolute")
    root.mkdir(parents=True, exist_ok=True)
    reserve = int((config.get("storage") or {}).get("reserve_bytes", 2 * 1024**3))
    import shutil
    t.need(shutil.disk_usage(root).free >= reserve + required, "Insufficient free space for rtxForge state and recovery data")
    return root


storage_module.storage = windows_storage

# ---------- Steam discovery ----------

import discovery  # noqa: E402


def windows_steam_roots() -> list[Path]:
    # Development and tests: an explicit list of Steam folders replaces discovery entirely.
    if os.environ.get("RTXFORGE_STEAM_ROOTS"):
        return [Path(p) for p in os.environ["RTXFORGE_STEAM_ROOTS"].split(os.pathsep) if p and Path(p).is_dir()]
    found: list[Path] = []
    try:
        import winreg
        for hive, key, value in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    found.append(Path(winreg.QueryValueEx(handle, value)[0]))
            except OSError:
                pass
    except ImportError:
        pass
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            found.append(Path(base) / "Steam")
    out, seen = [], set()
    for path in found:
        key = str(path).casefold()
        if path.is_dir() and key not in seen:
            seen.add(key)
            out.append(path)
    return out


discovery.steam_roots = windows_steam_roots
discovery.MOUNT_FALLBACKS = []

# ---------- hardware ----------

import hardware  # noqa: E402


def windows_hardware() -> dict:
    import platform
    import re
    info = {"system": "Windows", "architecture": platform.machine(), "gpu": "Not detected", "driver": "Unknown",
            "vram": "Unknown", "cpu": _cpu_name() or platform.processor() or "Unknown", "ready": False, "reason": ""}
    if info["architecture"].lower() not in ("amd64", "x86_64"):
        info["reason"] = "This package requires 64-bit x86 Windows."
        return info
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"],
                                text=True, capture_output=True, timeout=10, check=True, creationflags=NO_WINDOW)
        rows = [line.split(",") for line in result.stdout.strip().splitlines() if line.count(",") >= 2]
        supported = [r for r in rows if re.search(r"RTX\s+40\d{2}", r[0])]
        chosen = (supported or rows)[0]
        info.update({"gpu": chosen[0].strip(), "driver": chosen[1].strip(), "vram": chosen[2].strip() + " MiB"})
        if not supported:
            info["reason"] = "This native NVIDIA package targets GeForce RTX 40-series GPUs. This GPU is not validated."
            return info
    except (OSError, subprocess.SubprocessError, IndexError):
        info["reason"] = "Cannot verify an NVIDIA GPU and working NVIDIA driver. Install is unavailable; restore remains available."
        return info
    info["ready"] = True
    info["reason"] = "Basic hardware and dependencies passed. Per-game compatibility still requires verification."
    return info


def _cpu_name() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except OSError:
        return ""


hardware.detect = windows_hardware

# ---------- engine adapters ----------

import engine_bridge  # noqa: E402
import ui  # noqa: E402
import desktop_service  # noqa: E402

import library_media  # noqa: E402

# Modules that bound `from storage import storage` before the patch above.
for _module in list(sys.modules.values()):
    if getattr(_module, "storage", None) is not None and getattr(_module, "storage") is not windows_storage \
            and callable(getattr(_module, "storage")) and getattr(getattr(_module, "storage"), "__module__", "") == "storage":
        _module.storage = windows_storage

_NO_SHORTCUT = LOCAL / "engine-state" / "windows-native-launch"


def _running_under(root: Path) -> list[str]:
    """Fresh native inventory; no PowerShell process per check or stale cache."""
    import win_processes
    return win_processes.running_under(root)


def _running_snapshot():
    import win_processes
    return win_processes.snapshot()


_running_under.snapshot = _running_snapshot


def windows_steam_running() -> bool:
    """Steam's client process (steam.exe) in the Windows process list."""
    try:
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/FO", "CSV", "/NH"],
                                text=True, capture_output=True, timeout=10, creationflags=NO_WINDOW)
        return "steam.exe" in result.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return True  # unknown: refuse writes Steam could overwrite


def adapt_engine(e):
    """Windows-native loading: no Proton overrides, so Steam's config is never written."""
    # Steam's own folders (registry and default installs) instead of the Linux candidates.
    e.STEAM_ROOT_CANDIDATES = windows_steam_roots()
    # Add rtxForge to Steam uses the real account choice and a real running check.
    e.steam_config_engine = lambda: _steam_config_engine(e)
    e._windows_originals = {name: getattr(e, name) for name in
                            ("choose_steam_user_config", "parse_shortcuts_spans", "match_shortcut_span")}
    _NO_SHORTCUT.parent.mkdir(parents=True, exist_ok=True)
    if not _NO_SHORTCUT.exists():
        _NO_SHORTCUT.write_bytes(b"")
    e.build_launch_options = lambda *a, **kw: "Loads natively on Windows (no launch options)"
    e.steam_running = lambda: False
    # Installs never need a Steam shortcut on Windows: the review's shortcut
    # check is satisfied by a sentinel, while real shortcuts.vdf files (used to
    # find Non-Steam artwork) still parse and match normally.
    parse, match = e.parse_shortcuts_spans, e.match_shortcut_span
    sentinel = [{"windows-native": True}]
    e.choose_steam_user_config = lambda games, assume_yes=False: {"shortcuts": _NO_SHORTCUT}
    e.parse_shortcuts_spans = lambda data: sentinel if data == b"" else parse(data)
    e.match_shortcut_span = lambda game, spans: {"windows": True} if spans is sentinel else match(game, spans)
    e.sync_launch_options_batch = lambda games, assume_yes=False, prompt=False, **kw: [{"status": "written", "game": g.name} for g in games]
    e.restore_launch_options_batch = lambda games, assume_yes=False, **kw: []
    e._running_processes_under_root = _running_under
    e._archive_payload_cli = lambda archive: _extract_with_windows_tar(e, archive)
    e._fsync_file = lambda path: _fsync_file(e, path)
    # A game that fails part-way is put back by engine_bridge.execute (undo_game), as on Linux.
    return e


def _fsync_file(e, path: Path) -> None:
    """Windows flushes through a writable handle only (os.fsync on a read-only one is EBADF)."""
    e.require(path.is_file() and not path.is_symlink(), f"Cannot fsync unsafe file: {path}")
    try:
        fd = os.open(path, os.O_RDWR | os.O_BINARY)
    except PermissionError:
        return  # read-only files were written and closed already; nothing is pending
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _steam_config_engine(e):
    """The engine as Steam-configuration code needs it: real shortcuts parsing,
    the signed-in account, and a refusal while Steam is running."""
    for name, original in e._windows_originals.items():
        setattr(e, name, original)
    e.steam_running = windows_steam_running
    return e


def _extract_with_windows_tar(e, archive: Path) -> dict[str, bytes]:
    """The engine's CLI extraction with Windows' bundled bsdtar (System32\\tar.exe, libarchive + liblzma)."""
    import tempfile
    tool = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
    e.require(tool.is_file(), "Windows tar.exe (bsdtar) is not available to extract the y4my .7z provider")
    with tempfile.TemporaryDirectory(prefix="rtxengine-y4my-") as td:
        root = Path(td)
        proc = subprocess.run([str(tool), "-xf", str(archive), "-C", str(root)], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, creationflags=NO_WINDOW)
        e.require(proc.returncode == 0, f"Provider extraction failed: {proc.stdout[-1200:]}")
        payload: dict[str, bytes] = {}
        for current, dirs, files in os.walk(root, followlinks=False):
            base = Path(current)
            for d in dirs:
                e.require(not (base / d).is_symlink(), f"Provider archive symlink refused: {(base / d).relative_to(root)}")
            for name in files:
                p = base / name
                e.require(p.is_file() and not p.is_symlink(), f"Provider archive non-regular file refused: {p.relative_to(root)}")
                rel = e.safe_rel(p.relative_to(root).as_posix())
                e.require(rel.casefold() not in {x.casefold() for x in payload}, f"Case-colliding provider path: {rel}")
                payload[rel] = p.read_bytes()
        return payload


class _WindowsCopy:
    """operation_session's recovery copies use `cp -a --reflink=auto -- SRC DST`.
    Windows has no cp: copy the file or whole tree with timestamps (copy2),
    refusing links exactly as the session's signature() check does."""

    def __getattr__(self, name):
        return getattr(subprocess, name)

    @staticmethod
    def run(args, *a, **kw):
        if args and args[0] == "cp":
            import shutil
            src, dst = Path(args[-2]), Path(args[-1])
            if src.is_symlink():
                raise OSError(f"Linked recovery path refused: {src}")
            if src.is_dir():
                shutil.copytree(src, dst, symlinks=True, copy_function=shutil.copy2)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            return subprocess.CompletedProcess(args, 0)
        return subprocess.run(args, *a, **kw)


import operation_session  # noqa: E402

operation_session.subprocess = _WindowsCopy()

_module = engine_bridge.module


def windows_module(*args, **kwargs):
    return adapt_engine(_module(*args, **kwargs))


engine_bridge.module = windows_module

# ---------- requests ----------

service = desktop_service.DesktopService()
reviews: dict[str, dict] = {}


def hello(_params):
    return {"root": str(ROOT), "state": str(STATE), "python": sys.version.split()[0]}


def scan(params):
    import library_scan
    rows = library_scan.scan(service, params.get('folders', []), params.get('library_folders', []))
    import feeder_provider
    rows = feeder_provider.expand_rows(engine_bridge.module(service.config), rows,
                                      selected=params.get('runtime_provider') == 'feeder')
    import package_adoption
    package_adoption.decorate(engine_bridge.module(service.config), rows)
    if params.get('runtime_provider')=='skynizz':
        import skynizz_provider
        skynizz_provider.scan_rows(rows,params.get('feature_mode','nr-only'))
    # Linux LibraryMedia.steam_art: the signed-in account's custom grid
    # (Non-Steam games matched through shortcuts.vdf), then Steam's cache.
    media = library_media.LibraryMedia(service.config, dict(library_media.DEFAULTS))
    for row in rows:
        try:
            art_row = dict(row, appid=row['metadata_appid']) if row.get('metadata_appid') else row
            row["art"] = media.steam_art(art_row)
        except Exception:  # artwork is optional; never fail the scan for it
            traceback.print_exc()
    # Your chosen artwork over Steam's, and each game's saved notes (Linux details()).
    win_features.decorate(rows)
    import skynizz_provider
    import transactions
    for row in rows:
        if row.get('installed') and row.get('runtime_provider') == 'skynizz' and row.get('exe'):
            try: row['feature_controls'] = skynizz_provider.read_controls((Path(row['game']) / row['exe']).parent / 'OptiScaler.ini')
            except (OSError, ValueError, TypeError, configparser.Error, transactions.Refusal): pass
    return sorted(rows, key=lambda r: r["name"].casefold())


def prepare(params):
    if (params.get('settings') or {}).get('runtime_provider') == 'skynizz':
        import skynizz_provider
        # Presentation flags belong to the requested mode. Fresh engine game
        # inspection still owns all capability/ownership and anti-cheat checks.
        params = dict(params, rows=skynizz_provider.scan_rows([dict(row) for row in params['rows']], params['mode']))
    review = service.prepare(params["rows"], params["mode"], params["operation"],
                             visual_settings=params.get("settings"), save_defaults=params.get("save_defaults", False))
    if review.get("kind") == "engine":
        import dlss_updates
        settings = library_media.load_settings(service.config) | (params.get("settings") or {})
        dlss_updates.attach_install(service.config, review, enabled=settings.get('manage_dlss_files', True))
        import game_display
        game_display.attach(review, enabled=settings.get('borderless_4k', False))
        import review_copy
        review_copy.attach(review)
        review["cancel_event"] = threading.Event()
    elif review.get('kind') in ('feeder', 'adoption'):
        review['cancel_event'] = threading.Event()
    token = uuid.uuid4().hex
    reviews[token] = review
    return {"token": token, "title": review.get("title"), "rows": review.get("rows", []), "blocked": review.get("blocked", []),
            "warnings": _override_warnings(review)}


def _override_warnings(review) -> list[dict]:
    """NVIDIA App DLSS Override vs the reviewed provider's Streamline: warning rows, never blocks."""
    if review.get("operation") not in ("install", "repair") or not review.get("payload"):
        return []
    provider = review["engine"].Y4MY_PROVIDER.get("name") or "the provider"
    warnings = []
    for plan in review.get("plans", []):
        try:
            found = win_features.streamline_override(plan["row"], provider=provider, payload=review["payload"])
        except Exception:  # a heads-up only; never fail the review for it
            traceback.print_exc()
            continue
        if found.get("warning"):
            warnings.append({"name": plan["row"]["name"], "reason": found["warning"]})
    return warnings


def execute(params):
    review = reviews.pop(params["token"])
    return {"report": service.execute(review)}


def cancel(params):
    review = reviews.get(params["token"]) or running.get(params["token"])
    if review and review.get("cancel_event"):
        review["cancel_event"].set()
    return {}


def discard_operation(params):
    # Executing operations already own their payload outside these dictionaries.
    # Discarding a review can never cancel or alter an in-flight write.
    for token in params.get('tokens', []):
        reviews.pop(token, None)
        dlss_reviews.pop(token, None)
    return {}


def save_defaults(params):
    service.save_visual_defaults(params)
    return {}


def prepare_dlss(params):
    import dlss_updates
    review = dlss_updates.prepare(service.config, params['rows'])
    token = uuid.uuid4().hex
    dlss_reviews[token] = review
    return {key: value for key, value in review.items() if key != 'plans'} | {'token': token}


dlss_reviews: dict[str, dict] = {}


def update_dlss(params):
    """Linux manage_dlss_files: update older known native DLSS files; backups kept."""
    import runtime_updates
    if 'token' in params:
        import dlss_updates
        review = dlss_reviews.pop(params['token'], None)
        t.need(review is not None, 'DLSS review expired. Review the update again.')
        return dlss_updates.execute(service.config, review)
    if params.get("restore"):
        return {"restored": [str(runtime_updates.restore_game(service.config, row["game"])) for row in params["rows"]]}
    return runtime_updates.manage(service.config, params["rows"], replace_same=params.get("replace_same", False))


# ---------- Add rtxForge to Steam (steam_self_install, as on Linux) ----------

import steam_self_install  # noqa: E402

_append_shortcut = steam_self_install.append_shortcut


def _windows_shortcut(raw, entry, *, engine, name="rtxForge", icon=""):
    # Steam on Windows shows an .exe/.ico icon, not the SVG the Linux build uses;
    # rtxForge.exe carries the app icon.
    return _append_shortcut(raw, entry, engine=engine, name=name, icon=str(Path(entry).resolve()))


steam_self_install.append_shortcut = _windows_shortcut
steam_reviews: dict[str, dict] = {}


def _app_exe() -> Path:
    exe = Path(os.environ.get("RTXFORGE_APP_EXE") or ROOT.parent / "rtxForge.exe")
    t.need(exe.is_file() and exe.suffix.lower() == ".exe", "Install rtxForge before adding it to Steam.")
    return exe.resolve()


def _steam_kwargs() -> dict:
    return {"engine": engine_bridge.module(service.config).steam_config_engine(), "entry": _app_exe()}


def _steam_settings() -> dict:
    return library_media.load_settings(service.config)


def steam_status(_params):
    status = steam_self_install.shortcut_status(service.config, _steam_settings(), **_steam_kwargs())
    token = uuid.uuid4().hex
    steam_reviews[token] = status
    return {"added": status["added"], "token": token}


def steam_review(_params):
    summary = steam_self_install.review(service.config, _steam_settings(), **_steam_kwargs())
    token = uuid.uuid4().hex
    steam_reviews[token] = summary
    return {"token": token, "created": summary["created"], "profile": summary["profile"],
            "roles": summary["roles"], "logo_position": summary.get("logo_position")}


def steam_install(params):
    summary = steam_reviews.pop(params["token"])
    return steam_self_install.install(service.config, _steam_settings(), reviewed=summary, **_steam_kwargs())


def steam_remove(params):
    status = steam_reviews.pop(params["token"])
    return steam_self_install.remove(service.config, _steam_settings(), reviewed=status, **_steam_kwargs())


running: dict[str, dict] = {}
METHODS = {"hello": hello, "hardware": lambda _p: service.hardware(), "scan": scan, "prepare": prepare,
           "execute": execute, "cancel": cancel, "discard_operation": discard_operation, "save_defaults": save_defaults,
           "prepare_dlss": prepare_dlss, "update_dlss": update_dlss,
           "steam_status": steam_status, "steam_review": steam_review, "steam_install": steam_install,
           "steam_remove": steam_remove}

# Artwork, SteamGridDB, recovery, reports, notes, extras, packages, diagnosis,
# DLSS restore and updates: windows/engine-host/win_features.py.
import win_features  # noqa: E402

METHODS.update(win_features.install(service, lambda: engine_bridge.module(service.config).steam_config_engine()))
import offline_routes
METHODS['launch_offline'] = lambda p: offline_routes.launch(engine_bridge.module(service.config), p['row'])

import companion_controls  # noqa: E402
METHODS.update(companion_controls.methods(STATE))


def handle(request: dict) -> None:
    rid = request.get("id")

    def report(event: dict) -> None:
        if event.get("kind") == "progress":
            send({"event": "progress", "id": rid, **{k: v for k, v in event.items() if k != "kind"}})
        elif event.get("kind") == "log" and str(event.get("text", "")).strip().startswith("Downloading"):
            # Package downloads can take a while; surface them as a phase.
            send({"event": "progress", "id": rid, "label": str(event["text"]).strip()})

    try:
        method = METHODS[request["method"]]
        if request["method"] == "execute":
            running[request["params"]["token"]] = reviews.get(request["params"]["token"], {})
        with ui.report_to(report):
            result = method(request.get("params") or {})
        send({"id": rid, "result": result})
    except BaseException as exc:  # every failure is reported, never left hanging
        traceback.print_exc()
        message = desktop_service.friendly(str(exc)).replace(" from Desktop Mode", "")  # SteamOS wording
        send({"id": rid, "error": message or type(exc).__name__})
    finally:
        if request.get("method") == "execute":
            running.pop((request.get("params") or {}).get("token", ""), None)


def main() -> int:
    send({"event": "ready", **hello({})})
    workers: list[threading.Thread] = []
    for line in sys.stdin.buffer:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        # A long-lived helper must not retain every completed request thread.
        workers[:] = [worker for worker in workers if worker.is_alive()]
        if request.get("method") == "cancel":
            handle(request)  # answered immediately, even while an operation runs
        else:
            worker = threading.Thread(target=handle, args=(request,), daemon=True)
            worker.start()
            workers.append(worker)
    # stdin closed (the app exited or a script piped its requests): finish what was asked.
    for worker in workers:
        worker.join()
    return 0


if __name__ == "__main__":
    sys.exit(main())
