# WORKER HANDOFF — rtxForge DLSS-Unlocked Native NVIDIA Ada MFG Fix

## Objective

Make rtxForge use **DLSS-Unlocked exactly as it is packaged and delivered**, then apply the minimum RTX 40 / Ada-specific configuration needed for native NVIDIA Frame Generation and Multi Frame Generation.

The target behavior is:

- preserve the game’s own native NVIDIA DLSS-G / Streamline integration whenever it exists
- use DLSS-Unlocked’s built-in Ada MFG unlock
- keep DLSS-Unlocked’s private `OptiScaler/streamline/` runtime private
- do not promote Streamline or NVIDIA FG DLLs into the game root
- do not use alternate/hybrid frame-generation backends
- keep NR off by default with F10 as the NR toggle
- optionally force a native game-owned 4× request through `OverrideInterpolationCount=3`
- fall back to OptiScaler-owned **native NVIDIA DLSS-G** only when the game-owned path cannot be made to work

This work is specifically for RTX 40 / Ada.

---

## Current DLSS-Unlocked packaging model

DLSS-Unlocked standalone packages are universal packages.

The package intentionally contains support for multiple GPU generations and multiple frame-generation paths. For RTX 40 / Ada, rtxForge must adapt the delivered package to the built-in Ada unlock.

DLSS-Unlocked ships with:

```text
dxgi.dll
OptiScaler.ini
nvngx_dlssnr.dll
nvngx.dll_dlssnr.dll

OptiScaler/
  streamline/
    sl.interposer.dll
    sl.common.dll
    sl.dlss.dll
    sl.dlss_g.dll
    sl.deepdvc.dll
    sl.dlss_nr.dll
    nvngx_dlssnr.dll
    ...
```

The private Streamline runtime belongs under:

```text
OptiScaler/streamline/
```

Do not relocate those DLLs into the game root.

---

## Current rtxForge behavior that must be fixed

### 1. Remove root promotion of private NVIDIA / Streamline runtime files

Current code in `engine/rtxengine.py` contains a DLSS-Unlocked `mfg-only` block that copies files from:

```text
OptiScaler/streamline/
```

to the game root when matching native runtime files already exist.

This must be removed.

The private DLSS-Unlocked runtime is not a replacement source for the game’s root Streamline / DLSS-G runtime.

The following must remain untouched in the game root unless they are already owned by the game:

```text
sl.*
nvngx_dlss.dll
nvngx_dlssd.dll
nvngx_dlssg.dll
nvngx_deepdvc.dll
nvapi64.dll
```

The existing `scripts/engine_bridge.py` root-runtime safety check is correct and should remain authoritative.

Keep the current refusal logic that rejects provider payloads containing root native runtime replacements.

---

## 2. Add a provider-specific RTX 40 / Ada adapter for DLSS-Unlocked

DLSS-Unlocked packages are delivered with Ampere/Turing-oriented MFG settings.

For RTX 40 / Ada, rtxForge must explicitly switch the package to the built-in Ada unlock.

For:

```text
provider = dlss-unlocked
family = ada
feature_mode = nr-mfg OR mfg-only
```

apply only:

```ini
[FrameGen]
External=false

[DLSSG]
AmpereMfgUnlock=false
AdaMfgUnlock=true
AdaBlackwellKernels=false
```

### Why

The built-in Ada unlock is disabled when either of these is true:

```text
AmpereMfgUnlock=true
External=true
```

The Ada unlock requires:

```text
AdaMfgUnlock=true
AmpereMfgUnlock=false
External=false
```

The current ShyVortex implementation checks these conditions at startup.

`AdaBlackwellKernels=false` is the current safe baseline. The Blackwell kernel retarget path is experimental and is not required for the architecture-gate unlock.

---

## 3. Do not rewrite normal FrameGen routing values for the game-owned path

Do not force these as part of the normal Ada adapter:

```ini
Enabled=false
FGInput=nofg
FGOutput=nofg
FGNvngxReplacement=None
```

Leave them at the package/user state unless a specific rtxForge mode explicitly owns them.

DLSS-Unlocked’s upstream defaults are effectively:

```ini
Enabled=auto
FGInput=auto
FGOutput=auto
FGNvngxReplacement=auto
```

The `auto` defaults already resolve to normal no-OptiFG behavior.

The primary Ada path should be:

```text
game owns native NVIDIA DLSS-G
OptiScaler only applies the Ada capability unlock
```

Do not manufacture an OptiScaler-owned FG path unless entering the explicit fallback mode described later.

---

## 4. NR behavior for rtxForge

For `nr-mfg` and `nr-only`:

