// Publish Dark Windows captures in both website themes until the native Light UI is ready.
// Keep actual Linux captures in its gallery; feature cards may fall back to Windows.
// Paths are relative to public/. A missing entry has an explicit pending state.
export const SCREENSHOTS = {
  linux: {
    'desktop-library': {
      src: 'assets/screenshots/linux-desktop-library.webp', width: 1270, height: 810,
      alt: 'rtxForge Linux desktop Library in the dark theme, showing a grid of games in the demo library.',
      label: 'Desktop library', caption: 'Library', provenance: 'Native Linux app · Demo library · October 16, 2026'
    },
    'desktop-details': {
      src: 'assets/screenshots/linux-desktop-details.webp', width: 910, height: 690,
      alt: 'rtxForge Linux desktop Game Details for Cyberpunk 2077, with the Tools section selected.',
      label: 'Desktop game details', caption: 'Game Details', provenance: 'Native Linux app · Demo library · October 16, 2026'
    }
  },
  windows: {
    'desktop-library': {
      src: 'assets/screenshots/windows-poster-desktop-library-dark.webp', width: 1440, height: 965,
      alt: 'Windows desktop Library in Poster View, with the sidebar collapsed and no games selected.',
      label: 'Desktop library', caption: 'Library', provenance: 'Native Windows app captured October 20, 2026.',
      selected: {
        src: 'assets/screenshots/windows-poster-desktop-library-selected-dark.webp',
        alt: 'The same Windows desktop Library with six games selected in an alternating pattern.',
        label: 'Desktop library with games selected'
      }
    },
    'desktop-details': {
      src: 'assets/screenshots/windows-poster-desktop-details-dark.webp', width: 1440, height: 965,
      alt: 'The Witcher 3: Wild Hunt — Remastered Overview in the Windows desktop app, with its artwork and the sidebar collapsed.',
      label: 'Desktop game details', caption: 'Game Details', provenance: 'Native Windows app captured October 20, 2026.'
    },
    presets: {
      src: 'assets/screenshots/windows-poster-presets-dark.webp', width: 1440, height: 965,
      alt: 'The standalone Windows Presets panel with horizontal frame-generation choices and neural-rendering and image-tuning cards.',
      label: 'Desktop presets', caption: 'Presets', provenance: 'Native Windows app captured October 20, 2026.'
    },
    'game-mode-library': {
      src: 'assets/screenshots/windows-poster-game-mode-library-dark.webp', width: 1440, height: 810,
      alt: 'Windows Game Mode Library in Poster View, with no games selected and Xbox A, B and Y controller glyphs visible.',
      label: 'Game Mode library', caption: 'Library', provenance: 'Native Windows app captured October 20, 2026 using a virtual Xbox controller for UI navigation.',
      selected: {
        src: 'assets/screenshots/windows-poster-game-mode-library-selected-dark.webp',
        alt: 'The same Windows Game Mode Library with seven games selected in a staggered pattern and Xbox controller glyphs visible.',
        label: 'Game Mode library with games selected'
      }
    },
    'game-mode-details': {
      src: 'assets/screenshots/windows-poster-game-mode-details-dark.webp', width: 1440, height: 810,
      alt: 'Cyberpunk 2077 Overview in Windows Game Mode, with Xbox controller glyphs for Select, Back and Library.',
      label: 'Game Mode game details', caption: 'Game Details', provenance: 'Native Windows app captured October 20, 2026 using a neutral virtual Xbox controller for UI navigation.'
    }
  }
};
