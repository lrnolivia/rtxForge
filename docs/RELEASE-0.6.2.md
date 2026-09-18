# rtxForge 0.6.2

## Release plumbing and desktop validation

0.6.2 tightens the development and release path around the current rtxForge desktop application without changing production RTX provider routing or native NVIDIA engine behavior.

## Interactive live smoke

The write-disabled interactive smoke mode now enters the real operation presentation automatically:

    python3 gui/rtxforge_gtk.py --live-smoke

It uses the existing application action path rather than maintaining a separate duplicate Progress implementation.

The poster or progress bar advances the fake operation through the real Progress and Done presentation.

No live game files are modified in this mode.

## Continuous development publishing

The Linux build workflow maintains `continuous` as the moving verified updater channel for successful `main` builds. It is intentionally a prerelease development channel so installed development builds can update directly from GitHub while work continues.

Numbered public Releases are not created automatically from ordinary `main` pushes. They can be published intentionally when a stable release is ready.

## CI validation

AppImage publication is now gated by additional validation before the build is published:

- Python compilation
- the v13 core-hardening test suite
- automated GTK desktop smoke validation
- expected smoke screenshots
- Git whitespace validation

The GTK smoke runs headlessly in GitHub Actions.

## Legacy loader R&D

The historical Windows/custom-loader builder and its acceptance metadata have been removed from the public production repository. That experimental path is not required by the current Linux/AppImage pipeline.

## README maintenance

AppImage examples no longer hard-code an old rtxForge version number.

The examples resolve the downloaded versioned AppImage dynamically so documentation does not become stale on every release.

## Architecture preserved

This release does not change:

- native NVIDIA-only production direction
- game-native DLSS-G authority
- Ada native MFG behavior
- provider pins
- provider deployment semantics
- NR F10 behavior
- game-root NVIDIA runtime preservation
- granular NR, sharpening or MFG tuning semantics
- the current 140x210 active-operation poster treatment

## Local validation

Before release preparation:

- 210 core-hardening tests passed
- automated GTK smoke passed
- all expected GTK smoke screenshots were produced
- the production GitHub Actions workflow parsed successfully as YAML
- no workflow tab characters were present
- `git diff --check` passed

GitHub Actions performs the new validation gate again before publishing release artifacts.
