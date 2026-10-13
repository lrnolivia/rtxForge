# Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by
[SignPath Foundation](https://signpath.org).

Signed files are the Windows release builds of rtxForge published on this repository's
[Releases](https://github.com/lrnolivia/rtxForge/releases) page: the setup program
(`rtxForge-Setup-<version>-<arch>.exe`) and the application files it installs
(`rtxForge.exe`, `rtxForge.dll`). They are built from this repository by GitHub Actions
(`.github/workflows/windows-build.yml`); nothing built elsewhere is signed. Each release
is signed only after a maintainer approves its signing request.

## Team roles

- Committers and reviewers: [repository members](https://github.com/lrnolivia/rtxForge/graphs/contributors)
- Approvers: [@lrnolivia](https://github.com/lrnolivia) (loew.fi)

## Privacy policy

rtxForge does not collect, store or send personal information, and has no telemetry or
analytics. It connects to other systems only for the features below:

- **Game information and artwork** (Settings › Library › Download game information /
  Download missing artwork, on by default, can be turned off): game names and Steam app
  IDs are sent to the Steam store (`store.steampowered.com`, `steamstatic.com`) to fetch
  descriptions, release dates and images.
- **SteamGridDB** (only if you connect an account): game names are sent to
  `steamgriddb.com` with your own API key to browse artwork.
- **Packages and DLSS files** (when you install features or update DLSS): provider
  packages and DLSS files are downloaded from their published GitHub releases. No data
  about you or your games is sent.

Settings, notes, logs and support reports stay on your computer. Support reports are only
shared if you choose to share them yourself.
