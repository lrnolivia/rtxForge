import {chromium, expect} from '@playwright/test';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
const art='data:image/svg+xml;base64,'+Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450"><rect width="300" height="450" fill="#ae3cec"/></svg>').toString('base64');
let colors={'C:/other':'#112233','C:/fixture':'#ee9933'},pending,fail=false;const calls=[],errors=[];
page.on('pageerror',error=>errors.push(error.message));
await page.route('**/api/snapshot',route=>route.fulfill({json:{schema:1,platform:'Windows',games:[{id:'fixture',name:'Fixture game',path:'C:/fixture',appid:null,source:'Manual',status:'Unchecked',art,hero:art,accent:colors['C:/fixture'],artworkAccent:'#ae3cec',artworkAccentReady:true}],packages:[],warnings:[],defaults:{},preferences:{game_accents:colors},operations:{available:true},capturedAt:new Date().toISOString()}}));
await page.route('**/api/engine/status',route=>route.fulfill({json:{enabled:true}}));
await page.route('**/api/engine',async route=>{
 const request=route.request().postDataJSON();calls.push(request);let result={};
 if(request.method==='settings_get')result={game_accents:colors};
 if(request.method==='scan_game')result=[{game:'C:/fixture',name:'Fixture game',installed:false}];
 if(request.method==='settings_review'){pending=request.params.changes.game_accents;result={token:'appearance-only'};}
 if(request.method==='run'){if(fail){fail=false;return route.fulfill({status:400,json:{error:'Save fixture failed. Try again.'}});}colors=pending;}
 await route.fulfill({json:{result}});
});
try{
 await page.goto(process.env.RTXFORGE_TEST_URL||'http://127.0.0.1:1420');
 await page.locator('.game-card').first().click();
 await page.locator('[data-detail-section="appearance"]').click();
 await expect(page.getByRole('button',{name:'Review accent color',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Choose accent color',exact:true}).click();
 await page.getByRole('textbox',{name:'Accent hex color'}).fill('#ae3cec');
 await expect(page.locator('#content')).toHaveCSS('--accent','#ae3cec');
 expect(colors['C:/fixture']).toBe('#ee9933');
 await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await expect(page.locator('#content')).toHaveCSS('--accent','#ee9933');
 await page.getByRole('button',{name:'Choose accent color',exact:true}).click();
 await page.getByRole('textbox',{name:'Accent hex color'}).fill('#123');
 await page.getByRole('button',{name:'Save color',exact:true}).click();
 await expect(page.getByRole('textbox',{name:'Accent hex color'})).toHaveAttribute('aria-invalid','true');
 expect(calls.filter(call=>call.method==='run')).toHaveLength(0);
 await page.getByRole('textbox',{name:'Accent hex color'}).fill('#8822dd');
 fail=true;await page.getByRole('button',{name:'Save color',exact:true}).click();
 await expect(page.locator('.color-picker-status')).toContainText('Save fixture failed');
 await page.getByRole('button',{name:'Save color',exact:true}).click();
 await expect(page.locator('.color-editor')).toBeHidden();
 expect(colors).toEqual({'C:/other':'#112233','C:/fixture':'#8822dd'});
 await expect(page.getByRole('heading',{name:'Review preferences',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Choose accent color',exact:true}).click();
 const sampler=page.locator('.artwork-sampler');await expect(sampler.locator('canvas')).toHaveAttribute('width','300');
 await sampler.focus();await page.keyboard.press('ArrowRight');await page.keyboard.press('Enter');
 await expect(page.getByRole('textbox',{name:'Accent hex color'})).toHaveValue('#ae3cec');
 await page.getByRole('button',{name:'Save color',exact:true}).click();
 await page.reload();await page.locator('.game-card').first().click();
 await expect(page.locator('#content')).toHaveCSS('--accent','#ae3cec');
 await page.locator('[data-detail-section="tools"]').click();
 await expect(page.getByRole('heading',{name:'ReShade & add-ons',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Install RenoDX',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Remove RenoDX',exact:true})).toBeVisible();
 expect(errors).toEqual([]);
 if(process.env.RTXFORGE_UI_CAPTURE)await page.locator('.reshade-tools').screenshot({path:process.env.RTXFORGE_UI_CAPTURE});
 console.log(JSON.stringify({passed:true,checks:['live preview','cancel rollback','invalid input','failed save retry','other games preserved','persisted color after reload','keyboard artwork sampling','unified ReShade actions']}));
}finally{await browser.close();}
