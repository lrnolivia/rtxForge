import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1280,height:900},reducedMotion:'reduce'});
await page.addInitScript(()=>localStorage.setItem('rtxforge-game-mode-prototype',JSON.stringify({theme:'light',tint:true,appearanceDefaultsVersion:2})));
await page.route('**/api/snapshot',route=>route.fulfill({json:{schema:1,source:'Crop fixture',platform:'windows',readOnly:true,capturedAt:'',games:[{id:'crop',appid:'10',name:'Crop fixture',path:'C:/fixture',source:'Steam',status:'Installed',accent:'#4191af',art:null}],packages:[],warnings:[],libraryCount:1,settingsFound:true,defaults:{},operations:{available:false}}}));
let fixture;
await page.route('**/api/store-screenshots?*',async route=>{
 fixture=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=320;c.height=180;const x=c.getContext('2d');x.fillStyle='#000';x.fillRect(0,0,320,180);x.fillStyle='#418db3';x.fillRect(0,24,320,132);return c.toDataURL('image/png');});
 await route.fulfill({json:{screenshots:[{id:'0',full:'fixture',thumbnail:fixture}]}});
});
await page.route('**/api/store-background?*',route=>route.fulfill({json:{image:fixture}}));
try{
 await page.goto('http://127.0.0.1:1420');await page.locator('.game-card').click();
 await expect(page.locator('#scene')).toHaveAttribute('data-background-state','ready');
 const bounds=await page.locator('#scene').evaluate(n=>{const s=getComputedStyle(n),r=n.getBoundingClientRect();return {height:r.height,size:s.backgroundSize,position:s.backgroundPosition};});
 expect(parseFloat(bounds.size.split(' ')[1])).toBeGreaterThan(bounds.height*1.3);
 expect(parseFloat(bounds.position.split(' ')[1])).toBeLessThan(-bounds.height*.1);
 await page.getByRole('button',{name:'Appearance',exact:true}).click();
 await expect.poll(()=>page.locator('.screenshot-choice img').getAttribute('src')).not.toBe(fixture);
 const sample=await page.locator('.screenshot-choice img').evaluate(async n=>{await n.decode();const c=document.createElement('canvas');c.width=c.height=1;const x=c.getContext('2d');x.drawImage(n,0,0,n.naturalWidth,1,0,0,1,1);return [...x.getImageData(0,0,1,1).data];});
 expect(sample[2]).toBeGreaterThan(120);
 console.log(JSON.stringify({passed:true,backgroundCoversBars:true,pickerCropsBars:true}));
}finally{await browser.close();}
