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

[Release notes](docs/RELEASE-0.6.2.md) describe the 0.6.2 validation, continuous development publishing and live-smoke improvements. Historical custom MFG builds are not part of the production AppImage path.

DLSS-Unlocked offers separate **NR Only** (pinned NR-v0.8.6; keep in-game FG off) and **MFG Only** (NR-v0.9.1, NR off, bundled NVIDIA runtime updates) pipelines. MFG Only backs up existing native DLLs and restores them on uninstall. Uninstall before changing pipelines. Combined NR + MFG remains available for experimentation.

Selected effects are enabled automatically when installed or repaired. Choose DLSS and the FG multiplier in the game settings; opening the OptiScaler overlay is unnecessary. CLI diagnosis may use `--disable-effects`.

## Interactive live smoke

For hands-on desktop UI validation without touching live game files, run:

    python3 gui/rtxforge_gtk.py --live-smoke

This opens the real write-disabled operation Progress presentation immediately. Click the poster or progress bar to advance through the fake game operations and into the real Done presentation.

Use `--live-smoke` while iterating on progress and Done UI.

For automated regression and screenshot validation, use:

    python3 gui/rtxforge_gtk.py --smoke-test

Neither mode performs live game-file mutations.

<!-- RTXFORGE_CLASSIC_UI_STATUS_START -->
## Classic UI development status

**Current maintenance release: 0.6.4**

The classic GTK/libadwaita interface is now at its final pre-0.7 checkpoint.

### Completed in 0.6.4

- Library artwork sizing now updates live and reliably across Poster and Wide Capsule views.
- The Library has an always-visible live artwork-size slider beside the view controls.
- Poster and Wide Capsule cards use consistent, bounded geometry at every supported size.
- Poster artwork keeps a fixed portrait frame; Wide Capsule uses dedicated capsule artwork and a fixed wide frame.
- Cards in the same view normalize to the height required by the tallest card, keeping Details actions aligned.
- Compact cards may wrap longer titles while shorter titles use the remaining footer space naturally.
- Game-card Details actions use the artwork-derived accent color.
- Settings uses the Enhancement Mode-style segmented selector for Poster / Wide Capsule / List.
- Active Process no longer exposes the generic dialog scrollbar on hover.
- Done no longer exposes the generic dialog scrollbar on hover.
- Game Details titles wrap instead of ellipsizing and reduce their font size for longer names.

The established Progress / Done composition, Game Details redesign, dashboard controls, granular NR / Sharpening controls, and current classic visual direction should be preserved.

### Remaining work before 0.7

The **compact sticky Library / Dashboard header** is the next and only planned classic-UI feature before 0.7.

The sticky state should keep only controls and information that remain useful while scrolling the Library. It should be deliberately compact rather than a miniature copy of the full dashboard.

After that:

1. Ship **0.7**.
2. Treat the classic UI as effectively frozen.
3. Limit future classic-UI work to bug fixes, compatibility, accessibility, maintenance, and specifically approved changes.

Do not restart or broadly redesign the classic UI.
<!-- RTXFORGE_CLASSIC_UI_STATUS_END -->