```ini
[DlssNr]
Enabled=false
ToggleKey=0x79
```

`0x79` is F10.

NR must start OFF.

F10 must toggle NR on/off independently of the OptiScaler menu.

Preserve existing user NR tuning values during refresh.

Do not reset these unless the value is absent and rtxForge is applying a fresh default:

```text
WorkingScale
TransferStrength
ColourStrength
SkinProtection
SkinToneEnabled
SkinDetail
SkinColour
EnvironmentDetail
EnvironmentColour
RunBeforeSR
DeferredDLSS
FinishedPicture
other NR tuning
```

Provider-specific DLSS-Unlocked NR policy may still remove obsolete/conflicting keys if required by the current package, but do not reset user tuning unnecessarily.

---

## 5. Disable the unstable OptiScaler menu hotkey without breaking NR hotkeys

For DLSS-Unlocked under Proton:

```ini
[Menu]
OverlayMenu=false
ShortcutKey=-1
```

Important distinction:

```text
OverlayMenu=false
```

changes the overlay rendering path.

It does not mean “menu disabled.”

```text
ShortcutKey=-1
```

is what prevents the menu from opening from the keyboard.

F10 NR toggle remains independent because `DlssNr.ToggleKey` is handled separately.

---

# Native NVIDIA MFG strategy

## Primary path: game-owned native NVIDIA DLSS-G

This must be the default.

Requirements:

- game already has normal NVIDIA Frame Generation
- game owns its native Streamline / DLSS-G runtime
- rtxForge does not replace root NVIDIA FG runtime files
- Ada unlock is enabled through OptiScaler
- normal game Frame Generation UI remains usable

Base Ada config:

```ini
[FrameGen]
External=false

[DLSSG]
AdaMfgUnlock=true
AdaBlackwellKernels=false
AmpereMfgUnlock=false
```

---

# Optional forced 4× policy

4× must be a separate rtxForge policy.

Do not conflate:

```text
Ada unlock enabled
```

with:

```text
force 4×
```

Add an internal policy such as:

```text
native_mfg_multiplier = auto | 2 | 3 | 4 | 5 | 6
```

For 4× on the game-owned native Streamline path:

```ini
[DLSSG]
OverrideInterpolationCount=3
```

Mapping:

```text
1 = 2×
2 = 3×
3 = 4×
4 = 5×
5 = 6×
```

### Important

For the game-owned native path, use:

```text
OverrideInterpolationCount
```

Do not use:

```text
InterpolationCount
```

`OverrideInterpolationCount` changes the value sent through the game’s native Streamline DLSS-G path.

`InterpolationCount` is for OptiScaler-owned DLSS-G output.

Leave these alone unless a separate feature explicitly requires them:

```ini
InterpolationCount=auto
OverrideForceDMFG=auto
ForceDMFG=auto
FramerateTargetDMFG=auto
```

Do not enable Dynamic MFG as part of the basic 4× policy.

---

# Native NVIDIA fallback path

If the game has normal NVIDIA FG but the game-owned Streamline path cannot accept or honor the requested multiplier, rtxForge may expose an explicit fallback using DLSS-Unlocked’s private NVIDIA Streamline runtime.

This is still native NVIDIA DLSS-G.

Fallback config:

```ini
[FrameGen]
External=false
Enabled=true
FGInput=upscaler
FGOutput=dlssg
FGNvngxReplacement=None

[DLSSG]
AdaMfgUnlock=true
AdaBlackwellKernels=false
AmpereMfgUnlock=false
InterpolationCount=3
```

This means:

```text
OptiScaler owns DLSS-G output
private OptiScaler/streamline/ runtime is used
output remains NVIDIA DLSS-G
```

Do not use:

```text
Nukems
Arturs
FFX
Combo
dlssg_sm86
dlss-enabler-headless
dlssg_to_fsr3_amd_is_better
```

Those are outside the product direction.

Fallback must be explicit and logged.

Do not silently switch a game from game-owned native FG to OptiScaler-owned FG.

---

# Provider payload rules

For DLSS-Unlocked payload extraction:

Keep:

```text
dxgi.dll
OptiScaler.ini
nvngx_dlssnr.dll
nvngx.dll_dlssnr.dll
OptiScaler/streamline/*
native NVIDIA support files required by the package
```

Strip / refuse alternate FG backends:

```text
dlss-enabler-headless.dll
dlssg_to_fsr3_amd_is_better.dll
OptiScaler/dlssg_sm86/*
```

Do not move private runtime files into root.

Do not merge y4my runtime files into a DLSS-Unlocked install.

Provider boundaries must remain strict.

---

# rtxForge code changes

