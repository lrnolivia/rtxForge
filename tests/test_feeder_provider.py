"""Feeder ownership and model changes against disposable files, no GPU needed."""
import contextlib
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import feeder_provider as feeder
import transactions as t


def pe(suffix=b''):
    data = bytearray(256)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64)
    data[64:70] = b'PE\0\0\x64\x86'
    return bytes(data) + suffix


def copy_command(args, **kwargs):
    source, target = map(Path, args[-2:])
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return subprocess.CompletedProcess(args, 0)


class FeederTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.old = pe(b'old model')
        self.new = pe(b'new model')
        real = feeder.lock()
        self.assets = {name: pe(name.encode()) if name.endswith(('.dll', '.addon64')) else b'// shader fixture\n'
                       for name in real['assets']}
        self.spec = dict(real, assets={name: {'sha256': t.sha(data), 'size': len(data)} for name, data in self.assets.items()},
                         models={t.sha(self.old): {'version': '310.8.0.0', 'size': len(self.old)},
                                 t.sha(self.new): {'version': '310.9.16.0', 'size': len(self.new)}})
        self.lock_patch = patch.object(feeder, 'lock', lambda: copy.deepcopy(self.spec))
        self.lock_patch.start()
        self.addCleanup(self.lock_patch.stop)
        self.copy_patch = patch('operation_session.subprocess.run', side_effect=copy_command)
        self.copy_patch.start()
        self.addCleanup(self.copy_patch.stop)
        self.e = SimpleNamespace(STATE_ROOT=self.root / 'state', DESKTOP_PLATFORM='windows', Stop=RuntimeError,
                                 _running_processes_under_root=lambda root: [], load_baseline=lambda *args, **kw: None,
                                 pe_imported_dlls=lambda exe: {'d3d11.dll'}, mutation_lock=contextlib.nullcontext,
                                 now_stamp=lambda: 'fixture',
                                 save_json_atomic=lambda path, obj: t.atomic_file(path, json.dumps(obj).encode(), 0o600))
        self.e.STATE_ROOT.mkdir()
        self.source = self.root / 'source'
        self.source.mkdir()
        self.write_stack(self.source)
        self.new_path = self.root / 'new-model.dll'
        self.new_path.write_bytes(self.new)
        self.backups = self.root / 'manual-backups'
        self.backups.mkdir()
        self.settings = {'nr_on_launch': True, 'nr_runtime': str(self.new_path), 'feeder_source': str(self.source), 'feeder_backups': str(self.backups)}

    def write_stack(self, directory):
        for name, data in self.assets.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (directory / feeder.MODEL).write_bytes(self.old)
        (directory / 'ReShade.ini').write_bytes(b'[DEPTH]\r\nDepthCopyBeforeClears=1\r\n[RenoDX.DLSS5]\r\nNeuralUplift=1\r\nNRPasses=1\r\nNRFollowInputRes=1\r\nNRResolutionScale=0.7\r\nNRLocalTone=2\r\n')
        (directory / 'ReShadePreset.ini').write_text('Techniques=Lumenite_Kernel@lumenite_Kernel.fx,DLSS5_Feed@DLSS5_Feed.fx\n\n[DLSS5_Feed.fx]\nDEBUG_VIEW=0\n')

    def game(self, name='game', installed=False):
        directory = self.root / name
        directory.mkdir()
        (directory / 'game.exe').write_bytes(pe())
        (directory / 'save.dat').write_bytes(b'keep save')
        if installed:
            self.write_stack(directory)
            originals = self.backups / name
            originals.mkdir()
            files = [{'path': rel, 'before': None, 'after': t.digest(directory / rel)}
                     for rel in [*self.assets, *feeder.CONFIGS, feeder.MODEL]]
            (originals / 'manifest.json').write_text(json.dumps({'schema': 1, 'target': str(directory),
                                                               'state': 'installed-unverified', 'files': files}))
        return {'name': name, 'game': str(directory), 'exe': 'game.exe', 'anti_cheat': False}

    def prepare(self, row, operation='install', **settings):
        return feeder.prepare({}, [row], 'nr-only', operation, self.settings | settings, self.e)

    def apply(self, review):
        self.assertFalse(review['blocked'], review['blocked'])
        self.assertTrue(review['rows'])
        return feeder.execute(review)

    def files(self, row):
        root = Path(row['game'])
        return {path.relative_to(root).as_posix(): t.digest(path) for path in root.rglob('*') if path.is_file()}

    def test_adoption_updates_only_model_preserves_tuning_and_restores_originals(self):
        row = self.game(installed=True)
        before = self.files(row)
        review = self.prepare(row)
        self.assertEqual(self.files(row), before)
        self.assertEqual(set(review['plans'][0]['writes']), {feeder.MODEL})
        self.apply(review)
        after = self.files(row)
        self.assertEqual({name for name in before if before[name] != after[name]}, {feeder.MODEL})
        record = feeder.state(self.e, Path(row['game']))
        self.assertTrue(record['adopted'])
        self.assertEqual(Path(record['previous_models'][0]['path']).read_bytes(), self.old)
        self.assertTrue(feeder.inspect(self.e, row)['nr_enabled'])
        self.apply(self.prepare(row, 'uninstall'))
        self.assertEqual(self.files(row), {'game.exe': before['game.exe'], 'save.dat': before['save.dat']})

    def test_generated_cfg_not_required_to_recognize_installed(self):
        row = self.game(installed=True)
        self.assertFalse((Path(row['game']) / 'dlss5-feed.cfg').exists())
        found = feeder.expand_rows(self.e, [row], selected=True)[0]
        self.assertTrue(found['installed'])
        self.assertFalse(found['feeder_managed'])
        self.assertEqual(found['runtime_provider'], 'feeder')

    def test_clean_dx11_candidate_is_available_without_switching_packages(self):
        row = self.game('clean-dx11') | {'blocked': 'No native DLSS-G detected', 'native_dlss': False}
        before = self.files(row)
        found = feeder.expand_rows(self.e, [row])[0]
        self.assertEqual(found['blocked'], '')
        self.assertTrue(found['feeder_available'])
        self.assertEqual(found['install_provider'], 'feeder')
        self.assertFalse(found.get('installed', False))
        self.assertNotIn('runtime_provider', found)
        import skynizz_provider
        self.assertEqual(skynizz_provider.scan_rows([found], 'nr-mfg')[0]['blocked'], '')
        self.assertEqual(self.files(row), before)

    def test_scan_capability_does_not_allow_writes_to_a_running_game(self):
        row = self.game('running-dx11') | {'blocked': 'No native DLSS-G detected'}
        self.e._running_processes_under_root = lambda root: ['game.exe']
        found = feeder.expand_rows(self.e, [row])[0]
        self.assertTrue(found['feeder_available'])
        review = self.prepare(found)
        self.assertFalse(review['rows'])
        self.assertIn('Close this game', review['blocked'][0]['reason'])

    def test_known_dx11_native_nr_hint_can_use_feeder(self):
        row = self.game('bg3-dx11') | {'appid': '1086940', 'native_dlss': True}
        found = feeder.expand_rows(self.e, [row])[0]
        import skynizz_provider
        self.assertTrue(found['feeder_available'])
        self.assertFalse(skynizz_provider.scan_rows([found], 'nr-only')[0]['blocked'])

    def test_sims_launcher_resolves_to_the_dx11_game_before_install(self):
        row = self.game('sims')
        directory = Path(row['game'])
        (directory / 'TS4_Launcher_x64.exe').write_bytes(pe())
        (directory / 'TS4_x64.exe').write_bytes(pe())
        row['exe'] = 'TS4_Launcher_x64.exe'
        found = feeder.expand_rows(self.e, [row])[0]
        self.assertEqual(found['exe'], 'TS4_x64.exe')
        self.assertTrue(found['feeder_available'])

    def test_automatic_route_does_not_replace_native_or_unsupported_targets(self):
        row = self.game('native') | {'blocked': 'Original reason', 'native_dlss': True}
        self.assertNotIn('feeder_available', feeder.expand_rows(self.e, [row])[0])
        row['native_dlss'] = False
        row['anti_cheat'] = True
        self.assertNotIn('feeder_available', feeder.expand_rows(self.e, [row])[0])
        row['anti_cheat'] = False
        self.e.pe_imported_dlls = lambda exe: {'vulkan-1.dll'}
        found = feeder.expand_rows(self.e, [row])[0]
        self.assertNotIn('feeder_available', found)
        self.assertEqual(found['blocked'], 'Original reason')

    def test_directx12_games_without_dlss_get_an_unverified_feeder_route(self):
        row = self.game('dx12') | {'blocked': 'Original reason', 'native_dlss': False}
        self.e.pe_imported_dlls = lambda exe: {'d3d12.dll', 'dxgi.dll'}
        found = feeder.expand_rows(self.e, [row])[0]
        self.assertTrue(found['feeder_available'])
        self.assertEqual(found['nr_route_note'], 'Feeder NR · DirectX 12 · not verified · NR only')
        self.assertEqual(found['blocked'], '')
        # Feeder's DirectX 12 session refuses a second DLSS runtime on the game's device.
        found = feeder.expand_rows(self.e, [row | {'native_dlss': True}])[0]
        self.assertNotIn('feeder_available', found)

    def test_packed_executables_are_read_for_the_dlls_they_mention(self):
        row = self.game('packed')
        exe = Path(row['game']) / row['exe']
        exe.write_bytes(pe(b'\0LoadLibrary\0D3D12.dll\0'))
        self.e.pe_imported_dlls = lambda exe: {'Activation64.dll'}
        self.assertEqual(feeder.graphics_apis(self.e, exe), {'d3d12'})
        exe.write_bytes(pe(b'\0d3d11.dll\0d3d12.dll\0'))
        self.assertEqual(feeder.graphics_apis(self.e, exe), {'d3d11', 'd3d12'})
        exe.write_bytes(pe())
        self.assertEqual(feeder.graphics_apis(self.e, exe), set())

    def test_nr_starts_off_unless_enabled_on_launch(self):
        row = self.game('startup-default')
        settings = dict(self.settings)
        settings.pop('nr_on_launch')
        review = feeder.prepare({}, [row], 'nr-only', 'install', settings, self.e)
        self.apply(review)
        self.assertFalse(feeder.configured(Path(row['game']))['nr_enabled'])
        values = feeder._read_ini(Path(row['game']) / 'ReShade.ini')['RenoDX.DLSS5']
        self.assertEqual(float(values['NRResolutionScale']), .65)
        self.assertEqual(float(values['NRLocalStructure']), 1.0)
        self.assertEqual(float(values['NRSkinStructure']), 1.0)
        self.assertEqual(values['NRFollowInputRes'], '0')

    def test_new_install_and_repeat_restore(self):
        row = self.game()
        before = self.files(row)
        self.apply(self.prepare(row))
        self.assertEqual((Path(row['game']) / feeder.MODEL).read_bytes(), self.new)
        ini = feeder._read_ini(Path(row['game']) / 'ReShade.ini')
        self.assertTrue(feeder.configured(Path(row['game']))['nr_enabled'])
        for key, expected in {'NRResolutionScale': .65, 'NRLocalStructure': 1.0, 'NRSkinStructure': 1.0}.items():
            self.assertEqual(float(ini['RenoDX.DLSS5'][key]), expected)
        self.assertEqual(ini['RenoDX.DLSS5']['NRLocalTone'], '2')
        self.assertEqual(ini['RenoDX.DLSS5']['NRFollowInputRes'], '0')
        self.assertEqual(ini['DEPTH']['DepthCopyBeforeClears'], '1')
        self.apply(self.prepare(row, 'uninstall'))
        self.assertEqual(self.files(row), before)
        self.apply(self.prepare(row))
        self.apply(self.prepare(row, 'uninstall'))
        self.assertEqual(self.files(row), before)

    def test_fresh_install_uses_owned_stack_after_source_folder_is_gone(self):
        feeder.import_stack(self.e, self.source)
        shutil.rmtree(self.source)
        row = self.game('owned-stack')
        before = self.files(row)
        self.apply(self.prepare(row, feeder_source=str(self.source)))
        self.assertTrue((Path(row['game']) / 'dlss5-feed.addon64').is_file())
        self.assertEqual((Path(row['game']) / feeder.MODEL).read_bytes(), self.new)
        self.apply(self.prepare(row, 'uninstall'))
        self.assertEqual(self.files(row), before)

    def test_review_imports_source_and_owned_model_serves_without_selection(self):
        (self.source / feeder.MODEL).write_bytes(self.new)
        row = self.game('imported-on-review')
        self.apply(self.prepare(row))
        record = feeder.owned_stack(self.e)
        self.assertEqual(record['imported_from'], str(self.source))
        self.assertEqual(record['nr_version'], '310.9.16.0')
        other = self.game('no-model-choice')
        self.apply(self.prepare(other, feeder_source='', nr_runtime=None))
        self.assertEqual((Path(other['game']) / feeder.MODEL).read_bytes(), self.new)

    def test_without_source_or_owned_stack_fresh_install_refuses(self):
        row = self.game('nothing-stored')
        review = self.prepare(row, feeder_source='')
        self.assertFalse(review['rows'])
        self.assertIn('Import a verified Feeder stack', review['blocked'][0]['reason'])

    def test_changed_owned_stack_is_refused(self):
        record = feeder.import_stack(self.e, self.source)
        Path(record['files']['dxgi.dll']['path']).write_bytes(pe(b'tampered'))
        with self.assertRaisesRegex(t.Refusal, 'stored Feeder stack changed'):
            feeder.owned_stack(self.e)

    def test_recognition_uses_owned_originals_after_backups_folder_is_gone(self):
        row = self.game(installed=True)
        path = self.backups / row['name'] / 'manifest.json'
        doc = json.loads(path.read_text())
        original = b'original SR before this mod'
        next(entry for entry in doc['files'] if entry['path'] == 'nvngx_dlss.dll')['before'] = t.sha(original)
        path.write_text(json.dumps(doc))
        (path.parent / 'originals').mkdir()
        (path.parent / 'originals/nvngx_dlss.dll').write_bytes(original)
        self.assertEqual(feeder.import_backups(self.e, self.backups), 1)
        shutil.rmtree(self.backups)
        self.apply(self.prepare(row))
        self.apply(self.prepare(row, 'uninstall'))
        self.assertEqual((Path(row['game']) / 'nvngx_dlss.dll').read_bytes(), original)

    def test_owned_and_folder_copies_of_one_manifest_are_not_ambiguous(self):
        row = self.game(installed=True)
        feeder.import_backups(self.e, self.backups)
        self.assertTrue(self.prepare(row)['rows'])
        twin = self.backups / 'second-copy'
        twin.mkdir()
        doc = json.loads((self.backups / row['name'] / 'manifest.json').read_text())
        doc['note'] = 'another recipe record for the same game'
        (twin / 'manifest.json').write_text(json.dumps(doc))
        self.assertFalse(self.prepare(row)['rows'])

    def test_repair_pins_model_and_preserves_later_settings(self):
        row = self.game(installed=True)
        self.apply(self.prepare(row))
        directory = Path(row['game'])
        settings = (directory / 'ReShade.ini').read_bytes() + b'NRLocalStructure=1.13\r\n'
        (directory / 'ReShade.ini').write_bytes(settings)
        self.new_path.write_bytes(self.old)
        self.apply(self.prepare(row, 'repair'))
        self.assertEqual((directory / feeder.MODEL).read_bytes(), self.new)
        self.assertEqual((directory / 'ReShade.ini').read_bytes(), settings)

    def test_previous_renodx_keeps_installed_games_working_but_is_not_imported(self):
        earlier = pe(b'earlier renodx')
        self.spec['previous_assets'] = {'renodx-dlss5.addon64': [{'version': 'earlier', 'sha256': t.sha(earlier), 'size': len(earlier)}]}
        current, self.assets['renodx-dlss5.addon64'] = self.assets['renodx-dlss5.addon64'], earlier
        row = self.game(installed=True)
        old_source = self.root / 'old-source'
        old_source.mkdir()
        self.write_stack(old_source)
        self.assets['renodx-dlss5.addon64'] = current
        self.apply(self.prepare(row))
        self.apply(self.prepare(row, 'uninstall'))
        self.assertFalse((Path(row['game']) / 'renodx-dlss5.addon64').exists())
        with self.assertRaisesRegex(t.Refusal, 'Feeder files are missing or changed: renodx-dlss5.addon64'):
            feeder.import_stack(self.e, old_source)

    def test_wrong_stack_or_model_refused_without_game_changes(self):
        row = self.game(installed=True)
        before = self.files(row)
        self.new_path.write_bytes(pe(b'unrecognized model'))
        self.assertFalse(self.prepare(row)['rows'])
        self.assertEqual(self.files(row), before)
        self.new_path.write_bytes(self.new)
        (Path(row['game']) / 'dlss5-feed.addon64').write_bytes(pe(b'other feeder'))
        before = self.files(row)
        self.assertFalse(self.prepare(row)['rows'])
        self.assertEqual(self.files(row), before)

    def test_missing_original_or_wrong_target_manifest_refuses(self):
        row = self.game(installed=True)
        path = self.backups / row['name'] / 'manifest.json'
        doc = json.loads(path.read_text())
        doc['target'] = str(self.root / 'other-game')
        path.write_text(json.dumps(doc))
        self.assertFalse(self.prepare(row)['rows'])

    def test_unrelated_backup_formats_do_not_hide_the_matching_manifest(self):
        row = self.game(installed=True)
        other = self.backups/'unrelated';other.mkdir()
        (other/'manifest.json').write_text('[]')
        self.assertTrue(self.prepare(row)['rows'])
        (other/'manifest.json').write_text('not json')
        self.assertTrue(self.prepare(row)['rows'])

    def test_original_bytes_are_verified_and_restored(self):
        row = self.game(installed=True)
        path = self.backups / row['name'] / 'manifest.json'
        doc = json.loads(path.read_text())
        original = b'original SR before this mod'
        next(entry for entry in doc['files'] if entry['path'] == 'nvngx_dlss.dll')['before'] = t.sha(original)
        path.write_text(json.dumps(doc))
        self.assertFalse(self.prepare(row)['rows'])
        backup = path.parent / 'originals/nvngx_dlss.dll'
        backup.parent.mkdir()
        backup.write_bytes(original)
        self.apply(self.prepare(row))
        self.apply(self.prepare(row, 'uninstall'))
        self.assertEqual((Path(row['game']) / 'nvngx_dlss.dll').read_bytes(), original)

    def test_live_process_conflicts_api_and_modes_refuse(self):
        row = self.game()
        self.e._running_processes_under_root = lambda root: ['game.exe']
        self.assertFalse(self.prepare(row)['rows'])
        self.e._running_processes_under_root = lambda root: []
        self.e.pe_imported_dlls = lambda exe: {'vulkan-1.dll'}
        self.assertFalse(self.prepare(row)['rows'])
        self.e.pe_imported_dlls = lambda exe: {'d3d12.dll'}
        self.assertFalse(self.prepare(row | {'native_dlss': True})['rows'])
        self.e.pe_imported_dlls = lambda exe: {'d3d11.dll'}
        (Path(row['game']) / 'OptiScaler.ini').write_text('[Other]\nkeep=true\n')
        self.assertFalse(self.prepare(row)['rows'])
        with self.assertRaises(t.Refusal):
            feeder.prepare({}, [row], 'nr-mfg', 'install', self.settings, self.e)
        self.e.DESKTOP_PLATFORM = 'linux'
        self.assertFalse(self.prepare(row)['rows'])

    def test_target_or_cached_source_drift_blocks_entire_selection(self):
        first, second = self.game('first', True), self.game('second', True)
        review = feeder.prepare({}, [first, second], 'nr-only', 'install', self.settings, self.e)
        (Path(second['game']) / feeder.MODEL).write_bytes(self.new)
        before = self.files(first)
        with self.assertRaises(t.Refusal):
            feeder.execute(review)
        self.assertEqual(self.files(first), before)
        review = self.prepare(first)
        Path(review['plans'][0]['inputs'][feeder.MODEL]['path']).write_bytes(b'changed cached model')
        with self.assertRaises(t.Refusal):
            feeder.execute(review)
        self.assertEqual(self.files(first), before)

    def test_write_failure_restores_previous_model_and_metadata(self):
        row = self.game(installed=True)
        before = self.files(row)
        review = self.prepare(row)
        original = t.atomic_file
        failed = [False]
        def fail(path, *args, **kwargs):
            if Path(path).name == feeder.MODEL and not failed[0]:
                failed[0] = True
                raise OSError('injected failure')
            return original(path, *args, **kwargs)
        with patch.object(t, 'atomic_file', fail), self.assertRaises(t.Refusal):
            feeder.execute(review)
        self.assertEqual(self.files(row), before)
        self.assertIsNone(feeder.state(self.e, Path(row['game'])))

    def test_failed_undo_remains_discoverable_for_recovery(self):
        import operation_session
        row = self.game(installed=True)
        before = self.files(row)
        review = self.prepare(row)
        original = t.atomic_file
        def fail(path, *args, **kwargs):
            if Path(path).name == feeder.MODEL:
                raise OSError('injected write failure')
            return original(path, *args, **kwargs)
        with patch.object(t, 'atomic_file', fail), patch.object(feeder.Session, 'undo', side_effect=OSError('injected undo failure')):
            with self.assertRaises(t.Refusal):
                feeder.execute(review)
        sessions = operation_session.unfinished(self.e.STATE_ROOT / 'desktop-operations')
        self.assertEqual(len(sessions), 1)
        self.assertIsNotNone(sessions[0].interrupted())
        self.assertTrue(json.loads((sessions[0].root/'result.json').read_text())['recovery_required'])
        sessions[0].recover()
        self.assertEqual(self.files(row), before)
        self.assertIsNone(feeder.state(self.e, Path(row['game'])))

    def test_partial_failure_reports_completed_games(self):
        rows = [self.game('first', True), self.game('second', True)]
        before = self.files(rows[1])
        review = feeder.prepare({}, rows, 'nr-only', 'install', self.settings, self.e)
        original = t.atomic_file
        def fail(path, *args, **kwargs):
            if Path(path) == Path(rows[1]['game'])/feeder.MODEL:
                raise OSError('injected second game failure')
            return original(path, *args, **kwargs)
        with patch.object(t, 'atomic_file', fail), self.assertRaisesRegex(t.Refusal, 'after 1 completed game'):
            feeder.execute(review)
        self.assertEqual((Path(rows[0]['game'])/feeder.MODEL).read_bytes(), self.new)
        self.assertEqual(self.files(rows[1]), before)
        report = json.loads(next((self.e.STATE_ROOT/'desktop-operations').glob('*/result.json')).read_text())
        self.assertEqual(len(report['results']), 1)
        self.assertFalse(report['recovery_required'])

    def test_cancel_after_first_game_restores_every_started_target(self):
        rows = [self.game('first', True), self.game('second', True)]
        before = [self.files(row) for row in rows]
        review = feeder.prepare({}, rows, 'nr-only', 'install', self.settings, self.e)
        event = review['cancel_event'] = threading.Event()
        original = t.atomic_file
        def cancel_after_model(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if Path(path).name == feeder.MODEL:
                event.set()
            return result
        with patch.object(t, 'atomic_file', cancel_after_model), self.assertRaises(feeder.Cancelled):
            feeder.execute(review)
        self.assertEqual([self.files(row) for row in rows], before)

    def test_collection_has_three_separate_installation_identities(self):
        root = self.root / 'collection'
        for index in (1, 2, 3):
            directory = root / f'Game/ME{index}/Binaries/Win64'
            directory.mkdir(parents=True)
            (directory / f'MassEffect{index}.exe').write_bytes(pe())
            self.write_stack(directory)
        rows = feeder.expand_rows(self.e, [{'name': 'Mass Effect Legendary Edition', 'game': str(root),
                                          'exe': 'Launcher.exe'}], selected=True)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({row['game'] for row in rows}), 3)
        self.assertTrue(all(row['installed'] and row['profile'] == 'NR Only' for row in rows))

    def test_clean_collection_exposes_each_game_before_feeder_is_installed(self):
        root = self.root / 'clean-collection'
        for index in (1, 2, 3):
            directory = root / f'Game/ME{index}/Binaries/Win64'
            directory.mkdir(parents=True)
            (directory / f'MassEffect{index}.exe').write_bytes(pe())
        rows = feeder.expand_rows(self.e, [{'name': 'Mass Effect Legendary Edition', 'game': str(root),
                                          'exe': 'Launcher.exe', 'native_dlss': False, 'blocked': 'No native DLSS-G detected'}])
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({row['game'] for row in rows}), 3)
        self.assertTrue(all(row['feeder_available'] and not row.get('installed') and not row['blocked'] for row in rows))

    def test_feed_counters_and_requested_settings_do_not_prove_nr(self):
        feed = 'NGX runtime nvngx_dlssnr.dll: 310.9.16.0\n600 frames: feed GPU 1ms\n'
        report = feeder.parse_logs(feed, 'NeuralUplift=1\nNR-VERDICT v3 state=NOT_ENGAGED evals=0\n')
        self.assertFalse(report['feature18_created'])
        self.assertFalse(report['feature18_evaluated'])
        self.assertEqual(report['last_verdict'], 'NOT_ENGAGED')
        report = feeder.parse_logs(feed, 'feature 18 created via the signed snippet\ninline feature 18 evaluation succeeded (count=60, NR input 1920)\nNR-VERDICT v3 state=OFF evals=60\n')
        self.assertTrue(report['feature18_created'] and report['feature18_evaluated'])
        self.assertEqual(report['last_verdict'], 'OFF')

    def test_stale_old_model_log_never_verifies_updated_dll(self):
        row = self.game(installed=True)
        directory = Path(row['game'])
        (directory/'dlss5-feed.log').write_text('NGX runtime nvngx_dlssnr.dll: 310.8.0.0\n')
        (directory/'ReShade.log').write_text('feature 18 created via the signed snippet\ninline feature 18 evaluation succeeded (count=30, NR input 1920)\n')
        self.apply(self.prepare(row))
        report = feeder.diagnose(row)
        self.assertFalse(report['log']['matches_current_model_version'])
        self.assertTrue(report['log']['predates_current_files'])
        self.assertIn('No matching NR evaluation', ' '.join(report['observations']))

    def test_ea_wrapped_executable_delay_loading_d3d11_is_eligible(self):
        # Mass Effect LE: the normal import table names only EA's activation DLL.
        data = bytearray(0x600)
        data[:2] = b'MZ'
        struct.pack_into('<I', data, 60, 64)
        data[64:68] = b'PE\0\0'
        struct.pack_into('<HH', data, 68, 0x8664, 1)
        struct.pack_into('<H', data, 84, 240)
        struct.pack_into('<H', data, 88, 0x20B)
        struct.pack_into('<II', data, 88 + 112 + 13 * 8, 0x1000, 64)
        struct.pack_into('<IIII', data, 88 + 240 + 8, 0x200, 0x1000, 0x200, 0x400)
        struct.pack_into('<II', data, 0x400, 1, 0x1100)
        data[0x500:0x50A] = b'd3d11.dll\0'
        row = self.game('mass-effect')
        (Path(row['game']) / 'game.exe').write_bytes(bytes(data))
        self.assertEqual(feeder.delay_imported_dlls(Path(row['game']) / 'game.exe'), {'d3d11.dll'})
        self.e.pe_imported_dlls = lambda exe: {'Core/Activation64.dll'}
        self.assertTrue(feeder.expand_rows(self.e, [row])[0]['feeder_available'])
        (Path(row['game']) / 'game.exe').write_bytes(pe())
        self.assertNotIn('feeder_available', feeder.expand_rows(self.e, [row])[0])

    def test_install_again_after_the_game_folder_was_replaced(self):
        row = self.game()
        before = self.files(row)
        self.apply(self.prepare(row))
        # Steam verification restores the game's own files and removes Feeder's.
        for name in self.files(row):
            if name not in before:
                (Path(row['game']) / name).unlink()
        self.assertEqual(feeder.state(self.e, Path(row['game']))['status'], 'active')
        self.apply(self.prepare(row))
        self.assertTrue(feeder.inspect(self.e, row)['managed'])
        self.apply(self.prepare(row, 'uninstall'))
        self.assertEqual(self.files(row), before)

    def test_presets_apply_to_the_games_reshade_ini_and_refuse_while_running(self):
        row = self.game()
        self.apply(self.prepare(row))
        presets = {'nr_on_launch': False, 'nr_strength': 1.2,
                   'feature_controls': {'intensity': 1.5, 'passes': 2, 'work_scale': 1.4, 'preset': 2, 'unknown': 9}}
        review = self.prepare(row, 'apply', **presets)
        self.assertEqual(set(review['plans'][0]['writes']), {'ReShade.ini'})
        self.apply(review)
        values = feeder._read_ini(Path(row['game']) / 'ReShade.ini')['RenoDX.DLSS5']
        self.assertEqual((values['NeuralUplift'], values['NRIntensity'], values['NRPasses'], values['NRResolutionScale'], values['NRPreset']),
                         ('0', '1.50', '2', '1.00', '2'))
        self.assertEqual(values['NRLocalTone'], '2')
        self.assertIn('already uses', self.prepare(row, 'apply', **presets)['blocked'][0]['reason'])
        self.e._running_processes_under_root = lambda root: ['game.exe']
        self.assertIn('Close this game', self.prepare(row, 'apply', nr_strength=.5)['blocked'][0]['reason'])

    def test_panel_is_owned_and_replaces_the_manual_quiet_startup_addon(self):
        quiet = pe(b'quiet startup')
        addons = {name: pe(name.encode()) for name in feeder.PANELS}
        for name, data in addons.items():
            (self.root / name).write_bytes(data)
        row = self.game(installed=True)
        directory = Path(row['game'])
        (directory / 'quiet-startup.addon64').write_bytes(quiet)
        before = self.files(row)
        with patch.object(feeder, 'panel', lambda e: {name: feeder.cache(e, self.root / name) for name in feeder.PANELS}), \
                patch.dict(feeder.RETIRED, {'quiet-startup.addon64': t.sha(quiet)}):
            review = self.prepare(row, reshade_intro=False)
            self.assertEqual(review['plans'][0]['writes']['quiet-startup.addon64'], None)
            self.apply(review)
            for name, data in addons.items():
                self.assertEqual((directory / name).read_bytes(), data)
            self.assertFalse((directory / 'quiet-startup.addon64').exists())
            self.assertTrue(feeder.inspect(self.e, row)['managed'])
            self.apply(self.prepare(row, 'repair', reshade_intro=True))
            self.assertEqual(feeder._read_ini(directory / 'ReShade.ini')['rtxForge.UI']['QuietStartup'], '0')
            self.apply(self.prepare(row, 'uninstall'))
        self.assertEqual(self.files(row), {name: before[name] for name in ('game.exe', 'save.dat', 'quiet-startup.addon64')})


