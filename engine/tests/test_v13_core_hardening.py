import importlib.util
import io
import os
import json
import hashlib
import subprocess
import zipfile
import struct
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "rtxengine.py"


def load_engine():
    name = f"rtxengine_core_test_{id(object())}"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _kv_cstr(value: str) -> bytes:
    return value.encode("utf-8", errors="surrogateescape") + b"\x00"


def _kv_string(key: str, value: str) -> bytes:
    return b"\x01" + _kv_cstr(key) + _kv_cstr(value)


def _kv_int(key: str, value: int) -> bytes:
    return b"\x02" + _kv_cstr(key) + struct.pack("<i", value)


def make_shortcuts_fixture(game, launch: str | None = "MANGOHUD=1 %command%") -> bytes:
    # Real shortcuts.vdf framing: object `shortcuts`, shortcut objects, then one
    # terminator for the shortcuts map plus the final binary-KV root terminator.
    obj = bytearray()
    obj += b"\x00" + _kv_cstr("0")
    obj += _kv_string("AppName", game.name)
    obj += _kv_string("exe", f'"{game.exe}"')
    obj += _kv_string("StartDir", f'"{game.root}"')
    obj += _kv_int("appid", 0x1234567)
    if launch is not None:
        obj += _kv_string("LaunchOptions", launch)
    # Include a nested/unknown-to-us field so surgical edits prove they do not
    # flatten or reconstruct the rest of the shortcut object.
    obj += b"\x00" + _kv_cstr("tags") + _kv_string("0", "Favorite") + b"\x08"
    obj += b"\x08"
    return b"\x00" + _kv_cstr("shortcuts") + bytes(obj) + b"\x08\x08"


def write_minimal_pe(path: Path, imports: list[str]) -> None:
    # Minimal PE32+ image sufficient for rtxEngine's dependency-free normal
    # import-table parser. It is a parser fixture, not an executable program.
    pe_off = 0x80
    opt_size = 0xF0
    raw_off = 0x200
    section_va = 0x1000
    section_size = 0x600
    data = bytearray(raw_off + section_size)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, pe_off)
    data[pe_off:pe_off + 4] = b"PE\0\0"
    coff = pe_off + 4
    struct.pack_into("<H", data, coff, 0x8664)
    struct.pack_into("<H", data, coff + 2, 1)
    struct.pack_into("<H", data, coff + 16, opt_size)
    opt = coff + 20
    struct.pack_into("<H", data, opt, 0x20B)
    # Import data-directory entry (directory index 1).
    import_rva = section_va
    import_size = (len(imports) + 1) * 20
    struct.pack_into("<II", data, opt + 112 + 8, import_rva, import_size)

    sec = opt + opt_size
    data[sec:sec + 8] = b".rdata\0\0"
    struct.pack_into("<I", data, sec + 8, section_size)
    struct.pack_into("<I", data, sec + 12, section_va)
    struct.pack_into("<I", data, sec + 16, section_size)
    struct.pack_into("<I", data, sec + 20, raw_off)

    name_cursor = raw_off + 0x180
    for i, name in enumerate(imports):
        desc = raw_off + i * 20
        name_rva = section_va + (name_cursor - raw_off)
        struct.pack_into("<IIIII", data, desc, 0x1300, 0, 0, name_rva, 0x1400)
        raw = name.encode("ascii") + b"\0"
        data[name_cursor:name_cursor + len(raw)] = raw
        name_cursor += len(raw)
    path.write_bytes(data)


