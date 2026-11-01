import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';

const output = new URL('../.impeccable/review/', import.meta.url);
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: process.env.RTXFORGE_BROWSER || 'msedge', headless: true });
const errors = [];
const nav = name => page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name, exact: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 960 }, reducedMotion: 'reduce' });
const page = await context.newPage();
page.on('pageerror', error => errors.push(error.message));
async function capture(name) {
  await page.evaluate(async () => { await document.fonts.ready; });
  await page.screenshot({ path: new URL(name + '.png', output).pathname.replace(/^\/([A-Z]:)/, '$1'), fullPage: true });
}
async function noOverflow() {
  const overflow = await page.evaluate(() => [...document.querySelectorAll('main,section,.inner-card,.field,.games,.app-header,.shell')].filter(node => node.scrollWidth > node.clientWidth + 2).map(node => node.className));
  expect(overflow, 'No horizontal overflow').toEqual([]);
}
try {
  await page.goto('http://127.0.0.1:1420');
  await expect(page.getByText('Local library loaded', { exact: true })).toBeVisible({ timeout: 30000 });
  await noOverflow();
  await capture('desktop');
  // A standard-mapping synthetic pad checks dispatch/focus without touching a physical controller.
  await page.evaluate(() => {
    window.__testPad = { axes: [0, 0], buttons: Array.from({ length: 17 }, () => ({ pressed: false })) };
    navigator.getGamepads = () => [window.__testPad];
    window.dispatchEvent(new Event('gamepadconnected'));
  });
  await expect(page.locator('#input-hints')).toContainText('Sections');
  await nav('Library').focus();
  await page.evaluate(() => { window.__testPad.buttons[15].pressed = true; });
  await expect(nav('Presets')).toBeFocused();
  await page.evaluate(() => { window.__testPad.buttons[15].pressed = false; });
  await page.waitForTimeout(40);
  await page.evaluate(() => { window.__testPad.buttons[0].pressed = true; });
  await expect(page.getByRole('heading', { name: 'Presets', exact: true })).toBeVisible();
  await page.evaluate(() => { window.__testPad.buttons[0].pressed = false; });
  await page.waitForTimeout(40);
  await page.evaluate(() => { window.__testPad.buttons[1].pressed = true; });
  await expect(page.getByRole('heading', { name: 'Library', exact: true })).toBeVisible();
  await page.evaluate(() => {
    navigator.getGamepads = () => [];
    window.dispatchEvent(new Event('gamepaddisconnected'));
  });
  const gameCount = await page.locator('.game-card').count();
  if (gameCount) {
    await page.locator('.game-card').first().focus();
    await page.keyboard.press('ArrowRight');
    expect(await page.locator('.game-card:focus').count()).toBe(1);
    await page.keyboard.press('Enter');
    const detailsName = await page.locator('#page-title').innerText();
    await expect(page.getByRole('heading', { name: 'Testing', exact: true })).toBeVisible();
    await expect(page.locator('#page-title')).toHaveCSS('text-transform', 'none');
    await expect(page.locator('.details-page')).toBeVisible();
    await expect(page.locator('.details-identity .art-missing')).toHaveCount(0);
    await expect(page.getByText('Library record', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Install Features', exact: true })).toBeDisabled();
    await capture('details');
    await page.getByRole('button', { name: 'Appearance', exact: true }).click();
    await page.locator('#game-accent-color').fill('#4bbfff');
    const tintControl=page.getByRole('switch', { name: 'Accent tint', exact: true });if(await tintControl.getAttribute('aria-checked')!=='true')await tintControl.click();
    await expect(page.locator('html')).toHaveAttribute('data-tint', 'true');
    expect(await page.locator('.details-layout').evaluate(n=>getComputedStyle(n,':before').opacity)).toBe('0.3');
    await capture('details-tint');
    await expect(page.getByRole('button', { name: 'Light', exact: true })).toHaveCount(0);
    await nav('Settings').click();
    await page.getByRole('button', { name: 'Light', exact: true }).click();
    await nav('Library').click(); await page.getByRole('button',{name:'Open '+detailsName+' details',exact:true}).click();
    expect(await page.locator('.details-layout').evaluate(n=>getComputedStyle(n,':before').opacity)).toBe('0.15');
    await capture('details-light');
    await nav('Settings').click();
    await page.getByRole('button', { name: 'Clear', exact: true }).click();
    await nav('Library').click(); await page.getByRole('button',{name:'Open '+detailsName+' details',exact:true}).click();
    // Opening Details follows the original Game Mode and starts at Overview.
    await page.getByRole('button', { name: 'Appearance', exact: true }).click();
    await page.getByRole('switch', { name: 'Accent tint', exact: true }).click();
    await page.getByRole('button', { name: 'Features', exact: true }).click();
    await expect(page.locator('#mfg_mode')).toBeDisabled();
    await page.setViewportSize({ width: 390, height: 844 });
    await noOverflow(); await capture('details-mobile');
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.keyboard.press('Escape');
    await page.locator('#library-search').fill('no-such-game-fixture-9413');
    await expect(page.getByRole('heading', { name: 'No matching games' })).toBeVisible();
    await page.getByRole('button', { name: 'Clear search' }).click();
    expect(await page.locator('.game-card').count()).toBe(gameCount);
  }
  for (const width of [1280, 960, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 800 });
    await noOverflow();
    if (width === 390) await capture('mobile');
    else await capture(`library-${width}`);
    await nav('Settings').click();
    await noOverflow();
    if (width === 390) await capture('settings-mobile');
    await nav('Library').click();
  }
  await page.setViewportSize({ width: 1440, height: 960 });
  await nav('Settings').click();
  for (const theme of ['Light', 'Dark', 'Clear']) {
    await page.getByRole('button', { name: theme, exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme.toLowerCase());
    await noOverflow();
    await capture(`settings-${theme.toLowerCase()}`);
  }
  await page.getByRole('switch', { name: 'Accent tint' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-tint', 'true');
  await page.getByRole('button', { name: 'Dark', exact: true }).click();
  await expect(page.getByRole('switch', { name: 'Accent tint' })).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('button', { name: 'Reset appearance' }).click();
  const animation = await page.locator('.content > :first-child').evaluate(node => getComputedStyle(node).animationName);
  expect(animation).toBe('none');
  for (const name of ['Presets', 'Packages', 'Extras']) {
    await nav(name).click();
    await noOverflow(); await capture(name.toLowerCase());
    await page.setViewportSize({ width: 390, height: 844 });
    await noOverflow(); await capture(name.toLowerCase() + '-mobile');
    await page.setViewportSize({ width: 1440, height: 960 });
  }
  await page.route('**/api/snapshot', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Reader unavailable for the offline-state check.' }) }));
  await nav('Library').click();
  await page.getByRole('button', { name: 'Refresh library' }).click();
  await expect(page.getByText('Library reader unavailable', { exact: true })).toBeVisible();
  expect(await page.locator('.game-card').count()).toBe(gameCount);
  await capture('offline');
  await page.unroute('**/api/snapshot');
  await page.route('**/api/snapshot', async route => {
    const response = await route.fetch(); const data = await response.json(); data.games = []; data.libraryCount = 0;
    await route.fulfill({ json: data });
  });
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Your library starts here' })).toBeVisible({ timeout: 30000 });
  await capture('empty');
  expect(errors).toEqual([]);
  console.log(JSON.stringify({ passed: true, actualLibraryGames: gameCount, viewportWidths: [1440, 1280, 960, 390], checks: ['library', 'synthetic standard gamepad navigation/select/back', 'read-only feature controls, full-width details and reactive Details-only tint', 'game title case', 'search', 'themes', 'independent tint', 'reduced motion', 'packages', 'extras', 'offline with retained library', 'empty state', 'no page errors', 'no horizontal overflow'] }));
} finally { await browser.close(); }
