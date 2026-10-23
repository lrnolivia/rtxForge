// Actual native UI captures. Originals and capture receipts are retained privately.
const PROVENANCE = {
  windows: 'Native Windows sample app · Live-library-derived artwork · October 21, 2026. Sample operations are simulated.',
  linux: 'Native Linux GTK app in write-disabled demo mode · Same private sample library and live-library-derived artwork as Windows · October 23, 2026. Sample operations are simulated.'
};
const OS_NAMES = { windows: 'Windows', linux: 'Linux' };
// Linux desktop frames keep libadwaita's native window corners (22 px at 1.5x).
function shot(os, view, width, height, alt, label, caption, extra = {}) {
  const radius = os === 'linux' && !view.startsWith('game-mode') ? 22 : 16;
  return {
    src: `assets/screenshots/${os}-${view}-dark.webp`,
    light: { src: `assets/screenshots/${os}-${view}-light.webp` },
    width, height, radius, alt, label, caption, provenance: PROVENANCE[os], ...extra
  };
}
const windows = (...args) => shot('windows', ...args);
const linux = (...args) => shot('linux', ...args);
function install(os, mode, game, width, height) {
  const captions = { review: 'Review Installation', progress: 'Installing features', done: 'Done' };
  const context = os === 'linux' && mode === 'desktop' ? 'the Library' : 'the game artwork';
  const frames = Object.keys(captions).map(step => shot(os,
    `${mode}-install-${step}`, width, height,
    `${game} ${captions[step]} in the native ${OS_NAMES[os]} ${mode === 'desktop' ? 'desktop' : 'Game Mode'} app, with ${context} and navigation visible${mode === 'game-mode' ? ', including Xbox controller glyphs' : ''}.`,
    `${mode === 'desktop' ? 'Desktop' : 'Game Mode'} install: ${captions[step]}`, 'Install'
  ));
  return { ...frames[0], sequence: frames.slice(1) };
}
export const SCREENSHOTS = {
  linux: {
    'desktop-library': linux('desktop-library', 2985, 1780,
      'Linux desktop Library in Poster View, with the expanded sidebar and no games selected.',
      'Desktop library', 'Library', {
        selected: linux('desktop-library-selected', 2985, 1780,
          'The same Linux desktop Library with six games selected in a staggered pattern.',
          'Desktop library with games selected', 'Library')
      }),
    'desktop-details': linux('desktop-details', 2985, 1780,
      'The Witcher 3: Wild Hunt — Remastered Overview in the Linux desktop app, with the expanded sidebar.',
      'Desktop game details', 'Game Details'),
    'desktop-install': install('linux', 'desktop', 'inZOI', 2985, 1780),
    presets: linux('desktop-presets', 2985, 1780,
      'Standalone Linux Presets with frame generation, DLSS presets, neural rendering and image-tuning controls.',
      'Desktop presets', 'Presets', { carousel: false }),
    'game-mode-library': linux('game-mode-library', 2560, 1438,
      'Linux Game Mode Library in Poster View, with no games selected and Xbox controller glyphs visible.',
      'Game Mode library', 'Library', {
        selected: linux('game-mode-library-selected', 2560, 1438,
          'The same Linux Game Mode Library with six games selected in a staggered pattern and Xbox controller glyphs visible.',
          'Game Mode library with games selected', 'Library')
      }),
    'game-mode-details': linux('game-mode-details', 2560, 1438,
      'Dragon Age: The Veilguard Game Details in Linux Game Mode with the DLSS Files section selected and Xbox controller glyphs visible.',
      'Game Mode game details', 'Game Details'),
    'game-mode-presets': linux('game-mode-presets', 2560, 1438,
      'Linux Game Mode Presets with frame generation, neural rendering, image tuning and Xbox controller glyphs.',
      'Game Mode presets', 'Presets'),
    'game-mode-install': install('linux', 'game-mode', 'Avatar: Frontiers of Pandora', 2560, 1438)
  },
  windows: {
    'desktop-library': windows('desktop-library', 2985, 1781,
      'Windows desktop Library in Poster View, with the expanded sidebar and no games selected.',
      'Desktop library', 'Library', {
        selected: windows('desktop-library-selected', 2985, 1781,
          'The same Windows desktop Library with six games selected in a staggered pattern.',
          'Desktop library with games selected', 'Library')
      }),
    'desktop-details': windows('desktop-details', 2985, 1781,
      'The Witcher 3: Wild Hunt — Remastered Overview in the Windows desktop app, with the expanded sidebar.',
      'Desktop game details', 'Game Details'),
    'desktop-install': install('windows', 'desktop', 'inZOI', 2556, 1437),
    presets: windows('desktop-presets', 2985, 1781,
      'Standalone Windows Presets with frame generation, neural rendering and image-tuning controls.',
      'Desktop presets', 'Presets', { carousel: false }),
    'game-mode-library': windows('game-mode-library', 2560, 1438,
      'Windows Game Mode Library in Poster View, with no games selected and Xbox controller glyphs visible.',
      'Game Mode library', 'Library', {
        selected: windows('game-mode-library-selected', 2560, 1438,
          'The same Windows Game Mode Library with six games selected in a staggered pattern and Xbox controller glyphs visible.',
          'Game Mode library with games selected', 'Library')
      }),
    'game-mode-details': windows('game-mode-details', 2560, 1438,
      'Dragon Age: The Veilguard Game Details with the DLSS Files tab selected and Xbox controller glyphs visible.',
      'Game Mode game details', 'Game Details'),
    'game-mode-presets': windows('game-mode-presets', 2560, 1438,
      'Windows Game Mode Presets with frame generation, neural rendering, image tuning and Xbox controller glyphs.',
      'Game Mode presets', 'Presets'),
    'game-mode-install': install('windows', 'game-mode', 'Avatar: Frontiers of Pandora', 2560, 1438),
    overlay: {
      src: 'assets/screenshots/windows-control-overlay.webp', width: 2560, height: 1440, radius: 16,
      alt: 'rtxForge overlay open during actual CONTROL Resonant gameplay, beside a close-up of the character.',
      label: 'Windows gameplay overlay', caption: 'Overlay', carousel: false,
      provenance: 'Native Windows overlay over actual CONTROL Resonant gameplay · October 21, 2026. Work in progress; captured appearance is unchanged.'
    }
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
