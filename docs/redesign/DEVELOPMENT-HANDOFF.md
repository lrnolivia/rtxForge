# DEVELOPMENT HANDOFF — rtxForge Libadwaita Redesign

Updated: 2026-09-18

## Executive state

Production is at 0.7.0 plus subsequent maintenance commits on `main`.

The redesign shell is approved. Forge, Settings, and Recovery presentation shells are
built. Home follows an exact supplied mockup and has been undergoing responsive polish.

GitHub `main` is again the shared handoff/source-of-truth mechanism so fresh chats can
inspect current work.

The redesign beta workflow must remain manual-only; normal source pushes should not
automatically publish beta artifacts.

## Preserve

### Shell

Locked unless explicitly changed:

- Home / Game Library / Forge / Settings
- Recovery separated at bottom
- no Tools destination
- permanent sidebar
- current branding size/placement
- current left inset
- current larger selectable controls and spacing
- flat seamless header/content
- full-width page content

### Library

Preserve the finished classic viewport and behavior intact:

- layout
- card geometry/style/behavior
- selection
- filters
- artwork-size slider
- artwork scaling

List view is separately in flux and is out of redesign scope for now.

### Game Details / Settings / Progress

- Game Details: standalone windows
- Game Settings: standalone window
- Progress: preserve current boxes and operation flow
- Done: may be reconsidered later

## Completed presentation work

Forge:
- full-width
- NR / MFG / Both
- stacked NR and Sharpening sliders
- MFG multiplier
- review-first actions

Settings:
- approved
- appearance, layout, metadata, runtime, diagnostics

Recovery:
- approved
- safety, history, cleanup, reports

## Home

Exact target:

- Unity hero
- green RTX headline
- two hero actions
- four stat cards
- Recent Games row
- System Status
- Quick Actions

Responsive target:

- stats 4-wide -> 2x2
- Recent Games horizontal with horizontal scroll
- Quick Actions 3-wide -> vertical compact
- centered icon wells
- tidy left-aligned text

Verify the actual source before editing because Home has had multiple rapid local iterations.

## Migration plan

After Home approval:

1. create a clean Library migration boundary;
2. embed/transplant the finished classic viewport;
3. preserve Game Details/Game Settings/Progress;
4. connect redesign Forge/Settings/Recovery to real state later.

## Git discipline

Before editing:

```bash
git fetch origin
git status --short
git log -5 --oneline
```

Push coherent approved increments to `main`.

Do not force-push.

Do not publish redesign beta assets unless explicitly requested.

---

## 2026-09-19 — Golden Classic responsive-layout warning

Before continuing Classic Library work, read:

docs/redesign/ASTRA-CLASSIC-UI-HANDOFF-2026-09-19.md

The late UI iteration regressed the previously correct Poster/Wide responsive grid.

Use commit d442c7ad ("Finalize responsive classic library") as the primary golden implementation reference for grid/resize mechanics.

Do not wholesale revert newer UI styling.

Restore the proven responsive layout behavior from the golden commit while preserving newer approved visual changes.
