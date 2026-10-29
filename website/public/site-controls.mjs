import { platforms, storage } from './platforms.mjs';

// Shared header behavior; each page keeps its own content and form handling.
export function initSiteControls(onChange) {
  const tabs = [...document.querySelectorAll('[data-platform]')];
  function select(os, { updateUrl = false, announce = false, notify = true } = {}) {
    if (!Object.hasOwn(platforms, os)) os = '';
    document.documentElement.dataset.os = os || 'linux';
    for (const [index, tab] of tabs.entries()) {
      const selected = tab.dataset.platform === os;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected || (!os && index === 0) ? 0 : -1;
    }
    for (const link of document.querySelectorAll('[data-site-page]')) {
      const url = new URL(link.dataset.sitePage, location.href);
      if (os) url.searchParams.set('os', os);
      link.href = url.href;
    }
    const panel = document.getElementById('platform-content');
    if (panel) {
      if (os) panel.setAttribute('aria-labelledby', `tab-${os}`);
      else panel.removeAttribute('aria-labelledby');
    }
    if (updateUrl) {
      const url = new URL(location.href);
      if (os) url.searchParams.set('os', os); else url.searchParams.delete('os');
      history.replaceState({ os }, '', url);
      if (os) storage.set('rtxforge-platform', os);
    }
    if (announce) document.getElementById('platform-status').textContent = `Showing ${platforms[os].name} options.`;
    if (notify) onChange(os);
  }
  for (const tab of tabs) {
    tab.addEventListener('click', () => select(tab.dataset.platform, { updateUrl: true, announce: true }));
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const current = tabs.indexOf(tab);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      tabs[next].focus();
      select(tabs[next].dataset.platform, { updateUrl: true, announce: true });
    });
  }
  return { select };
}
