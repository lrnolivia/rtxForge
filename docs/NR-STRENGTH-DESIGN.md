# Visual controls — expanded in 0.6.0

The library header and individual game details expose independent NR Strength and Sharpening controls plus an MFG multiplier.

## NR Strength

Desktop NR Strength is continuous rather than preset-only:

- range: 0.0–2.0
- increment: 0.1
- default: 2.0
- slider and direct numeric input

The selected value is written to both:

    [DlssNr]
    Intensity=<value>
    SkinStructure=<value>

A value of `0.0` disables NR.

INI serialization keeps two decimal places for stable configuration output.

## Sharpening

Desktop Sharpening supports:

- range: 0.0–1.0
- increment: 0.1
- default: 0.5
- slider and direct numeric input

The selected value is written to:

    [Sharpness]
    Sharpness=<value>

A value of `0.0` disables the managed sharpening/CAS path.

## Legacy compatibility

Historical:

    Off
    Light
    Medium
    Strong

state remains accepted by the engine and can be migrated into numeric desktop values.

The desktop controls must not merely appear continuous. Numeric values must survive:

    GUI
    -> settings
    -> operation preview
    -> engine
    -> OptiScaler.ini
    -> rescan
    -> GUI

## MFG

MFG remains:

    Off
    2x
    3x
    4x
    5x
    6x

Requested ratios continue to use the native-game DLSS-G interpolation override and preserve native NVIDIA frame-generation routing.

Actual output remains game/runtime dependent.

## Safety

Global changes turn Reset All Settings into Apply Settings.

Applying updates eligible managed INIs and saves global defaults. Per-game Apply affects only that game's managed configuration.

Settings writes retain their backup/recovery behavior and refuse running games.
