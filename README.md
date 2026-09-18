# RTXForge

**GeForce tools, built for Linux.** A native GTK4/libadwaita library manager for Bazzite GNOME, distributed as an AppImage. No Windows client is planned for this release.

## Install and update

The GitHub **continuous** prerelease is the moving development build used for live updates from `main`; it is not a numbered stable release. Download the Bazzite x86_64 AppImage from [Releases](https://github.com/lrnolivia/RTXForge/releases), mark it executable and open it. Choose **Install / update app** in Settings to register it in your launcher. Alternatively:

```sh
APPIMAGE="$(ls -1t RTXForge-*-Bazzite-x86_64.AppImage | head -n1)"
chmod +x "$APPIMAGE"
"$APPIMAGE" --install
```

The persistent copy lives in `~/.local/share/rtxforge/application/RTXForge.AppImage`. After an updater-enabled build is installed, **Check for Updates** in Settings can download and verify a newer continuous AppImage, atomically replace the installed copy, and preserve the previous build. Updating the application does not redeploy games.

Runtime state and recovery data default to `$XDG_STATE_HOME/rtxforge` (normally `~/.local/state/rtxforge`). Existing installations that already contain rtxForge state under `/var/mnt/Games/Ada-Lab/RTXForge` continue using it automatically. Set `RTXFORGE_STATE_ROOT=/absolute/path` to choose another state location.

Package preparation requires `7z` or `7zz` on the host; on Bazzite, Homebrew `sevenzip` is a suitable option.

## Providers and installation

Settings offers **y4my Multipass** and **DLSS-Unlocked**, with complete, separately pinned packages. See [providers/lock.json](providers/lock.json) for exact commits, release URLs and SHA-256 values. Packages are downloaded and verified when preparing an action. Arbitrary repositories and independent provider updates are future work.

Choose **MFG Only**, **NR Only** (DLSS-Unlocked), or **NR + MFG**, select games, and review the floating action panel. Close Steam before applying so its launch settings can be saved safely. Uninstall the current provider before changing providers. Original terminal-edition baselines are reused; older desktop installations retain the legacy Undo path.

Selected effects activate automatically on install or repair. y4my needs a suitable local NR DLL (Settings, an existing game copy, or a locally discovered model); DLSS-Unlocked supplies its own NR package. MFG Only omits NR DLLs; stock upstream builds may still show their NR menu.

The engine leaves game-native DLSS-G in control: OptiScaler replacement input/output are `nofg`, with Ada unlock controlled separately. This corrects RC1.38's supposedly dormant `dlssg` output, which could initialize private Streamline at device creation even with FrameGen disabled. It is a source-level correction, not proof that every reported game crash is resolved.

## Reset settings

**Reset Settings** on a game card (or in its details) restores current sharpening, NR, MFG and menu-font defaults. **Reset All Settings** applies them to managed games across the library, including Bench games. Unmanaged and running games are skipped with a reason. The game keeps its installed provider/profile; no DLLs, saves or Steam launch options are changed. Each changed INI is backed up under that game’s engine state in `settings-resets/`, with its path in the operation report.

The main screen and each game panel expose **NR Strength**, **Sharpening**, and **MFG Multiplier**. NR Strength is adjustable from **0.0–2.0** in 0.1 increments and controls both NR intensity and skin structure. Sharpening is adjustable from **0.0–1.0** in 0.1 increments. Both controls can be dragged or entered numerically, and `0.0` disables the corresponding effect. Existing Off / Light / Medium / Strong desktop settings migrate to equivalent numeric values. Other visual settings retain 75% working scale, one Cinematic pass, local structure/tone 1.00 and auto skin mask. The initial defaults remain NR 2.0 and sharpening 0.5.

MFG offers Off and 2×–6×. The requested ratio is written as `[DLSSG] OverrideInterpolationCount` (0 for Off, otherwise multiplier minus one), preserving native DLSS-G routing. Actual output depends on the game/runtime; FG must be enabled in the game. NR-only installations do not receive MFG changes; MFG-only installations do not receive NR changes.

Changing a main-screen control turns **Reset All Settings** into **Apply Settings**. Applying writes the selected settings to ready managed games and saves them as app defaults; per-game Apply writes only that game's INI. Each game panel reads saved values from its INI, labeling unmatched tuning Custom or Game-controlled. Settings take effect on the next game launch. `UseHQFont=false` remains the upstream Vulkan menu-font workaround; stability is not guaranteed.

**Repair Files** preserves saved tuning. Use **Reset Settings** to replace it with current defaults. **Add Enhancements** and **Remove Enhancements** manage the graphics package, not the game installation.

## Library and reports

Poster, capsule and list views, artwork-led game details, provider buttons, selection and library actions remain available. Each game has notes and **Untested / Working / Problem / Bench** status. Bench excludes a game from bulk install/repair. Start and finish test records manually; the app records installed proxy hashes and copies bounded adjacent diagnostic logs. Support ZIPs stay local until you share them. A test record is not automatic evidence of runtime success.

## Terminal and development

From source, run `./rtxforge` or `./START\ HERE.sh`. In the AppImage, use `--cli`. Both use the RC1.38-derived engine in `engine/rtxengine.py` through the same provider adapter as the GUI.

```sh
APPIMAGE="$(ls -1t RTXForge-*-Bazzite-x86_64.AppImage | head -n1)"
"$APPIMAGE" --cli --help
```

Additional settings: `--nr-strength off|light|medium|strong`, `--sharpening-strength off|light|medium|strong`, `--mfg-multiplier 0|2|3|4|5|6` (0 is Off).

Provider flags: `--runtime-provider y4my|dlss-unlocked`, `--feature-mode mfg-only|nr-only|nr-mfg`, `--disable-effects`.

[Release notes](docs/RELEASE-0.7.0.md) describe the completed classic Library/dashboard UI, validation, and post-0.7 maintenance policy. Historical custom MFG builds are not part of the production AppImage path.

DLSS-Unlocked offers separate **NR Only** (pinned NR-v0.8.6; keep in-game FG off) and **MFG Only** (NR-v0.9.1, NR off, bundled NVIDIA runtime updates) pipelines. MFG Only backs up existing native DLLs and restores them on uninstall. Uninstall before changing pipelines. Combined NR + MFG remains available for experimentation.

Selected effects are enabled automatically when installed or repaired. Choose DLSS and the FG multiplier in the game settings; opening the OptiScaler overlay is unnecessary. CLI diagnosis may use `--disable-effects`.

## Interactive live smoke

For hands-on desktop UI validation without touching live game files, run:

    python3 gui/rtxforge_gtk.py --live-smoke

This opens the real write-disabled operation Progress presentation immediately. Click the poster or progress bar to advance through the fake game operations and into the real Done presentation.

Use `--live-smoke` while iterating on progress and Done UI.

For interactive Library, card-layout, Game Details, Settings, and sticky-titlebar validation, use:

    python3 gui/rtxforge_gtk.py --demo

Demo mode is write-disabled. Its sample Library is intentionally large enough to scroll so the collapsed sticky titlebar can be reviewed without requiring a large real Steam library.

For automated regression and screenshot validation, use:

    python3 gui/rtxforge_gtk.py --smoke-test

Neither mode performs live game-file mutations.

<!-- RTXFORGE_CLASSIC_UI_STATUS_START -->
## Classic UI development status

**Current release: 0.7.0**

The classic GTK/libadwaita interface has reached its planned 0.7 feature-complete state. Post-0.7 work is limited to specifically approved polish, maintenance, compatibility, accessibility, and bug fixes.

### Current production UI

- The full dashboard remains visible at the top of the Library.
- After it scrolls away, the native titlebar becomes the compact persistent dashboard.
- The rtxForge icon/title is anchored at the left with deliberate edge padding.
- Enhancement Mode remains near the middle while leaving breathing room for the bulk actions.
- Install All / Remove All / Reset All remain grouped on the right.
- The application hamburger sits directly beside the native window controls.
- Install actions use the save glyph consistently across the dashboard, sticky header, and selected-game action bar.
- The Library toolbar retains Search, filters, selection controls, live artwork sizing, and Poster / Wide Capsule / List controls.
- The Classic Poster and Wide Capsule galleries now use the frozen responsive-grid behavior: a 16px outer Library inset, an explicit 8px GTK FlowBox column gap, and card/template widths derived from the usable viewport width. Card geometry absorbs responsive width changes rather than manufacturing large dynamic child margins.
- Poster and Wide Capsule retain separate artwork sources. Demo mode may read already-cached local Steam artwork so Wide Capsule behavior can be reviewed without substituting poster images.
- The decorative Library-top gradient was removed in favor of clean physical spacing.
- Game Details and Settings open as independent, movable windows. Freshly reopened windows are placed relative to the main application again.
- Progress / Done intentionally remains the stationary in-app operation presentation rather than becoming a movable utility window.

The established responsive Library layout, card sizing, artwork handling, wrapped titles, artwork-derived accents, granular NR / Sharpening controls, native NVIDIA routing, recovery behavior, and current visual direction should be preserved.

The current Poster / Wide Capsule resize-and-padding behavior is now a frozen Classic UI invariant and a migration target for the redesign. A known follow-up remains: at certain viewport widths and artwork-size selections, the chosen column count can leave a conspicuous unused region at the right edge. Future work may intelligently adjust the effective artwork size around the user's selected size to eliminate that remainder, but must preserve the frozen 16px outer inset, explicit 8px inter-card gap, responsive aspect-ratio behavior, and separate Poster / Wide Capsule artwork paths.

### Classic UI policy after 0.7

Do not restart or broadly redesign the classic interface.

Future classic changes should remain narrowly scoped to approved fixes and maintenance while the separate redesign work develops independently.
<!-- RTXFORGE_CLASSIC_UI_STATUS_END -->

<!-- RTXFORGE_REDESIGN_STATUS_START -->
## Libadwaita redesign status

The next-generation Libadwaita redesign is under active development in `redesign/`.

GitHub `main` is the shared source of truth for approved redesign checkpoints. The redesign
beta workflow is manual-only; normal source pushes do not automatically publish beta builds.

Current status:

- approved/locked application shell;
- Forge presentation shell built;
- Settings presentation shell built and visually approved;
- Recovery presentation shell built and visually approved;
- Home follows the exact approved cinematic dashboard mockup and is in responsive visual
  polish;
- the finished classic Library viewport/card behavior/artwork-size slider, standalone
  Game Details/Game Settings windows, and Progress presentation are migration preservation
  targets.

See [Redesign Current Status](docs/redesign/CURRENT-STATUS.md) and
[Fresh Chat Continuation](docs/redesign/FRESH-CHAT-CONTINUATION.md).
<!-- RTXFORGE_REDESIGN_STATUS_END -->
