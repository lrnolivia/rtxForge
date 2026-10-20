# rtxForge Beta website

Static Linux/Windows landing page served by the `rtxforge` Cloudflare Worker at https://rtxforge.loew.fi.

Use `npm ci`, `npm run check`, and `npm run deploy` from this directory. The custom domain, TLS, and asset publishing are managed by Wrangler. No server build is required. Download destinations and platform copy live in `public/app.js`.

The `continuous` release tag is retained for installed-app updater compatibility. The public release title is rtxForge Beta.
