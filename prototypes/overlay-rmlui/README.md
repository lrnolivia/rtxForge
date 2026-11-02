# Overlay preview

This local native Windows preview uses the same RmlUi controller as the glass
runtime. It renders over selectable screenshot backgrounds; it never reports
demonstration values as game telemetry or changes a game installation.

Build with `Build.ps1`, supplying the pinned RmlUi checkout and the existing
OptiScaler FreeType library. `Preview.ps1` opens the result. Delete toggles the
controls; Settings contains layout, Appearance and shortcut preferences. The
preview keeps its preferences separate from the game overlay.

`--onboarding` starts with Side Panel, Advanced or Bar. Choosing a layout reveals
its live preview; Appearance is a secondary button rather than a required step.
Skip and keyboard navigation remain available. Use native overlays opens a brief confirmation showing the installed native
menu shortcuts. Confirming saves an opt-out for this game and closes rtxForge
only after the helper acknowledges it. Enabled native interfaces are also listed
alongside the rtxForge key on the layout screen.
The unchecked Make this my default option also changes app defaults, preserving
other explicit game choices. Re-enable through Desktop or Game Mode Overlay
settings or Game Details. Native menus may require a game restart. The standalone
prototype cannot change the manager's overlay policy. Completion is stored
separately from appearance, and the welcome toast remains independent.

Advanced's initial footprint grows with the viewport, while text size and overlay
scale remain user choices. Moving or resizing a window survives page changes.

`--self-test --output <image.png>` exercises native mouse and keyboard input,
undo/redo, hold-to-preview NR, pass controls, the four theme defaults and Settings.
Offscreen captures use a 2560 Ãƒâ€” 1440 canvas. The live window fits the monitor's
work area, including its title bar.

Appearance offers Clear, Light and Dark with an independent Surface Tint switch.
The approved tint presets keep each base style's character. Experimental character
and saturation sliders remain in God Mode. More holds
Blur and Motion. Experimental font and material tuning lives in the separate,
collapsed God Mode section, available only in this preview.

Headings use one consistent game-accent treatment per theme, shared by the game
title, section headings and detached windows. Clear uses a stable Screen reference
with stronger chroma, rather than recoloring each heading from its local scene.
Individual headings have no added shadow or outline; the existing subtle
material-wide text depth remains. Ordinary Clear ink stays light, and bright
yellow is kept out of olive or brown variants. Custom preview blend experiments
remain available in God Mode.

The self-test also checks window containment, Advanced content slots, Bar
footer separation, Settings navigation and toast placement across 54 layout,
viewport, text-size and scale combinations. `--layout-test` runs these bounds
checks alone. Capture specific states with `--layout floating|centered|bar`,
`--page overview|neural|frame|look|passes|hdr`, `--settings`, `--custom-mfg`,
`--text-size 20|22|24` and `--scale 70..150`. These native checks use the same
document and controller as the game renderer; they do not establish gameplay
acceptance.

`--game-capture --game-title <title> --output <image.png>` exports an SDR8 image
without a native window frame or the scene-selection toolbar. Demonstration
activity remains labeled as sample data. These exports are styling showcases,
not gameplay performance measurements.

`Get-Scenes.ps1` optionally caches the publisher screenshots listed in
`scenes.json`. Their source URLs, ownership and hashes remain recorded there;
the images are not redistributed in the repository or runtime DLL.
Every styling scene has animated, explicitly labelled sample NR/FG activity,
timings, render dimensions and frame history. These values respond to preview
controls and are generated only by the standalone prototype. They are never
published as measurements or included in the injected runtime.

The runtime boundary and its acceptance limits are documented in
[`providers/glass-overlay`](../../providers/glass-overlay/README.md).

### Accent sources

Appearance offers None, Adaptive (the default), and Game. None uses neutral controls and hides Surface Tint. Game uses the game color from rtxForge unless a valid #RRGGBB override is entered; clearing it restores the game color. Adaptive chooses a chromatic accent from the raw scene behind the main panel, reusing the existing 64 by 36 thumbnail every 250 ms. It follows muted and vivid scene saturation, settles toward neutral in grey scenes, and seeds from the first valid scene sample, then eases toward changed colors with a 0.22-second response. Overlay pixels never feed the sampler.

