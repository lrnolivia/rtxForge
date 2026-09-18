# rtxForge development notes

## 2026-09-18 — 0.7.0 classic freeze + Phase 1 redesign handoff

### Production / classic status

- Current production release: **0.7.0**.
- The classic GTK/libadwaita interface has completed its planned feature work.
- Future classic work is maintenance, compatibility, accessibility, bug fixes, and specifically approved changes only.
- Do not restart a broad classic redesign.

### Preserve from classic 0.7.0

- Finished Library viewport.
- Existing card geometry, styling, wrapping, height normalization, selection behavior, filters, and artwork-derived accents.
- Live artwork-size slider and artwork resizing behavior.
- Poster and Wide Capsule artwork rules.
- Compact sticky Library/dashboard titlebar behavior.
- Granular NR Strength and Sharpening controls.
- Native MFG multiplier behavior.
- Standalone Game Details windows with current sidebar / hero / content model.
- Standalone Game Settings window model.
- Active Progress boxes and operation flow.
- Current native-NVIDIA/provider safety architecture.

The List view is being reworked separately. Ignore it for redesign decisions until that work is explicitly brought back into scope.

### Redesign workflow

Redesign work is **local-only** for now.

- Work in `redesign/`.
- Do not commit, push, tag, publish, or move remote `main` for redesign iteration.
- Do not trigger or update redesign beta CI unless explicitly asked.
- The old `.github/workflows/redesign-beta.yml` remains in the repository but is parked.
- Do not edit production `gui/rtxforge_gtk.py`, engine/provider code, packaging, or updater while doing redesign-only work.
- Keep unrelated dirty production files untouched.

### Approved shell — locked

The user called the current shell perfect. Treat it as the baseline:

- `Adw.ApplicationWindow`
- `Adw.ToolbarView`
- `Adw.NavigationSplitView`
- permanent left sidebar
- Home / Game Library / Forge / Settings
- Recovery isolated at the bottom
- Tools removed
- flat seamless titlebar/content transition
- stock Adwaita dark surfaces
- full-width main content
- rtxForge icon above title, left aligned
- enlarged branding
- extra left inset
- taller navigation/selectable controls
- extra vertical breathing room between selectable rows

Do not rework the shell unless explicitly asked.

### Forge — completed presentation shell

- Full-width native page.
- Do not use the narrow `Adw.PreferencesPage` wrapper.
- Feature Mode: Neural Rendering / Multi Frame Generation / Both.
- Full-width stacked NR Strength and Sharpening sliders with numeric values.
- MFG multiplier preview.
- Review-first bulk actions are present but unwired.

### Settings — completed presentation shell

User feedback: **gorgeous**.

- Library Appearance.
- Poster / Wide Capsule / List layout selector.
- Dark Interface.
- Online Artwork.
- Steam Metadata.
- Recognize Existing rtxForge Installs.
- Runtime Provider.
- Neural Rendering Runtime.
- Network Timeout.
- System Information.
- Application Logs.
- Phase 1 controls remain unwired to production state.

### Recovery — completed presentation shell

User feedback: **looks great**.

- Recovery Safety / Review First.
- Previous Changes / Recovery Records.
- Cleanup / Old NR Files.
- Reports & Support / Library Reports.
- Phase 1 actions remain unwired.

### Home — exact target, still in polish

The user supplied an exact Home mockup and wants that content composition.

Required Home content:

- Assassin's Creed Unity cinematic hero.
- `Bring newer RTX features to your games.` headline with green RTX accent.
- Review Library.
- Forge Available Games.
- Four stat cards: Games in Library / Ready to Forge / Using rtxForge / Needs Attention.
- Recent Games horizontal strip with six cards and View All.
- System Status.
- Quick Actions: Review Library / Forge Available / Restore a Game.

Current state:

