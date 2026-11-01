# Game Mode prototype

A shared Tauri 2 shell for Windows and Linux, using the approved overlay glass materials. This is an isolated prototype; the existing native applications remain the production interfaces.

Library opens game tiles directly. Details uses a full-width desktop-style hero header with the poster beside the title, followed by the section navigation and translucent control workspace. Accent Tint affects that Details window only. Clear, Light and Dark remain independent choices.

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

### Windows portable preview

Extract the preview ZIP and open `rtxforge-game-mode.exe`. Operations are disabled by default. To install a separate Start menu entry, run the included `Install-Preview.ps1` from the extracted folder. Each version gets its own directory under `%LOCALAPPDATA%/Programs/rtxForge Game Mode Preview`; the existing Desktop application is not replaced. Earlier preview versions remain available for rollback.

From source, `Build-Portable.ps1` builds and bundles the Windows preview. The package includes dependency license texts and a `build.json` receipt identifying its source revision. Linux packaging, signing and updater integration remain qualification work.

Native prerequisites are documented by [Tauri](https://v2.tauri.app/start/prerequisites/): Rust, WebView2 and MSVC on Windows; the documented WebKitGTK and development packages on Linux. The native file picker uses the [Tauri dialog plugin](https://v2.tauri.app/plugin/dialog/).

## Reviewed operations

The default development preview keeps operations disabled. To connect the existing engine, start a separate run with `RTXFORGE_ENGINE_BRIDGE=1` or `Run.ps1 -Engine` (combine with `-Native` if desired).

This connects real methods. Confirming an install, restore, settings change, tool import or Steam shortcut review performs the corresponding existing engine operation. Library discovery and opening a review never fabricate an installed or active state.

The Windows adapter imports the existing host methods without calling its `main()`, which would start an automatic installed-overlay refresh. The Linux adapter binds the existing `DesktopService` configuration without its startup refresh. File planning, verification, ownership, backups, process checks and writes remain in the existing services. Exact review tokens stay in one long-lived host; confirmation sends that exact token once. Progress is forwarded from the host, and cancellation is requested at its safe boundaries.

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

The Windows Desktop Game Details page also uses the approved poster/title/information-card layout. Its information card uses light accent-hued ink on a moderately dark surface, or dark accent-hued ink on a light surface in Light mode. Hero titles adapt to sampled artwork without Screen blending. The existing native page continues to own navigation, operations and hero collapse.
