import { chromium, expect } from '@playwright/test';

const browser = await chromium.launch({ channel: process.env.RTXFORGE_BROWSER || 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, reducedMotion: 'reduce' });
const calls = [];
let game, cancellation = false;
await page.route('**/api/engine/status', route => route.fulfill({ json: { enabled: true, reason: 'Test-only contract transport.' } }));
await page.route('**/api/engine', async route => {
  const request = route.request().postDataJSON();
  calls.push(request);
  let result = {};
  if (request.method === 'scan_game') result = [{ name: game.name, game: game.path, exe: 'fixture.exe', installed: false, blocked: '' }];
  else if (request.method === 'prepare_routes') result = { token: 'fixture-exact-token', title: 'Test-only exact review', rows: [{ name: game.name, detail: 'Contract fixture only. No files are written.' }], blocked: [], trust: 'I acknowledge this test-only review.' };
  else if (request.method === 'execute_routes') { await new Promise(resolve => setTimeout(resolve, 500)); result = { report: 'Contract fixture completed. No files written.' }; }
  else if (request.method === 'cancel_routes') { cancellation = true; result = {}; }
  await route.fulfill({ json: { result } });
});
try {
  await page.goto('http://127.0.0.1:1420');
  await expect(page.getByText('Local library loaded', { exact: true })).toBeVisible({ timeout: 30000 });
  game = await page.evaluate(async () => (await (await fetch('/api/snapshot')).json()).games[0]);
  expect(game).toBeTruthy();
  await page.locator('.game-card').first().click();
  await page.getByRole('button', { name: 'Install Features', exact: true }).click();
  await page.getByRole('button',{name:'Review games',exact:true}).click();
  await expect(page.getByRole('heading', { name: 'Test-only exact review' })).toBeVisible();
  const confirm = page.getByRole('button', { name: 'Confirm changes' });
  await expect(confirm).toBeDisabled();
  expect(calls.filter(call => call.method === 'execute_routes')).toHaveLength(0);
  await page.getByRole('checkbox', { name: 'I acknowledge this test-only review.' }).check();
  await confirm.click();
  await expect(page.getByRole('button', { name: 'Request cancellation' })).toBeVisible();
  await page.getByRole('button', { name: 'Request cancellation' }).click();
  await expect(page.getByText('Contract fixture completed. No files written.', { exact: false })).toBeVisible();
  expect(cancellation).toBe(true);
  const execute = calls.find(call => call.method === 'execute_routes');
  expect(execute.params.token).toBe('fixture-exact-token');
  expect(execute.params.offline_acknowledged).toBe(true);
  const prepare = calls.find(call => call.method === 'prepare_routes');
  expect(prepare.params.rows).toHaveLength(1);
  expect(prepare.params.rows[0].game).toBe(game.path);
  expect(prepare.params.operation).toBe('install');
  await page.getByRole('button', { name: 'Back to game' }).click();
  await page.getByRole('button', { name: 'Install Features', exact: true }).click();
  await page.getByRole('button',{name:'Review games',exact:true}).click();
  await expect(page.getByRole('heading', { name: 'Test-only exact review' })).toBeVisible();
  await page.getByRole('button', { name: 'Back', exact: true }).click();
  expect(calls.find(call => call.method === 'discard_routes').params.tokens).toEqual(['fixture-exact-token']);
  expect(calls.filter(call => call.method === 'execute_routes')).toHaveLength(1);
  console.log(JSON.stringify({ passed: true, checks: ['no execute before confirmation', 'trust acknowledgement required', 'exact reviewed token preserved', 'exact selected installation preserved', 'safe cancellation request', 'discard releases exact token', 'no actual game operations'] }));
} finally { await browser.close(); }
