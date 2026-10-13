<picture>
  <source media="(prefers-color-scheme: dark)" srcset="packaging/steam-artwork/exports/rtxforge-logo-white.png">
  <img src="packaging/steam-artwork/exports/rtxforge-logo-dark.png" alt="rtxForge — new tricks for old cards" width="640">
</picture>

# rtxForge

rtxForge gives you one place to try multi-frame generation (MFG), explore experimental neural rendering (NR), and update the DLSS files in the games you already play. Pick a game, review what will change, and apply it when you're ready. Tune it later, or use the restore tools when you want to go back.

**Built natively for Linux and Windows**, with the same familiar desktop layout on both. Linux uses GTK4/libadwaita; Windows uses WinUI 3 with Fluent colors, platform fonts and glyphs. The logo stays the same. New Game Mode is intended for both platforms and is not yet released.

## Start here

Choose **Installer** for guided setup, or **Portable** to download and launch without installing the app. Both are intended release options for Linux and Windows.

| Option | How you use it |
| --- | --- |
| **Installer** | Let the installer guide you through setup, then open rtxForge from your application menu. |
| **Portable** | Keep it in a folder you choose. Download, extract if needed, and open the app there. Keep any companion files together. |

**For now:** Linux has an AppImage prerelease. Windows has unsigned x64 installer and portable previews from an open development branch; it has not been merged or published as a Windows release. [Releases](https://github.com/lrnolivia/rtxForge/releases) lists the published packages.

### Try the current previews

- **Linux:** download the AppImage from the [continuous prerelease](https://github.com/lrnolivia/rtxForge/releases/tag/continuous). In its file properties, allow execution, then open it. No extraction or app installation is needed. The continuous channel is a moving prerelease.
- **Windows x64:** open the [successful preview build](https://github.com/lrnolivia/rtxForge/actions/runs/38455800917). For guided setup, download **rtxForge-Setup-windows-x64**, extract it, and open the setup `.exe`; a SHA-256 checksum file is included. For Portable, download **rtxForge-windows-x64**, extract the entire ZIP, and open `rtxForge.exe`. These previews are **unsigned**. GitHub requires sign-in, and these downloads expire on October 27, 2026. See [preview status](https://github.com/lrnolivia/rtxForge/pull/17) for newer builds.

Portable skips app installation, but it can still save preferences, runtime downloads and recovery records outside its folder. On Linux, you'll need the dependencies listed below. The Windows preview includes its runtimes; no development SDK is needed.

## Your first game

Start with one game and see how it feels before changing your whole library. **The steps below currently work in the Linux build.** The Windows x64 preview now connects to the shared engine for real library scans and reviewed operations. Its bundled engine and installer passed basic automated checks, but a real-game feature installation has not yet been verified. For sample games without game writes, launch rtxForge with `--preview`.

1. **Find a game** in the Library. Search, filter, or add a game folder in Settings.
2. **Choose what to try:** MFG Only, NR Only, or NR + MFG, along with your provider. NR Only requires DLSS-Unlocked; NR + MFG is experimental.
3. **Close the game and Steam.** Choose **Install Features**, review the proposed changes, and apply. Packages are verified before installation and originals are backed up.
4. **Launch and check.** Enable DLSS and frame generation in the game for MFG. Actual output depends on the game and runtime. NR remains experimental and is not confirmed by a saved setting or diagnostic log. DLSS-Unlocked NR starts off; F10 toggles it where supported.
5. **Tune or recover.** Per-game **Apply** saves presets for the next launch. **Repair Feature Files** replaces damaged files while keeping tuning. **Restore Original Files** removes installed features; use it before changing provider or feature profile.

| Setting | Choices |
| --- | --- |
| NR Strength | 0.0–2.0; 0 disables NR |
| Sharpening | 0.0–1.0; 0 disables sharpening |
| MFG Multiplier | In game, Off, or requested 2×–6× |

Library **Apply Settings** updates eligible managed games and saves defaults. **Reset Presets** resets tuning. **DLSS Files** updates older known native DLSS files and offers separate restore controls; [read its backup and recovery guidance](docs/DLSS-FILES.md).

On Linux, **Settings → Gaming Mode** chooses Desktop or Big Picture UI and offers **Add to Steam**. Bundled app artwork needs no SteamGridDB key; browsing community game artwork uses your own key.

## A few things to know

- **Linux:** x86_64, working NVIDIA driver, host Python 3, GTK4, libadwaita 1.7+ and PyGObject. The Bazzite-named AppImage checks capabilities, not the distribution name. SDL2 provides controller input when available.
- **Windows preview:** x64; its declared minimum is Windows 10 version 2004.
- **For installing features**, the current target is an RTX 40-series card and compatible x64 games. RTX 20/30/50 and Steam Deck GPU support haven't been validated. HDR, VRR and controller behavior in Gamescope need testing on your setup.
- Keep space for runtime downloads and game backups. Linux setup/runtime preparation requires at least 4 GiB free at the state location. y4my needs an archive extractor and, for NR, a suitable local model.
- Close your game before changing its files. rtxForge stops when it detects anti-cheat or conflicting files; keep graphics mods out of protected online games. A game update or another mod can change files after your review. If that happens, keep your backups and check the conflict before trying again.
- **Tools** accepts extracted x64 ReShade DLLs for DirectX 10–12 and `.addon64` add-ons. Add-ons need a matching ReShade loader; occupied files are refused. Get ReShade from [its official site](https://reshade.me/). Custom ZIP instructions are inspected, never executed; checksums do not establish safety or game compatibility.

## Stay up to date, with a way back

On Linux, choose **Settings → System → Check for Updates**. Downloads are verified and the previous app build is retained. Updating the app does not reinstall features into games. Windows preview updates currently mean downloading a newer installer or extracting a newer portable build.

If you want to undo a change, use **Restore Original Files** for game features or the **DLSS Files** restore controls for native DLL updates. Hold on to recovery records and game backups until you're finished with them, including when using Portable.

## If something gets stuck

| Problem | What to check |
| --- | --- |
| App will not open | Linux: check executable permission, host Python/GTK dependencies and any FUSE error. Windows: extract all preview files before launching. |
| Games are missing | Open Steam once, refresh the Library and check game folders in Settings. |
| Installation or restore is refused | Close the game and Steam; review the reported conflict instead of overwriting changed files. |
| MFG or NR has no effect | Check the feature profile and in-game DLSS/FG settings. Use **Game Details → Tools → Diagnose NR**; log activity alone does not prove a visible effect. |
| Need to report a problem | Open **Settings → Recovery → Library Reports → Preview Support Report**, inspect the export, then share it. |

[Ask for help or report a bug](https://github.com/lrnolivia/rtxForge/issues). Include your platform, app build, GPU/driver, game and provider/profile, plus what you tried and what happened. Support reports stay on your computer until you share them. Check logs and notes before posting—automatic redaction can miss private information.

## Third-party notices

Runtime packages retain their upstream terms. Bundled font notices are preserved for [Bakbak One](gui/fonts/OFL-BakbakOne.txt) and [Inter](packaging/steam-artwork/source/OFL-Inter.txt).

## License and code signing

rtxForge is released under the [MIT License](LICENSE). Free code signing for the
Windows builds is provided by [SignPath.io](https://about.signpath.io), certificate by
[SignPath Foundation](https://signpath.org); see the [code signing policy](CODE_SIGNING.md).