class ExecutableProbeCacheTest(unittest.TestCase):
    """Library scans reuse a renderer answer until the executable itself changes."""

    def test_probe_is_reused_until_the_file_changes_and_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, store = base / 'game.exe', base / 'probes.json'
            exe.write_bytes(b'one')
            calls = []
            def probe():
                calls.append(1)
                return {'d3d11'}
            with patch.dict('os.environ', {'RTXFORGE_PROBE_CACHE': str(store)}), patch.object(feeder, '_PROBES', None):
                self.assertEqual(feeder.cached_probe('direct3d', exe, probe), {'d3d11'})
                self.assertEqual(feeder.cached_probe('direct3d', exe, probe), {'d3d11'})
                self.assertEqual(len(calls), 1)
                # A different kind of probe is a separate answer.
                feeder.cached_probe('renderers', exe, lambda: {'vulkan'})
                self.assertEqual(feeder.cached_probe('renderers', exe, probe), {'vulkan'})
                # An updated executable is probed again.
                exe.write_bytes(b'longer')
                self.assertEqual(feeder.cached_probe('direct3d', exe, lambda: {'d3d12'}), {'d3d12'})
            # A new process reads the answers kept on disk.
            with patch.dict('os.environ', {'RTXFORGE_PROBE_CACHE': str(store)}), patch.object(feeder, '_PROBES', None):
                self.assertEqual(feeder.cached_probe('direct3d', exe, probe), {'d3d12'})
                self.assertEqual(len(calls), 1)
            # A missing file is never cached.
            missing = base / 'missing.exe'
            with patch.dict('os.environ', {'RTXFORGE_PROBE_CACHE': ''}), patch.object(feeder, '_PROBES', None):
                self.assertEqual(feeder.cached_probe('direct3d', missing, lambda: set()), set())


class ReviewSessionTest(unittest.TestCase):
    """A review hashes each shared file once and takes one process inventory; execution checks afresh."""

    def test_review_shares_hashes_and_inventory_only_while_it_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ReShade64.dll'
            path.write_bytes(b'stack')
            inventories = []
            def running(root):
                return []
            running.snapshot = lambda: inventories.append(1) or (lambda root: [])
            e = SimpleNamespace(_running_processes_under_root=running)
            with patch.object(t, 'digest', wraps=t.digest) as hashed:
                with feeder.review_session(e):
                    for _ in range(3):
                        feeder.digest(path)
                        feeder.running_under(e, Path(folder))
                self.assertEqual((hashed.call_count, len(inventories)), (1, 1))
                feeder.digest(path)
                self.assertEqual(hashed.call_count, 2)


if __name__ == '__main__':
    unittest.main()
