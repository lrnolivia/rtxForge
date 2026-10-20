(() => {
  'use strict';
  const root = document.documentElement;
  const repo = 'https://github.com/lrnolivia/rtxForge';
  // Verified 2026-10-20 against public release assets and successful CI run.
  // Linux continuous: 0778d5e. Windows preview: 097bf32, expires 2026-11-01.
  const platforms = {
    linux: {
      name: 'Linux',
      copy: 'A native Linux app. Built with GTK and libadwaita.',
      meta: 'AppImage · x86_64 · Prerelease',
      download: `${repo}/releases/download/continuous/rtxForge-Bazzite-x86_64.AppImage`,
      downloadLabel: 'Download AppImage',
      install: 'Allow the AppImage to run in file properties, then open it. No extraction needed.',
      secondary: `${repo}/releases/tag/continuous`,
      secondaryLabel: 'Release details & checksum',
      note: 'A moving development preview. Updates are available in the app.',
      requirements: "Linux x86_64 with a working NVIDIA driver, Python 3, GTK4, libadwaita 1.7+, and PyGObject. The AppImage checks capabilities, so it isn't limited to Bazzite.",
      guide: `${repo}#your-first-game`,
      guideLabel: 'Read the getting started guide'
    },
    windows: {
      name: 'Windows',
      copy: 'A native Windows app. Built with WinUI 3.',
      meta: 'Installer or portable · x64 · Preview',
      download: `${repo}/actions/runs/39177946202/artifacts/12155775006`,
      downloadLabel: 'Get Windows installer',
      install: 'Download and extract the setup ZIP, then run the installer. The app includes its runtimes.',
      secondary: `${repo}/actions/runs/39177946202/artifacts/12155127522`,
      secondaryLabel: 'Get the portable preview',
      note: 'GitHub sign-in required. Unsigned preview; these downloads expire November 1, 2026.',
      requirements: 'Windows 10 version 2004 or later, x64, with a working NVIDIA driver. The installer and portable preview include the app runtimes. For portable, extract the entire ZIP and open rtxForge.exe.',
      guide: `${repo}/blob/main/windows/README.md#installer`,
      guideLabel: 'Read the Windows setup guide'
    }
  };
  const byId = id => document.getElementById(id);
  const tabs = [...document.querySelectorAll('[data-platform]')];
  const storage = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* Preference is optional. */ } }
  };

  function setPlatform(os, { updateUrl = false, announce = false } = {}) {
    if (!Object.hasOwn(platforms, os)) os = 'linux';
    const data = platforms[os];
    root.dataset.os = os;
    document.title = `rtxForge Beta for ${data.name}`;
    byId('platform-name').textContent = data.name;
    byId('platform-copy').textContent = data.copy;
    byId('package-meta').textContent = data.meta;
    byId('download-link').href = data.download;
    byId('download-label').textContent = data.downloadLabel;
    byId('install-copy').textContent = data.install;
    byId('secondary-link').href = data.secondary;
    byId('secondary-label').textContent = data.secondaryLabel;
    byId('channel-note').textContent = data.note;
    byId('requirements-copy').textContent = data.requirements;
    byId('guide-link').href = data.guide;
    byId('guide-link').replaceChildren(document.createTextNode(`${data.guideLabel} `));
    const arrow = document.createElement('span');
    arrow.setAttribute('aria-hidden', 'true');
    arrow.textContent = '↗';
    byId('guide-link').append(arrow);
    byId('platform-content').setAttribute('aria-labelledby', `tab-${os}`);
    for (const tab of tabs) {
      const selected = tab.dataset.platform === os;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    }
    const issue = new URL(`${repo}/issues/new`);
    issue.searchParams.set('title', `[${data.name}] `);
    issue.searchParams.set('body', `Platform: ${data.name}\nrtxForge build:\nGPU and driver:\nGame:\nProvider / profile:\n\nSteps to reproduce:\n\nExpected result:\n\nWhat happened:\n\nAttach a reviewed support report if available.\n`);
    byId('report-link').href = issue.href;
    byId('support-issue-link').href = issue.href;
    if (updateUrl) {
      const url = new URL(location.href);
      url.searchParams.set('os', os);
      history.replaceState({ os }, '', url);
      storage.set('rtxforge-platform', os);
    }
    if (announce) byId('platform-status').textContent = `Showing ${data.name} downloads, installation instructions, and requirements.`;
  }
  for (const tab of tabs) {
    tab.addEventListener('click', () => setPlatform(tab.dataset.platform, { updateUrl: true, announce: true }));
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const current = tabs.indexOf(tab);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      tabs[next].focus();
      setPlatform(tabs[next].dataset.platform, { updateUrl: true, announce: true });
    });
  }
  const colorPreference = matchMedia('(prefers-color-scheme: light)');
  function setTheme(theme, persist = false) {
    root.dataset.theme = theme;
    const next = theme === 'light' ? 'dark' : 'light';
    byId('theme-icon').src = next === 'light' ? 'assets/sun.svg' : 'assets/moon.svg';
    byId('theme-toggle').setAttribute('aria-label', `Switch to ${next} appearance`);
    byId('brand-mark').src = theme === 'light' ? 'assets/rtxforge-light.svg' : 'assets/rtxforge.svg';
    byId('hero-mark').src = byId('brand-mark').src;
    if (persist) storage.set('rtxforge-theme', theme);
  }
  const savedTheme = storage.get('rtxforge-theme');
  setTheme(['dark', 'light'].includes(savedTheme) ? savedTheme : colorPreference.matches ? 'light' : 'dark');
  byId('theme-toggle').addEventListener('click', () => setTheme(root.dataset.theme === 'light' ? 'dark' : 'light', true));
  colorPreference.addEventListener('change', event => {
    if (!storage.get('rtxforge-theme')) setTheme(event.matches ? 'light' : 'dark');
  });
  function platformFromLocation() {
    const requested = new URL(location.href).searchParams.get('os');
    const saved = storage.get('rtxforge-platform');
    return Object.hasOwn(platforms, requested) ? requested : Object.hasOwn(platforms, saved) ? saved : /Windows/i.test(navigator.userAgent) ? 'windows' : 'linux';
  }
  setPlatform(platformFromLocation());
  addEventListener('popstate', () => setPlatform(platformFromLocation()));
})();
