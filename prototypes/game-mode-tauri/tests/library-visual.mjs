import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:990},reducedMotion:'no-preference'});
const errors=[];page.on('pageerror',error=>errors.push(error.message));
const nav=name=>page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true});
try{
 await page.goto('http://127.0.0.1:1420');await page.waitForSelector('.game-card');await page.evaluate(()=>document.fonts.ready);
 const first=page.locator('.game-card').first(),title=first.locator('h3');
 await page.mouse.move(0,0);await page.locator('#page-title').focus();
 expect(await title.evaluate(n=>getComputedStyle(n).color)).toBe(await page.locator('body').evaluate(n=>getComputedStyle(n).color));
 const before=await first.boundingBox(),artBefore=await first.locator('.poster').boundingBox();
 await first.hover();await page.waitForTimeout(300);
 const after=await first.boundingBox(),artAfter=await first.locator('.poster').boundingBox();
 expect(Math.abs(after.width/before.width-artAfter.width/artBefore.width)).toBeLessThan(.002);
 expect(after.width/before.width).toBeGreaterThan(1.01);
 expect(await first.locator('.poster').evaluate(n=>getComputedStyle(n).transform)).toBe('none');
 expect(await title.evaluate(n=>getComputedStyle(n).color)).toBe(await page.locator('body').evaluate(n=>getComputedStyle(n).color));
 await page.locator('.select-game').first().click();
 expect(await page.locator('.game-item').first().getAttribute('data-selected')).toBe('true');
 expect(await title.evaluate(n=>getComputedStyle(n).color)).not.toBe(await page.locator('body').evaluate(n=>getComputedStyle(n).color));
 await page.getByRole('button',{name:'Clear selection',exact:true}).click();await page.mouse.move(0,0);
 for(const [layout,name] of [['grid','Poster grid'],['capsules','Wide capsules'],['list','Game list']]){
  await page.getByRole('button',{name,exact:true}).click();await page.locator('#page-title').focus();await page.waitForTimeout(350);
  await page.locator('.select-game').first().click();await page.mouse.move(0,0);await page.waitForTimeout(250);
  const fill=await page.locator('.game-item').first().evaluate(n=>{const c=document.createElement('canvas').getContext('2d');c.fillStyle=getComputedStyle(n).getPropertyValue('--game-accent');const expected=c.fillStyle;c.fillStyle=getComputedStyle(n.matches('.game-list .game-item')?n:n.querySelector('.game-card')).backgroundColor;return {actual:c.fillStyle,expected};});expect(fill.actual).toBe(fill.expected);
  await page.screenshot({path:`.impeccable/review/library-${layout}-refined.png`});await page.getByRole('button',{name:'Clear selection',exact:true}).click();
  expect(await page.locator('#content').evaluate(n=>n.scrollWidth<=n.clientWidth+1)).toBe(true);
 }
 await page.locator('.game-card').first().click();
 expect(await page.locator('.details-layout').evaluate(n=>getComputedStyle(n,'::before').left)).toBe('0px');
 const hero=await page.locator('.hero-artwork').boundingBox(),frame=await page.locator('#content').boundingBox();expect(Math.abs(hero.x-frame.x)).toBeLessThan(1);expect(Math.abs(hero.width-frame.width)).toBeLessThan(1);
 await page.getByRole('button',{name:'DLSS Files',exact:true}).click();expect(await page.locator('.detail-body h3').first().evaluate(n=>getComputedStyle(n).color)).toBe(await page.locator('body').evaluate(n=>getComputedStyle(n).color));
 for(const theme of ['clear','dark','light'])for(const accent of ['#ff473a','#ffd950','#ffffff','#000000','#17ff67','#307de8','#dc5ed1']){
  await page.emulateMedia({reducedMotion:'reduce'});await page.evaluate(({theme,accent})=>{document.documentElement.dataset.theme=theme;document.querySelector('#content').style.setProperty('--accent',accent);},{theme,accent});
  const selected=page.locator('.detail-nav button[aria-pressed=true]');
  expect(await selected.evaluate(n=>getComputedStyle(n).color)).toContain('color(srgb');
  const shadow=await selected.evaluate(n=>getComputedStyle(n).textShadow);if(theme==='light')expect(shadow).toBe('none');else expect(shadow).toMatch(/0px 1px 2px/);
  expect(await selected.locator('.icon').evaluate(n=>getComputedStyle(n).filter)).toBe('none');
 }
 await page.evaluate(()=>{document.documentElement.dataset.theme='clear';document.querySelector('#content').style.setProperty('--accent','#ff473a');});
 await page.screenshot({path:'.impeccable/review/sidebar-accent-refined.png'});
 await nav('Settings').click();await page.waitForTimeout(200);const select=page.locator('#details-navigation');
 await select.click();await expect(page.getByRole('listbox')).toBeVisible();
 const field=await select.boundingBox(),menu=await page.getByRole('listbox').boundingBox();expect(Math.abs(field.width-menu.width)).toBeLessThan(1);
 expect(await select.evaluate(n=>getComputedStyle(n).fontSize)).toBe(await page.getByRole('listbox').evaluate(n=>getComputedStyle(n).fontSize));
 await page.screenshot({path:'.impeccable/review/select-menu-refined.png'});
 await page.keyboard.press('Escape');await expect(select).toBeFocused();await expect(page.getByRole('listbox')).toHaveCount(0);
 await select.press('Enter');await page.keyboard.press('End');await page.keyboard.press('Enter');await expect(select).toHaveValue('tabs');
 await nav('Library').click();await page.locator('.game-card').first().click();await page.getByRole('button',{name:'Appearance',exact:true}).click();
 const materials=await page.locator('.detail-body>section').evaluateAll(nodes=>nodes.map(n=>({background:getComputedStyle(n).backgroundColor,filter:getComputedStyle(n).backdropFilter})));expect(new Set(materials.map(n=>n.background)).size).toBe(1);expect(materials.every(n=>n.filter==='none')).toBe(true);
 await page.screenshot({path:'.impeccable/review/appearance-material-consistent.png'});
 expect(errors).toEqual([]);
 console.log(JSON.stringify({passed:true,checks:['whole-card scaling with stationary artwork within card','neutral idle and hover titles; accent selection','checkbox selection','three Library views fit','full-width sidebar tint and hero artwork','neutral subheaders','soft accent labels with faint shadow; no light-theme shadow','custom menu width and typography','keyboard menu selection and dismissal','no page errors']}));
}finally{await browser.close();}
