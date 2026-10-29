import { SCREENSHOTS, captureForTheme, captureCornerRadius } from './screenshots.mjs';
import { setCardMedia } from './card-media.js';

export function setFeaturePlatform(os) {
  const byId = id => document.getElementById(id);
  const captures = SCREENSHOTS[os] || SCREENSHOTS.windows;
  const theme = document.documentElement.dataset.theme;
  function render(slot, capture, container) {
    const image = byId(`${slot}-image`), link = byId(`${slot}-original`);
    container.hidden = !capture;
    if (!capture) { image.removeAttribute('src'); link.removeAttribute('href'); return; }
    image.onerror = () => { container.hidden = true; };
    image.onload = () => { container.hidden = false; };
    image.src = capture.src; image.alt = capture.alt;
    image.width = capture.width; image.height = capture.height;
    image.style.borderRadius = captureCornerRadius(capture);
    link.href = capture.src;
    link.setAttribute('aria-label', `View ${capture.label.toLowerCase()} full size`);
  }
  const library = captureForTheme(captures['desktop-library'].selected, theme);
  byId('hero-library-media').style.setProperty('--native-radius-ratio', String(library.radius / library.width));
  render('hero-library', library, byId('hero-library-media'));
  byId('hero-library-provenance').textContent = library.provenance;
  byId('feature-overlay-copy').textContent = os === 'windows'
    ? 'Adjust NR and MFG while you play.'
    : 'Adjust NR and MFG while you play. Windows screenshot shown.';
  for (const [slot, key] of [['presets', 'presets'], ['overlay', 'overlay']]) {
    const capture = captureForTheme(captures[key] || (key === 'overlay' ? SCREENSHOTS.windows.overlay : null), theme);
    const container = byId(`feature-${slot}-media`);
    container.dataset.os = os;
    render(`feature-${slot}`, capture, container);
    byId(`feature-${slot}-provenance`).textContent = capture?.provenance || '';
  }
  setCardMedia(os, theme);
}
