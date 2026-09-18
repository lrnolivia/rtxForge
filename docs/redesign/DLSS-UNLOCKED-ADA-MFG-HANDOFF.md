# rtxForge — DLSS-Unlocked / Ada MFG Backend Boundary

This is a concise redesign-era backend handoff.

UI redesign work must preserve the production graphics architecture.

## Native ownership

Preserve game/native NVIDIA DLSS-G / Streamline integration whenever available.

Do not promote DLSS-Unlocked's private `OptiScaler/streamline/` runtime into the game root.

Do not use alternate/hybrid frame-generation paths as the product default.

## Ada configuration

For RTX 40 / Ada DLSS-Unlocked adaptation, preserve:

```ini
[FrameGen]
External=false

[DLSSG]
AmpereMfgUnlock=false
AdaMfgUnlock=true
AdaBlackwellKernels=false
```

NR behavior where configured:

```ini
[DlssNr]
Enabled=false
ToggleKey=0x79
```

Menu behavior:

```ini
[Menu]
OverlayMenu=false
ShortcutKey=-1
```

Do not change these while working on unrelated UI tasks.

## Redesign rule

The redesign should integrate around the production backend.

If a UI task appears to require provider/runtime changes, stop and inspect the current engine,
bridge, provider lock, tests, and release notes before making the change.
