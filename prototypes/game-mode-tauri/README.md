# rtxForge Game Mode

The Game Mode application for Windows and Linux, using the approved overlay glass materials and shared rtxForge engine. The browser demo uses the same interface with game-file operations disabled. Native platform and game-operation qualification are tracked explicitly in [FEATURE_PARITY.md](FEATURE_PARITY.md).

Library opens game tiles directly. Details uses a full-width desktop-style hero header with the poster beside the title, followed by the section navigation and translucent control workspace. Accent Tint affects that Details window only. Clear, Light and Dark remain independent choices.

Native Game Mode opens fullscreen. F11 or the More options menu switches to a borderless window; the empty header area can be dragged in windowed mode. Library item size is independent of text and display scaling, and its size control moves into a popover on narrow windows.

Game Details loads one Steam Store screenshot using the game's known Steam ID. Appearance lets you choose that screenshot. The chosen image can warm after pausing on a Library tile for a quarter second; the whole library is never prefetched. Initial images and selection changes fade in after decoding unless reduced motion is enabled. There is no automatic rotation. At most six compressed images are retained in memory. The loader tries the original of the Store's sized screenshot, prefers verified 3840×2160 imagery, and keeps a bounded 128 MiB disk cache under the application settings directory's `state/game-mode/store-backgrounds` folder. Cached images remain available offline. Lower-resolution originals receive a slight blur and grain. Games without a usable Store image retain the app background.

When there is no saved screenshot choice, up to eight small thumbnails are compared with the game's Desktop accent palette. Palette results are cached, two thumbnails are sampled at a time, and only the winning full-size image loads. An explicit screenshot choice always takes precedence.

Posters, capsules, hero artwork and saved per-game accents follow Desktop Mode's shared library records and rtxForge settings. An explicit rtxForge accent wins; otherwise the original poster supplies the automatic color. Old browser-only accent previews do not override Desktop settings. Native accent edits use the shared preference review flow.

Hero framing honors Desktop Mode's saved focal point, then uses its visual-saliency calculation when no override exists. Where the WebView exposes on-device face detection, it also checks the saliency result against faces. Select the Appearance preview to adjust directly with the D-pad, left stick or arrow keys; Select/Enter keeps the draft and Back/Escape cancels the adjustment. Compact sliders remain available. Native edits use the shared preference review flow. Windows Desktop's separate native face detector is not yet integrated into this WebView application.

Unknown Store screenshots are screened locally by a bundled CPU detector on Windows and Linux. Text-heavy panels and edge HUD labels are excluded from both defaults and the picker. Decisions are cached by image hash; curated corrections supplement the detector. Failed screening does not admit unknown images. Icon-only HUDs can still escape detection, and environmental signs can be false positives. See [SCREENSHOT_SCREENING.md](SCREENSHOT_SCREENING.md) for limits and dependency provenance.

## Run

Use Node 22.12+ and Python 3.11+. Install JavaScript dependencies once:

```sh
npm ci
npm run dev
```

