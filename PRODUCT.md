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

### Adoption

rtxForge detects existing feature packages separately from management ownership. Refreshing the library offers Adoption for detected, unmanaged installations. The same action is available from game details. Review verifies the selected provider's complete known recipe before registering it; filenames alone never grant ownership. This applies to supported OptiScaler package families and the separate Feeder route across games.

Adopt existing setup preserves the installed files and tuning. Back up and clean install captures that setup before applying the matching app-selected package with fresh settings. Unknown or mixed runtimes, changed review inputs and running games are refused. Adoption stores a recovery baseline; Restore returns to the pre-adoption setup, which may itself contain mods. It does not manufacture vanilla originals. Existing authoritative recovery records are never replaced by Adoption.

NR starts off on new and clean installs. Enable NR on launch is an explicit per-install choice, with its default in Graphics settings. MFG is independent. Adoption and repair preserve the existing startup choice. Installed files, saved enablement and observed runtime activity remain distinct.

On Windows, compatible x64 DirectX 11 games without a native NR route can use Feeder NR while Skynizz remains selected for native DLSS games. Library detection offers this as an NR-only install route, including the three separate Mass Effect Legendary Edition games; capability does not mean a package is installed or managed. Installation copies the verified local ReShade, Feeder, RenoDX and shader stack plus the selected compatible NR model. The app does not download this stack automatically. Packages exposes its one-time source setup. Mixed NR + MFG reviews offer Feeder games with NR supported and MFG unavailable, and preserve separate exact review tokens. Running games, incompatible executables, conflicting hooks and changed inputs are still refused at review or execution.

Anti-cheat remains a block unless a title has an explicit verified offline profile and the owner reviews its exception. Gears E-Day has a Windows offline-only profile, bound to its actual executable and EAC files. It launches the game directly with child-process-only null-client and Steam identification variables. Anti-cheat files, system environment and normal Steam launch settings are unchanged. Route drift or a running protected session disables the exception. Online support is not implied; adopted mod files must be removed before online play.

- Preserve explicit package choices and each installed game's recorded recipe during repair and restore.
- Keep one MFG component responsible for capability patches, kernels and multiplier control.
- Distinguish selected settings, applied runtime state and measured performance. A selected 4Ã— multiplier does not promise a fourfold performance gain.
- The companion's primary controls are MFG and NR. Other supported settings belong under Advanced.
- Unified controls use simple labels; Advanced uses original OptiScaler labels and numeric units for the supported live controls. Model resolution remains a percentage. Original OptiScaler is a separate overlay choice; its full menu needs the updated game package and a restart.
- A gear beside close exposes all Overlay settings without opening the manager. A globe opens a one-time Global NR/MFG bulk review, also available in the appâ€™s Settings â†’ Global. It preserves unrelated tuning and preset fields, retains backups, and excludes running or unsupported targets. It does not override future installs.
- Desktop, Game Mode and sidebar Overlay settings share independent OptiScaler/ReShade menu and intro choices. Intros default off. ReShade uses its guide and RenoDX welcome flags; loading notices are separate. Reviewed existing-game updates retain custom bindings, immutable runtimes, rendering choices and original restoration boundaries. Menu access can coexist with the sidebar; native-only remains an explicit primary-overlay choice.
- Desktop library artwork sizes range from 75% to 150%. Poster titles reserve two readable lines with trimming after the second line and aligned status badges.
- The Windows sidebar defaults to End. Both Overlay settings views record a custom single key or Ctrl/Alt/Shift combination, with Reset and Disable actions. Insert belongs to OptiScaler; earlier rtxForge Insert settings migrate to End while other chosen bindings remain intact. Recording pauses the helper shortcut temporarily, restores it on cancellation or timeout, and refuses reserved or occupied shortcuts before saving.
- NR + MFG installs present a second review for supported subsets, with NR/MFG check or unavailable badges and a concise reason. The confirmed operation retains exact per-mode review tokens; hard blockers remain excluded.
- Batch reviews reuse identical verified package and model payloads, release dismissed reviews, and use fresh native process checks at write boundaries.
- The overlay detects the compatible game being played from its verified running process. It has no game picker. Live edits target that exact game session and acknowledge application before reporting success.
- Opening the companion leaves the game in the foreground. Hiding returns focus to its invoking window only after interaction with the companion, never after switching to another app. Use the full invoking display for edge padding; do not hide or reconfigure the system taskbar.
- NR controls include model style, preset, strength and passes; detail, colour, local structure, local tone and skin handling; placement, model resolution and cache reuse. Group these by purpose and progressively reveal fine tuning and performance controls.
- Live edits require a compatible running installation. Show unavailable, waiting, stopped and failed states accurately; never substitute demonstration telemetry.
- Placement requests and observed placement are separate. Report actual model dimensions and a concise fallback reason only from fresh runtime observations. Older protocols show unverified placement. RR must retain the finished-image route until its pre-denoising input contract is validated; isolated candidates need gameplay acceptance before replacing installed runtimes.
- Preserve existing application layouts and functions outside the requested companion and its entry points.
- Use supported per-game configuration for optional 3840Ã—2160 borderless setup, with backups. Do not force unsupported display modes.

## Brand Commitments

The overlay uses airy, textured glass with real scene blur and adaptive shadows. Preserve the approved raw logo without a platter. The neutral rtxForge wordmark and accent-colored uppercase headings use Bakbak One; main controls use Roboto at the selected readable default, with simple text-size and overall-scale preferences. Keep the manager application's existing visual identity outside this overlay work.

Offer Side Panel, Advanced and Bar layouts. Empty chrome is draggable; panels raise together with their content. Bar popovers attach to the invoking button and detach when dragged. Advanced uses a sidebar, expanded Overview metadata and dedicated frame-generation and neural-rendering pages. Settings is a complete screen with an Appearance popout.

Clear is the default: light tint 20%, blur 48px, grain 4%, Soft Light at 50%. Dark uses tint 80%, blur 48px and Overlay at 15%; Light uses tint 100%, blur 44px and Overlay at 35%; both retain grain 4%. Clear foreground contrast adapts smoothly and prefers light text where readable. Fine material edits remain available while defaults are being finalized, label the appearance Custom, and reset when a built-in theme is selected. Preserve reduced-motion support and restrained single-line notifications with real shortcut keycaps.

Runtime telemetry is separate from requested settings. Show actual frame-generation output and NR processing time in a compact two-column row under status indicators; unavailable values remain absent or explicitly unreported. The screenshot prototype is a styling tool and does not establish game or renderer acceptance.

## Product Principles

1. Back up originals and make changes attributable to an exact package.
2. Give the player direct control of the game being played.
3. Keep the main task small and progressively reveal advanced settings.
4. Report actual runtime behavior separately from configuration.

## Evidence on Hand

Product architecture, supported routes and package constraints are described in README.md and implemented in the shared engine and Windows host. Runtime validation remains specific to an exact tested game and payload; it is not a universal compatibility claim.

The overlay tuning workflow is documented in [In-game tuning](docs/overlay.md), including session undo, named presets, A/B comparison and supported independent pass controls.
