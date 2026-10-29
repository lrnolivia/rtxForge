// rtxforge-reports: POST /rtxforge/api/report files one report from the app or the
// website as a GitHub issue. The redacted log ZIP goes to a private R2 bucket; only the
// report text is public. Website reports also pass a Cloudflare Turnstile check.
import { validate, issueTitle, issueBody, issueLabels, ZIP_LIMIT } from './report.mjs';
import { configured, installationToken, createIssue } from './github.mjs';

const PATH = '/rtxforge/api/report';
// Base64 grows the ZIP by a third; the text fields add little.
const BODY_LIMIT = Math.ceil(ZIP_LIMIT * 4 / 3) + 256 * 1024;
// The site is served at both addresses; the app sends no Origin at all.
const ORIGINS = ['https://loew.fi', 'https://rtxforge.loew.fi'];
const TURNSTILE = 'https://challenges.cloudflare.com/turnstile/v0/siteverify';

function cors(request) {
  const origin = request.headers.get('origin');
  return ORIGINS.includes(origin)
    ? { 'access-control-allow-origin': origin, 'access-control-allow-methods': 'POST', 'access-control-allow-headers': 'content-type', vary: 'origin' }
    : {};
}

function reply(request, status, data) {
  return new Response(JSON.stringify(data), {
    status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...cors(request) },
  });
}

function zipBytes(encoded) {
  if (typeof encoded !== 'string') throw new RangeError('The logs aren’t a ZIP file.');
  let bytes;
  try { bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0)); } catch { throw new RangeError('The logs aren’t a ZIP file.'); }
  if (bytes.length > ZIP_LIMIT) throw new RangeError('The logs are larger than 20 MB.');
  // Local file header, or the end record of an empty archive.
  const magic = bytes[0] === 0x50 && bytes[1] === 0x4b && ((bytes[2] === 3 && bytes[3] === 4) || (bytes[2] === 5 && bytes[3] === 6));
  if (!magic) throw new RangeError('The logs aren’t a ZIP file.');
  return bytes;
}

async function limited(limiter, key) {
  if (!limiter) return false;
  const { success } = await limiter.limit({ key });
  return !success;
}

async function human(env, token, client) {
  if (typeof token !== 'string' || !token || token.length > 2048) return false;
  const form = new FormData();
  form.append('secret', env.TURNSTILE_SECRET);
  form.append('response', token);
  if (client !== 'unknown') form.append('remoteip', client);
  const response = await fetch(TURNSTILE, { method: 'POST', body: form });
  if (!response.ok) return false;
  const result = await response.json();
  return result.success === true;
}

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname.replace(/\/+$/, '');
    if (path !== PATH) return reply(request, 404, { error: 'Not found.' });
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: { ...cors(request), 'access-control-max-age': '86400' } });
    if (request.method !== 'POST') return reply(request, 405, { error: 'Send reports with POST.' });
    if (Number(request.headers.get('content-length') || 0) > BODY_LIMIT) return reply(request, 413, { error: 'The report is too large.' });
    const client = request.headers.get('cf-connecting-ip') || 'unknown';
    if (await limited(env.LIMITER, client) || await limited(env.GLOBAL_LIMITER, 'all')) {
      return reply(request, 429, { error: 'Too many reports right now. Try again in a minute.' });
    }
    let payload;
    try {
      const text = await request.text();
      if (text.length > BODY_LIMIT) return reply(request, 413, { error: 'The report is too large.' });
      payload = JSON.parse(text);
    } catch {
      return reply(request, 400, { error: 'The report couldn’t be read.' });
    }
    const { errors, report } = validate(payload);
    if (errors.length) return reply(request, 400, { error: errors.join(' ') });
    let zip = null;
    if (payload.logs !== undefined && payload.logs !== null) {
      try { zip = zipBytes(payload.logs); } catch (error) { return reply(request, error.message.includes('20 MB') ? 413 : 400, { error: error.message }); }
    }
    // The app keeps a copy of every report; the website doesn't.
    const kept = report.source === 'app' ? ' Your report is saved on this computer.' : '';
    if (!configured(env) || (zip && !env.LOGS) || (report.source === 'web' && !env.TURNSTILE_SECRET)) {
      return reply(request, 503, { error: 'Reports can’t be sent yet.' + kept });
    }
    if (report.source === 'web' && !await human(env, payload.turnstile, client)) {
      return reply(request, 403, { error: 'We couldn’t confirm the report came from a person. Reload the page and try again.' });
    }
    const key = zip ? `reports/${new Date().toISOString().slice(0, 10)}/${report.id}.zip` : null;
    if (key) {
      await env.LOGS.put(key, zip, { httpMetadata: { contentType: 'application/zip' }, customMetadata: { report: report.id, source: report.source } });
    }
    try {
      const token = await installationToken(env);
      const issue = await createIssue(token, { title: issueTitle(report), body: issueBody(report, Boolean(key)), labels: issueLabels(report) });
      console.log(JSON.stringify({ event: 'report-filed', report: report.id, source: report.source, issue: issue.number, logs: Boolean(key) }));
      return reply(request, 201, { number: issue.number, url: issue.url, logs: Boolean(key) });
    } catch (error) {
      if (key) await env.LOGS.delete(key).catch(() => {});
      console.error(JSON.stringify({ event: 'report-failed', report: report.id, reason: String(error.message).slice(0, 200) }));
      return reply(request, 502, { error: 'GitHub didn’t accept the report. Try again in a few minutes.' + kept });
    }
  },
};
