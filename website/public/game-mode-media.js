import { SCREENSHOTS, captureForTheme, captureCornerRadius } from './screenshots.mjs';

// Lauren chose the current Linux five-option interface for both platform presentations.
const captures = SCREENSHOTS.linux;
const frames = [captures['game-mode-library'].selected, captures['game-mode-details'], captures['game-mode-presets']];
const labels = ['Selected Library', 'Game Details', 'Presets'];
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
let index = 0, theme, generation = 0, timer, visible = false, interacting = false;
let paused = reducedMotion.matches, initialized = false, current;
const byId = id => document.getElementById(id);
function schedule() {
  clearTimeout(timer);
  if (!paused && visible && !interacting && !document.hidden) timer = setTimeout(() => show((index + 1) % frames.length), 6000);
}
function updateButton() {
  const button = byId('game-mode-pause');
  button.textContent = paused ? 'Play' : 'Pause';
  button.setAttribute('aria-label', `${paused ? 'Play' : 'Pause'} Game Mode previews`);
}
async function show(nextIndex) {
  clearTimeout(timer);
  const revision = ++generation;
  const frame = captureForTheme(frames[nextIndex], theme);
  const image = current === byId('feature-game-mode-image') ? byId('feature-game-mode-alternate') : byId('feature-game-mode-image');
  image.classList.remove('is-current');
  image.src = frame.src;
  image.width = frame.width; image.height = frame.height;
  image.style.borderRadius = captureCornerRadius(frame);
  try { await image.decode(); }
  catch { if (revision === generation) schedule(); return; }
  if (revision !== generation) return;
  if (current) { current.classList.remove('is-current'); current.alt = ''; current.setAttribute('aria-hidden', 'true'); }
  image.alt = frame.alt; image.removeAttribute('aria-hidden'); image.classList.add('is-current');
  current = image; index = nextIndex;
  const container = byId('feature-game-mode-media');
  container.hidden = false; container.dataset.captureOs = 'linux'; container.dataset.state = String(index);
  byId('feature-game-mode-original').href = frame.src;
  byId('feature-game-mode-original').setAttribute('aria-label', `View Game Mode ${labels[index].toLowerCase()} full size`);
  byId('feature-game-mode-provenance').textContent = frame.provenance;
  byId('game-mode-state').textContent = labels[index];
  schedule();
}
export function setGameModeTheme(nextTheme) {
  if (!initialized) {
    initialized = true;
    const container = byId('feature-game-mode-media');
    // Observe the always-visible parent, since the media starts hidden until decoded.
    new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; schedule(); }, { threshold: .1 }).observe(container.parentElement);
    container.addEventListener('mouseenter', () => { interacting = true; schedule(); });
    container.addEventListener('mouseleave', () => { interacting = false; schedule(); });
    container.addEventListener('focusin', () => { interacting = true; schedule(); });
    container.addEventListener('focusout', event => { if (!container.contains(event.relatedTarget)) { interacting = false; schedule(); } });
    byId('game-mode-pause').addEventListener('click', () => { paused = !paused; updateButton(); schedule(); });
    document.addEventListener('visibilitychange', schedule);
    reducedMotion.addEventListener('change', () => { paused = reducedMotion.matches; updateButton(); schedule(); });
    updateButton();
  }
  if (theme === nextTheme && current) return;
  theme = nextTheme;
  show(index);
}
