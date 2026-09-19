# rtxForge development notes

<!-- RTXFORGE_CLASSIC_LIBRARY_HANDOFF_START -->
## 2026-09-18 — Classic Library production handoff

This section describes the current **classic / production** Library in
`gui/rtxforge_gtk.py`.

Do not continue this work in `redesign/`. The redesign remains a separate
project.

### Final responsive gallery contract

The previously planned fixed-slot gallery is now implemented.

Poster:

- exactly **7 visual slots per row**;
- card width follows the live Library viewport;
- Poster artwork source and aspect ratio remain independent from Wide Capsule.

Wide Capsule:

- exactly **6 visual slots per row**;
- card width follows the live Library viewport;
- Wide Capsule continues using its proper capsule artwork source and aspect
  ratio.

Shared behavior:

- there is no user-facing artwork-size slider anymore;
- window size is the sizing control: gallery cards grow and shrink
  automatically;
- widening, maximizing, restoring, and shrinking the window update card
  geometry live;
- card count per row never changes merely because additional cards could fit;
- no enlarged gallery state is allowed to become a new application-window
  minimum;
- horizontal viewport authority is the ScrolledWindow adjustment `page_size`;
- the Library uses `Gtk.PolicyType.EXTERNAL` horizontally so child minimum
  requests do not ratchet the containing window wider;
- incomplete rows receive inert ghost slots rather than changing row geometry;
- real cards and ghost slots share the same slot dimensions;
- ghost slots remain layout-only and never participate in selection, counts,
  filters, provider state, actions, or persistence.

### Right-edge handling

GTK overlay scrolling remains enabled.

The gallery reserves its scrollbar/paint allowance internally and includes a
small explicit far-right clip safety allowance. This avoids the visually
separate permanent scrollbar gutter that was rejected during testing while
keeping the final card inside the visible Library edge.

Do not revert the horizontal policy to `NEVER`: that caused large gallery child
requests to propagate into the top-level minimum width and made the window
impossible to shrink after resizing at a large width.

### Responsive card text

Poster / Wide Capsule title typography now scales with actual card width.

Current title scale:

- large: **15px**
- medium: **14px**
- small: **13px**
- extra-small: **12px**

Game titles:

- wrap normally;
- use at most **3 lines**;
- ellipsize only after the third line;
- never expand the natural width of the card.

Details buttons also become modestly more compact as card width decreases.

The existing tallest-card normalization remains authoritative: after text is
laid out, every card uses the footer height of the tallest card so rows stay
visually aligned.

### Library toolbar polish

- All / Installed / Available use more generous horizontal padding.
- NR Strength and Sharpening numeric fields have additional left-side text
  padding.
- the obsolete manual artwork-size controls were removed from the Library
  toolbar and Settings.

### List view

List remains structured as:

`Game | Location | Status | Enhancements | Actions`

Preserve:

- artwork and game identity;
- source/library location and useful path context;
- install/availability and test state;
- NR/MFG state;
- Apply / Repair where applicable;
- Game Details;
- selection and write safety;
- right-anchored Actions;
- existing classic styling.

### Validation

A dedicated `--resize-smoke` path captures six write-disabled states:

1. Poster normal
2. Poster maximized
3. Poster restored
4. Wide Capsule normal
5. Wide Capsule maximized
6. Wide Capsule restored

The accepted run verified:

- Poster: 7 slots throughout;
- Wide Capsule: 6 slots throughout;
- card widths increase on maximize and return on restore;
- the top-level window returns to its original width rather than becoming
  trapped by enlarged card minimum requests.

The final title, right-edge, filter-padding, and numeric-input polish was then
reviewed in the real write-disabled `--demo` UI.

### Important preservation rule

The fixed 7 / 6 responsive gallery is now a **completed production invariant**,
not future work.

Do not return to variable column-count fitting or a manual artwork-size control
without an explicit new user request.
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
