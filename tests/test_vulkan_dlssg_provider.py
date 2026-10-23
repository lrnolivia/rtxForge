"""Real-filesystem lifecycle/failure fixtures; no game or driver is required."""
import copy
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import vulkan_dlssg_provider as v


def pe(tail=b''):
    data = bytearray(128)
    data[:2] = b'MZ'; struct.pack_into('<I', data, 60, 64)
    data[64:70] = b'PE\0\0d\x86'
    return bytes(data) + tail


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.game = self.base / 'BG3/bin'; self.game.mkdir(parents=True)
        self.state = self.base / 'state'
        (self.game / 'bg3.exe').write_bytes(pe(b'game'))
        (self.game / 'nvngx_dlss.dll').write_bytes(pe(b'SR'))
        (self.game / v.PROXY).write_bytes(pe(b'original Bink'))
        (self.game / 'README.md').write_text('game-owned readme')
        (self.game / 'NativeMods').mkdir()
        (self.game / 'NativeMods/Unrelated.dll').write_bytes(b'other mod')
        (self.game / 'sl.log').write_bytes(b'old log\r\n')
        self.original = self.files()
        self.spec = copy.deepcopy(v.pin())
        self.members = {name: pe(name.encode()) if name.endswith('.dll') else name.encode()
                        for name in self.spec['files']}
        self.archive = self.base / 'package.zip'
        self.loader = self.base / 'bink2w64.dll'; self.loader.write_bytes(pe(b'our loader'))
        self.pin_path = self.base / 'provider/source.json'
        self.pin_path.parent.mkdir()
        (self.pin_path.parent / 'loader').mkdir()
        notice = (v.PIN.parent / 'loader/LICENSE.exports.txt').read_bytes()
        (self.pin_path.parent / 'loader/LICENSE.exports.txt').write_bytes(notice)
        self.spec['loader']['binary'] = {'size': self.loader.stat().st_size, 'sha256': v._digest(self.loader)}
        self.spec['loader']['game_original'] = {'size': (self.game / v.PROXY).stat().st_size,
                                               'sha256': v._digest(self.game / v.PROXY)}
        self.repack()
        self.pin_patch = patch.object(v, 'PIN', self.pin_path); self.pin_patch.start()
        self.addCleanup(self.pin_patch.stop)
        self.running = patch.object(v, 'running', return_value=False); self.running.start()
        self.addCleanup(self.running.stop)

    def files(self):
        return {p.relative_to(self.game).as_posix(): p.read_bytes() for p in self.game.rglob('*') if p.is_file()}

    def repack(self, names=None, symlink=None):
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for name, raw in self.members.items():
                member = zipfile.ZipInfo((names or {}).get(name, name.replace('/', '\\')))
                if name == symlink:
                    member.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(member, raw)
        self.spec['files'] = {name: {'size': len(raw), 'sha256': v._hash(raw)} for name, raw in self.members.items()}
        self.spec['archive'].update(size=self.archive.stat().st_size, sha256=v._digest(self.archive))
        self.pin_path.write_text(json.dumps(self.spec))

    def plan(self):
        return v.plan_install(self.game, self.archive, self.loader, self.state, experimental=True)

    def install(self):
        return v.execute(self.plan())

    def restore(self):
        return v.execute(v.plan_restore(self.game, self.state))

    def test_complete_roundtrip_and_namespace(self):
        plan = self.plan()
        self.assertEqual(self.original, self.files())
        result = v.execute(plan)
        self.assertEqual(result['status'], 'active')
        self.assertEqual((self.game / v.PROXY).read_bytes(), self.loader.read_bytes())
        self.assertEqual((self.game / v.ORIGINAL).read_bytes(), self.original[v.PROXY])
        self.assertIn(b'DLSSGFrames=1', (self.game / v.CONFIG).read_bytes())
        self.assertEqual((self.game / 'README.md').read_bytes(), self.original['README.md'])
        self.assertFalse(result['runtime_verified'])
        self.restore()
        self.assertEqual(self.original, self.files())
        self.assertFalse((self.game / 'NativeMods/Streamline').exists())

    def test_optin_required(self):
        with self.assertRaisesRegex(v.t.Refusal, 'Experimental'):
            v.plan_install(self.game, self.archive, self.loader, self.state)

    def test_unknown_loader_refused(self):
        (self.game / v.PROXY).write_bytes(pe(b'foreign loader'))
        with self.assertRaisesRegex(v.t.Refusal, 'Unknown Bink'):
            self.plan()

    def test_orphan_original_refused(self):
        (self.game / v.ORIGINAL).write_bytes(self.original[v.PROXY])
        with self.assertRaisesRegex(v.t.Refusal, 'Unmanaged'):
            self.plan()

    def test_unmanaged_ini_refused(self):
        (self.game / v.CONFIG).write_text('[fgvk]\nDLSSGFrames=3\n')
        with self.assertRaisesRegex(v.t.Refusal, 'Unmanaged'):
            self.plan()

    def test_root_interposer_refused(self):
        (self.game / 'sl.interposer.dll').write_bytes(b'foreign')
        with self.assertRaisesRegex(v.t.Refusal, 'coexistence'):
            self.plan()

    def test_running_game_preflight(self):
        with patch.object(v, 'running', return_value=True):
            with self.assertRaisesRegex(v.t.Refusal, 'Close ' + v._game_name()):
                self.plan()

    def test_started_after_review(self):
        plan = self.plan()
        with patch.object(v, 'running', return_value=True):
            with self.assertRaisesRegex(v.t.Refusal, 'Close ' + v._game_name()):
                v.execute(plan)
        self.assertEqual(self.original, self.files())

    def test_payload_drift_after_review(self):
        plan = self.plan(); self.loader.write_bytes(b'drift')
        with self.assertRaisesRegex(v.t.Refusal, 'Payload changed'):
            v.execute(plan)
        self.assertEqual(self.original, self.files())

    def test_target_drift_after_review(self):
        plan = self.plan(); (self.game / v.PROXY).write_bytes(b'drift')
        with self.assertRaisesRegex(v.t.Refusal, 'changed after review'):
            v.execute(plan)

    def test_review_tamper(self):
        plan = self.plan(); plan['target'] = str(self.base)
        with self.assertRaisesRegex(v.t.Refusal, 'integrity'):
            v.execute(plan)

    def test_game_update_after_review(self):
        plan = self.plan(); (self.game / v._executables()[0]).write_bytes(pe(b'updated game'))
        with self.assertRaisesRegex(v.t.Refusal, 'Payload changed'):
            v.execute(plan)

    @unittest.skipIf(os.name == 'nt', 'POSIX mode bits are not a Windows permission contract')
    def test_original_permissions_restored(self):
        (self.game / v.PROXY).chmod(0o640)
        self.install(); self.restore()
        self.assertEqual(stat.S_IMODE((self.game / v.PROXY).stat().st_mode), 0o640)

    def test_cancelled_install_can_restore(self):
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls == 3
        with self.assertRaises(v.Cancelled):
            v.execute(self.plan(), cancelled=cancelled)
        self.assertEqual(v._record(self.game, v.state_path(self.game, self.state))['status'], 'interrupted')
        self.restore()
        self.assertEqual(self.original, self.files())

    def test_write_failure_can_restore(self):
        original_atomic = v.t.atomic_file
        count = 0
        def fail(path, data, mode):
            nonlocal count
            if Path(path).is_relative_to(self.game):
                count += 1
                if count == 4:
                    raise OSError('simulated disk fault')
            return original_atomic(path, data, mode)
        with patch.object(v.t, 'atomic_file', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'disk fault'):
                self.install()
        self.restore()
        self.assertEqual(self.original, self.files())

    def test_cancelled_restore_is_resumable(self):
        self.install()
        count = 0
        def cancelled():
            nonlocal count
            count += 1
            return count == 4
        with self.assertRaises(v.Cancelled):
            v.execute(v.plan_restore(self.game, self.state), cancelled=cancelled)
        self.restore()
        self.assertEqual(self.original, self.files())

    def test_repair_missing_file_preserves_config_and_logs(self):
        self.install()
        (self.game / 'NativeMods/fgvk.dll').unlink()
        custom = b'[fgvk]\nConfigVersion=2\nDLSSGFrames=2\n'
        (self.game / v.CONFIG).write_bytes(custom)
        (self.game / 'fgvk.log').write_bytes(b'game log')
        plan = self.plan(); self.assertEqual(plan['operation'], 'repair')
        v.execute(plan)
        self.assertEqual((self.game / v.CONFIG).read_bytes(), custom)
        self.assertEqual((self.game / 'fgvk.log').read_bytes(), b'game log')
        self.assertTrue((self.game / 'NativeMods/fgvk.dll').exists())
        self.restore(); self.assertEqual(self.original, self.files())

    def test_changed_immutable_file_blocks_both_operations(self):
        self.install()
        (self.game / 'NativeMods/fgvk.dll').write_bytes(b'user changed DLL')
        before = self.files()
        for operation in (self.plan, lambda: v.plan_restore(self.game, self.state)):
            with self.assertRaisesRegex(v.t.Refusal, 'changed'):
                operation()
        self.assertEqual(before, self.files())

    def test_runtime_files_preserved_in_external_objects(self):
        self.install()
        (self.game / 'fgvk.log').write_bytes(b'new diagnostic evidence')
        (self.game / 'sl.log').write_bytes(b'new Streamline log')
        self.restore()
        record = v._record(self.game, v.state_path(self.game, self.state))
        evidence = {item['path']: item['sha256'] for item in record['observed_runtime']}
        self.assertEqual(evidence['fgvk.log'], v._hash(b'new diagnostic evidence'))
        self.assertEqual(self.original, self.files())

    def test_damaged_backup_blocks_restore(self):
        self.install()
        state = v.state_path(self.game, self.state)
        record = v._record(self.game, state)
        (state / 'objects' / record['originals'][v.PROXY]['sha256']).write_bytes(b'damaged')
        with self.assertRaisesRegex(v.t.Refusal, 'damaged'):
            v.plan_restore(self.game, self.state)

    def test_concurrent_operation_lock(self):
        plan = self.plan()
        with v._lock(v.state_path(self.game, self.state)):
            with self.assertRaisesRegex(v.t.Refusal, 'Another'):
                v.execute(plan)
        self.assertEqual(self.original, self.files())

    def test_state_cannot_overlap_game(self):
        with self.assertRaisesRegex(v.t.Refusal, 'outside'):
            v.plan_install(self.game, self.archive, self.loader, self.game / 'backup', experimental=True)

    def test_reinstall_after_exact_restore(self):
        self.install(); self.restore(); self.install(); self.restore()
        self.assertEqual(self.original, self.files())

    def test_double_restore_refused(self):
        self.install(); self.restore()
        with self.assertRaisesRegex(v.t.Refusal, 'No active'):
            v.plan_restore(self.game, self.state)

    def test_mixed_private_runtime_refused(self):
        self.install()
        (self.game / 'NativeMods/Streamline/unknown.dll').write_bytes(b'extra')
        with self.assertRaisesRegex(v.t.Refusal, 'Mixed'):
            self.plan()

    def test_archive_traversal_even_when_outer_hash_matches(self):
        name = next(iter(self.members))
        self.repack({name: '../fgvk.dll'})
        with self.assertRaises(v.t.Refusal):
            self.plan()

    def test_archive_symlink_even_when_outer_hash_matches(self):
        self.repack(symlink=next(iter(self.members)))
        with self.assertRaisesRegex(v.t.Refusal, 'links'):
            self.plan()

    def test_archive_member_digest_is_checked(self):
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for name, raw in self.members.items():
                archive.writestr(name, raw if name != 'README.md' else b'corruption')
        self.spec['archive'].update(size=self.archive.stat().st_size, sha256=v._digest(self.archive))
        self.pin_path.write_text(json.dumps(self.spec))
        with self.assertRaises(v.t.Refusal):
            self.plan()

    def test_missing_proxy_restores_original(self):
        self.install(); (self.game / v.PROXY).unlink(); self.restore()
        self.assertEqual(self.original, self.files())

    def test_diagnostics_require_displayed_frame_evidence(self):
        (self.game / 'fgvk.log').write_text('gate: 60 consecutive DLSS-SR frames -> DLSS-G ON\n'
            'FG inputs submitted ok\nFG stats: 300 presents -> 600 frames displayed (x2.00) status=0\n')
        report = v.diagnose(self.game)
        self.assertTrue(report['inputs_submitted'])
        self.assertEqual(report['stats'][0]['ratio'], 2.0)
        self.assertFalse(report['runtime_verified'])


