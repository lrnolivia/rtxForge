"""Overlay control parity checks that need no game or GPU.

These read the shipped sources so the limits each route declares stay the same
in the helper, the generated Feeder bindings and both overlay styles. They do
not prove a renderer applied anything; see docs/overlay/control-matrix.md.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import feeder_provider  # noqa: E402


def source(path):
    return (ROOT / path).read_text(encoding='utf-8')


class FeederPassCeiling(unittest.TestCase):
    def test_bindings_match_the_helper_range(self):
        build = source('windows/build/Build-FeederPanel.ps1')
        found = re.search(r"passes = @\{ ini = 'NRPasses'; max = (\d+); values = @\(([\d, ]+)\)", build)
        self.assertIsNotNone(found)
        low, high = feeder_provider.TUNING['passes'][1:]
        self.assertEqual(int(found.group(1)), high)
        self.assertEqual([int(v) for v in found.group(2).split(',')], list(range(low, high + 1)))

    def test_glass_takes_its_ceiling_from_the_runtime(self):
        controller = source('providers/glass-overlay/OverlayController.h')
        runtime = source('windows/overlay-rmlui/GlassRuntime.cpp')
        panel = source('providers/glass-overlay/ForgeGlassPanel.h')
        # No fixed three-pass clamp may remain in the stepper or its enablement.
        self.assertNotIn('1.f,3.f)', controller)
        self.assertNotIn('passCount>=3', controller)
        self.assertNotIn('values["passes"]>=3', runtime)
        self.assertIn('float(passesMax)', controller)
        self.assertIn('__passes_max', panel)
        self.assertIn('__passes_max', runtime)

    def test_optiscaler_keeps_three_passes(self):
        import json
        controls = json.loads(source('providers/skynizz-bridge/controls.json'))['controls']
        passes = next(c for c in controls if c['key'] == 'passes')
        self.assertEqual(passes['max'], 3)
        self.assertIn('int pass=2,passesMax=3;', source('providers/glass-overlay/OverlayController.h'))


class FeederLiveToggle(unittest.TestCase):
    def test_toggle_waits_for_renodx_readback(self):
        shim = source('windows/feeder-panel/shim/Config.h')
        self.assertIn('if (Pending())', shim)
        self.assertIn('ConfirmTimeout', shim)
        self.assertIn('RenoDX did not confirm', shim)
        # Readback stays truthful: Get never reports the requested value.
        get = re.search(r'float Get\(const char \*key, float fallback\)\s*\{(.*?)\n    \}', shim, re.S).group(1)
        self.assertNotIn('toggleTarget', get)
        self.assertNotIn('rebuildTarget', get)

    def test_glass_shows_waiting_and_unconfirmed(self):
        runtime = source('windows/overlay-rmlui/GlassRuntime.cpp')
        self.assertIn('__live_state', runtime)
        self.assertIn('Waiting for the game…', runtime)
        self.assertIn('Not confirmed', runtime)
        self.assertIn('readLiveState', source('windows/feeder-panel/panel.cpp'))

    def test_restart_label_names_what_restarts(self):
        rml = source('prototypes/overlay-rmlui/overlay.rml')
        self.assertNotIn('Changes will take effect after restart', rml)
        self.assertIn('Model tuning is saved and applies after restarting the game', rml)


class ReShadeAcknowledgment(unittest.TestCase):
    def test_every_processed_edit_is_acknowledged(self):
        bridge = source('windows/feeder-panel/EffectBridge.h')
        loop = bridge[bridge.index('for(const auto& edit:edits)'):bridge.index('if(changed)runtime->save_current_preset();')]
        # A dropped edit must be refused, never silently skipped: every
        # continue but the applied text setting's follows a refusal.
        self.assertEqual(loop.count('continue;'), loop.count('refuse(edit,') + 1)
        self.assertIn('"acknowledged",ack', bridge)
        self.assertIn('edits.empty()&&GetTickCount64()-refreshed<250', bridge)

    def test_glass_keeps_edits_pending_until_acknowledged(self):
        effects = source('providers/glass-overlay/EffectControls.h')
        self.assertIn('Acknowledge(data);', effects)
        self.assertIn('Pending(index,true)', effects)
        self.assertIn('ReShade reloaded its effects before', effects)
        self.assertIn('id="effects-result"', source('prototypes/overlay-rmlui/overlay.rml'))


class RenoDXLiveInterface(unittest.TestCase):
    def test_export_bounds_match_the_helper(self):
        live = source('providers/renodx-dlss5/rtxforge_live.hpp')
        bounds = {key: (float(lo), hi) for key, lo, hi in
                  re.findall(r'\{"(NR\w+)", ([\d.]+)f, ([^,]+), (?:true|false)\}', live)}
        for key, (ini, low, high) in feeder_provider.TUNING.items():
            self.assertIn(ini, bounds, key)
            self.assertEqual(bounds[ini][0], float(low), key)
            if ini != 'NRPasses':
                self.assertEqual(float(bounds[ini][1].rstrip('f')), float(high), key)
        # NR on/off stays on RenoDX's toggle key, which also resets its latches.
        self.assertNotIn('"NeuralUplift"', live)

    def test_resolution_floor_matches_renodx(self):
        self.assertEqual(feeder_provider.TUNING['work_scale'][1], 0.33)
        self.assertIn("work_scale = @{ ini = 'NRResolutionScale'; min = 0.33; max = 1 }",
                      source('windows/build/Build-FeederPanel.ps1'))

    def test_panel_is_live_only_with_the_interface(self):
        shim = source('windows/feeder-panel/shim/Config.h')
        self.assertIn('"RenoDXNrApiVersion"', shim)
        self.assertIn('live.version == 1', shim)
        self.assertIn('RenoDXNrAppliedGenerationV1', shim)
        self.assertIn('ForgePanel::liveTuning = Config::Instance()->Live();', source('windows/feeder-panel/panel.cpp'))

    def test_candidate_never_replaces_the_pin(self):
        import json
        spec = json.loads(source('providers/renodx-dlss5/source.json'))
        self.assertTrue(spec['candidate_only'])
        self.assertFalse(spec['replaces_pinned_asset'])
        pinned = json.loads(source('providers/feeder.json'))['assets']['renodx-dlss5.addon64']['sha256']
        self.assertEqual(pinned, 'dcd93881e976ad033d83c2bb01f4bc3e4ddc59c15fe0dd4ca165bc5fc7d1ac68')


class WelcomeToast(unittest.TestCase):
    def test_prompt_stays_opposite_the_logo(self):
        # A hidden icon still matches a sibling selector, so the rule that
        # pulls the message left must require a shown icon.
        rcss = source('prototypes/overlay-rmlui/overlay.rcss')
        self.assertNotIn('\n.welcome .toast-icon + .welcome-message', rcss)
        self.assertIn('.welcome.with-icon .toast-icon + .welcome-message { margin-left: 0; }', rcss)
        controller = source('providers/glass-overlay/OverlayController.h')
        self.assertIn('Element("welcome")->SetClass("with-icon",false);', controller)
        self.assertIn('Element("welcome")->SetClass("with-icon",true);', controller)


class FeederPointer(unittest.TestCase):
    def test_glass_route_still_draws_the_software_cursor(self):
        # Glass draws no pointer; games that hide the system cursor rely on
        # ImGui's software cursor, which is drawn only by an ImGui render pass.
        panel = source('windows/feeder-panel/panel.cpp')
        draw = panel[panel.index('bool Draw(const Frame &frame)'):panel.index('void Release()')]
        self.assertIn('io.MouseDrawCursor = visible;', draw[draw.index('ForgeGlassPanel::Draw('):])
        self.assertIn('ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());', draw)


class FeederHelperTruth(unittest.TestCase):
    def test_desktop_status_never_claims_live_tuning(self):
        helper = source('windows/engine-host/feeder_controls.py')
        self.assertIn("'can_edit': False", helper)
        self.assertIn('tuning applies the next time the game starts', helper)
        self.assertIn('File status does not establish live activity.', helper)
        self.assertIn('ForgePanel::liveTuning = false;', source('windows/feeder-panel/panel.cpp'))


if __name__ == '__main__':
    unittest.main()