## `engine/rtxengine.py`

### Remove

Delete the DLSS-Unlocked `mfg-only` runtime promotion block that copies:

```text
OptiScaler/streamline/*
```

into the game root.

There should be no private-to-root promotion for DLSS-Unlocked.

---

### Replace the current generic Ada INI patch

Current behavior sets Ada policy globally.

Replace it with provider-aware logic.

Pseudo-code:

```python
if provider_id == "dlss-unlocked":
    if family == "ada" and feature_mode in {"nr-mfg", "mfg-only"}:
        set_ini("FrameGen", "External", "false")
        set_ini("DLSSG", "AmpereMfgUnlock", "false")
        set_ini("DLSSG", "AdaMfgUnlock", "true")
        set_ini("DLSSG", "AdaBlackwellKernels", "false")
    else:
        set_ini("DLSSG", "AdaMfgUnlock", "false")
```

Do not force normal FrameGen routing keys unless the selected rtxForge mode explicitly owns them.

---

### NR defaults

For `nr-mfg` and `nr-only`:

```python
set_ini("DlssNr", "Enabled", "false")
set_ini("DlssNr", "ToggleKey", "0x79")
```

Preserve unrelated NR tuning.

---

### Menu safety

For DLSS-Unlocked / Proton policy:

```python
set_ini("Menu", "OverlayMenu", "false")
set_ini("Menu", "ShortcutKey", "-1")
```

---

### Optional forced multiplier

Add policy:

```python
native_mfg_multiplier
```

For game-owned native FG:

```python
if native_mfg_multiplier == 4:
    set_ini("DLSSG", "OverrideInterpolationCount", "3")
```

Do not touch `InterpolationCount`.

If multiplier is `auto`:

```ini
OverrideInterpolationCount=auto
```

---

## `scripts/engine_bridge.py`

Keep the existing root native runtime refusal.

It should continue rejecting provider payloads that attempt to place these in root:

```text
nvngx_dlss.dll
nvngx_dlssd.dll
nvngx_dlssg.dll
nvapi64.dll
sl.*
```

Keep stripping forbidden alternate/hybrid backends.

Add assertions for DLSS-Unlocked payload shape:

```text
dxgi.dll exists
OptiScaler.ini exists
OptiScaler/streamline/sl.interposer.dll exists
OptiScaler/streamline/sl.dlss_g.dll exists
```

Do not require root NVIDIA DLSS-G DLLs from the provider.

---

# Install / refresh ownership behavior

The existing baseline system should remain authoritative.

On refresh:

- preserve user-modified `OptiScaler.ini`
- reassert only rtxForge-owned policy keys
- preserve game-native root runtime files
- preserve external drift
- never overwrite unknown root NVIDIA runtime changes
- keep `OptiScaler/streamline/` provider-owned and private

On uninstall:

- remove rtxForge-owned OptiScaler files
- restore original files from baseline
- do not restore or delete root NVIDIA runtime files that rtxForge never owned

---

# Runtime logging / health reporting

Replace stale historical v3e-only health markers with current DLSS-Unlocked / ShyVortex evidence.

Parse `OptiScaler.log` for:

```text
MFG unlock: nvngx_dlssg.dll patched
MFG unlock: advertise
MFG unlock: validate
MFG unlock: arch gates patched
MFG unlock: unsupported or ambiguous DLSSG
MFG unlock: no compatible interpolation kernels
DLSSG runtime version
OverrideInterpolationCount
setDynamicMFGParams failed
Many frame count repeats in a row
```

Expose health as:

```text
DLSS-G integration       detected / missing
Native runtime owner     game / OptiScaler / unknown
Ada unlock               enabled / disabled
DLSS-G runtime           version
Architecture gates       patched / unsupported / unknown
Unlocked max             2× / 3× / 4× / 5× / 6× / unknown
Requested multiplier     auto / 2× / 3× / 4× / 5× / 6×
Native override          applied / unsupported / unknown
Reflex / pacing          OK / failed / unknown
Presentation             verified / unverified
```

Do not equate:

```text
game UI says 4×
```

with:

```text
verified real 4× presentation
```

---

# Regression test matrix

Use these games as known test cases.

## Positive control: native >2× already working

### Cyberpunk 2077

Expected:

```text
normal native NVIDIA FG works
higher MFG works
forced 4× must not regress it
```

### The Outer Worlds 2

Expected:

```text
normal native NVIDIA FG works
higher MFG works
forced 4× must not regress it
```

---

## Positive control: repaired 2×

### Halo Campaign Evolved

Expected:

```text
native 2× visibly works
NR starts OFF
F10 toggles NR
menu hotkey does not open OptiScaler menu
```

