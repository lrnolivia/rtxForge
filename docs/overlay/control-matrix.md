# Overlay control matrix

What each in-game control actually does on each route, as of main `3fd8952`.
Read it as "what the renderer confirms", not "what the panel
shows". A saved value, a queued edit, a requested multiplier or
`liveTuning=true` is not proof that a frame was rendered differently, and none
of it is an FPS measurement.

## States

| State | Meaning |
| --- | --- |
| **Live, confirmed** | Changed in the running renderer, and the overlay reads the value back from that renderer. |
| **Live, unconfirmed** | Sent to the running renderer, which has no readback. The overlay shows the request only. |
| **Saved, restart** | Written to the route's config. The renderer loads it at the next game start. |
| **Startup only** | Read once when the game starts; the overlay doesn't edit it in game. |
| **Unsupported** | The route has no such control. The overlay disables or hides it. |
| **Unavailable** | The surface doesn't exist for this route or platform. |

Evidence columns: **S** source reading at this commit, **T** exact-build
automated test (CI), **G** gameplay proof. No row has G: gameplay testing needs
Lauren's separate permission. Feeder, Glass and ReShade rows were re-read line
by line for this change. OptiScaler, Vulkan, Universal MFG and HDR rows rely on
the shared panel source and the assignment's earlier audit, and weren't
re-verified control by control. Treat them as S-only.

## Routes and surfaces

| Route | Windows | Proton (Linux) | In-game surface | Desktop / Game Mode |
| --- | --- | --- | --- | --- |
| OptiScaler (Skynizz bridge, DX12/DX11/Vulkan games) | Yes | Yes, same DLLs | Glass on DX11/DX12; ImGui (classic) when Glass doesn't load or on Vulkan games | Companion panel via shared memory |
| Feeder NR (RenoDX DLSS5 + ReShade, DX11) | Yes | Yes, same DLLs | Glass only. PR143 removed the ImGui fallback; if Glass fails the panel closes | Helper reads/writes `[RenoDX.DLSS5]` |
| Vulkan NR/MFG (rtxForge layer) | Yes | Yes | Its own ImGui panel (`providers/vulkan-dlssg/panel`). No Glass | Status only; live editing from Desktop is unavailable |
| Universal MFG (OptiScaler ASI plugin) | Yes | Yes | Same as OptiScaler | Same as OptiScaler |
| RenoDX MFG | Covered by the managed-addon rule: the OptiScaler panel hides MFG when `mfg_provider.ownership` is `managed-addon` | Same | MFG controls unavailable in rtxForge's panel; use the game's/RenoDX's own | — |
| RenoDX HDR | Yes | Yes | Glass HDR page (requests to helper) | Helper writes startup preferences |
| Generic ReShade effects / add-on INI | Yes | Yes | Glass Effects page | — |
| Unknown / custom packages | — | — | No rtxForge controls; the native menus stay available | Listed as unmanaged |

## Neural rendering

