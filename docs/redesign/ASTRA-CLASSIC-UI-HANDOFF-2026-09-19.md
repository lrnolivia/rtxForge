# rtxForge Classic UI — Astra Handoff — 2026-09-19

## Read this first

The Classic GTK/libadwaita UI is extremely close to the intended final design, but tonight's late Library work introduced regressions.

Preserve the successful visual work. Do not restart the Classic UI from scratch.

Primary implementation:

gui/rtxforge_gtk.py

The user wants surgical completion, not another redesign.

## CRITICAL: I REGRESSED THE RESPONSIVE GRID / RESIZE SYSTEM

The Poster / Wide Capsule responsive layout was already working correctly before tonight's later UI changes.

I broke/regressed that behavior while trying to modify card sizing, equal-height behavior, hover styling, and List artwork.

Do not treat the newest resize/grid implementation as authoritative.

### GOLDEN REFERENCE

Use this commit as the primary known-good reference:

d442c7ad2e17814096093f045555382c34f184b8
"Finalize responsive classic library"

Also useful as earlier history:

665feb03a13ecc57351efe9fec3dde9768026938
"Freeze responsive classic library layout"

Do NOT wholesale-reset the UI to those commits.

Instead, compare the current gui/rtxforge_gtk.py against d442c7ad and restore the proven gallery sizing/responsive mechanics while preserving all newer approved styling.

### What the golden responsive behavior had

Poster:
- exactly 7 visual slots per row
- responsive card/artwork sizing from the live Library viewport

Wide Capsule:
- exactly 6 visual slots per row
- responsive card/artwork sizing from the live Library viewport

Shared behavior:
- cards grow when the viewport grows
- cards shrink when the viewport shrinks
- maximize / restore is reversible
- all sibling cards receive identical dimensions
- incomplete rows use inert ghost slots
- live width authority comes from the horizontal ScrolledWindow adjustment page_size
- Library horizontal scrolling policy uses EXTERNAL
- no gallery child request should ratchet the entire application minimum width upward
- tallest-card normalization keeps every sibling card in a row equal height
- title typography responds to available card size
- Poster and Wide Capsule use their correct separate artwork sources
- right-edge safety keeps the last slot visible
- no manual artwork-size slider

The golden implementation was explicitly validated for Poster and Wide Capsule normal / maximized / restored states.

Astra should restore THAT mechanism, not attempt to invent another resizing system.

## Current approved visual direction

Remain GTK/libadwaita:
- native dark GTK/libadwaita surfaces
- no gradients
- no glass
- no neon theme
- compact but not cramped
- artwork-derived accent colors are intentional

Spacing vocabulary:
- 4px = tiny related spacing
- 8px = normal dense spacing
- 12px = comfortable internal/container spacing
- 16px = major section seam only

Do not allow adaptive narrow-window spacing to explode beyond these values without a specific reason.

## Library metadata pills — preserve these

This work is successful.

Source pills:
- fully rounded
- no stroke/border
- roomier padding
- approximately 9px text
- approximately 11px icon
- Steam uses gui/icons/rtxforge-steam.svg
- non-Steam currently displays OTHER with controller-style icon

Test/status pills:
- WORKS = green + check
- UNTESTED = orange + beaker/science icon
- ISSUE = red + alarm/error icon
- N/A = neutral

UNTESTED is only meaningful for installed games that have not been tested.

Available / Not Installed / blocked states use N/A.

Do not restore visible BENCH / TO TEST / NEEDS TEST labels in these Library pills.

Icons should follow the foreground/state color of their pills.

Selected Poster/Wide cards currently adapt the pills to the artwork accent. Preserve that direction.

## List Status column

The upper line such as:

● Installed
● Available
● Not Installed

is intended to use the same geometry as the pill below it:
- same protected width
- same icon lane
- same text start
- transparent/invisible background
- normal title case

The actual test pill sits immediately below it.

Unavailable wording was intentionally changed to Not Installed.

## Enhancement badges

NR and MFG labels should have stronger typographic weight than their numeric values.

Example visual hierarchy:

NR 2.0
MFG 4×

NR / MFG = heavier
value = lighter

## List action buttons

Repair / Apply / unavailable-no-symbol MUST use the exact same primary button geometry.

There should not be a special wider unavailable button.

Desired visual contract:

Repair
Apply
⊘

Same:
- Gtk.Button construction
- width
- height
- padding
- alignment
- surrounding spacing

Only the child changes between text and the no-symbol icon.

The latest attempts tried to unify this but verify the current file carefully.

## Poster / Wide Capsule styling

Normal:
- neighboring cards must have identical final width
- neighboring cards must have identical final height
- dynamic viewport resizing must continue working
- titles may wrap without changing one card's final height relative to siblings
- artwork/card corners should never expose square corners

