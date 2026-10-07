# RTXForge

**GeForce tools, built for Linux.** A native GTK4/libadwaita library manager for Bazzite GNOME, distributed as an AppImage. No Windows client is planned for this release.

## Install and update

For the complete Bazzite / RTX 4070 setup package, see
[Installation](docs/INSTALLATION.md). Its verified installer prepares the
selected runtime, preserves existing preferences and never modifies games.
Fresh package installations select DLSS-Unlocked / MFG Only.

The GitHub **continuous** prerelease is the moving development build used for live updates from `main`; it is not a numbered stable release. Download the Bazzite x86_64 AppImage from [Releases](https://github.com/lrnolivia/RTXForge/releases), mark it executable and open it. Choose **Install / update app** in Settings to register it in your launcher. Alternatively:

```sh
APPIMAGE="$(ls -1t RTXForge-*-Bazzite-x86_64.AppImage | head -n1)"
chmod +x "$APPIMAGE"
"$APPIMAGE" --install
```

The persistent copy lives in `~/.local/share/rtxforge/application/RTXForge.AppImage`. After an updater-enabled build is installed, **Check for Updates** in Settings can download and verify a newer continuous AppImage, atomically replace the installed copy, and preserve the previous build. Updating the application does not redeploy games.

Runtime state and recovery data default to `$XDG_STATE_HOME/rtxforge` (normally `~/.local/state/rtxforge`). Existing installations that already contain rtxForge state under `/var/mnt/Games/Ada-Lab/RTXForge` continue using it automatically. Set `RTXFORGE_STATE_ROOT=/absolute/path` to choose another state location.

DLSS-Unlocked ZIP preparation uses Python and needs no separate extractor.
y4my extraction uses system libarchive, with `7z` / `7zz` / `bsdtar` fallbacks.

## Input, tools and diagnostics

Add rtxForge to Steam uses the app’s bundled poster, wide capsule, hero, transparent logo and shortcut icon. It needs no SteamGridDB key. Before applying images, the GTK app reviews the Steam profile and identifies existing custom artwork that would be replaced. Changes since review stop the update; backups retain replaced images. Calls without a reviewed plan keep differing custom images. This is separate from the per-game artwork picker and its SteamGridDB connection.

Settings → Library → Input offers Automatic, Desktop and Couch startup modes, plus automatic or explicit Xbox, PlayStation, Nintendo and generic controller labels. Restart after changing the startup mode to rebuild every control. SDL2 (including sdl2-compat) provides mapped gamepad input when available: D-pad/stick moves focus, the south button activates, east goes back, north opens Library (or cycles its views), Start opens the menu and bumpers switch Dashboard / Library / Presets / DLSS Files. Presets adjusts the selected game. DLSS Files offers Update all or a Library selection flow for chosen games, with confirmation before updates. Library offers Install to all, Restore and Update DLSS as independent actions through the shared review flow. Unsupported games are excluded from those bulk actions. Settings is a controller-reachable gear at the top right; package selection is available from the controller menu. Move up from the first Library row to its view controls, then up again to page navigation. Input is handled only while an rtxForge window is active. Steam Input can present a virtual Xbox pad; it is not a universal XInput/DInput API. Keyboard and mouse remain usable when no mapped controller or SDL library is available.

Light and Dark use native Adwaita surface colors; Night is the deeper custom palette. Resizing and page transitions follow the system reduced-motion preference. Couch mode opens on Library, with shown, total and configured counts. Branding expands at the top and collapses while scrolling. Dashboard remains available in navigation. Library has poster, wide-capsule and list layouts, with directional grid navigation, automatic focus scrolling and retained selection when changing views or returning from a game. It shares Classic's artwork, aspect ratios, layout preference, artwork-derived accents and saved custom color choices; focused controls and selections carry that same game accent, with contrast-aware text. Controller input activates this interface; keyboard or mouse use returns to Classic controls. Protected operation reviews and progress stay inside the application surface. Game launch diagnostics are saved under the rtxForge state root at `desktop/launch-logs/requests.jsonl`, with one previous log retained. They distinguish launcher resolution, URI submission and failures; submission does not prove a game started.

Game Details → Tools and the library-wide Extras menu manage extracted x64 ReShade DLLs and `.addon64` add-ons, including RenoDX. Choose a local file, inspect its hash and destination, then explicitly trust it. ReShade is installed as `dxgi.dll` for DirectX 10–12; an occupied proxy is refused. A matching ReShade loader must exist before an add-on is installed. Proton may require `dxgi=n,b` added to the game's existing DLL overrides; the app does not overwrite launch options for this action. Each tool has a separate, hash-guarded Restore action. Shader packs, presets, Vulkan-layer installation and Windows setup executables are not imported by this adapter. Get ReShade from [its official site](https://reshade.me/).

**Diagnose NR** reads saved settings, adjacent runtime hashes, and a bounded OptiScaler log. It distinguishes model creation, NR GPU timing, warnings and logs older than the current INI. Generic NGX callbacks for SR/RR do not count as NR execution. GPU timing alone does not establish the visible result. The current deployment adapters remain targeted at RTX 40; RTX 20/30/50 are clearly marked unvalidated rather than inheriting a false compatibility claim.

Games without a Steam ID can receive information through a unique exact title match. This metadata identity never changes the game's launcher ID. Local artwork takes priority and does not prevent game information from loading; both downloads can be disabled independently.

## Providers and installation

Settings offers **y4my Multipass** and **DLSS-Unlocked**, with complete, separately pinned packages. See [providers/lock.json](providers/lock.json) for exact commits, release URLs and SHA-256 values. Packages are downloaded and verified when preparing an action. The Packages menu also links alternative community projects with their compatibility limits. A custom ZIP is inspected without executing its scripts; recognized DLSS-Unlocked layouts can be reviewed, parameterized and trusted by exact hash. Edited instructions are saved as review notes and never executed. Other layouts remain inspection-only.

Choose **MFG Only**, **NR Only** (DLSS-Unlocked), or **NR + MFG**, select games, and review the floating action panel. Close Steam before applying so its launch settings can be saved safely. Uninstall the current provider before changing providers. Original terminal-edition baselines are reused; older desktop installations retain the legacy Undo path.

MFG activates on install or repair when selected. NR strength 0 disables NR. Explicit install presets and per-game Apply set its saved state; repair preserves existing tuning. DLSS-Unlocked binds its runtime NR toggle to F10; delivery depends on the game's active input/overlay handler and is not established by a saved binding. A selected NR package alone does not prove the effect is enabled or working. y4my needs a suitable local NR DLL (Settings, an existing game copy, or a locally discovered model); DLSS-Unlocked supplies its own NR package. MFG Only omits NR DLLs; stock upstream builds may still show their NR menu.

The engine leaves game-native DLSS-G in control: OptiScaler replacement input/output are `nofg`, with Ada unlock controlled separately. This corrects RC1.38's supposedly dormant `dlssg` output, which could initialize private Streamline at device creation even with FrameGen disabled. It is a source-level correction, not proof that every reported game crash is resolved.

## Reset settings

**Reset Settings** on a game card (or in its details) restores current sharpening, NR, MFG and menu-font defaults. **Reset All Settings** applies them to managed games across the library, including Bench games. Unmanaged and running games are skipped with a reason. The game keeps its installed provider/profile; no DLLs, saves or Steam launch options are changed. Each changed INI is backed up under that game’s engine state in `settings-resets/`, with its path in the operation report.

The main screen and each game panel expose **NR Strength**, **Sharpening**, and **MFG Multiplier**. NR Strength is adjustable from **0.0–2.0** in 0.1 increments and controls both NR intensity and skin structure. Sharpening is adjustable from **0.0–1.0** in 0.1 increments. Both controls can be dragged or entered numerically, and `0.0` disables the corresponding effect. Existing Off / Light / Medium / Strong desktop settings migrate to equivalent numeric values. Other visual settings retain 75% working scale, one Cinematic pass, local structure/tone 1.00 and auto skin mask. The initial defaults remain NR 2.0 and sharpening 0.5.

MFG offers Off and 2×–6×. The requested ratio is written as `[DLSSG] OverrideInterpolationCount` (0 for Off, otherwise multiplier minus one), preserving native DLSS-G routing. Actual output depends on the game/runtime; FG must be enabled in the game. NR-only installations do not receive MFG changes; MFG-only installations do not receive NR changes.

Changing a main-screen control turns **Reset All Settings** into **Apply Settings**. Applying writes the selected settings to ready managed games and saves them as app defaults; per-game Apply writes only that game's INI. Each game panel reads saved values from its INI, labeling unmatched tuning Custom or Game-controlled. Settings take effect on the next game launch. `UseHQFont=false` remains the upstream Vulkan menu-font workaround; stability is not guaranteed.

**Repair Feature Files** in Game Details restores missing or damaged feature files while preserving presets. **Reset Presets** lives beside the preset controls and applies your library defaults. **Install Features** and **Restore Original Files** manage the graphics additions to a game.

Presets start collapsed. Installation offers an optional preset adjustment before continuing. Native **DLSS Files** runs automatically during feature installation, with per-game update/restore controls in Game Details and a default-on switch in Settings. See [DLSS Files](docs/DLSS-FILES.md) for supported files and backup behavior.

## Library and reports

Poster, capsule and list views, artwork-led game details, provider buttons, selection and library actions remain available. Each game has notes and **Untested / Working / Problem / Bench** status. Bench excludes a game from bulk install/repair. Start and finish test records manually; the app records installed proxy hashes and copies bounded adjacent diagnostic logs. Support ZIPs stay local until you share them. Logs and notes are opt-in; the app redacts common secrets and local paths, shows the exact export text, and saves only that approved preview. Review it before sharing because automatic redaction cannot identify every private value. A test record is not automatic evidence of runtime success.

## Terminal and development

From source, run `./rtxforge` or `./START\ HERE.sh`. In the AppImage, use `--cli`. Both use the RC1.38-derived engine in `engine/rtxengine.py` through the same provider adapter as the GUI.

```sh
APPIMAGE="$(ls -1t RTXForge-*-Bazzite-x86_64.AppImage | head -n1)"
"$APPIMAGE" --cli --help
```

Additional settings: `--nr-strength off|light|medium|strong`, `--sharpening-strength off|light|medium|strong`, `--mfg-multiplier 0|2|3|4|5|6` (0 is Off).

Provider flags: `--runtime-provider y4my|dlss-unlocked`, `--feature-mode mfg-only|nr-only|nr-mfg`, `--disable-effects`.

[Release notes](docs/RELEASE-0.7.0.md) describe the completed classic Library/dashboard UI, validation, and post-0.7 maintenance policy. Historical custom MFG builds are not part of the production AppImage path.

DLSS-Unlocked uses the complete verified **NR-v0.9.33** package for **NR Only**, **MFG Only**, and **NR + MFG**. MFG Only omits NR components; NR Only keeps the Ada unlock off. The native game controls frame generation by default (**In game** multiplier); explicit Off and 2×–6× overrides remain available. Managed files are backed up for restoration; game-native DLLs remain in place by default. Uninstall before changing pipelines. Combined NR + MFG remains available for experimentation.

Choose DLSS and the FG multiplier in the game settings; opening the OptiScaler overlay is unnecessary. DLSS-Unlocked NR starts off and F10 toggles it independently. CLI diagnosis may use `--disable-effects`.

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
sizes while asserting adaptive 3–9 column counts, equal side insets, and reversible sizing.

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

The **Card size** icon opens a Games per row selector with preferences from 3 to 9,
including even values. The gallery reduces columns when cards would become too
small and adds columns in very wide windows. Automatic changes favor odd counts.
Poster and Wide Capsule fill the viewport between equal 16px side insets, with
live resizing and equal sibling heights. Pills stay directly above Details.
Incomplete rows retain inert placeholders to keep the grid aligned.

List view uses resizable columns:

`Game | Location | Status | Features | Actions`

Game has a minimum width and single-line titles. Fixed thumbnail and row geometry
keeps scrolling stable. File repair is available in Game Details → Features;
preset reset is beside the preset controls. The top actions target selected games
when a selection exists. Select all and Clear are visible buttons above the grid.

Presets start collapsed with a short first-launch cue. The collapsed row is compact;
expanded content uses consistent 16px spacing. Game Details has a taller hero and
an accent swatch with Edit. Progress and the compact Done dialog share left-aligned
content; Done has a solid neutral background. Neutral grays and NVIDIA green replace
system accent colors while intentional game-artwork accents remain available.

### Validation

Write-disabled GTK checks cover normal/maximized/restored gallery allocations,
760px windows, List scrolling and column resizing, Game Details navigation,
preset controls, Settings, Progress and Done. Native DLSS lifecycle tests use
disposable game fixtures, including automatic older-version selection and recovery.

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


## Shared package and interface preview

The `rtxforge/shared-package-ui-20261002` review branch retains Classic and adds
an opt-in New navigation layout around the **same GTK Library widget**. The
application menu switches layouts; New Home offers an Open to Library/Home
preference. Classic remains the default. Compact Header is opt-in and retains
search, selection and action controls.

Packages uses the existing pinned DLSS-Unlocked/y4my catalog and hardware gate.
Custom ZIP inspection is static: archive paths, links, duplicate names, size,
configuration and instructions are checked without running archive code. A
recognized DLSS-Unlocked layout can be explicitly trusted and pinned to its hash;
its deployment uses the existing preview, ownership, backup and recovery engine.
Unknown layouts stay inspection-only. Instructions are reference text, never
shell commands. NR rendering and custom-package game compatibility are not
inferred from successful parsing.

The Qt/Kirigami frontend under `gui/qt/` uses the same toolkit-free service and
package parser. It is a native port under parity review, not a separate engine
or a stable replacement. Source preview: `python3 gui/qt/app.py --demo`.
GTK preview: `python3 gui/rtxforge_gtk.py --demo --ui-mode new`.

GTK can run under GNOME, Plasma or Hyprland with its native dependencies; the Qt
frontend targets Plasma and can be reused on Hyprland. Distribution names do not
select different engines. Setup now checks actual Linux, toolkit, storage, Steam
and GPU capabilities rather than requiring Bazzite by name. The bundled runtime
still requires its supported NVIDIA RTX 40-series hardware. This does not claim
Steam Deck GPU support, NR rendering, HDR, or Gamescope/controller parity.


One review AppImage carries both frontend sources. The existing GTK frontend
remains the default; `--frontend qt` explicitly starts the Kirigami preview when
PySide6/Kirigami are installed. `--frontend-doctor` reports available Python
bindings and session information without changing system settings. Toolkit
dependencies are not silently installed and no desktop environment is replaced.
