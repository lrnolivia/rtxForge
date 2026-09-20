# rtxForge development notes

<!-- RTXFORGE_CLASSIC_LIBRARY_HANDOFF_START -->
## 2026-09-19 — Classic Library / ColumnView handoff

This section is the current handoff for the **classic / production**
Library implemented in:

`gui/rtxforge_gtk.py`

Do **not** move this work into `redesign/`.

The redesign remains separate and currently has unrelated local work that must
not be staged as part of classic maintenance.

### Current state

The classic Library has gone through a substantial responsive-layout and List
view pass.

The result is materially improved and usable, but the List should **not** be
treated as visually final yet.

The next agent should continue polishing the existing implementation rather
than replacing it.

---

### Completed responsive gallery contract

Poster:

- exactly **7 visual slots per row**;
- card sizing follows the live Library viewport;
- Poster uses the correct Poster artwork source/aspect ratio.

Wide Capsule:

- exactly **6 visual slots per row**;
- card sizing follows the live Library viewport;
- Wide Capsule uses the correct capsule artwork source/aspect ratio.

Shared behavior:

- no manual artwork-size control;
- window width is the gallery sizing control;
- cards resize live while widening, shrinking, maximizing, and restoring;
- the slot count does not change simply because another card could fit;
- incomplete rows use inert ghost slots;
- ghost slots are layout-only;
- horizontal authority comes from the ScrolledWindow adjustment `page_size`;
- horizontal policy remains `Gtk.PolicyType.EXTERNAL`;
- `RIGHT_EDGE_SAFETY=32` remains intentional;
- overlay scrollbar behavior remains intentional.

These are completed production invariants.

Do not return to variable card counts or a manual artwork-size slider without
an explicit request.

---

### Gallery title behavior

Poster / Wide Capsule titles:

- responsive typography;
- maximum 3 lines;
- ellipsize only after line 3;
- tallest-card normalization keeps rows aligned.

Current responsive title scale remains approximately:

- 15px
- 14px
- 13px
- 12px

Do not regress this while working on List.

---

### Hero / Library header work

The classic hero was compacted without replacing its structure.

Bulk actions:

- Install All
- Remove All
- Reset All

sit at the bottom of the hero text area, aligned with the metadata/content
rather than consuming a separate oversized region.

The sticky-header behavior remains part of the classic implementation.

Do not redesign the hero as part of List cleanup unless specifically asked.

---

### Structured List view

List is now a real `Gtk.ColumnView`.

Current logical columns:

`Game | Location | Status | Enhancements | Actions`

This replaced the previous hand-built List row/header arrangement.

The implementation includes:

- `LibraryGameItem`
- `Gtk.ListStore`
- filtering/sorting models
- ColumnView factories
- List selection synchronization
- row activation into Game Details
- artwork-based selection accent
- action-button state styling

### Column contract

Game:

- remains the first column;
- owns spare horizontal viewport width;
- user-resizable;
- should never collapse to a useless width;
- contains checkbox, 96x45 artwork, title, and source pill.

Location:

- user-resizable;
- intended clamp is approximately **160–360px**;
- remains a single-line path/location field;
- may ellipsize rather than wrap vertically.

Status:

- natural protected width;
- not intended to absorb spare viewport width.

Enhancements:

- natural protected width;
- not intended to absorb spare viewport width.

Actions:

- natural protected width;
- remains right-aligned;
- should visually hug the far-right side of the List.

Columns to the right of Game may be reordered.

Game itself must remain first.

---

### List row-height contract

A major bug allowed wrapped titles to make rows absurdly tall.

The current implementation intentionally uses only **two row geometries**:

- normal title row: **52px content geometry**
- wrapped two-line title row: **78px content geometry**

Wrapped rows are therefore approximately 1.5x the normal row.

Game titles:

- may use up to 2 lines;
- use `WORD_CHAR` wrapping;
- ellipsize after the second line;
- should not create arbitrary row heights.

The current implementation also protects the title from collapsing to a
one-character natural width.

Do not reintroduce unconstrained title wrapping.

