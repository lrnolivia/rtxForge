# Live NR tuning for Feeder games

Feeder games today change only NR on/off live. Every other NR setting waits for
a game restart. That limit comes from how RenoDX DLSS5 is reached, not from
what it can do.

## What RenoDX already does

Source: [Andarael/RenoDX-DLSS5-Generic](https://github.com/Andarael/RenoDX-DLSS5-Generic)
branch `v8.5dev` at `9bb6c0f` (MIT). The original PEQHUB repository now returns
404; this fork keeps the snapshot. The source declares `kAddonVersion =
"v8.5.0-rc10"` and `kConfigVersion = 7`, matching the pinned add-on and the
`ConfigVersion=7` it writes. That is strong evidence, not proof, that rc10 was
built from it: the release has no build receipt.

- Every tunable is a `std::atomic` global that the renderer reads each frame (for example `stack_passes.load()` when it evaluates NR).
- A settings table (`struct Setting` in `dlssnr.hpp`) maps each `[RenoDX.DLSS5]` key to its atomic. `Setting::Commit(value)` stores the value, persists it to the ini and applies its effect. This is what RenoDX's own overlay window calls when a slider moves.
- Each setting declares its effect. Of 50 settings, 11 are `kNone` (apply on the next frame), 36 are `kHistory` (apply and reset temporal history) and 3 are `kRecreate` (`NRPreset`, `NRPasses`, `NRResolutionScale`: rebuild the NR feature). None needs a restart.
- `RequestHistoryReset` and `RecreateFeatures` raise flags the renderer handles on its next frame, so a call from another add-on on the render thread is safe.
- `DLSS5 Generic: NR effective settings: …` in `ReShade.log` reports what was loaded at startup. ME1 on 2026-11-04 logged `passes=4 intensity=1.7 resolution_scale=0.7` after rtxForge saved those values.

The only thing missing is an entry point. The add-on exports `NAME` and
`DESCRIPTION` and nothing else.

## Proposed interface (RenoDX side)

A small, versioned C export, added to `addon.cpp`, that reuses the settings table:

```cpp
// Returns 1. A host must refuse any other value.
extern "C" __declspec(dllexport) uint32_t RenoDXNrApiVersion();

// Reads the live value and the configuration generation.
extern "C" __declspec(dllexport) bool RenoDXNrGetV1(
    const char* key, float* value, uint64_t* generation);

// Commits through Setting::Commit on success. Returns 0 applied,
// 1 unknown key, 2 out of range or wrong type, 3 not ready (no runtime yet).
// *applied receives the value read back after the commit.
extern "C" __declspec(dllexport) int RenoDXNrSetV1(
    const char* key, float value, float* applied, uint64_t* generation);
```

Bounds come from the same limits the loader enforces (`SanitizeEnumKey` and the
float clamps used when reading the ini). An out-of-range value is refused, not
clamped, so the host can report it.

## rtxForge side

- The Feeder panel finds `renodx-dlss5.addon64` with `GetModuleHandleW` and looks up the exports. A missing export or a version other than 1 keeps today's behaviour: saved until restart, NR toggle via F6.
- When available, the panel sets `liveTuning=true` only for keys `RenoDXNrGetV1` recognizes. Each change goes through `RenoDXNrSetV1`, and the value Glass shows is the read-back `applied` value, never the request.
- Glass's pending, applied and rejected states and its restart label already fit this.
- `kRecreate` settings (passes, preset, resolution scale) briefly rebuild the model. The panel's existing 400 ms commit spacing still applies, so a slider drag doesn't rebuild every frame.
- Per-pass settings (`NRPass2…NRPass4*`) become reachable the same way.

## What shipped

rtxForge builds the add-on itself (`providers/renodx-dlss5`, `.github/workflows/renodx-dlss5.yml`) and Feeder installs download release `renodx-dlss5-8.5.0-rc10-rtxforge-1` by hash. The source was imported from an unpublished RenoDX base, so `renodx_compat.hpp` supplies five utilities public RenoDX lacks. Tested in Mass Effect LE 1 on 2026-11-04 (RTX 4070): strength, passes and resolution changed live and RenoDX's own readback confirmed each, with NR engaged throughout. Asking the maintainers to adopt the interface upstream would still let rtxForge return to a community build.

## Ways to get the export (as proposed)

1. **Upstream.** Ask the RenoDX DLSS5 maintainers to add it. Cleanest, and it keeps the community build. The original repository is gone, and releases are distributed through RenoDX's Discord, so the contact route needs Lauren.
2. **rtxForge-built add-on.** Apply the patch to the MIT source and build the `dlss5` target in a full RenoDX checkout on hosted Windows CI. This replaces the pinned rc10 binary with an rtxForge build, which is a provider pin change that needs Lauren's approval. The exact rc10 toolchain and RenoDX commit are unknown, so the build has to be qualified (NR engaged, settings parity, stability) before it ships.

Either way, rtxForge must keep working with the stock rc10, which lacks the
export.
