# rtxForge Beta website

Static Linux/Windows landing page served by the `rtxforge` Cloudflare Worker at https://rtxforge.loew.fi.

Use `npm ci`, `npm run check`, and `npm run deploy` from this directory. Wrangler manages the custom domain, TLS and static assets. There is no server build.

## Installation guide

`public/install.html` serves the richer OS-aware guide at `/install` in production. The landing page and guide share platform requirements and appearance preferences through `platforms.mjs` and `theme.mjs`. Guide downloads return to the selected OS on the landing page, where availability is resolved from real releases. Package-specific and development-only capabilities remain qualified.

## Release channels

`public/releases.mjs` defines the two planned GitHub tags: `beta` for the normal testing release and `development` for the moving development release. The page reads those releases through the public GitHub API and enables only published assets for the selected platform. Until a channel or platform package exists, its download says coming soon and has no destination. API failures are shown separately. Missing-release cache lasts one minute; published-release cache lasts three minutes.

Linux supports Flatpak references, Flatpak bundles and AppImages. Windows selects the x64 installer, with a portable ZIP option when present. ARM64, checksum files, recovery copies and assets outside this repository/tag are excluded. Change tag names in `CHANNELS` when the publisher uses a different convention. Keep release titles plain; put versions and build metadata in the release body.

The legacy `continuous` tag remains for installed Linux updater compatibility and is not used as either new landing-page channel. This page does not create or promote application releases.

## App screenshots

`public/screenshots.mjs` owns the ordered captures per OS. The six-view set is wide desktop Library, desktop Game Details, the standalone sidebar Presets screen, wide Game Mode Library, Game Mode Details and the overlay over actual gameplay. Windows uses The Witcher 3’s updated version for desktop Details, Cyberpunk 2077 for Game Mode Details and Control Resonant for the in-game overlay. Linux may rotate those game assignments. Adding an entry adds a pagination dot and includes it in rotation. Each entry supplies actual width/height, alt text, accessible label, visible platform/interface/view caption and internal provenance. Capture dates and technical metadata are not displayed on the page.

The carousel advances every six seconds with a 420ms crossfade while at least 35% of the image stage is visible. Mouse hover and hidden tabs suspend rotation. Keyboard focus or manual dot selection stops it until the play glyph is activated. Dots support Left/Right and Home/End. Reduced motion disables autoplay by default and removes fading; explicit play remains available. OS changes invalidate outstanding image loads and clear previous-platform images. Automatic rotation does not announce to screen readers; manual changes do.

Captures preserve their own proportions inside a shared 16:9 stage. Rounded corners apply to each image's actual bounds, including narrower images, with transparent surrounding space and CSS-only soft shadows. There is no painted background in a rounded corner and no stretched UI. No cursor or hover tooltip should appear. Every Game Mode capture must visibly show controller glyphs. Overlay images must show a running game in the background, not an idle sidebar or title screen.

Initial Linux assets are authentic GTK demo captures from source `3ee326888bc2d636547cc09c122edafd3d989428`, native Actions run [38864399419](https://github.com/lrnolivia/rtxForge/actions/runs/38864399419). Their original GUI/capture fixture content matches the website baseline. Unreplaced captures with keyboard Game Mode hints are excluded pending a new controller capture. Game artwork belongs to its respective owners.

Windows captures are from the installed app on LOMACHINE on October 20, 2026, obtained through the native Nudge companion with full client visibility and no missing native pixels. Desktop client geometry was 2866 × 1660; Nudge's capture transport produces 2560 × 1483 PNGs. The app's fullscreen Game Mode was 3840 × 2160, captured at 2560 × 1440. This is a documented transport downsample, not a claim of unscaled 1920 × 1080 originals. A neutral virtual Xbox controller selected the app's real controller hints; this is UI capture, not a physical controller or rendering acceptance test. PNG source captures remain in the task artifact directory. WebP derivatives use quality 92 without cropping, recoloring, additional scaling or generated UI.

To replace Linux captures, match the Windows views, wide library layout, language, dark appearance, filters and effective UI size. The featured games are The Witcher 3 (updated version), Cyberpunk 2077 and Control Resonant; Linux can rotate which game appears in each view. Use the same desktop and Game Mode client geometries where available, record actual OS/app scaling and final dimensions, and preserve original PNGs. Native platform differences remain visible. Do not change game files to match status labels. Treat the original 1920 × 1080 capture suggestion as superseded by the measured Windows capture geometry above. Overlay availability must follow the actual platform build; the new sidebar is currently Windows development work.