---

### List alignment

The following were already judged correct before this handoff and should be
preserved:

- vertical centering;
- column alignment.

Do not disturb those while refining horizontal spacing.

---

### Column controller/header

The old ColumnView controller/header was visually too thick and heavy.

It has been reduced to a compact native sortable/reorderable header with:

- roughly 29px header height;
- roughly 27px control height;
- 13px bold labels;
- subtle background/border treatment;
- hover and active feedback.

Further visual refinement is allowed, but keep it compact and obviously
interactive.

---

### List artwork

List artwork remains **96x45 Wide Capsule artwork**.

Current implementation adds clipping/rounding at multiple layers:

- outer artwork frame;
- overlay;
- artwork button;
- picture.

This was specifically added because square corners were leaking through the
rounded treatment.

The artwork itself should remain compact; do not convert List back to Poster
art.

Selection accent belongs around the artwork, not around the entire row.

---

### Metadata pills

Game identity uses compact metadata pills.

Source pill:

- STEAM / NON-STEAM;
- dark grey surface;
- medium-grey text;
- must never display as `...`.

Test state:

- UNTESTED uses the lighter treatment;
- actual tested/result states use the inverse darker treatment;
- List test state belongs under Status rather than being duplicated inside
  Game.

Gallery metadata sizing was also normalized so source/test pills do not become
ellipsis-only labels when cards shrink.

---

### Accent styling

Preserve the current accent semantics:

- selected List artwork gets the accent outline;
- card/game titles may use the configured accent;
- checked selection controls use the accent;
- selected actions may use the accent;
- normal action buttons remain neutral grey.

The accent picker remains an `Adw.Window` with live preview and explicit
Cancel / Done behavior.

Do not replace it while doing List cleanup.

---

### Dark / light panel seam

The Library has a dark upper surface and lighter Library surface.

The earlier runtime geometry experiment using
`balance_library_panel_seam()` was removed.

Current direction is explicit static spacing:

- dark-side bottom spacing: approximately 12px;
- light-side Library top spacing: approximately 12px.

There should be only one canonical `viewbar.set_margin_top(...)` assignment
after normalization.

This is closer than the previous state but should still be visually inspected
by the next agent. The user has **not** declared the List/seam visually final.

Do not restore runtime `compute_bounds()`-style seam measurement.

---

### What is still open

The current state is a handoff baseline, not a declaration that List is
finished.

The next agent should visually inspect and refine:

- horizontal distribution across the full List width;
- Game/Location resize behavior at narrow and wide window sizes;
- Actions staying cleanly at the far-right edge;
- exact List outer padding;
- exact controller/header visual weight;
- final dark/light seam balance;
- any remaining artwork corner artifacts;
- normal-vs-wrapped row visual rhythm.

Work **from the current ColumnView implementation**.

Do not throw it away and restart.

---

### Protected classic behavior

While continuing this work, do not casually modify:

- Progress modal;
- Done modal;
- Game Details;
- Game Settings;
- provider/write-safety logic;
- fixed 7 Poster / 6 Wide Capsule responsive gallery;
- gallery ghost-slot behavior;
- current selection/filter behavior;
- existing NR/MFG functionality.

Progress/Done in particular have significant finished work behind them and are
not part of this List polish task.

---

### Repository hygiene for the next agent

The local worktree at handoff may still contain unrelated dirty work under:

`redesign/`

It may also contain temporary `rtxforge-*.patch` files from iterative classic
development.

Those are **not** part of the production commit unless explicitly requested.

When committing classic maintenance, stage exact paths instead of using:

`git add -A`

or

`git add .`

GitHub `main` remains the shared source of truth once approved work is pushed.

Do not force-push.
<!-- RTXFORGE_CLASSIC_LIBRARY_HANDOFF_END -->


## 2026-09-18 — 0.7 classic freeze + redesign handoff

Production/classic rtxForge is 0.7.0 plus later maintenance work on `main`.

The classic UI is frozen apart from maintenance, compatibility, accessibility, bug fixes,
and explicitly approved changes.

