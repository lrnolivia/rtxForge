import importlib.util
import json
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "rtxengine.py"


def load_engine():
    name = f"rtxengine_v13_test_{id(object())}"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _cstr(value: str) -> bytes:
    return value.encode("utf-8", errors="surrogateescape") + b"\x00"


def _string_field(key: str, value: str) -> bytes:
    return b"\x01" + _cstr(key) + _cstr(value)


def _int_field(key: str, value: int) -> bytes:
    import struct
    return b"\x02" + _cstr(key) + struct.pack("<i", value)


def _shortcuts_fixture(game, launch: str) -> bytes:
    obj = bytearray(b"\x00" + _cstr("0"))
    obj += _string_field("AppName", game.name)
    obj += _string_field("exe", f'"{game.exe}"')
    obj += _string_field("StartDir", f'"{game.root}"')
    obj += _int_field("appid", 0x2345678)
    obj += _string_field("LaunchOptions", launch)
    obj += b"\x08"
    return b"\x00" + _cstr("shortcuts") + bytes(obj) + b"\x08\x08"


class DeepCleanTests(unittest.TestCase):
    def setUp(self):
        self.m = load_engine()
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.m.STATE_ROOT = self.base / "state"
        self.steam_root = self.base / "Steam"
        (self.steam_root / "logs").mkdir(parents=True)
        self.m.STEAM_ROOT_CANDIDATES = (self.steam_root,)
        self.root = self.base / "Game"
        self.target = self.root / "Binaries" / "Win64"
        self.target.mkdir(parents=True)
        self.game = self.m.Game(
            "A", "Fixture", self.root, "Steam", "123", None,
            self.target / "game.exe", self.target,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_classifier_guts_mods_but_preserves_dlss_updater_runtime(self):
        preserved = {
            "nvngx_dlss.dll": b"NVIDIA optiscaler text should not matter",
            "nvngx_dlssg.dll": b"NVIDIA",
            "nvngx_dlssd.dll": b"NVIDIA",
            "sl.dlss_g.dll": b"Streamline",
            "unrelated.dll": b"vanilla-ish",
            # Legitimate game DLLs can contain compatibility strings. Generic
            # DLL content alone must not authorize destructive deletion.
            "game-renderer.dll": b"supports ReShade compatibility diagnostics",
        }
        for name, data in preserved.items():
            (self.target / name).write_bytes(data)

        (self.target / "nvngx_dlssnr.dll").write_bytes(b"NR")
        (self.target / "dxgi.dll").write_bytes(b"prefix ReShade suffix")
        (self.target / "DreamPunk.ini").write_text("[Preset]", encoding="utf-8")
        (self.target / "ReShade.ini").write_text(
            "PresetPath=.\\DreamPunk.ini\n", encoding="utf-8"
        )
        (self.target / "foo.addon64").write_bytes(b"addon")
        (self.target / "dlssg_to_fsr3.ini").write_text("x=1", encoding="utf-8")
        # Old injector families often hide behind generic proxy names. Their
        # binary signature should still make them removable.
        (self.target / "version.dll").write_bytes(b"DLSSTweaks proxy fixture")
        (self.target / "winmm.dll").write_bytes(b"UniScaler compatibility proxy")
        (self.target / "nvngx.dll").write_bytes(b"DLSSTweaks wrapper fixture")
        (self.target / "XAPOFX1_5.dll").write_bytes(b"DLSSTweaks alternate wrapper")
        (self.target / "DLSSTweaks.ini").write_text("x=1", encoding="utf-8")
        opti = self.target / "OptiScaler"
        opti.mkdir()
        (opti / "sl.interposer.dll").write_bytes(b"OptiScaler package")
        backup = self.root / "_DLSS5_Backup"
        backup.mkdir()
        (backup / "x.bin").write_bytes(b"x" * 10)

        candidates = self.m.deep_clean_scan_game(self.game)
        rels = {str(c.path.relative_to(self.root)) for c in candidates}
        expected_removed = {
            "Binaries/Win64/OptiScaler",
            "Binaries/Win64/nvngx_dlssnr.dll",
            "Binaries/Win64/dxgi.dll",
            "Binaries/Win64/ReShade.ini",
            "Binaries/Win64/DreamPunk.ini",
            "Binaries/Win64/foo.addon64",
            "Binaries/Win64/dlssg_to_fsr3.ini",
            "Binaries/Win64/version.dll",
            "Binaries/Win64/winmm.dll",
            "Binaries/Win64/nvngx.dll",
            "Binaries/Win64/XAPOFX1_5.dll",
            "Binaries/Win64/DLSSTweaks.ini",
            "_DLSS5_Backup",
        }
        self.assertTrue(expected_removed <= rels, expected_removed - rels)
        for name in preserved:
            self.assertNotIn(f"Binaries/Win64/{name}", rels)

        row = self.m.deep_clean_apply_game(self.game, candidates)
        self.assertEqual(row["status"], "cleaned")
        for name in preserved:
            self.assertTrue((self.target / name).exists(), name)
        for rel in expected_removed:
            self.assertFalse((self.root / rel).exists(), rel)
        self.assertTrue(Path(row["receipt"]).is_file())

    def test_deep_clean_unlinks_known_mod_symlink_without_following_outside_target(self):
        outside = self.base / "outside-mod-target"
        outside.mkdir()
        sentinel = outside / "KEEP.txt"
        sentinel.write_text("keep", encoding="utf-8")
        link = self.target / "OptiScaler"
        link.symlink_to(outside, target_is_directory=True)

        candidates = self.m.deep_clean_scan_game(self.game)
        matching = [c for c in candidates if c.path == link]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].kind, "symlink")
        row = self.m.deep_clean_apply_game(self.game, candidates)
        self.assertEqual(row["status"], "cleaned")
        self.assertFalse(link.exists())
        self.assertTrue(sentinel.is_file())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_deep_clean_preserves_unmanaged_generic_proxy_symlink(self):
        outside = self.base / "outside-generic-proxy"
        outside.mkdir()
        sentinel = outside / "real-dxgi.dll"
        sentinel.write_bytes(b"legitimate-game-proxy")
        link = self.target / "dxgi.dll"
        link.symlink_to(sentinel)

        candidates = self.m.deep_clean_scan_game(self.game)
        self.assertFalse(any(c.path == link for c in candidates))
        self.assertTrue(link.is_symlink())
        self.assertEqual(sentinel.read_bytes(), b"legitimate-game-proxy")

    def test_deep_clean_unlinks_named_mod_file_symlink_without_following_target(self):
        outside = self.base / "outside-dlsstweaks"
        outside.mkdir()
        sentinel = outside / "settings.ini"
        sentinel.write_text("keep", encoding="utf-8")
        link = self.target / "DLSSTweaks.ini"
        link.symlink_to(sentinel)

        candidates = self.m.deep_clean_scan_game(self.game)
        match = [c for c in candidates if c.path == link]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0].kind, "symlink")
        self.m.deep_clean_apply_game(self.game, candidates)
        self.assertFalse(link.exists())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_deep_clean_unlinks_reshade_preset_symlink_without_following_target(self):
        outside = self.base / "outside-preset"
        outside.mkdir()
        sentinel = outside / "DreamPunk.ini"
        sentinel.write_text("external preset", encoding="utf-8")
        preset_link = self.target / "DreamPunk.ini"
        preset_link.symlink_to(sentinel)
        (self.target / "ReShade.ini").write_text("PresetPath=.\\DreamPunk.ini\n", encoding="utf-8")

        candidates = self.m.deep_clean_scan_game(self.game)
        match = [c for c in candidates if c.path == preset_link]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0].kind, "symlink")
        self.m.deep_clean_apply_game(self.game, candidates)
        self.assertFalse(preset_link.exists())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "external preset")

    def test_deep_clean_managed_proxy_replaced_by_outside_symlink_is_unlinked_safely(self):
        outside = self.base / "outside-proxy-target"
        outside.mkdir()
        sentinel = outside / "real.dll"
        sentinel.write_bytes(b"external")
        link = self.target / "dxgi.dll"
        link.symlink_to(sentinel)
        state = self.m.state_dir_for(self.target)
        state.mkdir(parents=True)
        self.m.save_json_atomic(state / "baseline.json", {
            "schema": 13,
            "target_dir": str(self.target),
            "name": self.game.name,
            "source": "Steam",
            "appid": "123",
            "managed_paths": ["dxgi.dll"],
        })
        candidates = self.m.deep_clean_scan_game(self.game)
        matching = [c for c in candidates if c.path == link]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].kind, "symlink")
        self.m.deep_clean_apply_game(self.game, candidates)
        self.assertFalse(link.exists())
        self.assertEqual(sentinel.read_bytes(), b"external")

    def test_deep_clean_marks_managed_state_recovery_before_first_deletion(self):
        payload = self.target / "nvngx_dlssnr.dll"
        payload.write_bytes(b"NR")
        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True)
        self.m.save_json_atomic(state_dir / "baseline.json", {
            "schema": 13,
            "target_dir": str(self.target),
            "exe": str(self.target / "game.exe"),
            "name": self.game.name,
            "source": "Steam",
            "appid": "123",
            "status": "active",
            "managed_paths": ["nvngx_dlssnr.dll"],
            "originals": {},
            "current": {},
        })
        candidates = self.m.deep_clean_scan_game(self.game)
        real_unlink = self.m.durable_unlink
        observed = {"pending": False}
        def inspect_then_unlink(path, *args, **kwargs):
            if Path(path) == payload:
                data = json.loads((state_dir / "baseline.json").read_text(encoding="utf-8"))
                self.assertEqual(data["status"], "destructive-pending")
                self.assertEqual(data["destructive_pending"]["mode"], "deep-clean")
                observed["pending"] = True
            return real_unlink(path, *args, **kwargs)
        self.m.durable_unlink = inspect_then_unlink
        try:
            self.m.deep_clean_apply_game(self.game, candidates)
        finally:
            self.m.durable_unlink = real_unlink
        self.assertTrue(observed["pending"])

    def test_deep_clean_refuses_corrupt_known_state_before_deletion(self):
        payload = self.target / "nvngx_dlssnr.dll"
        payload.write_bytes(b"NR")
        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True)
        (state_dir / "baseline.json").write_text("{not-json", encoding="utf-8")
        candidates = [self.m.DeepCleanCandidate(
            payload, "file", "explicit known-mod fixture", payload.stat().st_size,
            sha256=self.m.sha256_file(payload),
        )]
        with self.assertRaises(self.m.Stop) as cm:
            self.m.deep_clean_apply_game(self.game, candidates)
        self.assertIn("Known rtxEngine state could not be prepared", str(cm.exception))
        self.assertTrue(payload.is_file())

    def test_deep_clean_purges_bulky_target_state(self):
        (self.target / "nvngx_dlssnr.dll").write_bytes(b"NR")
        state_dir = self.m.state_dir_for(self.target)
        (state_dir / "baseline-backup").mkdir(parents=True)
        (state_dir / "baseline-backup" / "old.bin").write_bytes(b"old")
        baseline = {
            "schema": 13,
            "target_dir": str(self.target),
            "exe": str(self.target / "game.exe"),
            "name": "Fixture",
            "source": "Steam",
            "appid": "123",
            "status": "active",
            "managed_paths": ["nvngx_dlssnr.dll"],
            "originals": {},
            "current": {},
        }
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)
        candidates = self.m.deep_clean_scan_game(self.game)
        row = self.m.deep_clean_apply_game(self.game, candidates)
        self.assertEqual(row["state_dirs_purged"], 1)
        self.assertFalse(state_dir.exists())
        self.assertTrue(Path(row["receipt"]).is_file())

    def test_history_retention_is_thin(self):
        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True)
        for i in range(3):
            p = state_dir / f"baseline-backup-restored-20260101-00000{i}"
            p.mkdir()
            (p / "x").write_text(str(i), encoding="utf-8")
            time.sleep(0.002)
            q = state_dir / f"baseline-restored-20260101-00000{i}.json"
            q.write_text(str(i), encoding="utf-8")
            time.sleep(0.002)
        recovery = state_dir / "recovery-before-restore"
        recovery.mkdir()
        for i in range(3):
            p = recovery / f"20260101-00000{i}"
            p.mkdir()
            (p / "x").write_text(str(i), encoding="utf-8")
            time.sleep(0.002)

        self.m.prune_target_history(self.target)
        self.assertEqual(len(list(state_dir.glob("baseline-backup-restored-*"))), 0)
        self.assertEqual(len(list(state_dir.glob("baseline-restored-*.json"))), 1)
        self.assertEqual(len(list(recovery.iterdir())), 1)

    def test_verify_queue_is_fifo(self):
        other = self.m.Game("B", "Two", self.root, "Steam", "456")
        q = self.m.save_verify_queue([self.game, other])
        self.assertIsNotNone(q)
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log
        launched = []

        def fake_launch(appid):
            launched.append(appid)
            with log.open("a", encoding="utf-8") as f:
                f.write(f"Start validating appID {appid}\n")
                f.write(f"AppID {appid} scheduler finished : removed from schedule (result No Error, state 0xc)\n")

        self.m.launch_steam_verify = fake_launch
        first = self.m.start_next_steam_verify()
        second = self.m.start_next_steam_verify()
        self.assertEqual([first["appid"], second["appid"]], ["123", "456"])
        self.assertEqual(launched, ["123", "456"])

    def test_start_next_verify_keeps_launch_intent_until_log_confirmation(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log
        launched = []
        self.m.launch_steam_verify = lambda appid: launched.append(str(appid))
        self.m.save_verify_queue([self.game])
        row = self.m.start_next_steam_verify()
        self.assertEqual(row["appid"], "123")
        self.assertEqual(launched, ["123"])
        _path, data = self.m._load_verify_queue()
        self.assertEqual(data["in_flight"]["phase"], "launch-intent")
        self.assertIn("uri_sent_utc", data["in_flight"])
        self.assertNotIn("launch_confirmed_utc", data["in_flight"])

    def test_unconfirmed_launch_intent_stops_queue_without_waiting_hours(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log
        self.m.save_verify_queue([self.game])
        path, data = self.m._load_verify_queue()
        row = data["remaining"].pop(0)
        data["in_flight"] = {
            **row, "log_path": str(log), "start_offset": 0,
            "phase": "launch-intent", "launch_recorded_utc": self.m.now_iso(),
        }
        self.m.save_json_atomic(path, data)
        self.m.wait_for_steam_validation = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("unconfirmed launch-intent must not enter long wait")
        )
        summary = self.m.run_steam_verify_queue_sequential(timeout_seconds=9999, launch_confirm_seconds=0.001)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["unconfirmed_launch"]["appid"], "123")
        _path, current = self.m._load_verify_queue()
        self.assertEqual(current["in_flight"]["phase"], "launch-intent")

    def test_retry_unconfirmed_launch_intent_relaunches_same_appid(self):
        second = self.m.Game("B", "Two", self.root, "Steam", "456")
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log
        self.m.save_verify_queue([self.game, second])
        path, data = self.m._load_verify_queue()
        row = data["remaining"].pop(0)
        data["in_flight"] = {
            **row, "log_path": str(log), "start_offset": 0,
            "phase": "launch-intent", "launch_recorded_utc": self.m.now_iso(),
        }
        self.m.save_json_atomic(path, data)
        launched = []
        self.m.launch_steam_verify = lambda appid: launched.append(str(appid))
        retried = self.m.retry_failed_steam_verify()
        self.assertEqual(retried["appid"], "123")
        self.assertEqual(launched, ["123"])
        _path, current = self.m._load_verify_queue()
        self.assertEqual(current["in_flight"]["appid"], "123")
        self.assertEqual(current["in_flight"]["phase"], "launch-intent")
        self.assertIn("uri_sent_utc", current["in_flight"])
        self.assertEqual([row["appid"] for row in current["remaining"]], ["456"])

    def test_verify_log_path_refuses_nested_content_log_under_known_logs_dir(self):
        nested = self.steam_root / "logs" / "archive" / "content_log.txt"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text(
            "Start validating appID 123\n"
            "AppID 123 scheduler finished : removed from schedule (result No Error, state 0xc)\n",
            encoding="utf-8",
        )
        with self.assertRaises(self.m.Stop) as cm:
            self.m._validate_steam_content_log_path(nested)
        self.assertIn("canonical content_log.txt", str(cm.exception))

    def test_verify_log_path_refuses_symlink_retarget_inside_known_logs_dir(self):
        real = self.steam_root / "logs" / "synthetic.txt"
        real.write_text(
            "Start validating appID 123\n"
            "AppID 123 scheduler finished : removed from schedule (result No Error, state 0xc)\n",
            encoding="utf-8",
        )
        link = self.steam_root / "logs" / "content_log.txt"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(real)
        with self.assertRaises(self.m.Stop) as cm:
            self.m._validate_steam_content_log_path(link)
        self.assertIn("canonical content_log.txt", str(cm.exception))

    def test_verify_queue_refuses_non_list_completed_history(self):
        self.m.save_json_atomic(self.m._verify_queue_path(), {
            "schema": 2,
            "created_utc": self.m.now_iso(),
            "remaining": [],
            "in_flight": None,
            "completed": {"appid": "123"},
        })
        with self.assertRaises(self.m.Stop) as cm:
            self.m._load_verify_queue()
        self.assertIn("completed list is corrupt", str(cm.exception))

    def test_verify_queue_refuses_malformed_completed_row_before_finish(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.save_json_atomic(self.m._verify_queue_path(), {
            "schema": 2,
            "created_utc": self.m.now_iso(),
            "remaining": [],
            "in_flight": {
                "name": self.game.name, "appid": "123", "root": str(self.root),
                "log_path": str(log), "start_offset": 0, "phase": "launched",
            },
            "completed": ["not-a-row"],
        })
        with self.assertRaises(self.m.Stop) as cm:
            self.m._load_verify_queue()
        self.assertIn("completed row is corrupt", str(cm.exception))

    def test_verify_queue_refuses_boolean_inflight_offset(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("history\n", encoding="utf-8")
        self.m.save_json_atomic(self.m._verify_queue_path(), {
            "schema": 2, "created_utc": self.m.now_iso(), "remaining": [], "completed": [],
            "in_flight": {"name": "One", "appid": "123", "root": str(self.root),
                          "log_path": str(log), "start_offset": True, "phase": "launched"},
        })
        with self.assertRaises(self.m.Stop) as cm:
            self.m._load_verify_queue()
        self.assertIn("offset is corrupt", str(cm.exception))

    def test_verify_queue_refuses_boolean_log_identity(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("history\n", encoding="utf-8")
        self.m.save_json_atomic(self.m._verify_queue_path(), {
            "schema": 2, "created_utc": self.m.now_iso(), "remaining": [], "completed": [],
            "in_flight": {"name": "One", "appid": "123", "root": str(self.root),
                          "log_path": str(log), "start_offset": 0, "log_dev": True,
                          "phase": "launched"},
        })
        with self.assertRaises(self.m.Stop) as cm:
            self.m._load_verify_queue()
        self.assertIn("log_dev is corrupt", str(cm.exception))

    def test_verify_log_anchor_refuses_boolean_offset_directly(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("history\n", encoding="utf-8")
        with self.assertRaises(self.m.Stop) as cm:
            self.m._steam_log_anchor(log, True)
        self.assertIn("offset is invalid", str(cm.exception))

    def test_verify_log_slice_refuses_boolean_offset_directly(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("history\n", encoding="utf-8")
        with self.assertRaises(self.m.Stop) as cm:
            self.m._steam_log_slice(log, True)
        self.assertIn("offset is invalid", str(cm.exception))

    def test_verify_log_slice_treats_boolean_anchor_length_as_reset(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_bytes(b"history\n")
        text, _offset, reset = self.m._steam_log_slice(
            log, len(b"history\n"),
            expected_anchor_len=True, expected_anchor_sha256="0" * 64,
        )
        self.assertEqual(text, "")
        self.assertTrue(reset)

    def test_verify_queue_refuses_unknown_inflight_phase(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.save_json_atomic(self.m._verify_queue_path(), {
            "schema": 2,
            "created_utc": self.m.now_iso(),
            "remaining": [],
            "in_flight": {
                "name": self.game.name, "appid": "123", "root": str(self.root),
                "log_path": str(log), "start_offset": 0, "phase": "mystery",
            },
            "completed": [],
        })
        with self.assertRaises(self.m.Stop) as cm:
            self.m._load_verify_queue()
        self.assertIn("phase is invalid", str(cm.exception))

    def test_verify_queue_refuses_overlap_while_inflight_is_unproven(self):
        other = self.m.Game("B", "Two", self.root, "Steam", "456")
        self.m.save_verify_queue([self.game, other])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log
        launched = []
        self.m.launch_steam_verify = lambda appid: launched.append(appid)
        first = self.m.start_next_steam_verify()
        self.assertEqual(first["appid"], "123")
        with self.assertRaises(self.m.Stop):
            self.m.start_next_steam_verify()
        self.assertEqual(launched, ["123"])
        _, data = self.m._load_verify_queue()
        self.assertEqual(data["in_flight"]["appid"], "123")
        self.assertEqual([r["appid"] for r in data["remaining"]], ["456"])


    def test_verify_queue_rejects_boolean_schema_version(self):
        path = self.m._verify_queue_path()
        self.m.save_json_atomic(path, {
            "schema": True,
            "created_utc": self.m.now_iso(),
            "remaining": [{"name": "One", "appid": "123", "root": str(self.root)}],
            "in_flight": None,
            "completed": [],
        })
        with self.assertRaises(self.m.Stop) as cm:
            self.m._load_verify_queue()
        self.assertIn("schema", str(cm.exception).lower())

    def test_validation_log_monitor_requires_app_specific_completion(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("old line\n", encoding="utf-8")
        offset = log.stat().st_size
        with log.open("a", encoding="utf-8") as f:
            f.write("[x] Start validating appID 123\n")
            f.write("[x] AppID 123 update changed : Running,Validating,\n")
            f.write("[x] File validation finished: 1 files total\n")
            f.write("[x] AppID 123 scheduler finished : removed from schedule (result No Error, state 0xc)\n")
        self.assertTrue(
            self.m.wait_for_steam_validation(
                "123", log, offset, timeout_seconds=1, poll_seconds=0.001
            )
        )

    def test_scheduler_staying_in_schedule_is_not_completion(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        with log.open("a", encoding="utf-8") as f:
            f.write("Start validating appID 123\n")
            f.write("AppID 123 App update changed : Running Update,Verifying Installed,\n")
            f.write("AppID 123 scheduler finished : staying in schedule (result No Error, state 0xe)\n")
        status = self.m.steam_validation_status("123", log, 0)
        self.assertTrue(status["started"])
        self.assertFalse(status["completed"])
        self.assertFalse(status["failed"])

        with log.open("a", encoding="utf-8") as f:
            f.write("AppID 123 scheduler finished : removed from schedule (result No Error, state 0xc)\n")
        status = self.m.steam_validation_status("123", log, 0)
        self.assertTrue(status["completed"])
        self.assertFalse(status["failed"])

    def test_validation_update_none_is_not_success_without_terminal_result(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        offset = 0
        with log.open("a", encoding="utf-8") as f:
            f.write("Start validating appID 123\n")
            f.write("AppID 123 App update changed : Running Update,Validating,\n")
            f.write("AppID 123 App update changed : None\n")
        status = self.m.steam_validation_status("123", log, offset)
        self.assertTrue(status["started"])
        self.assertFalse(status["completed"])
        self.assertFalse(status["failed"])

    def test_validation_blocked_by_app_fails_fast_and_keeps_later_queue(self):
        other = self.m.Game("B", "Two", self.root, "Steam", "456")
        self.m.save_verify_queue([self.game, other])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log
        launched = []

        def fake_launch(appid):
            launched.append(str(appid))
            with log.open("a", encoding="utf-8") as f:
                f.write(f"Start validating appID {appid}\n")
                f.write(
                    f"AppID {appid} scheduler update : updates disabled by app; "
                    "blocking attempt Priority First\n"
                )

        self.m.launch_steam_verify = fake_launch
        with self.assertRaises(self.m.Stop) as cm:
            self.m.run_steam_verify_queue_sequential(timeout_seconds=1, launch_confirm_seconds=0.01)
        self.assertIn("verification failed", str(cm.exception))
        self.assertIn("blocking attempt", str(cm.exception))
        self.assertEqual(launched, ["123"])
        _path, data = self.m._load_verify_queue()
        self.assertEqual(data["in_flight"]["appid"], "123")
        self.assertEqual([row["appid"] for row in data["remaining"]], ["456"])
        self.assertEqual(data.get("completed"), [])

    def test_validation_blocker_without_start_marker_fails_immediately(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text(
            "AppID 123 scheduler update : updates disabled by app; blocking attempt Priority First\n",
            encoding="utf-8",
        )
        status = self.m.steam_validation_status("123", log, 0)
        self.assertFalse(status["started"])
        self.assertFalse(status["completed"])
        self.assertTrue(status["failed"])
        self.assertIn("blocking attempt", status["detail"])

    def test_validation_blocker_without_start_marker_never_matches_other_appid(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text(
            "AppID 1234 scheduler update : updates disabled by app; blocking attempt Priority First\n",
            encoding="utf-8",
        )
        status = self.m.steam_validation_status("123", log, 0)
        self.assertFalse(status["started"])
        self.assertFalse(status["completed"])
        self.assertFalse(status["failed"])

    def test_validation_failed_scheduler_result_never_advances_queue(self):
        other = self.m.Game("B", "Two", self.root, "Steam", "456")
        self.m.save_verify_queue([self.game, other])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log

        def fake_launch(appid):
            with log.open("a", encoding="utf-8") as f:
                f.write(f"Start validating appID {appid}\n")
                f.write(f"AppID {appid} App update changed : None\n")
                f.write(f"AppID {appid} scheduler finished : removed from schedule (result Corrupt game files, state 0x4ae)\n")

        self.m.launch_steam_verify = fake_launch
        with self.assertRaises(self.m.Stop) as cm:
            self.m.run_steam_verify_queue_sequential(timeout_seconds=1)
        self.assertIn("Steam verification failed", str(cm.exception))
        _, data = self.m._load_verify_queue()
        self.assertEqual(data["in_flight"]["appid"], "123")
        self.assertEqual([row["appid"] for row in data["remaining"]], ["456"])
        self.assertEqual(data.get("completed"), [])

    def test_failed_verify_retry_relaunches_same_app_before_later_queue(self):
        other = self.m.Game("B", "Two", self.root, "Steam", "456")
        self.m.save_verify_queue([self.game, other])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log
        launches = []

        def first_launch(appid):
            launches.append(appid)
            with log.open("a", encoding="utf-8") as f:
                f.write(f"Start validating appID {appid}\n")
                f.write(f"AppID {appid} scheduler finished : removed from schedule (result Corrupt game files, state 0x4ae)\n")

        self.m.launch_steam_verify = first_launch
        row = self.m.start_next_steam_verify()
        self.assertEqual(row["appid"], "123")

        def retry_launch(appid):
            launches.append(appid)

        self.m.launch_steam_verify = retry_launch
        retried = self.m.retry_failed_steam_verify()
        self.assertEqual(retried["appid"], "123")
        self.assertEqual(launches, ["123", "123"])
        _, data = self.m._load_verify_queue()
        self.assertEqual(data["in_flight"]["appid"], "123")
        self.assertEqual([r["appid"] for r in data["remaining"]], ["456"])

    def test_verify_retry_refuses_when_current_job_started_and_has_not_failed(self):
        self.m.save_verify_queue([self.game])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log

        def fake_launch(appid):
            with log.open("a", encoding="utf-8") as f:
                f.write(f"Start validating appID {appid}\n")
                f.write(f"AppID {appid} App update changed : Running Update,Validating,\n")

        self.m.launch_steam_verify = fake_launch
        self.m.start_next_steam_verify()
        path, data = self.m._load_verify_queue()
        self.m._resolve_verify_inflight_if_complete(path, data)
        with self.assertRaises(self.m.Stop):
            self.m.retry_failed_steam_verify()

    def test_auto_verify_queue_runs_sequentially_when_log_proves_completion(self):
        other = self.m.Game("B", "Two", self.root, "Steam", "456")
        self.m.save_verify_queue([self.game, other])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log

        def fake_launch(appid):
            with log.open("a", encoding="utf-8") as f:
                f.write(f"Start validating appID {appid}\n")
                f.write(f"AppID {appid} update changed : Running,Validating,\n")
                f.write(f"AppID {appid} scheduler finished : removed from schedule (result No Error, state 0xc)\n")

        self.m.launch_steam_verify = fake_launch
        summary = self.m.run_steam_verify_queue_sequential(timeout_seconds=1)
        self.assertEqual([r["appid"] for r in summary["completed"]], ["123", "456"])
        self.assertEqual(summary["pending"], 0)

    def test_generic_steam_update_verifying_installed_is_not_verify_launch_evidence(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        with log.open("a", encoding="utf-8") as f:
            f.write("AppID 123 scheduler update : Priority Manual, not played for 100 seconds, update disabled for 0 seconds\n")
            f.write("AppID 123 App update changed : Running Update,\n")
            f.write("AppID 123 App update changed : Running Update,Verifying Installed,\n")
            f.write("AppID 123 App update changed : Running Update,\n")
            f.write("AppID 123 scheduler finished : removed from schedule (result No Error, state 0xc)\n")
        status = self.m.steam_validation_status("123", log, 0)
        self.assertFalse(status["started"])
        self.assertFalse(status["completed"])
        self.assertFalse(status["failed"])

    def test_validation_parser_never_prefix_matches_another_appid(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        with log.open("a", encoding="utf-8") as f:
            f.write("Start validating appID 1234\n")
            f.write("AppID 1234 scheduler finished : removed from schedule (result Corrupt game files, state 0x4ae)\n")
        status = self.m.steam_validation_status("123", log, 0)
        self.assertFalse(status["started"])
        self.assertFalse(status["completed"])
        self.assertFalse(status["failed"])

    def test_validation_byte_offset_survives_multibyte_log_prefix(self):
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_bytes("prélude — old\n".encode("utf-8"))
        offset = log.stat().st_size
        with log.open("a", encoding="utf-8") as f:
            f.write("Start validating appID 123\n")
            f.write("AppID 123 scheduler finished : removed from schedule (result No Error, state 0xc)\n")
        status = self.m.steam_validation_status("123", log, offset)
        self.assertTrue(status["completed"])
        self.assertFalse(status["failed"])

    def test_start_next_reports_failed_inflight_instead_of_generic_overlap(self):
        other = self.m.Game("B", "Two", self.root, "Steam", "456")
        self.m.save_verify_queue([self.game, other])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log

        def fake_launch(appid):
            with log.open("a", encoding="utf-8") as f:
                f.write(f"Start validating appID {appid}\n")
                f.write(
                    f"AppID {appid} scheduler finished : removed from schedule "
                    "(result Corrupt game files, state 0x4ae)\n"
                )

        self.m.launch_steam_verify = fake_launch
        first = self.m.start_next_steam_verify()
        self.assertEqual(first["appid"], "123")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.start_next_steam_verify()
        self.assertIn("verification failed for", str(cm.exception))
        self.assertIn("123", str(cm.exception))
        _path, data = self.m._load_verify_queue()
        self.assertEqual(data["in_flight"]["appid"], "123")
        self.assertEqual([row["appid"] for row in data["remaining"]], ["456"])

    def test_verify_log_replacement_stops_queue_without_advancing(self):
        other = self.m.Game("B", "Two", self.root, "Steam", "456")
        self.m.save_verify_queue([self.game, other])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("old content long enough\n", encoding="utf-8")
        st = log.stat()
        path, data = self.m._load_verify_queue()
        row = data["remaining"].pop(0)
        data["in_flight"] = {
            **row,
            "log_path": str(log),
            "start_offset": int(st.st_size),
            "log_dev": int(st.st_dev),
            "log_ino": int(st.st_ino),
            "phase": "launched",
            "launch_recorded_utc": self.m.now_iso(),
        }
        self.m.save_json_atomic(path, data)

        replacement = log.with_suffix(".replacement")
        replacement.write_text(
            "Start validating appID 123\n"
            "AppID 123 scheduler finished : removed from schedule (result No Error, state 0xc)\n",
            encoding="utf-8",
        )
        replacement.replace(log)

        with self.assertRaises(self.m.Stop) as cm:
            self.m.run_steam_verify_queue_sequential(timeout_seconds=1)
        self.assertIn("log changed", str(cm.exception))
        _path, current = self.m._load_verify_queue()
        self.assertEqual(current["in_flight"]["appid"], "123")
        self.assertEqual([row["appid"] for row in current["remaining"]], ["456"])
        self.assertEqual(current.get("completed"), [])

    def test_retry_after_verify_log_replacement_relaunches_same_appid(self):
        other = self.m.Game("B", "Two", self.root, "Steam", "456")
        self.m.save_verify_queue([self.game, other])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("old content long enough\n", encoding="utf-8")
        st = log.stat()
        self.m.steam_content_log_path = lambda: log
        path, data = self.m._load_verify_queue()
        row = data["remaining"].pop(0)
        data["in_flight"] = {
            **row,
            "log_path": str(log),
            "start_offset": int(st.st_size),
            "log_dev": int(st.st_dev),
            "log_ino": int(st.st_ino),
            "phase": "launched",
            "launch_recorded_utc": self.m.now_iso(),
        }
        self.m.save_json_atomic(path, data)

        replacement = log.with_suffix(".replacement")
        replacement.write_text("new log\n", encoding="utf-8")
        replacement.replace(log)
        launched = []
        self.m.launch_steam_verify = lambda appid: launched.append(str(appid))

        retried = self.m.retry_failed_steam_verify()
        self.assertEqual(retried["appid"], "123")
        self.assertEqual(launched, ["123"])
        _path, current = self.m._load_verify_queue()
        self.assertEqual(current["in_flight"]["appid"], "123")
        self.assertEqual(current["in_flight"]["phase"], "launch-intent")
        self.assertEqual([row["appid"] for row in current["remaining"]], ["456"])

    def test_three_game_queue_attributes_third_failure_to_third_game_only(self):
        second = self.m.Game("B", "Two", self.root, "Steam", "123")
        third = self.m.Game("C", "Three", self.root, "Steam", "1234")
        first = self.m.Game("A", "One", self.root, "Steam", "77")
        self.m.save_verify_queue([first, second, third])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log

        def fake_launch(appid):
            with log.open("a", encoding="utf-8") as f:
                f.write(f"Start validating appID {appid}\n")
                result = "Corrupt game files" if str(appid) == "1234" else "No Error"
                f.write(f"AppID {appid} scheduler finished : removed from schedule (result {result}, state 0xc)\n")

        self.m.launch_steam_verify = fake_launch
        with self.assertRaises(self.m.Stop) as cm:
            self.m.run_steam_verify_queue_sequential(timeout_seconds=1, launch_confirm_seconds=0.01)
        self.assertIn("AppID 1234", str(cm.exception))
        _path, data = self.m._load_verify_queue()
        self.assertEqual(data["in_flight"]["appid"], "1234")
        self.assertEqual([r["appid"] for r in data.get("completed", [])], ["77", "123"])

    def test_verify_queue_records_nonempty_log_anchor_at_dispatch(self):
        self.m.save_verify_queue([self.game])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_bytes(b"existing steam history\n")
        self.m.steam_content_log_path = lambda: log
        self.m.launch_steam_verify = lambda appid: None

        row = self.m.start_next_steam_verify()
        self.assertEqual(row["appid"], "123")
        _path, data = self.m._load_verify_queue()
        inflight = data["in_flight"]
        self.assertEqual(inflight["start_offset"], len(b"existing steam history\n"))
        self.assertEqual(inflight["log_anchor_len"], len(b"existing steam history\n"))
        self.assertEqual(
            inflight["log_anchor_sha256"],
            self.m.sha256_bytes(b"existing steam history\n"),
        )

    def test_verify_detects_in_place_truncate_and_regrow_past_old_offset(self):
        log = self.steam_root / "logs" / "content_log.txt"
        original = b"old history that establishes continuity\n"
        log.write_bytes(original)
        st = log.stat()
        anchor_len, anchor_sha = self.m._steam_log_anchor(log, len(original))
        self.assertIsNotNone(anchor_sha)

        # Simulate Steam truncating the same inode and quickly regrowing beyond
        # the old offset before the next poll. Device/inode and size alone would
        # accept this as continuous and could parse unrelated AppID records.
        with log.open("wb") as f:
            f.write(b"replacement history with different bytes and enough padding " * 3)
            f.write(b"Start validating appID 123\n")
            f.write(b"AppID 123 scheduler finished : removed from schedule (result No Error, state 0xc)\n")
        new_st = log.stat()
        self.assertEqual((st.st_dev, st.st_ino), (new_st.st_dev, new_st.st_ino))
        self.assertGreaterEqual(new_st.st_size, len(original))

        status = self.m.steam_validation_status(
            "123", log, len(original),
            expected_dev=int(st.st_dev), expected_ino=int(st.st_ino),
            expected_anchor_len=anchor_len, expected_anchor_sha256=anchor_sha,
        )
        self.assertTrue(status["log_reset"])
        self.assertFalse(status["completed"])

    def test_in_place_log_rewrite_stops_queue_before_later_appid(self):
        other = self.m.Game("B", "Two", self.root, "Steam", "456")
        self.m.save_verify_queue([self.game, other])
        log = self.steam_root / "logs" / "content_log.txt"
        original = b"old steam content history\n"
        log.write_bytes(original)
        st = log.stat()
        anchor_len, anchor_sha = self.m._steam_log_anchor(log, len(original))
        path, data = self.m._load_verify_queue()
        row = data["remaining"].pop(0)
        data["in_flight"] = {
            **row,
            "log_path": str(log),
            "start_offset": len(original),
            "log_dev": int(st.st_dev),
            "log_ino": int(st.st_ino),
            "log_anchor_len": anchor_len,
            "log_anchor_sha256": anchor_sha,
            "phase": "launched",
            "launch_recorded_utc": self.m.now_iso(),
        }
        self.m.save_json_atomic(path, data)

        with log.open("wb") as f:
            f.write(b"totally new content that regrew beyond the persisted offset " * 4)
            f.write(b"Start validating appID 123\n")
            f.write(b"AppID 123 scheduler finished : removed from schedule (result No Error, state 0xc)\n")

        with self.assertRaises(self.m.Stop) as cm:
            self.m.run_steam_verify_queue_sequential(timeout_seconds=1)
        self.assertIn("log changed", str(cm.exception))
        _path, current = self.m._load_verify_queue()
        self.assertEqual(current["in_flight"]["appid"], "123")
        self.assertEqual([r["appid"] for r in current["remaining"]], ["456"])
        self.assertEqual(current.get("completed"), [])

    def test_clean_selection_can_select_unmanaged_games(self):
        unmanaged = self.m.Game("B", "Unmanaged", self.root, "Steam", "999")
        selected = self.m.parse_selection("ALL", [self.game, unmanaged], "clean")
        self.assertEqual(len(selected), 2)

    def test_launch_scrub_removes_only_deleted_proxy_override(self):
        existing = (
            'MANGOHUD=1 WINEDLLOVERRIDES="dxgi=n,b;dinput8=n,b" '
            'gamescope -f %command% -dx12'
        )
        cleaned = self.m.scrub_deep_clean_launch_options(existing, {"dxgi.dll"})
        self.assertNotIn("dxgi=n,b", cleaned)
        self.assertIn('WINEDLLOVERRIDES="dinput8=n,b"', cleaned)
        self.assertIn("MANGOHUD=1", cleaned)
        self.assertIn("gamescope -f %command% -dx12", cleaned)

    def test_launch_scrub_removes_empty_override_assignment(self):
        existing = 'WINEDLLOVERRIDES="dxgi=n,b" MANGOHUD=1 %command%'
        cleaned = self.m.scrub_deep_clean_launch_options(existing, {"dxgi.dll"})
        self.assertNotIn("WINEDLLOVERRIDES", cleaned)
        self.assertEqual(cleaned, "MANGOHUD=1 %command%")

    def test_deep_clean_steam_launch_scrub_is_transactional(self):
        config = self.steam_root / "userdata" / "42" / "config" / "localconfig.vdf"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            '"UserLocalConfigStore"\n{\n'
            '\t"Software"\n\t{\n'
            '\t\t"Valve"\n\t\t{\n'
            '\t\t\t"Steam"\n\t\t\t{\n'
            '\t\t\t\t"apps"\n\t\t\t\t{\n'
            '\t\t\t\t\t"123"\n\t\t\t\t\t{\n'
            '\t\t\t\t\t\t"LaunchOptions"\t\t"MANGOHUD=1 WINEDLLOVERRIDES=\\"dxgi=n,b;dinput8=n,b\\" %command%"\n'
            '\t\t\t\t\t}\n'
            '\t\t\t\t}\n'
            '\t\t\t}\n'
            '\t\t}\n'
            '\t}\n'
            '}\n',
            encoding="utf-8",
        )
        shortcuts = config.parent / "shortcuts.vdf"
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        self.m.choose_steam_user_config = lambda games, assume_yes=False: {
            "localconfig": config, "shortcuts": shortcuts, "userid": "42",
            "root": self.steam_root, "score": 1,
        }
        candidate = self.m.DeepCleanCandidate(
            self.target / "dxgi.dll", "file", "graphics injector/proxy signature", 1
        )
        rows = self.m.scrub_deep_clean_launch_options_batch([(self.game, [candidate])], assume_yes=True)
        self.assertEqual(rows[0]["status"], "scrubbed")
        value = self.m.read_localconfig_launch_options(config, "123")
        self.assertNotIn("dxgi=n,b", value)
        self.assertIn("dinput8=n,b", value)
        self.assertIn("MANGOHUD=1", value)
        self.assertEqual(self.m.load_pending_steam_transactions(), [])


    def test_deep_clean_nonsteam_launch_scrub_is_surgical(self):
        game = self.m.Game(
            "B", "NonSteam Fixture", self.root, "Non-Steam", None, None,
            self.target / "game.exe", self.target,
        )
        launch = 'MANGOHUD=1 WINEDLLOVERRIDES="dxgi=n,b;dinput8=n,b" %command% -dx12'
        config = self.steam_root / "userdata" / "42" / "config" / "localconfig.vdf"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('"UserLocalConfigStore"\n{\n}\n', encoding="utf-8")
        shortcuts = config.parent / "shortcuts.vdf"
        shortcuts.write_bytes(_shortcuts_fixture(game, launch))
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        self.m.choose_steam_user_config = lambda games, assume_yes=False: {
            "localconfig": config, "shortcuts": shortcuts, "userid": "42",
            "root": self.steam_root, "score": 1,
        }
        candidate = self.m.DeepCleanCandidate(
            self.target / "dxgi.dll", "file", "graphics injector/proxy signature", 1
        )
        rows = self.m.scrub_deep_clean_launch_options_batch([(game, [candidate])], assume_yes=True)
        self.assertEqual(rows[0]["status"], "scrubbed")
        parsed = self.m.parse_shortcuts_spans(shortcuts.read_bytes())
        obj = self.m.match_shortcut_span(game, parsed)
        value = self.m._shortcut_string(obj, "LaunchOptions")
        self.assertNotIn("dxgi=n,b", value)
        self.assertIn("dinput8=n,b", value)
        self.assertIn("MANGOHUD=1", value)
        self.assertIn("%command% -dx12", value)
        self.assertEqual(self.m.load_pending_steam_transactions(), [])

    def test_deep_clean_nonsteam_scrub_rolls_back_on_postwrite_failure(self):
        game = self.m.Game(
            "B", "NonSteam Fixture", self.root, "Non-Steam", None, None,
            self.target / "game.exe", self.target,
        )
        launch = 'WINEDLLOVERRIDES="dxgi=n,b" MANGOHUD=1 %command%'
        config = self.steam_root / "userdata" / "42" / "config" / "localconfig.vdf"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('"UserLocalConfigStore"\n{\n}\n', encoding="utf-8")
        shortcuts = config.parent / "shortcuts.vdf"
        original = _shortcuts_fixture(game, launch)
        shortcuts.write_bytes(original)
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        self.m.choose_steam_user_config = lambda games, assume_yes=False: {
            "localconfig": config, "shortcuts": shortcuts, "userid": "42",
            "root": self.steam_root, "score": 1,
        }
        candidate = self.m.DeepCleanCandidate(
            self.target / "dxgi.dll", "file", "graphics injector/proxy signature", 1
        )
        original_complete = self.m.complete_steam_transaction
        fired = {"done": False}
        def fail_once(path, data):
            if not fired["done"]:
                fired["done"] = True
                raise OSError("simulated journal finalization failure")
            return original_complete(path, data)
        self.m.complete_steam_transaction = fail_once
        with self.assertRaises(self.m.Stop):
            self.m.scrub_deep_clean_launch_options_batch([(game, [candidate])], assume_yes=True)
        self.assertEqual(shortcuts.read_bytes(), original)
        self.assertEqual(self.m.load_pending_steam_transactions(), [])



    def test_new_deep_clean_extends_active_verify_queue_instead_of_overwriting_it(self):
        second = self.m.Game("B", "Two", self.root, "Steam", "456")
        third = self.m.Game("C", "Three", self.root, "Steam", "789")
        self.m.save_verify_queue([self.game, second])
        log = self.steam_root / "logs" / "content_log.txt"
        log.write_text("", encoding="utf-8")
        self.m.steam_content_log_path = lambda: log
        self.m.launch_steam_verify = lambda appid: None
        self.m.start_next_steam_verify()

        self.m.save_verify_queue([second, third])
        _path, data = self.m._load_verify_queue()
        self.assertEqual(data["in_flight"]["appid"], "123")
        self.assertEqual([row["appid"] for row in data["remaining"]], ["456", "789"])

    def test_deep_clean_commits_verify_queue_before_first_destructive_apply(self):
        candidate_path = self.target / "dxgi.dll"
        candidate_path.write_bytes(b"ReShade proxy")
        candidate = self.m.DeepCleanCandidate(
            candidate_path, "file", "graphics injector/proxy signature", candidate_path.stat().st_size,
            sha256=self.m.sha256_file(candidate_path),
        )
        self.m.deep_clean_scan_game = lambda game: [candidate]
        self.m.scrub_deep_clean_launch_options_batch = lambda plans, assume_yes=False: []
        self.m.write_batch_report = lambda *args, **kwargs: self.base / "report.md"
        observed = {"queue_before_apply": False}

        real_apply = self.m.deep_clean_apply_game
        def inspect_then_apply(game, candidates):
            queue_path = self.m._verify_queue_path()
            self.assertTrue(queue_path.is_file())
            _path, data = self.m._load_verify_queue()
            self.assertEqual([row["appid"] for row in data["remaining"]], ["123"])
            observed["queue_before_apply"] = True
            return real_apply(game, candidates)
        self.m.deep_clean_apply_game = inspect_then_apply
        # Do not actually launch Steam validation in this unit test.
        self.m.start_next_steam_verify = lambda: {"name": self.game.name, "appid": self.game.appid}

        self.m.batch_deep_clean(
            [self.game], self.base, assume_yes=True, include_nonsteam=False, auto_verify=False
        )
        self.assertTrue(observed["queue_before_apply"])

    def test_failed_steam_clean_is_still_enqueued_for_verification(self):
        candidate = self.m.DeepCleanCandidate(
            self.target / "dxgi.dll", "file", "graphics injector/proxy signature", 1
        )
        self.m.deep_clean_scan_game = lambda game: [candidate]
        self.m.scrub_deep_clean_launch_options_batch = lambda plans, assume_yes=False: []
        self.m.deep_clean_apply_game = lambda game, candidates: (_ for _ in ()).throw(OSError("simulated partial clean failure"))
        self.m.write_batch_report = lambda *args, **kwargs: self.base / "report.md"
        captured = []
        def capture_queue(games):
            captured.extend(games)
            return None
        self.m.save_verify_queue = capture_queue

        self.m.batch_deep_clean(
            [self.game], self.base, assume_yes=True, include_nonsteam=False, auto_verify=False
        )
        self.assertEqual([g.appid for g in captured], ["123"])



    def test_cli_deep_clean_auto_verify_is_default_with_explicit_opt_out(self):
        captured = []
        self.m.scan_for_install = lambda drive: [self.game]
        def fake_batch(games, drive, **kwargs):
            captured.append(kwargs["auto_verify"])
        self.m.batch_deep_clean = fake_batch

        rc = self.m.cli_main(["--deep-clean-all", "--drive", str(self.base)])
        self.assertEqual(rc, 0)
        rc = self.m.cli_main(["--deep-clean-all", "--no-auto-verify", "--drive", str(self.base)])
        self.assertEqual(rc, 0)
        self.assertEqual(captured, [True, False])



    def test_deep_clean_scan_prunes_nested_mount_subtree(self):
        mounted = self.root / "MountedContent"
        mounted.mkdir()
        hidden = mounted / "DLSSTweaks.ini"
        hidden.write_text("x=1", encoding="utf-8")
        real_mount = self.m._path_is_mount
        self.m._path_is_mount = lambda p: p.resolve(strict=False) == mounted.resolve(strict=False)
        messages = []
        self.m.warn = messages.append
        try:
            candidates = self.m.deep_clean_scan_game(self.game)
        finally:
            self.m._path_is_mount = real_mount
        self.assertFalse(any(c.path == hidden for c in candidates))
        self.assertTrue(any("skipped nested mount point" in msg for msg in messages))

    def test_deep_clean_refuses_when_proton_like_process_has_game_cwd(self):
        import subprocess
        proxy = self.target / "dxgi.dll"
        proxy.write_bytes(b"ReShade")
        proc = subprocess.Popen(["sleep", "10"], cwd=self.root)
        try:
            candidates = [self.m.DeepCleanCandidate(proxy, "file", "fixture", proxy.stat().st_size)]
            with self.assertRaises(self.m.Stop) as cm:
                self.m.deep_clean_apply_game(self.game, candidates)
            self.assertIn("Game process still using", str(cm.exception))
            self.assertTrue(proxy.exists())
            self.assertTrue(any(str(proc.pid) in row and "[cwd]" in row for row in self.m._running_processes_under_root(self.root)))
        finally:
            proc.terminate()
            proc.wait(timeout=5)



    def test_deep_clean_refuses_file_bytes_drift_after_preview(self):
        candidate_path = self.root / "DLSSTweaks.ini"
        candidate_path.write_text("before", encoding="utf-8")
        candidates = self.m.deep_clean_scan_game(self.game)
        match = [c for c in candidates if c.path == candidate_path]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0].kind, "file")
        self.assertTrue(match[0].sha256)

        candidate_path.write_text("after!", encoding="utf-8")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.deep_clean_apply_game(self.game, candidates)
        self.assertIn("bytes changed after preview", str(cm.exception))
        self.assertTrue(candidate_path.is_file())
        self.assertEqual(candidate_path.read_text(encoding="utf-8"), "after!")

    def test_deep_clean_refuses_candidate_type_drift_after_preview(self):
        candidate_path = self.root / "DLSSTweaks.ini"
        candidate_path.write_text("[fixture]\n", encoding="utf-8")
        candidates = self.m.deep_clean_scan_game(self.game)
        match = [c for c in candidates if c.path == candidate_path]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0].kind, "file")

        candidate_path.unlink()
        candidate_path.mkdir()
        sentinel = candidate_path / "must-survive.txt"
        sentinel.write_text("keep", encoding="utf-8")

        with self.assertRaises(self.m.Stop) as cm:
            self.m.deep_clean_apply_game(self.game, candidates)
        self.assertIn("type changed after preview", str(cm.exception))
        self.assertTrue(sentinel.is_file())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_deep_clean_refuses_special_nodes_inside_directory_candidate(self):
        import os
        opti = self.target / "OptiScaler"
        opti.mkdir()
        fifo = opti / "unexpected.fifo"
        os.mkfifo(fifo)
        candidates = self.m.deep_clean_scan_game(self.game)
        self.assertTrue(any(c.path == opti and c.kind == "dir" for c in candidates))

        with self.assertRaises(self.m.Stop) as cm:
            self.m.deep_clean_apply_game(self.game, candidates)
        self.assertIn("filesystem hazard", str(cm.exception))
        self.assertTrue(opti.is_dir())
        self.assertTrue(fifo.exists())

    def test_partial_deep_clean_failure_writes_thin_receipt(self):
        first = self.target / "dxgi.dll"
        second = self.target / "version.dll"
        first.write_bytes(b"ReShade first")
        second.write_bytes(b"ReShade second")
        candidates = [
            self.m.DeepCleanCandidate(first, "file", "graphics injector/proxy signature", first.stat().st_size),
            self.m.DeepCleanCandidate(second, "file", "graphics injector/proxy signature", second.stat().st_size),
        ]
        real_replaceable = self.m.ensure_file_replaceable
        calls = {"n": 0}
        def fail_second(path, label):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("simulated deletion failure")
            return real_replaceable(path, label)
        self.m.ensure_file_replaceable = fail_second

        with self.assertRaises(self.m.Stop) as cm:
            self.m.deep_clean_apply_game(self.game, candidates)
        self.assertIn("partial Deep Clean receipt", str(cm.exception))
        receipt = self.m.STATE_ROOT / "deep-clean-receipts" / f"{self.m.target_key(self.game.root)}.json"
        data = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "partial-failed")
        self.assertEqual(len(data["removed"]), 1)
        self.assertIn("simulated deletion failure", data["error"])

    def test_deep_clean_writes_in_progress_receipt_before_first_deletion(self):
        victim = self.target / "dxgi.dll"
        victim.write_bytes(b"ReShade proxy")
        candidate = self.m.DeepCleanCandidate(
            victim, "file", "graphics injector/proxy signature", victim.stat().st_size,
            self.m.sha256_file(victim),
        )
        observed = {}
        real_replaceable = self.m.ensure_file_replaceable

        def inspect_before_delete(path, label):
            receipt = self.m.STATE_ROOT / "deep-clean-receipts" / f"{self.m.target_key(self.game.root)}.json"
            observed["exists"] = receipt.is_file()
            if receipt.is_file():
                observed["data"] = json.loads(receipt.read_text(encoding="utf-8"))
            raise OSError("stop before deletion")

        with patch.object(self.m, "ensure_file_replaceable", side_effect=inspect_before_delete):
            with self.assertRaises(self.m.Stop):
                self.m.deep_clean_apply_game(self.game, [candidate])

        self.assertTrue(observed.get("exists"))
        self.assertEqual(observed["data"]["status"], "in-progress")
        self.assertEqual(observed["data"]["planned_count"], 1)
        self.assertTrue(victim.is_file())

    def test_deep_clean_state_purge_atomically_retires_before_recursive_cleanup(self):
        state_dir = self.m.state_dir_for(self.target)
        (state_dir / "baseline-backup").mkdir(parents=True)
        (state_dir / "baseline-backup" / "payload.bin").write_bytes(b"recovery")
        self.m.save_json_atomic(state_dir / "baseline.json", {
            "schema": 13,
            "target_dir": str(self.target),
            "name": self.game.name,
            "source": "Steam",
            "appid": "123",
        })
        real_rmtree = self.m.shutil.rmtree

        def fail_trash_cleanup(path, *args, **kwargs):
            path = Path(path)
            if self.m._state_trash_root() in path.parents:
                raise OSError("simulated crash during trash cleanup")
            return real_rmtree(path, *args, **kwargs)

        messages = []
        self.m.warn = messages.append
        with patch.object(self.m.shutil, "rmtree", side_effect=fail_trash_cleanup):
            removed = self.m._purge_game_rtxengine_state(self.game)

        self.assertEqual(removed, 1)
        self.assertFalse(state_dir.exists(), "active state name must disappear before recursive cleanup")
        trash = self.m._state_trash_root()
        tombstones = list(trash.iterdir())
        self.assertEqual(len(tombstones), 1)
        self.assertTrue((tombstones[0] / "baseline.json").is_file())
        self.assertTrue(any("remains in trash" in msg for msg in messages))

    def test_state_purge_surfaces_corrupt_json_instead_of_treating_it_as_unrelated(self):
        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True)
        (state_dir / "baseline.json").write_text("{broken", encoding="utf-8")
        warnings = []
        self.m.warn = warnings.append
        removed = self.m._purge_game_rtxengine_state(self.game)
        self.assertEqual(removed, 0)
        self.assertTrue(state_dir.exists())
        self.assertTrue(any("Could not classify rtxEngine state" in msg for msg in warnings))

    def test_deep_clean_state_purge_never_follows_symlinked_state_directory(self):
        targets = self.m.STATE_ROOT / "targets"
        targets.mkdir(parents=True)
        outside = self.base / "outside-state"
        outside.mkdir()
        sentinel = outside / "KEEP.txt"
        sentinel.write_text("keep", encoding="utf-8")
        (outside / "baseline.json").write_text(json.dumps({
            "schema": 13,
            "target_dir": str(self.target),
            "name": self.game.name,
            "source": "Steam",
            "appid": "123",
        }), encoding="utf-8")
        link = targets / self.m.target_key(self.target)
        link.symlink_to(outside, target_is_directory=True)
        messages = []
        self.m.warn = messages.append
        removed = self.m._purge_game_rtxengine_state(self.game)
        self.assertEqual(removed, 0)
        self.assertTrue(link.is_symlink())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        self.assertTrue(any("Refusing symlinked" in msg for msg in messages))

    def test_deep_clean_state_purge_refuses_mismatched_state_directory_identity(self):
        wrong = self.m.STATE_ROOT / "targets" / "not-the-target-hash"
        wrong.mkdir(parents=True)
        self.m.save_json_atomic(wrong / "baseline.json", {
            "schema": 13,
            "target_dir": str(self.target),
            "name": self.game.name,
            "source": "Steam",
            "appid": "123",
        })
        messages = []
        self.m.warn = messages.append
        removed = self.m._purge_game_rtxengine_state(self.game)
        self.assertEqual(removed, 0)
        self.assertTrue(wrong.exists())
        self.assertTrue(any("state directory hash/target mismatch" in msg for msg in messages))


if __name__ == "__main__":
    unittest.main(verbosity=2)
