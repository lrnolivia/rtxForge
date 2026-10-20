import { SCREENSHOTS } from './screenshots.mjs';

export function createGallery() {
  const byId = id => document.getElementById(id);
  const modes = [...document.querySelectorAll('[data-gallery-mode]')];
  const views = [...document.querySelectorAll('[data-gallery-view]')];
  const image = byId('gallery-image'), stage = byId('gallery-stage');
  let os = 'linux', mode = 'desktop', view = 'library', generation = 0;

  function message(title, copy) {
    image.hidden = true;
    byId('gallery-original').hidden = true;
    byId('gallery-message-title').textContent = title;
    byId('gallery-message-copy').textContent = copy;
    byId('gallery-message').hidden = false;
    stage.classList.add('is-pending');
    stage.setAttribute('aria-busy', 'false');
  }
  function render(announce = false) {
    const name = os === 'windows' ? 'Windows' : 'Linux';
    const modeName = mode === 'desktop' ? 'Desktop' : 'Game Mode';
    const capture = SCREENSHOTS[os]?.[`${mode}-${view}`];
    const title = `${name} · ${modeName} · ${capture?.detail || (view === 'library' ? 'Library' : 'Game details')}`;
    const current = ++generation;
    modes.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.galleryMode === mode)));
    views.forEach(button => {
      const selected = button.dataset.galleryView === view;
      button.setAttribute('aria-selected', String(selected)); button.tabIndex = selected ? 0 : -1;
    });
    byId('gallery-panel').setAttribute('aria-labelledby', `gallery-tab-${view}`);
    byId('gallery-title').textContent = title;
    byId('gallery-provenance').textContent = capture?.provenance || '';
    image.onload = null; image.onerror = null;
    image.hidden = true; byId('gallery-original').hidden = true;
    if (!capture) {
      image.removeAttribute('src'); image.alt = '';
      message(`${name} screenshots are on the way.`, 'Library and game details, on desktop and in Game Mode.');
    } else {
      stage.classList.remove('is-pending'); stage.setAttribute('aria-busy', 'true');
      byId('gallery-message').hidden = true;
      image.alt = capture.alt; image.width = capture.width; image.height = capture.height;
      const ready = () => {
        if (current !== generation) return;
        image.hidden = false; stage.setAttribute('aria-busy', 'false');
        byId('gallery-original').href = capture.src; byId('gallery-original').hidden = false;
      };
      image.onload = ready;
      image.onerror = () => {
        if (current === generation) message('This screenshot could not be loaded.', 'Choose another view or try again shortly.');
      };
      image.src = capture.src;
      if (image.complete && image.naturalWidth) ready();
    }
    byId('gallery-status').textContent = announce ? (capture ? `Showing ${title}. ${capture.provenance}.` : `${title}. Screenshot coming soon.`) : '';
  }
  modes.forEach(button => button.addEventListener('click', () => { mode = button.dataset.galleryMode; render(true); }));
  views.forEach(button => {
    button.addEventListener('click', () => { view = button.dataset.galleryView; render(true); });
    button.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const index = views.indexOf(button);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? views.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + views.length) % views.length;
      views[next].focus(); view = views[next].dataset.galleryView; render(true);
    });
  });
  return { setPlatform(platform) { os = platform; render(); } };
}
