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
        found = re.search(r"passes = @\{ ini = 'NRPasses'; max = (\d+) \}", build)
        self.assertIsNotNone(found)
        self.assertEqual(int(found.group(1)), feeder_provider.TUNING['passes'][2])

    def test_passes_is_one_stepper_everywhere(self):
        import json
        controls = json.loads(source('providers/skynizz-bridge/controls.json'))['controls']
        passes = next(c for c in controls if c['key'] == 'passes')
        # A − count + stepper, not a fixed list of choices.
        self.assertEqual(passes['kind'], 'stepper')
        self.assertNotIn('values', passes)
        self.assertIn('Kind::stepper', source('providers/skynizz-bridge/ForgePanel.h'))
        self.assertIn('field.Kind == "stepper"', source('windows/RtxForge.Windows/Controls/PresetControlsView.cs'))

    def test_feeder_tunes_passes_two_to_four(self):
        build = source('windows/build/Build-FeederPanel.ps1')
        self.assertIn('foreach ($pass in 2..4)', build)
        self.assertIn("-replace '^pass3_', 'pass4_'", build)
        self.assertIn('id="pass-4"', source('prototypes/overlay-rmlui/overlay.rml'))
        self.assertIn('pass4_strength', source('windows/overlay-rmlui/GlassRuntime.cpp'))

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

    def test_optiscaler_reaches_eight_passes(self):
        import json
        controls = json.loads(source('providers/skynizz-bridge/controls.json'))['controls']
        passes = next(c for c in controls if c['key'] == 'passes')
        self.assertEqual(passes['max'], 8)
        for patch in ('ada-mfg.patch', 'panel-candidate.patch'):
            self.assertIn('request.passes <= 8', source('providers/skynizz-bridge/' + patch))
            self.assertNotIn('request.passes <= 3', source('providers/skynizz-bridge/' + patch))
        self.assertIn('1 <= value <= 8 if key == \'passes\'', source('windows/engine-host/companion_controls.py'))


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
        self.assertIn('The effects reloaded before', effects)
        self.assertIn('id="effects-result"', source('prototypes/overlay-rmlui/overlay.rml'))

    def test_effects_entry_does_not_crowd_hdr(self):
        rml = source('prototypes/overlay-rmlui/overlay.rml')
        actions = rml[rml.index('<div class="window-actions">'):rml.index('id="open-settings"')]
        self.assertIn('id="open-hdr"', actions)
        self.assertNotIn('id="open-effects"', actions)
        section = rml[rml.index('<section id="effects-section"'):]
        self.assertIn('id="open-effects"', section[:section.index('</section>')])
        self.assertIn('<span class="button-label">Effects</span>', rml)
        self.assertNotIn('>ReShade<', rml)
        self.assertIn('"EFFECTS"', source('providers/glass-overlay/OverlayController.h'))


class RenoDXLiveInterface(unittest.TestCase):
    def test_export_bounds_match_the_helper(self):
        live = source('providers/renodx-dlss5/rtxforge_live.hpp')
        bounds = {key: (float(lo), hi) for key, lo, hi in
                  re.findall(r'\{"(NR\w+)", (-?[\d.]+)f, ([^,]+), (?:true|false)\}', live)}
        # Passes 2-4 come from one macro row per key.
        for name, lo, hi in re.findall(r'\{"NRPass" #n "(\w+)", (-?[\d.]+)f, ([^,]+), (?:true|false)\}', live):
            for n in (2, 3, 4):
                bounds[f'NRPass{n}{name}'] = (float(lo), hi)
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

    def test_glass_hosts_renodx_corner_hud(self):
        # RenoDX's pill and issue notices (e.g. vram_over_budget) reach the
        # glass toast, and RenoDX skips its own HUD only while glass hosts it.
        live = source('providers/renodx-dlss5/rtxforge_live.hpp')
        self.assertIn('RenoDXNrHudV1Get(RenoDXNrHudV1* out)', live)
        self.assertIn('RenoDXNrHudV1Host(bool hosted)', live)
        self.assertIn('out->size != sizeof(RenoDXNrHudV1)', live)
        self.assertIn('inline std::atomic_bool rtxforge_hud_hosted{false};',
                      source('providers/renodx-dlss5/renodx_compat.hpp'))
        build = source('providers/renodx-dlss5/Build-RenoDXCandidate.ps1')
        self.assertIn('if (rtxforge_hud_hosted.load(std::memory_order_relaxed)) return;', build)
        self.assertIn("'RenoDXNrHudV1Get', 'RenoDXNrHudV1Host'", build)
        self.assertIn('expected 1', build)
        glass = source('windows/overlay-rmlui/GlassRuntime.cpp')
        self.assertIn('GetProcAddress(module,"RenoDXNrHudV1Get")', glass)
        self.assertIn('HostRenoDXHud(renodxHud&&c.showNotifications&&c.primaryMenu!="optiscaler");', glass)
        self.assertIn('renodxHost(false)', glass)
        # Both sides must lay the struct out the same way.
        self.assertIn('uint32_t size;int32_t kind;uint64_t sequence;char slug[48];char title[160];'
                      'char detail[200];char fix[240];uint32_t others;', glass)
        for field in ('uint32_t size;', 'int32_t kind;', 'uint64_t sequence;', 'char slug[48];',
                      'char title[160];', 'char detail[200];', 'char fix[240];', 'uint32_t others;'):
            self.assertIn(field, live)

    def test_feeder_installs_the_published_live_build(self):
        import json
        spec = json.loads(source('providers/renodx-dlss5/source.json'))
        lock = json.loads(source('providers/feeder.json'))
        runtime = json.loads(source('providers/feeder-runtime.json'))
        renodx = next(s for s in runtime['sources'] if 'renodx-dlss5.addon64' in s['members'].values())
        self.assertIn('/releases/download/' + spec['release_tag'] + '/', renodx['url'])
        self.assertEqual(lock['version'], runtime['recipe'])
        # rtxforge-3: rtxforge-2's live tuning plus the corner HUD export glass hosts.
        self.assertEqual(lock['assets']['renodx-dlss5.addon64']['sha256'],
                         '07d306db5f0e3f187e3e23dafd95c69517308ce35e6872dca3ff4438bc9412f8')
        # Games installed with stock rc10, rtxforge-1 or rtxforge-2 keep passing checks until updated.
        previous = {item['sha256'] for item in lock['previous_assets']['renodx-dlss5.addon64']}
        self.assertIn('7fdc1872b5a8553a746b08538fd74990b374a7bcdd5c2c342786a093de6cba74', previous)
        self.assertIn('dcd93881e976ad033d83c2bb01f4bc3e4ddc59c15fe0dd4ca165bc5fc7d1ac68', previous)
        self.assertIn('1e4823637965d3e01ff4840a222a5853fec191b2fa0c9001e2076b5bcf25fdd5', previous)


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


class BarPresetRow(unittest.TestCase):
    def test_bar_keeps_its_row_gap_when_a_game_shows_presets(self):
        # The stylesheet hides presets in Bar, but the live controller shows the
        # row inline once a game lacks NR or FG (Mass Effect has no FG). It then
        # needs the same gap as the sections below it, not to touch the header.
        rcss = source('prototypes/overlay-rmlui/overlay.rcss')
        self.assertIn('.layout-bar .overview .preset-row { margin-top: 24dp; }', rcss)
        self.assertIn('.layout-bar .tuning-sections { margin-top: 24dp; }', rcss)
        controller = source('providers/glass-overlay/OverlayController.h')
        self.assertIn('Element("presets")->GetParentNode()->SetProperty("display",nr||fg?"flex":"none");', controller)


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
