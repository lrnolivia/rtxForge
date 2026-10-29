import { platforms, storage, platformFromLocation } from './platforms.mjs';
import { initTheme } from './theme.mjs';

initTheme();
const tabs = [...document.querySelectorAll('[data-platform]')];
function setPlatform(os, { updateUrl = false, announce = false } = {}) {
  if (!Object.hasOwn(platforms, os)) os = 'linux';
  const platform = platforms[os];
  document.documentElement.dataset.os = os;
  document.title = `Install rtxForge for ${platform.name}`;
  document.getElementById('guide-platform-name').textContent = platform.name;
  document.getElementById('guide-requirements').textContent = platform.requirements;
  document.getElementById('platform-content').setAttribute('aria-labelledby', `tab-${os}`);
  for (const section of document.querySelectorAll('[data-guide-platform]')) section.hidden = section.dataset.guidePlatform !== os;
  for (const link of document.querySelectorAll('[data-downloads-link]')) link.href = `./?os=${os}#downloads`;
  for (const link of document.querySelectorAll('[data-home-link]')) link.href = `./?os=${os}`;
  for (const link of document.querySelectorAll('[data-report-link]')) link.href = `report.html?os=${os}`;
  for (const tab of tabs) {
    const selected = tab.dataset.platform === os;
    tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
  }
  if (updateUrl) {
    const url = new URL(location.href); url.searchParams.set('os', os);
    history.replaceState({ os }, '', url); storage.set('rtxforge-platform', os);
  }
  if (announce) document.getElementById('platform-status').textContent = `Showing the ${platform.name} installation guide.`;
}
for (const tab of tabs) {
  tab.addEventListener('click', () => setPlatform(tab.dataset.platform, { updateUrl: true, announce: true }));
  tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const current = tabs.indexOf(tab);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    tabs[next].focus(); setPlatform(tabs[next].dataset.platform, { updateUrl: true, announce: true });
  });
}
setPlatform(platformFromLocation());
addEventListener('popstate', () => setPlatform(platformFromLocation()));