| Control | OptiScaler | Feeder NR | Vulkan NR | Evidence |
| --- | --- | --- | --- | --- |
| NR on/off | Live, confirmed (volatile config, read back each frame) | **Live, unconfirmed → confirmed by readback**: the panel presses RenoDX's toggle key; RenoDX writes `NeuralUplift` back. This change waits up to 2 s for that readback, refuses a second press meanwhile, and shows *Waiting for the game…* or *Not confirmed* | Live in its own panel | S, T (source parity) |
| Style, strength, preset | Live, confirmed; the model rebuilds, coalesced at 400 ms | **Live, confirmed** with rtxForge's RenoDX build (read back through `RenoDXNrGetV1`; preset waits for the rebuild). Saved, restart with stock rc10 | Live in its own panel | S, G (ME1: strength 1.70 → 1.51 → 1.40 live) |
| Passes | Live, 1–3 | **Live, confirmed**, 1–4, waits for the rebuild. The panel capped this at 3; it now takes the ceiling from the route (`__passes_max`) | Live in its own panel | S, T, G (ME1: 1 → 2 live) |
| Per-pass tuning (pass 2/3, Feeder also 4) | Live, DX12-backed OptiScaler builds only; disabled when the runtime omits the keys | **Live** with rtxForge's RenoDX build: `Build-FeederPanel.ps1` maps `NRPass2…NRPass4` FollowPass1, Style, Intensity, Structure, LocalTone and Skin, and Glass shows pass 4 only when the route reports its keys. Saved, restart with stock rc10 | Unsupported | S |
| Resolution scale | Live, 0.25–2.0 | **Live, confirmed**, 0.33–1.0 (RenoDX's own floor; rtxForge allowed 0.25, which RenoDX silently raised), waits for the rebuild | Live | S, G (ME1: 0.70 → 0.50 live) |
| Local structure | Live | Live, confirmed with rtxForge's RenoDX build | — | S |
| Cache / interval, processing stage | Live where the runtime reports the key; otherwise disabled with *Not available in this runtime* | Unsupported | — | S |
| NR placement | Startup only (install recipe) | Startup only | Startup only | S |

## Upscaling, sharpening, frame generation

| Control | OptiScaler | Feeder NR | Vulkan | Evidence |
| --- | --- | --- | --- | --- |
| DLSS SR / RR presets | Live, confirmed (override flag + preset) | Unsupported | — | S |
| Sharpening, motion sharpening | Live, confirmed | Unsupported | — | S |
| FG multiplier | Live request, capped by the runtime's `__multiplier_max`; the measured ratio is shown separately and is the only evidence frames were generated | Unsupported (Feeder is NR-only) | Live in its own panel | S |
| Dynamic MFG | Live when the runtime reports `__dynamic_supported`; disabled otherwise, on Windows and Proton alike | Unsupported | Live in its own panel | S |

## Effects and HDR

| Control | State | Evidence |
| --- | --- | --- |
| ReShade technique on/off, uniforms | Live, confirmed: ReShade's runtime stores the value, and the next snapshot reads it back. **This change adds acknowledgments**: each edit is applied or refused with a reason, Glass keeps it pending until then, and a reload reports dropped edits instead of silently losing them | S, T (`Prototype.cpp` ack checks, parity test) |
| Add-on INI text settings | Saved; the add-on may only read it at startup (shown in the field tooltip) | S |
| RenoDX HDR | Startup only. The helper saves preferences and says to restart; live HDR edits stay in RenoDX's own menu | S |

## Presets, reset, undo

| Action | OptiScaler | Feeder NR |
| --- | --- | --- |
| Save / delete preset | Helper saves; *Saved* appears only after the helper's revision changes, *Couldn't confirm save* after 10 s | Same; values load at the next start |
| Reset (all / page) | Live, one recorded edit | Saved, restart (NR toggle live) |
| Undo / redo, A/B compare | Live; refused whole when a value isn't available in this session | Saved, restart, same refusal rule |
| Restart notice | Hidden (live route) | *Model tuning is saved and applies after restarting the game*; the tooltip notes NR on/off and effects are live. It used to say every change needed a restart |

## Menus, hotkeys, helper

| Item | State |
| --- | --- |
| Primary menu (rtxForge / OptiScaler / ReShade) | Saved; game-menu changes take effect after restarting the game (the Desktop says so) |
| Panel hotkey | Live; saved through the helper |
| Helper disconnected | Glass disables Save and Review and shows *Connect the background helper…*; tuning on live routes keeps working |
| Helper reconnect | Hello is re-sent; settings refresh on the next helper revision |

## Fixed when this matrix was first written

1. **Glass pass ceiling.** Feeder accepts 1–4 passes (`feeder_provider.TUNING`, generated bindings), but Glass clamped the stepper and its enablement to 3 in `OverlayController.h` and `GlassRuntime.cpp`. Glass now uses the route's own maximum. OptiScaler stays at 3.
2. **Feeder NR toggle.** A second request while RenoDX hadn't yet written `NeuralUplift` back could press the toggle key again and switch NR back. Requests are now refused until RenoDX confirms or 2 s pass. Glass shows waiting and unconfirmed states and notifies when the game didn't confirm.
3. **ReShade enqueue acknowledgment.** Out-of-range, stale-generation or unstorable edits were silently dropped, while Glass showed the value as set. Edits are now acknowledged as applied or refused, and Glass reports refusals and reload losses.
4. **Restart label.** On Feeder it now names what restarts instead of saying all changes need a restart.

## Feeder live tuning

Feeder installs now use RenoDX DLSS5 8.5.0-rc10 built by rtxForge with a live settings interface (`providers/renodx-dlss5`, release `renodx-dlss5-8.5.0-rc10-rtxforge-3`, which adds per-pass tuning for passes 2-4 and lets the glass overlay show RenoDX's corner HUD warnings as rtxForge notifications). See `feeder-live-tuning.md`. Games still on stock rc10 keep the saved-until-restart behaviour until repaired.

## Earlier blocker (resolved by the rtxForge build)

- **Feeder live model tuning.** RenoDX itself applies every NR setting live, with no restart (see `feeder-live-tuning.md`); what was missing is an entry point for rtxForge. The stock RenoDX DLSS5 rc10 add-on exports only `NAME`/`DESCRIPTION`. There is no versioned apply/readback API, and the exact rc10 build provenance is unresolved (review artifact `libfile_ffba3b4a3e988191ab8abc91dac4c515`). Style, strength, preset, passes, scale and structure therefore stay *Saved, restart*. No ABI was invented and no provider pin changed. Unblocking it needs RenoDX's maintainers to expose a supported interface, or a licensed source-built candidate qualified on an isolated Windows GPU environment.
- **Runtime proof.** None of the states above have gameplay evidence yet. Real renderer acknowledgment (NR toggle readback timing, ReShade acks, 4-pass rebuild stability) needs an authorized GPU test.
