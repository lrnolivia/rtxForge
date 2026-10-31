"""HDR matching, exact downloads and reversible composition with NR/MFG."""
import contextlib
import copy
import json
import os
import shutil
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import renodx_hdr as hdr
import transactions as t


def pe(machine=b'd\x86'):
    data = bytearray(256); data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64); data[64:70] = b'PE\0\0' + machine
    return bytes(data)


class Engine:
    def __init__(self):
        self.running = False; self.baseline = None; self.imports = {'d3d11.dll'}
    def _running_processes_under_root(self, root): return ['Game'] if self.running else []
    def load_baseline(self, path, **kwargs): return self.baseline
    def pe_imported_dlls(self, path): return self.imports
    def mutation_lock(self): return contextlib.nullcontext()


class HdrTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.game = self.root / 'game'; self.game.mkdir()
        self.state = self.root / 'state'; self.state.mkdir()
        (self.game / 'Game.exe').write_bytes(pe()); (self.game / 'save.dat').write_bytes(b'save')
        self.row = {'name': 'A Game', 'game': str(self.game), 'exe': 'Game.exe', 'appid': '123', 'source': 'Steam'}
        self.engine = Engine(); self.addon = pe() + b'HDR'; self.host = pe() + b'ReShade addon'
        self.pin = {'id': 42, 'size': len(self.addon), 'sha256': t.sha(self.addon)}
        self.catalog = {'schema': 1, 'source_commit': 'a'*40, 'assets': {'renodx-game.addon64': self.pin},
                        'games': [{'title': 'A Game', 'steam_appid': 123, 'aliases': [], 'mods': [{
                            'id': 'game', 'category': 'game', 'compatibility': 'working', 'notes': [], 'deploy': {},
                            'artifacts': [{'name': 'renodx-game.addon64', 'arch': 'x64'}]}]}]}
        for target, name, value in [
            (hdr, 'catalog', lambda: copy.deepcopy(self.catalog)),
            (hdr.engine_bridge, 'module', lambda config: self.engine),
            (hdr.state_storage, 'storage', lambda config, required=0: self.state),
            (hdr, '_fetch', lambda *args: {'renodx-game.addon64': self.addon, 'ReShade64.dll': self.host}),
            (hdr, 'HOSTS', {'x64': ('ReShade64.dll', t.sha(self.host), len(self.host))}),
            (hdr, 'WINDOWS', True),
        ]:
            p = patch.object(target, name, value); p.start(); self.addCleanup(p.stop)
        if os.name == 'nt':
            # Session's native Linux copy operation, adapted to fixture files on Windows.
            import operation_session
            def copy_files(args, **kwargs):
                self.assertEqual(args[:4], ['cp', '-a', '--reflink=auto', '--'])
                shutil.copy2(args[4], args[5])
            p = patch.object(operation_session.subprocess, 'run', side_effect=copy_files)
            p.start(); self.addCleanup(p.stop)

    def optiscaler(self, text='[Plugins]\nLoadReShade=false\n[DlssNr]\nEnabled=true\n'):
        proxy = self.game / 'dxgi.dll'; proxy.write_bytes(pe() + b'OptiScaler')
        (self.game / 'OptiScaler.ini').write_text(text, encoding='utf-8')
        self.engine.baseline = {'status': 'active', 'managed_paths': ['dxgi.dll', 'OptiScaler.ini'],
                                'current': {'provider_id': 'skynizz', 'proxy': 'dxgi.dll', 'installed_hashes': {'dxgi.dll': t.digest(proxy)}}}

    def test_exact_id_and_alias_matching_never_fuzzy(self):
        row = dict(self.row, name='Something else')
        self.assertEqual(hdr.match(row, 'x64')['name'], 'renodx-game.addon64')
        with self.assertRaises(t.Refusal): hdr.match(dict(self.row, appid='999'), 'x64')
        self.assertEqual(hdr.match(dict(self.row, appid='', name='A GAME™'), 'x64')['title'], 'A Game')
        with self.assertRaises(t.Refusal): hdr.match(dict(self.row, appid='', name='A Game sequel'), 'x64')

    def test_ambiguity_external_only_and_wrong_arch_do_not_guess(self):
        with self.assertRaises(t.Refusal): hdr.match(self.row, 'x86')
        mod = self.catalog['games'][0]['mods'][0]
        second = copy.deepcopy(mod); second['artifacts'][0]['name'] = 'renodx-other.addon64'
        self.catalog['assets']['renodx-other.addon64'] = self.pin
        self.catalog['games'][0]['mods'].append(second)
        with self.assertRaisesRegex(t.Refusal, 'Several'): hdr.match(self.row, 'x64')
        self.catalog['games'][0]['mods'] = [dict(mod, artifacts=[])]
        self.assertFalse(hdr.status({}, self.row)['available'])

    def steam_subgame(self):
        steamapps = self.root / 'steamapps'; game = steamapps / 'common' / 'Trilogy' / 'Game' / 'Part2'
        game.mkdir(parents=True); (game / 'Game.exe').write_bytes(pe())
        manifest = steamapps / 'appmanifest_123.acf'
        manifest.write_text('"AppState" { "appid" "123" "installdir" "Trilogy" }', encoding='utf-8')
        return dict(self.row, game=str(game), name='Trilogy · Part 2', appid=None), manifest

    def test_nested_subgame_uses_exact_steam_manifest_and_freezes_identity(self):
        row, manifest = self.steam_subgame()
        self.assertEqual(hdr.match(row, 'x64')['title'], 'A Game')
        plan = hdr.prepare({}, row)
        self.assertEqual(plan['steam_identity']['appid'], '123')
        manifest.write_text('"AppState" { "appid" "123" "installdir" "Another game" }', encoding='utf-8')
        with self.assertRaisesRegex(t.Refusal, 'identity changed'): hdr.apply({}, plan)
        self.assertFalse((Path(row['game']) / 'dxgi.dll').exists())

    def test_manifest_cannot_replace_explicit_id_or_guess_another_installation(self):
        row, manifest = self.steam_subgame()
        with self.assertRaises(t.Refusal): hdr.match(dict(row, appid='999'), 'x64')
        manifest.write_text('"AppState" { "appid" "123" "installdir" "Other" }', encoding='utf-8')
        with self.assertRaises(t.Refusal): hdr.match(row, 'x64')
        manifest.write_text('"AppState" { "appid" "123" "installdir" "../Trilogy" }', encoding='utf-8')
        with self.assertRaises(t.Refusal): hdr.match(row, 'x64')

    def test_duplicate_steam_ownership_is_not_automatic(self):
        row, manifest = self.steam_subgame()
        manifest.with_name('appmanifest_999.acf').write_text(
            '"AppState" { "appid" "999" "installdir" "Trilogy" }', encoding='utf-8')
        with self.assertRaisesRegex(t.Refusal, 'Several Steam records'): hdr.match(row, 'x64')

    def test_known_prerequisites_and_bad_pins_are_not_automatic(self):
        mod = self.catalog['games'][0]['mods'][0]
        mod['notes'] = ['Requires REFramework nightly to function.']
        with self.assertRaises(t.Refusal): hdr.match(self.row, 'x64')
        mod['notes'] = []; self.pin['sha256'] = 'bad'
        with self.assertRaises(t.Refusal): hdr.match(self.row, 'x64')

    def test_standalone_install_update_and_remove_preserve_saves(self):
        plan = hdr.prepare({}, self.row)
        self.assertEqual(plan['route'], 'reshade'); self.assertFalse((self.game / 'dxgi.dll').exists())
        hdr.apply({}, plan)
        self.assertEqual((self.game / 'dxgi.dll').read_bytes(), self.host)
        self.assertTrue(hdr.status({}, self.row)['installed'])
        self.addon = pe() + b'new HDR'; self.pin.update(size=len(self.addon), sha256=t.sha(self.addon))
        self.assertTrue(hdr.status({}, self.row)['update'])
        hdr.apply({}, hdr.prepare({}, self.row))
        hdr.apply({}, hdr.prepare_remove({}, self.row))
        self.assertFalse((self.game / 'dxgi.dll').exists())
        self.assertFalse((self.game / 'renodx-game.addon64').exists())
        self.assertEqual((self.game / 'save.dat').read_bytes(), b'save')

    def test_optiscaler_side_load_and_remove_keep_later_tuning(self):
        self.optiscaler(); original = (self.game / 'dxgi.dll').read_bytes()
        plan = hdr.prepare({}, self.row); self.assertEqual(plan['route'], 'optiscaler'); hdr.apply({}, plan)
        ini = self.game / 'OptiScaler.ini'
        ini.write_text(ini.read_text(encoding='utf-8') + '\n[DLSSG]\nOverrideInterpolationCount=3\n', encoding='utf-8')
        hdr.apply({}, hdr.prepare_remove({}, self.row))
        text = ini.read_text(encoding='utf-8')
        self.assertIn('LoadReShade=false', text); self.assertIn('OverrideInterpolationCount=3', text)
        self.assertIn('Enabled=true', text); self.assertEqual((self.game / 'dxgi.dll').read_bytes(), original)

    def test_absent_plugin_key_is_removed_without_other_keys(self):
        self.optiscaler('[Plugins]\nLoadSpecialK=false\n')
        hdr.apply({}, hdr.prepare({}, self.row)); hdr.apply({}, hdr.prepare_remove({}, self.row))
        text = (self.game / 'OptiScaler.ini').read_text(encoding='utf-8')
        self.assertNotIn('LoadReShade', text); self.assertIn('LoadSpecialK=false', text)

    def test_feeder_host_is_reused_and_never_removed(self):
        (self.game / 'dxgi.dll').write_bytes(self.host)
        (self.game / 'renodx-dlss5.addon64').write_bytes(b'NR')
        plan = hdr.prepare({}, self.row); self.assertEqual(plan['route'], 'existing-reshade')
        self.assertNotIn('dxgi.dll', [c['path'] for c in plan['changes']]); hdr.apply({}, plan)
        hdr.apply({}, hdr.prepare_remove({}, self.row))
        self.assertEqual((self.game / 'dxgi.dll').read_bytes(), self.host)
        self.assertEqual((self.game / 'renodx-dlss5.addon64').read_bytes(), b'NR')

    def test_new_host_respects_menu_policy_and_preserves_user_settings(self):
        hdr.apply({}, hdr.prepare({}, self.row))
        ini = self.game / 'ReShade.ini'
        self.assertEqual(t.ini(ini.read_text(encoding='utf-8')).get('OVERLAY', 'TutorialProgress'), '4')
        ini.write_text(ini.read_text(encoding='utf-8') + '\n[RenoDX]\nToneMapGameNits=203\n', encoding='utf-8')
        hdr.apply({}, hdr.prepare_remove({}, self.row))
        self.assertIn('ToneMapGameNits=203', ini.read_text(encoding='utf-8'))

    def test_collisions_running_game_and_changed_review_refused(self):
        (self.game / 'dxgi.dll').write_bytes(b'other mod')
        with self.assertRaises(t.Refusal): hdr.prepare({}, self.row)
        (self.game / 'dxgi.dll').unlink(); plan = hdr.prepare({}, self.row)
        self.engine.running = True
        with self.assertRaises(t.Refusal): hdr.apply({}, plan)
        self.engine.running = False; (self.game / 'Game.exe').write_bytes(pe() + b'updated')
        with self.assertRaises(t.Refusal): hdr.apply({}, plan)
        self.assertFalse((self.game / 'dxgi.dll').exists())

    def test_optiscaler_proxy_drift_after_review_is_refused(self):
        self.optiscaler(); plan = hdr.prepare({}, self.row)
        (self.game / 'dxgi.dll').write_bytes(pe() + b'changed loader')
        with self.assertRaises(t.Refusal): hdr.apply({}, plan)
        self.assertFalse((self.game / 'ReShade64.dll').exists())

    def test_changed_hdr_and_new_feature_host_ownership_preserved(self):
        hdr.apply({}, hdr.prepare({}, self.row))
        addon = self.game / 'renodx-game.addon64'; addon.write_bytes(b'user HDR')
        with self.assertRaises(t.Refusal): hdr.prepare_remove({}, self.row)
        addon.write_bytes(self.addon)
        self.engine.baseline = {'status': 'active', 'managed_paths': ['dxgi.dll']}
        with self.assertRaises(t.Refusal): hdr.prepare_remove({}, self.row)
        self.assertTrue((self.game / 'dxgi.dll').exists())

    def test_shared_optiscaler_is_reused_without_private_state_adoption(self):
        self.optiscaler(); self.engine.baseline = None
        shared = {'provider': {'id': 'skynizz'}, 'proxy': 'dxgi.dll',
                  'files': {n: t.digest(self.game/n) for n in ('dxgi.dll', 'OptiScaler.ini')}}
        with patch.object(hdr.cross_os, 'read', return_value=shared):
            plan = hdr.prepare({}, self.row)
        self.assertEqual(plan['route'], 'optiscaler')
        self.assertNotIn('dxgi.dll', [c['path'] for c in plan['changes']])

    def test_foreign_os_feature_cannot_lose_its_shared_host(self):
        hdr.apply({}, hdr.prepare({}, self.row))
        shared = {'files': {'dxgi.dll': t.digest(self.game/'dxgi.dll')}}
        with patch.object(hdr.cross_os, 'read', return_value=shared):
            with self.assertRaisesRegex(t.Refusal, 'Another feature'): hdr.prepare_remove({}, self.row)
        self.assertTrue((self.game / 'dxgi.dll').exists())

    def test_anti_cheat_and_vulkan_are_reported_without_game_writes(self):
        with self.assertRaises(t.Refusal): hdr.prepare({}, dict(self.row, anti_cheat=True))
        self.engine.imports = {'vulkan-1.dll'}
        self.assertFalse(hdr.status({}, self.row)['available'])
        self.assertFalse((self.game / 'dxgi.dll').exists())

    def test_failed_write_rolls_back_all_applied_files(self):
        plan = hdr.prepare({}, self.row); real = t.atomic_file; count = 0
        def fail(path, data, mode):
            nonlocal count
            if Path(path).is_relative_to(self.game):
                count += 1
                if count == 2: raise OSError('interrupted')
            return real(path, data, mode)
        with patch.object(t, 'atomic_file', side_effect=fail):
            with self.assertRaises(OSError): hdr.apply({}, plan)
        self.assertFalse((self.game / 'dxgi.dll').exists()); self.assertFalse((self.game / 'renodx-game.addon64').exists())
        self.assertEqual((self.game / 'save.dat').read_bytes(), b'save')

    def test_fetch_verifies_architecture_and_exact_archive_member(self):
        addon = self.root / 'addon'; addon.write_bytes(self.addon)
        setup = self.root / 'setup'
        with zipfile.ZipFile(setup, 'w') as z: z.writestr('ReShade64.dll', self.host)
        fetch = self._patches_fetch_restore()
        with fetch, patch.object(hdr.packages, 'download', side_effect=[addon, setup]) as download:
            payload = hdr._fetch({}, hdr.match(self.row, 'x64'), 'x64')
            self.assertEqual(payload['ReShade64.dll'], self.host)
            self.assertEqual(download.call_args_list[0].kwargs['expected'], t.sha(self.addon))
            self.assertEqual(download.call_args_list[0].args[0].headers['Accept'], 'application/octet-stream')

    def test_recovery_receipt_cannot_claim_arbitrary_game_files(self):
        hdr.apply({}, hdr.prepare({}, self.row))
        receipt = hdr._location(self.row)[2]
        record = json.loads(receipt.read_text(encoding='utf-8'))
        record['files']['save.dat'] = t.digest(self.game / 'save.dat')
        receipt.write_text(json.dumps(record), encoding='utf-8')
        with self.assertRaises(t.Refusal): hdr.prepare_remove({}, self.row)
        self.assertEqual((self.game / 'save.dat').read_bytes(), b'save')

    def test_proton_override_is_automatic_and_preserves_later_settings(self):
        prefix = self.root / 'pfx'; prefix.mkdir()
        registry = prefix / 'user.reg'; registry.write_text('WINE REGISTRY Version 2\n', encoding='utf-8')
        self.engine.STATE_ROOT = self.state
        with patch.object(hdr, 'WINDOWS', False), patch.object(hdr.proton_prefix, 'find_prefix', return_value=prefix), patch.object(hdr.proton_prefix, 'prefix_in_use', return_value=False):
            hdr.apply({}, hdr.prepare({}, self.row))
            self.assertEqual(hdr.proton_prefix.read_overrides(registry.read_text())['dxgi'], 'native,builtin')
            registry.write_text(registry.read_text() + '\n[SomeOtherSetting]\n"Keep"="yes"\n', encoding='utf-8')
            hdr.apply({}, hdr.prepare_remove({}, self.row))
            self.assertNotIn('dxgi', hdr.proton_prefix.read_overrides(registry.read_text()))
            self.assertIn('"Keep"="yes"', registry.read_text())

    def test_failed_proton_override_rolls_back_game_and_registry(self):
        prefix = self.root / 'pfx'; prefix.mkdir()
        registry = prefix / 'user.reg'; original = 'WINE REGISTRY Version 2\n'; registry.write_text(original)
        self.engine.STATE_ROOT = self.state
        def fail(*args):
            registry.write_text('partial failed override'); raise OSError('prefix write failed')
        with patch.object(hdr, 'WINDOWS', False), patch.object(hdr.proton_prefix, 'find_prefix', return_value=prefix), patch.object(hdr.proton_prefix, 'prefix_in_use', return_value=False):
            plan = hdr.prepare({}, self.row)
            with patch.object(hdr.proton_prefix, 'apply', side_effect=fail):
                with self.assertRaises(OSError): hdr.apply({}, plan)
        self.assertEqual(registry.read_text(), original)
        self.assertFalse((self.game / 'dxgi.dll').exists()); self.assertFalse((self.game / 'renodx-game.addon64').exists())

    def _patches_fetch_restore(self):
        # setUp patches downloads for transaction tests; exercise the real loader here.
        return patch.object(hdr, '_fetch', ORIGINAL_FETCH)


ORIGINAL_FETCH = hdr._fetch

class CatalogTests(unittest.TestCase):
    def test_published_catalog_has_real_pinned_assets_and_notices(self):
        data = hdr.catalog(); self.assertGreater(len(data['games']), 200)
        for game in data['games']:
            for mod in game['mods']:
                for artifact in mod.get('artifacts', []):
                    pin = data['assets'][artifact['name']]
                    self.assertEqual(pin['size'], artifact['size']); self.assertRegex(pin['sha256'], '^[a-f0-9]{64}$')
        for appid in ('1328670', '3669870', '552520', '1086940'):
            self.assertTrue(hdr.match({'appid': appid}, 'x64')['pin']['id'])
        self.assertIn('Copyright', (hdr.ROOT/'providers/renodx-hdr/RenoDX-LICENSE.txt').read_text(encoding='utf-8'))


if __name__ == '__main__': unittest.main()
