# rtxForge 0.6.0

0.6.0 is a desktop UX and tuning release focused on more precise RTX controls and a substantially refined operation experience.

## Granular NR and sharpening controls

NR Strength and Sharpening are no longer limited to preset-only sliders in the desktop application.

### NR Strength

NR Strength now supports:

- 0.0 through 2.0
- 0.1 increments
- slider adjustment
- direct numeric entry

The selected value controls both:

    [DlssNr]
    Intensity=<value>
    SkinStructure=<value>

A value of `0.0` disables Neural Rendering.

The initial desktop default remains 2.0.

### Sharpening

Sharpening now supports:

- 0.0 through 1.0
- 0.1 increments
- slider adjustment
- direct numeric entry

The selected value controls:

    [Sharpness]
    Sharpness=<value>

A value of `0.0` disables the managed sharpening path.

The initial desktop default remains 0.5.

### Compatibility

Historical Off / Light / Medium / Strong state remains readable by the engine and migrates to equivalent numeric desktop values.

Numeric tuning now survives the full path:

    GUI
    -> saved settings
    -> operation review
    -> engine bridge
    -> engine
    -> OptiScaler.ini
    -> library rescan
    -> GUI

MFG remains independently selectable as Off or 2x through 6x.

INI output retains stable two-decimal formatting, so values such as 1.7 and 0.4 are written as 1.70 and 0.40.

## Refined operation UI

Install, repair, reset, and removal presentation received a substantial visual refinement.

Active operations now use:

- a significantly larger game poster
- rounded poster corners
- a thin game-accent poster border
- vertically centered operation content
- increased outer modal padding
- reduced dead space above Cancel
- a more balanced operation panel
- current-game artwork during the active operation

The Overview / Enhancements / Notes / Appearance selector is also approximately 25% slimmer than its previous presentation.

## Refined completion state

Successful operations no longer leave the current game's hero image behind the result.

The Done state uses:

- a frozen snapshot of the rtxForge library
- GTK/GSK in-app blur
- a dark translucent overlay
- a fixed circular green success indicator
- green All Done text
- a matching green Done button
- centered result content with balanced outer padding

The blur is rendered inside the GTK/GSK application pipeline rather than relying on compositor backdrop blur.

## Application updates

rtxForge retains the verified application self-update system introduced in the 0.5.9.x line.

Updates:

- read the published update manifest
- download the AppImage to a staging path
- verify expected file size
- verify SHA-256
- atomically replace the persistent installed AppImage
- preserve the previous build
- restart into the persistent installed copy

Application updates do not redeploy or alter game enhancement state.

## Native NVIDIA architecture

0.6.0 preserves the native NVIDIA product path.

- Game/native NVIDIA DLSS-G remains authoritative.
- Ada MFG remains enabled through the native NVIDIA route where supported.
- `AdaBlackwellKernels=false` remains current policy.
- NR remains default-off where configured for on-demand use.
- F10 remains the configured NR toggle where applicable.
- Game-root native NVIDIA/Streamline runtime replacement remains refused.
- Hybrid frame-generation backends remain excluded from the production path.

Requested MFG ratios still depend on the game already exposing a functional native NVIDIA frame-generation path.

## Validation

0.6.0 passed:

- Python compilation
- direct granular-strength engine validation
- legacy preset compatibility validation
- 210-test engine hardening suite
- GTK smoke test
- `git diff --check`

Visual smoke output was also used to refine operation and completion presentation before release.