The browser preview is [http://127.0.0.1:1420](http://127.0.0.1:1420). It reads local manifests, settings, cached artwork and provider records. It contains no demonstration library or simulated runtime telemetry.

On Windows, `Run.ps1` also recognizes the project-local Rust toolchain when present:

```powershell
$env:RTXFORGE_PYTHON = 'C:/path/to/python.exe'
pwsh -NoProfile -File ./Run.ps1
# Native window, when you choose to open it:
pwsh -NoProfile -File ./Run.ps1 -Native
# Compile without opening a window:
pwsh -NoProfile -File ./Run.ps1 -Build
```

Set `RTXFORGE_NODE` if Node is not on the process PATH. Development builds use the checkout. The Windows portable preview includes a private Python runtime, the reader and engine files; it can run from another folder without a checkout or system Python. WebView2 is still required.

### Native packages

Extract the complete Windows ZIP and open `rtxforge-game-mode.exe`. Reviewed operations are enabled in the installed application. `RTXFORGE_PREVIEW_READ_ONLY=1` overrides enablement and prevents the operation host from starting. The browser development server remains read-only unless explicitly enabled.

Run `Install.ps1` to create a separate Start menu entry under `%LOCALAPPDATA%/Programs/rtxForge Game Mode`. Installation verifies every payload file, tests the installed host from its own directory, then updates the shortcut. Previous versions and the Desktop application are preserved. Linux tarballs contain a private Python and the same offline screening worker; run `./python/bin/python3 -B install_linux.py` for a per-user installation. Linux requires WebKitGTK 4.1.

Build the offline worker in an isolated Python 3.14 environment with `screening-requirements.txt` and `build_screening.py --output <scratch>`. On Windows, use `Build-Portable.ps1 -ScreeningPath <worker-folder> -OutputPath <package-folder>`. Linux and Windows complete payloads are also built by the Game Mode native workflow. `build.json` records source, native input digest and hashes for the complete package. Release builds refuse missing private engine/Python files instead of silently falling back to a development checkout.

Native prerequisites are documented by [Tauri](https://v2.tauri.app/start/prerequisites/): Rust, WebView2 and MSVC on Windows; the documented WebKitGTK and development packages on Linux. The native file picker uses the [Tauri dialog plugin](https://v2.tauri.app/plugin/dialog/).

## Reviewed operations

The default development preview keeps operations disabled. To connect the existing engine, start a separate run with `RTXFORGE_ENGINE_BRIDGE=1` or `Run.ps1 -Engine` (combine with `-Native` if desired).

This connects real methods. Confirming an install, restore, settings change, tool import or Steam shortcut review performs the corresponding existing engine operation. Library discovery and opening a review never fabricate an installed or active state.

The Windows adapter imports the existing host methods without calling its `main()`, which would start an automatic installed-overlay refresh. The Linux adapter binds the existing `DesktopService` configuration without its startup refresh. File planning, verification, ownership, backups, process checks and writes remain in the existing services. Exact review tokens stay in one long-lived host; confirmation sends that exact token once. Native close, exit and Desktop handoff close its input, request cancellation at existing safe boundaries, drain in-flight work and reap the process before leaving. New queued requests are refused during shutdown. Progress is forwarded from the host, and cancellation is requested at its safe boundaries.

No existing game installs, Steam state or shared preferences were changed during development verification. Engine workflow checks use explicit contract fixtures. The read-only native preview was opened for visual review. File pickers and real mutation flows were not exercised.

## Controls

- D-pad / left stick: spatial focus. A: select. B: back. LB / RB: sections.
- Left / right adjusts a focused select with a controller.
- Tab / arrow keys: move. Enter: select. Escape: back. `[` / `]`: sections.
- System reduced motion takes priority. The Motion option can also disable transitions.

The Gamepad API requires the window to receive a controller interaction. Polling stops while the window is hidden or unfocused. Hardware controller acceptance remains separate from the synthetic standard-mapping checks.

## Checks

```sh
npm run build
npm run check
python -B -m unittest discover -s tests -p test_reader.py
# With the local preview running and Microsoft Edge installed:
npm run check:ui
npm run check:contracts
npm run check:appearance
npm run check:presets
```

Set `RTXFORGE_BROWSER=chrome` to use an installed Chrome channel for headless checks. Screenshots are written under `.impeccable/review/` and are intentionally ignored by Git because they contain local library artwork.

See [FEATURE_PARITY.md](FEATURE_PARITY.md) for exact implemented scope, evidence and remaining work. Compilation is not game runtime acceptance or approval to replace the existing native shell.

The Library fills the available workspace. Poster and capsule results use available height and width to fit complete rows in a scrollable pane, with reserved shadow padding. At a 2560×1440 CSS viewport (3840×2160 at 150%), the poster layout shows two complete rows. All games remain reachable by scrolling or controller focus. Search and resize recalculate the layout.

Per-game color previews apply consistently to Details and Library selection in all three layouts and are remembered locally by this shell. Saved desktop accents remain the source when a local preview is absent. Automatic accents sample the original saved poster before display thumbnail conversion. Idle game names remain neutral.
