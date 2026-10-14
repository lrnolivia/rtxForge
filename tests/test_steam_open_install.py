"""Installs and restores with Steam open use the game's Proton prefix, never Steam's files."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import hashlib, json, sys, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import engine_bridge, proton_prefix, cross_os, transactions as t

USER_REG = 'WINE REGISTRY Version 2\n\n[Software\\\\Wine\\\\DllOverrides] 1788804309\n"atiadlxx"="disabled"\n\n'


class FakeEngine:
    PROXY_NAMES = ('dxgi.dll', 'winmm.dll')

    def __init__(self, root, steam_running=True):
        self.STATE_ROOT = root / 'state'
        self.running = steam_running
        self.baselines = {}
        self.synced = []

    def steam_running(self): return self.running
    def target_key(self, target): return hashlib.sha1(str(target).encode()).hexdigest()[:12]
    def state_dir_for(self, target): return self.STATE_ROOT / 'targets' / self.target_key(target)
    def load_baseline(self, target): return self.baselines.get(str(target))
    def baseline_path(self, target): return target / '.rtxengine-baseline.json'
    def sha256_file(self, path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def _tree_manifest_data(self, path): return {}
    def _steam_transaction_root(self): return self.STATE_ROOT / 'steam-transactions'
    def choose_steam_user_config(self, games, assume_yes=False): return None
    def now_stamp(self): return 'now'
    def save_json_atomic(self, path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(json.dumps(data, default=str))

    @contextmanager
    def mutation_lock(self): yield

    def install_target(self, g, *args, **kwargs):
        options = 'WINEDLLOVERRIDES="winmm=n,b" %command%'
        self.baselines[str(g.target_dir)] = {'current': {'launch_options': options}}
        return {'launch_options': options}

    def _launch_record_for_game(self, g):
        current = (self.baselines.get(str(g.target_dir)) or {}).get('current') or {}
        return {'required': current['launch_options']} if current.get('launch_options') else None

    def sync_launch_options_batch(self, games, **kwargs):
        self.synced.extend(games); return [{'status': 'written'}]

    def verify_native_restore(self, baseline): pass
    def restore_launch_options_batch(self, games, assume_yes=False): return []
    def restore_target(self, g):
        self.baselines.pop(str(g.target_dir), None); return {'restored': True}


class SteamOpenInstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        library = root / 'SteamLibrary' / 'steamapps'
        self.target = library / 'common' / 'Game'
        self.target.mkdir(parents=True)
        (self.target / 'Game.exe').write_bytes(b'exe')
        self.prefix = library / 'compatdata' / '1091500' / 'pfx'
        self.prefix.mkdir(parents=True)
        (self.prefix / 'user.reg').write_text(USER_REG)
        self.e = FakeEngine(root)
        self.g = SimpleNamespace(name='Game', root=self.target, target_dir=self.target, appid='1091500', exe=self.target / 'Game.exe')
        self.idle = patch.object(proton_prefix, 'prefix_in_use', return_value=False)
        self.idle.start()

    def tearDown(self):
        self.idle.stop()
        self.tmp.cleanup()

    def plan(self, operation):
        prefix = engine_bridge.steam_open_route(self.e, self.g, operation, self.e.load_baseline(self.target))
        return {'game': self.g, 'row': {'name': 'Game'}, 'preview': {}, 'fingerprint': engine_bridge.fingerprint(self.e, self.g),
                'prefix': str(prefix) if prefix else None}

    def review(self, operation, plan):
        return {'engine': self.e, 'operation': operation, 'plans': [plan], 'payload': {}, 'meta': {}, 'nr': None, 'nrmeta': None,
                'mode': 'mfg-only', 'enable_effects': True, 'nr_strength': 2.0, 'mfg_multiplier': 'auto', 'sharpening_strength': 0.5}

    def overrides(self):
        return proton_prefix.read_overrides((self.prefix / 'user.reg').read_text())

    def test_install_with_steam_open_uses_the_prefix(self):
        plan = self.plan('install')
        self.assertEqual(plan['prefix'], str(self.prefix))
        engine_bridge.execute(self.review('install', plan))
        self.assertEqual(self.overrides()['winmm'], 'native,builtin')
        self.assertEqual(self.e.synced, [], "Steam's launch settings must not be written while Steam runs")

    def test_restore_with_steam_open_removes_exactly_that(self):
        engine_bridge.execute(self.review('install', self.plan('install')))
        engine_bridge.execute(self.review('uninstall', self.plan('uninstall')))
        self.assertEqual(self.overrides(), {'atiadlxx': 'disabled'})
        self.assertEqual((self.prefix / 'user.reg').read_text(), USER_REG)

    def test_steam_closed_keeps_launch_options(self):
        self.e.running = False
        plan = self.plan('install')
        self.assertIsNone(plan['prefix'])
        engine_bridge.execute(self.review('install', plan))
        self.assertEqual(self.e.synced, [self.g])
        self.assertNotIn('winmm', self.overrides())

    def test_steam_saved_settings_need_steam_closed_to_restore(self):
        self.e.baselines[str(self.target)] = {'steam_launch': {'kind': 'steam'}}
        with self.assertRaisesRegex(t.Refusal, 'Close Steam to restore'):
            engine_bridge.steam_open_route(self.e, self.g, 'uninstall', self.e.load_baseline(self.target))

    def test_unlaunched_and_running_games_are_blocked_per_game(self):
        self.g.appid = '42'
        with self.assertRaisesRegex(proton_prefix.PrefixError, 'Play it once'):
            engine_bridge.steam_open_route(self.e, self.g, 'install', None)
        self.g.appid = '1091500'
        with patch.object(proton_prefix, 'prefix_in_use', return_value=True):
            with self.assertRaisesRegex(t.Refusal, 'running'):
                engine_bridge.steam_open_route(self.e, self.g, 'install', None)


class CrossOsTest(SteamOpenInstallTest):
    """A Windows install in a shared game folder is recognised and adapted, not reinstalled."""

    def windows_install(self):
        (self.target / 'dxgi.dll').write_bytes(b'optiscaler')
        (self.target / 'OptiScaler').mkdir()
        (self.target / 'OptiScaler' / 'OptiScaler.ini').write_text('[FrameGen]\n')
        with patch.object(cross_os, 'THIS_OS', 'windows'):
            return cross_os.write(self.target, 'windows', ['dxgi.dll', 'OptiScaler'], {'id': 'dlss-unlocked', 'name': 'DLSS-Unlocked', 'version': 'NR-v0.9.51'},
                                  'mfg-only', 'dxgi.dll')

    def test_record_round_trip_and_tamper_check(self):
        record = self.windows_install()
        self.assertEqual(set(record['files']), {'dxgi.dll', 'OptiScaler/OptiScaler.ini'})
        self.assertEqual(cross_os.other_install(self.target, 'linux')['os'], 'windows')
        self.assertIsNone(cross_os.other_install(self.target, 'windows'))
        (self.target / 'dxgi.dll').write_bytes(b'something else')
        self.assertIsNone(cross_os.other_install(self.target, 'linux'), 'changed files are not trusted')

    def test_linux_adapts_a_windows_install_with_the_proton_setting_only(self):
        self.windows_install()
        record = engine_bridge.windows_install(self.e, self.g, None)
        prefix, names = engine_bridge.proton_setup(self.e, self.g, record)
        self.assertEqual(names, ['dxgi'])
        plan = {'game': self.g, 'row': {'name': 'Game'}, 'preview': {}, 'fingerprint': engine_bridge.fingerprint(self.e, self.g),
                'prefix': str(prefix), 'linux_setup': names}
        engine_bridge.execute(self.review('install', plan))
        self.assertEqual(self.overrides()['dxgi'], 'native,builtin')
        self.assertEqual((self.target / 'dxgi.dll').read_bytes(), b'optiscaler', 'game files are not touched')
        remove = dict(plan, prefix=None, linux_setup=None, linux_setup_remove=True)
        engine_bridge.execute(self.review('uninstall', remove))
        self.assertEqual(self.overrides(), {'atiadlxx': 'disabled'})
        self.assertTrue((self.target / cross_os.MARKER).is_file(), "Windows' record stays for Windows")


if __name__ == '__main__':
    unittest.main()
