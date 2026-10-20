import { SCREENSHOTS } from './screenshots.mjs';

export function createGallery() {
  const byId = id => document.getElementById(id);
  const gallery = document.querySelector('.app-gallery');
  const image = byId('gallery-image'), previous = byId('gallery-previous');
  const stage = byId('gallery-stage'), dots = byId('gallery-dots');
  const rotation = byId('gallery-rotation');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let os = 'linux', interfaceMode = 'desktop', captures = [], index = 0, frame = 0, generation = 0, timer;
  let rotating = !reducedMotion.matches, hovering = false, visible = false, loading = false, failed = false, pointerRotation;

  function schedule() {
    clearTimeout(timer);
    if (rotating && visible && !hovering && !loading && !failed && !document.hidden && (captures.length > 1 || captures[index]?.[1].selected)) {
      timer = setTimeout(() => {
        const selectionNext = captures[index]?.[1].selected && frame === 0;
        show(selectionNext ? index : (index + 1) % captures.length, { selection: selectionNext ? 1 : 0 });
      }, 6000);
    }
  }
  function rotationState() {
    rotation.setAttribute('aria-label', `${rotating ? 'Pause' : 'Play'} screenshot carousel`);
    byId('gallery-rotation-icon').src = `assets/player-${rotating ? 'pause' : 'play'}.svg`;
    schedule();
  }
  function pause() { rotating = false; rotationState(); }
  function cancelTransition() {
    image.getAnimations().forEach(animation => animation.cancel());
    previous.getAnimations().forEach(animation => animation.cancel());
    previous.hidden = true; previous.removeAttribute('src');
  }
  function message(title, copy, { retry = false } = {}) {
    loading = false; image.hidden = true; image.removeAttribute('src'); image.alt = '';
    byId('gallery-original').hidden = true;
    byId('gallery-message-title').textContent = title;
    byId('gallery-message-copy').textContent = copy;
    byId('gallery-message').hidden = false;
    byId('gallery-retry').hidden = !retry;
    byId('gallery-retry').setAttribute('aria-disabled', 'false');
    byId('gallery-retry').textContent = 'Retry screenshot';
    stage.classList.add('is-pending'); stage.setAttribute('aria-busy', 'false');
    schedule();
  }
  function show(next, { manual = false, animate = true, selection = 0 } = {}) {
    clearTimeout(timer); cancelTransition();
    index = next; failed = false; const current = ++generation;
    if (manual) pause();
    const name = os === 'windows' ? 'Windows' : 'Linux';
    const interfaceName = interfaceMode === 'game-mode' ? 'Game Mode' : 'Desktop';
    const view = captures[index]?.[1];
    frame = selection && view?.selected ? 1 : 0;
    const capture = frame ? { ...view, ...view.selected } : view;
    [...dots.children].forEach((button, i) => {
      if (i === index) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    });
    byId('gallery-status').textContent = '';
    byId('gallery-title').textContent = capture?.caption || '';
    if (!capture) {
      byId('gallery-title').textContent = '';
      byId('gallery-panel').setAttribute('aria-label', `${name} ${interfaceName} screenshots coming soon`);
      message(`${name} ${interfaceName} screenshots are on the way.`, 'More app views will appear here when they are ready.');
      return;
    }
    loading = true; stage.setAttribute('aria-busy', 'true');
    byId('gallery-retry').setAttribute('aria-disabled', 'true');
    byId('gallery-retry').textContent = 'Retrying…';
    const preload = new Image();
    preload.onload = () => {
      if (current !== generation) return;
      const outgoing = !image.hidden && image.getAttribute('src');
      if (outgoing && animate && !reducedMotion.matches) {
        previous.src = outgoing; previous.width = image.width; previous.height = image.height; previous.hidden = false;
      }
      image.src = capture.src; image.alt = capture.alt;
      image.width = capture.width; image.height = capture.height; image.hidden = false;
      if (document.activeElement === byId('gallery-retry')) dots.children[index]?.focus();
      byId('gallery-message').hidden = true; stage.classList.remove('is-pending');
      stage.setAttribute('aria-busy', 'false'); loading = false;
      byId('gallery-title').textContent = capture.caption;
      byId('gallery-original').href = capture.src; byId('gallery-original').hidden = false;
      const label = `${index + 1} of ${captures.length}: ${name} ${capture.label}`;
      byId('gallery-panel').setAttribute('aria-label', label);
      if (manual) byId('gallery-status').textContent = `Showing ${label}.`;
      if (!previous.hidden) {
        const options = { duration: 420, easing: 'ease-in-out' };
        image.animate([{ opacity: 0 }, { opacity: 1 }], options);
        previous.animate([{ opacity: 1 }, { opacity: 0 }], options).finished.then(() => {
          if (current === generation) previous.hidden = true;
        }).catch(() => { /* A new selection cancels the previous fade. */ });
      }
      schedule();
    };
    preload.onerror = () => {
      if (current === generation) {
        failed = true;
        byId('gallery-panel').setAttribute('aria-label', `${name} ${capture.label} unavailable`);
        message('This screenshot could not be loaded.', 'Retry this image or choose another dot.', { retry: true });
        byId('gallery-status').textContent = `${name} ${capture.label} could not be loaded. Retry this image or choose another screenshot.`;
      }
    };
    preload.src = capture.src;
  }
  byId('gallery-retry').addEventListener('click', () => {
    if (!loading) show(index, { manual: true, animate: false, selection: frame });
  });
  function choose(next, { switchSelection = false } = {}) {
    const selection = switchSelection && next === index && captures[index]?.[1].selected ? 1 - frame : 0;
    show(next, { manual: true, selection }); dots.children[next]?.focus();
  }
  dots.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key) || !captures.length) return;
    event.preventDefault();
    choose(event.key === 'Home' ? 0 : event.key === 'End' ? captures.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + captures.length) % captures.length);
  });
  rotation.addEventListener('pointerdown', () => { pointerRotation = rotating; });
  rotation.addEventListener('click', event => { rotating = !(event.detail ? (pointerRotation ?? rotating) : rotating); pointerRotation = undefined; rotationState(); });
  gallery.addEventListener('focusin', pause);
  gallery.addEventListener('pointerenter', event => {
    if (event.pointerType === 'mouse') { hovering = true; schedule(); }
  });
  gallery.addEventListener('pointerleave', event => {
    if (event.pointerType === 'mouse') { hovering = false; schedule(); }
  });
  document.addEventListener('visibilitychange', schedule);
  addEventListener('pagehide', () => clearTimeout(timer));
  addEventListener('pageshow', schedule);
  reducedMotion.addEventListener('change', () => {
    if (reducedMotion.matches) { cancelTransition(); pause(); }
  });
  new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting && entries[0].intersectionRatio >= .35;
    schedule();
  }, { threshold: [0, .35] }).observe(stage);
  rotationState();
  function setPlatform(platform) {
    const selected = captures[index]?.[0], selection = frame; os = platform;
    captures = Object.entries(SCREENSHOTS[os] || {}).filter(([key]) => key.startsWith('game-mode-') === (interfaceMode === 'game-mode'));
    cancelTransition(); image.hidden = true; image.removeAttribute('src');
    byId('gallery-message').hidden = true; byId('gallery-retry').hidden = true;
    byId('gallery-original').hidden = true;
    dots.replaceChildren();
    captures.forEach(([key, capture], i) => {
      const button = document.createElement('button'); button.type = 'button';
      button.className = 'gallery-dot'; button.dataset.capture = key;
      button.setAttribute('aria-label', `Show screenshot ${i + 1} of ${captures.length}: ${capture.label}${capture.selected ? '. Activate again to switch selected games.' : ''}`);
      if (capture.selected) button.title = 'Activate again to switch selected and unselected games';
      button.setAttribute('aria-controls', 'gallery-panel');
      button.addEventListener('click', () => choose(i, { switchSelection: true })); dots.append(button);
    });
    byId('gallery-controls').hidden = captures.length < 2 && !captures[0]?.[1].selected;
    show(Math.max(0, captures.findIndex(([key]) => key === selected)), { animate: false, selection });
    rotationState();
  }
  const interfaces = [byId('gallery-desktop'), byId('gallery-game-mode')];
  function setInterface(next) {
    const mode = next === 1 ? 'game-mode' : 'desktop';
    if (mode === interfaceMode) return;
    interfaceMode = mode; frame = 0;
    interfaces.forEach((button, i) => {
      button.setAttribute('aria-selected', String(i === next)); button.tabIndex = i === next ? 0 : -1;
    });
    byId('gallery-content').setAttribute('aria-labelledby', interfaces[next].id);
    pause(); setPlatform(os);
  }
  interfaces.forEach((button, i) => {
    button.addEventListener('click', () => setInterface(i));
    button.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? 1 : 1 - i;
      setInterface(next); interfaces[next].focus();
    });
  });
  return { setPlatform };
}
