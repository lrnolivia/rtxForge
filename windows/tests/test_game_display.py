"""Display changes preserve unrelated preferences and recover real originals."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'windows/engine-host')]
import game_display as display
import transactions as t


class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = SimpleNamespace(STATE_ROOT=self.root / 'state')
        self.game = SimpleNamespace(appid='2456740', exe='inZOI-Win64-Shipping.exe', root=self.root / 'game')
        self.locations = dict(local=self.root / 'local', docs=self.root / 'docs')
        self.path, self.section, self.settings = display.target(self.game, **self.locations)
        self.path.parent.mkdir(parents=True)
        self.original = ('; keep this\r\n[' + self.section + ']\r\nFullscreenMode=0\r\nResolutionSizeX=1920\r\nResolutionSizeY=1080\r\nDLSSG_Mode=4\r\n[Other]\r\nQuality=3\r\n').encode()
        self.path.write_bytes(self.original)

    def plan(self, restore=False):
        result, description = display.prepare(self.engine, self.game, restore, **self.locations)
        self.assertIsNotNone(result, description)
        return result

    def test_install_restore_and_repeat_preserves_original_and_later_edits(self):
        display.apply(self.plan())
        text = self.path.read_bytes().decode()
        self.assertIn('FullscreenMode=1\r\n', text)
        self.assertIn('DLSSG_Mode=4\r\n', text)
        self.assertIn('ResolutionSizeX=3840\r\n', text)
        display.apply(self.plan())
        self.path.write_bytes(self.path.read_bytes().replace(b'Quality=3', b'Quality=1'))
        display.apply(self.plan(True))
        self.assertEqual(self.original.replace(b'Quality=3', b'Quality=1'), self.path.read_bytes())

    def test_restore_preserves_user_resolution_change(self):
        display.apply(self.plan())
        self.path.write_bytes(self.path.read_bytes().replace(b'ResolutionSizeX=3840', b'ResolutionSizeX=2560'))
        display.apply(self.plan(True))
        self.assertIn(b'ResolutionSizeX=2560', self.path.read_bytes())
        self.assertIn(b'FullscreenMode=0', self.path.read_bytes())

    def test_review_drift_refuses_before_write(self):
        plan = self.plan()
        self.path.write_bytes(self.original + b'; concurrent change\r\n')
        with self.assertRaises(t.Refusal):
            display.apply(plan)
        self.assertFalse(plan['record_path'].exists())

    def test_missing_or_unknown_settings_are_skipped(self):
        self.path.unlink()
        plan, message = display.prepare(self.engine, self.game, **self.locations)
        self.assertIsNone(plan)
        self.assertIn('skipped', message)
        self.game.appid = 'unknown'
        self.game.exe = 'unknown.exe'
        self.assertIsNone(display.target(self.game, **self.locations))

    def test_other_schemas_only_change_display(self):
        for appid, exe, section, data in [
            ('292030', 'witcher3.exe', 'Viewport', 'FullScreenMode=1\nResolution="1920x1080"\nReflexMode=1\n'),
            ('1716740', 'Starfield.exe', 'Display', 'iSize W=1920\niSize H=1080\nbFull Screen=1\nbBorderless=0\nfGamma=2.4\n')]:
            self.game.appid, self.game.exe = appid, exe
            self.game.root = self.root / appid
            path, _, _ = display.target(self.game, **self.locations)
            path.parent.mkdir(parents=True)
            original = ('[' + section + ']\n' + data).encode()
            path.write_bytes(original)
            display.apply(self.plan())
            self.assertIn(b'3840', path.read_bytes())
            display.apply(self.plan(True))
            self.assertEqual(original, path.read_bytes())


if __name__ == '__main__':
    unittest.main()
