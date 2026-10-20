import { SCREENSHOTS } from './screenshots.mjs';

export function setFeaturePlatform(os) {
  const byId = id => document.getElementById(id);
  const windows = os === 'windows';
  byId('feature-second-heading').textContent = 'Play.';
  byId('feature-second-copy').textContent = windows
    ? 'Keep your game in view. The Windows overlay is in development, bringing controls for neural rendering and multi-frame generation into your game.'
    : 'Open your library in Game Mode, with larger artwork and controller navigation.';
  for (const [slot, key] of [['presets', 'presets'], ['second', windows ? 'overlay' : 'game-mode-details']]) {
    const capture = SCREENSHOTS[os]?.[key], image = byId(`feature-${slot}-image`);
    byId(`feature-${slot}-media`).hidden = !capture;
    if (capture) {
      image.src = capture.src; image.alt = capture.alt; image.width = capture.width; image.height = capture.height;
      byId(`feature-${slot}-provenance`).textContent = capture.provenance;
      image.onerror = () => { byId(`feature-${slot}-media`).hidden = true; };
    } else { image.removeAttribute('src'); image.alt = ''; }
  }
}