All headings share the same theme treatment: soft bright Clear, medium Dark, rich Light. Bright yellow in Light uses neutral text with vivid yellow controls, avoiding muddy derived ink. AccentMode and AccentColor round-trip through native preferences and helper snapshots. The inline desktop illustration approximates Adaptive using its screenshot; the full preview and injected overlay sample the actual region behind the panel. Use --accent-mode custom for Library-color showcase captures, or --accent-mode adaptive for scene-driven captures.

### Settings ownership and notifications

Desktop and Game Mode define defaults. Routine in-game edits stay in the current game's override, including appearance and shortcuts. Only the explicit Make this my default checkbox in native-overlay confirmation also changes app defaults. The app's Apply defaults to all overlays action clears overrides and cached game appearance profiles. Close games before applying it. Package/menu file updates still use the existing reviewed Update Overlays flow.

The glass renderer queues a single Neural rendering active notification only after telemetry confirms NR is running and the welcome or current toast has finished. Disabling notifications suppresses it. The Feeder quiet add-on suppresses RenoDX 8.5 rc10's duplicate status card only when the initialized glass renderer exports notification ownership. Separate upstream issue notices remain available. This is a window-level integration for the pinned upstream version, not a binary patch.

### Performance fixture

`--benchmark --output <file.png>` measures 600 static-scene frames, discarding the first 120 CPU samples. It reports CPU submission mean/p95 and asynchronous D3D11 timestamp mean/p95 with sample counts. The timestamp interval includes idle time while the CPU submits commands; it is not an isolated shader cost or a gameplay FPS comparison. Use the same viewport, scene, layout, theme, scale, and source for comparisons.

The controller caches unchanged material properties, and the runtime skips composition and blur when all panels are hidden. A hidden overlay with no toast or active picker polls preferences/telemetry at most every 250 ms; intervening DX11/DX12 frames skip context-state work and resource wrapping. Cached GPU surfaces remain allocated for reopening. Adaptive sampling reuses the existing 64 by 36 readback on a 250 ms cadence. Open-window composition still uses full-resolution layers plus quarter-resolution separable blur; real-game CPU/GPU and memory profiling, especially HDR/DX12/Proton, remains necessary before calling it lightweight.


Custom color is a circular swatch. Open it for a compact frosted popover with a hex field and a small cached game-poster preview; clicking the poster samples its pixels. A circular swatch inside the hex field opens a compact saturation/brightness spectrum with a hue strip, replacing the poster until selection. It uses a single generated atlas under 1 MiB, without downloads or per-frame texture generation. There are no RGB sliders. The popover points to its swatch and dismisses as soon as a color is chosen. Escape or a click outside cancels without an extra close button. Pick from screen arms a temporary eyedropper: click a visible color, or cancel with Escape/right-click. Its hooks and screen reads exist only for that explicit interaction and are released afterward. Desktop uses the native Windows color picker, Linux uses its native color chooser, and the full preview uses the same glass controls as the injected overlay. Use `--color-picker --poster <image>` (or `--color-spectrum` to open the spectrum) for an isolated picker fixture.

Dragged main overlays, appearance panels and detached inspectors retain normalized screen positions per game, layout and placement edge. Positions clamp into the current viewport when the display size changes. They are stored separately from appearance defaults, and Windows app-default reset removes the cached game positions too.

First-run defaults are Light / Clear / Dark with Clear selected and None / Adaptive / Game with Adaptive selected. Surface Tint starts on; existing explicit appearance preferences remain unchanged. Toasts use event glyphs and concise feedback for preset, shortcut and reset actions; plugin error notices remain available.

Panels softly snap near screen edges while dragging. Releasing a Side Panel or Bar at the opposite edge updates its placement choice and preserves the snapped position. Adaptive Clear retains sampled hue/saturation and varies its material brightness only within a narrow range.

On Clear and Dark, low-contrast headings lighten toward white against a shared estimate that includes the game-title background and visible glass; the contrast rule never darkens the material or adds a heading shadow. Extremely bright backgrounds can still exceed what a light-only text rule can correct.
Open dropdowns retain native RmlUi selection, scrolling and keyboard behavior. Their visual mirror uses the existing glass compositor and cached targets only while a menu is open, with bright ink in Clear/Dark and dark ink in Light. Selection uses a restrained highlight rather than a solid accent fill. Small supporting text uses regular weight; it adds no blur/glow/shadow text effects.
