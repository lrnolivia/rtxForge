"""Per-game package routing, bounded extraction, ownership and restoration."""
from pathlib import Path
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import extra_tools
import reshade_import as r
import transactions as t


def pe(arch='x64', name=b'ReShade'):
    value = bytearray(160)
    value[:2] = b'MZ'; struct.pack_into('<I', value, 60, 64)
    value[64:70] = b'PE\0\0' + (b'd\x86' if arch == 'x64' else b'L\x01')
    value[80:80+len(name)] = name
    return bytes(value)


class ReShadeImportTest(unittest.TestCase):
    def test_overlay_bundle_requires_both_verified_controls_and_renderer(self):
        import json
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'providers/feeder-panel';folder.mkdir(parents=True)
            payload={'rtxforge-effects.addon64':b'effects','rtxforge-glass.dll':b'glass'}
            for name,data in payload.items():(folder/name).write_bytes(data)
            (folder/'package.json').write_text(json.dumps({'files':{name:{'size':len(data),'sha256':t.sha(data)} for name,data in payload.items()}}))
            with patch.object(r.hdr,'ROOT',root):
                self.assertEqual(r.bridge_files('x64'),payload)
                self.assertEqual(r.bridge_files('x86'),{})
                (folder/'rtxforge-glass.dll').write_bytes(b'changed')
                with self.assertRaises(t.Refusal):r.bridge_files('x64')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = Path(self.temp.name)
        self.root = self.base / 'game'; self.root.mkdir()
        self.exe = self.root / 'game.exe'; self.exe.write_bytes(pe(name=b'game'))
        self.game = {'game': str(self.root), 'exe': 'game.exe', 'name': 'Test Game'}
        self.engine = SimpleNamespace(mutation_lock=nullcontext, _running_processes_under_root=lambda _: [], load_baseline=lambda *a, **k: None,
                                      pe_imported_dlls=lambda _: {'d3d11.dll'})
        self.patches = [patch.object(r.engine_bridge, 'module', return_value=self.engine),
                        patch.object(r.discovery, 'inspect_game', return_value=SimpleNamespace(anti_cheat=False)),
                        patch.object(r.hdr, '_owned', return_value=False),
                        patch.object(r, 'storage', return_value=self.base / 'state'),
                        patch.object(extra_tools, 'storage', return_value=self.base / 'state'),
                        patch.object(r, 'host_bytes', return_value=pe()),
                        patch.object(r, 'WINDOWS', True)]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def package(self, entries):
        path = self.base / 'Custom.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in entries.items(): archive.writestr(name, data)
        return path

    def deploy(self, source=None):
        plan = extra_tools.prepare({}, self.game, str(source) if source else None, 'reshade-import')
        return plan, extra_tools.apply({}, plan)

    def test_nested_shader_pack_and_custom_ini_roundtrip(self):
        preset = b'; publisher tuning\n[Custom.fx]\nUnknownSetting=7.25\n'
        package = self.package({'Publisher/Shaders/Custom.fx': b'uniform float UnknownSetting;',
                                'Publisher/Textures/LUT.png': b'png', 'Publisher/Custom.ini': preset,
                                'Publisher/LICENSE.txt': b'Publisher license'})
        plan, state = self.deploy(package)
        self.assertEqual((self.root / 'Custom.ini').read_bytes(), preset)
        self.assertTrue((self.root / 'reshade-shaders/Shaders/Custom.fx').is_file())
        self.assertEqual((self.root / 'rtxForge-ReShade-Notices/LICENSE.txt').read_bytes(), b'Publisher license')
        config = t.ini((self.root / 'ReShade.ini').read_text())
        self.assertEqual(config['GENERAL']['PresetPath'], '.\\Custom.ini')
        self.assertEqual(extra_tools.recoveries({}, self.game)[0]['kind'], 'reshade-import')
        extra_tools.restore({}, state)
        self.assertEqual({p.name for p in self.root.iterdir() if p.is_file()}, {'game.exe'})

    def test_standalone_import_installs_and_restores_the_complete_overlay(self):
        payload={'rtxforge-effects.addon64':b'effects','rtxforge-glass.dll':b'glass'}
        with patch.object(r,'bridge_files',return_value=payload):
            _,state=self.deploy()
        for name,data in payload.items():self.assertEqual((self.root/name).read_bytes(),data)
        extra_tools.restore({},state)
        self.assertEqual({p.name for p in self.root.iterdir() if p.is_file()},{'game.exe'})

    def test_shader_import_preserves_paid_runtime_and_existing_settings(self):
        paid = pe(name=b'ReShade custom build')
        (self.root / 'dxgi.dll').write_bytes(paid)
        (self.root / 'ReShade.ini').write_text('; keep comment\n[Custom]\nSpecial=99\n')
        plan, _ = self.deploy(self.package({'Shaders/Unique.fx': b'float unique;'}))
        r.host_bytes.assert_not_called()
        self.assertEqual((self.root / 'dxgi.dll').read_bytes(), paid)
        self.assertNotIn('dxgi.dll', [c['path'] for c in plan['changes']])
        self.assertIn('; keep comment', (self.root / 'ReShade.ini').read_text())
        self.assertEqual(t.ini((self.root / 'ReShade.ini').read_text())['Custom']['Special'], '99')

    def test_real_preset_globals_and_unknown_shader_values_are_preserved(self):
        raw = b'PreprocessorDefinitions=MY_FEATURE=1\nTechniques=Custom@Paid.fx\nTechniqueSorting=Custom@Paid.fx\n\n[Paid.fx]\nPrivateParameter=4.125\n'
        _, _ = self.deploy(self.package({'PrivatePreset.ini': raw}))
        self.assertEqual((self.root / 'PrivatePreset.ini').read_bytes(), raw)

    def test_addon_settings_are_not_mistaken_for_a_shader_preset(self):
        (self.root / 'ReShade.ini').write_text('[GENERAL]\nPresetPath=.\\Existing.ini\n')
        _, _ = self.deploy(self.package({'Plugin.ini': b'[CustomPlugin]\nUnknownSetting=42\n'}))
        self.assertEqual(t.ini((self.root / 'ReShade.ini').read_text())['GENERAL']['PresetPath'], '.\\Existing.ini')
        self.assertTrue((self.root / 'Plugin.ini').exists())

    def test_document_only_or_wrong_architecture_packages_do_not_install_official_runtime(self):
        for entries in ({'README.txt': b'Instructions'}, {'ReShade32.dll': pe('x86'), 'README.txt': b'Instructions'}):
            with self.subTest(entries=list(entries)), self.assertRaises(t.Refusal): r.prepare({}, self.game, self.package(entries))
        r.host_bytes.assert_not_called()

    def test_optiscaler_loader_is_reused_and_plugin_enabled(self):
        (self.root / 'dxgi.dll').write_bytes(pe(name=b'OptiScaler'))
        (self.root / 'OptiScaler.ini').write_text('[Plugins]\nLoadReShade=false\n')
        baseline = {'status':'active','current':{'provider_id':'skynizz','proxy':'dxgi.dll','installed_hashes':{'dxgi.dll':t.digest(self.root / 'dxgi.dll')}}}
        with patch.object(r.hdr, '_managed', return_value=baseline):
            plan, state = self.deploy()
        self.assertEqual(plan['route'], 'optiscaler')
        self.assertTrue((self.root / 'ReShade64.dll').exists())
        self.assertIn('LoadReShade=true', (self.root / 'OptiScaler.ini').read_text())
        extra_tools.restore({}, state)
        self.assertIn('LoadReShade=false', (self.root / 'OptiScaler.ini').read_text())
        self.assertTrue((self.root / 'dxgi.dll').exists())

    def test_proton_failure_rolls_back_imported_files(self):
        prefix = self.base / 'prefix'; prefix.mkdir(); (prefix / 'user.reg').write_text('WINE REGISTRY Version 2\n')
        with patch.object(r, 'WINDOWS', False), patch.object(r.proton_prefix, 'find_prefix', return_value=prefix), patch.object(r.proton_prefix, 'prefix_in_use', return_value=False), patch.object(r.proton_prefix, 'apply', side_effect=t.Refusal('session started')):
            plan = r.prepare({}, self.game)
            with self.assertRaises(t.Refusal): r.apply({}, plan)
        self.assertFalse((self.root / 'dxgi.dll').exists())
        self.assertFalse((self.root / 'ReShade.ini').exists())

    def test_official_runtime_auto_install_and_restore(self):
        _, state = self.deploy()
        self.assertEqual((self.root / 'dxgi.dll').read_bytes(), pe())
        self.assertTrue((self.root / 'rtxForge-ReShade-Notices/ReShade-LICENSE.txt').exists())
        extra_tools.restore({}, state)
        self.assertFalse((self.root / 'dxgi.dll').exists())

    def test_dx9_uses_d3d9_proxy(self):
        self.engine.pe_imported_dlls = lambda _: {'d3d9.dll'}
        plan, _ = self.deploy()
        self.assertEqual(plan['host'], 'd3d9.dll')

    def test_mixed_architecture_archive_selects_matching_runtime(self):
        plan, _ = self.deploy(self.package({'ReShade64.dll': pe(), 'ReShade32.dll': pe('x86')}))
        self.assertEqual((self.root / 'dxgi.dll').read_bytes(), pe())
        self.assertIn('ReShade32.dll (other architecture)', plan['skipped'])

    def test_x86_game_selects_32_bit_runtime(self):
        self.exe.write_bytes(pe('x86', b'game'))
        _, _ = self.deploy(self.package({'ReShade64.dll': pe(), 'ReShade32.dll': pe('x86')}))
        self.assertEqual((self.root / 'dxgi.dll').read_bytes(), pe('x86'))

    def test_path_traversal_duplicate_paths_and_symlinks_are_refused(self):
        for names in ({'../outside.ini': b'[x]\ny=1'}, {'A.ini': b'[x]', 'a.ini': b'[x]'}, {'C:/outside.ini': b'[x]'}):
            with self.subTest(names=list(names)), self.assertRaises(t.Refusal): r._archive(self.package(names))
        path = self.base / 'link.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            entry = zipfile.ZipInfo('link.fx'); entry.external_attr = 0o120777 << 16
            archive.writestr(entry, '../outside')
        with self.assertRaises(t.Refusal): r._archive(path)

    def test_expansion_limit_checked_before_read(self):
        package = self.package({'large.fx': b'123456789'})
        with patch.object(r, 'MAX_TOTAL', 8), self.assertRaises(t.Refusal): r._archive(package)

    def test_refuses_unrelated_loader_and_different_custom_host(self):
        (self.root / 'dxgi.dll').write_bytes(pe(name=b'other tool'))
        with self.assertRaises(t.Refusal): r.prepare({}, self.game)
        (self.root / 'dxgi.dll').write_bytes(pe(name=b'ReShade paid'))
        with self.assertRaises(t.Refusal): r.prepare({}, self.game, self.package({'ReShade64.dll': pe()}))

    def test_game_changes_after_review_never_written(self):
        plan = r.prepare({}, self.game)
        self.exe.write_bytes(pe(name=b'changed game'))
        with self.assertRaises(t.Refusal): r.apply({}, plan)
        self.assertFalse((self.root / 'dxgi.dll').exists())

    def test_edited_preset_blocks_restore_and_keeps_user_edit(self):
        _, state = self.deploy(self.package({'Custom.ini': b'[Custom.fx]\nNew=1\n'}))
        (self.root / 'Custom.ini').write_text('[Custom.fx]\nNew=2\n')
        with self.assertRaises(t.Refusal): extra_tools.restore({}, state)
        self.assertIn('New=2', (self.root / 'Custom.ini').read_text())
        self.assertTrue((self.root / 'dxgi.dll').exists())

    def test_existing_shader_collision_is_not_overwritten(self):
        target = self.root / 'reshade-shaders/Shaders/Custom.fx'; target.parent.mkdir(parents=True)
        target.write_bytes(b'original shader')
        with self.assertRaises(t.Refusal): r.prepare({}, self.game, self.package({'Shaders/Custom.fx': b'replacement'}))
        self.assertEqual(target.read_bytes(), b'original shader')

    def test_game_start_while_waiting_for_mutation_lock_blocks_import(self):
        plan = r.prepare({}, self.game)
        @contextmanager
        def game_started():
            self.engine._running_processes_under_root = lambda _: [123]
            yield
        self.engine.mutation_lock = game_started
        with self.assertRaises(t.Refusal): r.apply({}, plan)
        self.assertFalse((self.root / 'dxgi.dll').exists())

    def test_preset_edited_while_waiting_for_mutation_lock_is_kept(self):
        _, state = self.deploy(self.package({'Custom.ini': b'[Custom.fx]\nNew=1\n'}))
        @contextmanager
        def edited():
            (self.root / 'Custom.ini').write_text('[Custom.fx]\nNew=2\n')
            yield
        self.engine.mutation_lock = edited
        with self.assertRaises(t.Refusal): r.restore({}, state)
        self.assertIn('New=2', (self.root / 'Custom.ini').read_text())
        self.assertTrue((self.root / 'dxgi.dll').exists())


if __name__ == '__main__': unittest.main()
