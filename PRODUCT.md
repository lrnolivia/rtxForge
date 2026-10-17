# Product

<!-- impeccable:product-schema 1 -->

## Platform

adaptive

rtxForge has a native WinUI 3 Windows application and a GTK4/libadwaita Linux application. The companion control panel targets Windows first. Mobile platforms are outside this work.

## Users

Players managing graphics enhancements for their installed PC games, including Steam libraries, manually added folders and pinned copies of game builds. The Windows companion serves a player adjusting NR and MFG while a game is open.

## Product Purpose

Manage compatible Neural Rendering (NR), Multi Frame Generation (MFG) and DLSS runtimes through a game library, reviewed installation changes, recorded package ownership and restorable original files.

## Operating Context

The desktop application and controller-oriented Game Mode share the package engine. Package support depends on the game, renderer, hardware and installed runtime. A Windows companion must remain accessible above a windowed or borderless game through a configurable keyboard shortcut while rtxForge is running.

## Capabilities and Constraints

- Preserve explicit package choices and each installed game's recorded recipe during repair and restore.
- Keep one MFG component responsible for capability patches, kernels and multiplier control.
- Distinguish selected settings, applied runtime state and measured performance. A selected 4× multiplier does not promise a fourfold performance gain.
- The companion's primary controls are MFG and NR. Other supported settings belong under Advanced.
- Live edits require a compatible running installation. Show unavailable, waiting, stopped and failed states accurately; never substitute demonstration telemetry.
- Preserve existing application layouts and functions outside the requested companion and its entry points.
- Use supported per-game configuration for optional 3840×2160 borderless setup, with backups. Do not force unsupported display modes.

## Brand Commitments

Keep the rtxForge name and existing icon. The companion brief specifies dark translucent surfaces with blur, distinct surface depth, rounded corners, soft shadows and readable typography. It should feel at home beside the existing Windows application.

## Product Principles

1. Back up originals and make changes attributable to an exact package.
2. Give the player direct control of the selected game.
3. Keep the main task small and progressively reveal advanced settings.
4. Report actual runtime behavior separately from configuration.

## Evidence on Hand

Product architecture, supported routes and package constraints are described in README.md and implemented in the shared engine and Windows host. Runtime validation remains specific to an exact tested game and payload; it is not a universal compatibility claim.
