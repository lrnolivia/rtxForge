import {libraryFixture} from './ui-fixture.mjs';
import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch(process.env.RTXFORGE_BROWSER?{channel:process.env.RTXFORGE_BROWSER,headless:true}:{headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:2,reducedMotion:'reduce'});
const errors=[];page.on('pageerror',error=>errors.push(error.message));
const snapshot=libraryFixture();
await page.route('**/api/snapshot',route=>route.fulfill({json:snapshot}));
await page.route('**/api/engine/status',route=>route.fulfill({json:{enabled:true,reason:''}}));
await page.route('**/api/engine',route=>{const request=route.request().postDataJSON();const result=request.method==='steam_status'?{added:true,token:'fixture'}:request.method==='settings_get'?{}:request.method==='scan'?[]:{};return route.fulfill({json:{result}});});
try{
  await page.goto(process.env.RTXFORGE_UI_URL||'http://127.0.0.1:1434');
  try{await page.waitForSelector('.game-card',{timeout:10000});}catch(error){console.log({errors,body:(await page.locator('body').innerText()).slice(0,1600)});throw error;}await page.evaluate(()=>document.fonts.ready);
  const geometry=()=>page.locator('.games').evaluate(grid=>({columns:getComputedStyle(grid).gridTemplateColumns,rows:grid.dataset.visibleRows,width:grid.querySelector('.game-card').getBoundingClientRect().width,height:document.querySelector('#game-results').clientHeight}));
  for(const layout of ['Poster grid','Wide capsules']){
    await page.getByRole('button',{name:layout,exact:true}).click();
    for(const value of [100,105]){
      await page.getByRole('slider',{name:'Library item size'}).fill(String(value));
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      await expect(page.locator('[data-select-game]')).toHaveCount(0);
      await page.getByRole('button',{name:'Select games',exact:true}).click();
      const before=await geometry();
      await page.locator('[data-select-game]').first().click();
      await expect(page.getByRole('button',{name:'Clear selection',exact:true})).toBeVisible();
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      expect(await geometry(),`${layout} ${value}% stays stable in selection mode`).toEqual(before);
      await page.getByRole('button',{name:'Clear selection',exact:true}).click();
      await page.getByRole('button',{name:'Done selecting',exact:true}).click();
    }
  }
  await page.locator('.game-card').first().click();
  const detailBody=page.locator('.detail-body');
  await expect(detailBody.locator(':scope > :last-child').getByRole('heading',{name:'Testing',exact:true})).toBeVisible();
  await expect(detailBody.getByText('Game folder',{exact:true})).toBeVisible();
  await expect(detailBody.getByText('Game executable',{exact:true})).toBeVisible();
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Settings',exact:true}).click();
  const settings=page.getByRole('navigation',{name:'Settings sections'});
  for(const [group,labels] of [['General',['Appearance','Library','Game Features']],['Interfaces',['Game Mode','Overlay']],['App & support',['System','Recovery','About']]]){
    expect(await settings.getByRole('group',{name:group,exact:true}).getByRole('button').allTextContents())
      .toEqual(labels.map(label=>expect.stringContaining(label)));
  }
  await page.setViewportSize({width:390,height:844});
  expect(await settings.evaluate(node=>node.scrollWidth<=node.clientWidth+1)).toBe(true);
  await settings.getByRole('button',{name:'About',exact:true}).click();
  await expect(page.getByRole('heading',{name:'App and updates',exact:true})).toBeVisible();
  await page.setViewportSize({width:1920,height:1080});
  await page.getByRole('button',{name:'Appearance',exact:true}).click();
  expect(await page.locator('[data-theme-choice]').evaluateAll(nodes=>nodes.map(n=>n.dataset.themeChoice))).toEqual(['light','clear','dark']);
  await expect(page.locator('[data-theme-choice=clear]')).toHaveAttribute('aria-pressed','true');
  await page.getByRole('slider',{name:'Surface Tint',exact:true}).fill('35');
  await expect(page.locator('.surface-tint-control output')).toHaveText('35%');
  await page.getByRole('combobox',{name:'Accent source',exact:true}).selectOption('adaptive');
  await expect(page.locator('html')).toHaveAttribute('data-accent-mode','adaptive');
  await page.reload();await page.waitForSelector('.game-card');
  expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('rtxforge-game-mode-prototype')).tintStrength)).toBe(35);
  expect(errors).toEqual([]);console.log('4K/200% selection, Overview order, theme order and tint persistence passed.');
}finally{await browser.close();}
