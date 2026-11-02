import {chromium, expect} from '@playwright/test';

const browser=await chromium.launch({channel:process.env.RTXFORGE_BROWSER||'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1080},reducedMotion:'reduce'});
const errors=[];page.on('pageerror',error=>errors.push(error.message));
const nav=name=>page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true});
try {
  await page.addInitScript(()=>{if(!localStorage.getItem('rtxforge-game-mode-prototype'))localStorage.setItem('rtxforge-game-mode-prototype',JSON.stringify({libraryScale:105}));});
  await page.goto('http://127.0.0.1:1420');await page.waitForSelector('.game-card');await page.evaluate(()=>document.fonts.ready);
  await expect(page.getByRole('slider',{name:'Library item size'})).toHaveValue('100');
  await page.reload();await page.waitForSelector('.game-card');
  await expect(page.getByRole('slider',{name:'Library item size'})).toHaveValue('100');
  const bounds=()=>page.locator('.app-header,#content').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return [r.x,r.y,r.width,r.height]}));
  const baseline=await bounds();
  for(const name of ['Presets','Packages','Extras','Settings','Library']){await nav(name).click();expect(await bounds()).toEqual(baseline);}
  const pane=await page.locator('#game-results').evaluate(n=>{const content=n.closest('#content'),r=n.getBoundingClientRect(),c=content.getBoundingClientRect(),s=getComputedStyle(content);return {bottom:c.bottom-parseFloat(s.paddingBottom)-r.bottom,right:c.right-r.right,left:r.left-c.left,glow:parseFloat(getComputedStyle(n).paddingLeft)}});
  expect(Math.abs(pane.bottom)).toBeLessThan(2);expect(pane.right).toBeLessThanOrEqual(2);expect(pane.left).toBeLessThanOrEqual(2);expect(pane.glow).toBeGreaterThanOrEqual(24);
  await page.locator('#game-results').evaluate(n=>n.scrollTop=500);
  await expect(page.locator('.shell')).toHaveAttribute('data-header-collapsed','true');
  await page.getByRole('slider',{name:'Library item size'}).press('Home');
  await expect.poll(()=>page.locator('#game-results').evaluate(n=>n.scrollTop)).toBe(0);
  await expect(page.locator('.shell')).toHaveAttribute('data-header-collapsed','false');
  for(const name of ['Extras','Settings']){await nav(name).click();await page.locator('#content').evaluate(n=>n.scrollTop=500);await expect(page.locator('.shell')).toHaveAttribute('data-header-collapsed','true');await page.locator('#content').evaluate(n=>n.scrollTop=0);await expect(page.locator('.shell')).toHaveAttribute('data-header-collapsed','false');}
  await nav('Library').click();
  await page.keyboard.press('Tab');await nav('Extras').focus();expect(await nav('Extras').evaluate(n=>getComputedStyle(n).outlineOffset)).toBe('-3px');
  for(const width of [760,550,390]){
    await page.setViewportSize({width,height:1000});
    const button=page.getByRole('button',{name:'Card size',exact:true});
    await expect(button).toBeVisible();await expect(page.getByRole('slider',{name:'Library item size'})).toBeHidden();
    const positions=await page.locator('.library-filter,.library-size-button,.view-switch').evaluateAll(nodes=>nodes.map(n=>Math.round(n.getBoundingClientRect().top)));
    expect(Math.max(...positions)-Math.min(...positions)).toBeLessThanOrEqual(8);
    await button.click();await expect(page.getByRole('slider',{name:'Library item size'})).toBeFocused();
    const panel=await page.locator('#library-size-panel').boundingBox();expect(panel.x).toBeGreaterThanOrEqual(0);expect(panel.x+panel.width).toBeLessThanOrEqual(width);
    await page.keyboard.press('Escape');await expect(button).toBeFocused();await expect(button).toHaveAttribute('aria-expanded','false');
    expect(await page.locator('#content,.shell,.library-tools').evaluateAll(nodes=>nodes.filter(n=>n.scrollWidth>n.clientWidth+2).map(n=>n.className))).toEqual([]);
  }
  expect(errors).toEqual([]);
  console.log(JSON.stringify({passed:true,checks:['stable shell across five pages','results fill surface height and width','glow bleed space','scroll collapse and restore','size change returns to first row','inset nav focus','narrow size popup and shared control row']}));
} finally {await browser.close();}
