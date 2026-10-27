"""Set Up for Linux does what made Skynizz work under Proton, and Remove undoes exactly that."""
from pathlib import Path
from types import SimpleNamespace
import sys, tempfile, unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / 'tests'))
import stack_fixture as fx
from test_steam_open_install import FakeEngine
import engine_bridge, proton_overlay, proton_prefix, cross_os, transactions as t
import universal_mfg_provider as universal


@unittest.skipUnless(sys.platform.startswith('linux'), 'Set Up for Linux runs on Linux')
class LinuxSetupEngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        library = root / 'SteamLibrary'
        self.lib = fx.proton(root, name='cachyos-rtxmg-test')
        self.prefix = fx.prefix(library, 3669870, self.lib)
        self.registry = (self.prefix / 'user.reg').read_text()
        self.settings_file = self.lib.parent.parent / 'user_settings.py'
        self.target = library / 'steamapps' / 'common' / 'CONTROL Resonant'
        (self.target / 'OptiScaler' / 'plugins').mkdir(parents=True)
        (self.target / 'CONTROLResonant.exe').write_bytes(b'MZ')
        (self.target / 'winmm.dll').write_bytes(b'bridge')
        (self.target / universal.PLUGIN).write_bytes(b'plugin')
        with patch.object(cross_os, 'THIS_OS', 'windows'):
            cross_os.write(self.target, 'windows', ['winmm.dll', universal.PLUGIN], {'id': 'skynizz', 'name': 'Skynizz', 'version': '1'},
                           'nr-mfg', 'winmm.dll')
        self.e = FakeEngine(root)
        self.g = SimpleNamespace(name='CONTROL Resonant', root=self.target, target_dir=self.target, appid='3669870',
                                 exe=self.target / 'CONTROLResonant.exe')
        self.row = {'name': 'CONTROL Resonant', 'game': str(self.target), 'exe': 'CONTROLResonant.exe', 'appid': '3669870'}
        self.settings = {'game_accents': {str(self.target): '#E4A87F'}}
        self.idle = patch.object(proton_prefix, 'prefix_in_use', return_value=False)
        self.idle.start()

    def tearDown(self):
        self.idle.stop()
        self.tmp.cleanup()

    def plan(self):
        record = engine_bridge.windows_install(self.e, self.g, None)
        prefix, names = engine_bridge.proton_setup(self.e, self.g, record)
        extras, notes = engine_bridge.linux_extras({}, self.g, self.row, self.settings, prefix, record['feature_mode'])
        return {'game': self.g, 'row': self.row, 'preview': {}, 'fingerprint': engine_bridge.fingerprint(self.e, self.g),
                'prefix': str(prefix), 'linux_setup': names, 'linux_extras': extras}, notes

    def review(self, operation, plan):
        return {'engine': self.e, 'operation': operation, 'plans': [plan], 'payload': {}, 'meta': {}, 'nr': None, 'nrmeta': None,
                'mode': 'nr-mfg', 'enable_effects': True, 'nr_strength': 2.0, 'mfg_multiplier': 'auto', 'sharpening_strength': 0.5}

    def test_set_up_writes_override_cuda_panel_and_identity_and_remove_undoes_them(self):
        plan, notes = self.plan()
        self.assertTrue(any('every game that uses cachyos-rtxmg-test' in note for note in notes), notes)
        self.assertFalse(self.settings_file.exists(), 'review writes nothing')
        engine_bridge.execute(self.review('install', plan))
        text = (self.prefix / 'user.reg').read_text()
        self.assertEqual(proton_prefix.read_overrides(text)['winmm'], 'native,builtin')
        self.assertIn('"PROTON_NVIDIA_NVCUDA": "1"', self.settings_file.read_text())
        identity = proton_overlay.read_values(text, proton_overlay.GAMES_KEY)
        self.assertTrue(identity and all(v == '"#E4A87F|CONTROL Resonant"' for v in identity.values()), identity)
        self.assertEqual((self.target / 'winmm.dll').read_bytes(), b'bridge', 'game files are not touched')
        remove = dict(plan, prefix=None, linux_setup=None, linux_extras=None, linux_setup_remove=True)
        engine_bridge.execute(self.review('uninstall', remove))
        self.assertFalse(self.settings_file.exists())
        after = (self.prefix / 'user.reg').read_text()
        self.assertEqual(proton_prefix.read_overrides(after), proton_prefix.read_overrides(self.registry))
        self.assertEqual(proton_overlay.read_values(after, proton_overlay.GAMES_KEY), {})

    def test_a_failure_after_the_cuda_write_puts_it_back(self):
        plan, _ = self.plan()
        with patch.object(proton_prefix, 'apply', side_effect=OSError('disk full')), \
                self.assertRaisesRegex(t.Refusal, 'put back as they were'):
            engine_bridge.execute(self.review('install', plan))
        self.assertFalse(self.settings_file.exists())
        self.assertEqual((self.prefix / 'user.reg').read_text(), self.registry)


if __name__ == '__main__':
    unittest.main()
