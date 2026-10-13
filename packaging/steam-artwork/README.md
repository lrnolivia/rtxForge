# rtxForge Steam artwork — 35mm hardware edition

Approved static artwork for rtxForge, including the raised poster lockup, user-revised hero and stronger transparent-logo shadow.

[Download the original artwork pack](https://github.com/lrnolivia/rtxForge/releases/tag/artwork-35mm-20261004). That historical pack predates the revised hero and stronger logo shadow. Current exports contain every PNG and SVG listed below; `build.py` reproduces them from the source assets.

| Asset | Size | Use |
| --- | --- | --- |
| `exports/rtxforge-steam-portrait.png` | 600 × 900 | Portrait grid/poster |
| `exports/rtxforge-steam-wide.png` | 920 × 430 | Wide library capsule |
| `exports/rtxforge-steam-hero.png` | 3840 × 1240 | Image-only library hero |
| `exports/rtxforge-logo-white.png` | 1280 × 400 | Separate white transparent wordmark, soft shadow |
| `exports/rtxforge-logo-dark.png` | 1280 × 400 | Separate dark transparent wordmark, soft shadow |

The hero intentionally contains no logo or text. Its source is `assets/rtxhero.png` (3840 × 1240), and its PNG export preserves the supplied bytes; the SVG embeds that same image without a new crop or fade. Overlay the separate logo in Steam. The logo PNGs have real transparency, a stronger soft black shadow and padding around the blur. Any checkerboard in the preview is only a review aid. The poster's logo and wordmark sit 40 px higher than the first 35mm revision, with the lower fade adjusted for legibility. Poster and wide capsule artwork are unchanged by the hero revision.

Fine grain and vignette affect the hardware imagery. The approved icon and outlined typography remain crisp. Bakbak One is used for the wordmark; Inter for the tagline. Font licenses are included in `source/`.

Outlined SVG exports, source fonts, the original approved icon, raster image plates, and `build.py` are included. Rebuild with Python 3, fontTools and Inkscape. The original hardware image used by the poster and wide capsule is AI-generated conceptual imagery, not a particular commercial graphics card. The revised hero is a separately supplied user edit.

These files publish the artwork only. Steam does not automatically read custom artwork embedded inside an arbitrary non-Steam executable; applying it requires Steam's custom-artwork controls or an explicit integration helper. This artwork publication does not claim that the integration helper or the app's release candidate is finished.
