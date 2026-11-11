import contextlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nr_install
import reshade_ui_settings as menus
import transactions as t


class ReShadeUiSettingsTest(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(temp).resolve() / 'game'
        self.root.mkdir()
        (self.root / 'game.exe').write_bytes(b'game')
        self.row = {'game': str(self.root), 'exe': 'game.exe'}
        self.host = self.root / 'ReShade64.dll'
        self.host.write_bytes(b'managed ReShade')
        self.ini = self.root / 'ReShade.ini'
        self.initial = (b'\xef\xbb\xbf[INPUT]\r\nKeyOverlay=45,1,0,0\r\nGamepadNavigation=1\r\n'
                        b'[OVERLAY]\r\nTutorialProgress=0\r\n[RenoDX.DLSS5]\r\nUiWelcomed=0\r\nNeuralUplift=1\r\n')
        self.ini.write_bytes(self.initial)
        receipt = nr_install._receipt(self.row)
        receipt.parent.mkdir()
        receipt.write_text(json.dumps({'schema':1, 'route':'optiscaler', 'ini':{}, 'setup':{},
                                       'host':self.host.name, 'files':{self.host.name:t.digest(self.host)}}))
        self.running = True
        self.engine = self.enterContext(patch.object(menus.engine_bridge, 'module')).return_value
        self.engine.mutation_lock.side_effect = contextlib.nullcontext
        self.engine._running_processes_under_root.side_effect = lambda _: self.running
        self.enterContext(patch.object(menus.feeder_provider, 'state', return_value=None))
        self.enterContext(patch.object(menus.renodx_hdr, '_managed', return_value=None))
        self.enterContext(patch.object(menus.storage, 'storage', return_value=Path(temp) / 'state'))

    def read(self):
        return t.ini(self.ini.read_text(encoding='utf-8-sig'))

    def test_deferred_edits_merge_and_keep_render_settings(self):
        self.assertTrue(menus.stage({}, self.row, {'reshade_ui':False})['pending'])
        self.assertTrue(menus.stage({}, self.row, {'reshade_intro':False})['pending'])
        self.assertEqual(menus.flush({}), {'applied':0})
        self.assertEqual(self.ini.read_bytes(), self.initial)
        self.running = False
        self.assertEqual(menus.flush({}), {'applied':1})
        saved = self.read()
        self.assertEqual(saved.get('INPUT', 'KeyOverlay'), '0,0,0,0')
        self.assertEqual(saved.get('INPUT', 'GamepadNavigation'), '0')
        self.assertEqual(saved.get('OVERLAY', 'TutorialProgress'), '4')
        self.assertTrue(saved.getboolean('rtxForge.UI', 'QuietStartup'))
        self.assertTrue(saved.getboolean('RenoDX.DLSS5', 'UiWelcomed'))
        self.assertTrue(saved.getboolean('RenoDX.DLSS5', 'NeuralUplift'))
        self.assertTrue(self.ini.read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertEqual(menus.flush({}), {'applied':0})
        menus.stage({}, self.row, {'reshade_ui':True})
        menus.flush({})
        self.assertEqual(self.read().get('INPUT', 'KeyOverlay'), '45,1,0,0')
        self.assertEqual(self.read().get('INPUT', 'GamepadNavigation'), '1')
        self.assertEqual(self.read().get('OVERLAY', 'TutorialProgress'), '4')

    def test_changed_host_is_left_untouched_after_staging(self):
        menus.stage({}, self.row, {'reshade_ui':False})
        self.host.write_bytes(b'foreign replacement')
        self.running = False
        self.assertEqual(menus.flush({}), {'applied':0})
        self.assertEqual(self.ini.read_bytes(), self.initial)
        self.assertFalse(menus.stage({}, self.row, {'reshade_ui':False})['managed'])

    def test_intro_only_keeps_the_menu_binding(self):
        self.running = False
        menus.stage({}, self.row, {'reshade_intro':False})
        menus.flush({})
        self.assertEqual(self.read().get('INPUT', 'KeyOverlay'), '45,1,0,0')
        self.assertEqual(self.read().get('INPUT', 'GamepadNavigation'), '1')


if __name__ == '__main__':
    unittest.main()
