# rtxForge Fresh-Chat Continuation

Use this file as the starting point for any fresh chat continuing rtxForge work.

## Start by inspecting the repository

Repository:

```text
~/Repos/rtxForge
```

GitHub `main` is the shared source of truth again.

Before proposing changes:

```bash
cd ~/Repos/rtxForge
git fetch origin
git status --short
git log -5 --oneline
git diff
```

Read:

1. `docs/redesign/CURRENT-STATUS.md`
2. `docs/redesign/DEVELOPMENT-HANDOFF.md`
3. `docs/redesign/LIBADWAITA-REDESIGN-GUIDE.md`
4. `docs/redesign/FUTURE-WORKER-GUIDE.md`
5. `notes.md`

Read `docs/redesign/DLSS-UNLOCKED-ADA-MFG-HANDOFF.md` only if touching backend/provider
behavior.

Inspect the actual redesign source:

```text
redesign/gui/rtxforge_redesign_lab.py
```

Do not assume a remembered local patch is present. The current repo wins.

## Git workflow

Coherent, approved redesign increments may be committed and pushed to `main`.

Do not:

- force-push `main`
- publish a stable release unless explicitly asked
- automatically publish redesign beta builds
- rewrite unrelated production work

The redesign beta workflow is manual-only.

If `origin/main` moved since the current local checkout, reconcile before editing.

## Locked shell

The user called the current shell perfect.

Do not redesign it unless asked.

Navigation:

```text
Home
Game Library
Forge
Settings
────────
Recovery
```

Preserve:

- permanent sidebar
- current branding stack/size
- left inset
- taller navigation/selectable controls
- spacing between selectable rows
- flat seamless headerbar/content
- stock Adwaita dark surfaces
- full-width page content

## Protected production surfaces

Do not broadly redesign:

- finished Library viewport/card layout/behavior
- selection/filter behavior
- artwork-size slider and artwork scaling
- standalone Game Details windows
- standalone Game Settings window
- Progress boxes and operation flow

List view is being reworked separately; ignore it for redesign decisions for now.

Done is less protected and may be revisited later.

## Completed redesign pages

Forge, Settings, and Recovery presentation shells are built.

Settings and Recovery were visually approved.

Forge is full-width with native Adwaita groups, feature mode, stacked NR/Sharpening sliders,
MFG multiplier, and review-first actions.

## Home

Use the user's exact Home mockup as the target.

Required:

- Assassin's Creed Unity hero
- green RTX headline accent
- Review Library / Forge Available Games
- four stat cards
- Recent Games horizontal strip
- System Status
- three Quick Actions

Responsive intent:

- stats: 4 across wide, 2x2 compact
- Recent Games: always horizontal; scroll when narrow
- Quick Actions: 3 across wide; vertical compact is acceptable
- icons centered in fixed wells
- text left aligned
- preserve wide mockup proportions

Inspect and launch the current implementation before changing it.

## Next work

Finish Home responsive visual polish if still needed.

Then begin migration plumbing to transplant the finished classic Library viewport into the
approved shell **without changing its layout or behavior**.

Preserve standalone Game Details, Game Settings, and Progress during migration.

## Validation

```bash
cd ~/Repos/rtxForge
python3 -m py_compile redesign/gui/rtxforge_redesign_lab.py
python3 redesign/gui/rtxforge_redesign_lab.py --smoke-test
git diff --check
python3 redesign/gui/rtxforge_redesign_lab.py
```

When a visual increment is approved, commit it with a focused message and push normally to
`origin main`.

---

## 2026-09-19 — Golden Classic responsive-layout warning

Before continuing Classic Library work, read:

docs/redesign/ASTRA-CLASSIC-UI-HANDOFF-2026-09-19.md

The late UI iteration regressed the previously correct Poster/Wide responsive grid.

Use commit d442c7ad ("Finalize responsive classic library") as the primary golden implementation reference for grid/resize mechanics.

Do not wholesale revert newer UI styling.

Restore the proven responsive layout behavior from the golden commit while preserving newer approved visual changes.