class CoreHardeningTests(unittest.TestCase):
    def setUp(self):
        self.m = load_engine()
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.m.STATE_ROOT = self.base / "state"
        # Production keeps a >32 MiB floor. Tests substitute a tiny deterministic
        # PE-shaped runtime so transaction coverage stays fast and self-contained.
        self.m.NR_RUNTIME_MIN_BYTES = 64
        self.drive = self.base / "Games"
        self.target = self.drive / "SteamLibrary" / "steamapps" / "common" / "Fixture" / "Binaries" / "Win64"
        self.target.mkdir(parents=True)
        self.exe = self.target / "game.exe"
        self.exe.write_bytes(b"MZfixture")
        self.game = self.m.Game(
            "A", "Fixture", self.target.parents[2], "Steam", "123", None,
            self.exe, self.target,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _baseline(self, **updates):
        data = {
            "schema": 13,
            "status": "active",
            "created_utc": self.m.now_iso(),
            "name": "Fixture",
            "source": "Steam",
            "appid": "123",
            "exe": str(self.exe),
            "target_dir": str(self.target),
            "originals": {},
            "managed_paths": [],
            "history": [],
            "current": {"installed_hashes": {}},
        }
        data.update(updates)
        self.m.state_dir_for(self.target).mkdir(parents=True, exist_ok=True)
        self.m.save_json_atomic(self.m.baseline_path(self.target), data)
        return data

    def test_avatar_defaults_reach_install_and_saved_tuning_survives_repair(self):
        import configparser
        self.game.dlss = True
        self.game.dlssg = True
        meta = {"name": "fixture.7z", "sha256": "4" * 64, "tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), meta, "ada")
        ini = self.target / "OptiScaler.ini"
        cfg = configparser.ConfigParser()
        cfg.read(ini)
        self.assertEqual(cfg['Sharpness']['Shader'], 'da')
        self.assertEqual(cfg['Sharpness']['Sharpness'], '0.50')
        self.assertEqual(cfg['CAS']['MotionSharpnessEnabled'], 'true')
        self.assertEqual(cfg['DlssNr']['Style'], '2')
        self.assertEqual(cfg['DlssNr']['Intensity'], '2.00')
        self.assertEqual(cfg['DlssNr']['SkinStructure'], '2.00')
        self.assertEqual(cfg['DlssNr']['WorkingScale'], '0.75')
        edited = self.m.set_ini_value(ini.read_text(), 'DlssNr', 'Intensity', '1.23')
        edited = self.m.set_ini_value(edited, 'Sharpness', 'Sharpness', '0.42')
        ini.write_text(edited)
        self.m.install_target(self.game, self._sm86_payload(), meta, "ada")
        cfg.read(ini)
        self.assertEqual(cfg['DlssNr']['Intensity'], '1.23')
        self.assertEqual(cfg['Sharpness']['Sharpness'], '0.42')

    def test_avatar_defaults_do_not_enable_nr_in_mfg_only(self):
        text, values = self.m.apply_visual_defaults('[DlssNr]\nEnabled=false\n', None, 'mfg-only')
        self.assertNotIn('DlssNr', values)
        self.assertIn('Enabled=false', text)
        self.assertIn('Sharpness=0.50', text)

    def test_reset_visual_settings_backs_up_only_config_and_retains_profile(self):
        self.game.dlss = True
        self.game.dlssg = True
        meta = {"name": "fixture.7z", "sha256": "4" * 64, "tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), meta, "ada")
        ini = self.target / 'OptiScaler.ini'
        edited = self.m.set_ini_value(ini.read_text(), 'DlssNr', 'Intensity', '0.2')
        edited = self.m.set_ini_value(edited, 'Sharpness', 'Sharpness', '0.1')
        edited = self.m.set_ini_value(edited, 'GameCustom', 'KeepMe', 'yes')
        edited = self.m.set_ini_value(edited, 'Menu', 'UseHQFont', 'true')
        ini.write_text(edited)
        before = {p.relative_to(self.target):p.read_bytes() for p in self.target.rglob('*') if p.is_file()}
        baseline = self.m.baseline_path(self.target).read_bytes()
        with patch.object(self.m, '_running_processes_under_root', return_value=[]):
            preview = self.m.reset_visual_settings(self.game, dry_run=True)
            self.assertTrue(preview['changed'])
            self.assertEqual(ini.read_text(), edited)
            record = self.m.reset_visual_settings(self.game)
        self.assertEqual(Path(record['backup']).read_text(), edited)
        self.assertIn('Intensity=2.00', ini.read_text())
        self.assertIn('Sharpness=0.50', ini.read_text())
        self.assertIn('KeepMe=yes', ini.read_text())
        self.assertIn('UseHQFont=false', ini.read_text())
        self.assertEqual(self.m.baseline_path(self.target).read_bytes(), baseline)
        for rel, data in before.items():
            if str(rel) != 'OptiScaler.ini':self.assertEqual((self.target/rel).read_bytes(), data)
        with patch.object(self.m, '_running_processes_under_root', return_value=[]):
            self.assertFalse(self.m.reset_visual_settings(self.game)['changed'])
        self.m.install_target(self.game, self._sm86_payload(), meta, 'ada')
        self.assertIn('Intensity=2.00', ini.read_text())

    def test_reset_visual_settings_refuses_unmanaged_linked_and_running_games(self):
        with self.assertRaises(self.m.Stop):self.m.reset_visual_settings(self.game)
        self.game.dlss = True
        self.game.dlssg = True
        meta = {"name": "fixture.7z", "sha256": "4" * 64, "tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), meta, 'ada')
        ini = self.target / 'OptiScaler.ini'
        data = ini.read_bytes()
        with patch.object(self.m, '_running_processes_under_root', return_value=['123:game']):
            with self.assertRaises(self.m.Stop):self.m.reset_visual_settings(self.game)
        self.assertEqual(ini.read_bytes(), data)
        outside = self.base/'external.ini';outside.write_bytes(data)
        ini.unlink();ini.symlink_to(outside)
        with self.assertRaises(self.m.Stop):self.m.reset_visual_settings(self.game)
        self.assertEqual(outside.read_bytes(), data)

    def test_desktop_reset_skips_download_and_steam_sync_and_keeps_mfg_only(self):
        sys.path.insert(0, str(SCRIPT.parents[1]/'scripts'))
        import engine_bridge
        ini = self.target/'OptiScaler.ini'
        ini.write_text('[DlssNr]\nEnabled=false\nIntensity=0.1\n[Sharpness]\nSharpness=0.1\n')
        self._baseline(current={'feature_mode':'mfg-only','provider_id':'dlss-unlocked',
                                'installed_hashes':{'OptiScaler.ini':self.m.sha256_file(ini)}})
        row={'name':'Fixture','game':str(self.game.root),'exe':str(self.exe.relative_to(self.game.root))}
        with patch.object(engine_bridge, 'module', return_value=self.m), \
             patch.object(engine_bridge, 'game', return_value=self.game), \
             patch.object(engine_bridge, 'payload', side_effect=AssertionError('Unexpected download')), \
             patch.object(self.m, '_running_processes_under_root', return_value=[]), \
             patch.object(self.m, 'steam_running', return_value=True), \
             patch.object(self.m, 'sync_launch_options_batch', side_effect=AssertionError('Unexpected Steam write')):
            review=engine_bridge.prepare({},[row],'nr-mfg','reset',{})
            self.assertFalse(review['blocked'])
            engine_bridge.execute(review)
        self.assertIn('Sharpness=0.50',ini.read_text())
        self.assertIn('Enabled=false',ini.read_text())
        self.assertIn('Intensity=0.1',ini.read_text())

    def test_desktop_cancel_restores_ini_and_baseline(self):
        sys.path.insert(0,str(SCRIPT.parents[1]/'scripts'))
        import engine_bridge, threading
        from operation_session import Cancelled
        ini=self.target/'OptiScaler.ini';ini.write_text('[Sharpness]\nSharpness=0.1\n')
        self._baseline(current={'feature_mode':'mfg-only','provider_id':'dlss-unlocked','installed_hashes':{'OptiScaler.ini':self.m.sha256_file(ini)}})
        before=ini.read_bytes();baseline=self.m.baseline_path(self.target).read_bytes()
        row={'name':'Fixture','game':str(self.game.root),'exe':str(self.exe.relative_to(self.game.root))}
        cancel=threading.Event();original=self.m.reset_visual_settings
        def reset(*a,**kw):
            result=original(*a,**kw)
            if not kw.get('dry_run'):cancel.set()
            return result
        with patch.object(engine_bridge,'module',return_value=self.m),patch.object(engine_bridge,'game',return_value=self.game),patch.object(self.m,'_running_processes_under_root',return_value=[]):
            review=engine_bridge.prepare({},[row],'mfg-only','reset',{})
            review['cancel_event']=cancel
            with patch.object(self.m,'reset_visual_settings',side_effect=reset),self.assertRaises(Cancelled):engine_bridge.execute(review)
        self.assertEqual(ini.read_bytes(),before)
        self.assertEqual(self.m.baseline_path(self.target).read_bytes(),baseline)

    def test_nr_strength_install_reset_and_repair_use_selected_preset(self):
        self.game.dlss = True
        self.game.dlssg = True
        meta = {"name": "fixture.7z", "sha256": "4" * 64, "tag": "fixture"}
        self.m.install_target(self.game,self._sm86_payload(),meta,'ada',nr_strength='medium',sharpening_strength='medium')
        ini = self.target/'OptiScaler.ini'
        self.assertIn('Intensity=1.50',ini.read_text())
        self.assertIn('SkinStructure=1.50',ini.read_text())
        self.assertIn('Sharpness=0.375',ini.read_text())
        with patch.object(self.m,'_running_processes_under_root',return_value=[]):
            for preset, nr, sharp in [('light','1.00','0.25'),('strong','2.00','0.50'),('medium','1.50','0.375')]:
                record=self.m.reset_visual_settings(self.game,nr_strength=preset,sharpening_strength=preset)
                self.assertEqual(record['nr_strength'],preset)
                self.assertIn('Intensity='+nr,ini.read_text())
                self.assertIn('SkinStructure='+nr,ini.read_text())
                self.assertIn('Sharpness='+sharp,ini.read_text())
                self.assertIn('LocalTone=1.00',ini.read_text())
                self.assertIn('WorkingScale=0.75',ini.read_text())
        ini.write_text(self.m.set_ini_value(ini.read_text(),'DlssNr','Intensity','1.23'))
        self.m.install_target(self.game,self._sm86_payload(),meta,'ada',nr_strength='light')
        self.assertIn('Intensity=1.23',ini.read_text())
        self.assertIn('Sharpness=0.375',ini.read_text())
        before=ini.read_bytes()
        with self.assertRaises(self.m.Stop):self.m.reset_visual_settings(self.game,nr_strength='invalid')
        self.assertEqual(ini.read_bytes(),before)

    def test_visual_controls_off_and_multiplier_mapping_preserve_native_route(self):
        self.game.dlss = True
        self.game.dlssg = True
        meta={'name':'fixture.7z','sha256':'4'*64,'tag':'fixture'}
        self.m.install_target(self.game,self._sm86_payload(),meta,'ada')
        ini=self.target/'OptiScaler.ini'
        import configparser
        with patch.object(self.m,'_running_processes_under_root',return_value=[]):
            self.m.reset_visual_settings(self.game,nr_strength='off',sharpening_strength='off',mfg_multiplier=0)
            cfg=configparser.ConfigParser();cfg.read(ini)
            self.assertEqual(cfg['DlssNr']['Enabled'],'false')
            self.assertEqual(cfg['CAS']['Enabled'],'false')
            self.assertEqual(cfg['CAS']['MotionSharpnessEnabled'],'false')
            self.assertEqual(cfg['Sharpness']['Sharpness'],'0.00')
            self.assertEqual(cfg['DLSSG']['OverrideInterpolationCount'],'0')
            for multiplier in range(2,7):
                self.m.reset_visual_settings(self.game,nr_strength='light',sharpening_strength='strong',mfg_multiplier=multiplier)
                cfg.read(ini)
                self.assertEqual(cfg['DLSSG']['OverrideInterpolationCount'],str(multiplier-1))
                self.assertEqual(cfg['DlssNr']['Enabled'],'true')
                self.assertEqual(cfg['DlssNr']['Intensity'],'1.00')
                self.assertEqual(cfg['Sharpness']['Sharpness'],'0.50')
                self.assertEqual(cfg['CAS']['Enabled'],'true')
                self.assertEqual(cfg['FrameGen']['FGInput'],'nofg')
                self.assertEqual(cfg['FrameGen']['FGOutput'],'nofg')
            original=ini.read_bytes()
            with self.assertRaises(self.m.Stop):self.m.reset_visual_settings(self.game,mfg_multiplier=7)
            self.assertEqual(ini.read_bytes(),original)
        self.m.install_target(self.game,self._sm86_payload(),meta,'ada',nr_strength='strong',enable_effects=False)
        cfg.read(ini);self.assertEqual(cfg['DlssNr']['Enabled'],'false')

    def test_nr_only_does_not_write_mfg_override(self):
        text='[DlssNr]\nEnabled=true\n[DLSSG]\nOverrideInterpolationCount=auto\n'
        updated,values=self.m.apply_visual_defaults(text,None,'nr-only','medium',6,'off')
        self.assertNotIn('DLSSG',values)
        self.assertIn('OverrideInterpolationCount=auto',updated)
        self.assertIn('Intensity=1.50',updated)
        self.assertIn('Sharpness=0.00',updated)

    def test_desktop_only_library_apply_saves_global_defaults(self):
        sys.path.insert(0,str(SCRIPT.parents[1]/'scripts'))
        import desktop_service
        service=desktop_service.DesktopService.__new__(desktop_service.DesktopService);service.config={}
        values={'nr_strength':'light','sharpening_strength':'medium','mfg_multiplier':6}
        def preview(*args):return {'kind':'engine','operation':'reset','rows':[]}
        with patch.object(desktop_service.library_media,'load_settings',return_value={}), \
             patch.object(desktop_service.engine_bridge,'prepare',side_effect=preview), \
             patch.object(desktop_service.engine_bridge,'execute',return_value='report'), \
             patch.object(service,'save_visual_defaults') as save:
            game_review=service.prepare([],'nr-mfg','reset',visual_settings=values)
            service.execute(game_review);save.assert_not_called()
            library_review=service.prepare([],'nr-mfg','reset',visual_settings=values,save_defaults=True)
            service.execute(library_review);save.assert_called_once_with(values)

    def test_next_state_retirement_cleans_safe_stale_trash_first(self):
        trash = self.m._state_trash_root()
        trash.mkdir(parents=True)
        stale = trash / "stale-old"
        stale.mkdir()
        (stale / "old.bin").write_bytes(b"old")

        state_dir = self.m.state_dir_for(self.target)
        backup = state_dir / "baseline-backup"
        backup.mkdir(parents=True)
        (backup / "payload.bin").write_bytes(b"payload")
        self.m.discard_consumed_baseline_backup(self.target)
        self.assertFalse(stale.exists())
        self.assertFalse(backup.exists())
        self.assertEqual(list(trash.iterdir()), [])

    def test_consumed_backup_is_retired_before_recursive_cleanup_failure(self):
        state_dir = self.m.state_dir_for(self.target)
        backup = state_dir / "baseline-backup"
        backup.mkdir(parents=True)
        (backup / "payload.bin").write_bytes(b"payload")
        real_rmtree = self.m.shutil.rmtree
        def fail_trash_cleanup(path, *args, **kwargs):
            if "state-trash" in Path(path).parts:
                raise OSError("simulated crashy trash cleanup")
            return real_rmtree(path, *args, **kwargs)
        self.m.shutil.rmtree = fail_trash_cleanup
        try:
            retired = self.m.discard_consumed_baseline_backup(self.target)
        finally:
            self.m.shutil.rmtree = real_rmtree
        self.assertGreater(retired, 0)
        self.assertFalse(backup.exists(), "active baseline-backup name must be gone before recursive cleanup")
        trash = self.m._state_trash_root()
        tombstones = list(trash.iterdir())
        self.assertEqual(len(tombstones), 1)
        self.assertTrue((tombstones[0] / "payload.bin").is_file())
        self.assertIsNone(self.m.quarantine_orphan_baseline_backup(self.target))

    def test_target_history_retention_keeps_current_recovery_slot_regardless_of_mtime(self):
        state = self.m._validated_state_dir(self.target)
        recovery_root = state / "recovery-before-restore"
        recovery_root.mkdir(parents=True)
        current = recovery_root / "current-slot"
        stale = recovery_root / "newer-stale-slot"
        current.mkdir()
        stale.mkdir()
        (current / "OptiScaler.ini").write_bytes(b"preserved-user-drift")
        (stale / "old.txt").write_bytes(b"stale")
        os.utime(current, ns=(1, 1))
        os.utime(stale, ns=(999, 999))

        self.m.prune_target_history(self.target, protected_recovery=current)

        self.assertTrue(current.is_dir())
        self.assertEqual((current / "OptiScaler.ini").read_bytes(), b"preserved-user-drift")
        self.assertFalse(stale.exists())

    def test_target_history_retention_drops_empty_current_recovery_slot(self):
        state = self.m._validated_state_dir(self.target)
        recovery_root = state / "recovery-before-restore"
        current = recovery_root / "empty-slot"
        current.mkdir(parents=True)
        self.m.prune_target_history(self.target, protected_recovery=current)
        self.assertFalse(current.exists())
        self.assertFalse(recovery_root.exists())

    def test_steam_backup_generated_child_symlink_pivot_is_refused(self):
        config = self._steam_localconfig('gamescope %command%')
        backup_root = self.m._validated_state_namespace("steam-config-backups")
        backup_root.mkdir(parents=True)
        outside = self.base / "outside-steam-backup"
        outside.mkdir()
        stamp = "20990101-000000"
        (backup_root / stamp).symlink_to(outside, target_is_directory=True)

        with patch.object(self.m, "now_stamp", return_value=stamp):
            with self.assertRaises(self.m.Stop) as cm:
                self.m.backup_steam_config(config, "42")
        self.assertIn("symlink refused", str(cm.exception))
        self.assertEqual(list(outside.iterdir()), [])

    def test_steam_backup_prune_never_deletes_explicit_prejournal_generation(self):
        root = self.m.STATE_ROOT / "steam-config-backups"
        protected = root / "old-but-current"
        newer1 = root / "newer-1"
        newer2 = root / "newer-2"
        for path in (protected, newer1, newer2):
            path.mkdir(parents=True)
            (path / "x").write_text(path.name, encoding="utf-8")
        # Deliberately make the just-created/current generation look oldest;
        # correctness must not rely on its mtime winning the retention sort.
        os.utime(protected, ns=(1, 1))
        os.utime(newer1, ns=(2, 2))
        os.utime(newer2, ns=(3, 3))
        self.m.prune_steam_config_backups(keep=1, extra_protected={protected})
        self.assertTrue(protected.is_dir())
        self.assertFalse(newer1.exists())
        self.assertTrue(newer2.is_dir())

    def test_atomic_write_fsyncs_containing_directory_after_replace(self):
        target = self.base / "durable" / "state.json"
        real_fsync = self.m.os.fsync
        calls = []
        def tracking_fsync(fd):
            calls.append(fd)
            return real_fsync(fd)
        with patch.object(self.m.os, "fsync", side_effect=tracking_fsync):
            self.m.atomic_write(target, b"durable")
        self.assertEqual(target.read_bytes(), b"durable")
        # One fsync is the temporary file; at least one later fsync is the
        # containing directory after os.replace().
        self.assertGreaterEqual(len(calls), 2)

    def test_copy_verified_failure_never_replaces_existing_destination(self):
        src = self.base / "src.bin"
        dst = self.base / "dst.bin"
        src.write_bytes(b"new-recovery-bytes")
        dst.write_bytes(b"old-safe-bytes")
        real_copy2 = self.m.shutil.copy2

        def partial_then_fail(source, target, *args, **kwargs):
            target = Path(target)
            target.write_bytes(b"partial")
            raise OSError("simulated copy failure")

        with patch.object(self.m.shutil, "copy2", side_effect=partial_then_fail):
            with self.assertRaises(OSError):
                self.m.copy_verified(src, dst)
        self.assertEqual(dst.read_bytes(), b"old-safe-bytes")
        self.assertFalse(any(dst.parent.glob(f".{dst.name}.rtxforge-copy-*")))

    def test_mutation_lock_blocks_second_process_and_releases_cleanly(self):
        probe = self.base / "lock_probe.py"
        probe.write_text(
            "import importlib.util, os, sys\n"
            f"script = {str(SCRIPT)!r}\n"
            "spec = importlib.util.spec_from_file_location('rtxengine_lock_probe', script)\n"
            "m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)\n"
            "try:\n"
            "    with m.mutation_lock():\n"
            "        print('ACQUIRED')\n"
            "except m.Stop as exc:\n"
            "    print('BUSY:' + str(exc))\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["RTXFORGE_DLSS_UNLOCKED_STATE"] = str(self.m.STATE_ROOT)
        with self.m.mutation_lock():
            blocked = subprocess.run(
                [sys.executable, str(probe)], env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
            )
            self.assertIn("BUSY:Another rtxEngine mutating operation is already running", blocked.stdout)
        released = subprocess.run(
            [sys.executable, str(probe)], env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        self.assertIn("ACQUIRED", released.stdout)

    def test_mutation_lock_refuses_symlink_lockfile(self):
        self.m.STATE_ROOT.mkdir(parents=True)
        outside = self.base / "outside-lock"
        outside.write_text("outside", encoding="utf-8")
        (self.m.STATE_ROOT / ".writer.lock").symlink_to(outside)
        with self.assertRaises(self.m.Stop) as cm:
            with self.m.mutation_lock():
                pass
        self.assertIn("writer lock symlink refused", str(cm.exception))
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside")

    def test_durable_replace_and_unlink_sync_parent_directory(self):
        parent = self.base / "durable-names"
        parent.mkdir()
        src = parent / "old"
        dst = parent / "new"
        src.write_bytes(b"x")
        synced = []
        with patch.object(self.m, "_fsync_dir", side_effect=lambda p: synced.append(Path(p))):
            self.m.durable_replace(src, dst)
            self.assertTrue(dst.is_file())
            self.assertIn(parent, synced)
            synced.clear()
            self.m.durable_unlink(dst)
            self.assertFalse(dst.exists())
            self.assertIn(parent, synced)

    def test_restore_drift_copy_failure_aborts_before_live_file_deletion(self):
        self.game.dlss = True
        self.game.dlssg = True
        meta = {"name": "fixture.zip", "sha256": "a" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), meta, "sm86")
        live = self.target / "OptiScaler.ini"
        live.write_bytes(b"user-edited-after-install")
        real_copy = self.m.copy_verified

        def fail_recovery_copy(src, dst):
            if "recovery-before-restore" in str(dst):
                raise OSError("simulated recovery media failure")
            return real_copy(src, dst)

        with patch.object(self.m, "copy_verified", side_effect=fail_recovery_copy):
            with self.assertRaises(OSError):
                self.m.restore_target(self.game)
        self.assertTrue(live.is_file())
        self.assertEqual(live.read_bytes(), b"user-edited-after-install")
        self.assertTrue(self.m.baseline_path(self.target).is_file())

    def test_regular_tree_backup_is_flushed_before_manifest_commit(self):
        source = self.base / "tree-source"
        source.mkdir()
        (source / "a.bin").write_bytes(b"a")
        backup_root = self.m.state_dir_for(self.target) / "baseline-backup"
        backup_root.mkdir(parents=True)
        flushed = []
        real = self.m._fsync_tree
        with patch.object(self.m, "_fsync_tree", side_effect=lambda p: (flushed.append(Path(p)), real(p))[1]):
            info = self.m.backup_tree(source, backup_root, "OptiScaler")
        self.assertEqual(flushed, [Path(info["backup"])])
        self.assertTrue(Path(info["manifest"]).is_file())

    def test_state_child_namespaces_refuse_symlink_pivots(self):
        self.m.STATE_ROOT.mkdir(parents=True)
        outside = self.base / "outside-state-namespace"
        outside.mkdir()
        for name in ("steam-transactions", "steam-config-backups", "state-trash", "deep-clean-receipts", "pristine-reset-receipts"):
            link = self.m.STATE_ROOT / name
            link.symlink_to(outside, target_is_directory=True)
            try:
                with self.subTest(name=name):
                    with self.assertRaises(self.m.Stop):
                        self.m._validated_state_namespace(name)
            finally:
                link.unlink()

    def test_verify_queue_symlink_is_refused_before_read(self):
        self.m.STATE_ROOT.mkdir(parents=True)
        outside = self.base / "outside-queue.json"
        outside.write_text(json.dumps({"schema": 2, "remaining": [], "in_flight": None}), encoding="utf-8")
        queue = self.m.STATE_ROOT / "steam-verify-queue.json"
        queue.symlink_to(outside)
        with self.assertRaises(self.m.Stop) as cm:
            self.m._load_verify_queue()
        self.assertIn("queue symlink refused", str(cm.exception))
        self.assertTrue(outside.is_file())

    def test_steam_transaction_journal_boolean_schema_is_rejected(self):
        tx_root = self.m._steam_transaction_root()
        tx_root.mkdir(parents=True)
        journal = tx_root / "bool-schema.json"
        journal.write_text(json.dumps({"schema": True, "phase": "prepared"}), encoding="utf-8")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_pending_steam_transactions()
        self.assertIn("Unsupported Steam transaction journal", str(cm.exception))
        self.assertTrue(journal.is_file(), "corrupt journal must not be mutated or discarded")

    def test_committed_steam_transaction_journal_is_validated_before_cleanup(self):
        tx_root = self.m._steam_transaction_root()
        tx_root.mkdir(parents=True)
        journal = tx_root / "corrupt-committed.json"
        journal.write_text(json.dumps({
            "schema": 1, "phase": "committed", "kind": "steam",
            "config_path": True, "entries": [{"appid": "123", "before": None}],
        }), encoding="utf-8")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_pending_steam_transactions()
        self.assertIn("journal config path", str(cm.exception))
        self.assertTrue(journal.is_file(), "corrupt terminal journal must remain for recovery diagnosis")

    def test_unknown_steam_transaction_phase_is_rejected_before_recovery(self):
        tx_root = self.m._steam_transaction_root()
        tx_root.mkdir(parents=True)
        journal = tx_root / "unknown-phase.json"
        journal.write_text(json.dumps({
            "schema": 1, "phase": "mystery", "kind": "steam",
            "config_path": "/tmp/localconfig.vdf",
            "entries": [{"appid": "123", "before": None}],
        }), encoding="utf-8")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_pending_steam_transactions()
        self.assertIn("journal phase", str(cm.exception))
        self.assertTrue(journal.is_file(), "unknown transaction state must fail closed")

    def test_rolled_back_steam_transaction_journal_is_validated_then_cleaned(self):
        steam_root = self.base / "steam-root"
        config = steam_root / "userdata" / "42" / "config" / "localconfig.vdf"
        config.parent.mkdir(parents=True)
        config.write_text('"UserLocalConfigStore"\n{\n}\n', encoding="utf-8")
        self.m.STEAM_ROOT_CANDIDATES = [steam_root]
        tx_root = self.m._steam_transaction_root()
        tx_root.mkdir(parents=True)
        journal = tx_root / "rolled-back.json"
        journal.write_text(json.dumps({
            "schema": 1, "phase": "rolled_back", "kind": "steam",
            "config_path": str(config),
            "entries": [{"appid": "123", "before": None}],
        }), encoding="utf-8")
        self.assertEqual(self.m.load_pending_steam_transactions(), [])
        self.assertFalse(journal.exists(), "validated terminal rollback journal should be retired idempotently")

    def test_terminal_steam_transaction_outside_userdata_is_not_discarded(self):
        steam_root = self.base / "steam-root"
        (steam_root / "userdata").mkdir(parents=True)
        self.m.STEAM_ROOT_CANDIDATES = [steam_root]
        outside = self.base / "outside" / "localconfig.vdf"
        outside.parent.mkdir(parents=True)
        outside.write_text('"UserLocalConfigStore"\n{\n}\n', encoding="utf-8")
        tx_root = self.m._steam_transaction_root()
        tx_root.mkdir(parents=True)
        journal = tx_root / "forged-committed.json"
        journal.write_text(json.dumps({
            "schema": 1, "phase": "committed", "kind": "steam",
            "config_path": str(outside),
            "entries": [{"appid": "123", "before": None}],
        }), encoding="utf-8")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_pending_steam_transactions()
        self.assertIn("canonical userdata", str(cm.exception))
        self.assertTrue(journal.is_file(), "invalid terminal journal must remain for diagnosis")

    def test_terminal_steam_transaction_noncanonical_userdata_path_is_not_discarded(self):
        steam_root = self.base / "steam-root"
        forged = steam_root / "userdata" / "42" / "other" / "nested" / "localconfig.vdf"
        forged.parent.mkdir(parents=True)
        forged.write_text('"UserLocalConfigStore"\n{\n}\n', encoding="utf-8")
        self.m.STEAM_ROOT_CANDIDATES = [steam_root]
        tx_root = self.m._steam_transaction_root()
        tx_root.mkdir(parents=True)
        journal = tx_root / "forged-noncanonical-committed.json"
        journal.write_text(json.dumps({
            "schema": 1, "phase": "committed", "kind": "steam",
            "config_path": str(forged),
            "entries": [{"appid": "123", "before": None}],
        }), encoding="utf-8")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_pending_steam_transactions()
        self.assertIn("canonical userdata", str(cm.exception))
        self.assertTrue(journal.is_file(), "noncanonical terminal journal must remain for diagnosis")

    def test_steam_transaction_journal_boolean_config_path_is_rejected_before_recovery(self):
        tx_root = self.m._steam_transaction_root()
        tx_root.mkdir(parents=True)
        journal = tx_root / "bool-config.json"
        journal.write_text(json.dumps({
            "schema": 1, "phase": "prepared", "kind": "steam",
            "config_path": True, "entries": [{"appid": "123", "before": None}],
        }), encoding="utf-8")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_pending_steam_transactions()
        self.assertIn("journal config path", str(cm.exception))
        self.assertTrue(journal.is_file(), "corrupt journal must remain untouched")

    def test_steam_transaction_journal_boolean_shortcut_appid_is_rejected_before_recovery(self):
        steam_root = self.base / "steam-root"
        shortcuts = steam_root / "userdata" / "42" / "config" / "shortcuts.vdf"
        shortcuts.parent.mkdir(parents=True)
        shortcuts.write_bytes(b"fixture")
        self.m.STEAM_ROOT_CANDIDATES = [steam_root]
        tx_root = self.m._steam_transaction_root()
        tx_root.mkdir(parents=True)
        journal = tx_root / "bool-shortcut-appid.json"
        journal.write_text(json.dumps({
            "schema": 1, "phase": "prepared", "kind": "shortcut",
            "config_path": str(shortcuts),
            "entries": [{
                "before": "",
                "locator": {
                    "shortcut_appid": True,
                    "shortcut_appname": "Example",
                    "shortcut_exe": "/games/example.exe",
                },
            }],
        }), encoding="utf-8")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_pending_steam_transactions()
        self.assertIn("shortcut AppID in journal", str(cm.exception))
        self.assertTrue(journal.is_file(), "corrupt journal must remain untouched")

    def test_nonsteam_shortcut_boolean_appid_is_rejected(self):
        rec = {
            "kind": "shortcut",
            "config_path": str(self.base / "steam-root" / "userdata" / "123" / "config" / "shortcuts.vdf"),
            "shortcut_appid": True,
            "shortcut_appname": "Example",
            "shortcut_exe": "/games/example.exe",
            "original": "",
            "applied": "WINEDLLOVERRIDES=dxgi=n,b %command%",
            "required": None,
        }
        steam_root = self.base / "steam-root"
        rec_path = Path(rec["config_path"])
        rec_path.parent.mkdir(parents=True)
        rec_path.write_bytes(b"")
        with patch.object(self.m, "STEAM_ROOT_CANDIDATES", [steam_root]):
            with self.assertRaises(self.m.Stop) as cm:
                self.m._validate_steam_launch_record(rec)
        self.assertIn("Non-Steam shortcut AppID is invalid", str(cm.exception))

    def test_steam_transaction_journal_symlink_is_refused_before_read(self):
        tx_root = self.m._steam_transaction_root()
        tx_root.mkdir(parents=True)
        outside = self.base / "outside-tx.json"
        outside.write_text(json.dumps({"schema": 1, "phase": "prepared"}), encoding="utf-8")
        (tx_root / "evil.json").symlink_to(outside)
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_pending_steam_transactions()
        self.assertIn("journal symlink refused", str(cm.exception))

        backup_root = self.m._validated_state_namespace("steam-config-backups")
        backup_root.mkdir(parents=True)
        generation = backup_root / "generation"
        generation.mkdir()
        self.assertIsNone(self.m._active_steam_backup_generations(backup_root))
        self.m.prune_steam_config_backups(keep=0)
        self.assertTrue(generation.is_dir(), "ambiguous journal state must disable retention pruning")

    def test_persisted_traversal_is_rejected_before_live_mutation(self):
        victim = self.base / "outside.txt"
        victim.write_text("keep", encoding="utf-8")
        b = self._baseline(managed_paths=["../../../../../../outside.txt"])
        with self.assertRaises(self.m.Stop):
            self.m.verify_baseline_integrity(self.target, b, adopt_legacy=False)
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep")

    def test_managed_root_without_recovery_baseline_is_rejected_before_delete(self):
        # A malformed/partially migrated legacy state must never be able to
        # claim a stock game runtime DLL for deletion without proving what
        # existed before rtxEngine managed that filename.
        live = self.target / "nvngx_dlssg.dll"
        live.write_bytes(b"stock-native-dlssg")
        b = self._baseline(
            originals={},
            managed_paths=["nvngx_dlssg.dll"],
            current={"installed_hashes": {"nvngx_dlssg.dll": self.m.sha256_file(live)}},
        )
        with self.assertRaises(self.m.Stop) as cm:
            self.m.restore_target(self.game)
        self.assertIn("Managed root path is missing its recovery baseline", str(cm.exception))
        self.assertEqual(live.read_bytes(), b"stock-native-dlssg")

    def test_wrong_case_optiscaler_descendant_requires_own_baseline_before_restore(self):
        # Linux path ownership is case-sensitive. A lower-case optiscaler/
        # path is not inside the canonical OptiScaler/ tree baseline and must
        # never borrow that tree's ownership exemption.
        lower = self.target / "optiscaler"
        lower.mkdir()
        live = lower / "foreign.dll"
        live.write_bytes(b"foreign-lowercase-tree-file")
        b = self._baseline(
            originals={},
            managed_paths=["optiscaler/foreign.dll"],
            current={"installed_hashes": {
                "optiscaler/foreign.dll": self.m.sha256_file(live)
            }},
        )

        with self.assertRaises(self.m.Stop) as cm:
            self.m.restore_target(self.game)

        self.assertIn("Managed root path is missing its recovery baseline", str(cm.exception))
        self.assertEqual(live.read_bytes(), b"foreign-lowercase-tree-file")
        self.assertTrue(self.m.baseline_path(self.target).is_file())

    def test_optiscaler_descendant_managed_path_uses_tree_baseline(self):
        # Provider files under OptiScaler/ are legitimately represented by the
        # captured tree root rather than one original entry per child.
        backup_root = self.m.state_dir_for(self.target) / "baseline-backup"
        backup_root.mkdir(parents=True)
        source = self.base / "old-opti-descendant"
        source.mkdir()
        (source / "nvngx_dlssg.dll").write_bytes(b"old-tree-dlssg")
        info = self.m.backup_tree(source, backup_root, "OptiScaler")
        b = self._baseline(
            originals={"OptiScaler/": info},
            managed_paths=["OptiScaler/", "OptiScaler/nvngx_dlssg.dll"],
            current={"installed_hashes": {}},
        )
        self.m.verify_baseline_integrity(self.target, b, adopt_legacy=False)

    def test_baseline_backup_root_symlink_pivot_is_rejected(self):
        state = self.m._validated_state_dir(self.target)
        state.mkdir(parents=True)
        outside = self.base / "outside-backups"
        outside.mkdir()
        payload = outside / "dxgi.dll"
        payload.write_bytes(b"outside")
        (state / "baseline-backup").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(self.m.Stop) as cm:
            self.m._baseline_backup_member(self.target, str(payload))
        self.assertIn("backup root symlink", str(cm.exception))

    def test_restore_recovery_root_symlink_pivot_is_rejected(self):
        state = self.m._validated_state_dir(self.target)
        state.mkdir(parents=True)
        outside = self.base / "outside-recovery-root"
        outside.mkdir()
        (state / "recovery-before-restore").symlink_to(outside, target_is_directory=True)
        slot = outside / "slot"
        slot.mkdir()
        with self.assertRaises(self.m.Stop) as cm:
            self.m._validate_restore_recovery_dir(self.target, str(slot))
        self.assertIn("recovery root symlink", str(cm.exception))

    def test_backup_path_escape_is_rejected(self):
        external = self.base / "evil-backup.dll"
        external.write_bytes(b"evil")
        b = self._baseline(originals={
            "dxgi.dll": {
                "kind": "file", "existed": True,
                "backup": str(external),
                "sha256": self.m.sha256_file(external),
                "mode": 0o644,
            }
        })
        with self.assertRaises(self.m.Stop):
            self.m.verify_baseline_integrity(self.target, b, adopt_legacy=False)

    def test_baseline_boolean_file_mode_is_rejected_before_restore_mutation(self):
        live = self.target / "dxgi.dll"
        live.write_bytes(b"engine-current")
        backup_root = self.m.state_dir_for(self.target) / "baseline-backup"
        backup_root.mkdir(parents=True)
        backup = backup_root / "original-dxgi.dll"
        backup.write_bytes(b"game-original")
        b = self._baseline(
            originals={
                "dxgi.dll": {
                    "kind": "file",
                    "existed": True,
                    "backup": str(backup),
                    "sha256": self.m.sha256_file(backup),
                    "mode": True,
                }
            },
            managed_paths=["dxgi.dll"],
            current={"installed_hashes": {"dxgi.dll": self.m.sha256_file(live)}},
        )
        with self.assertRaises(self.m.Stop) as cm:
            self.m.restore_target(self.game)
        self.assertIn("Baseline file mode invalid", str(cm.exception))
        self.assertEqual(live.read_bytes(), b"engine-current")

    def test_baseline_out_of_range_file_mode_is_rejected(self):
        backup_root = self.m.state_dir_for(self.target) / "baseline-backup"
        backup_root.mkdir(parents=True)
        backup = backup_root / "original-dxgi.dll"
        backup.write_bytes(b"game-original")
        b = self._baseline(originals={
            "dxgi.dll": {
                "kind": "file", "existed": True,
                "backup": str(backup),
                "sha256": self.m.sha256_file(backup),
                "mode": 0o10000,
            }
        })
        with self.assertRaises(self.m.Stop) as cm:
            self.m.verify_baseline_integrity(self.target, b, adopt_legacy=False)
        self.assertIn("Baseline file mode invalid", str(cm.exception))

    def test_tree_manifest_detects_tamper_before_restore_deletes_live_tree(self):
        live = self.target / "OptiScaler"
        live.mkdir()
        (live / "current.bin").write_bytes(b"current")
        backup_root = self.m.state_dir_for(self.target) / "baseline-backup"
        backup_root.mkdir(parents=True)
        source = self.base / "old-opti"
        source.mkdir()
        (source / "old.bin").write_bytes(b"original")
        info = self.m.backup_tree(source, backup_root, "OptiScaler")
        b = self._baseline(
            originals={"OptiScaler/": info},
            managed_paths=["OptiScaler/"],
            current={"installed_hashes": {}},
        )
        # Damage the baseline after its manifest was written.
        (Path(info["backup"]) / "old.bin").write_bytes(b"tampered")
        with self.assertRaises(self.m.Stop):
            self.m.restore_target(self.game)
        self.assertTrue(live.is_dir())
        self.assertEqual((live / "current.bin").read_bytes(), b"current")

    def test_tree_baseline_refuses_source_change_during_copy(self):
        source = self.base / "moving-opti"
        source.mkdir()
        live = source / "core.dll"
        live.write_bytes(b"before")
        backup_root = self.m.state_dir_for(self.target) / "baseline-backup"
        backup_root.mkdir(parents=True)
        real_copytree = self.m.shutil.copytree

        def copy_then_mutate(src, dst, *args, **kwargs):
            result = real_copytree(src, dst, *args, **kwargs)
            live.write_bytes(b"after")
            return result

        with patch.object(self.m.shutil, "copytree", side_effect=copy_then_mutate):
            with self.assertRaises(self.m.Stop) as cm:
                self.m.backup_tree(source, backup_root, "OptiScaler")
        self.assertIn("changed while baseline backup", str(cm.exception))
        self.assertEqual(live.read_bytes(), b"after")

    def test_legacy_tree_gets_integrity_metadata_without_touching_live_game(self):
        backup_root = self.m.state_dir_for(self.target) / "baseline-backup"
        tree = backup_root / "trees" / "OptiScaler"
        tree.mkdir(parents=True)
        (tree / "old.bin").write_bytes(b"old")
        b = self._baseline(originals={
            "OptiScaler/": {
                "kind": "tree", "existed": True,
                "backup": str(tree), "bytes": 3,
            }
        })
        self.m.verify_baseline_integrity(self.target, b, adopt_legacy=True)
        reloaded = self.m.load_baseline(self.target)
        info = reloaded["originals"]["OptiScaler/"]
        self.assertIn("manifest", info)
        self.assertIn("manifest_sha256", info)
        self.assertIn("tree_sha256", info)
        self.assertTrue(Path(info["manifest"]).is_file())

    def test_malicious_tar_member_is_rejected(self):
        archive = self.base / "bad.tar"
        with tarfile.open(archive, "w") as tf:
            payload = b"oops"
            ti = tarfile.TarInfo("../escape")
            ti.size = len(payload)
            tf.addfile(ti, io.BytesIO(payload))
        with self.assertRaises(self.m.Stop):
            self.m._validate_tar_archive(archive, expected_top="OptiScaler", exact_file=False)

    def test_duplicate_tar_members_are_refused(self):
        archive = self.base / "duplicate.tar"
        with tarfile.open(archive, "w") as tf:
            for payload in (b"first", b"second"):
                ti = tarfile.TarInfo("OptiScaler/core.dll")
                ti.size = len(payload)
                tf.addfile(ti, io.BytesIO(payload))
        with self.assertRaises(self.m.Stop) as cm:
            self.m._validate_tar_archive(archive, expected_top="OptiScaler", exact_file=False)
        self.assertIn("Duplicate tar member", str(cm.exception))

    def test_current_baseline_float_schema_is_refused(self):
        state = self.m._validated_state_dir(self.target)
        state.mkdir(parents=True)
        baseline = state / "baseline.json"
        baseline.write_text(json.dumps({
            "schema": 13.0, "target_dir": str(self.target),
            "managed_paths": [], "originals": {},
        }), encoding="utf-8")
        before = baseline.read_bytes()
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_baseline(self.target)
        self.assertIn("Unsupported rtxEngine/legacy rtxForge state", str(cm.exception))
        self.assertEqual(baseline.read_bytes(), before)

    def test_legacy_baseline_float_schema_is_not_migrated(self):
        state = self.m._validated_state_dir(self.target)
        state.mkdir(parents=True)
        baseline = state / "baseline.json"
        baseline.write_text(json.dumps({
            "schema": 2.0, "target_dir": str(self.target),
            "managed_paths": [], "originals": {},
        }), encoding="utf-8")
        before = baseline.read_bytes()
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_baseline(self.target)
        self.assertIn("Unsupported rtxEngine/legacy rtxForge state", str(cm.exception))
        self.assertEqual(baseline.read_bytes(), before)

    def test_baseline_json_symlink_is_refused_before_read(self):
        state = self.m._validated_state_dir(self.target)
        state.mkdir(parents=True)
        outside = self.base / "outside-baseline.json"
        outside.write_text(json.dumps({
            "schema": 13, "target_dir": str(self.target), "managed_paths": [], "originals": {}
        }), encoding="utf-8")
        (state / "baseline.json").symlink_to(outside)
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_baseline(self.target)
        self.assertIn("Baseline state file symlink refused", str(cm.exception))
        self.assertTrue(outside.is_file())

    def test_corrupt_state_is_visible_not_silently_hidden(self):
        bad = self.m.STATE_ROOT / "targets" / "bad" / "baseline.json"
        bad.parent.mkdir(parents=True)
        bad.write_text("{ definitely not json", encoding="utf-8")
        messages = []
        self.m.warn = messages.append
        games = self.m.load_installed_states_under_drive(self.drive)
        self.assertEqual(games, [])
        self.assertTrue(any("Corrupt/unreadable install state surfaced" in x for x in messages))

    def test_desktop_preview_is_read_only_and_mfg_only_needs_no_nr(self):
        self.game.dlss = self.game.dlssg = True
        payload = {k:v for k,v in self._sm86_payload().items() if "dlssnr" not in k}
        before = list(self.target.rglob("*"))
        preview = self.m.install_target(self.game,payload,{"sha256":"a"*64},"ada",feature_mode="mfg-only",dry_run=True)
        self.assertEqual(list(self.target.rglob("*")),before)
        self.assertFalse(self.m.STATE_ROOT.exists())
        self.assertNotIn("nvngx_dlssnr.dll",preview["files"])

    def test_native_fg_missing_original_refuses_before_restore_writes(self):
        native=self.target / "nvngx_dlssg.dll";native.write_bytes(b"native 2x runtime")
        baseline=self._baseline(managed_paths=["nvngx_dlssg.dll"],originals={"nvngx_dlssg.dll":{"kind":"file","existed":False}})
        before=self.m.baseline_path(self.target).read_bytes()
        with self.assertRaisesRegex(self.m.Stop,"native NVIDIA"):
            self.m.restore_target(self.game)
        self.assertEqual(native.read_bytes(),b"native 2x runtime")
        self.assertEqual(self.m.baseline_path(self.target).read_bytes(),before)

    def test_explicit_native_ada_activation_keeps_game_output(self):
        self.game.dlss = self.game.dlssg = True
        self.m.install_target(self.game,self._sm86_payload(),{"sha256":"a"*64},"ada",feature_mode="mfg-only",enable_effects=True)
        text=(self.target/"OptiScaler.ini").read_text()
        self.assertIn("AdaMfgUnlock=true",text)
        self.assertIn("FGInput=nofg",text);self.assertIn("FGOutput=nofg",text)
        self.assertFalse((self.target/"nvngx_dlssnr.dll").exists())

    def test_dlss_unlocked_keeps_its_model_and_restores_existing_model(self):
        self.game.dlss = self.game.dlssg = True
        self.m.Y4MY_PROVIDER = {**self.m.Y4MY_PROVIDER, 'id':'dlss-unlocked'}
        model=self.target/'nvngx_dlssnr.dll';original=b'MZ'+b'O'*128;model.write_bytes(original)
        payload=self._sm86_payload()
        self.m.install_target(self.game,payload,{'sha256':'a'*64},'ada',feature_mode='nr-mfg',enable_effects=True)
        self.assertEqual(model.read_bytes(),payload['nvngx_dlssnr.dll'])
        self.m.restore_target(self.game)
        self.assertEqual(model.read_bytes(),original)

    def test_frozen_mfg_updates_native_runtime_and_restores_original(self):
        self.game.dlss = self.game.dlssg = True
        self.m.Y4MY_PROVIDER = {**self.m.Y4MY_PROVIDER, 'id':'dlss-unlocked'}
        native=self.target/'nvngx_dlssg.dll';native.write_bytes(b'MZ-original-native-fg')
        payload=self._sm86_payload();payload['OptiScaler/streamline/nvngx_dlssg.dll']=b'MZ-new-native-fg'
        self.m.install_target(self.game,payload,{'sha256':'a'*64},'ada',feature_mode='mfg-only',enable_effects=True)
        self.assertEqual(native.read_bytes(),b'MZ-new-native-fg')
        self.assertFalse((self.target/'nvngx_dlssnr.dll').exists())
        self.m.restore_target(self.game)
        self.assertEqual(native.read_bytes(),b'MZ-original-native-fg')

    def test_frozen_nr_only_disables_mfg_unlock(self):
        self.game.dlss = self.game.dlssg = True
        self.m.Y4MY_PROVIDER = {**self.m.Y4MY_PROVIDER, 'id':'dlss-unlocked'}
        result=self.m.install_target(self.game,self._sm86_payload(),{'sha256':'a'*64},'ada',feature_mode='nr-only',enable_effects=True)
        text=(self.target/'OptiScaler.ini').read_text()
        self.assertIn('AdaMfgUnlock=false',text)
        self.assertIn('Enabled=true',text.split('[DlssNr]')[1])
        self.assertFalse(result['mfg_provider']['enabled'])
        self.assertTrue(result['nr_profile']['enabled'])

    def test_lab_copy_never_matches_original_shortcut_by_name(self):
        shortcuts=self.m.parse_shortcuts_spans(make_shortcuts_fixture(self.game))
        clone=self.base/'Forge Lab'/'Fixture';clone.mkdir(parents=True)
        game=self.m.Game('','Fixture',clone,'Folder',exe=clone/'game.exe')
        self.assertIsNone(self.m.match_shortcut_span(game,shortcuts))
        self.assertIsNotNone(self.m.match_shortcut_span(self.game,shortcuts))

    def _sm86_payload(self):
        return {
            "dxgi.dll": b"optiscaler-proxy-v1",
            "OptiScaler.ini": b"[Menu]\nOverlayMenu=true\n",
            "OptiScaler/core.dll": b"core-v1",
            "OptiScaler/dlssg_sm86/dlssg_sm86.dll": b"sm86-v1",
            "OptiScaler/dlssg_sm86/dlssg_sm86.ini": b"[x]\n",
            "OptiScaler/streamline/sl.interposer.dll": b"streamline-v1",
            "OptiScaler/streamline/sl.dlss_g.dll": b"dlssg-v1",
            "Licenses/LICENSE.txt": b"fixture-license",
            "nvngx.dll_dlssnr.dll": b"nr-alias-v1",
            "nvngx_dlssnr.dll": b"MZ" + (b"N" * 128),
        }

    def _seed_legacy_mfg_state(self, proxy="winmm.dll", payload=b"MZ-legacy-rtxmfg"):
        """Turn a current baseline into a deterministic 187-style split-provider state."""
        baseline = self.m.load_baseline(self.target)
        self.assertIsNotNone(baseline)
        baseline = self.m.extend_baseline_for_new_paths(baseline, self.target, {proxy})
        (self.target / proxy).write_bytes(payload)
        baseline["managed_paths"] = sorted(set(baseline.get("managed_paths", [])) | {proxy}, key=str.casefold)
        current = baseline["current"]
        current.setdefault("installed_hashes", {})[proxy] = self.m.sha256_bytes(payload)
        current["mfg_provider"] = {
            "name": "Universal RTXMFG", "version": "legacy-187",
            "proxy": proxy, "ownership": "external",
            "dll_sha256": self.m.sha256_bytes(payload),
        }
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)
        return payload

    def _steam_localconfig(self, launch_value=None):
        steam_root = self.base / "Steam"
        config = steam_root / "userdata" / "42" / "config" / "localconfig.vdf"
        config.parent.mkdir(parents=True, exist_ok=True)
        launch = ""
        if launch_value is not None:
            launch = f'\t\t\t\t\t\t"LaunchOptions"\t\t"{launch_value}"\n'
        config.write_text(
            '"UserLocalConfigStore"\n{\n'
            '\t"Software"\n\t{\n'
            '\t\t"Valve"\n\t\t{\n'
            '\t\t\t"Steam"\n\t\t\t{\n'
            '\t\t\t\t"apps"\n\t\t\t\t{\n'
            '\t\t\t\t\t"123"\n\t\t\t\t\t{\n'
            + launch +
            '\t\t\t\t\t}\n'
            '\t\t\t\t}\n'
            '\t\t\t}\n'
            '\t\t}\n'
            '\t}\n'
            '}\n',
            encoding="utf-8",
        )
        self.m.STEAM_ROOT_CANDIDATES = (steam_root,)
        return config

    def test_localconfig_restore_can_remove_launchoptions_exactly(self):
        config = self._steam_localconfig(None)
        original_bytes = config.read_bytes()
        before = self.m.update_localconfig_launch_options(config, {"123": "FOO=1 %command%"})
        self.assertIsNone(before["123"])
        self.assertEqual(self.m.read_localconfig_launch_options(config, "123"), "FOO=1 %command%")
        self.m.update_localconfig_launch_options(config, {"123": None})
        self.assertIsNone(self.m.read_localconfig_launch_options(config, "123"))
        # Whitespace can differ, but the LaunchOptions key must be truly absent.
        self.assertNotIn('"LaunchOptions"', config.read_text(encoding="utf-8"))
        self.assertTrue(original_bytes)

    def test_interrupted_steam_transaction_rolls_config_and_baseline_metadata_back(self):
        config = self._steam_localconfig("MANGOHUD=1 %command%")
        previous_record = {
            "kind": "steam", "appid": "123", "original": None,
            "applied": "MANGOHUD=1 %command%", "config_path": str(config),
            "steam_userid": "42",
        }
        self._baseline(steam_launch=previous_record)
        file_backup = self.m.backup_steam_config(config, "42")
        new_record = {
            "kind": "steam", "appid": "123", "original": None,
            "applied": "MANGOHUD=1 PROTON_ENABLE_NVAPI=1 %command%",
            "config_path": str(config), "steam_userid": "42",
        }
        entries = [{
            "game": "Fixture", "target_dir": str(self.target), "appid": "123",
            "before": "MANGOHUD=1 %command%",
            "previous_steam_launch": previous_record,
            "new_record": new_record,
        }]
        tx_path, tx = self.m.begin_steam_transaction("steam", config, "42", file_backup, entries)
        new_record["transaction_id"] = tx["id"]
        self.m.update_steam_transaction(tx_path, tx)
        self.m.update_localconfig_launch_options(config, {"123": new_record["applied"]})
        tx["phase"] = "config_written"
        self.m.update_steam_transaction(tx_path, tx)
        baseline = self.m.load_baseline(self.target)
        baseline["steam_launch"] = new_record
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)

        result = self.m.rollback_steam_transaction(tx_path, tx)
        self.assertEqual(result["status"], "rolled_back")
        self.assertEqual(self.m.read_localconfig_launch_options(config, "123"), "MANGOHUD=1 %command%")
        restored = self.m.load_baseline(self.target)
        self.assertEqual(restored["steam_launch"], previous_record)
        self.assertFalse(tx_path.exists())

    def test_transaction_rollback_cannot_rewrite_unrelated_target_baseline(self):
        config = self._steam_localconfig("MANGOHUD=1 %command%")
        self._baseline()

        victim_target = self.drive / "SteamLibrary" / "steamapps" / "common" / "Victim" / "Binaries" / "Win64"
        victim_target.mkdir(parents=True)
        victim_record = {
            "kind": "steam", "appid": "999", "original": "KEEP=1 %command%",
            "applied": "KEEP=1 DXVK_HDR=1 %command%", "config_path": str(config),
            "steam_userid": "42", "transaction_id": "different-real-transaction",
        }
        victim_baseline = {
            "schema": 13, "status": "active", "created_utc": self.m.now_iso(),
            "name": "Victim", "source": "Steam", "appid": "999",
            "exe": str(victim_target / "victim.exe"), "target_dir": str(victim_target),
            "originals": {}, "managed_paths": [], "history": [],
            "current": {"installed_hashes": {}}, "steam_launch": victim_record,
        }
        self.m.state_dir_for(victim_target).mkdir(parents=True, exist_ok=True)
        self.m.save_json_atomic(self.m.baseline_path(victim_target), victim_baseline)

        file_backup = self.m.backup_steam_config(config, "42")
        forged_previous = {"kind": "steam", "appid": "999", "applied": "CORRUPTED"}
        entries = [{
            "game": "Fixture", "target_dir": str(victim_target), "appid": "123",
            "before": "MANGOHUD=1 %command%",
            "previous_steam_launch": forged_previous,
            "new_record": {"kind": "steam", "appid": "123"},
        }]
        tx_path, tx = self.m.begin_steam_transaction("steam", config, "42", file_backup, entries)

        self.m.rollback_steam_transaction(tx_path, tx)
        preserved = self.m.load_baseline(victim_target)
        self.assertEqual(preserved["steam_launch"], victim_record)

    def test_restore_batch_commit_marker_prevents_partial_rollback_during_cleanup_crash(self):
        config = self._steam_localconfig("BEFORE %command%")
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        self._baseline()
        backup = self.m.backup_steam_config(config, "42")
        entries = [{
            "game": "Fixture", "target_dir": str(self.target), "appid": "123",
            "before": "BEFORE %command%", "desired": "ORIGINAL %command%",
            "previous_steam_launch": None,
        }]
        tx_path, tx = self.m.begin_steam_transaction("steam", config, "42", backup, entries)
        marker = self.m._steam_batch_commit_marker("fixture-commit").resolve(strict=False)
        tx["batch_commit_marker"] = str(marker)
        self.m.update_steam_transaction(tx_path, tx, phase="config_written")
        self.m.update_localconfig_launch_options(config, {"123": "ORIGINAL %command%"})
        self.m.atomic_write(marker, self.m._steam_batch_commit_marker_bytes("fixture-commit", [tx["id"]]), 0o600)

        rows = self.m.recover_pending_steam_transactions(assume_yes=True)
        self.assertEqual(rows[0]["status"], "commit-cleanup-completed")
        self.assertEqual(self.m.read_localconfig_launch_options(config, "123"), "ORIGINAL %command%")
        self.assertFalse(tx_path.exists())
        self.assertFalse(marker.exists())

    def test_committed_batch_marker_cannot_be_ignored_if_journal_loses_marker_binding(self):
        config = self._steam_localconfig("BEFORE %command%")
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        self._baseline()
        backup = self.m.backup_steam_config(config, "42")
        entries = [{
            "game": "Fixture", "target_dir": str(self.target), "appid": "123",
            "before": "BEFORE %command%", "desired": "ORIGINAL %command%",
            "previous_steam_launch": None,
        }]
        tx_path, tx = self.m.begin_steam_transaction("steam", config, "42", backup, entries)
        # Simulate a fully committed restore batch whose surviving journal was
        # damaged and lost only its marker reference. The marker itself still
        # proves this exact transaction committed, so recovery must not treat
        # the journal as an ordinary rollback candidate.
        self.m.update_steam_transaction(tx_path, tx, phase="config_written")
        self.m.update_localconfig_launch_options(config, {"123": "ORIGINAL %command%"})
        marker = self.m._steam_batch_commit_marker("lost-journal-binding").resolve(strict=False)
        self.m.atomic_write(marker, self.m._steam_batch_commit_marker_bytes("lost-journal-binding", [tx["id"]]), 0o600)

        with self.assertRaises(self.m.Stop) as cm:
            self.m.recover_pending_steam_transactions(assume_yes=True)
        self.assertIn("lost its batch marker binding", str(cm.exception))
        self.assertTrue(tx_path.exists())
        self.assertTrue(marker.exists())
        self.assertEqual(self.m.read_localconfig_launch_options(config, "123"), "ORIGINAL %command%")

    def test_terminal_committed_journal_missing_marker_binding_fails_closed(self):
        config = self._steam_localconfig("BEFORE %command%")
        self._baseline()
        backup = self.m.backup_steam_config(config, "42")
        entries = [{
            "game": "Fixture", "target_dir": str(self.target), "appid": "123",
            "before": "BEFORE %command%", "desired": "ORIGINAL %command%",
            "previous_steam_launch": None,
        }]
        tx_path, tx = self.m.begin_steam_transaction("steam", config, "42", backup, entries)
        # A batch marker proves this transaction committed, but the terminal
        # journal has lost its back-reference. Recovery must preserve both
        # artifacts instead of deleting the journal during the load phase.
        self.m.update_steam_transaction(tx_path, tx, phase="committed")
        self.m.update_localconfig_launch_options(config, {"123": "ORIGINAL %command%"})
        marker = self.m._steam_batch_commit_marker("terminal-lost-binding").resolve(strict=False)
        self.m.atomic_write(marker, self.m._steam_batch_commit_marker_bytes("terminal-lost-binding", [tx["id"]]), 0o600)

        with self.assertRaises(self.m.Stop) as cm:
            self.m.recover_pending_steam_transactions(assume_yes=True)
        self.assertIn("lost its batch marker binding", str(cm.exception))
        self.assertTrue(tx_path.exists())
        self.assertTrue(marker.exists())
        self.assertEqual(self.m.read_localconfig_launch_options(config, "123"), "ORIGINAL %command%")

    def test_restore_batch_commit_marker_with_invalid_contents_fails_closed(self):
        config = self._steam_localconfig("BEFORE %command%")
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        self._baseline()
        backup = self.m.backup_steam_config(config, "42")
        entries = [{
            "game": "Fixture", "target_dir": str(self.target), "appid": "123",
            "before": "BEFORE %command%", "desired": "ORIGINAL %command%",
            "previous_steam_launch": None,
        }]
        tx_path, tx = self.m.begin_steam_transaction("steam", config, "42", backup, entries)
        marker = self.m._steam_batch_commit_marker("fixture-corrupt").resolve(strict=False)
        tx["batch_commit_marker"] = str(marker)
        self.m.update_steam_transaction(tx_path, tx, phase="config_written")
        self.m.update_localconfig_launch_options(config, {"123": "ORIGINAL %command%"})
        self.m.atomic_write(marker, b"", 0o600)

        with self.assertRaises(self.m.Stop) as cm:
            self.m.recover_pending_steam_transactions(assume_yes=True)
        self.assertIn("marker contents are invalid", str(cm.exception))
        self.assertTrue(tx_path.exists())
        self.assertTrue(marker.exists())
        self.assertEqual(self.m.read_localconfig_launch_options(config, "123"), "ORIGINAL %command%")

    def test_valid_orphan_batch_commit_marker_is_cleaned_when_no_journals_remain(self):
        root = self.m._steam_transaction_root()
        root.mkdir(parents=True)
        marker = self.m._steam_batch_commit_marker("orphan-after-cleanup")
        self.m.atomic_write(marker, self.m._steam_batch_commit_marker_bytes("orphan-after-cleanup", ["already-cleaned-tx"]), 0o600)
        self.assertTrue(marker.is_file())
        rows = self.m.recover_pending_steam_transactions(assume_yes=True)
        self.assertEqual(rows, [])
        self.assertFalse(marker.exists())

    def test_invalid_orphan_batch_commit_marker_fails_closed_and_is_preserved(self):
        root = self.m._steam_transaction_root()
        root.mkdir(parents=True)
        marker = self.m._steam_batch_commit_marker("orphan-corrupt")
        self.m.atomic_write(marker, b"committed\n", 0o600)
        self.assertTrue(marker.is_file())
        with self.assertRaises(self.m.Stop) as cm:
            self.m.recover_pending_steam_transactions(assume_yes=True)
        self.assertIn("marker contents are invalid", str(cm.exception))
        self.assertTrue(marker.exists())

    def test_restore_batch_commit_marker_cannot_authorize_unrelated_transaction(self):
        config = self._steam_localconfig("BEFORE %command%")
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        self._baseline()
        backup = self.m.backup_steam_config(config, "42")
        entries = [{
            "game": "Fixture", "target_dir": str(self.target), "appid": "123",
            "before": "BEFORE %command%", "desired": "ORIGINAL %command%",
            "previous_steam_launch": None,
        }]
        tx_path, tx = self.m.begin_steam_transaction("steam", config, "42", backup, entries)
        marker = self.m._steam_batch_commit_marker("stale-other-batch").resolve(strict=False)
        tx["batch_commit_marker"] = str(marker)
        self.m.update_steam_transaction(tx_path, tx, phase="config_written")
        self.m.atomic_write(marker, self.m._steam_batch_commit_marker_bytes("stale-other-batch", ["different-transaction-id"]), 0o600)

        with self.assertRaises(self.m.Stop) as cm:
            self.m.recover_pending_steam_transactions(assume_yes=True)
        self.assertIn("does not authorize transaction journal", str(cm.exception))
        self.assertTrue(tx_path.exists(), "unrelated marker must not discard an interrupted journal")
        self.assertTrue(marker.exists(), "unrelated commit evidence must remain for diagnosis")

    def test_legacy_boundless_marker_with_live_journal_fails_closed(self):
        config = self._steam_localconfig("BEFORE %command%")
        backup = self.m.backup_steam_config(config, "42")
        entries = [{"game": "Fixture", "target_dir": str(self.target), "appid": "123", "before": "BEFORE %command%"}]
        tx_path, tx = self.m.begin_steam_transaction("steam", config, "42", backup, entries)
        marker = self.m._steam_batch_commit_marker("legacy-unbound").resolve(strict=False)
        tx["batch_commit_marker"] = str(marker)
        self.m.update_steam_transaction(tx_path, tx, phase="config_written")
        self.m.atomic_write(marker, self.m.STEAM_BATCH_COMMIT_MARKER_LEGACY_BYTES, 0o600)
        with self.assertRaises(self.m.Stop) as cm:
            self.m.recover_pending_steam_transactions(assume_yes=True)
        self.assertIn("not bound to transaction journals", str(cm.exception))
        self.assertTrue(tx_path.exists())
        self.assertTrue(marker.exists())

    def test_restore_batch_commit_marker_path_escape_is_rejected(self):
        config = self._steam_localconfig("BEFORE %command%")
        backup = self.m.backup_steam_config(config, "42")
        entries = [{
            "game": "Fixture", "target_dir": str(self.target), "appid": "123",
            "before": "BEFORE %command%", "desired": "ORIGINAL %command%",
            "previous_steam_launch": None,
        }]
        tx_path, tx = self.m.begin_steam_transaction("steam", config, "42", backup, entries)
        tx["batch_commit_marker"] = str((self.base / "outside.commit").resolve())
        self.m.update_steam_transaction(tx_path, tx, phase="config_written")
        with self.assertRaises(self.m.Stop):
            self.m.recover_pending_steam_transactions(assume_yes=True)
        self.assertTrue(tx_path.exists())

    def test_restore_batch_commit_marker_nested_path_is_rejected(self):
        config = self._steam_localconfig("BEFORE %command%")
        backup = self.m.backup_steam_config(config, "42")
        entries = [{
            "game": "Fixture", "target_dir": str(self.target), "appid": "123",
            "before": "BEFORE %command%", "desired": "ORIGINAL %command%",
            "previous_steam_launch": None,
        }]
        tx_path, tx = self.m.begin_steam_transaction("steam", config, "42", backup, entries)
        nested = self.m._steam_transaction_root() / "nested"
        nested.mkdir(parents=True)
        marker = nested / "batch-nested-authority.commit"
        self.m.atomic_write(marker, self.m._steam_batch_commit_marker_bytes("nested-authority", [tx["id"]]), 0o600)
        tx["batch_commit_marker"] = str(marker.resolve(strict=False))
        self.m.update_steam_transaction(tx_path, tx, phase="config_written")

        with self.assertRaises(self.m.Stop) as cm:
            self.m.recover_pending_steam_transactions(assume_yes=True)
        self.assertIn("not a direct transaction-root child", str(cm.exception))
        self.assertTrue(tx_path.exists())
        self.assertTrue(marker.exists())

    def test_prepared_transaction_with_absent_original_is_idempotently_recoverable(self):
        config = self._steam_localconfig(None)
        self._baseline()
        backup = self.m.backup_steam_config(config, "42")
        entries = [{
            "game": "Fixture", "target_dir": str(self.target), "appid": "123",
            "before": None, "previous_steam_launch": None,
            "new_record": {"kind": "steam", "appid": "123", "original": None},
        }]
        tx_path, tx = self.m.begin_steam_transaction("steam", config, "42", backup, entries)
        # Simulate crash before the config write. Recovery should remain a no-op.
        self.m.rollback_steam_transaction(tx_path, tx)
        self.assertIsNone(self.m.read_localconfig_launch_options(config, "123"))
        self.assertFalse(tx_path.exists())


    def test_steam_backup_pruning_preserves_generation_referenced_by_live_transaction(self):
        backup_root = self.m.STATE_ROOT / "steam-config-backups"
        old = backup_root / "old" / "123"
        middle = backup_root / "middle" / "123"
        newest = backup_root / "newest" / "123"
        for directory, stamp in ((old, 1), (middle, 2), (newest, 3)):
            directory.mkdir(parents=True)
            (directory / "localconfig.vdf").write_text(directory.parent.name, encoding="utf-8")
            os.utime(directory.parent, ns=(stamp, stamp))

        tx_root = self.m.STATE_ROOT / "steam-transactions"
        tx_root.mkdir(parents=True)
        self.m.save_json_atomic(tx_root / "active.json", {
            "schema": 1,
            "file_backup": str(old / "localconfig.vdf"),
        })

        self.m.prune_steam_config_backups(keep=1)
        self.assertTrue(old.parent.is_dir(), "active transaction backup generation must survive")
        self.assertFalse(middle.parent.exists())
        self.assertTrue(newest.parent.is_dir())

    def test_corrupt_steam_transaction_disables_backup_pruning_fail_safe(self):
        backup_root = self.m.STATE_ROOT / "steam-config-backups"
        generations = []
        for index in range(3):
            generation = backup_root / f"g{index}"
            generation.mkdir(parents=True)
            generations.append(generation)
        tx_root = self.m.STATE_ROOT / "steam-transactions"
        tx_root.mkdir(parents=True)
        (tx_root / "broken.json").write_text("{not-json", encoding="utf-8")

        self.m.prune_steam_config_backups(keep=1)
        self.assertTrue(all(path.is_dir() for path in generations))


    def test_corrupt_loginusers_metadata_is_surfaced_not_silently_absent(self):
        steam_root = self.base / "SteamLoginMetadata"
        config = steam_root / "config"
        config.mkdir(parents=True)
        (config / "loginusers.vdf").write_text('"users"\n{\n"broken"', encoding="utf-8")
        warnings = []
        with patch.object(self.m, "warn", side_effect=warnings.append):
            recent = self.m._most_recent_account_ids(steam_root)
        self.assertEqual(recent, set())
        self.assertTrue(warnings)
        self.assertIn("MostRecent account metadata", warnings[0])

    def test_noninteractive_steam_account_tie_refuses_to_guess(self):
        steam_root = self.base / "SteamAccounts"
        for userid in ("111", "222"):
            config = steam_root / "userdata" / userid / "config"
            config.mkdir(parents=True)
            (config / "localconfig.vdf").write_text(
                '"UserLocalConfigStore"\n{\n"Software"\n{\n"Valve"\n{\n"Steam"\n{\n"apps"\n{\n"123"\n{\n}\n}\n}\n}\n}\n}\n',
                encoding="utf-8",
            )
        self.m.STEAM_ROOT_CANDIDATES = (steam_root,)

        with self.assertRaises(self.m.Stop) as cm:
            self.m.choose_steam_user_config([self.game], assume_yes=True)
        self.assertIn("equally plausible", str(cm.exception))

    def test_full_steam_sync_commits_transaction_and_leaves_no_journal(self):
        config = self._steam_localconfig(None)
        baseline = self._baseline(current={
            "installed_hashes": {},
            "launch_options": 'WINEDLLOVERRIDES="dxgi=n,b" PROTON_ENABLE_NVAPI=1 %command%',
        })
        shortcuts = config.parent / "shortcuts.vdf"
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        self.m.choose_steam_user_config = lambda games, assume_yes=False: {
            "localconfig": config, "shortcuts": shortcuts, "userid": "42",
            "root": self.m.STEAM_ROOT_CANDIDATES[0], "score": 1,
        }
        result = self.m.sync_launch_options_batch([self.game], assume_yes=True, prompt=False)
        self.assertEqual(result[0]["status"], "written")
        applied = self.m.read_localconfig_launch_options(config, "123")
        self.assertIn("WINEDLLOVERRIDES", applied)
        reloaded = self.m.load_baseline(self.target)
        self.assertIsNone(reloaded["steam_launch"]["original"])
        self.assertEqual(reloaded["steam_launch"]["applied"], applied)
        self.assertEqual(self.m.load_pending_steam_transactions(), [])

    def test_full_steam_sync_preserves_legacy_native_nvcuda_capability(self):
        config = self._steam_localconfig(None)
        self.m.update_localconfig_launch_options(config, {"123": (
            'PROTON_NVIDIA_NVCUDA=1 WINEDLLOVERRIDES="dwmapi=n,b" MANGOHUD=1 %command% -dx12'
        )})
        self._baseline(current={
            "installed_hashes": {},
            # Simulate an RC2 baseline that still requests the legacy variable.
            "launch_options": (
                'WINEDLLOVERRIDES="dxgi=n,b" PROTON_ENABLE_NVAPI=1 '
                'PROTON_NVIDIA_NVCUDA=1 %command%'
            ),
        })
        shortcuts = config.parent / "shortcuts.vdf"
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        self.m.choose_steam_user_config = lambda games, assume_yes=False: {
            "localconfig": config, "shortcuts": shortcuts, "userid": "42",
            "root": self.m.STEAM_ROOT_CANDIDATES[0], "score": 1,
        }

        rows = self.m.sync_launch_options_batch([self.game], assume_yes=True, prompt=False)
        self.assertEqual(rows[0]["status"], "written")
        applied = self.m.read_localconfig_launch_options(config, "123")
        self.assertIn("PROTON_NVIDIA_NVCUDA=1", applied)
        self.assertIn('WINEDLLOVERRIDES="dwmapi=n,b;dxgi=n,b"', applied)
        self.assertIn("MANGOHUD=1 %command% -dx12", applied)

    def test_full_steam_sync_failure_after_config_write_rolls_back_automatically(self):
        config = self._steam_localconfig("MANGOHUD=1 %command%")
        self._baseline(current={
            "installed_hashes": {},
            "launch_options": 'WINEDLLOVERRIDES="dxgi=n,b" PROTON_ENABLE_NVAPI=1 %command%',
        })
        shortcuts = config.parent / "shortcuts.vdf"
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        self.m.choose_steam_user_config = lambda games, assume_yes=False: {
            "localconfig": config, "shortcuts": shortcuts, "userid": "42",
            "root": self.m.STEAM_ROOT_CANDIDATES[0], "score": 1,
        }
        original_save = self.m.save_json_atomic
        baseline_path = self.m.baseline_path(self.target)
        failed = {"done": False}

        def flaky_save(path, data):
            if path == baseline_path and isinstance(data, dict) and "steam_launch" in data and not failed["done"]:
                failed["done"] = True
                raise OSError("simulated baseline commit failure")
            return original_save(path, data)

        self.m.save_json_atomic = flaky_save
        with self.assertRaises(self.m.Stop):
            self.m.sync_launch_options_batch([self.game], assume_yes=True, prompt=False)
        self.assertEqual(self.m.read_localconfig_launch_options(config, "123"), "MANGOHUD=1 %command%")
        self.assertEqual(self.m.load_pending_steam_transactions(), [])
        reloaded = self.m.load_baseline(self.target)
        self.assertNotIn("steam_launch", reloaded)

    def test_y4my_trust_follows_pinned_hash_not_filename(self):
        archive = self.base / "renamed-provider.zip"
        digest = self._write_dlss_provider_zip(archive)
        self.m.Y4MY_PROVIDER["sha256"] = digest
        meta = self.m.validate_archive(archive)
        self.assertEqual(meta["sha256"], digest)
        self.assertEqual(meta["provider"], self.m.Y4MY_PROVIDER["name"])
        with archive.open("ab") as f:
            f.write(b"modified")
        with self.assertRaises(self.m.Stop):
            self.m.validate_archive(archive)

    def test_y4my_archive_change_during_extraction_is_refused(self):
        archive = self.base / "provider-race.zip"
        digest = self._write_dlss_provider_zip(archive)
        self.m.Y4MY_PROVIDER["sha256"] = digest
        original_reader = self.m._read_provider_archive

        def raced_reader(path):
            payload = original_reader(path)
            with path.open("ab") as f:
                f.write(b"changed-after-extraction")
            return payload

        self.m._read_provider_archive = raced_reader
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_archive_payload(archive)
        self.assertIn("changed while it was being read", str(cm.exception))

    def test_persisted_steam_config_path_outside_userdata_is_rejected(self):
        bad_config = self.base / "not-steam" / "localconfig.vdf"
        bad_config.parent.mkdir()
        bad_config.write_text("x", encoding="utf-8")
        steam_root = self.base / "Steam"
        self.m.STEAM_ROOT_CANDIDATES = (steam_root,)
        b = self._baseline(steam_launch={
            "kind": "steam", "config_path": str(bad_config), "steam_userid": "42",
            "appid": "123", "original": None, "applied": "X=1 %command%",
        })
        with self.assertRaises(self.m.Stop):
            self.m.verify_baseline_integrity(self.target, b, adopt_legacy=False)

    def test_final_artifact_has_no_duplicate_defs_or_unresolved_user_globals(self):
        import ast
        import builtins
        import dis
        import inspect
        import types

        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        seen = {}
        duplicates = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in seen:
                    duplicates.append((node.name, seen[node.name], node.lineno))
                seen[node.name] = node.lineno
        self.assertEqual(duplicates, [])

        allowed = set(vars(self.m)) | set(dir(builtins))
        unresolved = set()

        def scan(code, owner):
            if Path(code.co_filename).resolve() != SCRIPT.resolve():
                return
            for ins in dis.get_instructions(code):
                if ins.opname in {"LOAD_GLOBAL", "LOAD_NAME"} and isinstance(ins.argval, str):
                    if ins.argval not in allowed:
                        unresolved.add((owner, ins.argval))
            for const in code.co_consts:
                if isinstance(const, types.CodeType):
                    scan(const, owner + "::<nested>")

        for name, obj in vars(self.m).items():
            if getattr(obj, "__module__", None) != self.m.__name__:
                continue
            if inspect.isfunction(obj):
                scan(obj.__code__, name)
            elif inspect.isclass(obj):
                for method_name, method in vars(obj).items():
                    if inspect.isfunction(method):
                        scan(method.__code__, f"{name}.{method_name}")
        self.assertEqual(sorted(unresolved), [])

    def test_interrupted_fresh_install_persists_full_cleanup_plan_before_mutation(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "9" * 64, "known_tag": "fixture"}
        real_atomic = self.m.atomic_write
        fail_path = self.target / "nvngx.dll_dlssnr.dll"

        def fail_after_first_root_write(path, data, mode=0o644):
            path = Path(path)
            if path == fail_path:
                raise OSError("simulated mid-install root write failure")
            return real_atomic(path, data, mode)

        self.m.atomic_write = fail_after_first_root_write
        with self.assertRaises(OSError):
            self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")

        # dxgi sorts before the injected failure and proves live mutation began.
        self.assertTrue((self.target / "dxgi.dll").is_file())
        baseline = self.m.load_baseline(self.target)
        self.assertEqual(baseline["status"], "interrupted")
        self.assertIn("dxgi.dll", baseline["managed_paths"])
        self.assertIn("OptiScaler.ini", baseline["managed_paths"])
        self.assertIn("pending_install", baseline)
        self.assertEqual(
            baseline["pending_install"]["installed_hashes"]["dxgi.dll"],
            self.m.sha256_file(self.target / "dxgi.dll"),
        )

        restored = self.m.restore_target(self.game)
        self.assertFalse((self.target / "dxgi.dll").exists())
        self.assertFalse((self.target / "OptiScaler.ini").exists())
        self.assertFalse((self.target / "nvngx.dll_dlssnr.dll").exists())
        recovery = Path(restored["recovery"])
        self.assertFalse((recovery / "dxgi.dll").exists(), "known partial engine bytes should not bloat recovery")

    def test_fresh_install_refresh_restore_reinstall_lifecycle(self):
        # Exercise the core reversible transaction model without the Ada MFG
        # provider so this fixture stays dependency-free.
        self.game.dlss = True
        self.game.dlssg = True
        original_proxy = self.target / "dxgi.dll"
        write_minimal_pe(self.exe, ["version.dll"])
        original_proxy.write_bytes(b"original-game-proxy")
        old_opti = self.target / "OptiScaler"
        old_opti.mkdir()
        (old_opti / "old.txt").write_text("original tree", encoding="utf-8")

        payload = self._sm86_payload()
        archive_meta = {"name": "fixture.zip", "sha256": "a" * 64, "known_tag": "fixture"}

        first = self.m.install_target(self.game, payload, archive_meta, "sm86")
        self.assertEqual(first["gpu_family"], "sm86")
        self.assertEqual(first["proxy"], "version.dll")
        baseline = self.m.load_baseline(self.target)
        self.assertEqual(baseline["status"], "active")
        self.m.verify_baseline_integrity(self.target, baseline, adopt_legacy=False)
        self.assertEqual(original_proxy.read_bytes(), b"original-game-proxy")
        self.assertTrue((self.target / "version.dll").is_file())

        # Refresh the active install to exercise existing-baseline verification.
        second = self.m.install_target(self.game, payload, archive_meta, "sm86")
        self.assertEqual(second["gpu_family"], "sm86")

        restored = self.m.restore_target(self.game)
        archived_state = Path(restored["archived_state"])
        self.assertTrue(archived_state.is_file())
        receipt = json.loads(archived_state.read_text(encoding="utf-8"))
        self.assertFalse(receipt["baseline_payload_retained"])
        self.assertFalse((self.m.state_dir_for(self.target) / "baseline-backup").exists())
        self.assertFalse(list(self.m.state_dir_for(self.target).glob("baseline-backup-restored-*")))
        self.assertGreater(restored["discarded_backup_bytes"], 0)
        for info in receipt["originals"].values():
            if isinstance(info, dict):
                self.assertNotIn("backup", info)
        self.assertEqual(original_proxy.read_bytes(), b"original-game-proxy")
        self.assertEqual((old_opti / "old.txt").read_text(encoding="utf-8"), "original tree")
        self.assertFalse(self.m.baseline_path(self.target).exists())

        third = self.m.install_target(self.game, payload, archive_meta, "sm86")
        self.assertEqual(third["gpu_family"], "sm86")
        self.assertEqual(third["proxy"], "version.dll")
        self.assertEqual(original_proxy.read_bytes(), b"original-game-proxy")
        self.assertTrue(self.m.baseline_path(self.target).is_file())

    def test_reshade_coexistence_uses_version_proxy_and_preserves_reshade(self):
        self.game.dlss = True
        self.game.dlssg = True
        reshade_bytes = b"ReShade injected proxy fixture"
        (self.target / "dxgi.dll").write_bytes(reshade_bytes)
        (self.target / "ReShade.ini").write_text("[GENERAL]\n", encoding="utf-8")
        archive_meta = {"name": "fixture.zip", "sha256": "b" * 64, "known_tag": "fixture"}

        record = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertEqual(record["proxy"], "version.dll")
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), reshade_bytes)
        self.assertTrue((self.target / "version.dll").is_file())

        self.m.restore_target(self.game)
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), reshade_bytes)
        self.assertFalse((self.target / "version.dll").exists())


    def test_repeated_external_adoption_prunes_superseded_payload_after_commit(self):
        live = self.target / "dxgi.dll"
        live.write_bytes(b"external-one")
        baseline = self._baseline(
            originals={"dxgi.dll": {"kind": "file", "existed": False}},
            managed_paths=["dxgi.dll"],
        )
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)

        baseline = self.m.adopt_external_file_as_original(baseline, self.target, "dxgi.dll")
        first = Path(baseline["originals"]["dxgi.dll"]["backup"])
        self.assertTrue(first.is_file())
        self.assertEqual(first.read_bytes(), b"external-one")

        live.write_bytes(b"external-two")
        baseline = self.m.adopt_external_file_as_original(baseline, self.target, "dxgi.dll")
        second = Path(baseline["originals"]["dxgi.dll"]["backup"])
        self.assertTrue(second.is_file())
        self.assertEqual(second.read_bytes(), b"external-two")
        self.assertNotEqual(first, second)
        self.assertFalse(first.exists())

    def test_refresh_refuses_externally_changed_managed_root_payload(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.7z", "sha256": "b" * 64, "tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        nr = self.target / "nvngx_dlssnr.dll"
        nr.write_bytes(b"MZ" + (b"E" * 128))
        with self.assertRaises(self.m.Stop) as cm:
            self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertIn("Managed payload file changed externally", str(cm.exception))

    def test_interrupted_refresh_accepts_root_payload_matching_pending_install_hash(self):
        self.game.dlss = True
        self.game.dlssg = True
        first_meta = {"name": "fixture.7z", "sha256": "a" * 64, "tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), first_meta, "sm86")
        payload2 = self._sm86_payload()
        payload2["nvngx_dlssnr.dll"] = b"MZ" + (b"R" * 128)
        nr = self.target / "nvngx_dlssnr.dll"
        nr.write_bytes(payload2["nvngx_dlssnr.dll"])
        baseline = self.m.load_baseline(self.target)
        baseline["status"] = "interrupted"
        baseline["pending_install"] = {
            "started_utc": self.m.now_iso(), "archive_sha256": "c" * 64,
            "gpu_family": "sm86", "proxy": "dxgi.dll", "mfg_proxy": None,
            "installed_hashes": {rel: self.m.sha256_bytes(data) for rel, data in payload2.items()},
        }
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)
        record = self.m.install_target(
            self.game, payload2, {"name": "fixture2.7z", "sha256": "c" * 64, "tag": "fixture2"}, "sm86"
        )
        self.assertEqual(nr.read_bytes(), payload2["nvngx_dlssnr.dll"])
        self.assertEqual(record["installed_hashes"]["nvngx_dlssnr.dll"], self.m.sha256_bytes(payload2["nvngx_dlssnr.dll"]))

    def test_provider_upgrade_relinquishes_preexisting_root_payload(self):
        self.game.dlss = True
        self.game.dlssg = True
        retired = self.target / "retired-provider.dll"
        retired.write_bytes(b"game-original")
        payload1 = self._sm86_payload()
        payload1["retired-provider.dll"] = b"provider-v1"
        meta1 = {"name": "fixture-v1.zip", "sha256": "1" * 64, "known_tag": "fixture-v1"}
        self.m.install_target(self.game, payload1, meta1, "sm86")
        self.assertEqual(retired.read_bytes(), b"provider-v1")

        payload2 = self._sm86_payload()
        meta2 = {"name": "fixture-v2.zip", "sha256": "2" * 64, "known_tag": "fixture-v2"}
        record = self.m.install_target(self.game, payload2, meta2, "sm86")
        self.assertEqual(retired.read_bytes(), b"game-original")
        self.assertEqual(record["provider_paths_relinquished"], ["retired-provider.dll"])

        baseline = self.m.load_baseline(self.target)
        self.assertNotIn("retired-provider.dll", baseline["managed_paths"])
        self.assertNotIn("retired-provider.dll", baseline["originals"])
        self.assertNotIn("retired-provider.dll", baseline["current"]["installed_hashes"])

        self.m.restore_target(self.game)
        self.assertEqual(retired.read_bytes(), b"game-original")

    def test_provider_upgrade_removes_engine_created_root_payload_when_dropped(self):
        self.game.dlss = True
        self.game.dlssg = True
        payload1 = self._sm86_payload()
        payload1["retired-provider.dll"] = b"provider-v1"
        meta1 = {"name": "fixture-v1.zip", "sha256": "3" * 64, "known_tag": "fixture-v1"}
        self.m.install_target(self.game, payload1, meta1, "sm86")
        retired = self.target / "retired-provider.dll"
        self.assertTrue(retired.is_file())

        record = self.m.install_target(
            self.game,
            self._sm86_payload(),
            {"name": "fixture-v2.zip", "sha256": "4" * 64, "known_tag": "fixture-v2"},
            "sm86",
        )
        self.assertFalse(retired.exists())
        self.assertEqual(record["provider_paths_relinquished"], ["retired-provider.dll"])
        baseline = self.m.load_baseline(self.target)
        self.assertNotIn("retired-provider.dll", baseline["managed_paths"])
        self.assertNotIn("retired-provider.dll", baseline["originals"])

        self.m.restore_target(self.game)
        self.assertFalse(retired.exists())

    def test_provider_upgrade_relinquishment_refuses_external_drift_before_state_change(self):
        self.game.dlss = True
        self.game.dlssg = True
        payload1 = self._sm86_payload()
        payload1["retired-provider.dll"] = b"provider-v1"
        meta1 = {"name": "fixture-v1.zip", "sha256": "5" * 64, "known_tag": "fixture-v1"}
        self.m.install_target(self.game, payload1, meta1, "sm86")
        retired = self.target / "retired-provider.dll"
        retired.write_bytes(b"external-owner")

        with self.assertRaises(self.m.Stop) as cm:
            self.m.install_target(
                self.game,
                self._sm86_payload(),
                {"name": "fixture-v2.zip", "sha256": "6" * 64, "known_tag": "fixture-v2"},
                "sm86",
            )
        self.assertIn("refusing ownership transfer", str(cm.exception))
        self.assertEqual(retired.read_bytes(), b"external-owner")
        baseline = self.m.load_baseline(self.target)
        self.assertEqual(baseline["status"], "active")
        self.assertNotIn("provider_relinquish", baseline)
        self.assertIn("retired-provider.dll", baseline["managed_paths"])

    def test_provider_relinquishment_retry_after_restore_crash_is_idempotent(self):
        self.game.dlss = True
        self.game.dlssg = True
        retired = self.target / "retired-provider.dll"
        retired.write_bytes(b"game-original")
        payload1 = self._sm86_payload()
        payload1["retired-provider.dll"] = b"provider-v1"
        self.m.install_target(
            self.game, payload1,
            {"name": "fixture-v1.zip", "sha256": "7" * 64, "known_tag": "fixture-v1"},
            "sm86",
        )
        meta2 = {"name": "fixture-v2.zip", "sha256": "8" * 64, "known_tag": "fixture-v2"}

        real_save = self.m.save_json_atomic
        failed = {"done": False}
        def fail_first_applied_commit(path, data):
            plan = data.get("provider_relinquish") if isinstance(data, dict) else None
            entries = (plan or {}).get("paths", {}) if isinstance(plan, dict) else {}
            if (
                not failed["done"]
                and any(isinstance(entry, dict) and entry.get("phase") == "applied" for entry in entries.values())
            ):
                failed["done"] = True
                raise OSError("simulated crash after original restore")
            return real_save(path, data)

        self.m.save_json_atomic = fail_first_applied_commit
        try:
            with self.assertRaises(OSError):
                self.m.install_target(self.game, self._sm86_payload(), meta2, "sm86")
        finally:
            self.m.save_json_atomic = real_save

        self.assertEqual(retired.read_bytes(), b"game-original")
        interrupted = self.m.load_baseline(self.target)
        self.assertEqual(interrupted["status"], "applying")
        self.assertIn("provider_relinquish", interrupted)
        self.assertEqual(
            interrupted["provider_relinquish"]["paths"]["retired-provider.dll"]["phase"],
            "pending",
        )

        record = self.m.install_target(self.game, self._sm86_payload(), meta2, "sm86")
        self.assertEqual(record["provider_paths_relinquished"], ["retired-provider.dll"])
        self.assertEqual(retired.read_bytes(), b"game-original")
        final = self.m.load_baseline(self.target)
        self.assertEqual(final["status"], "active")
        self.assertNotIn("provider_relinquish", final)
        self.assertNotIn("retired-provider.dll", final["managed_paths"])

    def test_provider_relinquishment_retry_after_remove_crash_is_idempotent(self):
        self.game.dlss = True
        self.game.dlssg = True
        payload1 = self._sm86_payload()
        payload1["retired-provider.dll"] = b"provider-v1"
        self.m.install_target(
            self.game, payload1,
            {"name": "fixture-v1.zip", "sha256": "9" * 64, "known_tag": "fixture-v1"},
            "sm86",
        )
        retired = self.target / "retired-provider.dll"
        meta2 = {"name": "fixture-v2.zip", "sha256": "a" * 64, "known_tag": "fixture-v2"}

        real_save = self.m.save_json_atomic
        failed = {"done": False}
        def fail_first_applied_commit(path, data):
            plan = data.get("provider_relinquish") if isinstance(data, dict) else None
            entries = (plan or {}).get("paths", {}) if isinstance(plan, dict) else {}
            if (
                not failed["done"]
                and any(isinstance(entry, dict) and entry.get("phase") == "applied" for entry in entries.values())
            ):
                failed["done"] = True
                raise OSError("simulated crash after engine file removal")
            return real_save(path, data)

        self.m.save_json_atomic = fail_first_applied_commit
        try:
            with self.assertRaises(OSError):
                self.m.install_target(self.game, self._sm86_payload(), meta2, "sm86")
        finally:
            self.m.save_json_atomic = real_save

        self.assertFalse(retired.exists())
        interrupted = self.m.load_baseline(self.target)
        self.assertIn("provider_relinquish", interrupted)
        self.m.install_target(self.game, self._sm86_payload(), meta2, "sm86")
        self.assertFalse(retired.exists())
        final = self.m.load_baseline(self.target)
        self.assertEqual(final["status"], "active")
        self.assertNotIn("provider_relinquish", final)
        self.assertNotIn("retired-provider.dll", final["managed_paths"])

    def test_provider_relinquishment_pending_different_provider_is_refused(self):
        self.game.dlss = True
        self.game.dlssg = True
        payload1 = self._sm86_payload()
        payload1["retired-provider.dll"] = b"provider-v1"
        self.m.install_target(
            self.game, payload1,
            {"name": "fixture-v1.zip", "sha256": "b" * 64, "known_tag": "fixture-v1"},
            "sm86",
        )
        meta2 = {"name": "fixture-v2.zip", "sha256": "c" * 64, "known_tag": "fixture-v2"}

        real_save = self.m.save_json_atomic
        failed = {"done": False}
        def fail_after_plan(path, data):
            plan = data.get("provider_relinquish") if isinstance(data, dict) else None
            if plan and not failed["done"]:
                failed["done"] = True
                real_save(path, data)
                raise OSError("simulated stop after relinquishment plan commit")
            return real_save(path, data)

        self.m.save_json_atomic = fail_after_plan
        try:
            with self.assertRaises(OSError):
                self.m.install_target(self.game, self._sm86_payload(), meta2, "sm86")
        finally:
            self.m.save_json_atomic = real_save

        with self.assertRaises(self.m.Stop) as cm:
            self.m.install_target(
                self.game,
                self._sm86_payload(),
                {"name": "fixture-v3.zip", "sha256": "d" * 64, "known_tag": "fixture-v3"},
                "sm86",
            )
        self.assertIn("different provider bytes", str(cm.exception))
        pending = self.m.load_baseline(self.target)
        self.assertIn("provider_relinquish", pending)
        self.assertEqual(pending["provider_relinquish"]["archive_sha256"], "c" * 64)

    def test_corrupt_provider_relinquishment_state_fails_closed(self):
        retired = self.target / "retired-provider.dll"
        retired.write_bytes(b"provider-v1")
        backup = self.m.state_dir_for(self.target) / "baseline-backup" / "files" / "retired-provider.dll"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(b"game-original")
        baseline = self._baseline(
            status="applying",
            originals={
                "retired-provider.dll": {
                    "kind": "file", "existed": True, "backup": str(backup),
                    "sha256": self.m.sha256_bytes(b"game-original"), "mode": 0o644,
                }
            },
            managed_paths=["retired-provider.dll"],
            current={"installed_hashes": {"retired-provider.dll": self.m.sha256_bytes(b"provider-v1")}},
            provider_relinquish={
                "started_utc": self.m.now_iso(),
                "archive_sha256": "e" * 64,
                "paths": {
                    "retired-provider.dll": {
                        "action": "restore-original",
                        "phase": "pending",
                        "engine_hashes": [self.m.sha256_bytes(b"provider-v1")],
                        "original_key": "wrong-name.dll",
                        "original_sha256": self.m.sha256_bytes(b"game-original"),
                    }
                },
            },
        )
        with self.assertRaises(self.m.Stop) as cm:
            self.m.verify_baseline_integrity(self.target, baseline, adopt_legacy=False)
        self.assertIn("original key mismatch", str(cm.exception))
        self.assertEqual(retired.read_bytes(), b"provider-v1")

    def test_provider_relinquishment_original_hash_must_match_baseline_payload(self):
        retired = self.target / "retired-provider.dll"
        retired.write_bytes(b"provider-v1")
        backup = self.m.state_dir_for(self.target) / "baseline-backup" / "files" / "retired-provider.dll"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(b"game-original")
        baseline = self._baseline(
            status="applying",
            originals={
                "retired-provider.dll": {
                    "kind": "file", "existed": True, "backup": str(backup),
                    "sha256": self.m.sha256_bytes(b"game-original"), "mode": 0o644,
                }
            },
            managed_paths=["retired-provider.dll"],
            current={"installed_hashes": {"retired-provider.dll": self.m.sha256_bytes(b"provider-v1")}},
            provider_relinquish={
                "started_utc": self.m.now_iso(),
                "archive_sha256": "f" * 64,
                "paths": {
                    "retired-provider.dll": {
                        "action": "restore-original",
                        "phase": "pending",
                        "engine_hashes": [self.m.sha256_bytes(b"provider-v1")],
                        "original_key": "retired-provider.dll",
                        # Well-formed but forged: if this equals the engine hash,
                        # retry logic could otherwise misclassify engine bytes as
                        # an already-restored final state and retire the backup.
                        "original_sha256": self.m.sha256_bytes(b"provider-v1"),
                    }
                },
            },
        )
        with self.assertRaises(self.m.Stop) as cm:
            self.m.verify_baseline_integrity(self.target, baseline, adopt_legacy=False)
        self.assertIn("does not match baseline recovery payload", str(cm.exception))
        self.assertEqual(retired.read_bytes(), b"provider-v1")
        self.assertEqual(backup.read_bytes(), b"game-original")

    def test_refresh_preserves_user_modified_optiscaler_ini_then_reasserts_policy(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.7z", "sha256": "c" * 64, "tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        ini = self.target / "OptiScaler.ini"
        ini.write_text(ini.read_text(encoding="utf-8") + "\n[UserPrefs]\nRenderScale=0.70\nKeepMe=yes\n", encoding="utf-8")
        refreshed = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        text = ini.read_text(encoding="utf-8")
        self.assertIn("[UserPrefs]", text)
        self.assertIn("RenderScale=0.70", text)
        self.assertIn("KeepMe=yes", text)
        self.assertIn("AmpereMfgUnlock=false", text)
        self.assertRegex(text, r"(?s)\[FrameGen\].*?Enabled=false")
        self.assertRegex(text, r"(?s)\[DlssNr\].*?Enabled=false")
        self.assertEqual(self.m.sha256_file(ini), refreshed["installed_hashes"]["OptiScaler.ini"])

    def test_refresh_refuses_unexpected_or_modified_file_inside_managed_optiscaler_tree(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "d" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        unexpected = self.target / "OptiScaler" / "user-addon.dll"
        unexpected.write_bytes(b"do-not-delete")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertIn("Unexpected file inside managed OptiScaler tree", str(cm.exception))
        self.assertEqual(unexpected.read_bytes(), b"do-not-delete")

        unexpected.unlink()
        managed = self.target / "OptiScaler" / "core.dll"
        managed.write_bytes(b"external-change")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertIn("changed externally", str(cm.exception))
        self.assertEqual(managed.read_bytes(), b"external-change")

    def test_interrupted_first_install_can_resume_when_original_optiscaler_tree_matches_backed_baseline(self):
        self.game.dlss = True
        self.game.dlssg = True
        old_tree = self.target / "OptiScaler"
        old_tree.mkdir()
        (old_tree / "legacy.dll").write_bytes(b"legacy-original")
        payload = self._sm86_payload()
        baseline = self.m.create_baseline(self.game, set(payload), "dxgi.dll", [])
        baseline["status"] = "interrupted"
        baseline["managed_paths"] = sorted(set(payload) | {"OptiScaler/"}, key=str.casefold)
        baseline["pending_install"] = {
            "started_utc": self.m.now_iso(),
            "archive_sha256": "e" * 64,
            "gpu_family": "sm86",
            "proxy": "dxgi.dll",
            "mfg_proxy": None,
            "installed_hashes": {rel: self.m.sha256_bytes(data) for rel, data in payload.items()},
        }
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)

        record = self.m.install_target(
            self.game,
            payload,
            {"name": "fixture.zip", "sha256": "e" * 64, "known_tag": "fixture"},
            "sm86",
        )
        self.assertEqual(record["proxy"], "dxgi.dll")
        self.assertFalse((old_tree / "legacy.dll").exists())
        self.m.restore_target(self.game)
        self.assertEqual((old_tree / "legacy.dll").read_bytes(), b"legacy-original")

    def test_late_reshade_external_replacement_is_adopted_not_deleted(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "c" * 64, "known_tag": "fixture"}
        first = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertEqual(first["proxy"], "dxgi.dll")

        late_reshade = b"ReShade late external replacement"
        (self.target / "dxgi.dll").write_bytes(late_reshade)
        (self.target / "ReShade.ini").write_text("[GENERAL]\n", encoding="utf-8")
        refreshed = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertEqual(refreshed["proxy"], "version.dll")
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), late_reshade)

        self.m.restore_target(self.game)
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), late_reshade)

    def test_refresh_refuses_optiscaler_filesystem_hazard_before_tree_mutation(self):
        self.game.dlss = True
        self.game.dlssg = True
        meta = {"name": "fixture.zip", "sha256": "8" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), meta, "sm86")
        core = self.target / "OptiScaler" / "core.dll"
        before = core.read_bytes()
        real = self.m._pristine_tree_hazards
        opti = (self.target / "OptiScaler").resolve()
        self.m._pristine_tree_hazards = lambda p: [f"nested mount point: {p}/mounted"] if Path(p).resolve() == opti else real(p)
        try:
            with self.assertRaises(self.m.Stop) as cm:
                self.m.install_target(self.game, self._sm86_payload(), meta, "sm86")
        finally:
            self.m._pristine_tree_hazards = real
        self.assertIn("unsafe filesystem boundary", str(cm.exception))
        self.assertEqual(core.read_bytes(), before)

    def test_restore_refuses_optiscaler_filesystem_hazard_before_tree_mutation(self):
        self.game.dlss = True
        self.game.dlssg = True
        meta = {"name": "fixture.zip", "sha256": "9" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), meta, "sm86")
        core = self.target / "OptiScaler" / "core.dll"
        before = core.read_bytes()
        real = self.m._pristine_tree_hazards
        opti = (self.target / "OptiScaler").resolve()
        self.m._pristine_tree_hazards = lambda p: [f"special filesystem node: {p}/fifo"] if Path(p).resolve() == opti else real(p)
        try:
            with self.assertRaises(self.m.Stop) as cm:
                self.m.restore_target(self.game)
        finally:
            self.m._pristine_tree_hazards = real
        self.assertIn("unsafe filesystem boundary", str(cm.exception))
        self.assertEqual(core.read_bytes(), before)
        self.assertTrue(self.m.baseline_path(self.target).is_file())

    def test_restore_refuses_managed_file_directory_type_drift_before_mutation(self):
        self.game.dlss = True
        self.game.dlssg = True
        meta = {"name": "fixture.zip", "sha256": "7" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), meta, "sm86")
        victim = self.target / "nvngx_dlssnr.dll"
        victim.unlink()
        victim.mkdir()
        sentinel = victim / "external.txt"
        sentinel.write_text("keep", encoding="utf-8")
        untouched = self.target / "dxgi.dll"
        before = untouched.read_bytes()

        with self.assertRaises(self.m.Stop) as cm:
            self.m.restore_target(self.game)
        self.assertIn("changed filesystem type externally", str(cm.exception))
        self.assertTrue(sentinel.is_file())
        self.assertEqual(untouched.read_bytes(), before)
        self.assertTrue(self.m.baseline_path(self.target).is_file())

    def test_same_proxy_external_drift_refuses_refresh(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "d" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        (self.target / "dxgi.dll").write_bytes(b"unknown external replacement")
        with self.assertRaises(self.m.Stop):
            self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), b"unknown external replacement")

    def test_managed_optiscaler_proxy_symlink_type_drift_refuses_refresh(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "e" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        managed = self.target / "dxgi.dll"
        original_bytes = managed.read_bytes()
        outside = self.base / "outside-identical-dxgi.dll"
        outside.write_bytes(original_bytes)
        managed.unlink()
        managed.symlink_to(outside)
        with self.assertRaises(self.m.Stop) as cm:
            self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        # Baseline path-containment validation may reject the symlink even
        # earlier than the managed-proxy structural-drift guard. Either way,
        # refresh must fail before replacing/following the link.
        self.assertTrue(
            "filesystem type externally" in str(cm.exception)
            or "Persisted path escapes target" in str(cm.exception)
        )
        self.assertTrue(managed.is_symlink())
        self.assertEqual(outside.read_bytes(), original_bytes)

    def test_shortcuts_binary_patch_and_restore_is_surgical_and_exact(self):
        shortcuts = self.base / "shortcuts.vdf"
        original_launch = 'MANGOHUD=1 gamescope -f %command% -dx12'
        original = make_shortcuts_fixture(self.game, original_launch)
        shortcuts.write_bytes(original)

        expected = 'MANGOHUD=1 WINEDLLOVERRIDES="dxgi=n,b" gamescope -f %command% -dx12'
        result = self.m.patch_shortcuts_launch_options(shortcuts, [(self.game, expected)])
        row = result[self.game.name]
        self.assertEqual(row["status"], "updated")
        self.assertEqual(row["original"], original_launch)

        changed = shortcuts.read_bytes()
        self.assertNotEqual(changed, original)
        parsed = self.m.parse_shortcuts_spans(changed)
        matched = self.m.match_shortcut_span(self.game, parsed)
        self.assertIsNotNone(matched)
        self.assertEqual(self.m._shortcut_string(matched, "LaunchOptions"), expected)
        self.assertEqual(self.m._shortcut_string(matched, "AppName"), self.game.name)
        self.assertIsNotNone(self.m._shortcut_field(matched, "tags"))

        locator = {
            "shortcut_appid": row["shortcut_appid"],
            "shortcut_appname": row["shortcut_appname"],
            "shortcut_exe": row["shortcut_exe"],
        }
        self.m.restore_shortcut_launch_option(shortcuts, locator, original_launch)
        self.assertEqual(shortcuts.read_bytes(), original)

    def test_shortcuts_without_launchoptions_refuses_structural_rewrite(self):
        shortcuts = self.base / "shortcuts.vdf"
        original = make_shortcuts_fixture(self.game, None)
        shortcuts.write_bytes(original)
        result = self.m.patch_shortcuts_launch_options(
            shortcuts, [(self.game, 'WINEDLLOVERRIDES="dxgi=n,b" %command%')]
        )
        self.assertEqual(result[self.game.name]["status"], "unmatched")
        self.assertIn("no existing LaunchOptions", result[self.game.name]["error"])
        self.assertEqual(shortcuts.read_bytes(), original)

    def test_pe_import_parser_and_safe_proxy_selection(self):
        write_minimal_pe(self.exe, ["VERSION.dll", "winmm.dll", "dxgi.dll"])
        self.assertEqual(
            self.m.pe_imported_dlls(self.exe),
            {"version.dll", "winmm.dll", "dxgi.dll"},
        )
        # OptiScaler owns dxgi and an external/game-owned version.dll exists, so
        # RTXMFG must select the next actually imported free proxy.
        (self.target / "version.dll").write_bytes(b"game-owned")
        chosen = self.m.choose_rtxmfg_proxy(self.game, {"dxgi.dll"})
        self.assertEqual(chosen, "winmm.dll")

    def test_y4my_v4_prefers_imported_wininet_over_unproven_dxgi(self):
        write_minimal_pe(self.exe, ["wininet.dll"])
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.7z", "sha256": "a" * 64, "tag": "fixture"}
        record = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertEqual(record["proxy"], "wininet.dll")
        self.assertIn('WINEDLLOVERRIDES="wininet=n,b"', record["launch_options"])
        self.assertEqual(record["compatibility_policy"]["proxy_imports"], ["wininet.dll"])

    def test_y4my_v4_refresh_moves_dxgi_to_positive_import_proxy_safely(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.7z", "sha256": "d" * 64, "tag": "fixture"}
        first = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertEqual(first["proxy"], "dxgi.dll")
        write_minimal_pe(self.exe, ["wininet.dll"])
        refreshed = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertEqual(refreshed["proxy"], "wininet.dll")
        self.assertFalse((self.target / "dxgi.dll").exists())
        self.assertEqual((self.target / "wininet.dll").read_bytes(), self._sm86_payload()["dxgi.dll"])

    def test_188_migration_preserves_prior_proxy_when_legacy_runtime_log_proves_mfg_applied(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.7z", "sha256": "e" * 64, "tag": "fixture"}
        first = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertEqual(first["proxy"], "dxgi.dll")
        (self.target / "OptiScaler.log").write_text(
            "RTXForge.NativeMfgMenu.v3e: applied native interpolation request generation=1\n",
            encoding="utf-8",
        )
        write_minimal_pe(self.exe, ["wininet.dll", "dxgi.dll"])
        refreshed = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertEqual(refreshed["proxy"], "dxgi.dll")
        self.assertTrue(refreshed["compatibility_policy"]["preserved_proven_proxy"])

    def test_y4my_v4_reshade_coexistence_prefers_imported_wininet_and_keeps_dxgi_override(self):
        write_minimal_pe(self.exe, ["wininet.dll"])
        self.game.dlss = True
        self.game.dlssg = True
        (self.target / "dxgi.dll").write_bytes(b"ReShade injected proxy fixture")
        (self.target / "ReShade.ini").write_text("[GENERAL]\n", encoding="utf-8")
        archive_meta = {"name": "fixture.7z", "sha256": "b" * 64, "tag": "fixture"}
        record = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertEqual(record["proxy"], "wininet.dll")
        self.assertIn('WINEDLLOVERRIDES="dxgi=n,b;wininet=n,b"', record["launch_options"])
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), b"ReShade injected proxy fixture")

    def test_ada_unified_loader_falls_back_without_overwriting_occupied_import_proxy(self):
        write_minimal_pe(self.exe, ["winmm.dll"])
        self.game.dlss = True
        self.game.dlssg = True
        occupied = self.target / "winmm.dll"
        occupied.write_bytes(b"game-owned-winmm")
        archive_meta = {"name": "fixture.7z", "sha256": "e" * 64, "tag": "fixture"}
        record = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertEqual(record["proxy"], "dxgi.dll")
        self.assertEqual(occupied.read_bytes(), b"game-owned-winmm")
        self.assertEqual(record["mfg_provider"]["name"], self.m.Y4MY_PROVIDER["name"])
        self.assertNotIn("proxy", record["mfg_provider"])

    def test_187_to_188_migration_refuses_legacy_mfg_proxy_type_drift_before_mutation(self):
        write_minimal_pe(self.exe, ["dinput8.dll"])
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.7z", "sha256": "0" * 64, "tag": "fixture"}
        first = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertEqual(first["proxy"], "dxgi.dll")
        self._seed_legacy_mfg_state("winmm.dll")
        unrelated = self.target / "nvngx_dlssnr.dll"
        unrelated_before = unrelated.read_bytes()
        managed_mfg = self.target / "winmm.dll"
        managed_mfg.unlink()
        managed_mfg.mkdir()
        sentinel = managed_mfg / "external.txt"
        sentinel.write_bytes(b"do-not-touch")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertIn("Managed RTXMFG proxy changed filesystem type externally", str(cm.exception))
        self.assertEqual(sentinel.read_bytes(), b"do-not-touch")
        self.assertEqual(unrelated.read_bytes(), unrelated_before)
        baseline = self.m.load_baseline(self.target)
        self.assertEqual(baseline["status"], "active")
        self.assertEqual(baseline["current"]["mfg_provider"]["proxy"], "winmm.dll")

    def test_187_to_188_migration_preserves_externally_replaced_legacy_mfg_proxy(self):
        write_minimal_pe(self.exe, ["dinput8.dll"])
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.7z", "sha256": "1" * 64, "tag": "fixture"}
        first = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self._seed_legacy_mfg_state("winmm.dll")
        external = b"external replacement that must survive"
        (self.target / "winmm.dll").write_bytes(external)
        refreshed = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertEqual(refreshed["proxy"], first["proxy"])
        self.assertEqual(refreshed["mfg_provider"]["name"], self.m.Y4MY_PROVIDER["name"])
        self.assertEqual((self.target / "winmm.dll").read_bytes(), external)
        baseline = self.m.load_baseline(self.target)
        self.assertNotIn("winmm.dll", baseline["managed_paths"])
        self.m.restore_target(self.game)
        self.assertEqual((self.target / "winmm.dll").read_bytes(), external)



    def test_permission_locked_tree_uses_baseline_fallback_before_live_repair(self):
        self.game.dlss = True
        self.game.dlssg = True
        opti = self.target / "OptiScaler"
        opti.mkdir()
        (opti / "legacy.bin").write_bytes(b"legacy")
        archive_meta = {"name": "fixture.zip", "sha256": "3" * 64, "known_tag": "fixture"}

        real_copytree = self.m.shutil.copytree
        def deny_old_tree(src, dst, *args, **kwargs):
            if Path(src) == opti:
                raise PermissionError("fixture EACCES")
            return real_copytree(src, dst, *args, **kwargs)
        self.m.shutil.copytree = deny_old_tree

        def fake_tar_backup(src, backup_root, name):
            archive = backup_root / "trees" / f"{name}.tar"
            archive.parent.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive, "w") as tf:
                tf.add(src, arcname=name)
            return {
                "kind": "tar_tree", "existed": True, "backup": str(archive),
                "bytes": archive.stat().st_size, "archive_sha256": self.m.sha256_file(archive),
                "preserves_numeric_owner": True,
            }
        self.m._backup_tree_tar = fake_tar_backup

        repair_seen = []
        def fake_repair(path, label):
            baseline = self.m.load_baseline(self.target)
            self.assertIsNotNone(baseline, "live repair happened before baseline.json existed")
            self.assertEqual(baseline["originals"]["OptiScaler/"]["kind"], "tar_tree")
            repair_seen.append(str(path))
            return True
        self.m.ensure_tree_replaceable = fake_repair

        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertEqual(repair_seen, [str(opti)])
        baseline = self.m.load_baseline(self.target)
        self.assertEqual(baseline["originals"]["OptiScaler/"]["kind"], "tar_tree")

    def test_permission_locked_root_file_is_archived_before_exact_file_repair(self):
        self.game.dlss = True
        self.game.dlssg = True
        legacy = self.target / "OptiScaler.ini"
        legacy.write_bytes(b"legacy ini")
        archive_meta = {"name": "fixture.zip", "sha256": "4" * 64, "known_tag": "fixture"}

        real_copy_verified = self.m.copy_verified
        def deny_legacy(src, dst):
            if Path(src) == legacy:
                raise PermissionError("fixture EACCES")
            return real_copy_verified(src, dst)
        self.m.copy_verified = deny_legacy

        def fake_file_tar(src, backup_root, rel):
            archive = backup_root / "file-tars" / (rel + ".tar")
            archive.parent.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive, "w") as tf:
                tf.add(src, arcname=Path(rel).name)
            return {
                "kind": "tar_file", "existed": True, "backup": str(archive),
                "member": Path(rel).name, "restore_parent": ".",
                "bytes": archive.stat().st_size, "archive_sha256": self.m.sha256_file(archive),
                "preserves_numeric_owner": True,
            }
        self.m._backup_file_tar = fake_file_tar

        repair_seen = []
        real_file_repair = self.m.ensure_file_replaceable
        def fake_file_repair(path, label):
            if Path(path) == legacy:
                baseline = self.m.load_baseline(self.target)
                self.assertIsNotNone(baseline, "file repair happened before baseline.json existed")
                self.assertEqual(baseline["originals"]["OptiScaler.ini"]["kind"], "tar_file")
                repair_seen.append(str(path))
                return True
            return real_file_repair(path, label)
        self.m.ensure_file_replaceable = fake_file_repair

        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertEqual(repair_seen, [str(legacy)])
        baseline = self.m.load_baseline(self.target)
        self.assertEqual(baseline["originals"]["OptiScaler.ini"]["kind"], "tar_file")



    def test_batch_report_history_is_capped_per_action(self):
        import time
        self.m.STATE_ROOT = self.base / "state-report-cap"
        self.m.STATE_ROOT.mkdir(parents=True)
        paths = []
        for i in range(8):
            path = self.m.STATE_ROOT / f"audit-20000101-00000{i}.md"
            path.write_text(str(i), encoding="utf-8")
            paths.append(path)
            time.sleep(0.002)
        # Force a uniquely newer report name while avoiding dependence on wall-clock seconds.
        real_stamp = self.m.now_stamp
        self.m.now_stamp = lambda: "20990101-999999"
        try:
            newest = self.m.write_batch_report("audit", [], self.base)
        finally:
            self.m.now_stamp = real_stamp
        kept = sorted(self.m.STATE_ROOT.glob("audit-*.md"))
        self.assertEqual(len(kept), 5)
        self.assertIn(newest, kept)

    def test_install_history_is_capped_to_ten_compact_rows(self):
        b = self._baseline(history=[{"installed_utc": f"old-{i}"} for i in range(15)])
        self.game.dlss = True
        self.game.dlssg = True
        # Active refresh requires valid current metadata; use a fresh baseline
        # created by a real install, then inject oversized history before refresh.
        self.m.baseline_path(self.target).unlink()
        archive_meta = {"name": "fixture.zip", "sha256": "5" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        active = self.m.load_baseline(self.target)
        active["history"] = [{"installed_utc": f"old-{i}"} for i in range(15)]
        self.m.save_json_atomic(self.m.baseline_path(self.target), active)
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        reloaded = self.m.load_baseline(self.target)
        self.assertEqual(len(reloaded["history"]), 10)
        self.assertEqual(reloaded["history"][-1]["archive_sha256"], "5" * 64)



    def _write_dlss_provider_zip(self, path: Path, extra_entries=None) -> str:
        entries = {
            "OptiScaler.dll": b"MZ" + (b"O" * (70 * 1024)),
            "OptiScaler.ini": b"[Menu]\nOverlayMenu=true\n",
            "nvngx.dll_dlssnr.dll": b"MZnr-forwarder",
            "OptiScaler/nvngx_dlss.dll": b"MZdlss",
            "OptiScaler/nvngx_dlssd.dll": b"MZdlssd",
            "OptiScaler/nvngx_dlssg.dll": b"MZdlssg",
            "OptiScaler/streamline/sl.interposer.dll": b"MZsl",
            "OptiScaler/streamline/sl.common.dll": b"MZcommon",
            "OptiScaler/streamline/sl.dlss_g.dll": b"MZslg",
            "Licenses/LICENSE.txt": b"fixture",
        }
        if extra_entries:
            entries.update(extra_entries)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in entries.items():
                zf.writestr(name, data)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _write_rtxmfg_zip(self, path: Path, *, duplicate=False, traversal=False, symlink=False) -> str:
        payload = b"MZ" + b"R" * (70 * 1024)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
            if traversal:
                zf.writestr("../RTXMFG.dll", payload)
            elif symlink:
                info = zipfile.ZipInfo("RTXMFG.dll")
                info.create_system = 3
                info.external_attr = (0o120777 << 16)
                zf.writestr(info, b"target")
            else:
                zf.writestr("RTXMFG.dll", payload)
                if duplicate:
                    zf.writestr("nested/RTXMFG.dll", payload)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_ada_y4my_v4_policy_arms_nr_and_native_mfg_but_executes_neither_at_boot(self):
        out = self.m.patch_optiscaler_ini(
            b"[Menu]\nOverlayMenu=false\n[DLSSG]\nAdaMfgUnlock=false\nAmpereMfgUnlock=true\n",
            "ada",
        ).decode("utf-8")
        for line in (
            "OverlayMenu=auto", "ShortcutKey=0x2D", "UseHQFont=false", "DisableSplash=true",
            "CheckForUpdate=false", "Dx12Upscaler=auto", "DualFeature=true",
            "DualEnlarger=dlss", "PreUpscale=false", "Passes=1", "WorkingScale=1.0",
            "FGInput=nofg", "FGOutput=nofg", "FGNvngxReplacement=None",
            "AdaMfgUnlock=false", "AdaBlackwellKernels=auto", "DisableFlipMetering=auto",
            "DisableReflexSync=auto",
        ):
            self.assertIn(line, out)
        self.assertNotIn("AmpereMfgUnlock=", out)
        self.assertNotIn("RunBeforeSR=", out)
        self.assertNotIn("External=", out)
        self.assertRegex(out, r"(?s)\[DlssNr\].*?Enabled=false")
        self.assertRegex(out, r"(?s)\[FrameGen\].*?Enabled=false")

    def test_rc124_regression_nr_runtime_present_does_not_auto_execute_on_launch(self):
        """RC1.24 supplied the missing runtime but also forced NR on at startup.

        That converted a batch-wide missing-runtime install failure into a
        batch-wide launch-crash risk.  A successful install must keep the model
        DLL present while leaving NR dormant until the user enables it in-game.
        """
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.7z", "sha256": "4" * 64, "tag": "fixture"}
        record = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertTrue((self.target / self.m.NR_RUNTIME_NAME).is_file())
        ini = (self.target / "OptiScaler.ini").read_text(encoding="utf-8")
        self.assertRegex(ini, r"(?s)\[DlssNr\].*?Enabled=false")
        self.assertFalse(record["nr_profile"]["enabled"])
        self.assertEqual(record["nr_profile"]["activation"], "manual-after-launch")
        self.assertRegex(ini, r"(?s)\[FrameGen\].*?Enabled=false")
        self.assertRegex(ini, r"(?s)\[DLSSG\].*?AdaMfgUnlock=false")
        self.assertEqual(record["mfg_provider"]["enabled"], False)
        self.assertEqual(record["mfg_provider"]["activation"], "manual-after-launch")

    def test_rc125_regression_native_ada_mfg_is_dormant_on_first_launch(self):
        """RC1.25 disabled NR but still forced native FG + the experimental Ada unlock on every boot."""
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.7z", "sha256": "5" * 64, "tag": "fixture"}
        record = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        ini = (self.target / "OptiScaler.ini").read_text(encoding="utf-8")
        self.assertRegex(ini, r"(?s)\[FrameGen\].*?Enabled=false")
        self.assertRegex(ini, r"(?s)\[DLSSG\].*?AdaMfgUnlock=false")
        self.assertRegex(ini, r"(?s)\[DLSSG\].*?AdaBlackwellKernels=auto")
        self.assertRegex(ini, r"(?s)\[NvApi\].*?DisableFlipMetering=auto")
        self.assertRegex(ini, r"(?s)\[NvApi\].*?DisableReflexSync=auto")
        self.assertEqual(record["mfg_provider"]["enabled"], False)
        self.assertEqual(record["mfg_provider"]["activation"], "manual-after-launch")
        self.assertEqual(record["compatibility_policy"]["upscaler_route"], "auto-first-launch")
        self.assertEqual(record["compatibility_policy"]["mfg_route"], "native-ada-y4my-v4-armed")

    def test_handoff188_retires_v3e_loader_and_uses_y4my_as_single_provider(self):
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_integrated_ada_runtime()
        self.assertIn("retired by Handoff 188", str(cm.exception))
        self.game.dlss = True
        self.game.dlssg = True
        write_minimal_pe(self.exe, ["winmm.dll"])
        archive_meta = {"name": "fixture.7z", "sha256": "7" * 64, "tag": "fixture"}
        record = self.m.install_target(
            self.game, self._sm86_payload(), archive_meta, "ada",
            rtxmfg_payload=b"MZ-legacy-ignored",
            rtxmfg_meta={"version": "legacy", "sha256": "8" * 64, "dll_sha256": "9" * 64},
        )
        self.assertEqual(record["mfg_provider"]["name"], self.m.Y4MY_PROVIDER["name"])
        self.assertEqual(record["mfg_provider"]["commit"], self.m.Y4MY_PROVIDER["commit"])
        self.assertFalse(record["nr_profile"]["enabled"])
        self.assertEqual(record["compatibility_policy"]["mfg_route"], "native-ada-y4my-v4-armed")
        self.assertFalse((self.target / "winmm.dll").exists() and record["proxy"] != "winmm.dll")
        ini = (self.target / "OptiScaler.ini").read_text(encoding="utf-8")
        self.assertIn("AdaMfgUnlock=false", ini)
        self.assertIn("AdaBlackwellKernels=auto", ini)
        self.assertRegex(ini, r"(?s)\[FrameGen\].*?Enabled=false")
        self.assertRegex(ini, r"(?s)\[DlssNr\].*?Enabled=false")

    def test_y4my_v4_policy_keeps_upscaler_auto_and_disables_dxgi_vulkan_spoofing(self):
        raw = (
            b"[Upscalers]\nDx12Upscaler=xess\n"
            b"[Spoofing]\nDxgi=auto\nStreamlineSpoofing=auto\nVulkan=auto\n"
            b"[Hotfix]\nDisableOverlays=false\n"
        )
        out = self.m.patch_optiscaler_ini(raw, "ada").decode("utf-8")
        self.assertRegex(out, r"(?s)\[Upscalers\].*?Dx12Upscaler=auto")
        self.assertRegex(out, r"(?s)\[Spoofing\].*?Dxgi=false")
        self.assertRegex(out, r"(?s)\[Spoofing\].*?Vulkan=false")
        self.assertRegex(out, r"(?s)\[Hotfix\].*?DisableOverlays=false")

    def test_y4my_v4_does_not_auto_enable_global_overlay_blocker_for_eos(self):
        eos = self.game.root / "Engine" / "Binaries" / "ThirdParty" / "EOS"
        eos.mkdir(parents=True)
        (eos / "EOSOVH-Win64-Shipping.dll").write_bytes(b"fixture")
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.7z", "sha256": "c" * 64, "tag": "fixture"}
        record = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "ada")
        self.assertFalse(record["compatibility_policy"]["eos_overlay_detected"])
        self.assertFalse(record["compatibility_policy"]["overlay_blocker_enabled"])
        ini = (self.target / "OptiScaler.ini").read_text(encoding="utf-8")
        self.assertNotIn("DisableOverlays=true", ini)

    def test_rc2_runtime_evidence_uses_execution_marker_not_overlay_presence(self):
        (self.target / "OptiScaler.log").write_text(
            "loader started\n"
            "RTXForge.NativeMfgMenu.v3e: applied native interpolation request "
            "generation=7 sourceViewport=0 outputViewport=0 nativeFrames=3 outputFrames=3\n",
            encoding="utf-8",
        )
        evidence = self.m.inspect_optiscaler_runtime_log(self.target)
        self.assertEqual(evidence["status"], "mfg-applied")
        self.assertTrue(evidence["mfg_applied"])
        self.assertTrue(evidence["native_bridge_seen"])

    def test_sm86_policy_is_nr_only_without_experimental_mfg_unlock(self):
        out = self.m.patch_optiscaler_ini(b"[DLSSG]\nAmpereMfgUnlock=true\n", "sm86").decode("utf-8")
        self.assertNotIn("AmpereMfgUnlock=", out)
        self.assertIn("AdaMfgUnlock=false", out)
        self.assertRegex(out, r"(?s)\[FrameGen\].*?Enabled=false")
        self.assertRegex(out, r"(?s)\[DlssNr\].*?Enabled=false")
        self.assertIn("DualFeature=true", out)
        self.assertIn("WorkingScale=1.0", out)

    def test_y4my_provider_structure_validation_and_case_collision_refusal(self):
        good = self.base / "renamed-provider.zip"
        digest = self._write_dlss_provider_zip(good)
        self.m.Y4MY_PROVIDER["sha256"] = digest
        meta = self.m.validate_archive(good)
        self.assertEqual(meta["sha256"], digest)
        self.assertEqual(meta["provider"], self.m.Y4MY_PROVIDER["name"])
        payload, _ = self.m.load_archive_payload(good)
        self.assertIn("OptiScaler/streamline/sl.interposer.dll", payload)
        self.assertIn("dxgi.dll", payload)
        collision = self.base / "collision.zip"
        digest2 = self._write_dlss_provider_zip(collision, {"OPTISCALER/nvngx_dlss.dll": b"duplicate-case"})
        self.m.Y4MY_PROVIDER["sha256"] = digest2
        with self.assertRaises(self.m.Stop):
            self.m.load_archive_payload(collision)

    def test_rtxmfg_zip_validation_rejects_duplicate_traversal_and_symlink(self):
        for label, kwargs in (
            ("duplicate", {"duplicate": True}),
            ("traversal", {"traversal": True}),
            ("symlink", {"symlink": True}),
        ):
            path = self.base / f"{label}.zip"
            digest = self._write_rtxmfg_zip(path, **kwargs)
            with self.subTest(label=label):
                with self.assertRaises(self.m.Stop):
                    self.m._safe_zip_payload_single_file(path, "RTXMFG.dll", digest)

    def test_rtxmfg_download_cache_validates_hash_and_cleans_part_on_failure(self):
        source = self.base / "source.zip"
        digest = self._write_rtxmfg_zip(source)
        blob = source.read_bytes()
        self.m.DEFAULT_DOWNLOAD_DIR = self.base / "Downloads" / "Compressed"
        self.m.RTXMFG_CACHE_DIR = self.base / "cache"
        self.m.RTXMFG_PROVIDER = {
            "version": "fixture", "archive": "RTXMFG-fixture.zip",
            "sha256": digest, "url": "https://example.invalid/RTXMFG-fixture.zip",
        }
        self.m.urllib.request.urlopen = lambda *a, **k: io.BytesIO(blob)
        cached = self.m.ensure_rtxmfg_archive(allow_download=True)
        self.assertTrue(cached.is_file())
        self.assertEqual(self.m.sha256_file(cached), digest)
        self.assertFalse(list(self.m.RTXMFG_CACHE_DIR.glob("*.part-*")))
        self.assertFalse(list(self.m.RTXMFG_CACHE_DIR.glob(".*.part-*")))

        cached.unlink()
        self.m.RTXMFG_PROVIDER["sha256"] = "0" * 64
        with self.assertRaises(self.m.Stop):
            self.m.ensure_rtxmfg_archive(allow_download=True)
        self.assertFalse(list(self.m.RTXMFG_CACHE_DIR.glob("*.part-*")))
        self.assertFalse(list(self.m.RTXMFG_CACHE_DIR.glob(".*.part-*")))

    def test_newly_quarantined_orphan_is_never_pruned_by_older_mtime_history(self):
        state = self.m.state_dir_for(self.target)
        backup = state / "baseline-backup"
        backup.mkdir(parents=True)
        (backup / "fresh-recovery.bin").write_bytes(b"fresh")
        # Make the current orphan source look ancient by mtime.
        os.utime(backup, ns=(1, 1))
        old = state / "baseline-backup-orphan-old"
        old.mkdir()
        (old / "old.bin").write_bytes(b"old")
        os.utime(old, ns=(9_999_999_999, 9_999_999_999))

        archived = self.m.quarantine_orphan_baseline_backup(self.target)
        self.assertIsNotNone(archived)
        self.assertTrue((archived / "fresh-recovery.bin").is_file())
        self.assertFalse(old.exists())

    def test_stale_orphan_baseline_is_quarantined_and_retention_is_capped(self):
        state = self.m.state_dir_for(self.target)
        backup = state / "baseline-backup"
        backup.mkdir(parents=True)
        (backup / "old.bin").write_bytes(b"old")
        archived = self.m.quarantine_orphan_baseline_backup(self.target)
        self.assertIsNotNone(archived)
        self.assertFalse(backup.exists())
        self.assertTrue(archived.is_dir())
        # A second orphan generation should prune the older one to keep only one.
        backup.mkdir(parents=True)
        (backup / "new.bin").write_bytes(b"new")
        archived2 = self.m.quarantine_orphan_baseline_backup(self.target)
        orphans = list(state.glob("baseline-backup-orphan-*"))
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0], archived2)


    def test_launchoptions_ownership_ignores_managed_lookalikes_after_command(self):
        original = 'MANGOHUD=1 %command% --foo'
        required = (
            'WINEDLLOVERRIDES="dxgi=n,b" '
            'PROTON_ENABLE_NVAPI=1 PROTON_NVIDIA_NVCUDA=1 %command%'
        )
        applied = self.m.merge_rtxengine_launch_options(original, required)
        self.assertIn('WINEDLLOVERRIDES="dxgi=n,b"', applied)
        current = applied + ' PROTON_ENABLE_NVAPI=0 WINEDLLOVERRIDES=literal-game-arg'

        restored = self.m.reconcile_rtxengine_launch_options(current, original, applied)
        self.assertEqual(
            restored,
            'MANGOHUD=1 %command% --foo PROTON_ENABLE_NVAPI=0 WINEDLLOVERRIDES=literal-game-arg',
        )

    def test_launchoptions_merge_does_not_import_post_command_wine_override_argument(self):
        existing = '%command% WINEDLLOVERRIDES=literal-game-arg --dx12'
        required = (
            'WINEDLLOVERRIDES="version=n,b" '
            'PROTON_ENABLE_NVAPI=1 PROTON_NVIDIA_NVCUDA=1 %command%'
        )
        merged = self.m.merge_rtxengine_launch_options(existing, required)
        self.assertTrue(merged.startswith('WINEDLLOVERRIDES="version=n,b" '))
        self.assertIn('%command% WINEDLLOVERRIDES=literal-game-arg --dx12', merged)

    def test_launch_option_merge_preserves_mangohud_gamescope_args_and_existing_overrides(self):
        existing = 'MANGOHUD=1 WINEDLLOVERRIDES="dinput8=n,b" gamescope -f %command% -dx12'
        required = 'WINEDLLOVERRIDES="dxgi=n,b;version=n,b" %command%'
        merged = self.m.merge_rtxengine_launch_options(existing, required)
        self.assertIn("MANGOHUD=1", merged)
        self.assertIn("gamescope -f %command% -dx12", merged)
        self.assertIn("dinput8=n,b", merged)
        self.assertIn("dxgi=n,b", merged)
        self.assertIn("version=n,b", merged)
        self.assertEqual(merged.count("%command%"), 1)
        self.assertNotIn("PROTON_ENABLE_NVAPI", merged)
        self.assertNotIn("PROTON_NVIDIA_NVCUDA", merged)

    def test_launchoptions_build_contract_is_proxy_only(self):
        launch = self.m.build_launch_options("dxgi.dll", {"detected": False})
        self.assertEqual(launch, 'WINEDLLOVERRIDES="dxgi=n,b" %command%')
        self.assertNotIn("PROTON_ENABLE_NVAPI", launch)
        self.assertNotIn("PROTON_NVIDIA_NVCUDA", launch)

    def test_uninstall_preserves_legacy_native_nvidia_capability_flags(self):
        original = '%command%'
        applied = (
            'WINEDLLOVERRIDES="dxgi=n,b" PROTON_ENABLE_NVAPI=1 '
            'PROTON_NVIDIA_NVCUDA=1 %command%'
        )
        restored = self.m.reconcile_rtxengine_launch_options(applied, original, applied)
        self.assertEqual(restored, 'PROTON_ENABLE_NVAPI=1 PROTON_NVIDIA_NVCUDA=1 %command%')
        self.assertNotIn('WINEDLLOVERRIDES', restored)

    def test_refresh_preserves_preexisting_native_nvapi_capability_flag(self):
        existing = 'PROTON_ENABLE_NVAPI=1 MANGOHUD=1 %command% -dx12'
        required = 'WINEDLLOVERRIDES="wininet=n,b" %command%'
        merged = self.m.merge_rtxengine_launch_options(existing, required)
        self.assertIn('PROTON_ENABLE_NVAPI=1', merged)
        self.assertIn('WINEDLLOVERRIDES="wininet=n,b"', merged)
        self.assertIn('MANGOHUD=1 %command% -dx12', merged)

    def test_launchoptions_refresh_preserves_native_nvcuda_capability_flag(self):
        existing = (
            'PROTON_NVIDIA_NVCUDA=1 WINEDLLOVERRIDES="dwmapi=n,b" '
            'MANGOHUD=1 gamescope -f %command% -dx12'
        )
        required = 'WINEDLLOVERRIDES="wininet=n,b" PROTON_ENABLE_NVAPI=1 %command%'
        merged = self.m.merge_rtxengine_launch_options(existing, required)
        self.assertIn("PROTON_NVIDIA_NVCUDA=1", merged)
        self.assertIn('WINEDLLOVERRIDES="dwmapi=n,b;wininet=n,b"', merged)
        self.assertIn("MANGOHUD=1 gamescope -f %command% -dx12", merged)

    def test_launchoptions_preserves_halo_dwmapi_override(self):
        existing = 'WINEDLLOVERRIDES="dwmapi=n,b" %command%'
        required = 'WINEDLLOVERRIDES="dxgi=n,b" PROTON_ENABLE_NVAPI=1 %command%'
        merged = self.m.merge_rtxengine_launch_options(existing, required)
        self.assertIn('WINEDLLOVERRIDES="dwmapi=n,b;dxgi=n,b"', merged)
        self.assertEqual(merged.count("%command%"), 1)

    def test_launchoptions_refuses_managed_assignment_after_wrapper_command(self):
        existing = 'gamescope -f WINEDLLOVERRIDES="dwmapi=n,b" %command%'
        required = 'WINEDLLOVERRIDES="dxgi=n,b" PROTON_ENABLE_NVAPI=1 %command%'
        with self.assertRaises(self.m.Stop) as cm:
            self.m.merge_rtxengine_launch_options(existing, required)
        self.assertIn("refusing unsafe automatic rewrite", str(cm.exception))

    def test_launchoptions_preserves_env_wrapper_native_nvapi_assignment(self):
        existing = 'env PROTON_ENABLE_NVAPI=0 %command% --foo'
        required = 'WINEDLLOVERRIDES="dxgi=n,b" PROTON_ENABLE_NVAPI=1 %command%'
        merged = self.m.merge_rtxengine_launch_options(existing, required)
        self.assertTrue(merged.startswith('WINEDLLOVERRIDES="dxgi=n,b" '))
        self.assertIn(existing, merged)
        self.assertEqual(merged.count('PROTON_ENABLE_NVAPI='), 1)

    def test_batch_reports_same_timestamp_are_unique_and_atomic(self):
        with patch.object(self.m, "now_stamp", return_value="20260911-190000"):
            first = self.m.write_batch_report("audit", [], self.drive)
            second = self.m.write_batch_report("audit", [], self.drive)
        self.assertNotEqual(first, second)
        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())
        self.assertEqual(first.name, "audit-20260911-190000.md")
        self.assertEqual(second.name, "audit-20260911-190000-1.md")
        self.assertTrue(first.read_text(encoding="utf-8").endswith("\n"))
        self.assertTrue(second.read_text(encoding="utf-8").endswith("\n"))

    def test_audit_refuses_destructive_pending_recovery_state(self):
        current = {
            "installed_hashes": {},
            "proxy": "dxgi.dll",
            "mfg_provider": None,
            "nr_profile": {},
            "launch_options": "%command%",
        }
        baseline = self._baseline(current=current)
        baseline["status"] = "destructive-pending"
        baseline["destructive_pending"] = {"mode": "deep-clean", "previous_status": "active"}
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)
        with self.assertRaises(self.m.Stop) as cm:
            self.m.audit_target(self.game)
        self.assertIn("not active", str(cm.exception))

    def test_audit_detects_changed_and_missing_and_report_preserves_provenance(self):
        good = self.target / "dxgi.dll"
        changed = self.target / "OptiScaler.ini"
        good.write_bytes(b"good")
        changed.write_bytes(b"before")
        b = self._baseline(current={
            "installed_hashes": {
                "dxgi.dll": self.m.sha256_bytes(b"good"),
                "OptiScaler.ini": self.m.sha256_bytes(b"before"),
                "OptiScaler/missing.dll": self.m.sha256_bytes(b"missing"),
            },
            "proxy": "dxgi.dll",
            "mfg_provider": {
                "name": "Universal RTXMFG", "version": "fixture", "ownership": "external",
                "dll_sha256": "a" * 64, "menu_key": "Backspace",
            },
            "nr_profile": {"enabled": True, "run_before_sr": True, "passes": 1, "working_scale": 1.0, "menu_key": "Insert"},
            "launch_options": 'WINEDLLOVERRIDES="dxgi=n,b" %command%',
        })
        changed.write_bytes(b"after")
        row = self.m.audit_target(self.game)
        self.assertEqual(row["missing"], ["OptiScaler/missing.dll"])
        self.assertEqual(row["changed"], ["OptiScaler.ini"])
        row["status"] = "drift"
        report = self.m.write_batch_report(
            "audit", [row], self.drive,
            {"name": "provider.zip", "sha256": "b" * 64},
        )
        text = report.read_text(encoding="utf-8")
        self.assertIn("Status: `drift`", text)
        self.assertIn("MFG provider: `Universal RTXMFG fixture` (`external` owner)", text)
        self.assertIn("MFG DLL SHA256", text)
        self.assertIn("NR profile", text)
        self.assertIn("OptiScaler/NR menu key: `Insert`", text)
        self.assertIn("Missing: 1", text)
        self.assertIn("Changed: 1", text)
        self.assertIn("Archive SHA256", text)

    def test_y4my_provider_pin_constants_are_exact(self):
        self.assertEqual(self.m.Y4MY_PROVIDER["tag"], "v10.0.0-dev-fork-y4my4my4m-v4")
        self.assertEqual(self.m.Y4MY_PROVIDER["commit"], "7b7220bbb4994a9c8ae60cfc75a44cb67995efb8")
        self.assertEqual(self.m.Y4MY_PROVIDER["archive"], "OptiScaler_v10.0.0-dev-fork-y4my4my4m-v4_20260905_with_DLSS.7z")
        self.assertEqual(self.m.Y4MY_PROVIDER["sha256"], "9d7824cc9cfb15265bc6438b4638aad74ff9cd6d1d3488ab73724affb386a8b0")
        self.assertEqual(self.m.Y4MY_PROVIDER["release_size"], 117366545)

    def test_streaming_binary_marker_scan_handles_chunk_boundaries_and_case(self):
        path = self.base / "proxy.dll"
        path.write_bytes(b"A" * 15 + b"OpTiScAlEr" + b"Z" * 20)
        self.assertTrue(
            self.m.file_contains_any(
                path, (b"reshade", b"optiscaler"), max_bytes=1024, chunk_size=8
            )
        )
        self.assertFalse(
            self.m.file_contains_any(
                path, (b"not-present", b"rtxmfg"), max_bytes=1024, chunk_size=8
            )
        )

    def test_streaming_binary_marker_scan_respects_size_cap_and_symlink_boundary(self):
        path = self.base / "large.dll"
        path.write_bytes(b"optiscaler" + b"x" * 64)
        self.assertFalse(self.m.file_contains_any(path, (b"optiscaler",), max_bytes=4, chunk_size=2))
        link = self.base / "link.dll"
        link.symlink_to(path)
        self.assertFalse(self.m.file_contains_any(link, (b"optiscaler",), max_bytes=1024, chunk_size=8))


    def test_nr_runtime_autodiscovery_skips_bad_candidate_and_uses_later_valid_copy(self):
        compressed = self.base / "Downloads" / "Compressed"
        downloads = self.base / "Downloads"
        compressed.mkdir(parents=True)
        self.m.DEFAULT_DOWNLOAD_DIR = compressed
        self.m.HOME = self.base
        bad = compressed / self.m.NR_RUNTIME_NAME
        good = downloads / self.m.NR_RUNTIME_NAME
        bad.write_bytes(b"not-a-valid-runtime")
        good_bytes = b"MZ" + (b"R" * 128)
        good.write_bytes(good_bytes)

        data, meta = self.m.load_user_nr_runtime()
        self.assertEqual(data, good_bytes)
        self.assertEqual(meta["path"], str(good.resolve()))
        self.assertTrue(any(str(bad) in row for row in meta["skipped_auto_candidates"]))

    def test_nr_runtime_autodiscovery_bad_only_defers_to_per_game_resolution(self):
        compressed = self.base / "Downloads" / "Compressed"
        compressed.mkdir(parents=True)
        self.m.DEFAULT_DOWNLOAD_DIR = compressed
        self.m.HOME = self.base
        (compressed / self.m.NR_RUNTIME_NAME).write_bytes(b"bad")
        data, meta = self.m.load_user_nr_runtime()
        self.assertIsNone(data)
        self.assertIsNone(meta)

    def test_explicit_nr_runtime_remains_strict_even_if_autodiscovery_has_good_copy(self):
        downloads = self.base / "Downloads"
        downloads.mkdir(parents=True)
        self.m.HOME = self.base
        good = downloads / self.m.NR_RUNTIME_NAME
        good.write_bytes(b"MZ" + (b"R" * 128))
        bad = self.base / "explicit-bad.dll"
        bad.write_bytes(b"bad")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.load_user_nr_runtime(str(bad))
        self.assertIn("unexpectedly small", str(cm.exception))

    def _install_pinned_nr_fixture(self, family="ada"):
        self.m.HOME = self.base
        self.m.DEFAULT_DOWNLOAD_DIR = self.base / "Downloads" / "Compressed"
        runtime = b"MZ" + (b"N" * (70 * 1024))
        cache = self.m._nr_runtime_cache_dir(family)
        cache.mkdir(parents=True)
        archive = cache / f"fixture-{family}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr(self.m.NR_RUNTIME_NAME, runtime)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        providers = dict(self.m.NR_RUNTIME_PROVIDERS)
        providers[family] = {
            "name": f"fixture NR {family}",
            "tag": f"fixture-{family}",
            "archive": archive.name,
            "sha256": digest,
            "url": "https://invalid.example/fixture.zip",
            "release_size": archive.stat().st_size,
        }
        self.m.NR_RUNTIME_PROVIDERS = providers
        return runtime, archive

    def test_nr_runtime_family_fallback_bootstraps_exact_pinned_archive(self):
        runtime, archive = self._install_pinned_nr_fixture("ada")
        data, meta = self.m.load_user_nr_runtime(family="ada")
        self.assertEqual(data, runtime)
        self.assertEqual(meta["path"], str(archive.resolve()))
        self.assertEqual(meta["provider_archive_sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        self.assertEqual(meta["gpu_family"], "ada")
        self.assertIn("not bundled", meta["ownership"])

    def test_nr_runtime_bad_local_copy_falls_through_to_pinned_family_provider(self):
        runtime, archive = self._install_pinned_nr_fixture("ada")
        bad = self.m.DEFAULT_DOWNLOAD_DIR / self.m.NR_RUNTIME_NAME
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_bytes(b"bad")
        data, meta = self.m.load_user_nr_runtime(family="ada")
        self.assertEqual(data, runtime)
        self.assertEqual(meta["path"], str(archive.resolve()))
        self.assertTrue(any(str(bad) in row for row in meta["skipped_auto_candidates"]))

    def test_nr_runtime_corrupt_pinned_cache_is_not_install_authority(self):
        _runtime, archive = self._install_pinned_nr_fixture("ada")
        archive.write_bytes(b"corrupt-after-pin")
        called = []
        def refuse_download(family):
            called.append(family)
            raise self.m.Stop("network disabled fixture")
        self.m._download_nr_runtime_archive = refuse_download
        with self.assertRaises(self.m.Stop) as cm:
            self.m.ensure_nr_runtime_archive("ada")
        self.assertEqual(called, ["ada"])
        self.assertIn("network disabled fixture", str(cm.exception))

    def test_nr_runtime_download_is_hash_and_size_pinned_and_cleans_partial_on_failure(self):
        self.m.HOME = self.base / "home"
        self.m.DEFAULT_DOWNLOAD_DIR = self.base / "Downloads" / "Compressed"
        source = self.base / "nr-source.zip"
        runtime = b"MZ" + (b"D" * (70 * 1024))
        with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr(self.m.NR_RUNTIME_NAME, runtime)
        blob = source.read_bytes()
        digest = hashlib.sha256(blob).hexdigest()
        self.m.NR_RUNTIME_PROVIDERS = dict(self.m.NR_RUNTIME_PROVIDERS)
        self.m.NR_RUNTIME_PROVIDERS["ada"] = {
            "name": "fixture NR download",
            "tag": "fixture-download",
            "archive": "fixture-download.zip",
            "sha256": digest,
            "url": "https://example.invalid/fixture-download.zip",
            "release_size": len(blob),
        }
        self.m.urllib.request.urlopen = lambda *a, **k: io.BytesIO(blob)
        cached = self.m._download_nr_runtime_archive("ada")
        self.assertEqual(self.m.sha256_file(cached), digest)
        self.assertEqual(cached.stat().st_size, len(blob))
        self.assertFalse(list(cached.parent.glob(".*.part-*")))

        cached.unlink()
        self.m.NR_RUNTIME_PROVIDERS["ada"]["sha256"] = "0" * 64
        with self.assertRaises(self.m.Stop):
            self.m._download_nr_runtime_archive("ada")
        self.assertFalse(list(cached.parent.glob(".*.part-*")))

    def test_batch_install_passes_explicit_nr_runtime_to_each_game_and_continues_after_failure(self):
        runtime_path = self.base / "nvngx_dlssnr.dll"
        runtime_bytes = b"MZ" + (b"R" * 128)
        runtime_path.write_bytes(runtime_bytes)
        archive = self.base / "provider.7z"
        archive.write_bytes(b"fixture")
        payload = self._sm86_payload()
        payload.pop("nvngx_dlssnr.dll", None)
        meta = {"name": "provider.7z", "sha256": "a" * 64, "tag": "fixture"}

        target2 = self.drive / "SteamLibrary" / "steamapps" / "common" / "Fixture2" / "Binaries" / "Win64"
        target2.mkdir(parents=True)
        exe2 = target2 / "game2.exe"
        exe2.write_bytes(b"MZfixture2")
        game2 = self.m.Game("B", "Fixture2", target2.parents[2], "Steam", "124", None, exe2, target2)
        game2.dlss = game2.dlssg = True
        self.game.dlss = self.game.dlssg = True
        selected = [self.game, game2]

        self.m.load_archive_payload = lambda _archive: (payload, meta)
        self.m.resolve_family = lambda _override=None: ("ada", "RTX 4070")
        self.m.print_games = lambda *a, **k: None
        self.m.heading = lambda *a, **k: None
        self.m.kv = lambda *a, **k: None
        self.m.write_batch_report = lambda *a, **k: self.base / "report.md"
        self.m.sync_launch_options_batch = lambda *a, **k: None
        calls = []

        def fake_install(game, _payload, _meta, family, *args, **kwargs):
            calls.append(game.name)
            self.assertEqual(family, "ada")
            self.assertEqual(kwargs["nr_runtime_payload"], runtime_bytes)
            self.assertEqual(kwargs["nr_runtime_meta"]["path"], str(runtime_path.resolve()))
            if game is self.game:
                raise self.m.Stop("fixture failure")
            return {
                "proxy": "dxgi.dll", "mfg_provider": {"name": self.m.Y4MY_PROVIDER["name"]},
                "nr_profile": {"enabled": True}, "launch_options": 'WINEDLLOVERRIDES="dxgi=n,b" %command%',
                "permission_repairs": [],
            }

        self.m.install_target = fake_install
        self.m.batch_install(
            selected, self.drive, archive, family_override="ada", assume_yes=True,
            nr_runtime_explicit=str(runtime_path),
        )
        self.assertEqual(calls, ["Fixture", "Fixture2"])

    def test_batch_install_missing_local_nr_runtime_bootstraps_once_for_nineteen_targets(self):
        runtime, archive = self._install_pinned_nr_fixture("ada")
        provider_archive = self.base / "provider.7z"
        provider_archive.write_bytes(b"fixture")
        payload = self._sm86_payload()
        payload.pop("nvngx_dlssnr.dll", None)
        meta = {"name": "provider.7z", "sha256": "a" * 64, "tag": "fixture"}
        selected = []
        for idx in range(19):
            target = self.drive / "SteamLibrary" / "steamapps" / "common" / f"Fixture{idx}" / "Binaries" / "Win64"
            target.mkdir(parents=True, exist_ok=True)
            exe = target / f"game{idx}.exe"
            exe.write_bytes(b"MZfixture")
            game = self.m.Game(str(idx), f"Fixture{idx}", target.parents[2], "Steam", str(1000 + idx), None, exe, target)
            game.dlss = game.dlssg = True
            selected.append(game)

        self.m.load_archive_payload = lambda _archive: (payload, meta)
        self.m.resolve_family = lambda _override=None: ("ada", "RTX 4070")
        self.m.print_games = lambda *a, **k: None
        self.m.heading = lambda *a, **k: None
        self.m.kv = lambda *a, **k: None
        self.m.write_batch_report = lambda *a, **k: self.base / "report.md"
        self.m.sync_launch_options_batch = lambda *a, **k: None
        seen = []
        def fake_install(game, _payload, _meta, family, *args, **kwargs):
            self.assertEqual(family, "ada")
            self.assertEqual(kwargs["nr_runtime_payload"], runtime)
            self.assertEqual(kwargs["nr_runtime_meta"]["path"], str(archive.resolve()))
            seen.append(game.name)
            return {
                "proxy": "dxgi.dll",
                "mfg_provider": {"name": self.m.Y4MY_PROVIDER["name"]},
                "nr_profile": {"enabled": True},
                "launch_options": 'WINEDLLOVERRIDES="dxgi=n,b" %command%',
                "permission_repairs": [],
            }
        self.m.install_target = fake_install
        self.m.batch_install(selected, self.drive, provider_archive, family_override="ada", assume_yes=True)
        self.assertEqual(len(seen), 19)

    def test_new_install_batch_has_no_active_legacy_mfg_loader_calls(self):
        import inspect
        source = inspect.getsource(self.m.batch_install)
        self.assertNotIn("load_integrated_ada_runtime", source)
        self.assertNotIn("load_rtxmfg_payload", source)
        self.assertNotIn("ensure_rtxmfg_archive", source)
        self.assertIn("load_user_nr_runtime", source)

    def test_scan_is_non_mutating_for_game_tree_and_state_root(self):
        root = self.drive / "SteamLibrary" / "steamapps" / "common" / "ScanFixture"
        root.mkdir(parents=True)
        exe = root / "ScanFixture.exe"
        exe.write_bytes(b"MZfixture")
        (root / "nvngx_dlss.dll").write_bytes(b"dlss")
        before = sorted((str(x.relative_to(self.drive)), x.read_bytes() if x.is_file() else None) for x in self.drive.rglob("*"))
        self.m.discover_games(self.drive)
        after = sorted((str(x.relative_to(self.drive)), x.read_bytes() if x.is_file() else None) for x in self.drive.rglob("*"))
        self.assertEqual(after, before)
        self.assertFalse(self.m.STATE_ROOT.exists())


    def test_cli_forwards_provider_nr_runtime_and_gpu_family_to_interactive_small_matrix(self):
        seen = {}
        self.m.detect_drive = lambda _override=None: self.drive
        def fake_interactive(drive_override=None, **kwargs):
            seen["drive"] = drive_override
            seen.update(kwargs)
            return 17
        self.m.interactive_main = fake_interactive
        rc = self.m.cli_main([
            "--drive", str(self.drive), "--archive", "/tmp/provider.7z",
            "--nr-runtime", "/tmp/nvngx_dlssnr.dll", "--gpu-family", "ada",
        ])
        self.assertEqual(rc, 17)
        self.assertEqual(seen["drive"], str(self.drive))
        self.assertEqual(seen["archive_override"], "/tmp/provider.7z")
        self.assertEqual(seen["nr_runtime_explicit"], "/tmp/nvngx_dlssnr.dll")
        self.assertEqual(seen["family_override"], "ada")

    def test_cli_help_smoke(self):
        cp = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("rtxEngine Terminal Edition v13", cp.stdout)
        self.assertIn("--deep-clean-all", cp.stdout)
        self.assertIn("--verify-queue-auto", cp.stdout)


    def test_restore_preserves_runtime_drift_inside_optiscaler_tree(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "6" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")

        runtime_log = self.target / "OptiScaler" / "runtime-created.log"
        runtime_log.write_text("runtime diagnostics", encoding="utf-8")
        managed = self.target / "OptiScaler" / "core.dll"
        managed.write_bytes(b"user-edited-core")

        row = self.m.restore_target(self.game)
        recovery = Path(row["recovery"])
        self.assertEqual(
            (recovery / "OptiScaler" / "runtime-created.log").read_text(encoding="utf-8"),
            "runtime diagnostics",
        )
        self.assertEqual(
            (recovery / "OptiScaler" / "core.dll").read_bytes(),
            b"user-edited-core",
        )

    def test_restore_refuses_live_optiscaler_symlink_before_deleting_tree(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "7" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        outside = self.base / "outside-runtime.txt"
        outside.write_text("keep", encoding="utf-8")
        link = self.target / "OptiScaler" / "runtime-link"
        link.symlink_to(outside)

        with self.assertRaises(self.m.Stop):
            self.m.restore_target(self.game)
        self.assertTrue((self.target / "OptiScaler").is_dir())
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep")
        self.assertTrue(self.m.baseline_path(self.target).is_file())


    def test_mixed_steam_and_nonsteam_launchoptions_restore_in_one_batch(self):
        steam_root = self.base / "Steam"
        config_dir = steam_root / "userdata" / "42" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        localconfig = config_dir / "localconfig.vdf"
        current_steam = 'WINEDLLOVERRIDES="dxgi=n,b" MANGOHUD=1 %command%'
        original_steam = 'MANGOHUD=1 %command%'
        localconfig.write_text(
            '"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n\t\t\t\t{\n\t\t\t\t\t"123"\n\t\t\t\t\t{\n'
            f'\t\t\t\t\t\t"LaunchOptions"\t\t"{current_steam.replace(chr(34), chr(92)+chr(34))}"\n'
            '\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n',
            encoding="utf-8",
        )
        self.m.STEAM_ROOT_CANDIDATES = (steam_root,)
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True

        self.game.installed = True
        self.game.reason = "INSTALLED"
        steam_b = self._baseline()
        steam_b["steam_launch"] = {
            "kind": "steam", "config_path": str(localconfig), "steam_userid": "42",
            "appid": "123", "original": original_steam, "applied": current_steam,
        }
        self.m.save_json_atomic(self.m.baseline_path(self.target), steam_b)

        non_root = self.drive / "Non-Steam Games" / "Other"
        non_target = non_root / "Binaries" / "Win64"
        non_target.mkdir(parents=True)
        non_exe = non_target / "other.exe"
        non_exe.write_bytes(b"MZother")
        non = self.m.Game("B", "Other", non_root, "Non-Steam", None, None, non_exe, non_target, installed=True, reason="INSTALLED")
        original_non = 'gamescope -f %command% -dx12'
        applied_non = 'WINEDLLOVERRIDES="version=n,b" gamescope -f %command% -dx12'
        shortcuts = config_dir / "shortcuts.vdf"
        shortcuts.write_bytes(make_shortcuts_fixture(non, applied_non))
        non_state = {
            "schema": 13, "status": "active", "created_utc": self.m.now_iso(),
            "name": non.name, "source": non.source, "appid": None,
            "exe": str(non_exe), "target_dir": str(non_target),
            "originals": {}, "managed_paths": [], "history": [], "current": {"installed_hashes": {}},
            "steam_launch": {
                "kind": "shortcut", "config_path": str(shortcuts), "steam_userid": "42",
                "shortcut_appid": 0x1234567, "shortcut_appname": non.name,
                "shortcut_exe": str(non_exe), "original": original_non, "applied": applied_non,
            },
        }
        self.m.state_dir_for(non_target).mkdir(parents=True, exist_ok=True)
        self.m.save_json_atomic(self.m.baseline_path(non_target), non_state)

        rows = self.m.restore_launch_options_batch([self.game, non], assume_yes=True)
        self.assertEqual({row["kind"] for row in rows}, {"Steam", "Non-Steam"})
        self.assertEqual(self.m.read_localconfig_launch_options(localconfig, "123"), original_steam)
        obj = self.m.match_shortcut_span(non, self.m.parse_shortcuts_spans(shortcuts.read_bytes()))
        self.assertEqual(self.m._shortcut_string(obj, "LaunchOptions"), original_non)

    def test_launchoptions_restore_refuses_owned_override_drift_before_any_write(self):
        config = self._steam_localconfig(None)
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        original = "%command%"
        required = 'WINEDLLOVERRIDES="dxgi=n,b" %command%'
        applied = self.m.merge_rtxengine_launch_options(original, required)
        current = applied.replace("dxgi=n,b", "dxgi=b")
        self.m.update_localconfig_launch_options(config, {"123": current})
        baseline = self._baseline()
        baseline["steam_launch"] = {
            "kind": "steam", "config_path": str(config), "steam_userid": "42",
            "appid": "123", "original": original, "applied": applied, "required": required,
        }
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)
        before = config.read_bytes()
        with self.assertRaises(self.m.Stop) as cm:
            self.m.restore_launch_options_batch([self.game], assume_yes=True)
        self.assertIn("rtxEngine-owned override dxgi", str(cm.exception))
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse((self.m.STATE_ROOT / "steam-transactions").exists())
        self.assertFalse((self.m.STATE_ROOT / "steam-config-backups").exists())

    def test_launchoptions_restore_preserves_unrelated_post_install_edits(self):
        config = self._steam_localconfig(None)
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        original = 'MANGOHUD=1 gamescope -f %command% -dx12'
        required = 'WINEDLLOVERRIDES="dxgi=n,b;version=n,b" PROTON_ENABLE_NVAPI=1 PROTON_NVIDIA_NVCUDA=1 %command%'
        applied = self.m.merge_rtxengine_launch_options(original, required)
        current = applied + ' USERFLAG=1 -newarg'
        self.m.update_localconfig_launch_options(config, {"123": current})
        baseline = self._baseline()
        baseline["steam_launch"] = {
            "kind": "steam", "config_path": str(config), "steam_userid": "42",
            "appid": "123", "original": original, "applied": applied, "required": required,
        }
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)

        rows = self.m.restore_launch_options_batch([self.game], assume_yes=True)
        self.assertEqual(rows[0]["status"], "restored")
        restored = self.m.read_localconfig_launch_options(config, "123")
        self.assertEqual(restored, original + ' USERFLAG=1 -newarg')

    def test_launchoptions_restore_preserves_unrelated_wine_override_and_restores_preexisting_proxy_value(self):
        config = self._steam_localconfig(None)
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        original = 'WINEDLLOVERRIDES="dxgi=b;dinput8=n,b" MANGOHUD=1 %command%'
        required = 'WINEDLLOVERRIDES="dxgi=n,b;version=n,b" PROTON_ENABLE_NVAPI=1 PROTON_NVIDIA_NVCUDA=1 %command%'
        applied = self.m.merge_rtxengine_launch_options(original, required)
        # User adds a Wine override rtxEngine never owned after installation.
        current = applied.replace('version=n,b"', 'version=n,b;winhttp=n,b"') + ' EXTRA=1'
        self.m.update_localconfig_launch_options(config, {"123": current})
        baseline = self._baseline()
        baseline["steam_launch"] = {
            "kind": "steam", "config_path": str(config), "steam_userid": "42",
            "appid": "123", "original": original, "applied": applied, "required": required,
        }
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)

        self.m.restore_launch_options_batch([self.game], assume_yes=True)
        restored = self.m.read_localconfig_launch_options(config, "123")
        self.assertIn('WINEDLLOVERRIDES="dxgi=b;dinput8=n,b;winhttp=n,b"', restored)
        self.assertNotIn('version=n,b', restored)
        self.assertIn('MANGOHUD=1 %command% EXTRA=1', restored)

    def test_launchoptions_restore_keeps_new_user_options_when_original_key_was_absent(self):
        config = self._steam_localconfig(None)
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        required = 'WINEDLLOVERRIDES="dxgi=n,b" PROTON_ENABLE_NVAPI=1 PROTON_NVIDIA_NVCUDA=1 %command%'
        applied = self.m.merge_rtxengine_launch_options(None, required)
        current = applied.replace('%command%', 'MANGOHUD=1 %command% -dx12')
        self.m.update_localconfig_launch_options(config, {"123": current})
        baseline = self._baseline()
        baseline["steam_launch"] = {
            "kind": "steam", "config_path": str(config), "steam_userid": "42",
            "appid": "123", "original": None, "applied": applied, "required": required,
        }
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)

        self.m.restore_launch_options_batch([self.game], assume_yes=True)
        self.assertEqual(
            self.m.read_localconfig_launch_options(config, "123"),
            'MANGOHUD=1 %command% -dx12',
        )

    def test_owned_delta_restore_refuses_multiple_winedlloverrides_assignments(self):
        original = '%command%'
        required = 'WINEDLLOVERRIDES="dxgi=n,b" PROTON_ENABLE_NVAPI=1 PROTON_NVIDIA_NVCUDA=1 %command%'
        applied = self.m.merge_rtxengine_launch_options(original, required)
        # A second assignment after %command% is a game argument, not an
        # environment-prefix assignment. It must survive owned-delta restore.
        current = applied + ' WINEDLLOVERRIDES="winhttp=n,b"'
        restored = self.m.reconcile_rtxengine_launch_options(current, original, applied)
        self.assertEqual(restored, '%command% WINEDLLOVERRIDES="winhttp=n,b"')

        # Two actual pre-command assignments remain ambiguous and must refuse.
        current = 'WINEDLLOVERRIDES="dxgi=n,b" WINEDLLOVERRIDES="winhttp=n,b" PROTON_ENABLE_NVAPI=1 PROTON_NVIDIA_NVCUDA=1 %command%'
        with self.assertRaises(self.m.Stop) as cm:
            self.m.reconcile_rtxengine_launch_options(current, original, applied)
        self.assertIn("multiple WINEDLLOVERRIDES", str(cm.exception))

    def test_nonsteam_launchoptions_restore_preserves_unrelated_post_install_edits(self):
        steam_root = self.base / "Steam"
        config_dir = steam_root / "userdata" / "42" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        self.m.STEAM_ROOT_CANDIDATES = (steam_root,)
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True

        non_root = self.drive / "Non-Steam Games" / "Delta"
        non_target = non_root / "Binaries" / "Win64"
        non_target.mkdir(parents=True)
        non_exe = non_target / "delta.exe"
        non_exe.write_bytes(b"MZdelta")
        non = self.m.Game("B", "Delta", non_root, "Non-Steam", None, None, non_exe, non_target, installed=True, reason="INSTALLED")
        original = 'gamescope -f %command% -dx12'
        required = 'WINEDLLOVERRIDES="version=n,b" PROTON_ENABLE_NVAPI=1 PROTON_NVIDIA_NVCUDA=1 %command%'
        applied = self.m.merge_rtxengine_launch_options(original, required)
        current = applied + ' USERFLAG=1'
        shortcuts = config_dir / "shortcuts.vdf"
        shortcuts.write_bytes(make_shortcuts_fixture(non, current))
        state = {
            "schema": 13, "status": "active", "created_utc": self.m.now_iso(),
            "name": non.name, "source": non.source, "appid": None,
            "exe": str(non_exe), "target_dir": str(non_target),
            "originals": {}, "managed_paths": [], "history": [], "current": {"installed_hashes": {}},
            "steam_launch": {
                "kind": "shortcut", "config_path": str(shortcuts), "steam_userid": "42",
                "shortcut_appid": 0x1234567, "shortcut_appname": non.name,
                "shortcut_exe": str(non_exe), "original": original, "applied": applied, "required": required,
            },
        }
        self.m.state_dir_for(non_target).mkdir(parents=True, exist_ok=True)
        self.m.save_json_atomic(self.m.baseline_path(non_target), state)

        self.m.restore_launch_options_batch([non], assume_yes=True)
        obj = self.m.match_shortcut_span(non, self.m.parse_shortcuts_spans(shortcuts.read_bytes()))
        self.assertEqual(self.m._shortcut_string(obj, "LaunchOptions"), original + ' USERFLAG=1')

    def test_multiconfig_launchoptions_restore_rolls_back_earlier_write_on_late_failure(self):
        steam_root = self.base / "Steam"
        config_dir = steam_root / "userdata" / "42" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        localconfig = config_dir / "localconfig.vdf"
        current_steam = 'WINEDLLOVERRIDES="dxgi=n,b" MANGOHUD=1 %command%'
        original_steam = 'MANGOHUD=1 %command%'
        localconfig.write_text(
            '"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n\t\t\t\t{\n\t\t\t\t\t"123"\n\t\t\t\t\t{\n'
            f'\t\t\t\t\t\t"LaunchOptions"\t\t"{current_steam.replace(chr(34), chr(92)+chr(34))}"\n'
            '\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n',
            encoding="utf-8",
        )
        self.m.STEAM_ROOT_CANDIDATES = (steam_root,)
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True
        steam_b = self._baseline()
        steam_b["steam_launch"] = {
            "kind": "steam", "config_path": str(localconfig), "steam_userid": "42",
            "appid": "123", "original": original_steam, "applied": current_steam,
        }
        self.m.save_json_atomic(self.m.baseline_path(self.target), steam_b)

        non_root = self.drive / "Non-Steam Games" / "OtherRollback"
        non_target = non_root / "Binaries" / "Win64"
        non_target.mkdir(parents=True)
        non_exe = non_target / "other.exe"
        non_exe.write_bytes(b"MZother")
        non = self.m.Game("B", "OtherRollback", non_root, "Non-Steam", None, None, non_exe, non_target, installed=True, reason="INSTALLED")
        original_non = 'gamescope -f %command% -dx12'
        applied_non = 'WINEDLLOVERRIDES="version=n,b" gamescope -f %command% -dx12'
        shortcuts = config_dir / "shortcuts.vdf"
        shortcuts.write_bytes(make_shortcuts_fixture(non, applied_non))
        non_state = {
            "schema": 13, "status": "active", "created_utc": self.m.now_iso(),
            "name": non.name, "source": non.source, "appid": None,
            "exe": str(non_exe), "target_dir": str(non_target),
            "originals": {}, "managed_paths": [], "history": [], "current": {"installed_hashes": {}},
            "steam_launch": {
                "kind": "shortcut", "config_path": str(shortcuts), "steam_userid": "42",
                "shortcut_appid": 0x1234567, "shortcut_appname": non.name,
                "shortcut_exe": str(non_exe), "original": original_non, "applied": applied_non,
            },
        }
        self.m.state_dir_for(non_target).mkdir(parents=True, exist_ok=True)
        self.m.save_json_atomic(self.m.baseline_path(non_target), non_state)

        original_restore = self.m.restore_shortcut_launch_option
        calls = {"count": 0}
        def fail_first_apply_then_allow_rollback(path, locator, value):
            calls["count"] += 1
            if calls["count"] == 1:
                raise self.m.Stop("simulated late shortcut restore failure")
            return original_restore(path, locator, value)
        self.m.restore_shortcut_launch_option = fail_first_apply_then_allow_rollback

        with self.assertRaises(self.m.Stop) as cm:
            self.m.restore_launch_options_batch([self.game, non], assume_yes=True)
        self.assertIn("rolled back safely", str(cm.exception))
        self.assertEqual(self.m.read_localconfig_launch_options(localconfig, "123"), current_steam)
        obj = self.m.match_shortcut_span(non, self.m.parse_shortcuts_spans(shortcuts.read_bytes()))
        self.assertEqual(self.m._shortcut_string(obj, "LaunchOptions"), applied_non)
        self.assertEqual(list((self.m.STATE_ROOT / "steam-transactions").glob("*.json")) if (self.m.STATE_ROOT / "steam-transactions").exists() else [], [])




    def test_postcommit_cleanup_failure_never_rolls_back_remaining_config(self):
        steam_root = self.base / "Steam"
        config_dir = steam_root / "userdata" / "42" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        self.m.STEAM_ROOT_CANDIDATES = (steam_root,)
        self.m.ensure_steam_stopped_for_write = lambda assume_yes=False: True

        # Steam game config + baseline.
        localconfig = config_dir / "localconfig.vdf"
        current_steam = 'WINEDLLOVERRIDES="dxgi=n,b" MANGOHUD=1 %command%'
        original_steam = 'MANGOHUD=1 %command%'
        localconfig.write_text(
            '"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n\t\t\t\t{\n\t\t\t\t\t"123"\n\t\t\t\t\t{\n'
            f'\t\t\t\t\t\t"LaunchOptions"\t\t"{current_steam.replace(chr(34), chr(92)+chr(34))}"\n'
            '\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n',
            encoding="utf-8",
        )
        steam_b = self._baseline()
        steam_b["steam_launch"] = {
            "kind": "steam", "config_path": str(localconfig), "steam_userid": "42",
            "appid": "123", "original": original_steam, "applied": current_steam,
        }
        self.m.save_json_atomic(self.m.baseline_path(self.target), steam_b)

        # Non-Steam shortcut config + baseline gives the restore two journals.
        non_root = self.drive / "Non-Steam Games" / "CommittedCleanup"
        non_target = non_root / "Binaries" / "Win64"
        non_target.mkdir(parents=True)
        non_exe = non_target / "other.exe"
        non_exe.write_bytes(b"MZother")
        non = self.m.Game("B", "CommittedCleanup", non_root, "Non-Steam", None, None, non_exe, non_target, installed=True, reason="INSTALLED")
        original_non = 'gamescope -f %command% -dx12'
        applied_non = 'WINEDLLOVERRIDES="version=n,b" gamescope -f %command% -dx12'
        shortcuts = config_dir / "shortcuts.vdf"
        shortcuts.write_bytes(make_shortcuts_fixture(non, applied_non))
        non_state = {
            "schema": 13, "status": "active", "created_utc": self.m.now_iso(),
            "name": non.name, "source": non.source, "appid": None,
            "exe": str(non_exe), "target_dir": str(non_target),
            "originals": {}, "managed_paths": [], "history": [], "current": {"installed_hashes": {}},
            "steam_launch": {
                "kind": "shortcut", "config_path": str(shortcuts), "steam_userid": "42",
                "shortcut_appid": 0x1234567, "shortcut_appname": non.name,
                "shortcut_exe": str(non_exe), "original": original_non, "applied": applied_non,
            },
        }
        self.m.state_dir_for(non_target).mkdir(parents=True, exist_ok=True)
        self.m.save_json_atomic(self.m.baseline_path(non_target), non_state)

        original_complete = self.m.complete_steam_transaction
        calls = {"n": 0}
        def complete_one_then_fail(path, data):
            calls["n"] += 1
            original_complete(path, data)
            if calls["n"] == 1:
                raise OSError("simulated cleanup failure after first journal removal")
        self.m.complete_steam_transaction = complete_one_then_fail
        try:
            with self.assertRaises(self.m.Stop) as cm:
                self.m.restore_launch_options_batch([self.game, non], assume_yes=True)
        finally:
            self.m.complete_steam_transaction = original_complete

        self.assertIn("committed successfully, but transaction cleanup was incomplete", str(cm.exception))
        # Both config writes were committed before the marker; neither may be
        # partially rolled back because cleanup failed afterward.
        self.assertEqual(self.m.read_localconfig_launch_options(localconfig, "123"), original_steam)
        obj = self.m.match_shortcut_span(non, self.m.parse_shortcuts_spans(shortcuts.read_bytes()))
        self.assertEqual(self.m._shortcut_string(obj, "LaunchOptions"), original_non)
        tx_root = self.m._steam_transaction_root()
        markers = list(tx_root.glob("batch-*.commit"))
        self.assertEqual(len(markers), 1)
        self.assertTrue(list(tx_root.glob("*.json")), "remaining journal must survive for cleanup recovery")

        rows = self.m.recover_pending_steam_transactions(assume_yes=True)
        self.assertTrue(any(r["status"] == "commit-cleanup-completed" for r in rows))
        self.assertEqual(self.m.read_localconfig_launch_options(localconfig, "123"), original_steam)
        obj = self.m.match_shortcut_span(non, self.m.parse_shortcuts_spans(shortcuts.read_bytes()))
        self.assertEqual(self.m._shortcut_string(obj, "LaunchOptions"), original_non)
        self.assertFalse(list(tx_root.glob("*.json")))
        self.assertFalse(list(tx_root.glob("batch-*.commit")))

    def test_failed_restore_is_durably_marked_recovery_before_live_mutation(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "8" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        proxy = self.target / "dxgi.dll"
        real_unlink = self.m.durable_unlink
        saw_pending = {"value": False}

        def fail_first_live_unlink(path, *args, **kwargs):
            if Path(path) == proxy:
                state = self.m.load_baseline(self.target)
                saw_pending["value"] = state.get("status") == "restore-pending"
                raise OSError("simulated crash at first live unlink")
            return real_unlink(path, *args, **kwargs)

        self.m.durable_unlink = fail_first_live_unlink
        try:
            with self.assertRaises(OSError):
                self.m.restore_target(self.game)
        finally:
            self.m.durable_unlink = real_unlink
        self.assertTrue(saw_pending["value"])
        state = self.m.load_baseline(self.target)
        self.assertEqual(state["status"], "restore-pending")
        self.assertEqual(state["restore_pending"]["previous_status"], "active")
        states = self.m.load_installed_states_under_drive(self.drive)
        recorded = next(g for g in states if g.target_dir == self.target)
        self.assertEqual(recorded.reason, "RECOVERY")
        with self.assertRaises(self.m.Stop) as cm:
            self.m.audit_target(recorded)
        self.assertIn("not active", str(cm.exception))
        with self.assertRaises(self.m.Stop) as cm:
            self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertIn("restore/uninstall is still pending", str(cm.exception))

    def test_restore_pending_retry_remains_idempotent_and_completes(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "7" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        proxy = self.target / "dxgi.dll"
        real_unlink = self.m.durable_unlink
        failed = {"value": False}
        def fail_once(path, *args, **kwargs):
            if Path(path) == proxy and not failed["value"]:
                failed["value"] = True
                raise OSError("simulated first restore interruption")
            return real_unlink(path, *args, **kwargs)
        self.m.durable_unlink = fail_once
        try:
            with self.assertRaises(OSError):
                self.m.restore_target(self.game)
        finally:
            self.m.durable_unlink = real_unlink
        result = self.m.restore_target(self.game)
        self.assertFalse(self.m.baseline_path(self.target).exists())
        receipt = Path(result["archived_state"])
        self.assertEqual(json.loads(receipt.read_text(encoding="utf-8"))["status"], "restored")

    def test_restore_retry_never_overwrites_preserved_drift_with_restored_original(self):
        original = self.target / "OptiScaler.ini"
        original.write_bytes(b"game-original")
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "a" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        original.write_bytes(b"user-drift-first")

        real_replace = self.m.durable_replace
        failed = {"done": False}
        def fail_before_baseline_archive(src, dst):
            if (
                not failed["done"]
                and Path(src) == self.m.baseline_path(self.target)
                and Path(dst).name.startswith("baseline-restored-")
            ):
                failed["done"] = True
                raise OSError("simulated crash after original bytes were restored")
            return real_replace(src, dst)
        self.m.durable_replace = fail_before_baseline_archive
        try:
            with self.assertRaises(OSError):
                self.m.restore_target(self.game)
        finally:
            self.m.durable_replace = real_replace

        baseline = self.m.load_baseline(self.target)
        self.assertIsNotNone(baseline)
        recovery = Path(baseline["restore_recovery_dir"])
        preserved = recovery / "OptiScaler.ini"
        self.assertEqual(preserved.read_bytes(), b"user-drift-first")
        self.assertEqual(original.read_bytes(), b"game-original")

        self.m.restore_target(self.game)
        self.assertEqual(preserved.read_bytes(), b"user-drift-first")
        self.assertEqual(original.read_bytes(), b"game-original")

    def test_restore_retry_reuses_same_recovery_slot_and_preserves_prior_drift(self):
        original = self.target / "OptiScaler.ini"
        original.write_bytes(b"game-original")
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "c" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        original.write_bytes(b"user-drift-that-must-survive")

        real_copy2 = self.m.shutil.copy2
        failed_once = {"value": False}

        def fail_on_original_restore(src, dst, *args, **kwargs):
            src_path = Path(src)
            if (
                not failed_once["value"]
                and "baseline-backup" in src_path.parts
                and src_path.name == "OptiScaler.ini"
            ):
                failed_once["value"] = True
                raise OSError("simulated restore failure after drift capture")
            return real_copy2(src, dst, *args, **kwargs)

        self.m.shutil.copy2 = fail_on_original_restore
        try:
            with self.assertRaises(OSError):
                self.m.restore_target(self.game)
        finally:
            self.m.shutil.copy2 = real_copy2

        after_failure = self.m.load_baseline(self.target)
        self.assertIsNotNone(after_failure)
        slot = Path(after_failure["restore_recovery_dir"])
        preserved = slot / "OptiScaler.ini"
        self.assertTrue(preserved.is_file())
        self.assertEqual(preserved.read_bytes(), b"user-drift-that-must-survive")
        self.assertFalse(original.exists())

        result = self.m.restore_target(self.game)
        self.assertEqual(Path(result["recovery"]), slot)
        self.assertTrue(preserved.is_file())
        self.assertEqual(preserved.read_bytes(), b"user-drift-that-must-survive")
        self.assertEqual(original.read_bytes(), b"game-original")

    def test_tar_file_restore_destination_must_match_baseline_key_before_mutation(self):
        victim = self.target / "victim.dll"
        wrong = self.target / "wrong.dll"
        victim.write_bytes(b"live-victim")
        wrong.write_bytes(b"live-wrong")

        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True, exist_ok=True)
        backup_root = self.m._validated_baseline_backup_root(self.target, require_exists=False)
        backup_root.mkdir(parents=True, exist_ok=True)
        archive = backup_root / "file-tars" / "victim.dll.tar"
        archive.parent.mkdir(parents=True, exist_ok=True)
        payload = self.base / "wrong.dll"
        payload.write_bytes(b"archived-original")
        with tarfile.open(archive, "w") as tf:
            tf.add(payload, arcname="wrong.dll")

        baseline = self._baseline()
        baseline["originals"] = {
            "victim.dll": {
                "kind": "tar_file",
                "existed": True,
                "backup": str(archive),
                "member": "wrong.dll",
                "restore_parent": ".",
                "archive_sha256": self.m.sha256_file(archive),
                "preserves_numeric_owner": True,
            }
        }
        baseline["managed_paths"] = ["victim.dll"]

        with self.assertRaises(self.m.Stop) as cm:
            self.m.verify_baseline_integrity(self.target, baseline, adopt_legacy=False)

        self.assertIn("restore destination mismatch", str(cm.exception))
        self.assertEqual(victim.read_bytes(), b"live-victim")
        self.assertEqual(wrong.read_bytes(), b"live-wrong")

    def test_tar_file_restore_destination_case_must_match_baseline_key(self):
        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True, exist_ok=True)
        backup_root = self.m._validated_baseline_backup_root(self.target, require_exists=False)
        backup_root.mkdir(parents=True, exist_ok=True)
        archive = backup_root / "file-tars" / "Victim.dll.tar"
        archive.parent.mkdir(parents=True, exist_ok=True)
        payload = self.base / "victim.dll"
        payload.write_bytes(b"archived-original")
        with tarfile.open(archive, "w") as tf:
            tf.add(payload, arcname="victim.dll")

        baseline = self._baseline()
        baseline["originals"] = {
            "Victim.dll": {
                "kind": "tar_file",
                "existed": True,
                "backup": str(archive),
                "member": "victim.dll",
                "restore_parent": ".",
                "archive_sha256": self.m.sha256_file(archive),
                "preserves_numeric_owner": True,
            }
        }
        baseline["managed_paths"] = ["Victim.dll"]

        with self.assertRaises(self.m.Stop) as cm:
            self.m.verify_baseline_integrity(self.target, baseline, adopt_legacy=False)
        self.assertIn("restore destination mismatch", str(cm.exception))

    def test_root_file_cannot_use_tree_baseline_kind_before_mutation(self):
        victim = self.target / "victim.dll"
        victim.write_bytes(b"live-managed-file")

        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True, exist_ok=True)
        backup_root = self.m._validated_baseline_backup_root(self.target, require_exists=False)
        backup_root.mkdir(parents=True, exist_ok=True)
        archive = backup_root / "trees" / "victim.dll.tar"
        archive.parent.mkdir(parents=True, exist_ok=True)
        payload_dir = self.base / "victim.dll"
        payload_dir.mkdir()
        (payload_dir / "original.bin").write_bytes(b"archived-tree")
        with tarfile.open(archive, "w") as tf:
            tf.add(payload_dir, arcname="victim.dll")

        baseline = self._baseline()
        baseline["originals"] = {
            "victim.dll": {
                "kind": "tar_tree",
                "existed": True,
                "backup": str(archive),
                "archive_sha256": self.m.sha256_file(archive),
            }
        }
        baseline["managed_paths"] = ["victim.dll"]
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)

        with self.assertRaises(self.m.Stop) as cm:
            self.m.restore_target(self.game)

        self.assertIn("File baseline kind is not a file", str(cm.exception))
        self.assertEqual(victim.read_bytes(), b"live-managed-file")
        self.assertFalse(baseline.get("restore_recovery_dir"))

    def test_optiscaler_tree_cannot_use_file_baseline_kind_before_mutation(self):
        live_tree = self.target / "OptiScaler"
        live_tree.mkdir(parents=True, exist_ok=True)
        live_file = live_tree / "live.txt"
        live_file.write_bytes(b"live-managed-tree")

        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True, exist_ok=True)
        backup_root = self.m._validated_baseline_backup_root(self.target, require_exists=False)
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / "OptiScaler.bin"
        backup.write_bytes(b"not-a-tree-baseline")

        baseline = self._baseline()
        baseline["originals"] = {
            "OptiScaler/": {
                "kind": "file",
                "existed": True,
                "backup": str(backup),
                "sha256": self.m.sha256_file(backup),
                "mode": 0o644,
            }
        }
        baseline["managed_paths"] = ["OptiScaler/"]
        self.m.save_json_atomic(self.m.baseline_path(self.target), baseline)

        with self.assertRaises(self.m.Stop) as cm:
            self.m.restore_target(self.game)

        self.assertIn("OptiScaler baseline kind is not a tree", str(cm.exception))
        self.assertTrue(live_tree.is_dir())
        self.assertEqual(live_file.read_bytes(), b"live-managed-tree")

    def test_tar_tree_root_must_be_directory_before_mutation(self):
        live_tree = self.target / "OptiScaler"
        live_tree.mkdir(parents=True, exist_ok=True)
        live_file = live_tree / "live.txt"
        live_file.write_bytes(b"live-managed-tree")

        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True, exist_ok=True)
        backup_root = self.m._validated_baseline_backup_root(self.target, require_exists=False)
        backup_root.mkdir(parents=True, exist_ok=True)
        archive = backup_root / "trees" / "OptiScaler.tar"
        archive.parent.mkdir(parents=True, exist_ok=True)
        payload = self.base / "OptiScaler"
        payload.write_bytes(b"not-a-directory")
        with tarfile.open(archive, "w") as tf:
            tf.add(payload, arcname="OptiScaler")

        baseline = self._baseline()
        baseline["originals"] = {
            "OptiScaler/": {
                "kind": "tar_tree",
                "existed": True,
                "backup": str(archive),
                "archive_sha256": self.m.sha256_file(archive),
                "preserves_numeric_owner": True,
            }
        }
        baseline["managed_paths"] = ["OptiScaler/"]

        with self.assertRaises(self.m.Stop) as cm:
            self.m.verify_baseline_integrity(self.target, baseline, adopt_legacy=False)

        self.assertIn("tree root is not a directory", str(cm.exception))
        self.assertTrue(live_tree.is_dir())
        self.assertEqual(live_file.read_bytes(), b"live-managed-tree")

    def test_case_colliding_originals_cannot_borrow_managed_duplicate_exception(self):
        baseline = self._baseline()
        baseline["originals"] = {
            "Case.dll": {"existed": False},
            "case.dll": {"existed": False},
        }
        baseline["managed_paths"] = ["Case.dll", "case.dll"]

        with self.assertRaises(self.m.Stop) as cm:
            self.m.verify_baseline_integrity(self.target, baseline, adopt_legacy=False)

        self.assertIn("Case-colliding persisted path", str(cm.exception))

    def test_validated_tar_snapshot_is_bound_to_bytes_even_if_archive_changes_after_staging(self):
        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True, exist_ok=True)
        backup_root = self.m._validated_baseline_backup_root(self.target, require_exists=False)
        backup_root.mkdir(parents=True, exist_ok=True)
        archive = backup_root / "file-tars" / "victim.dll.tar"
        archive.parent.mkdir(parents=True, exist_ok=True)
        payload = self.base / "victim.dll"
        payload.write_bytes(b"trusted-original")
        with tarfile.open(archive, "w") as tf:
            tf.add(payload, arcname="victim.dll")
        expected = self.m.sha256_file(archive)

        with self.m._validated_tar_snapshot(
            archive, expected, expected_top="victim.dll", exact_file=True
        ) as snap:
            # Replacing the pathname after staging must not change the stream
            # that privileged extraction will consume.
            payload.write_bytes(b"attacker-replacement")
            with tarfile.open(archive, "w") as tf:
                tf.add(payload, arcname="victim.dll")
            snap.seek(0)
            with tarfile.open(fileobj=snap, mode="r:*") as tf:
                restored = tf.extractfile("victim.dll").read()
            self.assertEqual(restored, b"trusted-original")

    def test_validated_tar_snapshot_rejects_changed_archive_before_extraction(self):
        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True, exist_ok=True)
        backup_root = self.m._validated_baseline_backup_root(self.target, require_exists=False)
        backup_root.mkdir(parents=True, exist_ok=True)
        archive = backup_root / "file-tars" / "victim.dll.tar"
        archive.parent.mkdir(parents=True, exist_ok=True)
        payload = self.base / "victim.dll"
        payload.write_bytes(b"trusted-original")
        with tarfile.open(archive, "w") as tf:
            tf.add(payload, arcname="victim.dll")
        expected = self.m.sha256_file(archive)
        payload.write_bytes(b"changed-before-staging")
        with tarfile.open(archive, "w") as tf:
            tf.add(payload, arcname="victim.dll")

        with self.assertRaises(self.m.Stop) as cm:
            with self.m._validated_tar_snapshot(
                archive, expected, expected_top="victim.dll", exact_file=True
            ):
                pass
        self.assertIn("tar hash mismatch", str(cm.exception))

    def test_provider_relinquish_privileged_restore_consumes_validated_snapshot(self):
        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True, exist_ok=True)
        backup_root = self.m._validated_baseline_backup_root(self.target, require_exists=False)
        backup_root.mkdir(parents=True, exist_ok=True)
        archive = backup_root / "file-tars" / "retired-provider.dll.tar"
        archive.parent.mkdir(parents=True, exist_ok=True)
        payload = self.base / "retired-provider.dll"
        payload.write_bytes(b"trusted-original")
        with tarfile.open(archive, "w") as tf:
            tf.add(payload, arcname="retired-provider.dll")

        info = {
            "kind": "tar_file",
            "existed": True,
            "backup": str(archive),
            "archive_sha256": self.m.sha256_file(archive),
            "member": "retired-provider.dll",
            "restore_parent": ".",
        }
        live = self.target / "retired-provider.dll"
        live.write_bytes(b"engine-owned")
        calls = []

        def fake_run(cmd, *, stdin=None, check=False, **kwargs):
            if stdin is None:
                return subprocess.CompletedProcess(cmd, 0)
            calls.append((list(cmd), stdin, check))
            self.assertIn("-xpf", cmd)
            self.assertEqual(cmd[cmd.index("-xpf") + 1], "-")
            # Replace the user-owned archive pathname after staging. The bytes
            # consumed by privileged extraction must remain the trusted snapshot.
            payload.write_bytes(b"attacker-replacement")
            with tarfile.open(archive, "w") as tf:
                tf.add(payload, arcname="retired-provider.dll")
            stdin.seek(0)
            with tarfile.open(fileobj=stdin, mode="r:*") as tf:
                member = tf.getmember("retired-provider.dll")
                restored = tf.extractfile(member).read()
            live.write_bytes(restored)
            return subprocess.CompletedProcess(cmd, 0)

        with patch.object(self.m.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), \
             patch.object(self.m.subprocess, "run", side_effect=fake_run):
            self.m._restore_baseline_file(self.target, "retired-provider.dll", info)

        self.assertEqual(live.read_bytes(), b"trusted-original")
        self.assertEqual(len(calls), 1)

    def test_provider_relinquish_original_hash_binds_tar_archive_hash(self):
        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True, exist_ok=True)
        backup_root = self.m._validated_baseline_backup_root(self.target, require_exists=False)
        backup_root.mkdir(parents=True, exist_ok=True)
        archive = backup_root / "file-tars" / "retired-provider.dll.tar"
        archive.parent.mkdir(parents=True, exist_ok=True)
        payload = self.base / "retired-provider.dll"
        payload.write_bytes(b"trusted-original")
        with tarfile.open(archive, "w") as tf:
            tf.add(payload, arcname="retired-provider.dll")
        expected_archive_hash = self.m.sha256_file(archive)
        info = {
            "kind": "tar_file",
            "existed": True,
            "backup": str(archive),
            "archive_sha256": expected_archive_hash,
            "member": "retired-provider.dll",
            "restore_parent": ".",
        }

        payload.write_bytes(b"changed-after-validation")
        with tarfile.open(archive, "w") as tf:
            tf.add(payload, arcname="retired-provider.dll")

        with self.assertRaises(self.m.Stop) as cm:
            self.m._baseline_original_file_hash(self.target, "retired-provider.dll", info)
        self.assertIn("tar hash mismatch", str(cm.exception))

    def test_recorded_restore_recovery_slot_escape_is_rejected(self):
        outside = self.base / "outside-recovery"
        outside.mkdir()
        baseline = self._baseline(restore_recovery_dir=str(outside))
        with self.assertRaises(self.m.Stop) as cm:
            self.m.verify_baseline_integrity(self.target, baseline, adopt_legacy=False)
        self.assertIn("escapes state root", str(cm.exception))

    def test_restore_target_refuses_live_game_before_file_mutation(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "b" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        proxy = self.target / "dxgi.dll"
        self.assertTrue(proxy.is_file())

        old_running = self.m._running_processes_under_root
        self.m._running_processes_under_root = lambda root: ["999/wine64 [cwd]"]
        try:
            with self.assertRaises(self.m.Stop) as cm:
                self.m.restore_target(self.game)
        finally:
            self.m._running_processes_under_root = old_running
        self.assertIn("Game process still using", str(cm.exception))
        self.assertTrue(proxy.is_file())
        self.assertTrue(self.m.baseline_path(self.target).is_file())

    def test_install_refuses_destructive_pending_recovery_state_before_mutation(self):
        self.game.dlss = True
        self.game.dlssg = True
        sentinel = self.target / "sentinel.bin"
        sentinel.write_bytes(b"keep")
        state_dir = self.m.state_dir_for(self.target)
        state_dir.mkdir(parents=True)
        baseline = {
            "schema": 13,
            "target_dir": str(self.target),
            "exe": str(self.game.exe),
            "name": self.game.name,
            "source": "Steam",
            "appid": "123",
            "status": "destructive-pending",
            "destructive_pending": {"mode": "deep-clean", "previous_status": "active"},
            "managed_paths": [],
            "originals": {},
            "current": {},
        }
        self.m.save_json_atomic(state_dir / "baseline.json", baseline)
        with self.assertRaises(self.m.Stop) as cm:
            self.m.install_target(
                self.game,
                self._sm86_payload(),
                {"name": "fixture.zip", "sha256": "9" * 64, "known_tag": "fixture"},
                "sm86",
            )
        self.assertIn("destructive cleanup is still pending", str(cm.exception))
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.assertFalse((self.target / "dxgi.dll").exists())

    def test_install_refuses_live_game_before_baseline_or_file_mutation(self):
        self.game.dlss = True
        self.game.dlssg = True
        archive_meta = {"name": "fixture.zip", "sha256": "a" * 64, "known_tag": "fixture"}
        old_running = self.m._running_processes_under_root
        self.m._running_processes_under_root = lambda root: ["999/wine64 [cwd]"]
        try:
            with self.assertRaises(self.m.Stop) as cm:
                self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        finally:
            self.m._running_processes_under_root = old_running
        self.assertIn("Game process still using", str(cm.exception))
        self.assertFalse(self.m.baseline_path(self.target).exists())
        self.assertFalse((self.target / "dxgi.dll").exists())

    def test_batch_uninstall_marks_all_baselines_recovery_before_steam_metadata_restore(self):
        self.game.dlss = True
        self.game.dlssg = True
        self.game.installed = True
        self.game.reason = "INSTALLED"
        first_meta = {"name": "fixture.zip", "sha256": "4" * 64, "known_tag": "fixture"}
        self.m.install_target(self.game, self._sm86_payload(), first_meta, "sm86")

        target2 = self.drive / "SteamLibrary" / "steamapps" / "common" / "Fixture2" / "Binaries" / "Win64"
        target2.mkdir(parents=True)
        exe2 = target2 / "game2.exe"
        exe2.write_bytes(b"MZfixture2")
        game2 = self.m.Game("B", "Fixture2", target2.parents[2], "Steam", "456", None, exe2, target2)
        game2.dlss = True
        game2.dlssg = True
        game2.installed = True
        game2.reason = "INSTALLED"
        self.m.install_target(game2, self._sm86_payload(), first_meta, "sm86")

        observed = {"checked": False}
        old_restore = self.m.restore_launch_options_batch
        def inspect_then_stop(games, assume_yes=False):
            states = [self.m.load_baseline(g.target_dir) for g in games]
            self.assertTrue(all(state["status"] == "restore-pending" for state in states))
            batch_ids = {state["restore_pending"].get("batch_id") for state in states}
            self.assertEqual(len(batch_ids), 1)
            self.assertNotIn(None, batch_ids)
            observed["checked"] = True
            raise self.m.Stop("simulated metadata-stage stop")
        self.m.restore_launch_options_batch = inspect_then_stop
        try:
            with self.assertRaises(self.m.Stop):
                self.m.batch_uninstall([self.game, game2], self.drive, assume_yes=True)
        finally:
            self.m.restore_launch_options_batch = old_restore
        self.assertTrue(observed["checked"])
        self.assertTrue((self.target / "dxgi.dll").is_file())
        self.assertTrue((target2 / "dxgi.dll").is_file())
        self.assertEqual(self.m.load_baseline(self.target)["status"], "restore-pending")
        self.assertEqual(self.m.load_baseline(target2)["status"], "restore-pending")

    def test_batch_uninstall_refuses_live_game_before_steam_metadata_restore(self):
        self.game.installed = True
        self.game.reason = "INSTALLED"
        touched = {"steam_restore": False}
        old_running = self.m._running_processes_under_root
        old_restore = self.m.restore_launch_options_batch
        self.m._running_processes_under_root = lambda root: ["999/wine64 [cwd]"]
        self.m.restore_launch_options_batch = lambda *args, **kwargs: touched.__setitem__("steam_restore", True)
        try:
            with self.assertRaises(self.m.Stop) as cm:
                self.m.batch_uninstall([self.game], self.drive, assume_yes=True)
        finally:
            self.m._running_processes_under_root = old_running
            self.m.restore_launch_options_batch = old_restore
        self.assertIn("Game process still using", str(cm.exception))
        self.assertFalse(touched["steam_restore"])

    def test_batch_uninstall_aborts_before_game_mutation_when_steam_restore_fails(self):
        self.game.installed = True
        self.game.reason = "INSTALLED"
        self._baseline()
        sentinel = self.target / "managed-sentinel.dll"
        sentinel.write_bytes(b"must survive")
        touched = {"restore_target": False}
        self.m.restore_launch_options_batch = lambda *a, **k: (_ for _ in ()).throw(self.m.Stop("simulated Steam restore failure"))
        def should_not_run(game):
            touched["restore_target"] = True
            sentinel.unlink(missing_ok=True)
            return {"target": str(self.target)}
        self.m.restore_target = should_not_run

        with self.assertRaises(self.m.Stop) as cm:
            self.m.batch_uninstall([self.game], self.drive, assume_yes=True)
        self.assertIn("no game files were removed", str(cm.exception))
        self.assertFalse(touched["restore_target"])
        self.assertEqual(sentinel.read_bytes(), b"must survive")
        self.assertEqual(self.m.load_baseline(self.target)["status"], "restore-pending")

    def test_batch_uninstall_partial_file_failure_is_retryable_and_does_not_resurrect_completed_game(self):
        meta = {"name": "fixture.zip", "sha256": "b" * 64, "known_tag": "fixture"}
        self.game.dlss = True
        self.game.dlssg = True
        self.game.installed = True
        self.game.reason = "INSTALLED"
        self.m.install_target(self.game, self._sm86_payload(), meta, "sm86")

        target2 = self.drive / "SteamLibrary" / "steamapps" / "common" / "Fixture2" / "Binaries" / "Win64"
        target2.mkdir(parents=True)
        exe2 = target2 / "game2.exe"
        exe2.write_bytes(b"MZfixture2")
        game2 = self.m.Game(
            "B", "Fixture2", target2.parents[2], "Steam", "456", None,
            exe2, target2, installed=True, reason="INSTALLED",
        )
        game2.dlss = True
        game2.dlssg = True
        self.m.install_target(game2, self._sm86_payload(), meta, "sm86")

        # Metadata restoration is intentionally treated as already successful;
        # this fixture isolates the per-game file phase and its retry semantics.
        self.m.restore_launch_options_batch = lambda *a, **k: []
        self.m.write_batch_report = lambda *a, **k: self.base / "batch.md"
        real_restore = self.m.restore_target
        failed_once = {"value": False}

        def fail_second_once(game):
            if game.name == "Fixture2" and not failed_once["value"]:
                failed_once["value"] = True
                raise OSError("simulated second-game restore failure")
            return real_restore(game)

        self.m.restore_target = fail_second_once
        self.m.batch_uninstall([self.game, game2], self.drive, assume_yes=True)

        # The first game is durably retired. The failed second game remains an
        # active managed install and still has its payload for a later retry.
        self.assertIsNone(self.m.load_baseline(self.target))
        self.assertFalse((self.target / "dxgi.dll").exists())
        self.assertIsNotNone(self.m.load_baseline(target2))
        self.assertTrue((target2 / "dxgi.dll").is_file())

        # Retry only the failed game. Already-restored Steam metadata is
        # idempotent/no-op here, and the completed first game stays retired.
        self.m.restore_target = real_restore
        self.m.batch_uninstall([game2], self.drive, assume_yes=True)
        self.assertIsNone(self.m.load_baseline(target2))
        self.assertFalse((target2 / "dxgi.dll").exists())
        self.assertIsNone(self.m.load_baseline(self.target))


    def test_fresh_install_does_not_overwrite_unknown_dxgi_and_falls_back_to_version(self):
        self.game.dlss = True
        self.game.dlssg = True
        original = b"game-owned-unknown-dxgi"
        write_minimal_pe(self.exe, ["version.dll"])
        (self.target / "dxgi.dll").write_bytes(original)
        archive_meta = {"name": "fixture.zip", "sha256": "8" * 64, "known_tag": "fixture"}

        row = self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertEqual(row["proxy"], "version.dll")
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), original)
        self.assertTrue((self.target / "version.dll").is_file())

        self.m.restore_target(self.game)
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), original)
        self.assertFalse((self.target / "version.dll").exists())

    def test_fresh_install_refuses_when_both_validated_optiscaler_proxies_are_unknown_owned(self):
        self.game.dlss = True
        self.game.dlssg = True
        (self.target / "dxgi.dll").write_bytes(b"game-owned-dxgi")
        (self.target / "version.dll").write_bytes(b"game-owned-version")
        archive_meta = {"name": "fixture.zip", "sha256": "9" * 64, "known_tag": "fixture"}

        with self.assertRaises(self.m.Stop) as cm:
            self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertIn("No safe OptiScaler proxy", str(cm.exception))
        self.assertFalse(self.m.baseline_path(self.target).exists())
        self.assertEqual((self.target / "dxgi.dll").read_bytes(), b"game-owned-dxgi")
        self.assertEqual((self.target / "version.dll").read_bytes(), b"game-owned-version")


    def test_fresh_install_refuses_unproven_version_fallback_when_dxgi_is_unknown_owned(self):
        self.game.dlss = True
        self.game.dlssg = True
        (self.target / "dxgi.dll").write_bytes(b"game-owned-dxgi")
        archive_meta = {"name": "fixture.zip", "sha256": "0" * 64, "known_tag": "fixture"}
        with self.assertRaises(self.m.Stop) as cm:
            self.m.install_target(self.game, self._sm86_payload(), archive_meta, "sm86")
        self.assertIn("No safe OptiScaler proxy", str(cm.exception))
        self.assertFalse((self.target / "version.dll").exists())
        self.assertFalse(self.m.baseline_path(self.target).exists())




    def test_game_file_scanner_prunes_nested_mounts_symlinks_and_special_evidence(self):
        root = self.base / "scan-root"
        root.mkdir()
        normal = root / "game.exe"
        normal.write_bytes(b"MZ")
        mounted = root / "Mounted"
        mounted.mkdir()
        mounted_evidence = mounted / "nvngx_dlss.dll"
        mounted_evidence.write_bytes(b"outside-ish")
        external = self.base / "external-nvngx_dlssg.dll"
        external.write_bytes(b"external")
        link = root / "nvngx_dlssg.dll"
        link.symlink_to(external)

        old_mount = self.m._path_is_mount
        self.m._path_is_mount = lambda path: Path(path).name == "Mounted"
        try:
            found = list(self.m.iter_game_files(root))
        finally:
            self.m._path_is_mount = old_mount

        self.assertIn(normal, found)
        self.assertNotIn(mounted_evidence, found)
        self.assertNotIn(link, found)

    def test_discovery_skips_manifest_installdir_that_escapes_common(self):
        drive = self.base / "DiscoverDrive"
        steamapps = drive / "SteamLibrary" / "steamapps"
        common = steamapps / "common"
        common.mkdir(parents=True)
        escaped = steamapps / "Escape"
        escaped.mkdir()
        (escaped / "game.exe").write_bytes(b"MZ")
        (escaped / "nvngx_dlss.dll").write_bytes(b"dlss")
        (escaped / "nvngx_dlssg.dll").write_bytes(b"dlssg")
        manifest = steamapps / "appmanifest_123.acf"
        manifest.write_text(
            '"AppState"\n{\n"appid" "123"\n"name" "Escaped Fixture"\n"installdir" "../Escape"\n}\n',
            encoding="utf-8",
        )

        games = self.m.discover_games(drive)
        self.assertFalse(any(g.appid == "123" for g in games))

    def test_default_y4my_archive_selection_ignores_unpinned_candidate(self):
        self.m.DEFAULT_DOWNLOAD_DIR = self.base / "Downloads" / "Compressed"
        self.m.Y4MY_CACHE_DIR = self.base / "cache" / "y4my-v4"
        self.m.DEFAULT_DOWNLOAD_DIR.mkdir(parents=True)
        self.m.Y4MY_CACHE_DIR.mkdir(parents=True)
        name = self.m.Y4MY_PROVIDER["archive"]
        bad = self.m.DEFAULT_DOWNLOAD_DIR / name
        good = self.m.Y4MY_CACHE_DIR / name
        bad.write_bytes(b"newer-but-untrusted-provider-bytes")
        good.write_bytes(b"known-good-provider-bytes")
        digest = hashlib.sha256(good.read_bytes()).hexdigest()
        self.m.Y4MY_PROVIDER["sha256"] = digest
        os.utime(good, ns=(1_000_000_000, 1_000_000_000))
        os.utime(bad, ns=(2_000_000_000, 2_000_000_000))
        self.assertEqual(self.m.find_default_archive(), good.resolve())
        self.assertEqual(self.m.choose_archive(), good.resolve())

    def test_rtxmfg_local_discovery_skips_bad_download_and_uses_valid_cache(self):
        source = self.base / "source-valid.zip"
        digest = self._write_rtxmfg_zip(source)
        self.m.DEFAULT_DOWNLOAD_DIR = self.base / "Downloads" / "Compressed"
        self.m.RTXMFG_CACHE_DIR = self.base / "cache"
        self.m.RTXMFG_PROVIDER = {
            "version": "fixture", "archive": "RTXMFG-fixture.zip",
            "sha256": digest, "url": "https://example.invalid/RTXMFG-fixture.zip",
        }
        self.m.DEFAULT_DOWNLOAD_DIR.mkdir(parents=True)
        bad = self.m.DEFAULT_DOWNLOAD_DIR / "RTXMFG-fixture.zip"
        bad.write_bytes(b"stale corrupt archive")
        self.m.RTXMFG_CACHE_DIR.mkdir(parents=True)
        good = self.m.RTXMFG_CACHE_DIR / "RTXMFG-fixture.zip"
        good.write_bytes(source.read_bytes())

        found = self.m.find_local_rtxmfg_archive()
        self.assertEqual(found, good.resolve())
        self.assertEqual(self.m.ensure_rtxmfg_archive(allow_download=False), good.resolve())

    def test_refresh_backup_writers_refuse_nested_backup_symlink_pivots(self):
        for child, operation in (("files", "extend"), ("external-adopted", "adopt")):
            with self.subTest(child=child):
                # Use a fresh target per subtest so state from one case cannot
                # influence the other.
                target = self.drive / f"Nested-{child}" / "Binaries" / "Win64"
                target.mkdir(parents=True)
                exe = target / "game.exe"
                exe.write_bytes(b"MZ")
                baseline = {
                    "schema": 13, "status": "active", "created_utc": self.m.now_iso(),
                    "name": child, "source": "Steam", "appid": "999",
                    "exe": str(exe), "target_dir": str(target),
                    "originals": {"dxgi.dll": {"kind": "file", "existed": False}},
                    "managed_paths": ["dxgi.dll"], "history": [],
                    "current": {"installed_hashes": {}},
                }
                state = self.m._validated_state_dir(target)
                state.mkdir(parents=True)
                self.m.save_json_atomic(self.m.baseline_path(target), baseline)
                backup_root = state / "baseline-backup"
                backup_root.mkdir()
                outside = self.base / f"outside-{child}"
                outside.mkdir()
                (backup_root / child).symlink_to(outside, target_is_directory=True)

                if operation == "extend":
                    live = target / "version.dll"
                    live.write_bytes(b"external-version")
                    call = lambda: self.m.extend_baseline_for_new_paths(baseline, target, {"version.dll"})
                else:
                    live = target / "dxgi.dll"
                    live.write_bytes(b"external-dxgi")
                    call = lambda: self.m.adopt_external_file_as_original(baseline, target, "dxgi.dll")

                with self.assertRaises(self.m.Stop) as cm:
                    call()
                self.assertIn("symlink", str(cm.exception).lower())
                self.assertEqual(list(outside.iterdir()), [])
                self.assertTrue(live.is_file())

    def test_refresh_backup_writer_refuses_baseline_backup_root_symlink_pivot(self):
        baseline = self._baseline()
        state = self.m._validated_state_dir(self.target, require_exists=True)
        outside = self.base / "outside-refresh-backup"
        outside.mkdir()
        backup_root = state / "baseline-backup"
        backup_root.symlink_to(outside, target_is_directory=True)
        external = self.target / "version.dll"
        external.write_bytes(b"external-version")

        with self.assertRaises(self.m.Stop) as cm:
            self.m.extend_baseline_for_new_paths(baseline, self.target, {"version.dll"})
        self.assertIn("Baseline backup root symlink refused", str(cm.exception))
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(external.read_bytes(), b"external-version")



if __name__ == "__main__":
    unittest.main(verbosity=2)
