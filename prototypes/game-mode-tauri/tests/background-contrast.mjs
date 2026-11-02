import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1440,height:960},reducedMotion:'reduce'});
await page.addInitScript(()=>localStorage.setItem('rtxforge-game-mode-prototype',JSON.stringify({theme:'light',tint:true,appearanceDefaultsVersion:2})));
await page.route('**/api/snapshot',async route=>{const data=await(await route.fetch()).json();data.games=data.games.filter(g=>g.appid==='1091500').map(g=>({...g,accent:'#2682a8',localArtwork:[]}));await route.fulfill({json:data});});
const thumb='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#2682a8"/></svg>');
await page.route('**/api/store-screenshots?appid=1091500',route=>route.fulfill({json:{screenshots:[{id:'0',full:'dark-fixture',thumbnail:thumb},{id:'1',full:'light-fixture',thumbnail:thumb}]}}));
await page.route('**/api/store-background?*',async route=>{const light=new URL(route.request().url()).searchParams.get('screenshot')==='1';const image=await page.evaluate(light=>{const canvas=document.createElement('canvas');canvas.width=64;canvas.height=64;const c=canvas.getContext('2d');c.fillStyle=light?'white':'#080b11';c.fillRect(0,0,64,64);return canvas.toDataURL('image/png');},light);await route.fulfill({json:{image}});});
try{
 await page.goto('http://127.0.0.1:1420');await page.waitForSelector('.game-card');await page.locator('.game-card').first().click();await expect(page.locator('#scene')).toHaveAttribute('data-background-state','ready');
 await expect(page.locator('.brand')).toHaveCSS('color','rgb(255, 255, 255)');await expect(page.locator('.scene-wash')).toHaveCSS('opacity','1');
 await expect(page.locator('#scene')).toHaveCSS('filter','blur(1.5px) brightness(0.85) saturate(0.8)');
 const edge=await page.locator('#content').evaluate(n=>getComputedStyle(n).borderTopColor);expect(edge).toContain('/ 0.12');
 await page.getByRole('button',{name:'Appearance',exact:true}).click();await page.locator('[data-background-shot="1"]').click();await expect(page.locator('#scene')).toHaveAttribute('data-screenshot-id','1');await expect(page.locator('.brand')).toHaveCSS('color','rgb(0, 0, 0)');
 console.log(JSON.stringify({passed:true,checks:['Light mode dark photo uses a white wordmark','bright photo uses a dark wordmark','Light screenshot wash and brighter exposure','Light perimeter is subtle game-accent ink']}));
}finally{await browser.close();}
