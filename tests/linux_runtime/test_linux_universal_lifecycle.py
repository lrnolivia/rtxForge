"""Fresh Skynizz bridge + Universal MFG Unlocker install under Proton, end to end on fixtures.

The real engine and desktop bridge install into a disposable Steam-library
layout with a fixture Proton prefix and a fake NVIDIA/Proton stack. Every DLL
is synthetic, nothing is launched, and no real Steam, prefix or game is read
or written. This proves file placement, INI ownership, the Proton override,
refusals and exact restore. It is not runtime evidence.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_fixture as fx
import engine_bridge, packages, proton_prefix, proton_stack, proton_mfg, cross_os
import skynizz_provider
import universal_mfg_provider as universal
import transactions as t

spec = importlib.util.spec_from_file_location('skynizz_fixtures', fx.ROOT / 'tests/test_skynizz_provider.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)

PLUGIN = fixtures.pe() + b'universal mfg fixture plugin'


class LinuxUniversalLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.root = root
        self.proc, self.wine = fx.driver(root)
        self.lib = fx.proton(root)
        self.library = root / 'SteamLibrary'
        self.prefix = fx.prefix(self.library, 870780, self.lib)
        self.target = self.library / 'steamapps' / 'common' / 'Control'
        self.target.mkdir(parents=True)
        (self.target / 'Control_DX12.exe').write_bytes(fixtures.pe())
        (self.target / 'nvngx_dlss.dll').write_bytes(fixtures.pe())
        (self.target / 'nvngx_dlssg.dll').write_bytes(fixtures.pe())
        (self.target / 'save.dat').write_bytes(b'untouched')
        self.before = self.files()
        self.registry_before = (self.prefix / 'user.reg').read_bytes()
        self.model = root / 'model.dll'
        self.model.write_bytes(fixtures.pe() + b'0' * (32 * 1024 ** 2))
        archive = root / 'combined.zip'
        self.release = fixtures.bridge_fixture(archive, root / 'production-sr.dll')
        self.config = {'storage': {'root': str(root / 'state'), 'reserve_bytes': 0}}
        component = universal.pinned()
        known = {'1.6.1': (component['commit'], component['sha256'], component['release_size'],
                           hashlib.sha256(PLUGIN).hexdigest(), len(PLUGIN))}
        # The real pinned identity, with only the DLL digest swapped for the fixture plugin's.
        fixture_component = dict(component, dll={'sha256': hashlib.sha256(PLUGIN).hexdigest(), 'size': len(PLUGIN)})
        original_module = engine_bridge.module

        def module(*args, **kwargs):
            e = original_module(*args, **kwargs)
            e._running_processes_under_root = lambda game_root: []
            e._nr_runtime_candidates = lambda explicit=None: [Path(explicit)] if explicit else []
            e.original_archive_loader = lambda source: ({'OptiScaler/streamline/sl.interposer.dll': fixtures.pe(),
                                                         'OptiScaler/streamline/sl.dlss_g.dll': fixtures.pe(),
                                                         'OptiScaler/nvngx_dlssg.dll': fixtures.pe()}, {})
            e.steam_running = lambda: True            # Steam open: the prefix route
            e.choose_steam_user_config = lambda *a, **k: None
            e.restore_launch_options_batch = lambda *a, **k: []
            e.sync_launch_options_batch = lambda *a, **k: self.fail('Steam launch options must not be touched')
            return e

        def download(url, *args, **kwargs):
            if url.startswith('https://raw.githubusercontent.com/NVIDIA/DLSS/'):
                name = Path(url).name
                return root / ('production-sr.dll' if name == 'nvngx_dlss.dll' else 'production-' + name)
            return archive

        def plugin_payload(config, record):
            universal.validate(record)
            return {universal.PLUGIN: PLUGIN, 'OptiScaler/licenses/MFG-Unlocker-LICENSE.txt': b'fixture license',
                    'OptiScaler/licenses/MFG-Unlocker-NOTICE.md': b'fixture notice'}

        self.patches = [
            patch.dict(os.environ, {'RTXFORGE_DLSS_UNLOCKED_STATE': str(root / 'engine-state')}),
            patch.object(engine_bridge, 'module', module),
            patch.object(packages, 'download', download),
            patch.object(skynizz_provider, 'bundled_bridge', lambda selection='latest': (dict(self.release, selected_source=selection), archive)),
            patch.object(universal, 'KNOWN', known),
            patch.object(universal, 'pinned', lambda: universal.validate(fixture_component)),
            patch.object(universal, 'load_payload', plugin_payload),
            patch.multiple(proton_stack, DRIVER_ROOT=self.proc, DRIVER_WINE_DIRS=(str(self.wine),)),
            patch.object(cross_os, 'THIS_OS', 'linux'),
            patch.object(proton_prefix, 'prefix_in_use', lambda prefix, proc=None: False),
        ]
        for item in self.patches:
            item.start()
        self.settings = {'runtime_provider': 'skynizz', 'skynizz_version': 'latest', 'nr_runtime': str(self.model),
                         'manage_dlss_files': False, 'mfg_provider': 'universal', 'skynizz_proton': True,
                         'mfg_multiplier': 4, 'dynamic_mfg': 0, 'mfg_saved_mode': 1, 'mfg_saved_multiplier': 4}

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def files(self):
        return {p.relative_to(self.target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.target.rglob('*') if p.is_file()}

    def row(self):
        return {'game': str(self.target), 'exe': 'Control_DX12.exe', 'name': 'Control', 'appid': '870780', 'source': 'Steam'}

    def prepare(self, operation='install', **changes):
        return engine_bridge.prepare(self.config, [self.row()], 'nr-mfg', operation, dict(self.settings, **changes))

    def test_install_places_exact_payload_sets_prefix_override_and_restores_exactly(self):
        review = self.prepare()
        self.assertEqual(review['blocked'], [])
        self.assertEqual(self.files(), self.before, 'review never writes')
        detail = review['rows'][0]['detail']
        self.assertIn(proton_mfg.LABEL, detail)
        self.assertIn('Universal MFG 1.6.1', detail)
        self.assertTrue(review['plans'][0]['proton_stack']['prerequisites_met'])
        self.assertFalse(review['plans'][0]['proton_stack']['runtime_verified'])
        engine_bridge.execute(review)

        self.assertEqual((self.target / universal.PLUGIN).read_bytes(), PLUGIN)
        self.assertEqual((self.target / 'save.dat').read_bytes(), b'untouched')
        ini = (self.target / 'OptiScaler.ini').read_text()
        for value in ('LoadAsiPlugins=true', 'AdaMfgUnlock=false', 'AdaBlackwellKernels=false', 'FGOutput=nofg',
                      'OverrideInterpolationCount=3', 'OverrideForceDMFG=false', 'MfgMode=1', 'MfgMultiplier=4',
                      'WorkingScale=0.65', 'LocalStructure=1.0', 'SkinStructure=1.0', 'DisableSplash=true'):
            self.assertIn(value, ini)
        # NR is off on a new install unless Enable NR on launch was chosen.
        self.assertRegex(ini, r'(?m)^Enabled=false')
        overrides = proton_prefix.read_overrides((self.prefix / 'user.reg').read_text())
        self.assertEqual(overrides.get('dxgi'), 'native,builtin')
        self.assertEqual(overrides.get('atiadlxx'), 'disabled', 'other prefix settings stay')
        e = review['engine']
        baseline = e.load_baseline(self.target)
        self.assertEqual(proton_mfg.verify(self.target, baseline), [])
        current = baseline['current']
        self.assertEqual(current['provider_id'], 'skynizz')
        self.assertEqual(current['archive']['release']['mfg_component']['id'], 'universal')
        self.assertIs(current.get('nr_on_launch'), False)
        record = cross_os.read(self.target)
        self.assertEqual(record['os'], 'linux')

        # Repair keeps the recorded component and the person's INI tuning.
        tuned = ini.replace('WorkingScale=0.65', 'WorkingScale=0.5')
        (self.target / 'OptiScaler.ini').write_text(tuned)
        engine_bridge.execute(self.prepare('repair', mfg_multiplier=6, mfg_saved_multiplier=6))
        self.assertIn('WorkingScale=0.5', (self.target / 'OptiScaler.ini').read_text())
        self.assertIn('OverrideInterpolationCount=3', (self.target / 'OptiScaler.ini').read_text())
        self.assertEqual(proton_mfg.verify(self.target, review['engine'].load_baseline(self.target)), [])

        engine_bridge.execute(self.prepare('uninstall'))
        self.assertEqual(self.files(), self.before)
        self.assertEqual((self.prefix / 'user.reg').read_bytes(), self.registry_before)

    def test_panel_preferences_in_the_prefix_are_restored_with_the_game(self):
        import linux_runtime, proton_overlay
        review = self.prepare()
        engine_bridge.execute(review)
        after_install = (self.prefix / 'user.reg').read_bytes()
        e = review['engine']
        report = linux_runtime.proton_report(dict(self.row(), native_dlssg=True))
        self.assertTrue(report['prerequisites_met'], report['user_reasons'])
        plan = linux_runtime.overlay_review(self.row(), {'overlay_renderer': 'game', 'panel_hotkey': 'Backtick'}, '#EC3D28')
        self.assertEqual((self.prefix / 'user.reg').read_bytes(), after_install, 'review never writes')
        linux_runtime.overlay_apply(e, self.row(), plan)
        values = proton_overlay.read_values((self.prefix / 'user.reg').read_text(), proton_overlay.OVERLAY_KEY)
        self.assertEqual((values['InGamePanel'], values['PanelKey']), ('dword:00000001', 'dword:000000c0'))
        engine_bridge.execute(self.prepare('uninstall'))
        self.assertEqual(self.files(), self.before)
        restored = (self.prefix / 'user.reg').read_text()
        self.assertEqual(proton_overlay.read_values(restored, proton_overlay.OVERLAY_KEY), {})
        self.assertEqual(proton_overlay.read_values(restored, proton_overlay.GAMES_KEY), {})
        self.assertEqual(proton_prefix.read_overrides(restored), {'atiadlxx': 'disabled'})

    def test_refused_without_opt_in_prerequisites_or_universal_and_nothing_changes(self):
        # Without the experimental opt-in the whole Linux request refuses up front.
        with self.assertRaisesRegex(t.Refusal, 'Windows-only'):
            self.prepare(skynizz_proton=False)
        review = self.prepare(mfg_provider='mfg-unlock')
        self.assertEqual(review['plans'], [])
        self.assertIn('Only the Universal MFG Unlocker', review['blocked'][0]['reason'])
        (self.prefix / 'drive_c/windows/system32/nvngx.dll').unlink()
        review = self.prepare()
        self.assertIn(proton_stack.REASONS['ngx-not-in-prefix'], review['blocked'][0]['reason'])
        self.assertEqual(self.files(), self.before)
        self.assertEqual((self.prefix / 'user.reg').read_bytes(), self.registry_before)

    def test_competing_unlock_and_dynamic_on_an_unsupported_game_refuse(self):
        (self.target / 'RTX40MFGCore.dll').write_bytes(b'manual unlock')
        review = self.prepare()
        self.assertIn('unmanaged MFG Unlocker', review['blocked'][0]['reason'])
        (self.target / 'RTX40MFGCore.dll').unlink()
        (self.target / universal.STATUS).write_text(json.dumps({'dynamicMfgSupportKnown': True, 'dynamicMfgSupported': False}))
        review = self.prepare(dynamic_mfg=1, mfg_saved_mode=2)
        self.assertIn("doesn't support Dynamic", review['blocked'][0]['reason'])

    def test_proton_change_between_review_and_apply_refuses_and_is_undone(self):
        review = self.prepare()
        (self.prefix / 'drive_c/windows/system32/nvapi64.dll').unlink()
        with self.assertRaisesRegex(t.Refusal, 'need attention'):
            engine_bridge.execute(review)
        before = dict(self.before)
        before.pop(cross_os.MARKER, None)
        self.assertEqual(self.files(), before)
        self.assertEqual((self.prefix / 'user.reg').read_bytes(), self.registry_before)


if __name__ == '__main__':
    unittest.main()
