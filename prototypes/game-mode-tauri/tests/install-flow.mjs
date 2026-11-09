import {libraryFixture} from './ui-fixture.mjs';
import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({...(process.env.RTXFORGE_BROWSER?{channel:process.env.RTXFORGE_BROWSER}:{}),headless:true});
const page=await browser.newPage({viewport:{width:1440,height:990},reducedMotion:'reduce'}),calls=[],errors=[];
page.on('pageerror',error=>errors.push(error.message));
let source,prepareRelease,executeRelease,progressId,mode='ready',installed=false;
await page.addInitScript(()=>{window.fixtureEvents=[];window.EventSource=class{constructor(){window.fixtureEvents.push(this);queueMicrotask(()=>this.onopen?.());}close(){this.onmessage=null;}};});
await page.route('**/api/snapshot',async route=>{const response=await route.fetch();source=process.env.RTXFORGE_UI_FIXTURE?libraryFixture():await response.json();source.defaults.runtime_provider='skynizz';source.defaults.default_profile='nr-mfg';await route.fulfill({json:source});});
await page.route('**/api/engine/status',route=>route.fulfill({json:{enabled:true,reason:'Fixture only; no files changed.'}}));
await page.route('**/api/engine',async route=>{
 const request=route.request().postDataJSON();calls.push(request);let result={};
 if(request.method==='scan_game')result=[{name:source.games[0].name,game:source.games[0].path,exe:'fixture.exe',runtime_provider:'skynizz',feature_mode:'nr-mfg',installed,nr_strength:2,feature_controls:{enabled:1,intensity:2},dynamic_mfg_available:true}];
 else if(request.method==='nr_catalog')result={install_choices:[{label:'Characters + world',setup:{character:{addon:'shortfuse'}},adapt:true}]};
 else if(request.method==='nr_review')result={token:'exact-nr-review',title:'Review Split Render',action:'Install Split Render',rows:[{game:source.games[0].path,name:source.games[0].name,summary:'Environment: Skynizz · Character detail: ShortFuse',details:'Add renodx-dlss.addon64'}]};
 else if(request.method==='run'&&request.params.token==='exact-nr-review')result={message:'Split Render installed in 1 game.'};
 else if(['prepare_routes','prepare_dlss'].includes(request.method)){
  if(mode==='delayed')await new Promise(resolve=>prepareRelease=resolve);
  const game=source.games[0];result={token:'exact-install-review',title:request.method==='prepare_dlss'?'Review DLSS update':'Review Installation',action:request.params.operation==='uninstall'?'Restore files':'Install Features',summary:'NR + MFG · reviewed startup settings',rows:mode==='empty'?[]:[{game:game.path,name:game.name,summary:'NR + MFG · managed package',details:'Fixture technical details, no files changed.'}],blocked:[{name:'Unsupported fixture',reason:'No compatible runtime for this executable.'}],warnings:[{name:'Offline use',reason:'Keep this change outside online multiplayer.'}],trust:'I understand the offline-use requirement.'};
  if(mode==='empty')result.supported=[{token:'exact-nr-subset',nr:true,mfg:false,reason:'Only NR is supported.',rows:[{name:game.name,game:game.path}]}];
 }else if(['execute_routes','update_dlss'].includes(request.method)){
  progressId=request.id;await new Promise(resolve=>executeRelease=resolve);
  if(mode==='failure'){await route.fulfill({json:{error:'The package could not be verified. Original files were kept.'}});return;}
  result=mode==='cancelled'?{cancelled:true,completed_batches:0,message:'Cancelled safely. No files were changed.'}:{message:'Reviewed installation completed.',completed_batches:1,reports:[{name:source.games[0].name,status:'Fixture complete'}]};
 }
 await route.fulfill({json:{result}});
});
const click=name=>page.getByRole('button',{name,exact:true}).click();
const waitForPrepare=()=>expect.poll(()=>Boolean(prepareRelease)).toBe(true);
const waitForExecution=()=>expect.poll(()=>Boolean(executeRelease)).toBe(true);
const finishExecution=async()=>{
 await waitForExecution();
 const release=executeRelease;
 executeRelease=undefined;
 release();
};
const screenshot=name=>process.env.RTXFORGE_CAPTURE_REVIEW?page.screenshot({path:process.env.RTXFORGE_CAPTURE_REVIEW+'/install-'+name+'.png'}):Promise.resolve();
const start=async()=>{await page.locator('.game-card').first().click();await click('Install Features');await expect(page.getByRole('button',{name:'Review games',exact:true})).toBeVisible();};
const overflow=async()=>expect(await page.evaluate(()=>[...document.querySelectorAll('.flow-body,.flow-panel,.startup-group,.flow-review-row,.main-nav')].filter(n=>n.scrollWidth>n.clientWidth+2).map(n=>n.className))).toEqual([]);
try{
 await page.goto((process.env.RTXFORGE_UI_URL||'http://127.0.0.1:1434'));await page.waitForSelector('.game-card');await start();
 expect(calls.filter(c=>c.method==='prepare_routes')).toHaveLength(0);await screenshot('startup');
 await click('Custom');await click('4×');await page.locator('[data-startup-control=intensity]').fill('1.75');await page.locator('[data-startup-control=intensity]').dispatchEvent('change');
 for(const width of [1440,960,390]){await page.setViewportSize({width,height:width===390?844:990});await overflow();if(width===390)await screenshot('startup-narrow');}
 await page.setViewportSize({width:1440,height:990});mode='delayed';await click('Review games');await expect(page.getByRole('heading',{name:'Preparing',exact:true})).toBeVisible();await screenshot('checking');await waitForPrepare();prepareRelease();prepareRelease=undefined;await expect(page.getByRole('heading',{name:'Review Installation',exact:true})).toBeVisible();
 const prepare=calls.find(c=>c.method==='prepare_routes');expect(prepare.params.settings.mfg_multiplier).toBe(4);expect(prepare.params.settings.nr_strength).toBe(1.75);expect(prepare.params.settings.feature_controls.intensity).toBe(1.75);expect(prepare.params.rows[0].game).toBe(source.games[0].path);
 await expect(page.locator('.flow-review-row')).toHaveCount(2);await expect(page.getByRole('button',{name:'Install Features',exact:true})).toBeDisabled();await screenshot('review');await page.getByRole('checkbox',{name:'I understand the offline-use requirement.'}).check();
 await click('Install Features');await expect(page.getByRole('button',{name:'Request cancellation',exact:true})).toBeVisible();await waitForExecution();await page.evaluate(({id,name})=>window.fixtureEvents.forEach(events=>events.onmessage?.({data:JSON.stringify({id,game:name,index:1,total:1,fraction:.42,label:'Verifying package files…'})})),{id:progressId,name:source.games[0].name});await expect(page.getByText('42%',{exact:true})).toBeVisible();await screenshot('progress');
 await page.getByRole('button',{name:'Request cancellation',exact:true}).focus();await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'Request cancellation',exact:true})).toBeFocused();await finishExecution();await expect(page.getByText('Reviewed installation completed.',{exact:true})).toBeVisible();await screenshot('done');await click('Back to game');
 // Empty primary review can only proceed with an explicit supported subset and trust.
 mode='empty';await click('Install Features');await click('Review games');await expect(page.getByRole('heading',{name:'Nothing ready yet',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Install Features',exact:true})).toBeDisabled();await page.locator('[data-supported-token]').check();await expect(page.getByRole('heading',{name:'1 game ready',exact:true})).toBeVisible();await page.locator('#review-trust').check();await click('Install Features');await expect(page.getByRole('button',{name:'Request cancellation',exact:true})).toBeVisible();mode='cancelled';await waitForExecution();await click('Request cancellation');await expect.poll(()=>calls.some(c=>c.method==='cancel_routes'&&c.params.token==='exact-install-review')).toBe(true);await finishExecution();await expect(page.getByText('Cancelled safely. No files were changed.',{exact:true})).toBeVisible();await screenshot('cancelled');expect(calls.filter(c=>c.method==='execute_routes').at(-1).params.supported).toEqual(['exact-nr-subset']);await click('Back to game');
 mode='ready';await click('Install Features');await click('Review games');await page.locator('#review-trust').check();await click('Install Features');await expect(page.getByRole('button',{name:'Request cancellation',exact:true})).toBeVisible();mode='failure';await finishExecution();await expect(page.getByText('The package could not be verified. Original files were kept.',{exact:true})).toBeVisible();await screenshot('error');await click('Back to game');
 mode='ready';await click('Install Features');await click('Review games');
 await page.getByLabel('Split Render').selectOption({label:'Characters + world'});
 await page.locator('#review-trust').check();await click('Install Features');
 await expect(page.getByRole('button',{name:'Request cancellation',exact:true})).toBeVisible();
 expect(calls.some(c=>c.method==='nr_review')).toBe(false);
 await finishExecution();await expect(page.getByRole('heading',{name:'Review Split Render',exact:true})).toBeVisible();
 await expect(page.getByText('Environment: Skynizz · Character detail: ShortFuse')).toBeVisible();
 expect(calls.find(c=>c.method==='nr_review').params.rows.map(row=>row.game)).toEqual([source.games[0].path]);
 expect(calls.some(c=>c.method==='run'&&c.params.token==='exact-nr-review')).toBe(false);
 await click('Install Split Render');await expect(page.getByText('Split Render installed in 1 game.')).toBeVisible();await click('Back to game');
 mode='ready';installed=true;await page.reload();await page.locator('.game-card').first().click();await click('Restore Original Files');await expect(page.getByRole('button',{name:'Restore files',exact:true})).toBeVisible();await screenshot('restore');await click('Back');
 await expect.poll(()=>calls.filter(c=>c.method==='discard_routes').at(-1)?.params.tokens).toEqual(['exact-install-review']);
 expect(errors).toEqual([]);console.log(JSON.stringify({passed:true,checks:['startup before preparation','original runtime units and exact targets','responsive startup controls','checking/progress/results with artwork','real progress events preserve Cancel focus','trust gates and explicit supported subsets','exact cancel/discard tokens','honest cancellation and failure','NR add-ons get a separate review for the exact installed games','restore review','fixture-only no game mutation']}));
}finally{prepareRelease?.();executeRelease?.();await browser.close();}
