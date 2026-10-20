# Code signing policy

SignPath signing has not been set up for rtxForge. The optional signing steps in
`.github/workflows/windows-build.yml` are preparation for a future setup; they do not
establish that a signing service or certificate is active.

Check the signing status stated with each Windows package on the
[Releases](https://github.com/lrnolivia/rtxForge/releases) page. A release must not be
described as signed without verification of its downloaded installer and application
files. The repository does not currently claim SignPath-signed release builds.

## Team roles

- Committers and reviewers: [repository members](https://github.com/lrnolivia/rtxForge/graphs/contributors)
- Release maintainer: [@lrnolivia](https://github.com/lrnolivia) (loew.fi)

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
