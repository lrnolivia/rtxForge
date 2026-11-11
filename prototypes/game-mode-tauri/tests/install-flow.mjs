import {libraryFixture} from './ui-fixture.mjs';
import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({...(process.env.RTXFORGE_BROWSER?{channel:process.env.RTXFORGE_BROWSER}:{}),headless:true});
const page=await browser.newPage({viewport:{width:1440,height:990},reducedMotion:'reduce'}),calls=[],errors=[];
page.on('pageerror',error=>errors.push(error.message));
let source,prepareRelease,executeRelease,splitRelease,progressId,mode='ready',installed=false,splitInstalled=false,feederMode=false,feederSaved=false,savedPreset,splitEnabled=true;
await page.addInitScript(()=>{window.fixtureEvents=[];window.EventSource=class{constructor(){window.fixtureEvents.push(this);queueMicrotask(()=>this.onopen?.());}close(){this.onmessage=null;}};});
await page.route('**/api/snapshot',async route=>{const response=await route.fetch();source=process.env.RTXFORGE_UI_FIXTURE?libraryFixture():await response.json();source.games=source.games.slice(0,3);source.defaults.runtime_provider='skynizz';source.defaults.default_profile='nr-mfg';await route.fulfill({json:source});});
await page.route('**/api/engine/status',route=>route.fulfill({json:{enabled:true,reason:'Fixture only; no files changed.'}}));
await page.route('**/api/engine',async route=>{
 const request=route.request().postDataJSON();calls.push(request);let result={};
 if(request.method==='scan_game'){const game=source.games.find(item=>item.path===request.params.folder)||source.games[0];result=[{name:game.name,game:game.path,exe:'fixture.exe',runtime_provider:'skynizz',feature_mode:'nr-mfg',installed,nr_strength:2,feature_controls:{enabled:1,intensity:2},dynamic_mfg_available:true}];}
 else if(request.method==='nr_catalog')result={
  enabled:splitEnabled,
  addons:[{id:'lecram',name:'Lecram',builds:[{id:'10.8',label:'10.8',default:true}]},{id:'shortfuse',name:'ShortFuse',builds:[{id:'1.0',label:'1.0',default:true},{id:'2.0',label:'2.0'}]}],
  models:[{id:'old',label:'Old DLSS 5 (310.8)'},{id:'new',label:'New DLSS 5 (310.9.16)'}],
  combos:{'characters-and-world':{name:'Characters + world',builtin:true,character:{addon:'shortfuse',model:'new'}},
    ...(savedPreset?{'fixture-preset':savedPreset}:{})},
  preset_packages:[{id:'skynizz',label:'Skynizz NR'},{id:'native',label:'Native DLSS'},{id:'feeder',label:'Feeder NR'}],
  runtime_nr:(request.params.row&&!feederMode)||request.params.package==='skynizz'?{id:'optiscaler',name:'Skynizz'}:null,
  ...(request.params.package==='feeder'?{blocked:'Feeder NR provides the environment.'}:{}),
  ...(feederMode&&request.params.row?{blocked:'Feeder NR provides the environment.',feeder_character:{
    available:true,stamp:'fixture-ini-stamp',passes:feederSaved?4:1,nr_enabled:true,
    options:[1,2,3,4].map(number=>({number,inherited:number!==1&&!(feederSaved&&number===4),
      character:feederSaved&&number===4,skin:-1}))
  }}:{})
 };
 else if(request.method==='feeder_character_apply'){feederSaved=true;result={message:'Pass 4 saved as Character for the next launch.'};}
 else if(request.method==='nr_match')result=request.params.remove
  ? request.params.rows.slice(0,2).map((_,index)=>({index,summary:'Split Render installed'}))
  : request.params.choice.model==='old'?[]:request.params.rows.slice(0,2).map((_,index)=>({index,summary:'Environment: Lecram · Model: 310.9.16'}));
 else if(request.method==='nr_status')result={installed:splitInstalled,setup:splitInstalled?{environment:{addon:'optiscaler'},character:{addon:'shortfuse'}}:undefined};
 else if(request.method==='nr_check')result={ok:true,verified:true};
 else if(request.method==='nr_combo_save'){
  savedPreset={...request.params.combo,name:request.params.name,builtin:false};result={id:'fixture-preset'};
 }
 else if(request.method==='split_render_routes_review'){
  await new Promise(resolve=>splitRelease=resolve);
  result={rows:[{game:source.games[0].path,name:source.games[0].name,summary:'Environment: Skynizz · Character detail: ShortFuse',details:'Add renodx-dlss.addon64'}]};
 }
 else if(request.method==='nr_review'){
  const remove=request.params.remove,rows=request.params.rows||[request.params.row];
  result={token:'exact-nr-review',title:remove?(request.params.rows?'Review Split Render removal':'Remove Split Render'):'Review Split Render',
    action:remove?'Remove Split Render':'Install Split Render',
    rows:rows.map(row=>({game:row.game,name:row.name,summary:remove?'Remove the recorded setup.':'Environment: Skynizz · Character detail: ShortFuse',
      details:remove?'Remove renodx-dlss.addon64':'Add renodx-dlss.addon64'}))};
 }
 else if(request.method==='run'&&request.params.token==='exact-nr-review')result={message:'Split Render installed in 1 game.'};
 else if(['prepare_routes','prepare_dlss'].includes(request.method)){
  if(mode==='delayed')await new Promise(resolve=>prepareRelease=resolve);
  const game=source.games[0];result={token:'exact-install-review',title:request.method==='prepare_dlss'?'Review DLSS update':'Review Installation',action:request.method==='prepare_dlss'?'Update DLSS':request.params.operation==='uninstall'?'Restore files':'Install Features',summary:'NR + MFG · reviewed startup settings',rows:mode==='empty'?[]:[{game:game.path,name:game.name,summary:'NR + MFG · managed package',details:'Fixture technical details, no files changed.'}],blocked:[{name:'Unsupported fixture',reason:'No compatible runtime for this executable.'}],warnings:[{name:'Offline use',reason:'Keep this change outside online multiplayer.'}],trust:'I understand the offline-use requirement.'};
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
const activeStep=()=>page.getByRole('dialog').locator('.flow-steps [aria-current=step]');
const dialogBounds=()=>page.getByRole('dialog').evaluate(dialog=>{
 const rect=dialog.getBoundingClientRect(),flow=dialog.querySelector('.operation-flow').getBoundingClientRect();
 const style=getComputedStyle(dialog);
 return {centerX:rect.left+rect.width/2-innerWidth/2,centerY:rect.top+rect.height/2-innerHeight/2,
  verticalSpace:rect.height-flow.height-parseFloat(style.paddingTop)-parseFloat(style.paddingBottom),
  height:rect.height,inside:rect.top>=0&&rect.bottom<=innerHeight};
});
try{
 await page.goto((process.env.RTXFORGE_UI_URL||'http://127.0.0.1:1434'));await page.waitForSelector('.game-card');
 await page.emulateMedia({reducedMotion:'no-preference'});
 const library=page.locator('#content');
 await library.evaluate(node=>Promise.allSettled(node.getAnimations({subtree:true})
  .filter(animation=>animation.effect.getTiming().iterations!==Infinity).map(animation=>animation.finished)));
 const libraryBefore=await library.boundingBox();
 const firstCard=page.locator('.game-item').first();
 const cardBefore=await firstCard.boundingBox();
 await click('Install Features');
 await expect(page.getByRole('button',{name:'Review games',exact:true})).toBeVisible();
 await expect(page.locator('.main-nav [data-route=library]')).toHaveAttribute('aria-current','page');
 const libraryBehind=await library.boundingBox();
 expect(libraryBehind.x).toBeCloseTo(libraryBefore.x,0);
 expect(libraryBehind.width).toBeCloseTo(libraryBefore.width,0);
 expect((await firstCard.boundingBox()).x).toBeCloseTo(cardBefore.x,0);
 expect(await library.evaluate(node=>node.getAnimations().length)).toBe(0);
 await click('Cancel');
 await page.emulateMedia({reducedMotion:'reduce'});
 await start();
 expect(calls.filter(c=>c.method==='prepare_routes')).toHaveLength(0);
 await expect(activeStep()).toHaveText('1Presets');
 await expect(page.locator('.startup-group').first()).toHaveCSS('padding-top','14px');
 await expect(page.locator('.number-stepper button').first()).toHaveCSS('border-top-left-radius','8px');
 const more=page.locator('.startup-more > summary');
 await expect(more).toHaveCSS('padding-left','12px');
 await expect(more).toHaveCSS('border-top-left-radius','10px');
 await more.press('Enter');
 await expect(more).toHaveCSS('outline-offset','-2px');
 await expect(page.locator('.startup-more .startup-group').first()).toHaveCSS('padding-top','14px');
 await more.press('Enter');
 await screenshot('startup');
 await click('Custom');await click('4×');await page.locator('[data-startup-control=intensity]').fill('1.75');await page.locator('[data-startup-control=intensity]').dispatchEvent('change');
 for(const width of [1440,960,390]){await page.setViewportSize({width,height:width===390?844:990});await overflow();if(width===390)await screenshot('startup-narrow');}
 await page.setViewportSize({width:1440,height:990});mode='delayed';await click('Review games');
 await expect(page.getByRole('heading',{name:'Preparing',exact:true})).toBeVisible();
 await expect(activeStep()).toHaveText('2Review games');
 const compact=await dialogBounds();
 expect(compact.verticalSpace).toBeCloseTo(0,0);
 for(const viewport of [{width:1440,height:990},{width:480,height:400}]){
  await page.setViewportSize(viewport);
  const bounds=await dialogBounds();
  expect(bounds.centerX).toBeCloseTo(0,0);
  expect(bounds.centerY).toBeCloseTo(0,0);
  expect(bounds.inside).toBe(true);
  await expect(page.getByRole('button',{name:'Cancel',exact:true})).toBeInViewport();
 }
 await page.setViewportSize({width:1440,height:990});
 await screenshot('checking');await waitForPrepare();prepareRelease();prepareRelease=undefined;
 await expect(page.getByRole('heading',{name:'Review Installation',exact:true})).toBeVisible();
 const prepare=calls.find(c=>c.method==='prepare_routes');expect(prepare.params.settings.mfg_multiplier).toBe(4);expect(prepare.params.settings.nr_strength).toBe(1.75);expect(prepare.params.settings.feature_controls.intensity).toBe(1.75);expect(prepare.params.rows[0].game).toBe(source.games[0].path);
 await expect(page.locator('.flow-review-row')).toHaveCount(2);await expect(page.getByRole('button',{name:'Install Features',exact:true})).toBeDisabled();await screenshot('review');await page.getByRole('checkbox',{name:'I understand the offline-use requirement.'}).check();
 await click('Install Features');await expect(page.getByRole('button',{name:'Request cancellation',exact:true})).toBeVisible();await waitForExecution();await page.evaluate(({id,name})=>window.fixtureEvents.forEach(events=>events.onmessage?.({data:JSON.stringify({id,game:name,index:1,total:1,fraction:.42,label:'Verifying package files…'})})),{id:progressId,name:source.games[0].name});await expect(page.getByText('42%',{exact:true})).toBeVisible();await screenshot('progress');
 await page.getByRole('button',{name:'Request cancellation',exact:true}).focus();await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'Request cancellation',exact:true})).toBeFocused();await finishExecution();await expect(page.getByText('Reviewed installation completed.',{exact:true})).toBeVisible();await screenshot('done');await click('Back to game');
 // Empty primary review can only proceed with an explicit supported subset and trust.
 mode='empty';await click('Install Features');await click('Review games');await expect(page.getByRole('heading',{name:'Nothing ready yet',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Install Features',exact:true})).toBeDisabled();await page.locator('[data-supported-token]').check();await expect(page.getByRole('heading',{name:'1 game ready',exact:true})).toBeVisible();await page.locator('#review-trust').check();await click('Install Features');await expect(page.getByRole('button',{name:'Request cancellation',exact:true})).toBeVisible();mode='cancelled';await waitForExecution();await click('Request cancellation');await expect.poll(()=>calls.some(c=>c.method==='cancel_routes'&&c.params.token==='exact-install-review')).toBe(true);await finishExecution();await expect(page.getByText('Cancelled safely. No files were changed.',{exact:true})).toBeVisible();await screenshot('cancelled');expect(calls.filter(c=>c.method==='execute_routes').at(-1).params.supported).toEqual(['exact-nr-subset']);await click('Back to game');
 mode='ready';await click('Install Features');await click('Review games');await page.locator('#review-trust').check();await click('Install Features');await expect(page.getByRole('button',{name:'Request cancellation',exact:true})).toBeVisible();mode='failure';await finishExecution();await expect(page.getByText('The package could not be verified. Original files were kept.',{exact:true})).toBeVisible();await screenshot('error');await click('Back to game');
 mode='ready';await click('Install Features');await click('Review games');
 await page.locator('#review-trust').check();
 await page.locator('#split-install-options summary').click();
 await page.locator('#split-install-preset').selectOption('auto');
 await expect(page.getByRole('button',{name:'Install Features',exact:true})).toBeDisabled();
 await expect.poll(()=>Boolean(splitRelease)).toBe(true);splitRelease();splitRelease=undefined;
 await expect(page.getByText('Environment: Skynizz · Character detail: ShortFuse')).toBeVisible();
 await expect(page.locator('#review-trust')).toBeChecked();
 const split=calls.find(c=>c.method==='split_render_routes_review');
 expect(split.params).toEqual({token:'exact-install-review',choice:{auto:true,model:'new'},revision:1});
 await click('Install Features');
 await expect(page.getByRole('button',{name:'Request cancellation',exact:true})).toBeVisible();
 await finishExecution();
 await expect(page.getByText('Reviewed installation completed.',{exact:true})).toBeVisible();
 expect(calls.some(c=>c.method==='nr_review')).toBe(false);
 await click('Back to game');
 await click('Packages');
 await page.locator('#split-packages summary').click();
 await page.locator('#split-packages-preset').selectOption('auto');
 await expect(page.locator('[data-nr-target]')).toHaveCount(2);
 await page.getByRole('searchbox',{name:'Search games'}).fill(source.games[0].name);
 await expect(page.locator('[data-nr-target]')).toHaveCount(1);
 await click('Select all results');await expect(page.locator('[data-nr-target]:checked')).toHaveCount(1);
 await click('Review selection');
 await expect(page.getByRole('heading',{name:'Review Split Render',exact:true})).toBeVisible();
 expect(calls.find(c=>c.method==='nr_review').params.rows.map(row=>row.game)).toEqual([source.games[0].path]);
 await click('Back');
 await expect(page.locator('[data-nr-target]:checked')).toHaveCount(1);
 await click('Clear selection');await expect(page.locator('[data-nr-target]:checked')).toHaveCount(0);
 await page.locator('#split-packages-model-old').check();
 await expect(page.getByText('No games can use this setup.')).toBeVisible();
 await expect(page.locator('[data-nr-target]')).toHaveCount(0);
 await click('Presets');
 await expect(page.getByRole('heading',{name:'Split Render Presets',exact:true})).toBeVisible();
 await expect(page.locator('#split-preset-package')).toHaveValue('skynizz');
 await expect(page.locator('#split-presets-environment')).toHaveCount(0);
 await page.locator('#split-preset-package').selectOption('native');
 await expect(page.locator('#split-presets-environment')).toBeVisible();
 await page.locator('#split-preset-package').selectOption('feeder');
 await expect(page.getByText('Open a Feeder game’s Tools to assign pass roles.',{exact:false})).toBeVisible();
 await page.locator('#split-preset-package').selectOption('skynizz');
 await page.locator('#split-presets-preset').selectOption('characters-and-world');
 await expect(page.locator('#split-presets-character-build')).toBeVisible();
 await page.locator('#split-presets-character-build').selectOption('2.0');
 await page.locator('#split-preset-name').fill('My character detail');
 await screenshot('split-presets');
 await click('Save preset');
 await expect(page.locator('#split-presets-preset option[value=fixture-preset]')).toHaveText('My character detail');
 expect(calls.find(c=>c.method==='nr_combo_save').params).toMatchObject({package:'skynizz',name:'My character detail',
   combo:{environment:{addon:'optiscaler'},character:{addon:'shortfuse',build:'2.0'}}});
 await click('Library');await page.locator('.game-card').first().click();await click('Tools');
 await expect(page.locator('#split-tools-preset')).toBeVisible();
 await expect(page.locator('#split-tools-character-build')).toHaveCount(0);
 await expect(page.locator('#split-preset-name')).toHaveCount(0);
 await page.locator('#split-tools-preset').selectOption('fixture-preset');
 await expect(page.getByRole('button',{name:'Review Split Render',exact:true})).toBeEnabled();
 await screenshot('split-tools');
 await click('Review Split Render');
 await expect(page.getByRole('heading',{name:'Review Split Render',exact:true})).toBeVisible();
 await expect(page.locator('.flow-review-row input[type=checkbox]')).toHaveCount(0);
 await click('Back');
 expect(calls.filter(c=>c.method==='nr_review').at(-1).params.row.game).toBe(source.games[0].path);
 splitInstalled=true;await click('Overview');await click('Tools');
 await expect(page.getByText('Installed · Environment: Skynizz · Character detail: ShortFuse · DLSS 5 model shared with Skynizz')).toBeVisible();
 await click('Remove Split Render');await expect(page.getByRole('heading',{name:'Remove Split Render',exact:true})).toBeVisible();
 expect(calls.filter(c=>c.method==='nr_review').at(-1).params.remove).toBe(true);await click('Back');
 splitInstalled=false;feederMode=true;await click('Overview');await click('Tools');
 await expect(page.getByRole('heading',{name:'Feeder NR passes',exact:true})).toBeVisible();
 await expect(page.locator('[data-feeder-pass]')).toHaveCount(4);
 await page.locator('[data-feeder-pass="4"]').click();
 await page.locator('[data-feeder-role="character"]').click();
 await expect(page.getByText('Full-frame passes · 1 → 4. Extra passes can lower frame rate.')).toBeVisible();
 await expect(page.locator('#feeder-skin')).toHaveValue('-1');
 await screenshot('feeder-character-pass');
 await click('Save pass role');
 expect(calls.find(c=>c.method==='feeder_character_apply').params).toMatchObject(
   {row:{game:source.games[0].path},stamp:'fixture-ini-stamp',pass_number:4,character:true,skin:-1});
 await expect(page.getByRole('button',{name:'Save pass role',exact:true})).toBeDisabled();
 await expect(page.locator('.operation-modal')).toHaveCount(0);
 mode='ready';installed=true;await page.reload();await page.locator('.game-card').first().click();await click('Restore Original Files');
 await expect(page.getByRole('button',{name:'Restore files',exact:true})).toBeVisible();
 await expect(activeStep()).toHaveText('1Review games');
 await expect(page.getByRole('dialog').locator('.flow-steps li').last()).toHaveText('2Restore');
 await screenshot('restore');await click('Back');
 await expect.poll(()=>calls.filter(c=>c.method==='discard_routes').at(-1)?.params.tokens).toEqual(['exact-install-review']);
 await click('Library');
 mode='delayed';await click('Update DLSS');await waitForPrepare();
 await expect(activeStep()).toHaveText('1Review games');
 await expect(page.getByRole('dialog').locator('.flow-steps li')).toHaveCount(2);
 prepareRelease();prepareRelease=undefined;mode='ready';
 await expect(page.getByRole('heading',{name:'Review DLSS update',exact:true})).toBeVisible();
 await expect(activeStep()).toHaveText('1Review games');
 const shortReview=await dialogBounds();
 expect(shortReview.height).toBeLessThan(850);
 expect(shortReview.centerY).toBeCloseTo(0,0);
 await page.setViewportSize({width:480,height:400});
 const cappedReview=await dialogBounds();
 expect(cappedReview.inside).toBe(true);
 expect(cappedReview.centerY).toBeCloseTo(0,0);
 expect(await page.locator('.flow-body').evaluate(node=>node.scrollHeight>node.clientHeight)).toBe(true);
 await expect(page.getByRole('dialog').getByRole('button',{name:'Update DLSS',exact:true})).toBeInViewport();
 await page.setViewportSize({width:1440,height:990});
 await page.locator('#review-trust').check();
 const reviewWidth=(await page.getByRole('dialog').boundingBox()).width;
 await page.getByRole('dialog').getByRole('button',{name:'Update DLSS',exact:true}).click();
 await expect(activeStep()).toHaveText('2Update DLSS');
 expect((await page.getByRole('dialog').boundingBox()).width).toBeCloseTo(reviewWidth,0);
 await finishExecution();await expect(page.getByText('Reviewed installation completed.',{exact:true})).toBeVisible();
 await expect(page.getByRole('dialog',{name:'Done',exact:true}).locator('.flow-heading')).toHaveCount(0);
 expect((await page.getByRole('dialog').boundingBox()).width).toBeCloseTo(reviewWidth,0);
 await click('Back to game');
 splitEnabled=false;await click('Packages');
 await expect(page.getByText('New setups are paused while performance and image quality are improved.')).toBeVisible();
 await expect(page.getByText('Choose games',{exact:true})).toHaveCount(0);
 await click('Remove Split Render');
 const picker=page.getByRole('dialog',{name:'Remove Split Render',exact:true});
 await expect(picker).toBeVisible();
 await expect(activeStep()).toHaveText('1Choose games');
 await page.keyboard.press('ArrowDown');
 await expect(picker.getByRole('searchbox',{name:'Search games'})).toBeFocused();
 await expect(picker.locator('[data-nr-target]')).toHaveCount(2);
 await click('Select all');
 await expect(picker.locator('[data-nr-target]:checked')).toHaveCount(2);
 await expect(picker.getByRole('button',{name:'Review selection'})).toBeInViewport();
 expect(await picker.locator('.nr-target-choice').evaluateAll(rows=>rows.every(row=>
   row.querySelector('.flow-thumbnail').getBoundingClientRect().right <=
   row.querySelector('.split-game-title').getBoundingClientRect().left))).toBe(true);
 await screenshot('bulk-removal-picker');
 await page.setViewportSize({width:480,height:400});
 await expect(picker.getByRole('button',{name:'Review selection'})).toBeInViewport();
 await expect(picker.getByRole('searchbox',{name:'Search games'})).toBeInViewport();
 await expect(page.locator('#toast')).toHaveCSS('z-index','49');
 await page.setViewportSize({width:1440,height:990});
 await click('Review selection');
 await expect(page.getByRole('heading',{name:'Review Split Render removal',exact:true})).toBeVisible();
 await expect(activeStep()).toHaveText('2Review games');
 await page.setViewportSize({width:480,height:400});
 await expect(page.getByRole('button',{name:'Remove Split Render',exact:true})).toBeInViewport();
 await page.setViewportSize({width:1440,height:990});
 await expect(page.getByRole('button',{name:'Remove Split Render',exact:true})).toBeEnabled();
 expect(calls.filter(c=>c.method==='nr_review').at(-1).params).toMatchObject(
   {remove:true,rows:source.games.slice(0,2).map(game=>({game:game.path}))});
 const details=page.getByRole('region',{name:'Details for '+source.games[0].name,exact:true});
 const infoButton=page.getByRole('button',{name:'Show details for '+source.games[0].name,exact:true});
 await infoButton.hover();
 await expect(infoButton).toHaveCSS('outline-style','none');
 await expect(infoButton).toHaveCSS('background-color','rgba(0, 0, 0, 0)');
 await infoButton.click();
 await expect(details).toContainText('Remove renodx-dlss.addon64');
 await expect(details).toBeInViewport();
 await screenshot('bulk-removal-review');
 await page.keyboard.press('Escape');
 await expect(details).toBeHidden();
 await expect(page.getByRole('heading',{name:'Review Split Render removal',exact:true})).toBeVisible();
 await click('Back');
 await expect(picker.locator('[data-nr-target]:checked')).toHaveCount(2);
 await page.keyboard.press('Escape');
 await expect(picker).toBeHidden();
 await expect(page.getByRole('button',{name:'Remove Split Render',exact:true})).toBeFocused();
 await click('Presets');
 await expect(page.getByRole('heading',{name:'Split Render Presets',exact:true})).toHaveCount(0);
 expect(errors).toEqual([]);console.log(JSON.stringify({passed:true,checks:['startup before preparation','original runtime units and exact targets','responsive startup controls','compact and centered progress with stationary library','DLSS, restore and Split Render step indicators','checking/progress/results with artwork','real progress events preserve Cancel focus','trust gates and explicit supported subsets','exact cancel/discard tokens','honest cancellation and failure','Split Render reviewed before one install run','compatibility filtering and bulk controls in Packages','package-specific preset editor feeds install-only Tools','per-game Tools review without selection checkboxes','Feeder can assign Character to any full-frame pass','restore review','fixture-only no game mutation']}));
}finally{prepareRelease?.();executeRelease?.();splitRelease?.();await browser.close();}
