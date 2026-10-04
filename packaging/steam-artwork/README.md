# rtxForge Steam artwork — 35mm hardware edition

Approved static artwork for rtxForge, including the final raised poster lockup.

[Download the complete artwork pack](https://github.com/lrnolivia/rtxForge/releases/tag/artwork-35mm-20261004). The pack contains every PNG and SVG listed below, plus fonts, licenses and source. In this source checkout the full-resolution hero is stored as editable SVG; build.py regenerates its PNG, also supplied ready to use in the release pack.

| Asset | Size | Use |
| --- | --- | --- |
| `exports/rtxforge-steam-portrait.png` | 600 × 900 | Portrait grid/poster |
| `exports/rtxforge-steam-wide.png` | 920 × 430 | Wide library capsule |
| `exports/rtxforge-steam-hero.png` | 3840 × 1240 | Image-only library hero |
| `exports/rtxforge-logo-white.png` | 1280 × 400 | Separate white transparent wordmark, soft shadow |
| `exports/rtxforge-logo-dark.png` | 1280 × 400 | Separate dark transparent wordmark, soft shadow |

The hero intentionally contains no logo or text. Overlay the separate logo in Steam. The logo PNGs have real transparency; any checkerboard in the preview is only a review aid. The poster's logo and wordmark sit 40 px higher than the first 35mm revision, with the lower fade adjusted for legibility.

Fine grain and vignette affect the hardware imagery. The approved icon and outlined typography remain crisp. Bakbak One is used for the wordmark; Inter for the tagline. Font licenses are included in `source/`.

Editable outlined SVG exports, source fonts, the original approved icon, raster image plate, and `build.py` are included. Rebuild with Python 3, fontTools and Inkscape. The hardware image is AI-generated conceptual imagery, not a particular commercial graphics card. Its 1536 × 1024 raster source is upscaled for the hero; the export is not native 4K image detail.

These files publish the artwork only. Steam does not automatically read custom artwork embedded inside an arbitrary non-Steam executable; applying it requires Steam's custom-artwork controls or an explicit integration helper. This artwork publication does not claim that the integration helper or the app's release candidate is finished.
