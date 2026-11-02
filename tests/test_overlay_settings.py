from pathlib import Path
import sys
import unittest
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import overlay_settings as overlay
import transactions as t


class OverlaySettingsTest(unittest.TestCase):
    def test_native_shortcuts_use_installed_game_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'bin';folder.mkdir()
            (folder/'OptiScaler.ini').write_text('[Menu]\nShortcutKey=0x77\n')
            (folder/'ReShade.ini').write_text('[INPUT]\nKeyOverlay=36,1,0,0\n')
            values=overlay.native_shortcuts({},root,'bin/game.exe')
            self.assertEqual(values,[{'name':'OptiScaler','key':'F8','enabled':True},{'name':'ReShade','key':'Ctrl+Home','enabled':True}])
            self.assertFalse(overlay.native_shortcuts({'reshade_ui':False},root,'bin/game.exe')[1]['enabled'])
            (folder/'OptiScaler.ini').write_text('[Menu]\nShortcutKey=0\n')
            self.assertEqual(overlay.native_shortcuts({},root,'bin/game.exe')[0],{'name':'OptiScaler','key':'Insert','enabled':False})

    def test_native_onboarding_is_local_unless_default_explicitly_selected(self):
        game=str(Path('one').resolve())
        settings={'overlay_renderer':'game','game_overlay_settings':{str(Path('two').resolve()):{'overlay_renderer':'game'}}}
        local=overlay.native_overlays(settings,game)
        self.assertEqual(local['overlay_renderer'],'game')
        self.assertEqual(overlay.effective(local,game)['overlay_renderer'],'optiscaler')
        self.assertEqual(overlay.effective(local,'three')['overlay_renderer'],'game')
        global_default=overlay.native_overlays(settings,game,True)
        self.assertEqual(overlay.effective(global_default,'three')['overlay_renderer'],'optiscaler')
        self.assertEqual(overlay.effective(global_default,'two')['overlay_renderer'],'game')
        self.assertEqual(settings['game_overlay_settings'][str(Path('two').resolve())],{'overlay_renderer':'game'})
        restored=overlay.game_edit(local,game,'overlay_renderer','game')
        self.assertEqual(overlay.effective(local|{'game_overlay_settings':restored},game)['overlay_renderer'],'game')
        with self.assertRaises(t.Refusal):overlay.native_overlays(settings,game,'yes')

    def test_per_game_choices_do_not_leak_to_another_game(self):
        game = str(Path('game-a').resolve())
        settings = {'overlay_welcome': True, 'game_overlay_settings': {game: {
            'overlay_welcome': False, 'overlay_welcome_position': 'bottom-right', 'panel_hotkey': 'End'}}}
        self.assertFalse(overlay.effective(settings, game)['overlay_welcome'])
        self.assertEqual(overlay.effective(settings, game)['panel_hotkey'], 'End')
        self.assertTrue(overlay.effective(settings, str(Path('game-b').resolve()))['overlay_welcome'])
        self.assertEqual(settings['overlay_welcome'], True)

    def test_game_appearance_does_not_replace_defaults(self):
        settings={'overlay_appearance':{'Theme':3},'panel_hotkey':'Delete'}
        game=str(Path('one').resolve())
        settings['game_overlay_settings']=overlay.game_edit(settings,game,'overlay_appearance',{'Theme':1,'AccentMode':'custom','AccentColor':'#3B8CCF'})
        settings['game_overlay_settings']=overlay.game_edit(settings,game,'panel_hotkey','F8')
        self.assertEqual(overlay.effective(settings,game)['overlay_appearance']['Theme'],1)
        self.assertEqual(overlay.effective(settings,'two')['overlay_appearance'],{'Theme':3})
        self.assertEqual(settings['panel_hotkey'],'Delete')
        with self.assertRaises(t.Refusal):overlay.game_edit(settings,game,'overlay_helper',False)

    def test_runtime_binding_stays_validated(self):
        self.assertEqual(overlay.shortcut_binding({'key':119,'modifiers':2}),('panel_hotkey','Ctrl+F8'))
        self.assertEqual(overlay.shortcut_binding({'key':0,'modifiers':0}),('panel_hotkey','Disabled'))
        for value in ({'key':46,'modifiers':3},{'key':-1,'modifiers':0},{'key':119,'modifiers':8}):
            with self.assertRaises((t.Refusal,ValueError)):overlay.shortcut_binding(value)

    def test_invalid_choices_refuse(self):
        for changes in ({'overlay_welcome': 1}, {'overlay_renderer': 'unknown'},
                        {'overlay_welcome_position': 'outside'}, {'overlay_theme': 'unknown'}, {'panel_hotkey': 'Ctrl+Alt+Delete'}):
            with self.subTest(changes=changes), self.assertRaises((t.Refusal, ValueError)):
                overlay.options(changes)

    def test_review_includes_menu_and_startup_choices(self):
        text = overlay.describe(overlay.DEFAULTS)
        for label in ('Overlay:', 'Welcome message:', 'Welcome position:', 'rtxForge shortcut:',
                      'OptiScaler menu:', 'ReShade welcome:', 'Native Vulkan MFG menu:'):
            self.assertIn(label, text)

    def test_overlay_theme_is_reviewed_and_isolated_per_game(self):
        first, second = str(Path('one').resolve()), str(Path('two').resolve())
        for theme in ('clear', 'dark', 'light', 'app'):
            settings = {'game_overlay_settings': {first: {'overlay_theme': theme}}}
            self.assertEqual(overlay.effective(settings, first)['overlay_theme'], theme)
            self.assertEqual(overlay.effective(settings, second)['overlay_theme'], 'clear')
            self.assertIn('Appearance:', overlay.describe(overlay.effective(settings, first)))


if __name__ == '__main__':
    unittest.main()