- Wide Home layout is broadly on target.
- Responsive mechanics work: the content reacts when the window narrows.
- Compact presentation still needs visual cleanup.
- Recent Games should stay a horizontal row and scroll horizontally when needed.
- Stat cards should be four-across when wide and a clean 2x2 when compact.
- Quick Actions may stack vertically when compact.
- Fix glyphs/icons that drift outside their circles/wells.
- Fix text/icon placement and preserve intentional card proportions.

A local-only compact-layout patch was most recently proposed. Verify the working tree before assuming it has been applied or visually approved.

### Protected redesign migration boundaries

Do not redesign these while migrating them:

1. Library viewport/card behavior/art-size slider.
2. Game Details standalone-window model.
3. Game Settings standalone-window model.
4. Progress boxes and operation flow.

Done/completion UI is less protected and may be revisited later.

### Next handoff target

Stop inventing placeholder surfaces. The next major architecture step is migration plumbing:

- finish Home compact visual polish;
- transplant/embed the finished classic Library viewport into the approved shell intact;
- preserve standalone Game Details and Game Settings;
- preserve Progress;
- wire Forge / Settings / Recovery only after migration boundaries are stable.

### Local validation

```bash
cd ~/Repos/rtxForge
python3 -m py_compile redesign/gui/rtxforge_redesign_lab.py
python3 redesign/gui/rtxforge_redesign_lab.py --smoke-test
git diff --check -- redesign/gui/rtxforge_redesign_lab.py
python3 redesign/gui/rtxforge_redesign_lab.py
```

Do not commit or push redesign changes unless the user explicitly changes the local-only rule.

<!-- RTXFORGE_CLASSIC_UI_POST_070_START -->
## 2026-09-18 — Classic UI post-0.7 maintenance checkpoint

### Sticky titlebar finalized

- rtxForge identity is anchored to the far-left side of the native titlebar with extra left breathing room.
- Enhancement Mode remains near center but is intentionally biased slightly left to create separation from the bulk action cluster.
- Install All / Remove All / Reset All stay grouped on the right.
- The hamburger is immediately beside the native window controls rather than inside the bulk-action group.
- The compact controls continue mirroring the canonical dashboard state; they are presentation mirrors, not a second configuration source.
- Enhancement-install actions now use `document-save-symbolic` consistently.
- Add Game Folder intentionally retains its add/plus glyph because it is not an enhancement-install action.

### Library sticky transition

- The decorative top-of-Library gradient was removed.
- The persistent hairline/seam was not worth further compositor-specific styling hacks.
- Clean physical bottom spacing now separates the sticky/top controls from Library content.
- Preserve the responsive Library layout and fixed outer visual edges.

### Game Details and Settings

- Game Details is an independent movable `Adw.Window`.
- Settings is an independent movable `Adw.Window`.
- Both initially use the main rtxForge window for compositor placement, then detach after mapping.
- Closing and reopening creates a fresh window placed relative to the main app again.
- Game Details uses its cinematic hero as a drag region.
- Settings uses its existing HeaderBar as a drag region.
- These windows remain resizable.

### Progress / Done

- Progress / Done deliberately stays on the attached `Adw.Dialog` operation path.
- It should remain stationary over the main application.
- Do not convert Progress / Done to the movable utility-window architecture.
- Existing Progress / Done composition and no-scrollbar behavior remain protected.

### Demo / visual smoke

- `--demo` contains enough repeated sample Library entries to guarantee vertical scrolling for sticky-header inspection.
- Repeated demo entries use unique internal paths so card identity does not collide.
- Demo copies may reuse the canonical games/AppIDs so local artwork can still resolve.
- `--demo` is the preferred visual smoke for Library, sticky titlebar, Game Details, and Settings.
- `--live-smoke` remains the dedicated Progress -> Done smoke path.

### Freeze rule

This is approved post-0.7 classic-UI maintenance. The classic UI remains frozen against broad redesign work.
<!-- RTXFORGE_CLASSIC_UI_POST_070_END -->
