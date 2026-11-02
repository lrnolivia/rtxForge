import {chromium, expect} from '@playwright/test';

const browser = await chromium.launch({channel:process.env.RTXFORGE_BROWSER || 'msedge',headless:true});
const page = await browser.newPage({viewport:{width:2560,height:1440},deviceScaleFactor:1.5,reducedMotion:'reduce'});
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
const nav=name=>page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true});
const noOverflow=async()=>expect(await page.locator('#content,.shell,.main-nav,.preset-pod,.preset-mfg,.field,.number-stepper,.game-list').evaluateAll(nodes=>nodes.filter(n=>n.scrollWidth>n.clientWidth+2).map(n=>n.className))).toEqual([]);
try {
  await page.goto('http://127.0.0.1:1420');
  await page.waitForSelector('.game-card');
  await page.evaluate(()=>document.fonts.ready);
  const count=await page.locator('.game-card').count();
  expect(count).toBeGreaterThan(20);
  const rows=await page.locator('#game-results').evaluate(results=>{
    const grid=results.querySelector('.games'),frame=results.getBoundingClientRect();
    const cards=[...grid.querySelectorAll('.game-item')].map(n=>n.getBoundingClientRect());
    const tops=[...new Set(cards.map(r=>r.top))];
    return {width:document.querySelector('#content').clientWidth,visible:Number(grid.dataset.visibleRows),
      complete:tops.filter(top=>{const card=cards.find(r=>r.top===top);return card.top>=frame.top&&card.bottom<=frame.bottom+1}).length,
      partial:cards.some(r=>r.top<frame.bottom-1&&r.bottom>frame.bottom+1)};
  });
  expect(rows.width).toBeGreaterThan(2400);
  expect(rows.visible).toBe(2);expect(rows.complete).toBe(2);expect(rows.partial).toBe(false);
  await noOverflow();
  await page.locator('#game-results').evaluate(n=>n.scrollTop=n.scrollHeight);
  const last=await page.locator('.game-item').last().boundingBox(),pane=await page.locator('#game-results').boundingBox();
  expect(last.y+last.height).toBeLessThanOrEqual(pane.y+pane.height);
  await page.locator('.game-card').last().click();
  await page.getByRole('button',{name:'Back to Library',exact:true}).click();
  await expect(page.locator('.game-card').last()).toBeFocused();
  expect(await page.locator('#game-results').evaluate(n=>n.scrollTop)).toBeGreaterThan(0);
  await page.locator('#library-search').fill('Assassin');
  expect(await page.locator('.game-card').count()).toBeLessThan(count);
  await page.locator('#library-search').fill('');
  await expect(page.locator('.game-card')).toHaveCount(count);
  await expect(page.locator('.games')).toHaveAttribute('data-visible-rows','2');
  // The demo's per-game color must propagate to the whole library and survive
  // a reload, without writing the shared desktop preferences.
  await page.getByRole('button',{name:'Open The Sims™ 4 details',exact:true}).click();
  await page.getByRole('button',{name:'Appearance',exact:true}).click();
  await page.locator('#game-accent-color').fill('#db38a3');
  await expect(page.getByRole('button',{name:'Use saved accent',exact:true})).toBeEnabled();
  await nav('Library').click();
  const sims=page.locator('.game-item').filter({has:page.getByRole('button',{name:'Open The Sims™ 4 details',exact:true})});
  expect(await sims.evaluate(n=>n.style.getPropertyValue('--game-accent'))).toBe('#db38a3');
  await sims.locator('[data-select-game]').click();
  await expect(sims.locator('.game-card')).toHaveCSS('background-color','rgb(219, 56, 163)');
  await page.getByRole('button',{name:'Clear selection',exact:true}).click();
  await page.reload();await page.waitForSelector('.game-card');
  expect(await sims.evaluate(n=>n.style.getPropertyValue('--game-accent'))).toBe('#db38a3');
  for(const size of [{width:1440,height:990},{width:960,height:900},{width:390,height:844}]) {
    await page.setViewportSize(size);
    for(const layout of ['Poster grid','Wide capsules','Game list']) {
      await page.getByRole('button',{name:layout,exact:true}).click();await noOverflow();
      const ratio=await page.locator('.poster').first().evaluate(n=>n.offsetWidth/n.offsetHeight);
      expect(ratio).toBeCloseTo(layout==='Poster grid'?2/3:92/43,1);
    }
    await page.locator('.game-card').first().click();
    await expect(page.locator('.hero-actions button')).toHaveCount(4);
    for(const icon of await page.locator('.hero-actions button>.icon').all())await expect(icon).toBeVisible();
    expect(await page.locator('.hero-actions button>.icon').count()).toBe(4);
    expect(await page.locator('.hero-actions').evaluate(n=>n.scrollWidth<=n.clientWidth+1)).toBe(true);
    await page.getByRole('button',{name:'Back to Library',exact:true}).click();
    await nav('Presets').click();await noOverflow();
    await nav('Settings').click();await noOverflow();
    for(const theme of ['Clear','Dark','Light']){await page.getByRole('button',{name:theme,exact:true}).click();await noOverflow();}
    await nav('Library').click();
  }
  await page.getByRole('button',{name:'More options',exact:true}).click();
  await expect(page.locator('#shell-menu')).toBeVisible();
  const menu=await page.locator('#shell-menu').boundingBox();
  expect(menu.x).toBeGreaterThanOrEqual(0);expect(menu.x+menu.width).toBeLessThanOrEqual(390);
  await page.keyboard.press('Escape');
  await expect(page.locator('#shell-menu-button')).toBeFocused();
  await expect(page.locator('#shell-menu-button')).toHaveAttribute('aria-expanded','false');
  await nav('Settings').click();
  await expect(page.locator('#details-navigation')).toHaveValue('sidebar');
  expect(errors).toEqual([]);
  console.log(JSON.stringify({passed:true,checks:['full-width 4K at 150% equivalent','two complete poster rows without partial row','all games reachable in real results scroller','focus and scroll restored after details','search replacement recalculates layout','Sims 4 color propagates to selected library card and survives reload','poster/capsule/list proportions and no overflow at 1440/960/390','Presets and all appearance themes fit','narrow menu anchoring and Escape focus/ARIA','sidebar default','no page errors']}));
} finally {await browser.close();}
