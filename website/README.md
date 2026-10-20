# rtxForge Beta website

Static Linux/Windows landing page served by the `rtxforge` Cloudflare Worker at https://rtxforge.loew.fi.

Use `npm ci`, `npm run check`, and `npm run deploy` from this directory. Wrangler manages the custom domain, TLS and static assets. There is no server build.

## Release channels

`public/releases.mjs` defines the two planned GitHub tags: `beta` for the normal testing release and `development` for the moving development release. The page reads those releases through the public GitHub API and enables only published assets for the selected platform. Until a channel or platform package exists, its download says coming soon and has no destination. API failures are shown separately. Missing-release cache lasts one minute; published-release cache lasts three minutes.

Linux supports Flatpak references, Flatpak bundles and AppImages. Windows selects the x64 installer, with a portable ZIP option when present. ARM64, checksum files, recovery copies and assets outside this repository/tag are excluded. Change tag names in `CHANNELS` when the publisher uses a different convention. Keep release titles plain; put versions and build metadata in the release body.

The legacy `continuous` tag remains for installed Linux updater compatibility and is not used as either new landing-page channel. This page does not create or promote application releases.
