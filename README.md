<picture>
  <source media="(prefers-color-scheme: dark)" srcset="packaging/steam-artwork/exports/rtxforge-logo-white.png">
  <img src="packaging/steam-artwork/exports/rtxforge-logo-dark.png" alt="rtxForge — new tricks for old cards" width="640">
</picture>

# rtxForge

Deploy neural rendering across compatible games, bring multi-frame generation to RTX 20, 30 and 40 series, and keep DLSS files up to date. Native apps for Linux and Windows, with reviewed changes and original-file backups.

**[Website & downloads](https://rtxforge.loew.fi/) · [Installation guide](https://rtxforge.loew.fi/install) · [Report a bug](https://github.com/lrnolivia/rtxForge/issues)**

## Download

| Channel | What to expect |
| --- | --- |
| **Beta** | The regular public testing release. Start here. |
| **Development** | A moving release with the latest changes and unfinished features. |

[Choose Linux or Windows on the website](https://rtxforge.loew.fi/#downloads) to see the packages available for each channel. Linux uses AppImage, or Flatpak when a release provides it. Windows offers an installer and a portable ZIP when published.

The new channels use the `beta` and `development` release tags. They are being set up; the site shows **coming soon** until a channel has a package for your OS. The older `continuous` prerelease remains for existing Linux updater compatibility. Release channels are separate from source-code branches.

### Download directly from GitHub

1. Open **[Releases](https://github.com/lrnolivia/rtxForge/releases)** on this repository.
2. Choose **rtxForge Beta** (`beta`) or **rtxForge Development** (`development`) when published.
3. Expand **Assets** and download the package for your OS: Linux `.AppImage` or a provided Flatpak; Windows setup `.exe`, setup ZIP or portable Windows ZIP.
4. Run the installer, or extract the entire portable ZIP and open `rtxForge.exe`. For Linux setup, follow the [installation guide](https://rtxforge.loew.fi/install?os=linux).

The automatic **Source code (zip)** and **Source code (tar.gz)** links contain the source, not the ready-to-run app. Checksum files are for verifying a download.

## Your first game

1. **Find your game.** Rescan the Library or add its folder. Start with one compatible title.
2. **Choose your packages.** Select a supported provider and NR Only, MFG Only or NR + MFG.
3. **Tune presets.** Set library defaults in Presets, then adjust individual games as needed.
4. **Install.** Close the game, choose **Install Features**, review the changes and apply. Follow any Steam or compatibility instructions in the review.
5. **Play.** Enable the in-game DLSS and frame-generation options required by your package. Check the result before expanding to more games.

Need to undo it? **Restore Original Files** uses your feature-install backups. **DLSS Files** has separate restore controls for native DLL updates. Keep your recovery records and backups.

The [full installation guide](https://rtxforge.loew.fi/install) covers app setup, packages, presets, installation, updates, recovery and troubleshooting for both OSes.

## Compatibility

- NR is experimental and requires a compatible RTX card, game and provider. MFG supports RTX 20, 30 and 40 series on compatible routes; a requested multiplier is not a guaranteed net FPS gain.
- Package support differs between Linux and Windows. The Windows overlay and one-click dual-boot adaptation are in development.
- Close games before changing their files. Avoid protected online games and anti-cheat; review conflicts rather than overwriting unknown files.

## Help

[Read troubleshooting](https://rtxforge.loew.fi/install#help) or [open an issue](https://github.com/lrnolivia/rtxForge/issues/new). Include your OS, app build, GPU/driver, game, provider and what happened.

For a support report, open **Settings → Recovery → Library Reports → Preview Support Report** in the app. Review the export before sharing it; reports stay local until you attach them.

## Development

See [Development](docs/DEVELOPMENT.md) for the shared engine, checks and contribution workflow, [Windows](windows/README.md) for native build instructions, and [DLSS Files](docs/DLSS-FILES.md) for its backup and restore behavior. Provider-specific requirements belong with the selected package and its release notes.

## License and notices

rtxForge is released under the [MIT License](LICENSE). Runtime packages retain their upstream terms. Font notices are preserved for [Bakbak One](gui/fonts/OFL-BakbakOne.txt) and [Inter](packaging/steam-artwork/source/OFL-Inter.txt).

See [code signing status](CODE_SIGNING.md) for Windows packages.
