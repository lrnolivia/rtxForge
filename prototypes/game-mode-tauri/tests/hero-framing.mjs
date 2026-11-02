import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({channel:process.env.RTXFORGE_BROWSER||'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1080},reducedMotion:'reduce'});
const errors=[];page.on('pageerror',error=>errors.push(error.message));
await page.addInitScript(()=>{window.pad={id:'Xbox framing fixture',mapping:'standard',axes:[0,0],buttons:Array.from({length:17},()=>({pressed:false}))};navigator.getGamepads=()=>[window.pad];});
await page.route('**/api/snapshot',async route=>{const source=await(await route.fetch()).json();source.games=source.games.slice(0,1).map(g=>({...g,heroFocus:[.72,.48]}));await route.fulfill({json:source});});
const press=async index=>{await page.evaluate(i=>window.pad.buttons[i].pressed=true,index);await page.waitForTimeout(65);await page.evaluate(i=>window.pad.buttons[i].pressed=false,index);await page.waitForTimeout(55);};
const open=async()=>{await page.locator('.game-card').first().click();await page.getByRole('button',{name:'Appearance',exact:true}).click();await expect(page.locator('.hero-focal-preview')).toBeVisible();await expect(page.locator('.details-hero-image')).toHaveJSProperty('complete',true);};
try{
  await page.goto('http://127.0.0.1:1420');await page.waitForSelector('.game-card');await open();
  const x=page.getByRole('slider',{name:'Horizontal hero focal point'}),y=page.getByRole('slider',{name:'Vertical hero focal point'});
  await expect(x).toHaveValue('72');await expect(y).toHaveValue('48');
  const initial=await page.locator('.hero-focal-preview img').evaluate(n=>n.style.objectPosition);
  await x.focus();await page.keyboard.press('ArrowRight');await expect(x).toHaveValue('73');await page.keyboard.press('ArrowDown');await expect(y).toBeFocused();await expect(y).toHaveValue('48');
  await page.keyboard.press('ArrowRight');await expect(y).toHaveValue('49');await page.keyboard.press('ArrowUp');await expect(x).toBeFocused();
  await page.evaluate(()=>window.dispatchEvent(new Event('gamepadconnected')));await press(15);await expect(x).toHaveValue('74');await press(13);await expect(y).toBeFocused();await press(15);await expect(y).toHaveValue('50');await press(12);await expect(x).toBeFocused();
  await expect(page.getByRole('button',{name:'Review hero framing',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Use Desktop framing',exact:true}).click();await expect(x).toHaveValue('72');await expect(y).toHaveValue('48');
  await expect(page.locator('.hero-focal-preview img')).toHaveCSS('object-position',initial);
  await x.fill('20');await x.dispatchEvent('input');
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Library',exact:true}).click();await open();await expect(x).toHaveValue('72');
  await page.setViewportSize({width:600,height:900});await x.scrollIntoViewIfNeeded();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const bounds=await page.locator('.hero-focal-preview').evaluate(n=>{const r=n.getBoundingClientRect();return {width:r.width,height:r.height}});expect(bounds.width).toBeGreaterThan(bounds.height);
  expect(errors).toEqual([]);console.log(JSON.stringify({passed:true,checks:['saved Desktop focus honored','keyboard and synthetic controller adjust and switch axes','live crop resets to Desktop','draft discarded on leaving Details','read-only preview cannot save','narrow preview fits']}));
}finally{await browser.close();}
