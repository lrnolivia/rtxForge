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
