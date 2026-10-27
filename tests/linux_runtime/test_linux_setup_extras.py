"""What Set Up for Linux writes besides the proxy override: CUDA, panel preferences, identity."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_fixture as fx
import linux_runtime
import proton_overlay
import ui_colors
import universal_mfg_provider as universal


class SetupExtrasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lib = fx.proton(self.root, name='cachyos-rtxmg-test')
        self.prefix = fx.prefix(self.root / 'library', 3669870, self.lib)
        self.game = self.root / 'library' / 'steamapps' / 'common' / 'CONTROL Resonant'
        self.exe = self.game / 'CONTROLResonant.exe'
        (self.game / 'OptiScaler' / 'plugins').mkdir(parents=True)
        (self.game / universal.PLUGIN).write_bytes(b'plugin')
        self.exe.write_bytes(b'MZ')
        self.row = {'game': str(self.game), 'exe': self.exe.name, 'appid': '3669870', 'name': 'CONTROL Resonant'}
        self.settings = {'game_accents': {str(self.game): '#E4A87F'}}
        self.e = SimpleNamespace(STATE_ROOT=self.root / 'state',
                                 target_key=lambda path: hashlib.sha256(str(path).encode()).hexdigest()[:20])

    def tearDown(self):
        self.tmp.cleanup()

    def review(self, mode='nr-mfg'):
        return linux_runtime.setup_review({}, self.row, self.settings, self.prefix, self.exe, mode)

    def test_mfg_setup_turns_on_cuda_and_writes_panel_identity_then_restores(self):
        registry_before = (self.prefix / 'user.reg').read_text()
        plans, notes = self.review()
        self.assertEqual(set(plans), {'cuda', 'overlay'})
        self.assertIn('every game that uses cachyos-rtxmg-test', notes[0])
        paths = linux_runtime.setup_paths(self.e, self.game, plans)
        self.assertIn(self.lib.parent.parent / 'user_settings.py', paths)
        self.assertIn(self.prefix / 'user.reg', paths)
        linux_runtime.setup_apply(self.e, self.game, plans)
        text = (self.prefix / 'user.reg').read_text()
        games = proton_overlay.read_values(text, proton_overlay.GAMES_KEY)
        self.assertTrue(games)
        self.assertTrue(all(value == '"#E4A87F|CONTROL Resonant"' for value in games.values()), games)
        self.assertEqual(proton_overlay.read_values(text, proton_overlay.OVERLAY_KEY)['InGamePanel'], 'dword:00000001')
        self.assertTrue((self.lib.parent.parent / 'user_settings.py').is_file())
        # A second review finds nothing left to change.
        self.assertEqual(self.review()[0]['cuda']['action'], 'keep')
        result = linux_runtime.setup_restore(self.e, self.game)
        self.assertEqual(result['cuda']['status'], 'removed')
        self.assertEqual(result['overlay']['status'], 'restored')
        self.assertFalse((self.lib.parent.parent / 'user_settings.py').exists())
        self.assertEqual(proton_overlay.read_values((self.prefix / 'user.reg').read_text(), proton_overlay.GAMES_KEY), {})
        self.assertNotIn('Overlay\\\\Games', registry_before)

    def test_nr_only_and_games_without_the_plugin_never_touch_proton(self):
        self.assertNotIn('cuda', self.review('nr-only')[0])
        (self.game / universal.PLUGIN).unlink()
        self.assertNotIn('cuda', self.review()[0])

    def test_accent_is_the_users_pick_else_the_poster_else_neutral(self):
        self.assertEqual(linux_runtime.game_accent({}, self.row, self.settings), '#E4A87F')
        poster = dict(self.row, poster=str(self.root / 'poster.png'))
        with patch.object(linux_runtime, '_poster_pixels', return_value=[(228, 168, 127, 255)] * 64):
            with patch.object(ui_colors, 'signature_color', return_value='#e4a87f') as signature:
                self.assertEqual(linux_runtime.game_accent({}, poster, {}), '#e4a87f')
                signature.assert_called_once()
        with patch.object(linux_runtime, '_poster_pixels', side_effect=OSError('unreadable')):
            self.assertEqual(linux_runtime.game_accent({}, poster, {}), ui_colors.NO_ARTWORK)


if __name__ == '__main__':
    unittest.main()
