const prefix = '/rtxforge';
function redirect(url) {
  return new Response(null, { status: 301, headers: { Location: url.href, 'Cache-Control': 'public, max-age=300' } });
}
export default {
  fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname === 'rtxforge.loew.fi') {
      url.hostname = 'loew.fi'; url.protocol = 'https:';
      if (url.pathname !== prefix && !url.pathname.startsWith(`${prefix}/`)) url.pathname = `${prefix}${url.pathname}`;
      if (url.pathname === prefix) url.pathname += '/';
      return redirect(url);
    }
    if (url.pathname === prefix) { url.pathname += '/'; return redirect(url); }
    // Cloudflare routes include query strings, so the route needs a trailing wildcard.
    // Similar prefixes belong to the existing loew.fi origin, never to these assets.
    if (!url.pathname.startsWith(`${prefix}/`)) return fetch(request);
    return env.ASSETS.fetch(request);
  }
};
