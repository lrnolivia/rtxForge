import test from 'node:test';
import assert from 'node:assert/strict';
import { validate, issueTitle, issueBody, redact } from '../src/report.mjs';
import { sample } from './sample.mjs';

test('a complete report passes and keeps choice answers exactly', () => {
  const { errors, report } = validate(sample());
  assert.deepEqual(errors, []);
  assert.equal(report.fields['mfg-result'], 'Not working in-game');
  assert.equal(issueTitle(report), '[Beta report] Control · Linux');
});

test('the OS and what happened are required, choices and lengths are enforced', () => {
  const { errors } = validate(sample({ platform: '', observations: '   ', 'nr-result': 'Amazing', game: 'x'.repeat(151) }));
  assert.ok(errors.includes('Operating system is empty.'));
  assert.ok(errors.includes('What happened? is empty.'));
  assert.ok(errors.includes('NR result: choose one of the listed answers.'));
  assert.ok(errors.includes('Game and version is longer than 150 characters.'));
});

test('unknown fields, non-text values and a missing ID are refused', () => {
  assert.ok(validate(sample({ extra: 'x' })).errors.some((e) => e.startsWith('Unknown field')));
  assert.ok(validate(sample({ game: 5 })).errors.includes('Game and version must be text.'));
  assert.ok(validate({ ...sample(), report_id: '../etc' }).errors.includes('The report has no valid ID.'));
  assert.deepEqual(validate(null).errors, ['The report is empty.']);
  assert.deepEqual(validate({}).errors, ['The report has no answers.']);
});

test('the public body is redacted again and pings no one', () => {
  const { report } = validate(sample({
    observations: 'token=s3cr3tvalue from me@example.com at /home/lauren/game\nand C:\\Users\\lauren\\x\nping @someone\n## fake heading',
  }));
  const body = issueBody(report, true);
  for (const secret of ['s3cr3tvalue', 'me@example.com', '/home/lauren', 'C:\\Users', '@someone']) assert.ok(!body.includes(secret), secret);
  assert.ok(body.includes('@\u200bsomeone'));
  assert.ok(body.includes('\\## fake heading'));
  assert.ok(body.includes('### What happened?'));
  assert.ok(body.includes('- Report ID: r20261029T120000-abc123'));
  assert.ok(body.includes('sent privately'));
  assert.ok(issueBody(report, false).includes('### Logs\n\nNot included.'));
});

test('redaction matches the app for tokens, URLs and Steam IDs', () => {
  assert.equal(redact('Authorization: Bearer xyz'), 'Authorization: [REDACTED]');
  assert.equal(redact('https://example.com/a?key=1#x'), 'https://example.com/a');
  assert.equal(redact('id 76561198000000000 and [U:1:42]'), 'id [STEAM ID] and [STEAM ID]');
  assert.equal(redact('ghp_' + 'a'.repeat(36)), '[REDACTED]');
});
