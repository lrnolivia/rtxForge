# Game Mode design

The surface is an operating interface for players managing graphics packages across their game library. It extends the approved overlay materials, typography, iconography and recovery-first operation model.

## Composition

The Library is a direct poster grid, wide capsule grid or list, with search and batch selection. A redundant selected-game summary is intentionally absent. Primary navigation remains stable above the workspace. Controller focus is visible and directional navigation follows rendered geometry.

Game Details fills the main workspace. Real hero artwork anchors the desktop-style header, with a poster beside the actual title and metadata. Section navigation defaults to a sidebar beside the nested translucent control workspace, with Tabs available in Appearance. Packages and Extras follow the current native Game Mode content hierarchy, with stronger controller focus. Game titles retain their real case; section headings use uppercase.

The same shell carries Packages, Extras, Settings, and exact-token operation review/progress. Preparation, blocked selections, user confirmation, cancellation, completed reports and errors have separate truthful states.

## Tokens

| Token | Value |
| --- | --- |
| Body | Roboto variable, 16px default / 18px large |
| Brand and section headings | Bakbak One |
| Symbols | Existing pinned Phosphor Regular font |
| Clear foreground | `#f7f3ec` warm white |
| Clear secondary foreground | `#e0dcd5` |
| Clear surface | warm neutral white, 13% alpha |
| Dark surface | `rgb(22 23 24 / 80%)` |
| Light surface | `rgb(239 238 234 / 92%)` |
| Clear section / nested / control | white at 8% / 13% / 19% |
| Dark section / nested / control | white at 7% / 11% / 16% |
| Light section / nested / control | white at 27% / 36% / 50% |
| Blur | 48px Clear/Dark, 44px Light |
| Grain | 2% deterministic monochrome texture |
| Default main UI accent | `#d8d5ce` neutral |
| Corners | 20px shell, 16px section, 12px nested, 10px control |
| Focus | 3px true accent outline, 5px offset |
| Motion | 170–320ms; spring focus `cubic-bezier(.2,1.16,.32,1)` |

Clear mode with Accent Tint on is the default. Accent Tint remains a persisted independent option and applies to the Details workspace. Hero titles use an adaptive shade of the actual accent with normal blending. Clear and Dark information cards use pale accent-hued text; Light uses dark accent-hued text over translucent light glass. Global chrome and Library, Packages, Extras and Settings surfaces stay neutral. General shadows are neutral; tinted Details cards may use soft accent shadows. The generic background is the existing 3840×1240 Steam hero. Poster focus lifts and scales the complete card. Nested cards do not reapply an opaque theme tint.

The logo is the existing raw mark without a platter, paired with the neutral rtxForge wordmark. Font and icon licenses are retained beside the copied files.

## Responsiveness and access

The shell uses the full viewport width, including 2560×1440 CSS pixels for a native 3840×2160 display at 150%. Library results fit complete poster or capsule rows using available width and height; their own inset scroller preserves toolbar access and shadow padding. Compact desktop and narrow layouts reflow controls, steppers and Presets columns. Most controls have 48px minimum height, with stable focus and no hover-only actions. Controller selection is available beside each tile. Xbox uses colored ABXY circles, PlayStation uses colored shapes, and Nintendo uses monochrome letter prompts. Reduced motion, forced colors, accessible labels, proper form controls and keyboard access are foundations.

## Truth

Discovery never implies compatibility, ownership or active execution. The local reader reports unverified state until a targeted engine scan supplies the relevant record. Runtime telemetry remains unreported unless the existing host observes it. Artwork and metadata come from local Steam and app caches; unavailable artwork has an honest placeholder.

Selected Library cards and rows use the desktop solid game-color fill with readable game-derived ink. Idle titles stay neutral. Button and navigation labels share a softened accent and Screen blend in Clear/Dark; Light uses normal blending. Each section uses one glass layer.
