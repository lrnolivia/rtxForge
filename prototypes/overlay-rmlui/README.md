# Overlay preview

This local native Windows preview uses the same RmlUi controller as the glass
runtime. It renders over selectable screenshot backgrounds; it never reports
demonstration values as game telemetry or changes a game installation.

Build with `Build.ps1`, supplying the pinned RmlUi checkout and the existing
OptiScaler FreeType library. `Preview.ps1` opens the result. Delete toggles the
controls; Settings contains layout, Appearance and shortcut preferences. The
preview keeps its preferences separate from the game overlay.

`--self-test --output <image.png>` exercises native mouse and keyboard input,
undo/redo, comparisons, pass controls, all three theme defaults and Settings.
Offscreen captures use a 2560 × 1440 canvas. The live window fits the monitor's
work area, including its title bar.

`Get-Scenes.ps1` optionally caches the publisher screenshots listed in
`scenes.json`. Their source URLs, ownership and hashes remain recorded there;
the images are not redistributed in the repository or runtime DLL.

The runtime boundary and its acceptance limits are documented in
[`providers/glass-overlay`](../../providers/glass-overlay/README.md).
