import {chromium,expect} from '@playwright/test';

const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:990},reducedMotion:'reduce'});
const calls=[],errors=[];page.on('pageerror',error=>errors.push(error.message));
let source,reviewed,positionSupport=true;
const nav=name=>page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true});
const section=name=>page.getByRole('navigation',{name:'Settings sections'}).getByRole('button',{name,exact:true});
await page.route('**/api/snapshot',async route=>{const response=await route.fetch();source=await response.json();if(positionSupport)source.overlayDefaults={...source.overlayDefaults,SidePanelSide:'left',BarPosition:'bottom'};await route.fulfill({json:source});});
await page.route('**/api/engine/status',route=>route.fulfill({json:{enabled:true,reason:'Contract fixture; no actual operations.'}}));
await page.route('**/api/engine',async route=>{
  const request=route.request().postDataJSON();calls.push(request);
  let result;
  if(request.method==='settings_get')result={...source.preferences,overlay_appearance:{...source.overlayDefaults,Layout:'bar',TextSize:26},overlay_helper:true};
  else if(request.method==='settings_review'){reviewed=request.params.changes;result={token:'settings-exact-fixture',title:'Exact settings fixture',rows:Object.entries(reviewed).map(([name,value])=>({name,detail:JSON.stringify(value)}))};}
  else if(request.method==='run'){expect(request.params.token).toBe('settings-exact-fixture');result={message:'Fixture settings confirmed; no files written.'};}
  else if(request.method==='discard')result={};
  else throw new Error('Unexpected fixture request: '+request.method);
  await route.fulfill({json:{result}});
});
try{
 await page.goto('http://127.0.0.1:1420');await page.waitForSelector('.game-card');await nav('Settings').click();
 expect(await page.locator('[data-settings-category]>span:not(.icon)').allTextContents()).toEqual(['Graphics','Overlay','Appearance','Library','Gaming Mode','System','Recovery','About']);
 await expect(page.getByRole('group',{name:'Color theme'})).toBeVisible();
 await section('Graphics').click();await expect(page.getByRole('switch',{name:'Recognize existing features',exact:true})).toBeEnabled();
 await expect(page.getByRole('switch',{name:'Borderless on install',exact:true})).toBeVisible();
 await expect(page.getByRole('combobox',{name:'Default mode',exact:true})).toBeVisible();
 await section('Overlay').click();
 for(const caption of ['Side Panel','Advanced','Bar'])await expect(page.getByRole('button',{name:caption,exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Bar',exact:true})).toHaveAttribute('aria-pressed','true');
 expect(await page.locator('.layout-choice svg').count()).toBe(3);
 await expect(page.getByRole('combobox',{name:'Side Panel position',exact:true})).toHaveCount(0);
 await expect(page.getByRole('combobox',{name:'Bar position',exact:true})).toHaveValue('"bottom"');
 await page.getByRole('combobox',{name:'Bar position',exact:true}).selectOption('"top"');
 await expect(page.locator('[data-overlay-layout="bar"] svg g')).toHaveAttribute('transform','translate(0 104) scale(1 -1)');
 await page.getByRole('button',{name:'Advanced',exact:true}).click();
 await expect(page.getByRole('combobox',{name:/^(Bar|Side Panel) position$/})).toHaveCount(0);
 await page.getByRole('button',{name:'Side Panel',exact:true}).click();
 await expect(page.getByRole('combobox',{name:'Side Panel position',exact:true})).toHaveValue('"left"');
 await expect(page.getByRole('combobox',{name:'Bar position',exact:true})).toHaveCount(0);
 await page.getByRole('combobox',{name:'Side Panel position',exact:true}).selectOption('"right"');
 await expect(page.locator('[data-overlay-layout="floating"] svg g')).toHaveAttribute('transform','translate(180 0) scale(-1 1)');
 await page.getByRole('button',{name:'Light',exact:true}).click();
 await expect(page.getByRole('combobox',{name:'Text size',exact:true})).toHaveValue('26');
 await page.getByRole('switch',{name:'Background overlay helper',exact:true}).click();
 await page.getByRole('button',{name:'Review preferences',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Exact settings fixture',exact:true})).toBeVisible();
 expect(reviewed.overlay_appearance.Layout).toBe('floating');expect(reviewed.overlay_appearance.TextSize).toBe(26);
 expect(reviewed.overlay_appearance.SidePanelSide).toBe('right');expect(reviewed.overlay_appearance.BarPosition).toBe('top');
 expect(reviewed.overlay_appearance.Theme).toBe(1);expect(reviewed.overlay_appearance.Blur).toBe(44);
 expect(reviewed.overlay_theme).toBe('light');expect(reviewed.overlay_helper).toBe(false);
 expect(calls.filter(call=>call.method==='run')).toHaveLength(0);
 await page.getByRole('button',{name:'Confirm changes',exact:true}).click();
 await expect(page.getByRole('button',{name:'Back to game',exact:true})).toBeVisible();
 expect(calls.filter(call=>call.method==='run')).toHaveLength(1);
 await page.getByRole('button',{name:'Back to game',exact:true}).click();
 for(const name of ['Library','Gaming Mode','System','Recovery','About']){await section(name).click();await expect(section(name)).toHaveAttribute('aria-pressed','true');}
 await section('Recovery').click();await expect(page.getByRole('button',{name:/Old NR files/})).toBeVisible();
 await section('Overlay').click();await page.screenshot({path:'.impeccable/review/settings-overlay-desktop.png'});
 for(const width of [1440,960,390]){
  await page.setViewportSize({width,height:width===390?844:990});
  for(const name of ['Graphics','Overlay','Library','Gaming Mode','System','Recovery','About']){
   await section(name).click();
   const overflow=await page.evaluate(()=>[...document.querySelectorAll('main,section,.inner-card,.field,.settings-groups,.settings-tabs,.overlay-layout-choices')].filter(n=>n.scrollWidth>n.clientWidth+2).map(n=>n.className));
   expect(overflow,`${name} at ${width}px`).toEqual([]);
  }
  await section('Overlay').click();if(width===390)await page.screenshot({path:'.impeccable/review/settings-overlay-narrow.png'});
 }
 // Reload with the real read-only status. Saved settings must remain visible,
 // while no shared-setting or engine action can be invoked.
 await page.unroute('**/api/engine/status');await page.reload();await page.waitForSelector('.game-card');await nav('Settings').click();await section('Overlay').click();
 for(const caption of ['Side Panel','Advanced','Bar'])await expect(page.getByRole('button',{name:caption,exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'Review preferences',exact:true})).toBeDisabled();
 positionSupport=false;await page.reload();await page.waitForSelector('.game-card');await nav('Settings').click();await section('Overlay').click();
 await expect(page.getByRole('combobox',{name:/^(Bar|Side Panel) position$/})).toHaveCount(0);
 expect(errors).toEqual([]);
 console.log(JSON.stringify({passed:true,checks:['eight original settings sections','new Appearance preserved','desktop layout preview geometry and source values','overlay theme resets material while retaining layout/text','exact settings token and no execute before confirmation','read-only controls disabled','all sections at 1440/960/390 without overflow','no page errors']}));
}finally{await browser.close();}
