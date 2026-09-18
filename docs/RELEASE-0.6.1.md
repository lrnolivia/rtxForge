# rtxForge 0.6.1

0.6.1 is a desktop interface refinement and UI-validation release built on the 0.6.0 tuning and native NVIDIA foundation.

No provider architecture, game-file ownership policy, native NVIDIA runtime policy, or engine transaction semantics are changed by this release.

## Refined active-operation presentation

The desktop operation presentation has been tightened substantially.

Active Progress now uses:

- a smaller, less dominant game poster
- poster-sized vertical layout geometry rather than centering against the entire dialog
- the operation text and progress bar centered relative to the poster height
- Cancel inside the main content composition
- Cancel anchored to the poster's bottom-right baseline
- stronger separation between the progress bar and Cancel
- more opaque control surfaces over busy artwork
- rounded poster treatment without the earlier clipped-corner presentation
- modal height derived from the active poster composition
- no horizontal or vertical scrollbar during active Progress or completion presentation

The active operation continues to use current-game artwork and the game's selected accent color.

## Refined completion presentation

The successful completion state retains the compact 0.6.0 visual direction while refining its controls.

The Done state uses:

- the frozen rtxForge library as the backdrop
- GTK/GSK in-app blur
- a dark translucent wash
- a centered circular green success indicator
- centered completion copy
- a compact centered Done button
- a smooth horizontal transition from the active-operation width into the compact result panel
- dark readable foreground text on the bright green Done button

The Done presentation does not display the current game's hero artwork.

## Game Details refinements

Game Details received a cleaner artwork-first presentation.

Changes include:

- removal of the conventional Game Details title bar
- Overview / Enhancements / Notes / Appearance controls placed directly over the hero
- the close control moved onto the same top overlay row
- more opaque floating controls for readability over artwork
- a larger game title
- adaptive title separation based on hero brightness
- soft dark shadow over light artwork
- restrained light glow over dark artwork

## Artwork-derived accent improvements

Game accents are more flexible and readable.

The Appearance page now supports choosing a custom game accent directly from the game's poster rather than relying only on predetermined swatches.

Bright and vibrant accent backgrounds use a darker same-hue foreground where appropriate instead of forcing white text. Dark accents continue to use a light foreground.

This applies to game-accent controls such as selected feature tabs and suggested actions.

## Settings refinement

The Settings navigation surface now visually continues through the full height of the dialog, including the footer area containing Save Settings.

The underlying settings behavior is unchanged.

## Interactive live smoke

0.6.1 adds:

    python3 gui/rtxforge_gtk.py --live-smoke

`--live-smoke` is an interactive, write-disabled UI validation mode intended specifically for Progress and Done design work.

It:

- forces demo/write-disabled behavior
- does not modify live game files
- opens the real active-operation Progress presentation
- allows the fake operation to be advanced manually
- exposes the real Done/completion presentation
- remains open for hands-on visual inspection

It is a development and UI-validation mode, not a production game-operation mode.

Do not confuse it with:

    python3 gui/rtxforge_gtk.py --smoke-test

`--smoke-test` remains the automated regression and screenshot-validation path.

## Native NVIDIA and engine behavior

0.6.1 retains the production behavior established by 0.6.0.

- Native NVIDIA DLSS-G remains authoritative.
- Ada MFG remains on the native NVIDIA route where supported.
- Existing provider boundaries remain unchanged.
- Transaction, backup, rollback, recovery, and ownership behavior remain unchanged.
- Application UI validation modes do not modify live game files.

## Validation

Release validation covers:

- Python compilation of the engine, bridge, desktop service, media layer, and GTK application
- the v13 core-hardening test suite
- automated GTK smoke and screenshot validation
- interactive write-disabled Progress / Done inspection with `--live-smoke`
- `git diff --check`
