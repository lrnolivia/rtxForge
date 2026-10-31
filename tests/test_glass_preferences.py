"""The manager/helper contract uses the native renderer's units and theme resets."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import glass_preferences as glass
import overlay_settings
import proton_overlay
import transactions as t


class GlassPreferencesTest(unittest.TestCase):
    def test_defaults_and_theme_materials_reach_the_real_helper_snapshot(self):
        settings = {}
        for theme, expected in [('clear',(3,20,48,50,'soft-light')),('light',(1,100,44,35,'overlay')),('dark',(2,80,48,15,'overlay'))]:
            glass.theme(settings,theme)
            result = proton_overlay.settings_snapshot(overlay_settings.options(settings))['overlay_appearance']
            tint = {'clear':'ClearTint','light':'LightTint','dark':'DarkTint'}[theme]
            self.assertEqual((result['Theme'],result[tint],result['Blur'],result['BlendStrength'],result['SurfaceBlend']),expected)
            self.assertEqual(result['Grain'],40)

    def test_custom_material_edit_then_theme_reset_keeps_type_and_layout(self):
        settings = {}
        for key,value in [('TextFont','inter'),('Layout','bar'),('Scale',120),('TextSize',26),('ClearTint',30)]:glass.edit(settings,key,value)
        self.assertEqual(glass.current(settings)['Custom'],1)
        glass.theme(settings,'clear')
        result = glass.current(json.loads(json.dumps(settings)))
        self.assertEqual((result['Custom'],result['ClearTint'],result['Layout'],result['TextFont'],result['Scale'],result['TextSize']), (0,20,'bar','inter',120,26))
        self.assertEqual(glass.DEFAULTS['TextFont'],'roboto')

    def test_unknown_options_invalid_units_and_unsupported_blends_are_refused(self):
        for value in [{'TextWeight':700},{'Scale':1.2},{'Scale':True},{'Blur':49},{'Theme':0},{'Layout':'unified'},{'SurfaceBlend':'reserved'},{'TextFont':'aptos'}]:
            with self.subTest(value=value),self.assertRaises(t.Refusal):glass.validate(value)

    def test_no_explicit_appearance_leaves_native_saved_preferences_intact(self):
        self.assertEqual(proton_overlay.settings_snapshot({})['overlay_appearance'],{})
        source={'overlay_appearance':{'Layout':'centered'}}
        snapshot=overlay_settings.options(source)
        snapshot['overlay_appearance']['Layout']='bar'
        self.assertEqual(source['overlay_appearance']['Layout'],'centered')


if __name__=='__main__':unittest.main()
