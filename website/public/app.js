import { REPOSITORY as repo, CHANNELS, selectDownloads } from './releases.mjs';

const root = document.documentElement;
const byId = id => document.getElementById(id);
const tabs = [...document.querySelectorAll('[data-platform]')];
const storage = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* Preferences and cache are optional. */ } }
};
const platforms = {
  linux: {
    name: 'Linux', copy: 'A native Linux app. Built with GTK and libadwaita.', arch: 'x86_64',
    requirements: 'Linux x86_64 with a working NVIDIA driver. Package-specific requirements are listed with each release.',
    guide: `${repo}#your-first-game`, guideLabel: 'Read the getting started guide'
  },
  windows: {
    name: 'Windows', copy: 'A native Windows app. Built with WinUI 3.', arch: 'x64',
    requirements: 'Windows 10 version 2004 or later, x64, with a working NVIDIA driver. Packaged builds include the app runtimes.',
    guide: `${repo}/blob/main/windows/README.md#installer`, guideLabel: 'Read the Windows setup guide'
  }
};
const releases = { beta: { status: 'loading' }, development: { status: 'loading' } };
function linkState(element, url) {
  element.classList.toggle('is-unavailable', !url);
  element.setAttribute('aria-disabled', String(!url)); element.tabIndex = url ? 0 : -1;
  if (url) element.href = url;
  else element.removeAttribute('href');
}
function installInstructions(format) {
  return {
    AppImage: 'Allow the AppImage to run in file properties, then open it. AppImage builds need host Python 3, GTK4, libadwaita 1.7+, and PyGObject.',
    Flatpak: 'Open the Flatpak reference with your software installer and follow its prompts.',
    'Flatpak bundle': 'Open the Flatpak bundle with your software installer and follow its prompts.',
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
  linkState(byId('download-link'), betaFiles?.primary.url);
  byId('download-label').textContent = betaFiles ? 'Download Beta' : beta.status === 'loading' ? 'Checking Beta downloads…' : beta.status === 'error' ? 'Beta downloads unavailable' : 'Beta coming soon';
  byId('package-meta').textContent = betaFiles ? `Beta · ${betaFiles.primary.format} · ${platform.arch}` : `Beta · ${platform.name} ${platform.arch}`;
  byId('install-copy').textContent = betaFiles ? installInstructions(betaFiles.primary.format) : beta.status === 'loading' ? 'Checking the published Beta release.' : beta.status === 'error' ? 'Release information could not be loaded. You can check GitHub in the footer.' : `The ${platform.name} Beta download will appear here when it is published.`;
  linkState(byId('secondary-link'), devFiles?.primary.url);
  byId('secondary-label').textContent = devFiles ? 'Download Development' : dev.status === 'loading' ? 'Checking Development…' : dev.status === 'error' ? 'Development unavailable' : 'Development coming soon';
  byId('channel-note').textContent = 'Development follows the latest changes and may be less stable than Beta.';
  const portable = betaFiles?.portable;
  byId('portable-link').hidden = !portable;
  linkState(byId('portable-link'), portable?.url);
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
  const data = platforms[os]; root.dataset.os = os;
  document.title = `rtxForge Beta for ${data.name}`;
  byId('platform-name').textContent = data.name; byId('platform-copy').textContent = data.copy;
  byId('guide-link').href = data.guide;
  byId('guide-link').replaceChildren(document.createTextNode(`${data.guideLabel} `));
  const arrow = document.createElement('span'); arrow.setAttribute('aria-hidden', 'true'); arrow.textContent = '↗'; byId('guide-link').append(arrow);
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
  if (announce) byId('platform-status').textContent = `Showing ${data.name} downloads, installation instructions, and requirements.`;
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
const colorPreference = matchMedia('(prefers-color-scheme: light)');
function setTheme(theme, persist = false) {
  root.dataset.theme = theme; const next = theme === 'light' ? 'dark' : 'light';
  byId('theme-icon').src = next === 'light' ? 'assets/sun.svg' : 'assets/moon.svg';
  byId('theme-toggle').setAttribute('aria-label', `Switch to ${next} appearance`);
  byId('brand-mark').src = 'assets/rtxforge.svg';
  if (persist) storage.set('rtxforge-theme', theme);
}
const savedTheme = storage.get('rtxforge-theme');
setTheme(['dark', 'light'].includes(savedTheme) ? savedTheme : colorPreference.matches ? 'light' : 'dark');
byId('theme-toggle').addEventListener('click', () => setTheme(root.dataset.theme === 'light' ? 'dark' : 'light', true));
colorPreference.addEventListener('change', event => {
  if (!storage.get('rtxforge-theme')) setTheme(event.matches ? 'light' : 'dark');
});
function platformFromLocation() {
  const requested = new URL(location.href).searchParams.get('os'), saved = storage.get('rtxforge-platform');
  return Object.hasOwn(platforms, requested) ? requested : Object.hasOwn(platforms, saved) ? saved : /Windows/i.test(navigator.userAgent) ? 'windows' : 'linux';
}
setPlatform(platformFromLocation());
addEventListener('popstate', () => setPlatform(platformFromLocation()));
await Promise.all(Object.keys(CHANNELS).map(async channel => { releases[channel] = await loadRelease(channel); renderDownloads(); }));
