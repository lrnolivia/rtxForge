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
        self.e.pe_imported_dlls = lambda exe: {'d3d12.dll'}
        self.assertFalse(self.prepare(row)['rows'])
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


if __name__ == '__main__':
    unittest.main()
