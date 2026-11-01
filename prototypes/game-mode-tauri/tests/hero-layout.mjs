import { chromium, expect } from '@playwright/test';

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await page.addInitScript(() => localStorage.setItem('rtxforge-game-mode-prototype', JSON.stringify({
  theme: 'clear', tint: true, accent: '#d8d5ce', appearanceDefaultsVersion: 2,
})));
await page.route('**/api/snapshot', route => route.fulfill({ json: {
  schema: 1, source: 'Layout fixture', platform: 'windows', readOnly: true, capturedAt: '',
  games: [{ id: 'hero-layout', name: 'A Long Game Title: Adventures Beyond the Horizon',
    path: 'C:/fixture/game', appid: null, source: 'Steam', status: 'Installed', art: null,
    developers: ['Example Development Studio'], release: 'November 1, 2026', accent: '#4191af',
    description: 'Explore a wide world with friends and discover new adventures. '.repeat(6),
  }], packages: [], warnings: [], libraryCount: 1, settingsFound: true, defaults: {},
  operations: { available: false, reason: 'Layout fixture only' },
} }));

try {
  await page.goto('http://127.0.0.1:1420');
  await page.locator('.game-card').first().click();
  await expect(page.locator('.details-page')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  let checks = 0;
  for (const width of [1920, 1280, 1000, 761, 760, 600, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const scroll of [0, 70, 180, 400]) {
      await page.locator('.details-scroll').evaluate((element, y) => { element.scrollTop = y; }, scroll);
      await expect.poll(() => page.evaluate(() => {
        const back = document.querySelector('.details-hero .back').getBoundingClientRect();
        return [...document.querySelectorAll('.details-identity .hero-status, .details-identity h1, .details-identity .detail-artwork')]
          .filter(node => {
            const rect = node.getBoundingClientRect();
            return rect.height && getComputedStyle(node).display !== 'none'
              && rect.left < back.right && rect.right > back.left
              && rect.top < back.bottom && rect.bottom > back.top;
          }).map(node => node.className);
      }), { message: 'Back button overlaps header at width ' + width + ', scroll ' + scroll }).toEqual([]);
      checks++;
    }
  }
  await page.locator('.details-hero .back').click();
  await expect(page.locator('.game-card')).toBeVisible();
  expect(errors).toEqual([]);
  console.log(JSON.stringify({ passed: true, responsiveOverlapChecks: checks, backReturnsToLibrary: true }));
} finally {
  await browser.close();
}
