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

`public/screenshots.mjs` owns the ordered captures per OS. Windows has five carousel views backed by seven images: Poster View desktop Library, The Witcher 3: Wild Hunt — Remastered desktop Game Details, standalone sidebar Presets, Poster View Game Mode Library, and Cyberpunk 2077 Game Mode Details. Each Library owns an unselected and selected frame under one dot: desktop has six alternating selections, Game Mode has seven staggered selections. Captions show only the view name: Library, Game Details or Presets. OS, interface, dates and technical metadata stay out of the visible caption.

The screenshot area's Desktop / Game Mode tabs filter these views independently of the page's Linux / Windows download selector. Windows Desktop has three dots; Windows Game Mode has two. The selected interface is preserved across OS changes. Linux uses its actual Desktop captures; its Game Mode tab has an explicit pending state until native Linux images are ready. Interface tabs support Left/Right and Home/End and pause rotation on selection.

Each image is held for six seconds with a 420ms crossfade while at least 35% of the stage is visible, on desktop and touch screens. Library fades from unselected to selected without changing its dot or caption, then advances to the next view. Hovering its image previews selected games; leaving fades back to unselected and resumes prior autoplay. Only hovering the image stage suspends rotation, not the heading or caption. Activating the current Library dot again switches selection frames manually. Hidden tabs suspend rotation. Keyboard focus or manual dot selection stops it until the play glyph is activated. Dots support Left/Right and Home/End. Reduced motion disables autoplay by default and removes fading; explicit play remains available. OS changes invalidate outstanding image loads and clear previous-platform images. Automatic rotation does not announce to screen readers; manual changes do.

Captures preserve their proportions inside a shared 16:9 stage. Rounded corners apply to each image's actual bounds, including narrower images, with transparent surrounding space and CSS-only soft shadows. No stretched UI, cursor or hover tooltip appears. All three Game Mode scenes visibly show controller glyphs.

The seven Windows images use the real app's Dark theme on both website themes. Native Light captures are retained privately until its contrast and focus treatments are corrected. Desktop sidebar is collapsed throughout. Desktop client geometry is 2659 × 1782, transported by Nudge as 1440 × 965 PNGs. Fullscreen Game Mode is 3840 × 2160, transported as 1440 × 810. This is capture-tool downsampling, not a claim of unscaled originals. The user opened the intended presets-cards-preview build on LOMACHINE; process identity and capture receipts are retained with original PNGs outside the checkout. The executable's source SHA was not independently established. A virtual Xbox controller navigated the actual app and enabled its real A/B/Y hints; this is UI evidence, not physical-controller or game-rendering acceptance.

WebP derivatives use quality 92 without cropping, recoloring, additional scaling or generated UI. The Presets feature illustration uses a CSS crop that keeps native canvas padding around complete cards: heading, frame generation and the NR/image-tuning cards on desktop, the complete NR card on phones. Game Mode spans the full Play card width and preserves the entire screenshot, including controller hints. Controls remain opaque and readable; no gradient crosses the interface. Presets and Game Mode cards may fall back to Windows on either OS page until matching Linux media exists; alt text and internal provenance retain Windows identity. The Linux main carousel continues to show actual Linux captures.

Initial Linux assets are authentic GTK demo captures from source `3ee326888bc2d636547cc09c122edafd3d989428`, native Actions run [38864399419](https://github.com/lrnolivia/rtxForge/actions/runs/38864399419). Their GUI/capture fixture content matches the website baseline. Game artwork belongs to its respective owners.

Packages and Overlay imagery remain deferred. An eventual overlay capture must show an actual game in progress behind the panel, with no taskbar or cursor. Do not substitute the standalone sidebar, a title screen or a mockup. Future Linux replacements should match Poster View, effective UI size, language and filters; game assignments may vary. Keep original PNGs and provenance for every replacement.
