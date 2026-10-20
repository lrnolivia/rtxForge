import { SCREENSHOTS } from './screenshots.mjs';

export function setFeaturePlatform(os) {
  const byId = id => document.getElementById(id);
  const windows = os === 'windows';
  byId('feature-overlay-copy').textContent = windows
    ? 'Adjust neural rendering and multi-frame generation while keeping your game in view.'
    : 'The in-game NR and MFG overlay is in development for Windows.';
  for (const [slot, key] of [['presets', 'presets'], ['game-mode', 'game-mode-library'], ['overlay', windows ? 'overlay' : null]]) {
    const capture = key && SCREENSHOTS[os]?.[key], image = byId(`feature-${slot}-image`);
    byId(`feature-${slot}-media`).hidden = !capture;
    if (capture) {
      image.src = capture.src; image.alt = capture.alt; image.width = capture.width; image.height = capture.height;
      byId(`feature-${slot}-provenance`).textContent = capture.provenance;
      image.onerror = () => { byId(`feature-${slot}-media`).hidden = true; };
    } else { image.removeAttribute('src'); image.alt = ''; }
  }
}
