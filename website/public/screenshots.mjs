// Keep only available native captures; replace demo entries with the paired set when ready.
// Paths are relative to public/. A missing entry has an explicit pending state.
export const SCREENSHOTS = {
  linux: {
    'desktop-library': {
      src: 'assets/screenshots/linux-desktop-library.webp', width: 1270, height: 810,
      alt: 'rtxForge Linux desktop Library in the dark theme, showing a grid of games in the demo library.',
      label: 'Desktop library', caption: 'Desktop – Library', provenance: 'Native Linux app · Demo library · October 16, 2026'
    },
    'desktop-details': {
      src: 'assets/screenshots/linux-desktop-details.webp', width: 910, height: 690,
      alt: 'rtxForge Linux desktop Game Details for Cyberpunk 2077, with the Tools section selected.',
      label: 'Desktop game details', caption: 'Desktop – Game Details', provenance: 'Native Linux app · Demo library · October 16, 2026'
    }
  },
  windows: {
    'desktop-library': {
      src: 'assets/screenshots/windows-desktop-library.webp', width: 2560, height: 1483,
      alt: 'rtxForge on Windows with the installed library in the wide capsule view, including Control Resonant.',
      label: 'Desktop library', caption: 'Desktop – Library', provenance: 'Native Windows app captured October 20, 2026.'
    },
    'desktop-details': {
      src: 'assets/screenshots/windows-desktop-details.webp', width: 2560, height: 1483,
      alt: 'Control Resonant game details in the native Windows app, with its artwork and Overview selected.',
      label: 'Desktop game details', caption: 'Desktop – Game Details', provenance: 'Native Windows app captured October 20, 2026.'
    },
    'game-mode-details': {
      src: 'assets/screenshots/windows-game-mode-details.webp', width: 2560, height: 1440,
      alt: 'Control Resonant in rtxForge Game Mode, with Xbox controller glyphs for Select, Back and Library.',
      label: 'Game Mode game details', caption: 'Game Mode – Game Details', provenance: 'Native Windows app captured October 20, 2026 using a neutral virtual Xbox controller for UI navigation.'
    }
  }
};
