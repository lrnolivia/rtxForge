# Bazzite / RTX 4070 setup

This package installs the existing rtxForge application and prepares its pinned
graphics runtime. It targets Bazzite GNOME on x86_64 with an NVIDIA RTX 40-series
GPU and a working NVIDIA driver. It uses host Python, GTK4 and libadwaita with
`Adw.ToggleGroup`. Run it as your normal desktop user, without sudo.

## Install

Extract the downloaded `.tar.gz`, open a terminal in the extracted directory,
then run:

```sh
/usr/bin/python3 install.py
```

Setup verifies the included AppImage, checks the host and free space, verifies
the selected provider download and payload, and installs the application in
your launcher. The setup entry point works without a FUSE mount.

A new installation selects **DLSS-Unlocked / MFG Only**, 2× requested MFG,
NR strength 2.0 and sharpening 0.5. Existing app preferences remain unchanged.
To explicitly choose a DLSS-Unlocked profile, use one of:

```sh
/usr/bin/python3 install.py install --profile mfg-only
/usr/bin/python3 install.py install --profile nr-only
/usr/bin/python3 install.py install --profile nr-mfg
```

An explicit profile choice saves a backup of existing preferences first.
It changes the app's selection, not any game's installed provider or settings.
For a game already managed by rtxForge, use **Restore Original Files** before
changing that game's provider or profile.

| Profile | Pinned package | Behavior |
| --- | --- | --- |
| MFG Only | DLSS-Unlocked NR-v0.9.33 | Native game DLSS-G with Ada unlock; NR components omitted |
| NR Only | DLSS-Unlocked NR-v0.9.33 | NR available; keep in-game FG off |
| NR + MFG | DLSS-Unlocked NR-v0.9.33 | Experimental combination; verify one game before expanding |

The source archives are approximately 469 MB (one verified archive shared by all three profiles). Setup
downloads only the selected package and verifies its pinned SHA-256. The
included `providers-lock.json` records the exact upstream URLs and hashes.
The application reuses its verified cache. DLSS-Unlocked ZIP preparation needs
no separate 7-Zip installation. Choosing y4my preserves its separate model and
extraction requirements.

## First game

1. Open rtxForge from the launcher and select one compatible game.
2. Close Steam before applying changes to its launch settings.
3. Review **Install Features** and apply. Original files and recovery records
   stay under rtxForge's existing state locations.
4. Launch through your selected Proton version. Enable DLSS and frame generation
   in the game for MFG. Actual output depends on the game and runtime.
5. DLSS-Unlocked NR starts **off**. F10 toggles NR on supported installations.
   NR-only testing should keep in-game frame generation off.

Setup never writes game files, Steam launch options, Proton configuration,
system packages, drivers, display settings, saves or firmware. Those game-level
operations remain the app's explicit review/apply workflow. Native DLSS file
updates remain enabled by default in rtxForge Settings and use its existing
backup and restore system.

## Check and recover

Read-only host check:

```sh
/usr/bin/python3 install.py check --json
```

Prepare another runtime without installing or changing preferences:

```sh
/usr/bin/python3 install.py prepare --profile nr-only
```

Restore the previous application build (game files/settings are unaffected):

```sh
/usr/bin/python3 install.py rollback
```

The installed application is
`~/.local/share/rtxforge/application/RTXForge.AppImage` (or your `XDG_DATA_HOME`).
The previous build is retained beside it. Preferences and runtime cache use
the existing rtxForge state root, including the legacy Games-drive location
when present. Setup writes its receipt to `setup/last-setup.json` there.

Checksums establish package integrity. Host checks and fixture tests do not
establish actual NVIDIA/game compatibility. This package does not claim to
solve Desktop Mode 4K/HDR, VRR or game-specific crashes. Those require testing
the exact build on your PC. Use the working Gamescope/Proton configuration as
the starting point and record results one game at a time.
