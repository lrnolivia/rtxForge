import { platforms, platformFromLocation } from './platforms.mjs';
import { initTheme } from './theme.mjs';
import { initSiteControls } from './site-controls.mjs';

initTheme();
function revealHelp() {
  let target;
  try { target = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch { return; }
  if (!target) return;
  for (let detail = target.closest('details'); detail; detail = detail.parentElement?.closest('details')) detail.open = true;
  if (!target.closest('[hidden]')) target.scrollIntoView({ block: 'start' });
}
function setPlatform(os) {
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
  if (location.hash) revealHelp();
}
const site = initSiteControls(setPlatform);
site.select(platformFromLocation());
addEventListener('popstate', () => site.select(platformFromLocation()));
addEventListener('hashchange', revealHelp);
