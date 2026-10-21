// Actual native UI captures. Originals and capture receipts are retained privately.
const provenance = 'Native Windows sample app · Live-library-derived artwork · October 21, 2026. Sample operations are simulated.';
function windows(view, width, height, alt, label, caption, extra = {}) {
  return {
    src: `assets/screenshots/windows-${view}-dark.webp`,
    light: { src: `assets/screenshots/windows-${view}-light.webp` },
    width, height, radius: view.startsWith('desktop-') ? 16 : 0, alt, label, caption, provenance, ...extra
  };
}
function install(mode, game, sizes) {
  const captions = { review: 'Review Installation', progress: 'Installing features', done: 'Done' };
  const frames = Object.entries(sizes).map(([step, [width, height]]) => windows(
    `${mode}-install-${step}`, width, height,
    `${game} ${captions[step]} panel in the native Windows ${mode === 'desktop' ? 'desktop' : 'Game Mode'} app.`,
    `${mode === 'desktop' ? 'Desktop' : 'Game Mode'} install: ${captions[step]}`, 'Install', { radius: mode === 'desktop' ? 14 : 22 }
  ));
  return { ...frames[0], sequence: frames.slice(1) };
}
export const SCREENSHOTS = {
  linux: {
    'desktop-library': {
      src: 'assets/screenshots/linux-desktop-library.webp', width: 1270, height: 810, radius: 12,
      alt: 'rtxForge Linux desktop Library in the dark theme, showing a grid of games in the demo library.',
      label: 'Desktop library', caption: 'Library', provenance: 'Native Linux app · Demo library · October 16, 2026'
    },
    'desktop-details': {
      src: 'assets/screenshots/linux-desktop-details.webp', width: 910, height: 690, radius: 12,
      alt: 'rtxForge Linux desktop Game Details for Cyberpunk 2077, with the Tools section selected.',
      label: 'Desktop game details', caption: 'Game Details', provenance: 'Native Linux app · Demo library · October 16, 2026'
    }
  },
  windows: {
    'desktop-library': windows('desktop-library', 2989, 1785,
      'Windows desktop Library in Poster View, with the expanded sidebar and no games selected.',
      'Desktop library', 'Library', {
        selected: windows('desktop-library-selected', 2989, 1785,
          'The same Windows desktop Library with six games selected in a staggered pattern.',
          'Desktop library with games selected', 'Library')
      }),
    'desktop-details': windows('desktop-details', 2989, 1785,
      'The Witcher 3: Wild Hunt — Remastered Overview in the Windows desktop app, with the expanded sidebar.',
      'Desktop game details', 'Game Details'),
    'desktop-install': install('desktop', 'inZOI', { review: [667, 574], progress: [998, 478], done: [858, 338] }),
    presets: windows('desktop-presets', 2989, 1785,
      'Standalone Windows Presets with frame generation, neural rendering and image-tuning controls.',
      'Desktop presets', 'Presets', { carousel: false }),
    'game-mode-library': windows('game-mode-library', 2560, 1440,
      'Windows Game Mode Library in Poster View, with no games selected and Xbox controller glyphs visible.',
      'Game Mode library', 'Library', {
        selected: windows('game-mode-library-selected', 2560, 1440,
          'The same Windows Game Mode Library with six games selected in a staggered pattern and Xbox controller glyphs visible.',
          'Game Mode library with games selected', 'Library')
      }),
    'game-mode-details': windows('game-mode-details', 2560, 1440,
      'Dragon Age: The Veilguard Game Details with the DLSS Files tab selected and Xbox controller glyphs visible.',
      'Game Mode game details', 'Game Details'),
    'game-mode-presets': windows('game-mode-presets', 2560, 1440,
      'Windows Game Mode Presets with frame generation, neural rendering, image tuning and Xbox controller glyphs.',
      'Game Mode presets', 'Presets'),
    'game-mode-install': install('game-mode', 'Avatar: Frontiers of Pandora', { review: [1268, 565], progress: [1268, 570], done: [1268, 290] })
  }
};
export function captureForTheme(capture, theme) {
  if (!capture) return capture;
  const resolved = theme === 'light' && capture.light ? { ...capture, ...capture.light } : { ...capture };
  if (capture.selected) resolved.selected = captureForTheme(capture.selected, theme);
  if (capture.sequence) resolved.sequence = capture.sequence.map(frame => captureForTheme(frame, theme));
  return resolved;
}
export function screenshotsForTheme(os, theme) {
  return Object.fromEntries(Object.entries(SCREENSHOTS[os] || {}).map(([key, capture]) => [key, captureForTheme(capture, theme)]));
}
export function captureCornerRadius(capture) {
  const radius = capture?.radius || 0;
  return radius ? `${100 * radius / capture.width}% / ${100 * radius / capture.height}%` : '0';
}
