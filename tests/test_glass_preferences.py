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
    def test_bar_position_survives_theme_layout_and_helper_snapshot(self):
        settings={}
        self.assertEqual(glass.current(settings)['BarPosition'],'bottom')
        for position in ('top','bottom'):
            glass.edit(settings,'BarPosition',position)
            glass.edit(settings,'Layout','centered')
            glass.theme(settings,'dark')
            glass.edit(settings,'Layout','bar')
            result=proton_overlay.settings_snapshot(overlay_settings.options(settings))['overlay_appearance']
            self.assertEqual(result['BarPosition'],position)
        with self.assertRaises(t.Refusal):glass.edit(settings,'BarPosition','left')

    def test_side_panel_edge_is_independent_of_theme_and_layout(self):
        settings={}
        self.assertEqual(glass.current(settings)['SidePanelSide'],'left')
        for side in ('right','left'):
            glass.edit(settings,'SidePanelSide',side)
            glass.edit(settings,'Layout','bar')
            glass.theme(settings,'light')
            result=proton_overlay.settings_snapshot(overlay_settings.options(settings))['overlay_appearance']
            self.assertEqual(result['SidePanelSide'],side)
            self.assertEqual(result['Layout'],'bar')
        with self.assertRaises(t.Refusal):glass.edit(settings,'SidePanelSide','bottom')

    def test_accent_tint_preserves_the_selected_base_and_approved_values(self):
        settings={}
        for base,character,saturation in [('clear',10,200),('light',50,200),('dark',100,94)]:
            glass.appearance(settings,base=base,tint=True)
            values=glass.current(settings)
            self.assertEqual((glass.base_theme(settings),values['Theme'],values['AccentCharacter'],values['AccentSaturation']),(base,4,character,saturation))
            glass.appearance(settings,tint=False)
            self.assertEqual(glass.base_theme(settings),base)
            self.assertNotEqual(glass.current(settings)['Theme'],4)
        glass.edit(settings,'OriginalLabels',1)
        glass.appearance(settings,base='clear',tint=True)
        self.assertEqual(glass.current(settings)['OriginalLabels'],1)

    def test_accent_saturation_round_trips_independently_and_resets(self):
        settings={};glass.theme(settings,'accent');glass.edit(settings,'AccentCharacter',85)
        for saturation in (0,65,100,200):
            glass.edit(settings,'AccentSaturation',saturation)
            actual=proton_overlay.settings_snapshot(overlay_settings.options(settings))['overlay_appearance']
            self.assertEqual((actual['AccentSaturation'],actual['AccentCharacter'],actual['Custom']),(saturation,85,0))
        for value in (-1,201,True,1.5):
            with self.subTest(value=value),self.assertRaises(t.Refusal):glass.edit(settings,'AccentSaturation',value)
        glass.theme(settings,'accent');self.assertEqual(glass.current(settings)['AccentSaturation'],100)

    def test_accent_character_round_trips_and_preserves_the_standard_theme(self):
        settings={}
        glass.theme(settings,'accent')
        self.assertEqual((glass.current(settings)['Theme'],glass.current(settings)['SurfaceBlend']),(4,'normal'))
        for character,tint in [(0,20),(50,80),(100,80)]:
            glass.edit(settings,'AccentCharacter',character)
            actual=proton_overlay.settings_snapshot(overlay_settings.options(settings))['overlay_appearance']
            self.assertEqual((actual['Theme'],actual['AccentCharacter'],actual['AccentTint'],actual['Custom']),(4,character,tint,0))
        glass.edit(settings,'AccentTint',35)
        self.assertEqual(glass.current(settings)['Custom'],1)
        glass.theme(settings,'accent')
        self.assertEqual((glass.current(settings)['AccentCharacter'],glass.current(settings)['AccentTint'],glass.current(settings)['Custom']),(35,67,0))
        for value in [-1,101,True]:
            with self.subTest(value=value),self.assertRaises(t.Refusal):glass.edit(settings,'AccentCharacter',value)

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
