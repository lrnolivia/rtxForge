import { SCREENSHOTS, captureForTheme, captureCornerRadius } from './screenshots.mjs';

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const byId = id => document.getElementById(id);
function createSequence(prefix) {
  const container = byId(`${prefix}-media`);
  const link = byId(`${prefix}-original`);
  const images = [byId(`${prefix}-image`), byId(`${prefix}-alternate`)];
  const pagination = byId(`${prefix}-pagination`);
  let frames = [], key, index = 0, revision = 0, current, timer, visible = false, hovered = false, focused = false;
  function schedule() {
    clearTimeout(timer);
    if (frames.length > 1 && visible && !hovered && !focused && !document.hidden && !reducedMotion.matches) {
      timer = setTimeout(() => show((index + 1) % frames.length), 8000);
    }
  }
  function updateDots() {
    [...pagination.children].forEach((button, i) => button.setAttribute('aria-current', String(i === index)));
  }
  async function show(next, animate = true) {
    clearTimeout(timer);
    const request = ++revision, frame = frames[next];
    if (!frame) return;
    images.forEach(image => image.getAnimations().forEach(animation => animation.cancel()));
    const image = images.find(item => item !== current);
    image.style.opacity = '0'; image.src = frame.src;
    image.width = frame.width; image.height = frame.height;
    image.style.borderRadius = captureCornerRadius(frame);
    try { await image.decode(); }
    catch { if (request === revision) schedule(); return; }
    if (request !== revision) return;
    const previous = current;
    if (previous) { previous.alt = ''; previous.setAttribute('aria-hidden', 'true'); previous.style.zIndex = '0'; }
    image.style.zIndex = '1'; image.style.opacity = '1';
    image.alt = frame.alt; image.removeAttribute('aria-hidden');
    current = image; index = next;
    container.hidden = false; container.dataset.state = String(index);
    link.href = frame.src; link.setAttribute('aria-label', `View ${frame.label.toLowerCase()} full size`);
    byId(`${prefix}-provenance`).textContent = frame.provenance;
    updateDots(); schedule();
    // The outgoing frame stays opaque below the incoming image throughout the fade.
    if (animate && previous && !reducedMotion.matches) {
      await image.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 1600, easing: 'cubic-bezier(.4,0,.2,1)' }).finished.catch(() => {});
    }
    if (request === revision && previous !== current && previous) previous.style.opacity = '0';
  }
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; schedule(); }, { threshold: .1 }).observe(container.parentElement);
  container.addEventListener('mouseenter', () => { hovered = true; schedule(); });
  container.addEventListener('mouseleave', () => { hovered = false; schedule(); });
  container.addEventListener('focusin', () => { focused = true; schedule(); });
  container.addEventListener('focusout', event => { if (!container.contains(event.relatedTarget)) { focused = false; schedule(); } });
  document.addEventListener('visibilitychange', schedule);
  reducedMotion.addEventListener('change', () => {
    images.forEach(image => image.getAnimations().forEach(animation => animation.finish()));
    schedule();
  });
  return (nextFrames, nextKey) => {
    if (key === nextKey) return;
    key = nextKey; frames = nextFrames;
    pagination.replaceChildren(...frames.map((frame, i) => {
      const button = document.createElement('button'); button.type = 'button';
      button.setAttribute('aria-label', frame.label); button.setAttribute('aria-controls', link.id);
      button.addEventListener('click', () => show(i));
      button.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? frames.length - 1 : (i + (event.key === 'ArrowRight' ? 1 : -1) + frames.length) % frames.length;
        pagination.children[next].focus(); show(next);
      });
      return button;
    }));
    index = Math.min(index, frames.length - 1); updateDots(); show(index, false);
  };
}
let install, gameMode;
export function setCardMedia(os, theme) {
  install ||= createSequence('feature-install');
  gameMode ||= createSequence('feature-game-mode');
  const capture = captureForTheme(SCREENSHOTS[os]['desktop-install'], theme);
  install([capture, ...(capture.sequence || [])], `${os}:${theme}`);
  // Lauren chose the current Linux five-option interface for both platform presentations.
  const game = SCREENSHOTS.linux;
  gameMode([game['game-mode-library'].selected, game['game-mode-details'], game['game-mode-presets']].map(frame => captureForTheme(frame, theme)), theme);
}