Selected:
- whole card uses exact artwork/game accent
- title uses darker same-hue accent
- darker accent should be saturated/readable, not muddy
- Details button uses translucent/light surface with darker accent text
- metadata pills adapt to accent

Hover:
- do NOT brighten the entire FlowBox child/card with a pale grey wrapper
- accent feedback belongs on the artwork
- roughly 3–3.5px inner accent stroke
- subtle matching glow is acceptable
- artwork must completely fill its container
- artwork radius and stroke/container radius must match
- no dark corner gaps behind artwork

## IMPORTANT: Poster/Wide card sizing regression

Tonight's changes also regressed equal sizing and/or padding behavior.

Use d442c7ad as the source of truth for:
- responsive width calculation
- fixed slot count
- FlowBox behavior
- exact sibling equality
- tallest-card normalization
- reversible resize
- ghost-slot layout

Do not solve this by piling more CSS overrides onto the current broken geometry.

Restore the proven Python sizing model first, then reapply the approved newer styling.

## List artwork — current major problem

The user repeatedly observed incorrect artwork dimensions in List view:
- missing/ghost artwork differed from real artwork
- Forza / non-Steam artwork also showed inconsistent geometry
- multiple widget/CSS sizing paths appeared to compete

This is unacceptable.

The user explicitly wants ONE authoritative List artwork component with ONE geometry.

Latest architectural attempt introduced:

class ListArtwork(Gtk.Overlay)

Intended invariant:
- shared fixed outer allocation
- shared fixed visible artwork dimensions
- same class for Steam
- same class for non-Steam
- same class for real artwork
- same class for missing artwork
- missing state changes only the texture/overlay, not geometry

Do not add another special ghost-size pathway.

## Known unfinished ListArtwork migration

The last smoke after the rewrite exposed at least one stale old field reference:

root._art_frame

inside selection synchronization.

The intended new API is along the lines of:

root._artwork.set_selected(selected)

Before editing anything else, search current List code for stale references to:

root._art_frame
root._picture
root._fallback
root._art_overlay
root._art_button

Do not blindly replace these globally; only migrate old List-row callers.

The final List-row contract should use the new ListArtwork object rather than exposing its internals everywhere.

## GTK minimum-width warnings

The last live run also produced many GTK warnings where allocated widths around 139–152px were smaller than children requesting roughly 160–200px.

This is likely connected to narrow-window constraints / hardcoded minimums.

Do not "fix" it by making the entire application minimum width huge.

Trace which widgets advertise those minimum sizes and remove conflicting constraints.

## List titles / spacing

Latest approved direction:
- List title approximately 10% smaller than the old 12px treatment
- around 10.8px
- small gap beneath the title before the source pill
- more breathing room between List rows
- around 8px total visual separation is reasonable

Avoid giant responsive padding at small window sizes.

## Hero / toolbar spacing

Collapsed toolbar appearance was approved.

Full hero / Library seam direction:
- native titlebar gets a little more vertical breathing room
- vertical padding above Search Library should match the lower full-hero seam
- use the slightly thicker spacing consistently on both sides
- more horizontal space between hero panels
- more horizontal space between Install All / Remove All / Reset All
- install buttons and hero panels should share a coherent horizontal rhythm
- more breathing room between the Library controls/header and the first game row
- user specifically requested roughly twice the earlier gap in that seam

Keep narrow windows compact.

## Floating bottom toolbar

Preserve:
- persistent selection pill on lower left
- action controls on lower right
- equal bottom baseline / distance from app edge

But:
- selection pill should NOT be as tall as the action buttons
- keep it one line
- maintain comfortable horizontal padding
- final Library rows/cards must scroll high enough to clear the bottom fade/actions

## Toast

Verify the status toast still uses an opaque darkest-native-GTK/libadwaita grey rather than a translucent whitish surface.

## Do not redo successful work

Do not begin by changing:
- pill design
- selected accent-card treatment
- overall GTK/libadwaita palette
- Progress / Done UI
- provider/runtime architecture

Progress / Done in particular have substantial finished work and are not part of this cleanup.

## Recommended Astra order

1. Read this handoff.
2. Read notes.md.
3. Inspect current HEAD and gui/rtxforge_gtk.py.
4. Compare current gallery code directly against d442c7ad.
5. Restore the golden responsive grid/resize algorithm without reverting newer visuals.
6. Complete the ListArtwork migration and remove stale callers.
7. Make Apply / Repair / ⊘ use identical primary-button geometry.
8. Resolve narrow-width minimum-size warnings.
9. Verify spacing.
10. Only then do visual cleanup.

The Classic UI is very close. Do not turn this into another redesign.
