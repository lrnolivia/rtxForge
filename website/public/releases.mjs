export const REPOSITORY = 'https://github.com/lrnolivia/rtxForge';
export const CHANNELS = Object.freeze({
  beta: { tag: 'beta', label: 'Beta' },
  development: { tag: 'development', label: 'Development' }
});

// Publication contract: plain release titles, separate channel tags.
export function selectDownloads(release, platform) {
  if (!release || release.draft || !Array.isArray(release.assets)) return null;
  const prefix = `${REPOSITORY}/releases/download/${encodeURIComponent(release.tag_name)}/`;
  const assets = release.assets.filter(asset =>
    typeof asset.name === 'string' && /rtxforge/i.test(asset.name) &&
    !/\.previous|arm64|aarch64|\.sha256$|\.sig$/i.test(asset.name) &&
    (!asset.state || asset.state === 'uploaded') &&
    typeof asset.browser_download_url === 'string' && asset.browser_download_url.startsWith(prefix)
  );
  const first = pattern => assets.find(asset => pattern.test(asset.name));
  const file = (asset, format) => asset ? { url: asset.browser_download_url, name: asset.name, format } : null;
  if (platform === 'linux') {
    const primary = file(first(/\.flatpakref$/i), 'Flatpak') || file(first(/\.flatpak$/i), 'Flatpak bundle') || file(first(/\.AppImage$/i), 'AppImage');
    return primary ? { primary, portable: null } : null;
  }
  if (platform !== 'windows') return null;
  const setup = first(/(?:setup|install).*\.exe$/i);
  const setupZip = first(/(?:setup|install).*?(?:windows|win).*\.zip$/i);
  const portableAsset = assets.find(asset => /(?:windows|win).*\.zip$/i.test(asset.name) && !/(?:setup|install)/i.test(asset.name));
  const portable = file(portableAsset, 'Portable');
  const primary = file(setup, 'Installer') || file(setupZip, 'Installer ZIP') || portable;
  return primary ? { primary, portable: portable && portable !== primary ? portable : null } : null;
}