Then test:

```ini
OverrideInterpolationCount=3
```

Expected result:

```text
request reaches native Streamline path
```

If actual 4× presentation does not occur, record it as a title/runtime limitation rather than falling back silently.

---

## Critical 4× tests

### inZOI

Current observed behavior:

```text
game UI can be set to 4×
visible result appears to remain around 2×
```

Test:

```ini
OverrideInterpolationCount=3
```

Determine whether real multi-frame presentation appears.

---

### PRAGMATA

Current observed behavior:

```text
game UI can be set to 4×
2× visibly works
higher multiplier is not consistently visible
```

Test:

```ini
OverrideInterpolationCount=3
```

---

## Failure control

### Avowed

Current observed behavior:

```text
native FG/MFG path remains problematic
```

Use logs to determine whether failure is:

```text
Ada unlock never activates
runtime signature unsupported
Streamline override not honored
pacing failure
presentation failure
game-specific integration issue
```

Do not add broad global workarounds based only on Avowed.

---

# Required automated tests

## Test A — no root runtime replacement

Create a fixture containing sentinel versions of:

```text
sl.interposer.dll
sl.common.dll
sl.dlss_g.dll
nvngx_dlssg.dll
nvngx_dlss.dll
nvngx_dlssd.dll
```

Install DLSS-Unlocked.

Assert every root sentinel hash is unchanged.

---

## Test B — private runtime stays private

Assert:

```text
OptiScaler/streamline/sl.interposer.dll
OptiScaler/streamline/sl.dlss_g.dll
```

exist after install.

Assert corresponding provider files are not promoted to root.

---

## Test C — Ada adaptation

Given DLSS-Unlocked package INI:

```ini
External=true
AmpereMfgUnlock=true
AdaMfgUnlock=false
```

Ada install must produce:

```ini
External=false
AmpereMfgUnlock=false
AdaMfgUnlock=true
AdaBlackwellKernels=false
```

---

## Test D — normal FG routing untouched

Given:

```ini
Enabled=auto
FGInput=auto
FGOutput=auto
FGNvngxReplacement=auto
```

Ada adaptation must leave those values unchanged.

---

## Test E — NR defaults

For `nr-mfg` / `nr-only`:

```ini
Enabled=false
ToggleKey=0x79
```

must be present under `[DlssNr]`.

---

## Test F — menu hotkey

Assert:

```ini
[Menu]
OverlayMenu=false
ShortcutKey=-1
```

for DLSS-Unlocked Proton installs.

---

## Test G — 4× game-owned policy

When:

```text
native_mfg_multiplier=4
route=game-owned
```

assert:

```ini
OverrideInterpolationCount=3
InterpolationCount=auto
```

---

## Test H — OptiScaler-owned NVIDIA fallback

When explicit fallback is enabled:

```ini
Enabled=true
FGInput=upscaler
FGOutput=dlssg
FGNvngxReplacement=None
InterpolationCount=3
```

Assert:

```text
private Streamline runtime is present
no alternate FG backend is present
root game-native runtime is untouched
```

---

## Test I — uninstall safety

Install and uninstall DLSS-Unlocked.

Assert:

```text
game-native root NVIDIA runtime hashes are unchanged
original OptiScaler tree/file state is restored
provider-owned private runtime is removed
```

---

# Provider version strategy

Keep the currently pinned DLSS-Unlocked release while implementing and validating this architecture.

Do not combine:

```text
provider update
installer architecture rewrite
forced 4× policy
```

into one change.

First make the current pin work correctly.

Then update DLSS-Unlocked as a separate regression-tested provider bump.

---

# Definition of done

The DLSS-Unlocked integration is complete when all of the following are true:

- no private Streamline DLL is promoted into the game root
- game-owned native NVIDIA FG continues to work
- RTX 40 installs use `External=false`
- RTX 40 installs use `AmpereMfgUnlock=false`
- RTX 40 installs use `AdaMfgUnlock=true`
- RTX 40 installs use `AdaBlackwellKernels=false`
- normal FG routing keys remain package/user-owned by default
- NR starts OFF
- F10 toggles NR
- OptiScaler menu hotkey is disabled
- optional game-owned 4× uses `OverrideInterpolationCount=3`
- OptiScaler-owned fallback remains native NVIDIA DLSS-G
- no hybrid/alternate FG backend is installed
- Cyberpunk and The Outer Worlds 2 retain working >2× MFG
- Halo retains working 2×
- inZOI and PRAGMATA can be tested deterministically for forced 4×
- Avowed failures can be classified from logs rather than guessed
- uninstall restores the game cleanly
