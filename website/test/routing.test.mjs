import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../worker/index.mjs';
const unusedAssets = { ASSETS: { fetch() { throw new Error('Unexpected asset lookup'); } } };
test('old website and deep links permanently redirect with their query intact', async () => {
  for (const path of ['/?os=linux', '/install.html?os=windows', '/assets/rtxforge.svg', '/rtxforge/install?os=linux']) {
    const response = await worker.fetch(new Request(`https://rtxforge.loew.fi${path}`), unusedAssets);
    assert.equal(response.status, 301);
    assert.equal(response.headers.get('location'), `https://loew.fi${path.startsWith('/rtxforge/') ? path : '/rtxforge' + path}`);
  }
});
test('primary landing URL gains a slash to keep relative image and guide links within the site', async () => {
  const response = await worker.fetch(new Request('https://loew.fi/rtxforge?os=linux'), unusedAssets);
  assert.equal(response.headers.get('location'), 'https://loew.fi/rtxforge/?os=linux');
});
test('primary assets retain the complete prefixed URL, method and conditional headers', async () => {
  const request = new Request('https://loew.fi/rtxforge/assets/screen.webp', { method: 'HEAD', headers: { 'If-None-Match': 'capture-hash' } });
  const response = await worker.fetch(request, { ASSETS: { fetch(received) {
    assert.equal(received, request);
    return new Response(null, { status: 304 });
  } } });
  assert.equal(response.status, 304);
});
test('other loew.fi paths and similarly named prefixes pass through to the existing origin', async t => {
  t.mock.method(globalThis, 'fetch', async request => new Response(`Existing origin: ${new URL(request.url).pathname}`));
  for (const path of ['/', '/rtxforge-other', '/about']) {
    const response = await worker.fetch(new Request(`https://loew.fi${path}`), unusedAssets);
    assert.equal(await response.text(), `Existing origin: ${path}`);
  }
});
