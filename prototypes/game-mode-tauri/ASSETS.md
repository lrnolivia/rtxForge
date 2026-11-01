# Asset provenance

- `public/logo-mark.png`: existing `prototypes/overlay-rmlui/logo-mark.png`, unchanged. Native icon files are format exports of the same raw mark.
- `public/fonts/RobotoVariable.ttf`: existing `gui/fonts/RobotoVariable.ttf`; OFL retained.
- `public/fonts/BakbakOne-Regular.ttf`: existing `gui/fonts/BakbakOne-Regular.ttf`; OFL retained.
- `public/fonts/Phosphor.ttf`: existing pinned `assets/game-mode/icons/Phosphor.ttf`; MIT notice retained in `public/fonts/LICENSE.txt`.
- `public/grain.png`: deterministic 64×64 monochrome grain, Python `random.Random(4)`, rendered at 2% opacity. Origin is also embedded in PNG metadata.
- Game artwork is read at runtime from the user's existing Steam and app caches. No game artwork is copied into the repository or claimed as project-owned imagery.

- `public/app-hero-dark.png`: existing `packaging/steam-artwork/exports/rtxforge-steam-hero.png`, unchanged 3840×1240 PNG. This is the generic app backdrop; game-specific hero art remains read at runtime.
- `public/app-hero-light.png`: light presentation variant of the same rtxForge backdrop, used only by the Light material.
