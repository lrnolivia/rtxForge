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
        get = re.search(r'float Get\(const char \*key, float fallback\) \{([^}]*)\}', shim).group(1)
        self.assertNotIn('toggleTarget', get)

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


class FeederHelperTruth(unittest.TestCase):
    def test_desktop_status_never_claims_live_tuning(self):
        helper = source('windows/engine-host/feeder_controls.py')
        self.assertIn("'can_edit': False", helper)
        self.assertIn('tuning applies the next time the game starts', helper)
        self.assertIn('File status does not establish live activity.', helper)
        self.assertIn('ForgePanel::liveTuning = false;', source('windows/feeder-panel/panel.cpp'))


if __name__ == '__main__':
    unittest.main()
