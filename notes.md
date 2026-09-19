# rtxForge development notes

<!-- RTXFORGE_CLASSIC_LIBRARY_HANDOFF_START -->
## 2026-09-18 — Classic Library production handoff

This section is the current handoff for the **classic / production** Library in
`gui/rtxforge_gtk.py`.

Do not continue this work in `redesign/`. The redesign is a separate project and
must not be changed while working this handoff.

### Work completed in the current classic Library worktree

The production Library has received a cumulative round of post-0.7 maintenance
and structural work.

Poster / Wide Capsule work:

- preserves separate Poster and Wide Capsule artwork paths;
- preserves the user's artwork-size setting rather than silently stretching
  artwork to consume spare space;
- restores a fixed 16px outer Library inset;
- prevents List-mode expansion/alignment state from leaking back into gallery
  modes;
- keeps card/art geometry stable while horizontal spare room is handled by the
  row layout;
- clears old per-card remainder corrections when artwork size or allocation
  changes;
- uses the ScrolledWindow horizontal adjustment `page_size` as the authoritative
  visible viewport width after allocation, avoiding timing-sensitive scrollbar
  width guesses;
- uses the same viewport-width definition in automated smoke validation;
- fixes the GTK4 smoke regression by reading the FlowBox request through
  `get_size_request()` rather than the nonexistent `get_width_request()`.

The responsive right-edge implementation has been explored extensively. The
current implementation is a useful checkpoint, but the user has chosen a
simpler deterministic gallery contract for the next worker rather than
continuing to tune variable column-count math.

List view work:

- List is now a true structured row rather than the old generic card treatment;
- column structure is explicitly:

  `Game | Location | Status | Enhancements | Actions`

- Game contains thumbnail, selection control, title and app/detection metadata;
- Location contains source plus relative path and retains the complete game path
  as a tooltip;
- Status contains install/availability state plus test status;
- Enhancements contains NR and MFG state chips;
- Actions contains the primary Apply / Repair action plus Game Details;
- header and body use matching column geometry;
- Actions are right anchored;
- existing rtxForge styling, selection behavior, action behavior and write
  safety remain intact.

### NEXT WORKER — approved gallery plan

Do **not** keep iterating on automatic "how many cards fit?" column selection.

Replace Poster / Wide Capsule gallery layout with deterministic fixed slot
counts whose card size responds to the viewport:

#### Poster

- exactly **7 slots per row**;
- poster artwork must never be narrower than **72px**;
- current card allowance is artwork width + 4px, so the minimum card slot is
  76px;
- preserve **16px outer inset** on both sides;
- at the minimum Library viewport of **612px**, seven 76px slots leave 48px for
  six gaps = **8px per gap**.

#### Wide Capsule

- exactly **6 slots per row**;
- wide-capsule artwork must never be narrower than **88px**;
- current card allowance is artwork width + 4px, so the minimum card slot is
  92px;
- preserve **16px outer inset** on both sides;
- at a **612px** Library viewport, six 92px slots leave 28px for five gaps =
  **5.6px average gap**;
- therefore internal capsule spacing may compress below 8px at the minimum
  width, but artwork must not shrink below 88px.

#### Shared fixed-slot contract

- **612px is the hard minimum usable Library viewport width**;
- set the application/window minimum so the Library viewport itself cannot fall
  below that 612px requirement after surrounding UI/chrome is accounted for;
- artwork/card size should scale dynamically upward with wider windows;
- column count does not change:
  - Poster = 7
  - Wide Capsule = 6
- maintain 16px outer inset;
- distribute remaining horizontal space evenly between slots;
- rows must run visually edge-to-edge between those outer insets;
- do not stretch one card differently from the others;
- preserve separate Poster and Wide Capsule media sources.

### Ghost slots

Incomplete rows should be padded with inert **ghost cards** until every row has
the full slot count.

Ghost design:

- same neutral grey family as the existing secondary/label text;
- ghost surface at approximately **50% opacity**;
- small game icon centered in the slot;
- icon uses the normal, full-strength label grey;
- same geometry as a real card in that view;
- not selectable;
- not clickable;
- no install / reset / remove actions;
- never included in game counts, filters, selection state or operations.

The ghosts are structural layout placeholders, not fake games.

### Important handoff constraint

The fixed-slot / ghost-card plan above is **approved next work but is not yet
implemented in this checkpoint**.

Start from the production classic Library code and implement it there only.
Do not modify redesign files while doing this work.
<!-- RTXFORGE_CLASSIC_LIBRARY_HANDOFF_END -->


## 2026-09-18 — 0.7 classic freeze + redesign handoff

Production/classic rtxForge is 0.7.0 plus later maintenance work on `main`.

The classic UI is frozen apart from maintenance, compatibility, accessibility, bug fixes,
and explicitly approved changes.

### Preserve from classic

- finished Library viewport
- card geometry/style/behavior
- selection/filters
- live artwork-size slider
- artwork scaling
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