class SharedBg3Tests(ProviderTests):
    profile_name = 'bg3'

    def setUp(self):
        super().setUp()
        self.spec['id'] = 'rtxforge-vulkan-native'
        self.spec['deployable'] = True
        self.spec['experimental'] = True
        self.spec['runtime_verified'] = False
        self.spec['default_promoted'] = False
        self.spec['profiles'] = {
            'bg3': {'executable': 'bg3.exe', 'loader': copy.deepcopy(self.spec['loader'])},
            'rdr2': {'executable': 'RDR2.exe', 'loader': copy.deepcopy(self.spec['loader'])},
        }
        if self.profile_name == 'rdr2':
            (self.game / 'bg3.exe').rename(self.game / 'RDR2.exe')
        self.original = self.files()
        self.members['NativeMods/nvngx_dlssnr.dll'] = pe(b'user supplied NR model')
        self.members['NativeMods/nvngx.dll_dlssnr.dll'] = pe(b'NR forwarder')
        self.members['NativeMods/MFG/MFGUnlocker.dll'] = pe(b'Universal MFG')
        self.members['NativeMods/MFG/RTXMFG-Universal.json'] = b'{"followGame":true}\n'
        self.members['RTX40MFG-UI.ini'] = b'[Overlay]\nFirstLaunchMenuShown=1\n'
        self.repack()
        selection = v.profile(self.profile_name, self.pin_path)
        selection.__enter__()
        self.addCleanup(selection.__exit__, None, None, None)

    def test_profile_change_after_review_is_refused(self):
        plan = self.plan()
        other = 'bg3' if self.profile_name == 'rdr2' else 'rdr2'
        with v.profile(other, self.pin_path):
            with self.assertRaisesRegex(v.t.Refusal, 'profile differs'):
                v.execute(plan)
        self.assertEqual(self.original, self.files())

    def test_nr_model_drift_blocks_restore(self):
        self.install()
        (self.game / 'NativeMods/nvngx_dlssnr.dll').write_bytes(b'changed NR model')
        with self.assertRaisesRegex(v.t.Refusal, 'changed'):
            v.plan_restore(self.game, self.state)

    def test_shared_defaults_enable_native_nr(self):
        self.install()
        ini = (self.game / v.CONFIG).read_bytes()
        self.assertIn(b'[nr]\nEnabled=1', ini)
        self.assertIn(b'ReflexSleep=0' if self.profile_name == 'rdr2' else b'ReflexSleep=1', ini)
        self.assertEqual(v._record(self.game, v.state_path(self.game, self.state))['provider_id'],
                         'rtxforge-vulkan-native:' + self.profile_name)

    def test_mfg_preferences_survive_repair_and_restore_as_evidence(self):
        self.install()
        changes = {'NativeMods/MFG/RTXMFG-Universal.json': b'{"followGame":false,"multiplier":4}\n',
                   'RTX40MFG-UI.ini': b'[Overlay]\nFirstLaunchMenuShown=1\nLanguage=en\n'}
        for name, raw in changes.items():
            (self.game / name).write_bytes(raw)
        (self.game / 'NativeMods/fgvk.dll').unlink()
        v.execute(self.plan())
        for name, raw in changes.items():
            self.assertEqual((self.game / name).read_bytes(), raw)
        self.restore()
        self.assertEqual(self.original, self.files())
        record = v._record(self.game, v.state_path(self.game, self.state))
        evidence = {item['path']: item['sha256'] for item in record['observed_runtime']}
        for name, raw in changes.items():
            self.assertEqual(evidence[name], v._hash(raw))

    def test_restored_candidate_can_change_inventory_without_losing_evidence(self):
        self.install()
        setting = b'[nr]\nEnabled=0\n'
        (self.game / v.CONFIG).write_bytes(setting)
        self.restore()
        state = v.state_path(self.game, self.state)
        previous = (state / 'baseline.json').read_bytes()
        self.members['NativeMods/rtxForge-vulkan/new-notice.txt'] = b'new pinned notice\n'
        self.repack()
        v.execute(self.plan())
        record = v._record(self.game, state)
        self.assertEqual(record['prior_record_sha256'], v._hash(previous))
        archived = json.loads((state / 'objects' / record['prior_record_sha256']).read_bytes())
        evidence = {item['path']: item['sha256'] for item in archived['observed_runtime']}
        self.assertEqual((state / 'objects' / evidence[v.CONFIG]).read_bytes(), setting)
        self.restore()
        self.assertEqual(self.original, self.files())

    def test_active_candidate_inventory_change_is_refused(self):
        self.install()
        self.members['NativeMods/rtxForge-vulkan/new-notice.txt'] = b'new pinned notice\n'
        self.repack()
        with self.assertRaisesRegex(v.t.Refusal, 'inventory differs'):
            self.plan()

    def test_changed_old_inventory_is_not_abandoned_after_restore(self):
        extra = 'NativeMods/rtxForge-vulkan/old-notice.txt'
        self.members[extra] = b'old pinned notice\n'
        self.repack()
        self.install()
        self.restore()
        (self.game / extra).parent.mkdir(parents=True, exist_ok=True)
        (self.game / extra).write_bytes(b'concurrent file\n')
        del self.members[extra]
        self.repack()
        with self.assertRaisesRegex(v.t.Refusal, 'Restored inventory changed'):
            self.plan()
        self.assertEqual((self.game / extra).read_bytes(), b'concurrent file\n')


class SharedRdr2Tests(SharedBg3Tests):
    profile_name = 'rdr2'


if __name__ == '__main__':
    unittest.main()
