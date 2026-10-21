# Linux catch-up

The Windows app reached the 1.0 Beta RC on 2026-10-21. This page tracks what the Linux (GTK4/libadwaita) app still lacks and the order to close it. Nothing here is runtime-verified on Linux yet; each step needs a live Proton smoke test before it leaves experimental.

## In place

- **Shared engine.** Universal MFG, Dynamic gating, DLSS presets, crash-durable restore and the Feeder provider live in the shared Python engine, so Linux receives them wherever Linux runs those paths.
- **Skynizz on Proton (experimental).** Settings → Graphics Provider. With it on, Linux can set up a Skynizz + Universal MFG install made on Windows in the same shared game folder. Linux adds only the Proton DLL override for that install's proxy (`WINEDLLOVERRIDES`); no game files change, and the Windows install stays restorable from either OS. Fresh Skynizz installs from Linux are still refused.

## Smoke test (on Linux)

1. Install NR + MFG (Universal) on Windows in a game on the shared drive, then boot Linux.
2. Turn on Skynizz on Proton, then install or repair that game from Linux. The review should say it adapts the Windows install and only adds the Proton setting.
3. Launch through Steam with Proton. In the game folder, `RTXMFG-Universal.status.json` and `RTXMFG-<game>.log` should show the plugin loaded and DLSS state samples reporting 4 frames presented. DLSS-G under Proton needs NVAPI; rtxForge never changes those flags.
4. Restore from Linux, then check that Windows sees the install as restored.

## Still to port

1. **Presets on the shared control schema.** The GTK Presets page still uses the old three values (NR strength, sharpening, MFG). Build it from `providers/skynizz-bridge/controls.json` plus `providers/mfg-unlocker/preset-controls.json`, the same vocabulary that drives the Windows editors and the in-game panel: Auto/Custom/Dynamic MFG, NR, image tuning, sharpening, performance and DLSS presets. Send them as `feature_controls`, as Windows does.
2. **Dynamic gating in GTK.** Show Dynamic only when the row's `dynamic_mfg_available` is true, with `dynamic_mfg_detail` as the explanation.
3. **Fresh Skynizz installs on Linux.** After the adoption path passes its smoke test, allow `skynizz_provider.require_mode('linux', …)` behind the same opt-in, reusing the y4my Proton launch-option route.
4. **Library and game page parity.** Hero focal point (move `FadedImage`'s saliency + face analysis into the shared engine; OpenCV where available), credits line, Needs Attention, Feeder storage, the narrow single-column layouts and the collapsing hero behaviour.

## Native overlay on Vulkan/Proton

The in-game panel is rendered by the Skynizz bridge inside the game, so it already draws under Proton on both D3D12 (vkd3d-proton) and Vulkan. What breaks is its helper. The panel talks to rtxForge's background helper through a named file mapping (`Local\rtxForge.panel.<pid>`) and per-game presets through `Local\rtxForge.controls.<pid>`. Both live inside Wine's object namespace, where a native Linux process cannot open them.

Plan:

1. Ship a small Windows-side relay (`rtxforge-relay.exe`, console, no UI) that the Linux app starts inside the game's own prefix (`proton run` / `wine` with the game's `WINEPREFIX`). It opens both mappings exactly as the Windows helper does and forwards the panel's JSON requests over a Unix socket to the Linux app. This relies on Wine mapping Windows `AF_UNIX` sockets to host sockets; confirm on the target Proton first, and fall back to a localhost TCP port bound to 127.0.0.1 with a per-session token if it does not.
2. The Linux app answers with the same handlers as `windows/engine-host/companion_controls.py` and `NativePanelCoordinator`: status, save, reset, presets and protocol 7 replay.
3. Until the relay exists, the panel shows "Waiting for the background helper" and its controls still apply live in-process; only Save, Reset and preset replay need the relay.
4. Verify on Linux: panel opens on the hotkey, Save persists and replays on the next launch, and Dynamic and DLSS presets round-trip.

OptiScaler's own overlay has known Proton issues, so this panel may become the only reliable in-game control surface on Linux.
