import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "rtxengine.py"


def load_engine():
    name = f"rtxengine_v13_pristine_test_{id(object())}"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PristineResetTests(unittest.TestCase):
    def setUp(self):
        self.m = load_engine()
        # Synthetic tests must not depend on Lauren's running Steam client.
        self.m._steam_process_names = lambda: []
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.m.STATE_ROOT = self.base / "state"
        self.lib = self.base / "SteamLibrary"
        self.steamapps = self.lib / "steamapps"
        self.common = self.steamapps / "common"
        self.root = self.common / "Fixture"
        self.target = self.root / "Binaries" / "Win64"
        self.target.mkdir(parents=True)
        self.manifest = self.steamapps / "appmanifest_123.acf"
        self.manifest.write_text(
            '"AppState"\n{\n\t"appid"\t\t"123"\n\t"name"\t\t"Fixture"\n\t"installdir"\t\t"Fixture"\n}\n',
            encoding="utf-8",
        )
        self.game = self.m.Game(
            "A", "Fixture", self.root, "Steam", "123", self.manifest,
            self.target / "game.exe", self.target,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_pristine_accepts_exact_manifest_root(self):
        root, manifest, data = self.m._validate_pristine_steam_game(self.game)
        self.assertEqual(root, self.root.resolve())
        self.assertEqual(manifest, self.manifest.resolve())
        self.assertEqual(data["appid"], "123")
        self.assertEqual(data["installdir"], "Fixture")

    def test_validate_pristine_refuses_nonsteam_and_root_mismatch(self):
        nonsteam = self.m.Game("B", "Loose", self.base / "Loose", "Non-Steam")
        (self.base / "Loose").mkdir()
        with self.assertRaises(self.m.Stop):
            self.m._validate_pristine_steam_game(nonsteam)

        wrong = self.base / "Wrong"
        wrong.mkdir()
        bad = self.m.Game("C", "Fixture", wrong, "Steam", "123", self.manifest)
        with self.assertRaises(self.m.Stop):
            self.m._validate_pristine_steam_game(bad)

    def test_pristine_apply_wipes_every_payload_but_keeps_root_and_thin_receipt(self):
        (self.target / "game.exe").write_bytes(b"game")
        (self.target / "nvngx_dlss.dll").write_bytes(b"DLSS Updater replacement")
        (self.target / "dxgi.dll").write_bytes(b"ReShade")
        (self.root / "user-config.ini").write_text("local", encoding="utf-8")
        extra = self.root / "mods" / "nested"
        extra.mkdir(parents=True)
        (extra / "payload.bin").write_bytes(b"x" * 32)

        state = self.m.state_dir_for(self.target)
        state.mkdir(parents=True)
        self.m.save_json_atomic(state / "baseline.json", {
            "schema": 13,
            "target_dir": str(self.target),
            "name": self.game.name,
            "source": "Steam",
            "appid": "123",
        })

        row = self.m.pristine_steam_reset_apply_game(self.game)
        self.assertEqual(row["status"], "wiped")
        self.assertTrue(self.root.is_dir())
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertFalse(state.exists())

        receipt = Path(row["receipt"])
        data = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "wiped-pending-steam-verify")
        self.assertEqual(data["mode"], "steam-pristine-reset-no-payload-backup")
        self.assertGreaterEqual(data["inventory_before"]["files"], 5)
        self.assertNotIn("removed", data, "Pristine receipt must stay thin; do not record every deleted file")

    def test_pristine_rechecks_each_directory_for_late_filesystem_hazards(self):
        child = self.root / "mods"
        child.mkdir()
        payload = child / "payload.bin"
        payload.write_bytes(b"keep")
        self.m.steam_running = lambda: False
        self.m._running_processes_under_root = lambda root: []
        real_hazards = self.m._pristine_tree_hazards
        calls = []

        def staged_hazards(path):
            path = Path(path).resolve(strict=False)
            calls.append(path)
            if path == self.root.resolve():
                return []
            if path == child.resolve():
                return [f"nested mount point: {child}"]
            return real_hazards(path)

        self.m._pristine_tree_hazards = staged_hazards
        try:
            with self.assertRaises(self.m.Stop) as cm:
                self.m.pristine_steam_reset_apply_game(self.game)
        finally:
            self.m._pristine_tree_hazards = real_hazards
        self.assertIn("filesystem hazard", str(cm.exception))
        self.assertTrue(payload.is_file())
        self.assertIn(child.resolve(), calls)

    def test_pristine_writes_in_progress_receipt_before_first_delete(self):
        victim = self.root / "loose-mod.bin"
        victim.write_bytes(b"mod")
        real_unlink = self.m.durable_unlink
        observed = {}

        def inspect_then_fail(path, *args, **kwargs):
            receipt = self.m.STATE_ROOT / "pristine-reset-receipts" / "steam-123.json"
            observed["exists"] = receipt.is_file()
            if receipt.is_file():
                observed["data"] = json.loads(receipt.read_text(encoding="utf-8"))
            raise OSError("stop before first unlink")

        self.m.durable_unlink = inspect_then_fail
        try:
            with self.assertRaises(self.m.Stop):
                self.m.pristine_steam_reset_apply_game(self.game)
        finally:
            self.m.durable_unlink = real_unlink

        self.assertTrue(observed.get("exists"))
        self.assertEqual(observed["data"]["status"], "in-progress")
        self.assertTrue(victim.is_file())

    def test_pristine_recursive_deletion_flushes_filesystem_before_success(self):
        (self.target / "game.exe").write_bytes(b"game")
        mods = self.root / "mods"
        mods.mkdir()
        (mods / "payload.bin").write_bytes(b"mod")
        calls = []
        real_sync = self.m._sync_filesystem
        self.m._sync_filesystem = lambda path: calls.append(Path(path).resolve())
        try:
            row = self.m.pristine_steam_reset_apply_game(self.game)
        finally:
            self.m._sync_filesystem = real_sync
        self.assertEqual(row["status"], "wiped")
        self.assertTrue(calls)
        self.assertTrue(all(path == self.root.resolve() for path in calls))

    def test_pristine_apply_partial_failure_writes_receipt(self):
        blocked = self.root / "blocked"
        blocked.mkdir()
        (blocked / "file.bin").write_bytes(b"x")
        real_rmtree = self.m.shutil.rmtree

        def fail_once(path, *args, **kwargs):
            if Path(path) == blocked:
                raise PermissionError("simulated blocked subtree")
            return real_rmtree(path, *args, **kwargs)

        self.m.shutil.rmtree = fail_once
        try:
            with self.assertRaises(self.m.Stop) as cm:
                self.m.pristine_steam_reset_apply_game(self.game)
        finally:
            self.m.shutil.rmtree = real_rmtree
        self.assertIn("partial Pristine Reset receipt", str(cm.exception))
        receipt = self.m.STATE_ROOT / "pristine-reset-receipts" / "steam-123.json"
        data = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "partial-failed")
        self.assertIn("simulated blocked subtree", data["error"])

    def test_pristine_marks_managed_state_recovery_before_first_deletion(self):
        payload = self.root / "mod.bin"
        payload.write_bytes(b"mod")
        state = self.m.state_dir_for(self.target)
        state.mkdir(parents=True)
        self.m.save_json_atomic(state / "baseline.json", {
            "schema": 13,
            "target_dir": str(self.target),
            "name": self.game.name,
            "source": "Steam",
            "appid": "123",
            "status": "active",
        })
        real_unlink = self.m.durable_unlink
        observed = {"pending": False}
        def inspect_then_unlink(path, *args, **kwargs):
            if Path(path) == payload:
                data = json.loads((state / "baseline.json").read_text(encoding="utf-8"))
                self.assertEqual(data["status"], "destructive-pending")
                self.assertEqual(data["destructive_pending"]["mode"], "pristine-reset")
                observed["pending"] = True
            return real_unlink(path, *args, **kwargs)
        self.m.durable_unlink = inspect_then_unlink
        try:
            self.m.pristine_steam_reset_apply_game(self.game)
        finally:
            self.m.durable_unlink = real_unlink
        self.assertTrue(observed["pending"])

    def test_partial_pristine_attempt_retires_stale_managed_state(self):
        blocked = self.root / "blocked"
        blocked.mkdir()
        (blocked / "file.bin").write_bytes(b"x")
        state = self.m.state_dir_for(self.target)
        state.mkdir(parents=True)
        self.m.save_json_atomic(state / "baseline.json", {
            "schema": 13,
            "target_dir": str(self.target),
            "name": self.game.name,
            "source": "Steam",
            "appid": "123",
        })
        real_rmtree = self.m.shutil.rmtree

        def destructive_then_fail(path, *args, **kwargs):
            if Path(path) == blocked:
                # Model rmtree deleting a child before encountering a later error.
                (blocked / "file.bin").unlink()
                raise PermissionError("failed after partial subtree mutation")
            return real_rmtree(path, *args, **kwargs)

        self.m.shutil.rmtree = destructive_then_fail
        try:
            with self.assertRaises(self.m.Stop):
                self.m.pristine_steam_reset_apply_game(self.game)
        finally:
            self.m.shutil.rmtree = real_rmtree
        self.assertFalse(state.exists(), "stale active baseline must be retired after any destructive attempt")
        receipt = self.m.STATE_ROOT / "pristine-reset-receipts" / "steam-123.json"
        data = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "partial-failed")
        self.assertEqual(data["state_dirs_purged"], 1)

    def test_pristine_refuses_unattended_run_while_steam_is_open(self):
        self.m.steam_running = lambda: True
        with self.assertRaises(self.m.Stop) as cm:
            self.m._ensure_steam_stopped_for_pristine(assume_yes=True)
        self.assertIn("Steam is running", str(cm.exception))

    def test_pristine_selection_is_steam_only(self):
        nonroot = self.base / "NonSteam"
        nonroot.mkdir()
        nongame = self.m.Game("B", "Loose", nonroot, "Non-Steam")
        selected = self.m.parse_selection("ALL", [self.game, nongame], "pristine")
        self.assertEqual(selected, [self.game])
        with self.assertRaises(self.m.Stop):
            self.m.parse_selection("B", [self.game, nongame], "pristine")

    def test_batch_pristine_queues_repair_even_when_wipe_fails(self):
        (self.target / "game.exe").write_bytes(b"game")
        self.m._ensure_steam_stopped_for_pristine = lambda assume_yes=False: None
        self.m.restore_launch_options_batch = lambda *args, **kwargs: []
        self.m.deep_clean_scan_game = lambda game: []
        self.m.scrub_deep_clean_launch_options_batch = lambda *args, **kwargs: []
        self.m.pristine_steam_reset_apply_game = lambda game: (_ for _ in ()).throw(OSError("simulated wipe failure"))
        self.m.write_batch_report = lambda *args, **kwargs: self.base / "report.md"
        captured = {"queued": [], "auto": 0}

        def save_queue(games):
            captured["queued"] = list(games)
            return self.base / "queue.json"

        def run_auto():
            captured["auto"] += 1
            return {"completed": [], "pending": 1}

        self.m.save_verify_queue = save_queue
        self.m.run_steam_verify_queue_sequential = run_auto
        self.m.batch_pristine_steam_reset([self.game], self.base, assume_yes=True, auto_verify=True)
        self.assertEqual([g.appid for g in captured["queued"]], ["123"])
        self.assertEqual(captured["auto"], 1)


    def test_pristine_unlinks_external_symlink_without_touching_target(self):
        outside = self.base / "Outside"
        outside.mkdir()
        sentinel = outside / "KEEP.txt"
        sentinel.write_text("keep", encoding="utf-8")
        link = self.root / "external-link"
        link.symlink_to(outside, target_is_directory=True)
        (self.target / "game.exe").write_bytes(b"game")

        row = self.m.pristine_steam_reset_apply_game(self.game)
        self.assertEqual(row["status"], "wiped")
        self.assertTrue(sentinel.is_file())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        self.assertFalse(link.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_pristine_hazard_scan_prunes_nested_mount_before_descending(self):
        import os
        mounted = self.root / "MountedContent"
        mounted.mkdir()
        fifo = mounted / "inside.fifo"
        os.mkfifo(fifo)
        real_mount = self.m._path_is_mount
        self.m._path_is_mount = lambda p: p.resolve(strict=False) == mounted.resolve(strict=False)
        try:
            hazards = self.m._pristine_tree_hazards(self.root)
        finally:
            self.m._path_is_mount = real_mount
        self.assertTrue(any("nested mount point" in h for h in hazards))
        self.assertFalse(any("special filesystem node" in h and "inside.fifo" in h for h in hazards))

    def test_pristine_refuses_special_filesystem_nodes_before_deletion(self):
        import os
        (self.target / "game.exe").write_bytes(b"game")
        fifo = self.root / "unexpected.fifo"
        os.mkfifo(fifo)
        with self.assertRaises(self.m.Stop) as cm:
            self.m.pristine_steam_reset_apply_game(self.game)
        self.assertIn("filesystem hazard", str(cm.exception))
        self.assertTrue((self.target / "game.exe").is_file())
        self.assertTrue(fifo.exists())

    def test_pristine_refuses_proton_like_process_with_external_exe_but_game_cwd(self):
        import subprocess
        (self.target / "game.exe").write_bytes(b"game")
        proc = subprocess.Popen(["sleep", "10"], cwd=self.root)
        try:
            with self.assertRaises(self.m.Stop) as cm:
                self.m.pristine_steam_reset_apply_game(self.game)
            self.assertIn("Game process still running", str(cm.exception))
            self.assertTrue((self.target / "game.exe").is_file())
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_pristine_apply_refuses_if_steam_restarts_after_preview(self):
        (self.target / "game.exe").write_bytes(b"game")
        self.m.steam_running = lambda: True
        with self.assertRaises(self.m.Stop) as cm:
            self.m.pristine_steam_reset_apply_game(self.game)
        self.assertIn("Steam restarted", str(cm.exception))
        self.assertTrue((self.target / "game.exe").is_file())

    def test_pristine_batch_commits_repair_queue_before_wipe(self):
        (self.target / "game.exe").write_bytes(b"game")
        self.m._ensure_steam_stopped_for_pristine = lambda assume_yes=False: None
        self.m.restore_launch_options_batch = lambda *args, **kwargs: []
        self.m.deep_clean_scan_game = lambda game: []
        self.m.scrub_deep_clean_launch_options_batch = lambda *args, **kwargs: []
        self.m.write_batch_report = lambda *args, **kwargs: self.base / "report.md"
        order = []

        def save_queue(games):
            order.append("queue")
            return self.base / "queue.json"

        def wipe(game):
            order.append("wipe")
            return {"game": game.name, "appid": game.appid, "status": "wiped", "target": str(game.root)}

        self.m.save_verify_queue = save_queue
        self.m.pristine_steam_reset_apply_game = wipe
        self.m.run_steam_verify_queue_sequential = lambda: {"completed": [], "pending": 1}
        self.m.batch_pristine_steam_reset([self.game], self.base, assume_yes=True, auto_verify=True)
        self.assertEqual(order[:2], ["queue", "wipe"])

    def test_cli_pristine_requires_second_destructive_acknowledgement(self):
        called = []
        self.m.scan_for_install = lambda drive: called.append("scan") or [self.game]
        rc = self.m.cli_main(["--pristine-steam-all", "--drive", str(self.base)])
        self.assertEqual(rc, 2)
        self.assertEqual(called, [], "CLI must refuse before scanning/mutating without --confirm-pristine")

    def test_cli_pristine_auto_verify_default_and_opt_out(self):
        captured = []
        self.m.scan_for_install = lambda drive: [self.game]
        self.m.batch_pristine_steam_reset = lambda games, drive, **kwargs: captured.append(kwargs["auto_verify"])
        rc = self.m.cli_main(["--pristine-steam-all", "--confirm-pristine", "--drive", str(self.base)])
        self.assertEqual(rc, 0)
        rc = self.m.cli_main(["--pristine-steam-all", "--confirm-pristine", "--no-auto-verify", "--drive", str(self.base)])
        self.assertEqual(rc, 0)
        self.assertEqual(captured, [True, False])


if __name__ == "__main__":
    unittest.main(verbosity=2)
