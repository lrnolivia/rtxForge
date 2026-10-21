# rtxForge Beta website

Static Linux/Windows landing page served by the `rtxforge` Cloudflare Worker at https://rtxforge.loew.fi.

Use `npm ci`, `npm run check`, and `npm run deploy` from this directory. Wrangler manages the custom domain, TLS and static assets. There is no server build.

## Installation guide

`public/install.html` serves the richer OS-aware guide at `/install` in production. The landing page and guide share platform requirements and appearance preferences through `platforms.mjs` and `theme.mjs`. Guide downloads return to the selected OS on the landing page, where availability is resolved from real releases. Package-specific and development-only capabilities remain qualified.

## Release channels

`public/releases.mjs` defines the two planned GitHub tags: `beta` for the normal testing release and `development` for the moving development release. The page reads those releases through the public GitHub API and enables only published assets for the selected platform. Until a channel or platform package exists, its download says coming soon and has no destination. API failures are shown separately. Missing-release cache lasts one minute; published-release cache lasts three minutes.

The download card announces Public Beta for Friday, October 23, 2026. Its date badge disappears when a published Beta package is available for the selected OS; reaching the date alone never enables a download or claims release availability.

Linux supports Flatpak references, Flatpak bundles and AppImages. Windows selects the x64 installer, with a portable ZIP option when present. ARM64, checksum files, recovery copies and assets outside this repository/tag are excluded. Change tag names in `CHANNELS` when the publisher uses a different convention. Keep release titles plain; put versions and build metadata in the release body.

The legacy `continuous` tag remains for installed Linux updater compatibility and is not used as either new landing-page channel. This page does not create or promote application releases.

## App screenshots

`public/screenshots.mjs` owns the captures per OS and their theme variants. Windows is the initial landing-page platform for new visits; explicit `?os=linux` / `?os=windows` links and saved visitor choices take precedence. The appearance toggle swaps both the page and Windows screenshots, preserving the current view and installation step. Linux keeps its authentic existing images until matching replacements are captured.

Windows Desktop has three carousel items: Library, The Witcher 3: Wild Hunt — Remastered Game Details, and the inZOI install sequence. Desktop uses the expanded sidebar. Standalone Desktop Presets remains a feature illustration. Game Mode has Library, Dragon Age: The Veilguard Game Details on the DLSS Files tab, Presets, and the Avatar: Frontiers of Pandora install sequence. Each Library pairs unselected and six selected games under one dot. Captions contain only Library, Game Details, Presets, or Install.

The Desktop / Game Mode tabs operate independently of the OS selector. Linux Game Mode has an explicit pending state. Interface tabs and dots support Left/Right and Home/End, and manual selection pauses rotation. Each frame remains visible for six seconds with a 420ms crossfade. Library advances through its paired states; Install advances through Review, Installing, and Done before moving to the next item. Activating the current dot again advances its internal frames. Hover previews selected Library games and pauses rotation; leaving restores the base Library frame and prior autoplay state. Hidden pages suspend rotation, and reduced motion disables initial autoplay and fades. Theme/OS switches invalidate outstanding image loads. Automatic rotation is silent to screen readers; manual changes are announced.

The October 21 Windows images show the actual native private sample app, using the user's trimmed library and copied custom artwork from their live library. Install operations in that sample are simulated; the screenshots do not measure real install speed. The user's supplied Desktop images are 2989 × 1785. Game Mode runs at 3840 × 2160 and Nudge transported 2560 × 1440 captures with actual Xbox controller glyphs visible. New Desktop install captures were transported as 2560 × 1441. Capture receipts preserve the executable identity; its exact compiled source was not independently established. UI screenshots do not establish physical-controller, rendering, overlay, or real installation acceptance.

Original PNGs remain private. The user approved pixel-only removal of the Sample badge from supplied Desktop captures, with every pixel outside its small badge rectangle verified unchanged. No generated UI or recoloring is used. Install derivatives crop to complete native panels, with transparent rounded corners and CSS shadows; full originals retain the app context. Public full-screen derivatives trim only the measured two-pixel capture border: the Desktop perimeter and Game Mode top edge. WebP derivatives use quality 92 without additional scaling. Images preserve their proportions inside the shared stage. Desktop and fullscreen Game Mode captures use subtle corner radii that scale from native capture pixels rather than a fixed website radius.

The Presets feature uses a CSS crop with native padding around the heading and complete cards on desktop, and the full neural-rendering card on phones. Game Mode's Play illustration preserves the full screenshot and controller footer. Feature images may fall back to Windows on either OS page pending Linux replacements; alt text and internal provenance retain their Windows identity. Controls remain opaque, and no gradient crosses the UI.

Initial Linux assets are authentic GTK demo captures from source `3ee326888bc2d636547cc09c122edafd3d989428`, native Actions run [38864399419](https://github.com/lrnolivia/rtxForge/actions/runs/38864399419). Their GUI/capture fixture content matches the website baseline. Game artwork belongs to its respective owners.

Packages and Overlay imagery remain deferred. An eventual overlay capture must show an actual game in progress behind the panel, with no taskbar or cursor. Do not substitute the standalone sidebar, a title screen or a mockup. Future Linux replacements should match Poster View, effective UI size, language and filters; game assignments may vary. Keep original PNGs and provenance for every replacement.
