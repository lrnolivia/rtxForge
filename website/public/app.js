import { CHANNELS, selectDownloads } from './releases.mjs';
import { setFeaturePlatform } from './features.js';
import { platforms, storage } from './platforms.mjs';
import { initTheme } from './theme.mjs';
import { initSiteControls } from './site-controls.mjs';

const root = document.documentElement;
const byId = id => document.getElementById(id);
initTheme();
new MutationObserver(() => {
  setFeaturePlatform(root.dataset.os);
}).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
function platformForPage() {
  const requested = new URL(location.href).searchParams.get('os'), saved = storage.get('rtxforge-platform');
  return Object.hasOwn(platforms, requested) ? requested : Object.hasOwn(platforms, saved) ? saved : 'linux';
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
    AppImage: 'Allow the file to run, then open it. Check the setup guide for system dependencies.',
    Flatpak: 'Start here on SteamOS. Open it with your software installer.',
    'Flatpak bundle': 'Start here on SteamOS. Open it in Discover or GNOME Software.',
    Installer: 'Run the installer, then open rtxForge from the Start menu.',
    'Installer ZIP': 'Extract the ZIP, then run the installer.',
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
  byId('download-label').textContent = betaFiles ? (os === 'linux' ? `Download ${betaFiles.primary.format.startsWith('Flatpak') ? 'Flatpak' : 'AppImage'}` : 'Download Beta 1') : beta.status === 'loading' ? 'Checking Beta downloads…' : beta.status === 'error' ? 'Beta downloads unavailable' : 'Beta coming soon';
  byId('package-meta').textContent = betaFiles ? `Beta 1 · ${os === 'linux' && betaFiles.alternative ? 'Flatpak & AppImage' : betaFiles.primary.format} · ${platform.arch}` : `Beta · ${platform.name} ${platform.arch}`;
  byId('install-copy').textContent = betaFiles ? installInstructions(betaFiles.primary.format) : beta.status === 'loading' ? 'Finding your download…' : beta.status === 'error' ? 'We couldn’t load the downloads. Try again or open GitHub Releases.' : `The ${platform.name} Beta will appear here when it’s ready.`;
  linkState(byId('secondary-link'), devFiles?.primary.url);
  byId('secondary-label').textContent = devFiles ? 'Download Development' : dev.status === 'loading' ? 'Checking Development…' : dev.status === 'error' ? 'Development unavailable' : 'Development coming soon';
  byId('channel-note').textContent = 'Newer changes. Less tested. Choose Beta if you’re unsure.';
  byId('release-actions').hidden = Boolean(betaFiles && dev.status !== 'error' && !retryingReleases);
  byId('release-retry').hidden = !retryingReleases && ![beta, dev].some(release => release.status === 'error');
  byId('release-retry').setAttribute('aria-disabled', String(retryingReleases));
  byId('release-retry').textContent = retryingReleases ? 'Checking…' : 'Try again';
  // Windows: the portable ZIP. Linux: the AppImage beside a Flatpak.
  const extra = betaFiles?.alternative || betaFiles?.portable;
  byId('portable-link').hidden = !extra;
  linkState(byId('portable-link'), extra?.url);
  byId('portable-link').firstChild.nodeValue = extra && extra === betaFiles.alternative ? 'Download AppImage ' : 'Portable Beta ';
  byId('portable-link').classList.toggle('download-button', os === 'linux');
  byId('portable-link').classList.toggle('download-alternative', os === 'linux');
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
function setPlatform(os) {
  if (!Object.hasOwn(platforms, os)) os = 'linux';
  const data = platforms[os]; root.dataset.os = os; setFeaturePlatform(os);
  document.title = `rtxForge Beta 1 for ${data.name}`;
  byId('platform-name').textContent = data.name; byId('platform-copy').textContent = data.copy;
  byId('guide-link').href = data.guide;
  byId('footer-guide-link').href = data.guide;
  byId('faq-guide-link').href = data.guide;
  byId('platform-content').setAttribute('aria-labelledby', `tab-${os}`);
  for (const link of document.querySelectorAll('[data-report-link]')) link.href = `report.html?os=${os}`;
  renderDownloads();
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
const site = initSiteControls(setPlatform);
site.select(platformForPage());
addEventListener('popstate', () => site.select(platformForPage()));
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
