# One Beta release for two operating systems

Windows and Linux publish into the same GitHub release, tagged `beta`, from separate workflows. Each one can publish without changing or blocking the other.

## Publishing

Both are manual `workflow_dispatch` runs on `main`, with the exact reviewed commit:

- Windows: `windows-build.yml` with `publish_beta` and `expected_sha`.
- Linux: `linux-build.yml` with `publish_beta` and `expected_sha`. `publish_preview` (the continuous channel) cannot be used in the same run.

A run stops before building if it is not on `main` or `expected_sha` is not the commit being built. It checks again before uploading, in case `main` moved during the build. `VERSION` must be `1.0.0-beta.N`. N must be higher than the version that OS currently has in the release.

## What each OS owns

| OS | Current assets |
|---|---|
| Windows | `rtxForge-Setup-<version>-x64.exe`, `-arm64.exe`, `rtxForge-windows-<version>-x64.zip`, each with `.sha256` (6 files) |
| Linux | `rtxForge-<version>-x86_64.AppImage` and `rtxForge-<version>-x86_64.flatpak`, each with `.sha256`, and `rtxforge-beta-linux.json` (5 files) |

`packaging/beta_release.py` holds these rules. Each publish only counts, replaces and verifies its own OS's assets, and then checks that the other OS's assets are unchanged. When a build is replaced, its files stay in the release as `<name>.previous-<sha12>`, where `<sha12>` is the first 12 characters of that OS's previous source commit. The website and the updaters ignore `.previous-` assets.

The Linux publish waits for both the AppImage and the Flatpak builds of the same commit. A release published before the Flatpak (3 Linux files) is replaced the same way; its AppImage files are kept as rollback copies.

`rtxforge-beta-linux.json` uses the same schema as the continuous channel's `rtxforge-update.json` (`channel`, `version`, `commit`, `appimage`, `sha256`, `size`), with `channel: beta`, so the Linux updater can follow it.

## Tag and notes

- The `beta` tag and the release target point at whichever OS published last. They do not identify either OS's build.
- Each OS's build is identified by its own line at the end of the release notes, for example ``Windows: version `1.0.0-beta.2` · source `<sha>` · [Build](...)``. A publish rewrites only its own line and keeps the other OS's line. The rest of the notes is regenerated from `docs/releases/1.0-beta.md` at the commit being published.
- Releases published before this policy carry the old single line, ``Version: `…` · Source: `…` ``. It is read as the Windows line.
- Both publish jobs use the `rtxforge-beta-release` concurrency group, so they never write to the release at the same time.

## Continuous channel

The `continuous` release and `rtxForge-Bazzite-x86_64.AppImage` are unchanged. They still publish only through `publish_preview`.
