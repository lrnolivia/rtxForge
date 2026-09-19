# rtxForge Redesign — Current Status

Updated: 2026-09-18

## Workflow

GitHub `main` is once again the shared source of truth for the redesign so fresh chats and
other workers can inspect the real current source.

After a coherent redesign increment is visually approved and validated, it may be committed
and pushed to `main`.

The redesign beta workflow is **manual-only**. Pushing redesign source must not
automatically publish or replace a beta release.

Do not force-push `main`.

Before editing:

```bash
cd ~/Repos/rtxForge
git fetch origin
git status --short
git log -5 --oneline
```

If another worker has moved `main`, reconcile that before generating patches.

## Production baseline

Production/classic rtxForge is **0.7.0**.

The classic GTK/libadwaita interface is feature-complete and effectively frozen except for
maintenance, compatibility, accessibility, bug fixes, and explicitly approved work.

Recent production maintenance after 0.7.0 may exist on `main`; inspect the current log rather
than assuming the release commit is HEAD.

## Locked redesign shell

The user called the current shell **perfect**. Do not rework it without an explicit request.

Permanent navigation:

- Home
- Game Library
- Forge
- Settings
- separator
- Recovery

Tools was removed as redundant.

Approved shell characteristics:

- `Adw.ApplicationWindow`
- `Adw.ToolbarView`
- `Adw.NavigationSplitView`
- permanent left sidebar
- flat seamless headerbar/content transition
- stock Adwaita dark neutral surfaces
- full-width page content
- rtxForge icon above the app name
- left-aligned enlarged branding
- extra left sidebar inset
- taller navigation/selectable controls
- extra breathing room between selectable rows

## Completed redesign presentation work

### Forge

- full-width page
- native Adwaita groups/rows
- Feature Mode: Neural Rendering / Multi Frame Generation / Both
- stacked full-width NR Strength and Sharpening controls
- MFG multiplier
- review-first Library actions
- backend/persistence intentionally unwired during Phase 1

### Settings

Visually approved by the user.

- Library Appearance
- Poster / Wide Capsule / List layout selector
- Dark Interface
- Online Artwork
- Steam Metadata
- Recognize Existing rtxForge Installs
- Runtime Provider
- Neural Rendering Runtime
- Network Timeout
- System Information
- Application Logs

### Recovery

Visually approved by the user.

- Recovery Safety / Review First
- Previous Changes / Recovery Records
- Cleanup / Old NR Files
- Reports & Support / Library Reports

Actions remain intentionally unwired until migration plumbing is stable.

## Home — exact target

The user supplied a specific Home mockup and wants that composition.

Required Home content:

1. Cinematic Assassin's Creed Unity hero.
2. `Bring newer RTX features to your games.` with green RTX accent.
3. Review Library + Forge Available Games.
4. Four summary cards:
   - Games in Library
   - Ready to Forge
   - Using rtxForge
   - Needs Attention
5. Recent Games horizontal strip with six cards and View All.
6. System Status.
7. Quick Actions:
   - Review Library
   - Forge Available
   - Restore a Game

The already-approved sidebar shell remains authoritative even where the mockup shows extra
sidebar destinations.

### Responsive Home requirements

The responsive mechanics work, but compact visual polish has been in active iteration.

Desired behavior:

- summary cards: 4 across when wide, clean 2x2 when compact
- Recent Games: remain one horizontal row; horizontally scroll when narrow
- Quick Actions: 3 across when wide; vertical compact layout is acceptable
- glyphs/icons remain centered inside fixed wells/circles
- text remains left aligned and intentionally spaced
- no giant vertically stretched Recent Game cards
- preserve the wide mockup proportions

Always inspect the current `redesign/gui/rtxforge_redesign_lab.py` and launch it before
assuming which Home polish patch is currently present.

## Protected production UX

### Library

Hard preservation target:

- finished viewport layout
- card geometry/styling/behavior
- selection behavior
- filters
- artwork-size slider
- artwork scaling
- Poster behavior
- Wide Capsule behavior

Color/theme harmonization may be considered. Layout/behavior changes require explicit
approval.

List view is being reworked separately and should not drive redesign decisions right now.

### Game Details

Standalone windows are protected. Preserve the current sidebar/hero/content-window model.

Do not turn Game Details back into modals or force them into the main page stack.

### Game Settings

Keep the standalone-window model.

### Progress

Strongly protected. Preserve the existing Progress boxes and operation flow.

### Done

Less protected. May be revisited later, but do not casually remove it during migration.

## Next architecture step

Once Home is visually approved:

1. create migration plumbing for the finished classic Library viewport;
2. transplant/embed that viewport into the approved shell intact;
3. preserve standalone Game Details and Game Settings;
4. preserve Progress;
5. wire Forge / Settings / Recovery only after those boundaries are stable.

Do not rebuild the Library from the early Phase 1 placeholder shell.

## Validation

For redesign-only changes:

```bash
python3 -m py_compile redesign/gui/rtxforge_redesign_lab.py
python3 redesign/gui/rtxforge_redesign_lab.py --smoke-test
git diff --check
python3 redesign/gui/rtxforge_redesign_lab.py
```

For a broad checkpoint that also includes production changes, use the repository's full
Python compilation/tests and both production/redesign smoke tests before pushing.

---

## 2026-09-19 — Golden Classic responsive-layout warning

Before continuing Classic Library work, read:

docs/redesign/ASTRA-CLASSIC-UI-HANDOFF-2026-09-19.md

The late UI iteration regressed the previously correct Poster/Wide responsive grid.

Use commit d442c7ad ("Finalize responsive classic library") as the primary golden implementation reference for grid/resize mechanics.

Do not wholesale revert newer UI styling.

Restore the proven responsive layout behavior from the golden commit while preserving newer approved visual changes.
