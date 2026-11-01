import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:960},reducedMotion:'reduce'});const failures=[];page.on('pageerror',error=>failures.push(error.message));
await page.route('**/api/snapshot',async route=>{const response=await route.fetch();const data=await response.json();data.games=data.games.slice(0,3).map((game,index)=>({...game,accent:['#307de8','#dc5ed1',undefined][index],...(index===2?{appid:null,localArtwork:[],art:null,capsule:null,hero:null,artworkAccent:null}:{})}));await route.fulfill({json:data});});
const nav=name=>page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true});
const accent=()=>page.locator('#content').evaluate(node=>getComputedStyle(node).getPropertyValue('--accent').trim());
const open=async index=>{await nav('Library').click();await page.locator('.game-card').nth(index).click();};
try{
 await page.goto('http://127.0.0.1:1420');await page.waitForSelector('.game-card');
 await open(0);expect(await accent()).toBe('#307de8');
 await page.getByRole('button',{name:'Appearance',exact:true}).click();await expect(page.getByRole('button',{name:'Light',exact:true})).toHaveCount(0);
 await page.getByRole('switch',{name:'Accent tint',exact:true}).click();
 // Shell CSS changes must not inherit into the active Details workspace.
 await page.evaluate(()=>document.documentElement.style.setProperty('--accent','#10ff20'));expect(await accent()).toBe('#307de8');
 await open(1);expect(await accent()).toBe('#dc5ed1');
 await open(2);expect(await accent()).toBe('#d8d5ce');expect(await page.locator('.details-layout').evaluate(n=>getComputedStyle(n,':before').opacity)).toBe('0');
 await nav('Settings').click();await page.locator('#accent-color').fill('#21dd34');await open(0);expect(await accent()).toBe('#307de8');
 await nav('Library').click();expect(await accent()).toBe('#21dd34');
 await open(1);await page.getByRole('button',{name:'Features',exact:true}).click();
 const expanded=await page.locator('.details-hero').evaluate(n=>n.getBoundingClientRect().height);expect(expanded).toBeGreaterThanOrEqual(240);expect(expanded).toBeLessThanOrEqual(300);
 await page.locator('.details-scroll').evaluate(n=>n.scrollTop=1000);await page.waitForTimeout(80);
 const compact=await page.locator('.details-hero').evaluate(n=>n.getBoundingClientRect().height);expect(compact).toBe(128);
 await page.screenshot({path:'.impeccable/review/details-collapsed.png'});
 // The short DLSS section previously ran out of scroll room before full
 // collapse. Back must remain actionable, with the banner fully faded out.
 for (const viewport of [{width:1440,height:990},{width:1440,height:1200},{width:960,height:900}]) {
  await page.setViewportSize(viewport);
  await open(0);
  for (const section of ['DLSS Files','Notes','Overview','Features','Tools','Appearance']) {
   await page.getByRole('navigation',{name:'Game details',exact:true}).getByRole('button',{name:section,exact:true}).click();
   await page.locator('.details-scroll').evaluate(n=>n.scrollTop=1e6);
   await expect.poll(()=>page.locator('.details-hero').evaluate(n=>n.getBoundingClientRect().height)).toBe(128);
   const back=page.getByRole('button',{name:'Back to Library',exact:true});
   await expect(back).toBeVisible();await back.click({trial:true});
   expect(await page.locator('.details-hero-image').evaluate(n=>getComputedStyle(n).opacity)).toBe('0');
   const backBox=await back.boundingBox(), posterBox=await page.locator('.detail-artwork').boundingBox();
   expect(backBox.x+backBox.width).toBeLessThan(posterBox.x);
  }
  await page.getByRole('button',{name:'Back to Library',exact:true}).click();
  await expect(page.locator('.game-card')).toHaveCount(3);
 }
 await page.setViewportSize({width:1440,height:990});await open(0);
 expect(await page.locator('.detail-artwork-light.glow-core').evaluate(n=>getComputedStyle(n).opacity)).toBe('0.6');
 expect(await page.locator('.detail-artwork>.detail-poster').evaluate(n=>getComputedStyle(n).borderTopColor)).toBe('rgb(48, 125, 232)');
 await page.getByRole('navigation',{name:'Game details',exact:true}).getByRole('button',{name:'DLSS Files',exact:true}).click();
 await page.locator('.details-scroll').evaluate(n=>n.scrollTop=1e6);
 await expect.poll(()=>page.locator('.details-hero').evaluate(n=>n.getBoundingClientRect().height)).toBe(128);
 await page.screenshot({path:'.impeccable/review/details-files-compact-fixed.png'});
 expect(await page.locator('.detail-artwork').evaluate(n=>n.getBoundingClientRect().height)).toBe(56);
 const centered=await page.locator('.details-hero').evaluate(hero=>{const box=hero.getBoundingClientRect();return ['.back','.detail-artwork','.details-title-copy'].map(selector=>{const r=hero.querySelector(selector).getBoundingClientRect();return Math.abs(r.y+r.height/2-box.y-box.height/2);});});
 expect(centered.every(offset=>offset<1)).toBe(true);
 await nav('Settings').click();await page.getByRole('button',{name:'Light',exact:true}).click();await open(1);expect(await accent()).toBe('#dc5ed1');
 await page.getByRole('button',{name:'Overview',exact:true}).click();await page.screenshot({path:'.impeccable/review/details-light-compact.png'});
 await nav('Settings').click();await page.locator('#details-navigation').selectOption('sidebar');await open(0);
 await page.getByRole('navigation',{name:'Game details',exact:true}).getByRole('button',{name:'DLSS Files',exact:true}).click();
 await page.locator('.details-scroll').evaluate(n=>n.scrollTop=1e6);
 await expect.poll(()=>page.locator('.details-hero').evaluate(n=>n.getBoundingClientRect().height)).toBe(128);
 const rail=await page.locator('.detail-nav').boundingBox(),workspace=await page.locator('.details-scroll').boundingBox();
 expect(rail.width).toBeLessThan(240);expect(workspace.x).toBeGreaterThan(rail.x+rail.width);
 await page.getByRole('button',{name:'Back to Library',exact:true}).click();await expect(page.locator('.game-card').first()).toBeFocused();
 expect(failures).toEqual([]);console.log(JSON.stringify({passed:true,checks:['two distinct configured game accents','no game accent neutral','shell accent edit while Details active','return to Library restores shell accent','Details has no global theme picker','Details-only tint disabled when no game accent','Clear/Light preserve game accent','compact240-300px hero collapses to128px','no page errors']}));
}finally{await browser.close();}
