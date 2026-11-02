import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:990},reducedMotion:'reduce'}),errors=[];
page.on('pageerror',error=>errors.push(error.message));
let release;const delayed=new Promise(resolve=>release=resolve);
await page.route('**/api/snapshot',async route=>{await delayed;await route.continue();});
const nav=name=>page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true});
const shot=name=>page.screenshot({path:'.impeccable/review/'+name+'.png'});
const noOverflow=async()=>expect(await page.evaluate(()=>[...document.querySelectorAll('main,.main-nav,.setting-group,.inner-card,.background-picker')].filter(n=>n.scrollWidth>n.clientWidth+2).map(n=>n.className))).toEqual([]);
try{
 await page.goto('http://127.0.0.1:1420');await expect(page.locator('.skeleton-card')).toHaveCount(14);await expect(page.locator('.library-skeleton')).toHaveAttribute('aria-busy','true');await shot('library-skeleton');release();await page.waitForSelector('.game-card');
 const header=await page.locator('.app-header').evaluate(n=>({bg:getComputedStyle(n).backgroundColor,shadow:getComputedStyle(n).boxShadow}));expect(header.bg).toBe('rgba(0, 0, 0, 0)');expect(header.shadow).toBe('none');
 const frame=await page.locator('.app-header').boundingBox(),island=await page.locator('.main-nav').boundingBox();expect(Math.abs(island.x+island.width/2-frame.x-frame.width/2)).toBeLessThan(2);await shot('nav-island-library');
 await page.getByRole('button',{name:'More options',exact:true}).click();await expect(page.locator('#shell-menu')).toBeVisible();await expect(page.getByRole('menuitem',{name:'Desktop mode',exact:true})).toBeDisabled();await expect(page.getByRole('menuitem',{name:'Exit rtxForge',exact:true})).toBeDisabled();await shot('nav-island-menu');await page.keyboard.press('Escape');
 await nav('Settings').click();await shot('appearance-grouped');const swatch=await page.locator('#accent-color').boundingBox();expect(swatch.width).toBe(44);expect(swatch.height).toBe(44);
 await page.locator('#background-image-file').setInputFiles('public/app-hero-light.png');await expect(page.locator('html')).toHaveAttribute('data-custom-background','true');expect((await page.evaluate(()=>JSON.parse(localStorage.getItem('rtxforge-game-mode-prototype')).background)).length).toBeLessThan(1600000);
 await page.reload();await page.waitForSelector('.game-card');await expect(page.locator('html')).toHaveAttribute('data-custom-background','true');await nav('Settings').click();await page.getByRole('button',{name:'Use default',exact:true}).click();await expect(page.locator('html')).toHaveAttribute('data-custom-background','false');
 await page.getByRole('button',{name:'Light',exact:true}).click();expect(await page.locator('#scene').evaluate(n=>getComputedStyle(n).backgroundImage)).toContain('app-hero-light.png');await shot('appearance-light-hero');
 await page.getByRole('button',{name:'Clear',exact:true}).click();
 for(const width of [1440,960,390]){await page.setViewportSize({width,height:width===390?844:990});await noOverflow();if(width===390)await shot('appearance-grouped-narrow');}
 await page.setViewportSize({width:1440,height:990});await page.getByRole('navigation',{name:'Settings sections'}).getByRole('button',{name:'Library',exact:true}).click();await shot('library-folder-sgdb-polish');
 await nav('Library').click();await page.locator('.game-card').first().click();await expect(page.locator('.details-page')).toBeVisible();await page.locator('.details-scroll').evaluate(n=>n.scrollTop=180);await expect(page.locator('.details-scroll')).toHaveClass(/scroll-fade/);await expect.poll(async()=>parseFloat(await page.locator('.details-scroll').evaluate(n=>getComputedStyle(n).getPropertyValue('--fade-top')))).toBeGreaterThan(0);await shot('details-accent-fade');
 expect(errors).toEqual([]);console.log(JSON.stringify({passed:true,checks:['14 noninteractive loading skeletons','centered nav island; bare header','menu layers and safe native entries','circular color swatch','custom background choose/persist/default','Light uses approved light hero','Appearance groups desktop/narrow overflow','Details edge fade']}));
}finally{release();await browser.close();}
