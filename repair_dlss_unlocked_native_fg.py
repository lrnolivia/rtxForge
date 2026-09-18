#!/usr/bin/env python3
"""
Repair existing rtxForge DLSS-Unlocked installs that used the old
root-runtime-promotion MFG recipe.

Preferred rtxForge repo:
    /home/loew/Repos/rtxForge

What this does:
  - Finds active DLSS-Unlocked installs recorded by rtxForge.
  - Detects root NVIDIA/Streamline DLLs that rtxForge managed/replaced.
  - Verifies the live DLL still matches exactly what rtxForge installed.
  - Restores the game's original DLL from rtxForge's baseline backup.
  - Relinquishes rtxForge ownership of that native game DLL permanently.
  - Leaves OptiScaler/streamline/* untouched/private.
  - Reasserts the documented RTX 40 game-owned DLSS-G configuration:
        FrameGen.Enabled=false
        FGInput=nofg
        FGOutput=nofg
        FGNvngxReplacement=None
        AdaMfgUnlock=true
        AdaBlackwellKernels=false
        AmpereMfgUnlock=false
  - Preserves all unrelated OptiScaler.ini settings.

Safety:
  - Dry-run by default.
  - Refuses to overwrite externally changed DLLs.
  - Uses the existing verified rtxForge recovery baseline.
  - Makes a repair snapshot before changing anything.
  - Does not touch y4my installs.
  - Does not deploy any hybrid/FSR FG backend.

Run from anywhere:
    python3 repair_dlss_unlocked_native_fg.py

Apply:
    python3 repair_dlss_unlocked_native_fg.py --apply

Optional single target:
    python3 repair_dlss_unlocked_native_fg.py \
        --target "/path/to/game/bin/x64" --apply
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time


PREFERRED_REPO = Path("/home/loew/Repos/rtxForge")

BAD_ROOT_NAMES = {
    "nvngx_dlss.dll",
    "nvngx_dlssd.dll",
    "nvngx_dlssg.dll",
    "nvngx_deepdvc.dll",
}


def is_native_root_runtime(rel: str) -> bool:
    """Return True only for native NVIDIA/Streamline files in game root."""
    if "/" in rel or "\\" in rel:
        return False

    name = rel.casefold()
    return name.startswith("sl.") or name in BAD_ROOT_NAMES


def find_repo_root() -> Path:
    candidates = [
        PREFERRED_REPO,
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parent.parent,
        Path.cwd(),
    ]

    seen: set[Path] = set()

    for root in candidates:
        try:
            root = root.expanduser().resolve()
        except OSError:
            continue

        if root in seen:
            continue
        seen.add(root)

        if (root / "engine" / "rtxengine.py").is_file():
            return root

    raise SystemExit(
        "Could not find engine/rtxengine.py.\n"
        f"Expected repo at: {PREFERRED_REPO}\n"
        "Move this script into the rtxForge repo or update PREFERRED_REPO."
    )


def load_engine(repo: Path):
    engine_path = repo / "engine" / "rtxengine.py"

    spec = importlib.util.spec_from_file_location(
        "rtxengine_native_runtime_repair",
        engine_path,
    )
    if spec is None or spec.loader is None:
        raise SystemExit(f"Could not import {engine_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    module.STATE_ROOT = Path(
        os.environ.get(
            "RTXFORGE_DLSS_UNLOCKED_STATE",
            str(Path.home() / ".local/state/rtxforge-dlss-unlocked"),
        )
    )

    module.USE_COLOR = True
    return module


def hash_stream(stream) -> str:
    h = hashlib.sha256()

    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        h.update(chunk)

    return h.hexdigest()


def original_entry_for(baseline: dict, rel: str):
    originals = baseline.get("originals") or {}

    for key, info in originals.items():
        if isinstance(key, str) and key.casefold() == rel.casefold():
            return key, info

    return None, None


def installed_hash_for(record: dict, rel: str):
    hashes = record.get("installed_hashes") or {}

    for key, digest in hashes.items():
        if isinstance(key, str) and key.casefold() == rel.casefold():
            return key, digest

    return None, None


def original_digest(engine, target: Path, info: dict) -> str:
    kind = info.get("kind")

    if kind == "file":
        digest = info.get("sha256")
        engine.require(
            isinstance(digest, str) and len(digest) == 64,
            "Original baseline file hash is missing",
        )
        return digest

    if kind != "tar_file":
        raise engine.Stop(
            f"Unsupported native-runtime baseline type: {kind!r}"
        )

    archive = engine._baseline_backup_member(
        target,
        info.get("backup", ""),
    )

    engine.require(
        archive.is_file() and not archive.is_symlink(),
        f"Baseline archive missing: {archive}",
    )

    engine.require(
        engine.sha256_file(archive) == info.get("archive_sha256"),
        f"Baseline archive checksum mismatch: {archive}",
    )

    wanted = str(info.get("member", "")).lstrip("./")

    with tarfile.open(archive, "r:*") as tf:
        matches = []

        for member in tf.getmembers():
            normalized = member.name.lstrip("./")
            if normalized == wanted and member.isfile():
                matches.append(member)

        engine.require(
            len(matches) == 1,
            f"Could not identify exactly one original file in {archive}",
        )

        src = tf.extractfile(matches[0])
        engine.require(
            src is not None,
            f"Could not read original file from {archive}",
        )

        with src:
            return hash_stream(src)


def restore_original(engine, target: Path, rel: str, info: dict) -> None:
    dst = engine._target_member_path(target, rel)
    kind = info.get("kind")

    engine.require(
        info.get("existed") is True,
        f"Native game runtime has no original backup: {rel}",
    )

    if kind == "file":
        src = engine._baseline_backup_member(
            target,
            info.get("backup", ""),
        )

        engine.require(
            src.is_file() and not src.is_symlink(),
            f"Original backup missing: {src}",
        )

        engine.ensure_file_replaceable(
            dst,
            f"native runtime repair {rel}",
        )

        engine.copy_verified(src, dst)
        os.chmod(dst, info.get("mode", 0o644))
        engine._fsync_file(dst)
        engine._fsync_dir(dst.parent)

        engine.require(
            engine.sha256_file(dst) == info["sha256"],
            f"Restore verification failed: {rel}",
        )

        return

    if kind == "tar_file":
        engine.require(
            shutil.which("sudo") is not None
            and shutil.which("tar") is not None,
            f"sudo + tar are required to restore {rel}",
        )

        archive = engine._baseline_backup_member(
            target,
            info.get("backup", ""),
        )

        restore_parent = info.get("restore_parent", ".")

        if restore_parent == ".":
            restore_dir = target
        else:
            restore_dir = engine._target_member_path(
                target,
                restore_parent,
            )

        engine._mkdir_durable(restore_dir)

        with engine._validated_tar_snapshot(
            archive,
            info["archive_sha256"],
            expected_top=info["member"],
            exact_file=True,
        ) as snapshot:
            subprocess.run(
                [
                    "sudo",
                    "tar",
                    "--acls",
                    "--xattrs",
                    "--numeric-owner",
                    "-xpf",
                    "-",
                    "-C",
                    str(restore_dir),
                ],
                stdin=snapshot,
                check=True,
            )

        engine.require(
            dst.is_file() and not dst.is_symlink(),
            f"Privileged restore failed: {rel}",
        )

        engine._sync_filesystem(restore_dir)
        return

    raise engine.Stop(
        f"Unsupported baseline type for {rel}: {kind!r}"
    )


def discover_states(engine, requested_target: Path | None):
    if requested_target is not None:
        target = requested_target.expanduser().resolve()
        baseline = engine.load_baseline(target)

        if baseline is None:
            raise engine.Stop(
                f"No rtxForge baseline exists for {target}"
            )

        yield target, baseline
        return

    targets_root = engine._validated_targets_root()

    if not targets_root.is_dir():
        return

    for state_dir in sorted(targets_root.iterdir()):
        if state_dir.is_symlink() or not state_dir.is_dir():
            continue

        baseline_file = state_dir / "baseline.json"

        if not baseline_file.is_file() or baseline_file.is_symlink():
            continue

        try:
            raw = json.loads(
                baseline_file.read_text(encoding="utf-8")
            )

            target_raw = raw.get("target_dir")
            if not isinstance(target_raw, str) or not target_raw:
                continue

            target = Path(target_raw).expanduser().resolve()

            if state_dir != engine._validated_state_dir(target):
                continue

            baseline = engine.load_baseline(target)

            if baseline is not None:
                yield target, baseline

        except Exception as exc:
            print(
                f"[skip] unreadable state {baseline_file}: {exc}",
                file=sys.stderr,
            )


def repair_ini(engine, target: Path, current: dict, apply: bool):
    """Preserve user's INI and change only rtxForge's FG ownership policy."""
    ini = target / "OptiScaler.ini"

    if not ini.is_file() or ini.is_symlink():
        return None, False

    text = ini.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )

    before = text

    text = engine.set_ini_value(
        text, "FrameGen", "Enabled", "false"
    )
    text = engine.set_ini_value(
        text, "FrameGen", "FGInput", "nofg"
    )
    text = engine.set_ini_value(
        text, "FrameGen", "FGOutput", "nofg"
    )
    text = engine.set_ini_value(
        text, "FrameGen", "FGNvngxReplacement", "None"
    )

    text = engine.set_ini_value(
        text, "DLSSG", "AdaMfgUnlock", "true"
    )

    # ShyVortex RTX40 guidance keeps this experimental kernel retargeting
    # disabled by default.
    text = engine.set_ini_value(
        text, "DLSSG", "AdaBlackwellKernels", "false"
    )

    text = engine.set_ini_value(
        text, "DLSSG", "AmpereMfgUnlock", "false"
    )

    if text == before:
        return engine.sha256_file(ini), False

    if not apply:
        return None, True

    engine.atomic_write(
        ini,
        text.encode("utf-8"),
        0o644,
    )

    return engine.sha256_file(ini), True


def make_repair_snapshot(
    engine,
    target: Path,
    baseline: dict,
    runtime_paths: list[str],
) -> Path:
    state_dir = engine._validated_state_dir(
        target,
        require_exists=True,
    )

    repair_dir = (
        state_dir
        / "native-runtime-repair"
        / f"{engine.now_stamp()}-{time.time_ns()}"
    )

    engine._mkdir_durable(repair_dir, mode=0o700)

    shutil.copy2(
        engine.baseline_path(target),
        repair_dir / "baseline-before.json",
    )

    for rel in runtime_paths:
        src = engine._target_member_path(target, rel)

        if src.is_file() and not src.is_symlink():
            dst = repair_dir / "provider-root-bytes" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    ini = target / "OptiScaler.ini"
    if ini.is_file() and not ini.is_symlink():
        shutil.copy2(
            ini,
            repair_dir / "OptiScaler.ini.before",
        )

    return repair_dir


def relinquish_runtime_ownership(
    engine,
    target: Path,
    baseline: dict,
    runtime_paths: list[str],
    new_ini_hash: str | None,
):
    """Stop rtxForge from owning restored game-native NVIDIA/Streamline DLLs."""
    folded = {rel.casefold() for rel in runtime_paths}

    baseline["managed_paths"] = [
        rel
        for rel in baseline.get("managed_paths", [])
        if not (
            isinstance(rel, str)
            and rel.casefold() in folded
        )
    ]

    originals = baseline.get("originals") or {}
    for key in list(originals):
        if isinstance(key, str) and key.casefold() in folded:
            originals.pop(key, None)

    for record_name in ("current", "pending_install"):
        record = baseline.get(record_name)

        if not isinstance(record, dict):
            continue

        hashes = record.get("installed_hashes")

        if isinstance(hashes, dict):
            for key in list(hashes):
                if isinstance(key, str) and key.casefold() in folded:
                    hashes.pop(key, None)

    current = baseline.get("current") or {}

    if new_ini_hash:
        hashes = current.get("installed_hashes") or {}

        ini_key = next(
            (
                key
                for key in hashes
                if isinstance(key, str)
                and key.casefold() == "optiscaler.ini"
            ),
            None,
        )

        if ini_key is not None:
            hashes[ini_key] = new_ini_hash

    policy = current.setdefault(
        "compatibility_policy",
        {},
    )

    policy["mfg_route"] = (
        "game-owned-native-dlssg-ada-unlock"
    )
    policy["native_runtime_ownership"] = "game"
    policy["provider_streamline_location"] = (
        "OptiScaler/streamline/"
    )
    policy["root_runtime_replacement"] = False

    current["native_runtime_repair"] = {
        "repaired_utc": engine.now_iso(),
        "restored_paths": sorted(
            runtime_paths,
            key=str.casefold,
        ),
        "ownership": "game",
    }

    baseline["last_attempt_utc"] = engine.now_iso()

    engine.save_json_atomic(
        engine.baseline_path(target),
        baseline,
    )


def process_target(
    engine,
    target: Path,
    baseline: dict,
    apply: bool,
):
    current = baseline.get("current") or {}

    if baseline.get("status") != "active":
        return "skip", "install is not active"

    if current.get("provider_id") != "dlss-unlocked":
        return "skip", "not a DLSS-Unlocked install"

    feature_mode = current.get("feature_mode")

    if feature_mode == "nr-only":
        return "skip", "NR-only install has no Ada MFG path"

    if feature_mode not in {"mfg-only", "nr-mfg"}:
        return "skip", f"unsupported feature mode {feature_mode!r}"

    engine.verify_baseline_integrity(
        target,
        baseline,
        adopt_legacy=apply,
    )

    running = engine._running_processes_under_root(
        target.resolve()
    )

    engine.require(
        not running,
        "Game process appears to be running under "
        f"{target}: {', '.join(running[:5])}",
    )

    hashes = current.get("installed_hashes") or {}

    candidate_paths = sorted(
        [
            rel
            for rel in hashes
            if isinstance(rel, str) and is_native_root_runtime(rel)
        ],
        key=str.casefold,
    )

    restore_plan = []

    for rel in candidate_paths:
        original_key, info = original_entry_for(
            baseline,
            rel,
        )

        engine.require(
            original_key is not None
            and isinstance(info, dict)
            and info.get("existed") is True,
            f"Refusing repair: no original game backup for {rel}",
        )

        installed_key, installed_digest = installed_hash_for(
            current,
            rel,
        )

        engine.require(
            isinstance(installed_digest, str)
            and len(installed_digest) == 64,
            f"Missing installed hash for {rel}",
        )

        live = engine._target_member_path(
            target,
            rel,
        )

        engine.require(
            live.is_file() and not live.is_symlink(),
            f"Native runtime changed filesystem state: {live}",
        )

        live_digest = engine.sha256_file(live)

        original_sha = original_digest(
            engine,
            target,
            info,
        )

        if live_digest == original_sha:
            state = "already-restored"

        elif live_digest == installed_digest:
            state = "provider-replacement"

        else:
            raise engine.Stop(
                f"{rel} changed after rtxForge installed it.\n"
                f"  live:      {live_digest}\n"
                f"  rtxForge:  {installed_digest}\n"
                f"  original:  {original_sha}\n"
                "Refusing to overwrite external/game/user changes."
            )

        restore_plan.append(
            {
                "rel": rel,
                "info": info,
                "state": state,
                "original_sha": original_sha,
            }
        )

    print()
    print(f"Game target: {target}")
    print("Provider:    DLSS-Unlocked")
    print(f"Mode:        {feature_mode}")

    if restore_plan:
        print("Root runtime files incorrectly owned by rtxForge:")

        for row in restore_plan:
            print(
                f"  {row['rel']}: {row['state']}"
            )
    else:
        print(
            "No promoted root NVIDIA/Streamline runtime "
            "files remain."
        )

    if not apply:
        _, ini_change = repair_ini(
            engine,
            target,
            current,
            apply=False,
        )

        if ini_change:
            print(
                "OptiScaler.ini also needs the corrected "
                "DLSS-Unlocked Ada policy."
            )

        return "dry-run", (
            f"{len(restore_plan)} root runtime file(s) "
            "would be repaired"
        )

    repair_dir = make_repair_snapshot(
        engine,
        target,
        baseline,
        [row["rel"] for row in restore_plan],
    )

    print(f"Repair snapshot: {repair_dir}")

    for row in restore_plan:
        rel = row["rel"]

        if row["state"] == "provider-replacement":
            print(f"Restoring game runtime: {rel}")
            restore_original(
                engine,
                target,
                rel,
                row["info"],
            )
        else:
            print(f"Already game-owned:      {rel}")

        live_sha = engine.sha256_file(
            engine._target_member_path(
                target,
                rel,
            )
        )

        engine.require(
            live_sha == row["original_sha"],
            f"Post-repair verification failed: {rel}",
        )

    new_ini_hash, ini_changed = repair_ini(
        engine,
        target,
        current,
        apply=True,
    )

    if ini_changed:
        print("Updated native Ada policy in OptiScaler.ini")

    relinquish_runtime_ownership(
        engine,
        target,
        baseline,
        [row["rel"] for row in restore_plan],
        new_ini_hash,
    )

    repaired = engine.load_baseline(target)

    engine.require(
        repaired is not None,
        "Baseline disappeared after repair",
    )

    engine.verify_baseline_integrity(
        target,
        repaired,
        adopt_legacy=True,
    )

    print("Native runtime ownership repaired.")
    print("OptiScaler/streamline/ remains private and untouched.")

    return "repaired", (
        f"{len(restore_plan)} root runtime file(s) relinquished"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Repair existing rtxForge DLSS-Unlocked "
            "native NVIDIA FG installs."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the repair. Default is dry-run.",
    )

    parser.add_argument(
        "--target",
        type=Path,
        help=(
            "Repair only this exact game executable directory. "
            "Without this option, all recorded installs are scanned."
        ),
    )

    args = parser.parse_args()

    repo = find_repo_root()
    print(f"rtxForge repo: {repo}")

    engine = load_engine(repo)

    found = 0
    repaired_count = 0
    failures = 0

    for target, baseline in discover_states(
        engine,
        args.target,
    ):
        current = baseline.get("current") or {}

        if current.get("provider_id") != "dlss-unlocked":
            continue

        if current.get("feature_mode") == "nr-only":
            continue

        found += 1

        try:
            status, detail = process_target(
                engine,
                target,
                baseline,
                args.apply,
            )

            print(f"[{status}] {detail}")

            if status == "repaired":
                repaired_count += 1

        except Exception as exc:
            failures += 1
            print()
            print(f"[BLOCKED] {target}")
            print(str(exc))
            print()

    if not found:
        print(
            "No active DLSS-Unlocked MFG/NR+MFG "
            "rtxForge installs were found."
        )

    if args.apply:
        print()
        print(
            f"Repair complete: {repaired_count} repaired, "
            f"{failures} blocked."
        )
    else:
        print()
        print(
            "Dry run only. Re-run with --apply "
            "to perform the repair."
        )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
