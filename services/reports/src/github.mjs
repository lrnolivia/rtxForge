// Files issues as the rtxForge Reports GitHub App. Its only permissions are
// Issues: write and Metadata: read on lrnolivia/rtxForge. Keys and tokens live in
// Worker secrets and are never logged or returned.
export const REPOSITORY = 'lrnolivia/rtxForge';
const API = 'https://api.github.com';
const HEADERS = { accept: 'application/vnd.github+json', 'x-github-api-version': '2022-11-28', 'user-agent': 'rtxforge-reports' };

export function configured(env) {
  return Boolean(env.RTXFORGE_REPORTS_APP_ID && env.RTXFORGE_REPORTS_INSTALLATION_ID && env.RTXFORGE_REPORTS_PRIVATE_KEY);
}

function base64url(bytes) {
  let text = '';
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function derLength(length) {
  if (length < 0x80) return [length];
  const bytes = [];
  for (let rest = length; rest > 0; rest >>= 8) bytes.unshift(rest & 0xff);
  return [0x80 | bytes.length, ...bytes];
}

function der(tag, content) {
  return Uint8Array.from([tag, ...derLength(content.length), ...content]);
}

// GitHub hands out PKCS#1 keys ("BEGIN RSA PRIVATE KEY"); WebCrypto imports PKCS#8.
function pkcs8(pkcs1) {
  const version = Uint8Array.from([0x02, 0x01, 0x00]);
  const rsaEncryption = Uint8Array.from([0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x01, 0x05, 0x00]);
  return der(0x30, [...version, ...rsaEncryption, ...der(0x04, pkcs1)]);
}

export async function signingKey(pem) {
  const text = String(pem).replace(/\\n/g, '\n');
  const body = text.replace(/-----(BEGIN|END) [A-Z ]+-----/g, '').replace(/\s+/g, '');
  const bytes = Uint8Array.from(atob(body), (c) => c.charCodeAt(0));
  const key = text.includes('BEGIN RSA PRIVATE KEY') ? pkcs8(bytes) : bytes;
  return crypto.subtle.importKey('pkcs8', key, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['sign']);
}

export async function appJwt(env, now = Date.now()) {
  const seconds = Math.floor(now / 1000);
  const encode = (value) => base64url(new TextEncoder().encode(JSON.stringify(value)));
  // Backdated a minute for clock drift; GitHub allows at most ten minutes.
  const unsigned = `${encode({ alg: 'RS256', typ: 'JWT' })}.${encode({ iat: seconds - 60, exp: seconds + 540, iss: String(env.RTXFORGE_REPORTS_APP_ID) })}`;
  const key = await signingKey(env.RTXFORGE_REPORTS_PRIVATE_KEY);
  const signature = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', key, new TextEncoder().encode(unsigned));
  return `${unsigned}.${base64url(new Uint8Array(signature))}`;
}

async function call(url, init, what) {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`${what} failed with HTTP ${response.status}`);
  return response.json();
}

export async function installationToken(env) {
  const jwt = await appJwt(env);
  const result = await call(`${API}/app/installations/${encodeURIComponent(env.RTXFORGE_REPORTS_INSTALLATION_ID)}/access_tokens`,
    { method: 'POST', headers: { ...HEADERS, authorization: `Bearer ${jwt}` } }, 'Installation token');
  return result.token;
}

export async function createIssue(token, issue) {
  const result = await call(`${API}/repos/${REPOSITORY}/issues`,
    { method: 'POST', headers: { ...HEADERS, authorization: `Bearer ${token}`, 'content-type': 'application/json' }, body: JSON.stringify(issue) },
    'Creating the issue');
  return { number: result.number, url: result.html_url };
}
