import test from 'node:test';
import assert from 'node:assert/strict';
import { CHANNELS, REPOSITORY, selectDownloads } from '../public/releases.mjs';
const asset = (name, tag = 'beta') => ({ name, state: 'uploaded', browser_download_url: `${REPOSITORY}/releases/download/${tag}/${name}` });
const release = assets => ({ tag_name: 'beta', draft: false, assets });
test('unpublished, draft and platform-missing releases never produce a download', () => {
  assert.equal(selectDownloads(null, 'linux'), null);
  assert.equal(selectDownloads({ ...release([asset('rtxForge.AppImage')]), draft: true }, 'linux'), null);
  assert.equal(selectDownloads(release([asset('rtxForge-Setup-x64.exe')]), 'linux'), null);
  assert.equal(selectDownloads(release([]), 'windows'), null);
});
test('Linux selects its current package and excludes rollback and ARM files', () => {
  const selected = selectDownloads(release([asset('rtxForge-arm64.AppImage'), asset('rtxForge-x64.AppImage.previous-old'), asset('rtxForge-x64.AppImage.sha256'), asset('rtxForge-x64.AppImage')]), 'linux');
  assert.equal(selected.primary.name, 'rtxForge-x64.AppImage');
});
test('a published Flatpak can become the Linux install option', () => {
  assert.equal(selectDownloads(release([asset('rtxForge.AppImage'), asset('rtxForge.flatpakref')]), 'linux').primary.format, 'Flatpak');
});
test('Windows picks the x64 installer and keeps portable separate from artwork', () => {
  const selected = selectDownloads(release([asset('rtxForge-Setup-arm64.exe'), asset('rtxForge-Steam-Artwork.zip'), asset('rtxForge-Setup-x64.exe'), asset('rtxForge-windows-x64.zip')]), 'windows');
  assert.equal(selected.primary.name, 'rtxForge-Setup-x64.exe');
  assert.equal(selected.portable.name, 'rtxForge-windows-x64.zip');
});
test('downloads from another repository or tag are refused', () => {
  const wrong = asset('rtxForge.AppImage'); wrong.browser_download_url = 'https://example.com/rtxForge.AppImage';
  assert.equal(selectDownloads(release([wrong, asset('rtxForge.AppImage', 'development')]), 'linux'), null);
});
test('Beta and moving Development have separate release tags', () => {
  assert.equal(CHANNELS.beta.tag, 'beta'); assert.equal(CHANNELS.development.tag, 'development');
  assert.notEqual(CHANNELS.beta.tag, CHANNELS.development.tag);
});