### Preserve from classic

- finished Library viewport
- card geometry/style/behavior
- selection/filters
- automatic viewport-driven artwork scaling
- fixed 7-Poster / 6-Wide-Capsule rows
- Poster/Wide Capsule rules
- standalone Game Details
- standalone Game Settings
- Progress boxes/flow
- native NVIDIA/provider safety architecture

List view is being reworked separately.

### Redesign shell

User-approved and locked:

- Home
- Game Library
- Forge
- Settings
- Recovery separated at bottom
- no Tools
- full-width content
- current branding/inset/control sizing/spacing

### Page status

Forge: built.

Settings: built and visually approved.

Recovery: built and visually approved.

Home: exact supplied mockup; responsive visual polish active.

### Git workflow

GitHub `main` is again the shared source of truth.

Push coherent approved increments normally.

Do not force-push.

Redesign beta workflow is manual-only and should not auto-publish on source pushes.

### Next

Finish Home visual polish, then build migration plumbing for the finished Library viewport.

---

## CSS / STYLE AUDIT HANDOFF — 2026-09-19 01:39 EDT

### Current state

The current rtxForge build was intentionally committed and pushed **AS-IS WITHOUT TESTING**.

Do not assume the current UI has been regression-tested after the latest Library/game-card/layout work.

### NEXT WORKER — FIRST PRIORITY

Before doing more visual tweaking, perform a dedicated audit for **duplicate, overlapping, stale, and competing CSS/style rules**.

The goal is to determine whether multiple styling systems are fighting each other and causing changes to appear inconsistent, unexpectedly subtle, impossible to override cleanly, or dependent on widget state/order.

Audit especially:

- duplicate CSS selectors
- selectors defined more than once with different values
- competing rules with different specificity
- old CSS left behind after UI redesign iterations
- CSS providers being installed more than once
- multiple providers with overlapping selectors
- runtime-generated CSS blocks
- repeated `add_css_class()` / `remove_css_class()` behavior
- widgets carrying several classes that affect the same property
- inline/widget-level sizing fighting CSS sizing
- hardcoded margins/padding/min-width/max-width fighting responsive code
- style rules duplicated between classic UI and redesign/lab code
- hover/selected/active rules overriding base rules unexpectedly
- broad selectors affecting Library widgets unintentionally
- obsolete selectors that no longer correspond to the intended widget hierarchy

### Areas requiring special attention

The recent trouble has centered heavily around the **Library and game cards**, including:

- Poster view
- Wide Capsule view
- List view
- artwork sizing
- dynamic spacing/padding
- card/title/badge spacing
- equal-height card behavior
- responsive resizing
- badges
- hover surfaces
- alternating row/card surfaces
- GTK/libadwaita stock surface behavior

There have been several rapid iterations in this area. Assume there may now be **multiple generations of styling code coexisting**.

### Audit strategy

First inventory what exists. Do **not** immediately solve visual problems by adding another override.

Trace each visible Library component back to:

1. widget creation
2. CSS classes attached to it
3. every selector matching those classes
4. every CSS provider capable of supplying those selectors
5. Python-side size/margin/alignment constraints affecting the same property

Where duplicate or competing rules exist, identify which rule is canonical and which ones are legacy before deleting or consolidating anything.

The desired end state is a **single understandable source of truth** for each major Library visual behavior.

### Important

Preserve current functionality while auditing.

Do not start another broad redesign.

Do not paper over conflicts with increasingly specific CSS.

Find the competing rules first.

## 2026-09-19 — Classic UI CSS dedupe

A focused cleanup was completed in `gui/rtxforge_gtk.py` after auditing the classic GTK/libadwaita stylesheet for duplicate and competing rules.

### Completed

- Removed obsolete / duplicate legacy List-view CSS that was competing with the current `Gtk.ColumnView` implementation.
- Consolidated duplicate Library pill styling.
- Separated Library status styling that had been unnecessarily coupled.
- Preserved the current Poster, Wide Capsule, and List layouts.
- Preserved current alternating Library surfaces and hover behavior.
- Preserved the current responsive Library sizing behavior.
- No redesign-lab changes were part of this cleanup.

