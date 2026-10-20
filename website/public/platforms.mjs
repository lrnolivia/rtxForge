export const platforms = Object.freeze({
  linux: {
    name: 'Linux', copy: 'A native app for your Linux desktop.', arch: 'x86_64',
    requirements: 'Linux x86_64 with a working NVIDIA driver. Package-specific requirements are listed with each release.',
    guide: 'install.html?os=linux', guideLabel: 'Read the installation guide'
  },
  windows: {
    name: 'Windows', copy: 'A native app for your Windows desktop.', arch: 'x64',
    requirements: 'Windows 10 version 2004 or later, x64, with a working NVIDIA driver. Packaged builds include the app runtimes.',
    guide: 'install.html?os=windows', guideLabel: 'Read the installation guide'
  }
});

export const storage = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* Preferences and cache are optional. */ } }
};

export function platformFromLocation() {
  const requested = new URL(location.href).searchParams.get('os'), saved = storage.get('rtxforge-platform');
  return Object.hasOwn(platforms, requested) ? requested : Object.hasOwn(platforms, saved) ? saved : /Windows/i.test(navigator.userAgent) ? 'windows' : 'linux';
}
