# Linux catch-up

The Windows app reached the 1.0 Beta RC on 2026-10-21. This page tracks what the Linux (GTK4/libadwaita) app still lacks and the order to close it. Nothing here is runtime-verified on Linux yet; each step needs a live Proton smoke test before it leaves experimental.

## In place

- **Shared engine.** Universal MFG, Dynamic gating, DLSS presets, crash-durable restore and the Feeder provider live in the shared Python engine, so Linux receives them wherever Linux runs those paths.
- **Skynizz on Proton (experimental).** Settings → Graphics Provider. With it on, Linux can set up a Skynizz + Universal MFG install made on Windows in the same shared game folder. Linux adds only the Proton DLL override for that install's proxy (`WINEDLLOVERRIDES`); no game files change, and the Windows install stays restorable from either OS. Fresh Skynizz installs from Linux are still refused.

- **Runtime parity layer (fixture-tested, not runtime-verified).** Branch `rtxforge/linux-runtime-parity-20261021`:
  - Fresh Skynizz + Universal MFG installs under Proton, gated per game on detected prerequisites (`proton_stack`, `proton_mfg`; see [linux/proton-prerequisites.md](linux/proton-prerequisites.md)).
  - In-game panel preferences written into each game's prefix, plus a file-backed channel prototype (`proton_overlay`; see [linux/overlay-channel.md](linux/overlay-channel.md)).
  - Engine-side operation scope (`engine_bridge.check_scope`).
  - The shared MFG preset (Auto/Custom/Dynamic plus the dormant choice) for every provider.
  - Supported-subset offers (`DesktopService.prepare_supported`).
  - One-time Global and game-menu reviews, and App Storage cleanup (`linux_runtime`).

### Engine API for the GTK app

| Call | Purpose |
|---|---|
| `DesktopService.prepare(rows, mode, operation, adopt, visual_settings, save_defaults, scope)` | `scope={'kind': 'selected'\|'filtered', 'games': [row['game'], ...]}` must equal `rows`. An empty selection refuses, except a defaults-only Presets apply. |
| `DesktopService.prepare_supported(rows, mode, 'install', adopt, visual_settings, scope)` | `review['supported'] = [{reason_code, reason, mode, nr, mfg, games, review}]`. Each offer is opt-in and is executed separately. |
| `visual_settings` MFG keys | `mfg_multiplier` ('auto', 0, 2..6), `dynamic_mfg` (0/1), `mfg_saved_mode` (0/1/2), `mfg_saved_multiplier` (2..6). Rows read them back after a scan. |
| `visual_settings['skynizz_proton']` | Experimental opt-in. Fresh installs also need every prerequisite. |
| Adoption review rows | `row['adoption'] = {detected, choices: ['adopt', 'adopt-clean'], chosen, restore_boundary: 'before-adoption'}`. Run one `prepare(..., 'adopt'\|'adopt-clean')` per choice group. |
| `linux_runtime.proton_report(row, mode)` | Read-only checks with `reasons` codes and `user_reasons` text. `runtime_verified` is always false until evidence is recorded. |
| `linux_runtime.overlay_review(row, settings, accent)` → `overlay_apply(e, row, plan)` / `overlay_restore(e, row)` | Panel preferences in the game's prefix. |
| `linux_runtime.global_review(e, {'nr', 'mfg'})`, `menus_review(e, ui_options)` → `apply_review(review)` | One-time reviewed bulk changes. |
| `linux_runtime.storage_inventory(app_root, engine_root)`, `storage_review(...)` → `storage_cleanup(..., plan)` | App Storage. |
| `linux_runtime.mfg_observation(row)`, `record_runtime_evidence(e, row, report, observed, confirmed_by)` | Plugin status as an observation, and human-confirmed evidence. |

- **Other distributions** (`rtxforge/linux-ui-parity-20261021`, 2026-10-23). CachyOS/Arch run the app with pacman's GTK4 and libadwaita. SteamOS and hosts with libadwaita older than 1.7 open it in a `rtxforge` distrobox (`--container`), and setup accepts that route. The GPU check falls back to `/proc/driver/nvidia` when `nvidia-smi` is missing or unusable. Fixture-tested Steam layouts cover SteamOS internal and SD card libraries, `~/.steam` symlinks and Flatpak Steam. See [linux/distros.md](linux/distros.md).
- **Game Mode panel shortcut.** Game Mode records the in-game panel shortcut, app-wide and per game, as Windows Game Mode does.

## Smoke test (on Linux)

1. Install NR + MFG (Universal) on Windows in a game on the shared drive, then boot Linux.
2. Turn on Skynizz on Proton, then install or repair that game from Linux. The review should say it adapts the Windows install and only adds the Proton setting.
3. Launch through Steam with Proton. In the game folder, `RTXMFG-Universal.status.json` and `RTXMFG-<game>.log` should show the plugin loaded and DLSS state samples reporting 4 frames presented. DLSS-G under Proton needs NVAPI; rtxForge never changes those flags.
4. Restore from Linux, then check that Windows sees the install as restored.

## Still to port

1. **Presets on the shared control schema.** The GTK Presets page still uses the old three values (NR strength, sharpening, MFG). Build it from `providers/skynizz-bridge/controls.json` plus `providers/mfg-unlocker/preset-controls.json`, the same vocabulary that drives the Windows editors and the in-game panel: Auto/Custom/Dynamic MFG, NR, image tuning, sharpening, performance and DLSS presets. Send them as `feature_controls`, as Windows does.
2. **Dynamic gating in GTK.** Show Dynamic only when the row's `dynamic_mfg_available` is true, with `dynamic_mfg_detail` as the explanation.
3. **Fresh Skynizz installs on Linux.** The engine now admits them per game behind the same opt-in when every Proton prerequisite is detected. They still need a real in-game Proton run on RTX 40 before any runtime claim.
4. **Library and game page parity.** Hero focal point (move `FadedImage`'s saliency + face analysis into the shared engine; OpenCV where available), credits line, Needs Attention, Feeder storage, the narrow single-column layouts and the collapsing hero behaviour.

## Native overlay on Vulkan/Proton

The in-game panel is rendered by the Skynizz bridge inside the game, so it already draws under Proton on both D3D12 (vkd3d-proton) and Vulkan. What breaks is its helper. The panel talks to rtxForge's background helper through a named file mapping (`Local\rtxForge.panel.<pid>`) and per-game presets through `Local\rtxForge.controls.<pid>`. Both live inside Wine's object namespace, where a native Linux process cannot open them.

Plan:

1. Ship a small Windows-side relay (`rtxforge-relay.exe`, console, no UI) that the Linux app starts inside the game's own prefix (`proton run` / `wine` with the game's `WINEPREFIX`). It opens both mappings exactly as the Windows helper does and forwards the panel's JSON requests over a Unix socket to the Linux app. This relies on Wine mapping Windows `AF_UNIX` sockets to host sockets; confirm on the target Proton first, and fall back to a localhost TCP port bound to 127.0.0.1 with a per-session token if it does not.
2. The Linux app answers with the same handlers as `windows/engine-host/companion_controls.py` and `NativePanelCoordinator`: status, save, reset, presets and protocol 7 replay.
3. Until the relay exists, the panel shows "Waiting for the background helper" and its controls still apply live in-process; only Save, Reset and preset replay need the relay.
4. Verify on Linux: panel opens on the hotkey, Save persists and replays on the next launch, and Dynamic and DLSS presets round-trip.

OptiScaler's own overlay has known Proton issues, so this panel may become the only reliable in-game control surface on Linux.
