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
test('the 1.0 Beta offers the Flatpak first and the AppImage beside it', () => {
  const selected = selectDownloads(release([
    asset('rtxForge-1.0.0-beta.3-x86_64.AppImage'), asset('rtxForge-1.0.0-beta.3-x86_64.AppImage.sha256'),
    asset('rtxForge-1.0.0-beta.3-x86_64.flatpak.sha256'), asset('rtxForge-1.0.0-beta.3-x86_64.flatpak'),
    asset('rtxForge-1.0.0-beta.2-x86_64.flatpak.previous-bbbbbbbbbbbb'), asset('rtxforge-beta-linux.json')
  ]), 'linux');
  assert.equal(selected.primary.name, 'rtxForge-1.0.0-beta.3-x86_64.flatpak');
  assert.equal(selected.primary.format, 'Flatpak bundle');
  assert.equal(selected.alternative.name, 'rtxForge-1.0.0-beta.3-x86_64.AppImage');
  assert.equal(selected.alternative.format, 'AppImage');
  assert.equal(selected.portable, null);
});
test('an AppImage-only Linux release has no alternative', () => {
  const selected = selectDownloads(release([asset('rtxForge-1.0.0-beta.2-x86_64.AppImage')]), 'linux');
  assert.equal(selected.primary.format, 'AppImage');
  assert.equal(selected.alternative, null);
});
test('Windows picks the x64 installer and keeps portable separate from artwork', () => {
  const selected = selectDownloads(release([asset('rtxForge-Setup-arm64.exe'), asset('rtxForge-Steam-Artwork.zip'), asset('rtxForge-Setup-x64.exe'), asset('rtxForge-windows-x64.zip')]), 'windows');
  assert.equal(selected.primary.name, 'rtxForge-Setup-x64.exe');
  assert.equal(selected.portable.name, 'rtxForge-windows-x64.zip');
  assert.equal(selected.alternative, null);
});
test('downloads from another repository or tag are refused', () => {
  const wrong = asset('rtxForge.AppImage'); wrong.browser_download_url = 'https://example.com/rtxForge.AppImage';
  assert.equal(selectDownloads(release([wrong, asset('rtxForge.AppImage', 'development')]), 'linux'), null);
});
test('Beta and moving Development have separate release tags', () => {
  assert.equal(CHANNELS.beta.tag, 'beta'); assert.equal(CHANNELS.development.tag, 'development');
  assert.notEqual(CHANNELS.beta.tag, CHANNELS.development.tag);
});

test('1.0 Beta exposes its installer and portable ZIP with checksums excluded', () => {
  const selected = selectDownloads(release([
    asset('rtxForge-Setup-1.0.0-beta.1-arm64.exe'),
    asset('rtxForge-Setup-1.0.0-beta.1-x64.exe.sha256'),
    asset('rtxForge-Setup-1.0.0-beta.1-x64.exe'),
    asset('rtxForge-windows-1.0.0-beta.1-x64.zip.sha256'),
    asset('rtxForge-windows-1.0.0-beta.1-x64.zip')
  ]), 'windows');
  assert.equal(selected.primary.name, 'rtxForge-Setup-1.0.0-beta.1-x64.exe');
  assert.equal(selected.portable.name, 'rtxForge-windows-1.0.0-beta.1-x64.zip');
});
