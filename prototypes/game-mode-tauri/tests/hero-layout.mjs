import { chromium, expect } from '@playwright/test';

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await page.addInitScript(() => {if(!localStorage.getItem('rtxforge-game-mode-prototype'))localStorage.setItem('rtxforge-game-mode-prototype', JSON.stringify({
  theme: 'clear', tint: true, accent: '#d8d5ce', appearanceDefaultsVersion: 2,
}));});
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
      if(width>760&&scroll>=180){
        const compact=await page.locator('.details-page').getAttribute('data-hero-compact');
        if(compact==='true')expect(await page.locator('.game-title').evaluate(n=>getComputedStyle(n,'::before').display)).toBe('none');
      }
      const overlaps=await page.evaluate(()=>{
        const pane=innerWidth>760?document.querySelector('.details-scroll'):document.querySelector('#content');
        const gutter=pane.offsetWidth-pane.clientWidth;if(gutter<4||pane.scrollHeight<=pane.clientHeight)return [];
        const edge=pane.getBoundingClientRect().right-gutter-4;
        return [...document.querySelectorAll('.hero-actions button')].filter(n=>n.getBoundingClientRect().right>edge).map(n=>n.getAttribute('aria-label')||n.textContent);
      });
      expect(overlaps,'Hero actions must clear the scrollbar at '+width).toEqual([]);
    }
  }
  await page.locator('.details-hero .back').click();
  await expect(page.locator('.game-card')).toBeVisible();
  await page.evaluate(()=>localStorage.setItem('rtxforge-game-mode-prototype',JSON.stringify({theme:'light',tint:true,appearanceDefaultsVersion:2})));
  await page.reload();await page.setViewportSize({width:1280,height:900});
  await page.locator('.game-card').first().click();
  await page.locator('.details-scroll').evaluate(n=>{n.scrollTop=400;});
  await expect(page.locator('.details-page')).toHaveAttribute('data-hero-compact','true');
  const title=await page.locator('.game-title').evaluate(n=>{
    const s=getComputedStyle(n),ink=s.getPropertyValue('--hero-card-ink').trim();
    const rgb=ink.startsWith('#')?'rgb('+[1,3,5].map(i=>parseInt(ink.slice(i,i+2),16)).join(', ')+')':ink;
    return {color:s.color,accentInk:rgb,shadow:s.textShadow,backing:getComputedStyle(n,'::before').display};
  });
  expect(title.color).toBe(title.accentInk);expect(title.shadow).toBe('none');expect(title.backing).toBe('none');
  expect(errors).toEqual([]);
  console.log(JSON.stringify({ passed: true, responsiveOverlapChecks: checks, backReturnsToLibrary: true }));
} finally {
  await browser.close();
}
