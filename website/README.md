# rtxForge Beta website

Static Linux/Windows landing page served by the `rtxforge` Cloudflare Worker at https://rtxforge.loew.fi.

Use `npm ci`, `npm run check`, and `npm run deploy` from this directory. Wrangler manages the custom domain, TLS and static assets. There is no server build.

## Release channels

`public/releases.mjs` defines the two planned GitHub tags: `beta` for the normal testing release and `development` for the moving development release. The page reads those releases through the public GitHub API and enables only published assets for the selected platform. Until a channel or platform package exists, its download says coming soon and has no destination. API failures are shown separately. Missing-release cache lasts one minute; published-release cache lasts three minutes.

Linux supports Flatpak references, Flatpak bundles and AppImages. Windows selects the x64 installer, with a portable ZIP option when present. ARM64, checksum files, recovery copies and assets outside this repository/tag are excluded. Change tag names in `CHANNELS` when the publisher uses a different convention. Keep release titles plain; put versions and build metadata in the release body.

The legacy `continuous` tag remains for installed Linux updater compatibility and is not used as either new landing-page channel. This page does not create or promote application releases.

## App screenshots

`public/screenshots.mjs` owns the four captures per OS: `desktop-library`, `desktop-details`, `game-mode-library`, and `game-mode-details`. Each entry supplies its actual width, height, alt text, visible detail and provenance. Empty entries show a pending state; failed images show an error rather than a broken image or another OS's screenshot. The shared OS selector preserves the chosen interface and view. Images use `object-fit: contain`; no screenshot is stretched or cropped by the page.

The initial Linux images are authentic GTK demo captures from the October 16 native review of source `3ee326888bc2d636547cc09c122edafd3d989428`, Actions run [38864399419](https://github.com/lrnolivia/rtxForge/actions/runs/38864399419), artifact `rtxforge-native-package-review`. Its `gui/`, screenshot fixture and capture script content match the initial website baseline. The four originals are `completion-night.png`, `completion-tools.png`, `gm-library-posters-1920x1080.png`, and `gm-details-overview-1920x1080.png`; WebP encoding preserves their complete native content and original proportions. These are demo UI previews, not evidence of rendering results or game compatibility. Game artwork belongs to its respective owners. Windows captures are pending.

Replacement captures should use Control Resonant on both OSes, with the app's complete client surface at exactly **1920 × 1080 pixels**, dark appearance, English UI and effective 100% scaling. Include the app's own title/header/navigation controls, exclude external window shadows, OS desktop and taskbar. Desktop and Game Mode should both use this same canvas. Details should show Overview at the top, with identical artwork and focus targets. Keep each OS's real feature and installation status visible. Do not modify game files to align labels. Save unscaled PNG originals, verify their dimensions and include build/OS/scale metadata. If those dimensions or Control Resonant are unavailable, report that before substituting a game or scaling an image. Replace manifest entries and alt/provenance text when the native pairs arrive; the website needs no layout change.
