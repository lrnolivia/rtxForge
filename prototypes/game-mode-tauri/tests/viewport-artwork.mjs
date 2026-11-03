import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1080},reducedMotion:'reduce'});
const art='data:image/svg+xml;base64,'+Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450"><rect width="300" height="450" fill="#ee6633"/></svg>').toString('base64');
await page.route('**/api/snapshot',route=>route.fulfill({json:{schema:1,platform:'Windows',games:Array.from({length:120},(_,index)=>({id:String(index),name:'Fixture '+index,path:'C:/fixture/'+index,appid:null,source:'Manual',status:'Unchecked',art,hero:art,accent:'#ee6633',artworkAccentReady:true})),packages:[],warnings:[],defaults:{},preferences:{},operations:{available:false},capturedAt:new Date().toISOString()}}));
await page.route('**/api/engine/status',route=>route.fulfill({json:{enabled:false}}));
try{
 await page.goto(process.env.RTXFORGE_TEST_URL||'http://127.0.0.1:1420');
 const cards=page.locator('.game-item');await expect(cards).toHaveCount(120);
 await expect.poll(()=>page.locator('.game-item[data-art-visible=true]').count()).toBeGreaterThan(0);
 const bounds=await cards.first().boundingBox();
 const active=await page.locator('.game-item[data-art-visible=true]').count();expect(active).toBeLessThan(60);
 await page.locator('.game-card').last().focus();
 await page.locator('.game-card').last().scrollIntoViewIfNeeded();
 await expect(cards.last()).toHaveAttribute('data-art-visible','true');
 await expect(cards.first()).toHaveAttribute('data-art-visible','false');
 await expect(page.locator('.game-card').last()).toBeFocused();
 await expect(cards.last().locator('.artwork-glow').first()).toHaveCSS('display','block');
 await expect(cards.last()).toHaveCSS('overflow','visible');
 await page.locator('.game-card').first().scrollIntoViewIfNeeded();
 await expect(cards.first()).toHaveAttribute('data-art-visible','true');
 const after=await cards.first().boundingBox();expect(after.width).toBe(bounds.width);expect(after.height).toBe(bounds.height);
 console.log(JSON.stringify({passed:true,total:120,active,checks:['offscreen blur surfaces excluded','focused destination prepared','glow not contained','stable card geometry']}));
}finally{await browser.close();}
