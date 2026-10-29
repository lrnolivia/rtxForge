"""Adapt to Linux for Feeder NR installs made on Windows: the prefix dxgi override only."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_fixture as fx
import feeder_provider as feeder
import proton_prefix
import transactions as t
import cross_os


class FakeEngine:
    DESKTOP_PLATFORM = 'linux'
    Stop = RuntimeError

    def __init__(self, root):
        self.STATE_ROOT = root / 'state'

    def target_key(self, path): return hashlib.sha256(str(path).encode()).hexdigest()[:20]
    def _running_processes_under_root(self, root): return []
    def now_stamp(self): return 'now'
    def save_json_atomic(self, path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(json.dumps(data))
    def load_baseline(self, *a, **k): return None

    @contextmanager
    def mutation_lock(self): yield


class FeederLinuxSetupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        library = root / 'SteamLibrary'
        self.prefix = fx.prefix(library, 2208920, fx.proton(root))
        self.registry = (self.prefix / 'user.reg').read_text()
        self.game = library / 'steamapps' / 'common' / 'Assassins Creed Valhalla'
        self.game.mkdir(parents=True)
        self.files = {'ACValhalla.exe': b'MZ', 'dxgi.dll': b'reshade', 'dlss5-feed.addon64': b'feed',
                      'rtxforge-panel.addon64': b'panel', 'ReShade.ini': b'[GENERAL]\n'}
        for name, data in self.files.items():
            (self.game / name).write_bytes(data)
        self.e = FakeEngine(root)
        self.row = {'name': 'Assassin\'s Creed Valhalla', 'game': str(self.game), 'exe': 'ACValhalla.exe',
                    'appid': '2208920', 'installed_on': 'windows', 'runtime_provider': 'feeder'}
        self.patches = [patch.object(feeder, 'inspect', lambda e, row, cached=True: {'managed': False}),
                        patch.object(feeder, 'target', lambda row: (Path(row['game']), Path(row['game']) / row['exe'], Path(row['game']))),
                        patch.object(proton_prefix, 'prefix_in_use', lambda prefix, proc=None: False)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def prepare(self, operation):
        return feeder._prepare({}, [self.row], 'nr-only', operation, {}, self.e)

    def game_files(self):
        return {p.name: p.read_bytes() for p in self.game.iterdir() if p.name != cross_os.MARKER}

    def test_adapt_adds_only_the_dxgi_override_and_remove_puts_the_prefix_back(self):
        review = self.prepare('install')
        self.assertEqual(review['blocked'], [])
        self.assertIn('Adapt to Linux', review['rows'][0]['summary'])
        self.assertIn('Windows install is not touched', review['rows'][0]['summary'])
        self.assertFalse(feeder.linux_ready(self.e, self.row))
        feeder.execute(review)
        self.assertEqual(proton_prefix.read_overrides((self.prefix / 'user.reg').read_text())['dxgi'], 'native,builtin')
        self.assertEqual(self.game_files(), self.files, 'nothing in the game folder changes')
        self.assertTrue(feeder.linux_ready(self.e, self.row))
        self.assertEqual(cross_os.read(self.game)['installed_oses'], ['windows','linux'])
        self.assertEqual(cross_os.read(self.game)['provider']['id'], 'feeder')
        review = self.prepare('uninstall')
        self.assertIn('Remove Linux Setup', review['rows'][0]['summary'])
        feeder.execute(review)
        self.assertEqual((self.prefix / 'user.reg').read_text(), self.registry)
        self.assertFalse(feeder.linux_ready(self.e, self.row))
        self.assertEqual(self.game_files(), self.files)
        self.assertEqual(cross_os.read(self.game)['installed_oses'], ['windows'])

    def test_remove_without_a_linux_setup_points_to_windows(self):
        review = self.prepare('uninstall')
        self.assertEqual(review['plans'], [])
        self.assertIn('rtxForge on Windows', review['blocked'][0]['reason'])

    def test_mass_effect_games_share_one_prefix_record(self):
        me1 = dict(self.row, name='Mass Effect LE · Mass Effect 1', game=str(self.game / 'ME1'), collection_game=str(self.game))
        me2 = dict(me1, name='Mass Effect LE · Mass Effect 2', game=str(self.game / 'ME2'))
        self.assertEqual(feeder.linux_setup_state(self.e, me1), feeder.linux_setup_state(self.e, me2))
        self.row = me1
        (self.game / 'ME1').mkdir()
        for name, data in self.files.items():
            (self.game / 'ME1' / name).write_bytes(data)
        review = self.prepare('install')
        self.assertIn('shared by every Mass Effect game', review['rows'][0]['summary'])
        feeder.execute(review)
        self.assertTrue(feeder.linux_ready(self.e, me2))

    def test_a_failure_undoes_that_games_prefix_change(self):
        review = self.prepare('install')
        original = proton_prefix.apply

        def broken(prefix, names, state):
            original(prefix, names, state)
            raise OSError('disk full')
        with patch.object(proton_prefix, 'apply', broken), self.assertRaisesRegex(t.Refusal, 'Stopped after 0'):
            feeder.execute(review)
        self.assertEqual((self.prefix / 'user.reg').read_text(), self.registry)
        self.assertFalse(feeder.linux_ready(self.e, self.row))
        self.assertFalse((self.game/cross_os.MARKER).exists(), 'failed Linux setup published history')

    def test_windows_keeps_its_own_route(self):
        self.e.DESKTOP_PLATFORM = 'windows'
        with patch.object(feeder, 'eligible', side_effect=t.Refusal('Windows route')):
            review = self.prepare('install')
        self.assertEqual(review['plans'], [])
        self.assertEqual(review['blocked'][0]['reason'], 'Windows route')


if __name__ == '__main__':
    unittest.main()
