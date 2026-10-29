import { REPOSITORY as repo, CHANNELS, selectDownloads } from './releases.mjs';
import { setFeaturePlatform } from './features.js';
import { platforms, storage } from './platforms.mjs';
import { initTheme } from './theme.mjs';

const root = document.documentElement;
const byId = id => document.getElementById(id);
const tabs = [...document.querySelectorAll('[data-platform]')];
initTheme();
new MutationObserver(() => {
  setFeaturePlatform(root.dataset.os);
}).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
function platformForPage() {
  const requested = new URL(location.href).searchParams.get('os'), saved = storage.get('rtxforge-platform');
  return Object.hasOwn(platforms, requested) ? requested : Object.hasOwn(platforms, saved) ? saved : 'windows';
}
const releases = { beta: { status: 'loading' }, development: { status: 'loading' } };
let retryingReleases = false;
function linkState(element, url) {
  element.classList.toggle('is-unavailable', !url);
  element.setAttribute('aria-disabled', String(!url)); element.tabIndex = url ? 0 : -1;
  if (url) element.href = url;
  else element.removeAttribute('href');
}
function installInstructions(format) {
  return {
    AppImage: 'Allow the AppImage to run in file properties, then open it. AppImage builds need host Python 3, GTK4, libadwaita 1.7+, and PyGObject.',
    Flatpak: 'Recommended for SteamOS and any system without GTK4 and libadwaita. Open the Flatpak reference with your software installer and follow its prompts.',
    'Flatpak bundle': 'Recommended for SteamOS and any system without GTK4 and libadwaita. Open the bundle with Discover or GNOME Software. On Bazzite and CachyOS, the AppImage also works.',
    Installer: 'Run the installer. The app includes its runtimes.',
    'Installer ZIP': 'Extract the setup ZIP, then run the installer. The app includes its runtimes.',
    Portable: 'Extract the entire ZIP and open rtxForge.exe. Keep its companion files together.'
  }[format];
}
function renderDownloads() {
  const os = root.dataset.os;
  const platform = platforms[os];
  const beta = releases.beta, dev = releases.development;
  const betaFiles = selectDownloads(beta.release, os), devFiles = selectDownloads(dev.release, os);
  byId('beta-launch').hidden = Boolean(betaFiles);
  linkState(byId('download-link'), betaFiles?.primary.url);
  byId('download-label').textContent = betaFiles ? 'Download 1.0 Beta' : beta.status === 'loading' ? 'Checking Beta downloads…' : beta.status === 'error' ? 'Beta downloads unavailable' : 'Beta coming soon';
  byId('package-meta').textContent = betaFiles ? `1.0 Beta · ${betaFiles.primary.format} · ${platform.arch}` : `Beta · ${platform.name} ${platform.arch}`;
  byId('install-copy').textContent = betaFiles ? installInstructions(betaFiles.primary.format) : beta.status === 'loading' ? 'Checking the published Beta release.' : beta.status === 'error' ? 'Release information could not be loaded. Try again or check the releases on GitHub.' : `The ${platform.name} Beta download will appear here when it is published.`;
  linkState(byId('secondary-link'), devFiles?.primary.url);
  byId('secondary-label').textContent = devFiles ? 'Download Development' : dev.status === 'loading' ? 'Checking Development…' : dev.status === 'error' ? 'Development unavailable' : 'Development coming soon';
  byId('channel-note').textContent = 'Development follows the latest changes and may be less stable than Beta.';
  byId('release-actions').hidden = Boolean(betaFiles && dev.status !== 'error' && !retryingReleases);
  byId('release-retry').hidden = !retryingReleases && ![beta, dev].some(release => release.status === 'error');
  byId('release-retry').setAttribute('aria-disabled', String(retryingReleases));
  byId('release-retry').textContent = retryingReleases ? 'Checking…' : 'Try again';
  // Windows: the portable ZIP. Linux: the AppImage beside a Flatpak.
  const extra = betaFiles?.alternative || betaFiles?.portable;
  byId('portable-link').hidden = !extra;
  linkState(byId('portable-link'), extra?.url);
  byId('portable-link').firstChild.nodeValue = extra && extra === betaFiles.alternative ? 'AppImage for Bazzite and CachyOS ' : 'Portable Beta ';
  byId('requirements-copy').textContent = platform.requirements;
}
async function loadRelease(channel) {
  const { tag } = CHANNELS[channel], cacheKey = `rtxforge-release-v1-${tag}`;
  try {
    const cached = JSON.parse(storage.get(cacheKey) || 'null');
    if (cached && cached.expires > Date.now()) return cached.value;
  } catch { /* A broken cache falls through to the public API. */ }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 7000);
  try {
    const response = await fetch(`https://api.github.com/repos/lrnolivia/rtxForge/releases/tags/${encodeURIComponent(tag)}`, {
      headers: { Accept: 'application/vnd.github+json' }, signal: controller.signal
    });
    if (response.status === 404) {
      const value = { status: 'unpublished' };
      storage.set(cacheKey, JSON.stringify({ expires: Date.now() + 60000, value })); return value;
    }
    if (!response.ok) throw new Error(`Release lookup returned ${response.status}`);
    const release = await response.json();
    if (release.tag_name !== tag || release.draft) return { status: 'unpublished' };
    const value = { status: 'published', release };
    storage.set(cacheKey, JSON.stringify({ expires: Date.now() + 180000, value })); return value;
  } catch { return { status: 'error' }; }
  finally { clearTimeout(timeout); }
}
function setPlatform(os, { updateUrl = false, announce = false } = {}) {
  if (!Object.hasOwn(platforms, os)) os = 'linux';
  const data = platforms[os]; root.dataset.os = os; setFeaturePlatform(os);
  document.title = `rtxForge 1.0 Beta for ${data.name}`;
  byId('platform-name').textContent = data.name; byId('platform-copy').textContent = data.copy;
  byId('guide-link').href = data.guide;
  byId('guide-link').textContent = data.guideLabel;
  byId('footer-guide-link').href = data.guide;
  byId('faq-guide-link').href = data.guide;
  byId('platform-content').setAttribute('aria-labelledby', `tab-${os}`);
  for (const tab of tabs) {
    const selected = tab.dataset.platform === os;
    tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
  }
  const issue = new URL(`${repo}/issues/new`);
  issue.searchParams.set('title', `[${data.name}] `);
  issue.searchParams.set('body', `Platform: ${data.name}\nrtxForge build:\nGPU and driver:\nGame:\nProvider / profile:\n\nSteps to reproduce:\n\nExpected result:\n\nWhat happened:\n\nAttach a reviewed support report if available.\n`);
  byId('report-link').href = issue.href; byId('support-issue-link').href = issue.href; renderDownloads();
  if (updateUrl) {
    const url = new URL(location.href); url.searchParams.set('os', os);
    history.replaceState({ os }, '', url); storage.set('rtxforge-platform', os);
  }
  if (announce) byId('platform-status').textContent = `Showing ${data.name} screenshots, downloads, installation instructions, and requirements.`;
}
for (const tab of tabs) {
  tab.addEventListener('click', () => setPlatform(tab.dataset.platform, { updateUrl: true, announce: true }));
  tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault(); const current = tabs.indexOf(tab);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    tabs[next].focus(); setPlatform(tabs[next].dataset.platform, { updateUrl: true, announce: true });
  });
}
byId('requirements-link').addEventListener('click', event => {
  event.preventDefault();
  const requirements = byId('requirements-details');
  requirements.open = true;
  history.replaceState(history.state, '', byId('requirements-link').href);
  requirements.scrollIntoView({ block: 'start' });
  requirements.querySelector('summary').focus({ preventScroll: true });
});
byId('release-retry').addEventListener('click', () => {
  if (!retryingReleases) refreshReleases({ retry: true });
});
setPlatform(platformForPage());
addEventListener('popstate', () => setPlatform(platformForPage()));
async function refreshReleases({ retry = false } = {}) {
  retryingReleases = retry;
  const channels = Object.keys(CHANNELS).filter(channel => releases[channel].status !== 'published');
  for (const channel of channels) releases[channel] = { status: 'loading' };
  renderDownloads();
  await Promise.all(channels.map(async channel => {
    releases[channel] = await loadRelease(channel);
    renderDownloads();
  }));
  const recoverFocus = retry && document.activeElement === byId('release-retry');
  retryingReleases = false;
  renderDownloads();
  if (recoverFocus && byId('release-retry').hidden) {
    byId(byId('download-link').hasAttribute('href') ? 'download-link' : 'release-github').focus();
  }
}
await refreshReleases();