### Validation

The resulting classic UI was manually checked with the live smoke and no visible regression was observed.

Per user direction, no additional automated tests, smoke tests, unit tests, or syntax-test suite were run before this commit.

### Next worker

Continue auditing `gui/rtxforge_gtk.py` for stale, duplicate, overly broad, or competing CSS selectors.

When possible, consolidate the active selector instead of adding another late override.

Treat the current visual layout as the baseline. Do not alter unrelated Library layout, resizing behavior, card geometry, or the redesign lab while doing CSS cleanup unless explicitly requested.

---

## 2026-09-19 — IMPORTANT ASTRA CORRECTION: golden responsive Library

The late-night Classic UI work regressed the previously correct Poster/Wide grid and live resize behavior.

This regression was introduced during the later visual/card/List-artwork iteration and should NOT become the new baseline.

Primary golden reference:

d442c7ad2e17814096093f045555382c34f184b8
Finalize responsive classic library

Earlier useful reference:

665feb03a13ecc57351efe9fec3dde9768026938
Freeze responsive classic library layout

Astra should compare the current gui/rtxforge_gtk.py directly against d442c7ad and recover the known-good responsive mechanics rather than inventing another sizing algorithm.

Preserve newer approved styling while restoring:
- fixed 7 Poster slots
- fixed 6 Wide Capsule slots
- live viewport/page_size sizing
- reversible maximize/restore
- identical sibling width and height
- tallest-card normalization
- correct ghost-slot geometry
- EXTERNAL horizontal ScrolledWindow behavior
- proper right-edge safety

Do not wholesale revert the current UI to the golden commit. Transplant/restore the responsive layout behavior only.

Canonical expanded handoff:

docs/redesign/ASTRA-CLASSIC-UI-HANDOFF-2026-09-19.md

## 2026-09-19 — Classic geometry repair (Astra)

- Compared the live gallery solver with d442c7ad: the golden viewport/7/6-slot algorithm was already present. The regression came from child minimum widths, especially two full metadata pills plus footer padding.
- Compact footers now stack the approved pills; wide footers retain the horizontal arrangement. Corrected the malformed card-info selector and kept 8px internal padding.
- ListArtwork now uses explicit-ratio CoverPicture measurement: real Steam, non-Steam and missing artwork all allocate 96x45 inside the same border. Existing selection callers already used the new API.
- Shared List action padding/width rules no longer add a second minimum width. Balanced initial hero seam at 16px and made toast background opaque native dark.
- Enhanced --resize-smoke to check allocated sibling dimensions, real/ghost slot widths and final-slot bounds, not just requested sizes. All six normal/maximized/restored states passed (Poster 148/311/148; Capsule 174/364/174). Focused write-disabled List inspection verified matching artwork dimensions; no game files changed.
- VERSION remains 0.7.0. Next: consolidate stale Classic styling before updater work. Redesign untouched.

## 2026-09-19 — Classic style consolidation

- Consolidated repeated selector definitions without changing the final palette: header/toolbar, List row/title, pills, selection controls and gallery artwork frames. Removed obsolete pre-ListArtwork ghost/picture rules and superseded title scales.
- Removed the old FlowBox List branch and the duplicate 380-line art-scale resize pass. Initial cards and resizing now use the same golden viewport solver; retained button and artwork-control geometry.
- Audited CSS providers: one base provider; artwork providers cached by color; temporary picker provider removed on close. No provider duplication fix needed.
- Six-state allocated-geometry smoke passed after consolidation. Focused List demo verified real/missing artwork 96x45 and identical Repair/Apply/unavailable button content allocation (72x30 plus shared padding), with actions inside the viewport. GTK stylesheet parser and minimum-width warnings absent in the final List run; the host emits an unrelated Intel Vulkan-device warning before successfully rendering.
- Classic checkpoint is local only; no publishing or game deployment.

## 2026-09-20 — Active user-directed Classic expansion (supersedes fixed-slot freeze)

