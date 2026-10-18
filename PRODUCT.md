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

The desktop application and controller-oriented Game Mode share the package engine. Package support depends on the game, renderer, hardware and installed runtime. A Windows companion remains accessible above a windowed or borderless game through a configurable keyboard shortcut and an independent overlay helper. The main rtxForge window can close. Panel polling stops while hidden; animations use a short compositor scale and fade and respect reduced-motion settings.

## Capabilities and Constraints

- Preserve explicit package choices and each installed game's recorded recipe during repair and restore.
- Keep one MFG component responsible for capability patches, kernels and multiplier control.
- Distinguish selected settings, applied runtime state and measured performance. A selected 4× multiplier does not promise a fourfold performance gain.
- The companion's primary controls are MFG and NR. Other supported settings belong under Advanced.
- Unified controls use simple labels; Classic uses original OptiScaler labels and numeric units for the supported live controls. Model resolution remains a percentage. Original OptiScaler is a separate overlay choice; its full menu needs the updated game package and a restart.
- A gear beside close exposes all Overlay settings without opening the manager. A globe opens a one-time Global NR/MFG bulk review, also available in the app’s Settings → Global. It preserves unrelated tuning and preset fields, retains backups, and excludes running or unsupported targets. It does not override future installs.
- NR + MFG installs present a second review for supported subsets, with NR/MFG check or unavailable badges and a concise reason. The confirmed operation retains exact per-mode review tokens; hard blockers remain excluded.
- Batch reviews reuse identical verified package and model payloads, release dismissed reviews, and use fresh native process checks at write boundaries.
- The overlay detects the compatible game being played from its verified running process. It has no game picker. Live edits target that exact game session and acknowledge application before reporting success.
- NR controls include model style, preset, strength and passes; detail, colour, local structure, local tone and skin handling; placement, model resolution and cache reuse. Group these by purpose and progressively reveal fine tuning and performance controls.
- Live edits require a compatible running installation. Show unavailable, waiting, stopped and failed states accurately; never substitute demonstration telemetry.
- Preserve existing application layouts and functions outside the requested companion and its entry points.
- Use supported per-game configuration for optional 3840×2160 borderless setup, with backups. Do not force unsupported display modes.

## Brand Commitments

Keep the rtxForge name and existing icon. The Windows overlay is a minimal floating NR + MFG sidebar: nearly full screen height with generous edge and internal padding, rounded corners, a soft drop shadow and translucent black surfaces over a blurred game backdrop. It opens on the left. Titles, headings and controls use the active game's existing artwork-derived or custom rtxForge accent, set in Inter; idle and Global surfaces use a neutral accent. It has no standard app title bar or game-selection menu. The main application keeps its existing visual system.

## Product Principles

1. Back up originals and make changes attributable to an exact package.
2. Give the player direct control of the game being played.
3. Keep the main task small and progressively reveal advanced settings.
4. Report actual runtime behavior separately from configuration.

## Evidence on Hand

Product architecture, supported routes and package constraints are described in README.md and implemented in the shared engine and Windows host. Runtime validation remains specific to an exact tested game and payload; it is not a universal compatibility claim.
