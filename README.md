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

For focused responsive-Library regression and screenshot validation, use:

    python3 gui/rtxforge_gtk.py --resize-smoke

This captures Poster and Wide Capsule at normal, maximized, and restored window
sizes while asserting their fixed 7 / 6 slot counts and reversible card sizing.

For the broader automated regression and screenshot validation, use:

    python3 gui/rtxforge_gtk.py --smoke-test

Neither mode performs live game-file mutations.

<!-- RTXFORGE_CLASSIC_UI_STATUS_START -->
## Classic UI development status

**Current release: 0.7.0 plus approved post-release maintenance on `main`.**

The classic GTK/libadwaita application remains the production UI. Broad
redesign work belongs under `redesign/`; classic changes should remain explicit
production fixes and maintenance.

### Current production Library

Poster and Wide Capsule now use a deterministic responsive-scale layout rather
than variable column fitting or a user artwork-size control.

Current gallery contract:

- **Poster is always exactly 7 visual slots per row**;
- **Wide Capsule is always exactly 6 visual slots per row**;
- cards grow and shrink automatically with the current Library viewport;
- changing window size, maximizing, restoring, and shrinking all update card
  geometry live without requiring a view switch;
- gallery content no longer ratchets the application into a larger minimum
  window width;
- incomplete final rows are padded with inert ghost slots so the visual grid
  keeps its full geometry;
- Poster and Wide Capsule continue using their separate artwork sources and
  aspect ratios;
- the right edge includes an explicit paint/clip safety allowance so the final
  slot remains inside the visible viewport;
- GTK overlay scrolling remains enabled without a permanent scrollbar gutter.

The live resize path uses the horizontal ScrolledWindow adjustment `page_size`
as its viewport authority. The Library ScrolledWindow uses the `EXTERNAL`
horizontal policy so dynamically enlarged child requests do not become a new
application-window minimum.

Gallery title behavior is responsive:

- the existing full-size title is the maximum;
- compact cards step the title from **15px → 14px → 13px → 12px**;
- titles wrap to at most **3 lines**;
- ellipsis is used only after the third line is exhausted;
- Details buttons become modestly smaller with compact cards;
- the existing tallest-card normalization keeps sibling card heights aligned.

Additional Library polish:

- All / Installed / Available have expanded horizontal padding;
- NR Strength and Sharpening numeric fields have additional internal left
  padding;
- manual artwork-size controls were removed from both the Library toolbar and
  Settings.

List view remains structured as:

`Game | Location | Status | Enhancements | Actions`

with existing selection, provider state, install/repair actions, Game Details,
write safety, and classic visual styling preserved.

### Validation

The responsive gallery has a dedicated write-disabled resize smoke that captures
six states:

- Poster normal / maximized / restored;
- Wide Capsule normal / maximized / restored.

The accepted resize run verified that card widths grow and return to their
original values while slot counts remain fixed at 7 / 6. Final visual polish was
also reviewed in write-disabled `--demo` mode.

### Classic UI policy after 0.7

Do not restart or broadly redesign the classic interface.

Do not touch `redesign/` while performing classic Library work unless the user
explicitly requests it.
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
- the finished classic Library viewport/card behavior/automatic artwork scaling, standalone
  Game Details/Game Settings windows, and Progress presentation are migration preservation
  targets.

See [Redesign Current Status](docs/redesign/CURRENT-STATUS.md) and
[Fresh Chat Continuation](docs/redesign/FRESH-CHAT-CONTINUATION.md).
<!-- RTXFORGE_REDESIGN_STATUS_END -->
