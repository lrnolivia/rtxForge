# rtxForge 0.7.0

## Purpose

0.7.0 completes the planned feature work for the classic GTK/libadwaita interface and finalizes the compact Library/dashboard scrolling experience.

## Compact sticky dashboard

The full dashboard remains visible at the top of the Library with its established branding, bulk actions, Enhancement Mode controls, and tuning controls.

After the large dashboard scrolls away, the existing native titlebar reveals a compact dashboard containing:

- rtxForge icon and title
- Enhancement Mode selector
- Install All
- Remove All
- Reset All / Apply Settings

The compact controls mirror the canonical dashboard controls rather than maintaining a separate configuration state.

The sticky dashboard occupies titlebar space that already existed, avoiding an additional full-height toolbar row.

## Library toolbar

The Library toolbar remains one compact persistent row containing:

- Search
- All / Installed / Available
- Select all / Clear
- Poster / Wide Capsule / List controls

The redundant Library icon and Library text were intentionally removed. The full dashboard identifies the application before scrolling, and the compact titlebar takes over that identity after scrolling.

## Preserved 0.6.x work

0.7.0 preserves the finalized Library viewport and card behavior, including responsive Poster and Wide Capsule geometry, row-height normalization, wrapped compact titles, artwork-derived accents, and Game Details title wrapping. Post-0.7 maintenance replaces manual artwork resizing with automatic viewport-driven fixed-slot scaling.

The established Progress and Done presentations remain unchanged.

Game Details remains a separate-window presentation.

Granular NR Strength, Sharpening, and native MFG multiplier behavior remain unchanged.

## Architecture and safety

This UI release does not change provider routing or graphics-runtime architecture.

Native NVIDIA DLSS-G remains authoritative. Ada MFG stays on the native path. Provider provenance, recovery behavior, updater separation, and existing safety checks remain intact.

## Validation

The original 0.7.0 release commit required:

- Python compilation for the engine, bridge, desktop service, library media, and GTK UI
- engine hardening tests
- GTK smoke test
- Git whitespace validation

For the later responsive-gallery maintenance checkpoint documented below, the
classic GUI was Python-compiled, checked with `git diff --check`, exercised in
write-disabled live demo mode, and validated with a dedicated six-state
responsive screenshot smoke covering Poster and Wide Capsule at normal,
maximized, and restored widths.

## Classic UI status

With the sticky dashboard complete, the classic interface has reached its planned feature-complete 0.7 state.

Future work on the classic interface should be limited to bug fixes, compatibility, accessibility, maintenance, and specifically approved changes rather than broad redesign.

<!-- RTXFORGE_070_MAINTENANCE_START -->
## Post-0.7 maintenance

Approved maintenance after the original 0.7 classic-UI completion includes:

- polished compact-titlebar alignment so product identity, Enhancement Mode,
  bulk actions, application menu, and native window controls occupy distinct
  regions;
- standardized enhancement-install actions on the save glyph;
- removed the decorative Library-top gradient in favor of explicit spacing;
- converted Game Details and Settings into movable independent windows while
  retaining fresh parent-relative placement when reopened;
- preserved Progress / Done on its established attached operation-dialog path;
- expanded write-disabled demo data so sticky-titlebar and Library behavior can
  be exercised without a large real Steam library;
- replaced variable gallery column fitting with a deterministic responsive-scale
  model:
  - Poster = exactly **7 slots per row**;
  - Wide Capsule = exactly **6 slots per row**;
  - card size follows the live viewport rather than a manual artwork-size
    control;
- removed the Library and Settings artwork-size sliders;
- added inert ghost slots to complete partially populated visual rows;
- changed live resize plumbing to observe the horizontal adjustment
  `page_size`;
- changed the Library ScrolledWindow horizontal policy to `EXTERNAL`, preventing
  enlarged gallery child requests from becoming a new top-level minimum width;
- retained GTK overlay scrolling while reserving internal scrollbar/paint space
  plus a far-right clip-safety allowance;
- added responsive gallery typography:
  - 15px maximum title size;
  - 14px / 13px / 12px compact steps;
  - maximum three wrapped title lines;
  - ellipsis only after line three;
- added matching compact sizing for per-card Details buttons;
- preserved tallest-card footer normalization so every card in the gallery
  remains equal height;
- increased All / Installed / Available horizontal padding;
- added internal left padding to the NR Strength and Sharpening numeric fields;
- added a dedicated six-state `--resize-smoke` validation path with screenshots
  for Poster and Wide Capsule normal/maximized/restored states;
- made screenshot capture tolerate frames where GTK has not yet produced a
  render node instead of crashing the smoke test.

The accepted resize validation demonstrated reversible responsive sizing while
preserving the fixed slot counts: cards expanded at maximized width and returned
to their original width after restore in both gallery modes.

These changes do not reopen the classic interface for broad redesign. They are
maintenance and usability refinements within the post-0.7 freeze policy.
<!-- RTXFORGE_070_MAINTENANCE_END -->
