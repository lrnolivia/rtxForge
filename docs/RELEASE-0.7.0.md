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
- live artwork-size control
- Poster / Wide Capsule / List controls

The redundant Library icon and Library text were intentionally removed. The full dashboard identifies the application before scrolling, and the compact titlebar takes over that identity after scrolling.

## Preserved 0.6.x work

0.7.0 preserves the finalized Library viewport and card behavior, including live artwork resizing, bounded Poster and Wide Capsule geometry, row-height normalization, wrapped compact titles, artwork-derived accents, and Game Details title wrapping.

The established Progress and Done presentations remain unchanged.

Game Details remains a separate-window presentation.

Granular NR Strength, Sharpening, and native MFG multiplier behavior remain unchanged.

## Architecture and safety

This UI release does not change provider routing or graphics-runtime architecture.

Native NVIDIA DLSS-G remains authoritative. Ada MFG stays on the native path. Provider provenance, recovery behavior, updater separation, and existing safety checks remain intact.

## Validation

The release commit requires all of the following to pass before staging:

- Python compilation for the engine, bridge, desktop service, library media, and GTK UI
- engine hardening tests
- GTK smoke test
- Git whitespace validation

## Classic UI status

With the sticky dashboard complete, the classic interface has reached its planned feature-complete 0.7 state.

Future work on the classic interface should be limited to bug fixes, compatibility, accessibility, maintenance, and specifically approved changes rather than broad redesign.

<!-- RTXFORGE_070_MAINTENANCE_START -->
## Post-0.7 maintenance

The following approved maintenance landed after the original 0.7 classic-UI completion:

- polished compact-titlebar alignment so product identity, Enhancement Mode, bulk actions, application menu, and native window controls occupy distinct visual regions;
- standardized enhancement-install actions on the save glyph;
- removed the decorative Library-top gradient in favor of explicit spacing;
- converted Game Details and Settings into movable independent windows while retaining fresh parent-relative placement when reopened;
- preserved Progress / Done on its existing stationary attached operation-dialog path;
- expanded write-disabled demo data so the compact sticky titlebar can always be visually exercised without requiring a large real Library.

These changes do not reopen the classic interface for broad redesign. They are maintenance and usability refinements within the post-0.7 freeze policy.
<!-- RTXFORGE_070_MAINTENANCE_END -->