Latest user request explicitly replaces the fixed 7/6 contract and previous protected Progress/Done restrictions:
- Equal 16px cell gaps/insets throughout dashboard, Details and Settings; neutral gray/contrast sweep, NVIDIA green instead of system accent (preserve intentional artwork accents).
- Tuning is Presets, collapsed by default with one-time subtle attention animation; installation presents optional preset edits and Continue in its modal.
- DLSS File Management belongs in Game Details/appropriate Settings, routine handling automatic during install without extra review questions. Native updater backend currently uncommitted and tested; its standalone review UI must be integrated/reworked.
- Taller Details hero; prevent hidden page content; accent color swatch plus Edit.
- Gallery pills bottom anchored next to Details. Preferred 3–9 games per row (odd preferred, even allowed), adapt count down/up at cramped/oversized widths; preserve live reversible resizing and equal actual cards.
- Fix List scroll jump/slot-machine effect and column resizing. Game resizable with useful nonwrapping minimum, header text aligned to artwork; larger titles; matching pill thickness; crisp scalable Steam SVG.
- Center opaque operation bubble; remove bottom fade/right actions. Top actions act on selection when nonempty. Clearly styled/selectable Select All/Clear placement.
- Done matches Progress: left content, big check far left, Done far right, native dark background, no blur.
- Repair only in Details, with clear file-repair explanation; Reset Presets only near preset controls.
- FINAL terminology choice: **Features**, replacing Enhancements. Use Install Features / Restore Original Files / Repair Feature Files / Reset Presets.
- Finish this UI work before resuming DLSS-Unlocked stack updates. No live game writes have been performed.

## 2026-09-20 — Features / Presets / DLSS File Management completed

- User refinement implemented: compact collapsed Presets row, galleries fill exactly between equal 16px side margins (removed the obsolete right-edge reserve), Card size icon opens a Games per row popover, and Done is now 500×180 with the approved layout.
- Features is the user-facing terminology throughout the classic UI and engine progress. Reset/Apply Presets live beside tuning; file repair lives in Game Details → Features. Sidebar/content/footer selection is synchronized, including direct page changes.
- Responsive preferred density 3–9, automatic odd-count adaptation, bottom-anchored metadata and fixed List row/art geometry. Game column resizes with a 420px minimum; Game header aligns with artwork. Native Steam SVG stays vector-rendered.
- Native DLSS File Management uses immutable catalog verification and existing hash-guarded transactions. Default-on automatic management follows successful feature installation, only updates older known versions, excludes provider-owned/private files, and preserves verified originals. Per-game Update/Restore controls live in Details; Settings can disable automatic management.
- Cancellation is closed on the GTK thread before the engine's final undo decision; late cancellation at that boundary still rolls back. DLSS network failures are logged without misreporting successful feature installation.
- Verified: 9 disposable native-DLSS lifecycle/guard tests, 2 cancellation-boundary tests, syntax/diff checks, full write-disabled GUI smoke, six exact-edge resize allocations, 760px Poster/Wide allocations, List resize/scroll-to-top at fixed 64px row height, and visual review of Appearance, Features Presets, optional install Presets, and compact Done.
- No installed game files changed during development or verification. VERSION remains 0.7.0; DLSS-Unlocked stack pins and redesign remain unchanged.

- Follow-up spacing refinement: removed dashboard top inset/padding (including the scroll-to-top reset), removed legacy library bottom clearance, tightened the gap before cards/rows, and replaced the green Presets pulse with a tiny neutral blinking dot. Per explicit user correction, Game Details poster/text are bottom-aligned with a 16px lower inset; all text stays left-aligned. Title separation is a soft zero-offset glow rather than a directional drop shadow. Card-size popover mapping and an even preference of six columns verified.
- Added source (Steam/Non-Steam) and testing status pills below the Game Details description, reusing the library pill style. Removed source from the developer/date line to avoid duplication. User asked to push the UI checkpoint before further DLSS work; draft file-management integration will be kept out of that push and receive a separate Game Details tab in the follow-up.
