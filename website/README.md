# rtxForge Beta website

Static Linux/Windows landing page served by the `rtxforge` Cloudflare Worker at https://rtxforge.loew.fi.

Use `npm ci`, `npm run check`, and `npm run deploy` from this directory. Wrangler manages the custom domain, TLS and static assets. There is no server build.

## Installation guide

`public/install.html` serves the richer OS-aware guide at `/install` in production. The landing page and guide share platform requirements and appearance preferences through `platforms.mjs` and `theme.mjs`. Guide downloads return to the selected OS on the landing page, where availability is resolved from real releases. Package-specific and development-only capabilities remain qualified.

## Release channels

`public/releases.mjs` defines the two planned GitHub tags: `beta` for the normal testing release and `development` for the moving development release. The page reads those releases through the public GitHub API and enables only published assets for the selected platform. Until a channel or platform package exists, its download says coming soon and has no destination. API failures are shown separately. Missing-release cache lasts one minute; published-release cache lasts three minutes.

The download card announces Public Beta for Tuesday, October 27, 2026. Its date badge disappears when a published Beta package is available for the selected OS; reaching the date alone never enables a download or claims release availability.

Linux supports Flatpak references, Flatpak bundles and AppImages. Windows selects the x64 installer, with a portable ZIP option when present. ARM64, checksum files, recovery copies and assets outside this repository/tag are excluded. Change tag names in `CHANNELS` when the publisher uses a different convention. Keep release titles plain; put versions and build metadata in the release body.

The legacy `continuous` tag remains for installed Linux updater compatibility and is not used as either new landing-page channel. This page does not create or promote application releases.

## App screenshots

`public/screenshots.mjs` owns the captures per OS and their theme variants. Windows is the initial platform; explicit OS links and saved visitor choices take precedence. The appearance toggle swaps page and native captures together.

The hero presents the selected Desktop Library, with a bottom-only CSS fade, top corners scaled from native capture radii, and a soft drop shadow. Presets illustrates tuning. The Install card presents tightly and equally cropped Review, Installing, and Done images side by side (stacked on phones), with rounded bounds and labels over bottom gradients. The three frames retain the same native app/game background; crops are presentation CSS and full-size links retain the complete originals.

Game Mode uses the Linux five-option navigation set (Library, Presets, Packages, Extras, Settings) for both OS selections, as explicitly requested. Its native Linux provenance remains intact. The feature crossfades selected Library, Dragon Age: The Veilguard DLSS Files, and Presets every eight seconds, with a 1.6 second fade that keeps the outgoing frame opaque underneath. No visible state labels or controls are shown; reduced motion disables autoplay and transitions. Offscreen, hidden-page, hover and keyboard-focus states suspend rotation. Theme switches preserve the current state and invalidate stale image loads. Failed next-frame loads retain the last decoded image.

Desktop Library, Presets and install images follow the selected OS; the Windows gameplay overlay appears under both OS choices with its Windows provenance retained. Supporting images link to their full-size originals. Missing static images hide their media slot.

The October 21 Windows images show the actual native private sample app, using the user's trimmed library and copied custom artwork from their live library. Install operations in that sample are simulated; the screenshots do not measure real install speed. The user's supplied Desktop images are 2989 × 1785. Game Mode runs at 3840 × 2160 and Nudge transported 2560 × 1440 captures with actual Xbox controller glyphs visible. New Desktop install captures were transported as 2560 × 1441. Capture receipts preserve the executable identity; its exact compiled source was not independently established. UI screenshots do not establish physical-controller, rendering, overlay, or real installation acceptance.

Original PNGs remain private. The user approved pixel-only removal of the Sample badge from Desktop captures, with every pixel outside its small badge rectangle verified unchanged before border trimming and encoding. No generated UI or recoloring is used. Full-size installation images retain the full native app and game context; the cards use tighter CSS crops. The Install feature card shows all three inZOI stages together. Public full-screen derivatives trim only the measured two-pixel capture border: the Desktop perimeter and Game Mode top edge. WebP derivatives use quality 92 without additional scaling. Images preserve their native proportions. Desktop and fullscreen Game Mode captures use subtle corner radii that scale from native capture pixels rather than a fixed website radius.

The Presets feature uses a CSS crop with native padding around the heading and complete cards on desktop, and the full neural-rendering card on phones. Game Mode's Play illustration preserves the full Details screenshot and controller footer. Linux Presets uses its own measured crop (`data-os=linux`). The Overlay is the explicit exception to OS-specific imagery. The Overlay feature card shows the actual Control Resonant gameplay capture, unchanged, on both website themes; there is no synthetic Light overlay. The capture remains work in progress and does not establish fixes for its Reset-label or HUD-bleed defects. The hero fades at the bottom and install labels use a bottom gradient; source images retain their captured appearance.

The user identified an HDR capture color issue in the existing Windows media and chose to finish the layout before recapturing. Originals are already 8-bit sRGB or contain no HDR color/luminance metadata. Their current color appearance is retained temporarily; faithful SDR replacements require a later HDR-off capture pass.

The October 23 Linux images are native GTK4/libadwaita renders of `gui/rtxforge_gtk.py` from the Linux RC branch (`28a468b`), in write-disabled demo mode with the same private sample library and artwork as Windows (46 visible games after the sample's own removals). A capture-only driver outside the repository loads the sample in place of the demo games and simulates the install review/progress/done stages; it never reaches the engine and no game files are touched. Each frame is rendered by GTK's own renderer from the window's render nodes inside an isolated headless GNOME (mutter) session at monitor scale 2, drawn at 1.5× for 2985 × 1780 Desktop (1990 × 1187 logical window, expanded sidebar) and 2560 × 1438 fullscreen Game Mode (1707 × 959 logical) with Xbox controller glyphs; there is no cursor, tooltip or notification. Desktop keeps libadwaita's native 22 px window corners; Game Mode is fullscreen and square, masked to the shared 16 px radius. Only corner pixels outside that radius change; WebP quality 90. Linux matches the Windows scenes and games; its six staggered selections follow its seven-column grid, and Desktop install shows the Library behind the dialog because the Linux app closes Game Details before opening the operation dialog. Presets show the saved-defaults state. Original PNGs, hashes and the capture driver remain private. No Linux gameplay overlay capture exists yet.

Packages and a native Linux Overlay capture remain deferred. An eventual Linux overlay capture must show an actual game in progress behind the panel, with no taskbar or cursor. Do not substitute the standalone sidebar, a title screen or a mockup. Future Linux replacements should match Poster View, effective UI size, language and filters; game assignments may vary. Keep original PNGs and provenance for every replacement.
