# rtxForge for Windows

Native WinUI 3 desktop shell for rtxForge. It mirrors the Linux desktop build
screen for screen; see [DESIGN-MAP.md](DESIGN-MAP.md) for the control and
token map.

## Download Beta 1

[rtxForge Beta 1](https://github.com/lrnolivia/rtxForge/releases/tag/beta) is published for Windows and Linux. Windows packages currently use build version `1.0.0-beta.9`: choose the x64 or ARM64 setup `.exe`, or extract the x64 portable ZIP and run `rtxForge.exe`. The installer and portable app include their runtimes. SHA-256 files accompany the downloads; `.previous-` files are recovery copies.

Use the [Windows installation guide](https://loew.fi/rtxforge/install?os=windows) for setup and the release notes for known testing limits. The instructions below are for building from source.

Status: runs the shared rtxForge engine. `engine-host/rtxforge_win_host.py`
hosts `scripts/desktop_service.py` (and through it `engine/rtxengine.py`)
unchanged, adding Windows adapters: state under `%LOCALAPPDATA%\rtxForge`, the
writer lock, Steam discovery from the registry, GPU detection, artwork from
your Steam grid, `.7z` extraction with Windows' bundled `tar.exe`, and no
Proton launch options (Windows loads OptiScaler's proxy DLL natively, so
Steam's configuration is never written). Every write is reviewed first and
executed from that exact review, as on Linux.

Pass `--preview` (or run without Python) for the sample library with no
game writes.

## Application updates

Installed copies check after startup and every six hours, download verified updates in the background, and apply them quietly when you close rtxForge. Close games first, or choose **Restart to update** to apply immediately and return to the same interface. Settings → App and updates and Game Mode → About share the **Automatic updates** opt-out. A failed check retries in 30 minutes; manual checks remain available. Setup failures are shown on the next check; diagnostics are in `%LOCALAPPDATA%\rtxForge\updates\setup.log`.

Portable and development copies never run Setup automatically. Portable users extract the newest ZIP; settings and original-file backups remain in the user profile. Builds predating Beta 9 require one manual update to gain this behavior.

## Requirements

- Windows 10 version 2004 (19041) or later, x64 or ARM64
- .NET 10 SDK to build
- Python 3.11+ for dev builds only. `dotnet publish` bundles a private Python
  (python.org embeddable package, pinned by SHA-256) and the engine files via
  `build/Bundle-Engine.ps1`, so people who use the app install nothing.

The app is unpackaged and bundles the Windows App SDK runtime, so no separate
runtime install is needed.

## Build and run

```powershell
dotnet build windows/RtxForge.Windows/RtxForge.Windows.csproj -c Debug -r win-x64 -p:Platform=x64
windows/RtxForge.Windows/bin/x64/Debug/net10.0-windows10.0.22621.0/win-x64/rtxForge.exe
```

## Installer

```powershell
powershell -ExecutionPolicy Bypass -File windows/build/Build-Installer.ps1 -RuntimeIdentifier win-x64
```

Publishes the self-contained app (engine and Python included) and compiles
`installer/rtxForge.iss` with a pinned, portable Inno Setup into
`windows/out/rtxForge-Setup-<VERSION>-<arch>.exe` plus a `.sha256`. Setup
installs per user without an admin prompt (all users is offered), adds Start
menu shortcuts (optional desktop and Game Mode shortcuts), and upgrades in
place. Uninstall keeps `%LOCALAPPDATA%\rtxForge`, so original-file backups
survive a reinstall.

### Code signing

SignPath signing has not been set up for this project. Check each release's signing
status; the presence of optional signing steps in CI does not mean a package is signed.
See [CODE_SIGNING.md](../CODE_SIGNING.md).

The workflow can request signing during a manual **draft_release** run once the service
is configured. Other CI runs remain unsigned. The following is future setup guidance.

Setup, once SignPath accepts the project:

1. In SignPath, link the predefined **GitHub.com** trusted build system to the
   project, and install the SignPath GitHub App on this repository.
2. Create two artifact configurations:
   - `windows-app`:
     ```xml
     <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
       <zip-file>
         <pe-file path="rtxForge.exe"><authenticode-sign /></pe-file>
         <pe-file path="rtxForge.dll"><authenticode-sign /></pe-file>
       </zip-file>
     </artifact-configuration>
     ```
   - `windows-installer`:
     ```xml
     <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
       <zip-file>
         <pe-file path="rtxForge-Setup-*.exe"><authenticode-sign /></pe-file>
       </zip-file>
     </artifact-configuration>
     ```
3. In GitHub (Settings › Secrets and variables › Actions), add the secret
   `SIGNPATH_API_TOKEN` (a CI user's token with submitter rights) and the
   variable `SIGNPATH_ORGANIZATION_ID`. Optional variables:
   `SIGNPATH_PROJECT_SLUG` (default `rtxForge`) and `SIGNPATH_POLICY_SLUG`
   (default `release-signing`).

Until `SIGNPATH_ORGANIZATION_ID` exists, builds are unsigned and SmartScreen
asks users to confirm. The uninstaller Inno Setup embeds in the setup .exe is
not signed separately.

## CI

CI builds x64 and ARM64 on every change under `windows/` or the shared
engine, smoke-tests the bundled engine, builds both installers, installs and
uninstalls the x64 one, and uploads them as artifacts
(`.github/workflows/windows-build.yml`). Running the workflow by hand with
**draft_release** attaches the installers to a draft `windows-v<VERSION>`
release; nothing is public until a maintainer publishes the draft.

## Layout

| Path | Purpose |
| --- | --- |
| `RtxForge.Windows/App.xaml` | Fluent resources and the GeForce accent ramp |
| `RtxForge.Windows/Themes/Tokens.xaml` | rtxForge brand and status colors, hero typography |
| `RtxForge.Windows/Themes/Controls.xaml` | Fluent-based styles, named after the libadwaita classes they replace |
| `RtxForge.Windows/MainWindow.xaml` | Mica shell: title bar, NavigationView, operation and toast InfoBars |
| `RtxForge.Windows/Views/LibraryPage.xaml` | Dashboard, Features, Presets, library |
| `RtxForge.Windows/Views/GamePage.xaml` | Game page (navigated, with back) |
| `RtxForge.Windows/Views/SettingsPage.xaml` | Settings page |
| `RtxForge.Windows/Views/ActivityPage.xaml` | Activity log |
| `RtxForge.Windows/Controls/` | Settings cards and the NR/Sharpening/MFG pods |
| `RtxForge.Windows/Services/` | Engine service (Python host), preview service, theme |
| `engine-host/` | Windows host for the shared Python engine (JSON lines over stdio) |
| `build/` | Engine/Python bundling and the installer build script |
| `installer/rtxForge.iss` | Inno Setup script for the setup .exe |

Fonts, the brand mark and `VERSION` are linked from the repository so both
shells share one copy.
