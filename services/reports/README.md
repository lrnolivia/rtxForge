# rtxForge report service

`POST https://loew.fi/rtxforge/api/report` files one in-app bug report as an issue on
[lrnolivia/rtxForge](https://github.com/lrnolivia/rtxForge/issues). Testers need no GitHub
account. The app sends:

```json
{ "schema": 1, "report_id": "r20261029T120000-abc123",
  "fields": { "platform": "Linux", "observations": "…", "...": "…" },
  "details": ["Graphics API: d3d12"],
  "logs": "<base64 of the redacted ZIP the user previewed, optional>" }
```

- **Fields** are the app's and the issue form's (`src/fields.json`, kept equal to
  `scripts/beta_report.py` by `tests/test_beta_report.py`). Unknown fields, unlisted
  choices and over-long answers are refused. Only the OS and "What happened?" are required.
- **Public text** is redacted again here (tokens, emails, local paths, Steam IDs), and
  `@mentions` and headings are neutralized.
- **Logs** stay private: the ZIP (20 MB at most) goes to the `rtxforge-report-logs` R2
  bucket under `reports/<date>/<report id>.zip`. The issue only says logs were sent privately
  with the report ID. If the issue can't be filed, the stored ZIP is deleted.
- **Website reports** send `"source": "web"` and a Cloudflare Turnstile token as
  `"turnstile"`. They're labeled `from-web` instead of `from-app`. CORS is open only to
  `https://loew.fi` and `https://rtxforge.loew.fi`; the app sends no Origin.
- **Limits:** 3 reports a minute per IP and 30 a minute overall.
- **Responses:** `201 {number, url, logs}`, or `{error}` with 400, 404, 405, 413, 429,
  403 (Turnstile failed), 502 (GitHub refused), or 503 (not configured yet). Errors are
  sentences the app and the website show as-is.

The issue is filed by the **rtxForge Reports** GitHub App (Issues: write, Metadata: read,
installed only on rtxForge). Its credentials are Worker secrets, never committed:
`RTXFORGE_REPORTS_APP_ID`, `RTXFORGE_REPORTS_INSTALLATION_ID`, `RTXFORGE_REPORTS_PRIVATE_KEY`,
and `TURNSTILE_SECRET` for website reports.

Workers Builds deploys this folder from `main`. Run `npm test` here to test it (Node 22+).
