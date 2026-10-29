export const platforms = Object.freeze({
  linux: {
    name: 'Linux', copy: 'For Linux desktops and Game Mode.', arch: 'x86_64',
    requirements: 'Linux x86_64 and a working NVIDIA driver. Check the release notes for your package.',
    guide: 'install.html?os=linux', guideLabel: 'Read the installation guide'
  },
  windows: {
    name: 'Windows', copy: 'For your Windows games.', arch: 'x64',
    requirements: 'Windows 10 (version 2004 or later) or Windows 11, x64, and a working NVIDIA driver.',
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
