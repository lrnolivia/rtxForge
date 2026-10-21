import { SCREENSHOTS, captureForTheme, captureCornerRadius } from './screenshots.mjs';

let currentPlatform = 'windows', installStep = 1;
export function setFeaturePlatform(os) {
  const byId = id => document.getElementById(id);
  currentPlatform = os;
  const windows = os === 'windows';
  byId('feature-overlay-copy').textContent = windows
    ? 'Adjust neural rendering and multi-frame generation while keeping your game in view.'
    : 'The in-game NR and MFG overlay is in development for Windows.';
  const steps = byId('feature-install-steps');
  if (!steps.children.length) ['Review', 'Installing', 'Done'].forEach((label, i) => {
    const button = document.createElement('button'); button.type = 'button';
    button.textContent = label; button.setAttribute('aria-controls', 'feature-install-image');
    button.addEventListener('click', () => { installStep = i; setFeaturePlatform(currentPlatform); });
    steps.append(button);
  });
  [...steps.children].forEach((button, i) => button.setAttribute('aria-pressed', String(i === installStep)));
  for (const [slot, key] of [['presets', 'presets'], ['install', 'desktop-install'], ['game-mode', 'game-mode-library'], ['overlay', 'overlay']]) {
    let capture = captureForTheme(SCREENSHOTS[os]?.[key] || SCREENSHOTS.windows[key], document.documentElement.dataset.theme);
    if (slot === 'install' && capture) capture = [capture, ...(capture.sequence || [])][installStep] || capture;
    const image = byId(`feature-${slot}-image`);
    byId(`feature-${slot}-media`).hidden = !capture;
    if (capture) {
      image.src = capture.src; image.alt = capture.alt; image.width = capture.width; image.height = capture.height;
      image.style.borderRadius = captureCornerRadius(capture);
      byId(`feature-${slot}-provenance`).textContent = capture.provenance;
      image.onerror = () => { byId(`feature-${slot}-media`).hidden = true; };
    } else { image.removeAttribute('src'); image.alt = ''; }
  }
}
