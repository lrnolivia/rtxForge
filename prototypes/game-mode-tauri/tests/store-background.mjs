import {chromium,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const browser=await chromium.launch({channel:process.env.RTXFORGE_BROWSER||'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1080},reducedMotion:'reduce'});
const errors=[];page.on('pageerror',error=>errors.push(error.message));
const nav=name=>page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true});
try{
  let requests=0;page.on('request',request=>{if(request.url().includes('/api/store-background?appid=1091500'))requests++;});
  await page.goto('http://127.0.0.1:1420');await page.waitForSelector('.game-card');
  await page.getByRole('button',{name:'Open Cyberpunk 2077 details',exact:true}).click();
  await expect(page.locator('#scene')).toHaveAttribute('data-background-state','ready',{timeout:20000});
  await expect(page.locator('#scene')).toHaveAttribute('data-background-width','3840');
  await expect(page.locator('#scene')).toHaveAttribute('data-background-height','2160');
  await expect(page.locator('#scene')).toHaveAttribute('data-store-quality','native');
  expect(await page.locator('#scene').evaluate(n=>getComputedStyle(n).backgroundImage)).toContain('blob:');
  await nav('Library').click();await expect(page.locator('#scene')).toHaveAttribute('data-hero','false');
  await page.getByRole('button',{name:'Open Cyberpunk 2077 details',exact:true}).click();
  await expect(page.locator('#scene')).toHaveAttribute('data-background-state','ready');expect(requests).toBe(1);
  // Existing bundled art stands in for a smaller image only in this test.
  const small='data:image/png;base64,'+readFileSync(new URL('../public/app-hero-light.png',import.meta.url)).toString('base64');
  await page.route('**/api/store-background?appid=*',route=>route.fulfill({json:{image:small}}));
  await nav('Library').click();await page.getByRole('button',{name:'Open 007 First Light details',exact:true}).click();
  await expect(page.locator('#scene')).toHaveAttribute('data-background-state','ready');
  await expect(page.locator('#scene')).toHaveAttribute('data-store-quality','soft');
  expect(await page.locator('#scene').evaluate(n=>getComputedStyle(n).filter)).toContain('blur(1.5px)');
  expect(await page.locator('#scene').evaluate(n=>getComputedStyle(n,'::before').opacity)).toBe('0.045');
  expect(errors).toEqual([]);
  console.log(JSON.stringify({passed:true,checks:['real Steam 4K screenshot decoded','Details-only background','memory cache avoids repeat request','smaller images receive fine blur and grain']}));
}finally{await browser.close();}
