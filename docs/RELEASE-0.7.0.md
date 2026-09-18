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

The original 0.7.0 release commit required:

- Python compilation for the engine, bridge, desktop service, library media, and GTK UI
- engine hardening tests
- GTK smoke test
- Git whitespace validation

For the responsive-gallery maintenance checkpoint documented below, the accepted live visual state was intentionally frozen and committed without rerunning compile, smoke, or UI tests at the user's direction.

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
- froze the final Classic Poster / Wide Capsule responsive-gallery behavior: 16px outer Library inset, explicit 8px FlowBox inter-card spacing, responsive template/card widths derived from usable viewport width, and separate artwork sources for Poster and Wide Capsule;
- allowed write-disabled demo mode to reuse local Steam artwork caches so real Wide Capsule assets can be reviewed without network activity or poster substitution;
- recorded one deliberately deferred Classic Library issue: certain artwork-size/window-width combinations can still leave excessive unused width at the right edge. The future fix should adjust effective artwork sizing/column fit intelligently without changing the now-frozen padding, gap, aspect-ratio, or artwork-source behavior.

These changes do not reopen the classic interface for broad redesign. They are maintenance and usability refinements within the post-0.7 freeze policy.
<!-- RTXFORGE_070_MAINTENANCE_END -->
