// One rtxForge report, checked against the same fields the app, the website and the
// GitHub issue form use (fields.json mirrors scripts/beta_report.py; a Python test
// keeps them equal). Everything that reaches the public issue is redacted here again.
import FIELDS from './fields.json' with { type: 'json' };

const LABELS = Object.fromEntries(FIELDS.fields);
const DETAIL_LINES = 20;
const DETAIL_LENGTH = 300;
const REPORT_ID = /^r\d{8}T\d{6}-[0-9a-f]{6}$/;

// The app's game_notes.redact, line for line.
export function redact(text) {
  return String(text)
    .replace(/(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+/gi, '$1[REDACTED]')
    .replace(/((?:(?:access|refresh|auth|session)[_-]?)?token|api[_-]?key|password|passwd|secret)(\s*["']?\s*[:=]\s*["']?)[^\s,;"'&]+/gi, '$1$2[REDACTED]')
    .replace(/https?:\/\/[^\s"<>]+/gi, (url) => url.split('?')[0].split('#')[0])
    .replace(/(?<![\w:])\/(?:home|var\/home|run|mnt|var\/mnt|media|tmp)\/[^\n\r"<>]*/g, '[LOCAL PATH]')
    .replace(/\b[A-Z]:[\\/][^\n\r"<>]*/gi, '[WINDOWS PATH]')
    .replace(/\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b/g, '[REDACTED]')
    .replace(/\b7656119\d{10}\b/g, '[STEAM ID]')
    .replace(/\[U:1:\d+\]/g, '[STEAM ID]')
    .replace(/\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b/g, '[EMAIL]');
}

// Reports are public: no one gets pinged and no markup escapes its section.
function quiet(text) {
  return text.replace(/@(?=[A-Za-z0-9-])/g, '@​').replace(/^(#{1,6}\s)/gm, '\\$1');
}

function clean(value) {
  return quiet(redact(String(value ?? '').replace(/\r\n?/g, '\n').trim()));
}

/** Check one report; returns { errors, report } with every value cleaned. */
export function validate(payload) {
  const errors = [];
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return { errors: ['The report is empty.'], report: null };
  }
  const given = payload.fields;
  if (!given || typeof given !== 'object' || Array.isArray(given)) {
    return { errors: ['The report has no answers.'], report: null };
  }
  for (const key of Object.keys(given)) {
    if (!(key in LABELS)) errors.push(`Unknown field: ${key.slice(0, 40)}.`);
  }
  const fields = {};
  for (const [key, label] of FIELDS.fields) {
    const raw = given[key];
    if (raw !== undefined && raw !== null && typeof raw !== 'string') { errors.push(`${label} must be text.`); continue; }
    const value = String(raw ?? '').trim();
    if (!value) {
      if (FIELDS.required.includes(key)) errors.push(`${label} is empty.`);
    } else if (FIELDS.choices[key] && !FIELDS.choices[key].includes(value)) {
      errors.push(`${label}: choose one of the listed answers.`);
    } else if (value.length > (FIELDS.lengths[key] ?? Infinity)) {
      errors.push(`${label} is longer than ${FIELDS.lengths[key]} characters.`);
    }
    fields[key] = FIELDS.choices[key] ? value : clean(value);
  }
  const details = Array.isArray(payload.details) ? payload.details : [];
  if (details.length > DETAIL_LINES || details.some((line) => typeof line !== 'string' || line.length > DETAIL_LENGTH)) {
    errors.push('The detected details are too long.');
  }
  const id = typeof payload.report_id === 'string' && REPORT_ID.test(payload.report_id) ? payload.report_id : null;
  if (!id) errors.push('The report has no valid ID.');
  const source = payload.source === undefined ? 'app' : payload.source;
  if (!(source in FIELDS.sources)) errors.push('Unknown report source.');
  return {
    errors,
    report: { id, source, fields, details: errors.length ? [] : details.map(clean).filter(Boolean) },
  };
}

export function issueLabels(report) {
  return [...FIELDS.labels, FIELDS.sources[report.source].label];
}

export function issueTitle(report) {
  const game = report.fields.game || 'Unknown game';
  return `[Beta report] ${game} · ${report.fields.platform || 'Not sure'}`.slice(0, 250);
}

/** The body as GitHub renders the issue form, so app and website reports parse the same way. */
export function issueBody(report, logs) {
  const blocks = FIELDS.fields.map(([key, label]) => `### ${label}\n\n${report.fields[key] || '_No response_'}`);
  const detected = [...report.details, `Report ID: ${report.id}`];
  blocks.push('### Detected by rtxForge\n\n' + detected.map((line) => `- ${line}`).join('\n'));
  blocks.push('### Logs\n\n' + (logs
    ? `Redacted logs were sent privately to the rtxForge maintainers (report ${report.id}). They aren't public.`
    : 'Not included.'));
  blocks.push(`_${FIELDS.sources[report.source].footer}_`);
  return blocks.join('\n\n') + '\n';
}

export const ZIP_LIMIT = FIELDS.zip_limit;
