import { storage } from './platforms.mjs';

export function initTheme() {
  const root = document.documentElement;
  const colorPreference = matchMedia('(prefers-color-scheme: light)');
  function setTheme(theme, persist = false) {
    root.dataset.theme = theme;
    const next = theme === 'light' ? 'dark' : 'light';
    document.getElementById('theme-icon').src = next === 'light' ? 'assets/sun.svg' : 'assets/moon.svg';
    document.getElementById('theme-toggle').setAttribute('aria-label', `Switch to ${next} appearance`);
    if (persist) storage.set('rtxforge-theme', theme);
  }
  const saved = storage.get('rtxforge-theme');
  setTheme(['dark', 'light'].includes(saved) ? saved : colorPreference.matches ? 'light' : 'dark');
  document.getElementById('theme-toggle').addEventListener('click', () => setTheme(root.dataset.theme === 'light' ? 'dark' : 'light', true));
  colorPreference.addEventListener('change', event => {
    if (!storage.get('rtxforge-theme')) setTheme(event.matches ? 'light' : 'dark');
  });
}
