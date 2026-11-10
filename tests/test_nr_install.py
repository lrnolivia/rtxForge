"""NR add-on install and restore against disposable game folders. No downloads, no GPU."""
import contextlib
import io
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nr_install
import renodx_hdr as hdr
import transactions as t

COMBO = {'environment': {'addon': 'lecram', 'build': '10.8', 'model': 'new', 'values': {'structure': 0.4, 'character': 0.1}},
         'character': {'addon': 'shortfuse', 'model': 'new', 'values': {'character': 0.68}}}


def pe(tag=b''):
    data = bytearray(256); data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64); data[64:70] = b'PE\0\0d\x86'
    return bytes(data) + tag


class Engine:
    def __init__(self):
        self.baseline = None; self.imports = {'dxgi.dll', 'd3d12.dll'}
    def _running_processes_under_root(self, root): return []
    def load_baseline(self, path, **kwargs): return self.baseline
    def pe_imported_dlls(self, path): return self.imports
    def mutation_lock(self): return contextlib.nullcontext()


class NrInstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.game = base / 'game'; self.game.mkdir(); self.state = base / 'state'; self.state.mkdir()
        (self.game / 'Game.exe').write_bytes(pe()); (self.game / 'save.dat').write_bytes(b'save')
        self.row = {'name': 'A Game', 'game': str(self.game), 'exe': 'Game.exe', 'native_dlss': True, 'source': 'Steam'}
        self.engine = Engine(); self.host = pe(b'ReShade'); self.model = pe(b'NR model')
        self.addons = {'renodx-dlss5.addon64': pe(b'Lecram'), 'renodx-dlss.addon64': pe(b'ShortFuse')}
        for target, name, value in [
            (hdr, '_eligible', lambda config, row: (self.game, self.game / 'Game.exe', None, self.engine)),
            (hdr.state_storage, 'storage', lambda config, required=0: self.state),
            (hdr, 'WINDOWS', True),
            (nr_install, '_fetch', lambda config, archive, name: b'verified archive'),
            (nr_install, '_members', lambda data, pins: {m: self.addons[Path(m).name] for m in pins}),
            (nr_install, '_model', lambda data, pin: self.model),
            (nr_install, '_reshade_host', lambda config, arch: self.host),
        ]:
            p = patch.object(target, name, value); p.start(); self.addCleanup(p.stop)

    def files(self):
        return {p.relative_to(self.game).as_posix(): p.read_bytes() for p in self.game.rglob('*') if p.is_file()}

    def test_install_then_restore_returns_the_original_folder(self):
        before = self.files()
        review = nr_install.prepare({}, self.row, COMBO)
        self.assertEqual(self.files(), before, 'review changed the game')
        self.assertNotIn('not been verified', ' '.join(review['notes']))
        nr_install.apply({}, review)
        self.assertIn('LoadFromDllMain=renodx-dlss.addon64', (self.game / 'ReShade.ini').read_text(encoding='utf-8'))
        self.assertEqual((self.game / 'dxgi.dll').read_bytes(), self.host)
        self.assertEqual((self.game / 'nvngx_dlssnr.dll').read_bytes(), self.model)
        for name, data in self.addons.items():
            self.assertEqual((self.game / name).read_bytes(), data)
        ini = t.ini((self.game / 'ReShade.ini').read_text(encoding='utf-8'))
        self.assertEqual(ini['RenoDX.DLSS5']['ForeignNr'], 'observe')
        self.assertEqual((ini['RenoDX.DLSS5']['NRLocalStructure'], ini['RENODX-DLSS']['DirectNeuralRenderingSkinStructureStrength']), ('0.40', '0.68'))
        self.assertTrue(nr_install.status(self.row)['installed'])
        with self.assertRaisesRegex(t.Refusal, 'already installed'):
            nr_install.prepare({}, self.row, COMBO)
        nr_install.apply({}, nr_install.prepare_remove({}, self.row))
        self.assertEqual(self.files(), before)
        self.assertFalse(nr_install.status(self.row)['installed'])

    def test_restore_keeps_the_users_reshade_settings_and_changed_files(self):
        (self.game / 'ReShade.ini').write_text('[GENERAL]\nPresetPath=.\\Mine.ini\n[RenoDX.DLSS5]\nNRLocalStructure=0.80\n', encoding='utf-8')
        nr_install.apply({}, nr_install.prepare({}, self.row, COMBO))
        text = (self.game / 'ReShade.ini').read_text(encoding='utf-8')
        text = text.replace('LoadFromDllMain=renodx-dlss.addon64', 'LoadFromDllMain=renodx-dlss.addon64,mine.addon64')
        (self.game / 'ReShade.ini').write_text(text + '[OVERLAY]\nTutorialProgress=4\n', encoding='utf-8')
        (self.game / 'renodx-dlss.addon64').write_bytes(pe(b'replaced by the user'))
        review = nr_install.prepare_remove({}, self.row)
        self.assertIn('renodx-dlss.addon64', ' '.join(review['notes']))
        nr_install.apply({}, review)
        ini = t.ini((self.game / 'ReShade.ini').read_text(encoding='utf-8'))
        self.assertEqual(ini['RenoDX.DLSS5']['NRLocalStructure'], '0.80', 'the earlier value came back')
        self.assertNotIn('ForeignNr', ini['RenoDX.DLSS5'])
        self.assertNotIn('DirectNeuralRenderingSkinStructureStrength', ini['RENODX-DLSS'] if ini.has_section('RENODX-DLSS') else {})
        self.assertEqual((ini['GENERAL']['PresetPath'], ini['OVERLAY']['TutorialProgress']), ('.\\Mine.ini', '4'))
        self.assertEqual(ini['ADDON']['LoadFromDllMain'], 'mine.addon64', 'an add-on the user listed stays')
        self.assertEqual((self.game / 'renodx-dlss.addon64').read_bytes(), pe(b'replaced by the user'))
        self.assertFalse((self.game / 'nvngx_dlssnr.dll').exists())

    def optiscaler(self, mode):
        proxy = self.game / 'dxgi.dll'; proxy.write_bytes(pe(b'OptiScaler'))
        (self.game / 'OptiScaler.ini').write_bytes(b'[Plugins]\nLoadReShade=false\n')
        self.engine.baseline = {'status': 'active', 'current': {'provider_id': 'skynizz', 'proxy': 'dxgi.dll',
                                'feature_mode': mode, 'installed_hashes': {'dxgi.dll': t.digest(proxy)}}}

    def main_review(self):
        game = SimpleNamespace(root=self.game, target_dir=self.game, exe=self.game / 'Game.exe')
        projection = {
            'payload': {'dxgi.dll': pe(b'OptiScaler'), 'OptiScaler.ini': b'[Plugins]\nLoadReShade=false\n'},
            'remove': [], 'proxy': 'dxgi.dll', 'provider': 'skynizz', 'mode': 'nr-mfg',
        }
        return {'operation': 'install', 'engine': self.engine, 'rows': [self.row],
                'plans': [{'row': self.row, 'game': game, 'package_projection': projection}]}

    def test_pre_install_review_applies_exact_split_render_after_main_package(self):
        before = self.files()
        review = self.main_review()
        choice = {'auto': True, 'model': 'old'}
        result = nr_install.revise_package_reviews({}, [review], {'revision': 1, 'choice': choice}, 'ada')
        self.assertEqual(self.files(), before)
        self.assertEqual(len(result['rows']), 1)
        self.assertIn('Environment: Skynizz (shared model)', result['rows'][0]['summary'])
        self.assertIn('Add renodx-dlss.addon64', result['rows'][0]['details'])
        self.assertNotIn('nvngx_dlssnr.dll', result['rows'][0]['details'])
        self.optiscaler('nr-mfg')
        config, plan = review['plans'][0]['split_render']
        nr_install.apply_after_package(config, plan)
        self.assertTrue(nr_install.status(self.row)['installed'])
        self.assertEqual((self.game / 'renodx-dlss.addon64').read_bytes(), self.addons['renodx-dlss.addon64'])
        self.assertIn('LoadReShade=true', (self.game / 'OptiScaler.ini').read_text(encoding='utf-8'))

    def test_split_render_rejects_main_package_drift_before_writing(self):
        review = self.main_review()
        nr_install.revise_package_reviews({}, [review], {'revision': 1, 'choice': {'auto': True, 'model': 'new'}}, 'ada')
        self.optiscaler('nr-mfg')
        (self.game / 'OptiScaler.ini').write_text('[Plugins]\nLoadReShade=true\n', encoding='utf-8')
        before = self.files()
        with self.assertRaisesRegex(t.Refusal, 'Target drift: OptiScaler.ini'):
            nr_install.apply_after_package(*review['plans'][0]['split_render'])
        self.assertEqual(self.files(), before)

    def test_review_includes_skips_for_routes_that_do_not_provide_split_render(self):
        review = self.main_review()
        adopt = {'operation': 'adopt', 'rows': [{'name': 'Another Game', 'game': str(self.game / 'another')}]}
        result = nr_install.revise_package_reviews({}, [review, adopt], {'revision': 1, 'choice': {'auto': True, 'model': 'new'}}, 'ada')
        self.assertEqual(len(result['rows']), 2)
        self.assertIn('Character detail', result['rows'][0]['summary'])
        self.assertIn('unavailable with this main package route', result['rows'][1]['reason'])

    def test_latest_review_clears_split_render_and_stale_choices_cannot_reattach_it(self):
        review = self.main_review()
        choice = {'auto': True, 'model': 'new'}
        nr_install.revise_package_reviews({}, [review], {'revision': 1, 'choice': choice}, 'ada')
        nr_install.revise_package_reviews({}, [review], {'revision': 3, 'choice': None}, 'ada')
        with self.assertRaisesRegex(ValueError, 'newer Split Render review'):
            nr_install.revise_package_reviews({}, [review], {'revision': 2, 'choice': choice}, 'ada')
        self.assertNotIn('split_render', review['plans'][0])

    def test_feeder_files_block_split_render_before_downloads_or_writes(self):
        (self.game / 'dlss5-feed.addon64').write_bytes(pe(b'Feeder hook'))
        (self.game / 'renodx-dlss5.addon64').write_bytes(pe(b'Feeder renderer'))
        before = self.files()
        choice = {'setup': COMBO, 'adapt': False}
        with (patch.object(nr_install.engine_bridge, 'module', return_value=self.engine),
              patch.object(nr_install, '_payload') as payload):
            self.assertEqual(nr_install.match_batch({}, [self.row], choice), [])
            result = nr_install.prepare_batch({}, [self.row], choice)
            self.assertEqual(result['plans'], [])
            self.assertIn('Feeder NR', result['blocked'][0]['reason'])
            payload.assert_not_called()
        self.assertEqual(self.files(), before)

    def test_lecram_never_runs_where_optiscaler_is_installed(self):
        # ReShade reloads Lecram while the game starts; each reload hooks DLSS again and
        # OptiScaler's Ray Reconstruction and frame generation fail to start (The Witcher 3).
        for mode in ('mfg-only', 'nr-mfg'):
            with self.subTest(mode=mode):
                self.optiscaler(mode)
                with self.assertRaisesRegex(t.Refusal, 'Lecram .* where OptiScaler is installed'):
                    nr_install.prepare({}, self.row, {'environment': {'addon': 'lecram'}})
        self.engine.baseline['current'].pop('feature_mode')
        with self.assertRaisesRegex(t.Refusal, 'Repair OptiScaler'):
            nr_install.prepare({}, self.row, {'character': {'addon': 'shortfuse'}})

    def test_shortfuse_adds_character_detail_beside_optiscalers_nr(self):
        # The Witcher 3: OptiScaler NR + MFG for the world, ShortFuse for characters.
        self.optiscaler('nr-mfg')
        (self.game / 'nvngx_dlssnr.dll').write_bytes(pe(b'OptiScaler NR model'))
        (self.game / 'ReShade.ini').write_text('[ADDON]\nLoadFromDllMain=other.addon64\n', encoding='utf-8')
        before = self.files()
        with self.assertRaisesRegex(t.Refusal, 'Keep Skynizz as Environment'):
            nr_install.prepare({}, self.row, {'environment': {'addon': 'shortfuse'}})
        review = nr_install.prepare({}, self.row, {'environment': {'addon': 'optiscaler'},
                                                   'character': {'addon': 'shortfuse', 'values': {'resolution_scale': 0.74}}})
        self.assertTrue(any('video-memory' in note for note in review['notes']))
        nr_install.apply({}, review)
        self.assertEqual(nr_install.status(self.row)['setup']['environment'], {'addon': 'optiscaler'}, 'Skynizz is the world')
        self.assertEqual((self.game / 'nvngx_dlssnr.dll').read_bytes(), pe(b'OptiScaler NR model'), 'OptiScaler keeps its model')
        self.assertFalse((self.game / 'renodx-dlss5.addon64').exists())
        ini = t.ini((self.game / 'ReShade.ini').read_text(encoding='utf-8'))
        self.assertEqual(ini['ADDON']['LoadFromDllMain'], 'other.addon64,renodx-dlss.addon64')
        self.assertEqual(ini['RENODX-DLSS']['DirectNeuralRenderingProcessingScale'], '74')
        self.assertIn('LoadReShade=true', (self.game / 'OptiScaler.ini').read_text(encoding='utf-8'))
        nr_install.apply({}, nr_install.prepare_remove({}, self.row))
        self.maxDiff = None
        after = self.files()
        # Settings files are compared by value: ReShade and OptiScaler rewrite their own line endings.
        self.assertIn(b'LoadReShade=false', after.pop('OptiScaler.ini'))
        ini = t.ini(after.pop('ReShade.ini').decode())
        self.assertEqual(ini['ADDON']['LoadFromDllMain'], 'other.addon64')
        self.assertFalse(ini.has_section('RENODX-DLSS') and dict(ini['RENODX-DLSS']))
        for name in ('OptiScaler.ini', 'ReShade.ini'):
            before.pop(name)
        self.assertEqual(after, before)

    def test_gitc_and_shortfuse_still_work_beside_optiscaler_mfg_only(self):
        self.optiscaler('mfg-only')
        self.addons.update({'gitc-uplift.addon64': pe(b'GITC'), 'gitc-uplift.addon32': b'32', 'gitc-uplift-helper64.exe': pe(b'helper'),
                            'Uplift.fx': b'fx', 'UpliftMask.fx': b'mask', 'LICENSE': b'MIT', 'THIRD_PARTY_NOTICES.md': b'notices'})
        for setup in ({'environment': {'addon': 'gitc'}}, {'environment': {'addon': 'shortfuse'}}):
            with self.subTest(setup=setup):
                nr_install.apply({}, nr_install.prepare({}, self.row, setup))
                self.assertEqual((self.game / 'dxgi.dll').read_bytes(), pe(b'OptiScaler'), 'OptiScaler keeps its loader')
                self.assertTrue((self.game / 'ReShade64.dll').is_file())
                nr_install.apply({}, nr_install.prepare_remove({}, self.row))
                self.assertFalse((self.game / 'ReShade64.dll').exists())

    def test_another_tools_model_or_loader_is_never_overwritten(self):
        (self.game / 'nvngx_dlssnr.dll').write_bytes(pe(b'someone else'))
        with self.assertRaisesRegex(t.Refusal, r'A different nvngx_dlssnr\.dll'):
            nr_install.prepare({}, self.row, COMBO)
        with self.assertRaisesRegex(t.Refusal, 'Feeder NR'):
            nr_install.prepare({}, dict(self.row, native_dlss=False), {'environment': {'addon': 'lecram'}})

    def test_batch_reviews_compatible_games_and_keeps_skipped_games_untouched(self):
        plain = self.game.with_name('plain')
        plain.mkdir()
        (plain / 'Game.exe').write_bytes(pe())
        unsupported = dict(self.row, name='No native DLSS', game=str(plain), native_dlss=False)
        choice = {'setup': {'environment': {'addon': 'lecram'}}, 'adapt': False}

        def eligible(config, row):
            root = Path(row['game'])
            return root, root / row['exe'], None, self.engine

        before = self.files()
        with patch.object(hdr, '_eligible', eligible):
            review = nr_install.prepare_batch({}, [unsupported, self.row], choice)
            self.assertEqual(self.files(), before)
            self.assertEqual([p['name'] for p in review['plans']], [self.row['name']])
            self.assertIn('Choose Feeder NR', review['blocked'][0]['reason'])
            self.assertIn('Environment: Lecram', review['plans'][0]['selection'])
            self.assertEqual(nr_install.apply_batch({}, review)['errors'], [])
        self.assertTrue(nr_install.status(self.row)['installed'])
        self.assertEqual(list(plain.iterdir()), [plain / 'Game.exe'])

    def test_batch_combo_resolves_against_the_installed_package(self):
        self.optiscaler('nr-mfg')
        choice = {'setup': nr_install.nr_addons.builtin_combos()['characters-and-world'], 'adapt': True}
        review = nr_install.prepare_batch({}, [self.row], choice)
        self.assertEqual(review['blocked'], [])
        plan = review['plans'][0]
        self.assertIn('Environment: Skynizz (shared model)', plan['selection'])
        self.assertIn('Character detail: ShortFuse', plan['selection'])
        self.assertFalse(any(p['path'] == 'nvngx_dlssnr.dll' for p in plan['changes']))

    def test_matches_filter_by_route_and_model_without_downloading(self):
        old = {'setup': {'environment': {'addon': 'lecram', 'model': 'old'}}, 'adapt': False}
        new = {'setup': {'environment': {'addon': 'lecram', 'model': 'new'}}, 'adapt': False}
        rows = [dict(self.row, native_dlss=False), self.row, dict(self.row, anti_cheat='detected')]
        before = self.files()
        with patch.object(nr_install.engine_bridge, 'module', return_value=self.engine), \
             patch.object(nr_install, '_fetch', side_effect=AssertionError('matching downloaded files')):
            matches = nr_install.match_batch({}, rows, old, 'ampere')
            self.assertEqual([item['index'] for item in matches], [1])
            self.assertIn('Environment: Lecram', matches[0]['summary'])
            self.assertEqual(nr_install.match_batch({}, rows, new, 'ampere'), [])
        self.assertEqual(self.files(), before)

    def test_batch_picker_filters_an_occupied_addon(self):
        (self.game / 'renodx-dlss5.addon64').write_bytes(pe(b'different renderer'))
        before = self.files()
        with (patch.object(nr_install.engine_bridge, 'module', return_value=self.engine),
              patch.object(nr_install, '_payload') as payload):
            choice = {'setup': COMBO, 'adapt': False}
            self.assertEqual(nr_install.match_batch({}, [self.row], choice), [])
            payload.assert_not_called()
        self.assertEqual(self.files(), before)

    def test_auto_matches_the_same_setup_that_batch_review_prepares(self):
        choice = {'auto': True, 'model': 'old'}
        with patch.object(nr_install.engine_bridge, 'module', return_value=self.engine):
            for mode, detail in [(None, 'Environment: Lecram'),
                                 ('mfg-only', 'Environment: ShortFuse'),
                                 ('nr-mfg', 'Character detail: ShortFuse')]:
                with self.subTest(mode=mode):
                    if mode is not None:
                        self.optiscaler(mode)
                    [match] = nr_install.match_batch({}, [self.row], choice, 'ampere')
                    result = nr_install.prepare_batch({}, [self.row], choice, 'ampere')
                    self.assertEqual(result['blocked'], [])
                    [review] = result['plans']
                    self.assertEqual(match['summary'], review['selection'])
                    self.assertIn(detail, review['selection'])
                    if mode == 'nr-mfg':
                        self.assertIn('shared model', review['selection'])
                        self.assertFalse(any(p['path'] == 'nvngx_dlssnr.dll' for p in review['changes']))
                    else:
                        self.assertIn('Model: 310.8', review['selection'])

    def test_gitc_keeps_its_model_in_its_own_folder(self):
        self.addons.update({'gitc-uplift.addon64': pe(b'GITC'), 'gitc-uplift.addon32': b'32', 'gitc-uplift-helper64.exe': pe(b'helper'),
                            'Uplift.fx': b'fx', 'UpliftMask.fx': b'mask', 'LICENSE': b'MIT', 'THIRD_PARTY_NOTICES.md': b'notices'})
        nr_install.apply({}, nr_install.prepare({}, self.row, {'environment': {'addon': 'gitc'}}))
        self.assertEqual((self.game / 'GITC-Uplift/nvngx_dlssnr.dll').read_bytes(), self.model)
        self.assertFalse((self.game / 'nvngx_dlssnr.dll').exists())
        self.assertTrue((self.game / 'reshade-shaders/Shaders/UpliftMask.fx').is_file())
        self.assertTrue((self.game / 'rtxForge-NR-Licenses/gitc-LICENSE').is_file())

    def test_archive_members_and_models_are_checked(self):
        blob = pe(b'addon')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('renodx-dlss5.addon64', blob)
        data = buffer.getvalue()
        patch.stopall()
        good = nr_install._members(data, {'renodx-dlss5.addon64': {'sha256': t.sha(blob), 'size': len(blob)}})
        self.assertEqual(good['renodx-dlss5.addon64'], blob)
        for pins in ({'renodx-dlss5.addon64': {'sha256': '0' * 64}}, {'missing.addon64': {'sha256': t.sha(blob)}}):
            with self.subTest(pins=pins), self.assertRaises(t.Refusal):
                nr_install._members(data, pins)
        small = io.BytesIO()
        with zipfile.ZipFile(small, 'w') as archive:
            archive.writestr('bin/nvngx_dlssnr.dll', blob)
        with self.assertRaisesRegex(t.Refusal, 'valid Windows library'):
            nr_install._model(small.getvalue(), {})


if __name__ == '__main__':
    unittest.main()
