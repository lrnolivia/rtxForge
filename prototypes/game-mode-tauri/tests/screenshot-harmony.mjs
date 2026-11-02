import {chromium,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({reducedMotion:'reduce',viewport:{width:1440,height:960}}),calls=[];
const thumbnail=color=>'data:image/svg+xml,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="${color}"/></svg>`);
await page.route('**/api/snapshot',async route=>{const data=await(await route.fetch()).json();data.games=data.games.filter(g=>g.appid==='1091500').map(g=>({...g,accent:'#269ee5',localArtwork:[]}));await route.fulfill({json:data});});
await page.route('**/api/store-screenshots?appid=1091500',route=>route.fulfill({json:{screenshots:[{id:'1',full:'red-fixture',thumbnail:thumbnail('#d34a32')},{id:'9',full:'blue-fixture',thumbnail:thumbnail('#247ec3')}]}}));
const image='data:image/png;base64,'+readFileSync(new URL('../public/app-hero-light.png',import.meta.url)).toString('base64');
await page.route('**/api/store-background?*',route=>{calls.push(new URL(route.request().url()).searchParams.get('screenshot'));return route.fulfill({json:{image}});});
const open=async()=>{await page.locator('.game-card').first().click();await expect(page.locator('#scene')).toHaveAttribute('data-background-state','ready');};
try{
 await page.goto('http://127.0.0.1:1420');await page.waitForSelector('.game-card');expect(calls).toEqual([]);await open();await expect(page.locator('#scene')).toHaveAttribute('data-screenshot-id','9');expect(calls).toEqual(['9']);
 await page.getByRole('button',{name:'Appearance',exact:true}).click();await page.locator('[data-background-shot="1"]').click();await expect(page.locator('#scene')).toHaveAttribute('data-screenshot-id','1');expect(calls).toEqual(['9','1']);
 await page.reload();await page.waitForSelector('.game-card');await open();await expect(page.locator('#scene')).toHaveAttribute('data-screenshot-id','1');expect(calls).toEqual(['9','1','1']);
 console.log(JSON.stringify({passed:true,checks:['blue accent chooses the blue thumbnail palette over red','only the winning full-size image loads','explicit screenshot selection persists and overrides harmony']}));
}finally{await browser.close();}
