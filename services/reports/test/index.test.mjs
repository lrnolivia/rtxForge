import test from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPairSync, createVerify } from 'node:crypto';
import worker from '../src/index.mjs';
import { appJwt } from '../src/github.mjs';
import { sample } from './sample.mjs';

const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
const PKCS1 = privateKey.export({ type: 'pkcs1', format: 'pem' });
const PKCS8 = privateKey.export({ type: 'pkcs8', format: 'pem' });
const ZIP = Buffer.from([0x50, 0x4b, 0x05, 0x06, ...new Array(18).fill(0)]).toString('base64');

function bucket() {
  const objects = new Map();
  return { objects, async put(key, value, options) { objects.set(key, { value, options }); }, async delete(key) { objects.delete(key); } };
}

function environment(overrides = {}) {
  return {
    RTXFORGE_REPORTS_APP_ID: '12345', RTXFORGE_REPORTS_INSTALLATION_ID: '678', RTXFORGE_REPORTS_PRIVATE_KEY: PKCS1,
    LOGS: bucket(), LIMITER: { async limit() { return { success: true }; } }, GLOBAL_LIMITER: { async limit() { return { success: true }; } },
    ...overrides,
  };
}

function post(body, path = '/rtxforge/api/report') {
  return new Request('https://loew.fi' + path, { method: 'POST', headers: { 'cf-connecting-ip': '203.0.113.9' }, body: typeof body === 'string' ? body : JSON.stringify(body) });
}

function github(issueStatus = 201, human = true) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    if (String(url).includes('turnstile')) return Response.json({ success: human });
    if (String(url).endsWith('/access_tokens')) return Response.json({ token: 'installation-token' }, { status: 201 });
    if (String(url).endsWith('/repos/lrnolivia/rtxForge/issues')) {
      return issueStatus === 201 ? Response.json({ number: 321, html_url: 'https://github.com/lrnolivia/rtxForge/issues/321' }, { status: 201 }) : new Response('{}', { status: issueStatus });
    }
    return new Response('{}', { status: 404 });
  };
  return calls;
}

test('a report with logs files one issue and keeps the ZIP private', async () => {
  const calls = github();
  const env = environment();
  const response = await worker.fetch(post({ ...sample(), logs: ZIP }), env);
  assert.equal(response.status, 201);
  assert.deepEqual(await response.json(), { number: 321, url: 'https://github.com/lrnolivia/rtxForge/issues/321', logs: true });
  const [key] = [...env.LOGS.objects.keys()];
  assert.match(key, /^reports\/\d{4}-\d{2}-\d{2}\/r20261029T120000-abc123\.zip$/);
  const issue = JSON.parse(calls[1].init.body);
  assert.equal(issue.title, '[Beta report] Control · Linux');
  assert.deepEqual(issue.labels, ['beta-report', 'from-app']);
  assert.ok(!issue.body.includes(key), 'the storage key is not published');
  assert.equal(calls[1].init.headers.authorization, 'Bearer installation-token');
});

test('the app token is a valid RS256 JWT from a PKCS#1 or PKCS#8 key', async () => {
  for (const key of [PKCS1, PKCS8, PKCS1.replace(/\n/g, '\\n')]) {
    const jwt = await appJwt({ RTXFORGE_REPORTS_APP_ID: '12345', RTXFORGE_REPORTS_PRIVATE_KEY: key }, 1_800_000_000_000);
    const [header, payload, signature] = jwt.split('.');
    const verify = createVerify('RSA-SHA256');
    verify.update(`${header}.${payload}`);
    assert.ok(verify.verify(publicKey, Buffer.from(signature, 'base64url')));
    const claims = JSON.parse(Buffer.from(payload, 'base64url'));
    assert.deepEqual(claims, { iat: 1_799_999_940, exp: 1_800_000_540, iss: '12345' });
  }
});

test('bad input is refused before anything is stored or sent', async () => {
  const calls = github();
  const env = environment();
  assert.equal((await worker.fetch(post(''), env)).status, 400);
  assert.equal((await worker.fetch(post({}), env)).status, 400);
  assert.equal((await worker.fetch(post({ ...sample(), logs: btoa('not a zip') }), env)).status, 400);
  assert.equal((await worker.fetch(new Request('https://loew.fi/rtxforge/api/report'), env)).status, 405);
  assert.equal((await worker.fetch(post(sample(), '/rtxforge/api/other'), env)).status, 404);
  assert.equal(calls.length, 0);
  assert.equal(env.LOGS.objects.size, 0);
});

test('without secrets the service says so instead of failing', async () => {
  const calls = github();
  const response = await worker.fetch(post(sample()), environment({ RTXFORGE_REPORTS_PRIVATE_KEY: '' }));
  assert.equal(response.status, 503);
  assert.match((await response.json()).error, /can’t be sent yet/);
  assert.equal(calls.length, 0);
});

test('rate limits answer 429', async () => {
  github();
  const response = await worker.fetch(post(sample()), environment({ LIMITER: { async limit() { return { success: false }; } } }));
  assert.equal(response.status, 429);
});

test('website reports need a passed Turnstile check and are labeled from-web', async () => {
  const web = { ...sample(), source: 'web' };
  github(201, false);
  assert.equal((await worker.fetch(post({ ...web, turnstile: 'token' }), environment({ TURNSTILE_SECRET: 's' }))).status, 403);
  assert.equal((await worker.fetch(post(web), environment({ TURNSTILE_SECRET: 's' }))).status, 403);
  const missing = await worker.fetch(post({ ...web, turnstile: 'token' }), environment());
  assert.equal(missing.status, 503);
  assert.ok(!(await missing.json()).error.includes('this computer'), 'the website keeps no copy');
  const calls = github(201, true);
  const response = await worker.fetch(post({ ...web, turnstile: 'token' }), environment({ TURNSTILE_SECRET: 's' }));
  assert.equal(response.status, 201);
  const issue = JSON.parse(calls.find((c) => c.url.endsWith('/issues')).init.body);
  assert.deepEqual(issue.labels, ['beta-report', 'from-web']);
  assert.ok(issue.body.includes('_Sent from the rtxForge website._'));
  assert.equal((await worker.fetch(post({ ...sample(), source: 'email' }), environment())).status, 400);
});

test('only the site gets CORS headers, including on the preflight', async () => {
  const preflight = (origin) => worker.fetch(new Request('https://loew.fi/rtxforge/api/report', { method: 'OPTIONS', headers: { origin } }), environment());
  const allowed = await preflight('https://rtxforge.loew.fi');
  assert.equal(allowed.status, 204);
  assert.equal(allowed.headers.get('access-control-allow-origin'), 'https://rtxforge.loew.fi');
  assert.equal((await preflight('https://example.com')).headers.get('access-control-allow-origin'), null);
});

test('a GitHub failure removes the stored logs and returns a plain error', async () => {
  github(500);
  const env = environment();
  const response = await worker.fetch(post({ ...sample(), logs: ZIP }), env);
  assert.equal(response.status, 502);
  assert.equal(env.LOGS.objects.size, 0);
  assert.match((await response.json()).error, /didn’t accept the report/);
});
