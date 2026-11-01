# Overlay preview

This local native Windows preview uses the same RmlUi controller as the glass
runtime. It renders over selectable screenshot backgrounds; it never reports
demonstration values as game telemetry or changes a game installation.

Build with `Build.ps1`, supplying the pinned RmlUi checkout and the existing
OptiScaler FreeType library. `Preview.ps1` opens the result. Delete toggles the
controls; Settings contains layout, Appearance and shortcut preferences. The
preview keeps its preferences separate from the game overlay.

`--self-test --output <image.png>` exercises native mouse and keyboard input,
undo/redo, hold-to-preview NR, pass controls, the four theme defaults and Settings.
Offscreen captures use a 2560 × 1440 canvas. The live window fits the monitor's
work area, including its title bar.

Appearance offers Clear, Light, Dark and Accent; Accent's character slider goes
from clearer glass through a light accent tint to a dark accent tint. More holds
Blur and Motion. Experimental font and material tuning lives in the separate,
collapsed God Mode section, available only in this preview.

The self-test also checks window containment, Advanced content slots, Bar
footer separation, Settings navigation and toast placement across 54 layout,
viewport, text-size and scale combinations. `--layout-test` runs these bounds
checks alone. Capture specific states with `--layout floating|centered|bar`,
`--page overview|neural|frame|look|passes|hdr`, `--settings`, `--custom-mfg`,
`--text-size 20|22|24` and `--scale 70..150`. These native checks use the same
document and controller as the game renderer; they do not establish gameplay
acceptance.

`Get-Scenes.ps1` optionally caches the publisher screenshots listed in
`scenes.json`. Their source URLs, ownership and hashes remain recorded there;
the images are not redistributed in the repository or runtime DLL.

The runtime boundary and its acceptance limits are documented in
[`providers/glass-overlay`](../../providers/glass-overlay/README.md).
