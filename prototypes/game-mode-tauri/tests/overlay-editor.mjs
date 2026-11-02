import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
let source,reviewed;const calls=[],errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/snapshot',async route=>{
 const response=await route.fetch();source=await response.json();
 source.overlayDefaults={...source.overlayDefaults,Theme:4,AccentCharacter:10,AccentMode:'adaptive',AccentColor:''};
 await route.fulfill({json:source});
});
await page.route('**/api/engine/status',r=>r.fulfill({json:{enabled:true,reason:'Fixture transport only.'}}));
await page.route('**/api/engine',async route=>{
 const request=route.request().postDataJSON();calls.push(request);let result;
 if(request.method==='settings_get')result={...source.preferences,panel_hotkey:'Delete',overlay_renderer:'game',optiscaler_hotkey:'Disabled',overlay_appearance:{...source.overlayDefaults,Layout:'bar'},game_overlay_settings:{other:{panel_hotkey:'F8'}}};
 else if(request.method==='scan_game')result=[{game:request.params.folder,name:'Fixture game',exe:'fixture.exe',installed:false}];
 else if(request.method==='settings_review'){reviewed=request.params.changes;result={token:'overlay-fixture-review',title:'Exact overlay fixture',rows:[{name:'Preferences',detail:JSON.stringify(reviewed)}]};}
 else if(request.method==='discard')result={};
 else throw Error('Unexpected operation: '+request.method);
 await route.fulfill({json:{result}});
});
try{
 await page.goto('http://127.0.0.1:1420');await page.locator('.game-card').first().click();
 await page.locator('[data-detail-section="features"]').click();
 await page.getByRole('button',{name:'Overlay settings',exact:true}).click();
 await page.getByRole('button',{name:'Load current overlay settings',exact:true}).click();
 await expect(page.getByRole('combobox',{name:'Accent',exact:true})).toBeEnabled();
 await expect(page.getByRole('switch',{name:'Surface Tint',exact:true})).toHaveAttribute('aria-checked','true');
 await page.locator('[data-overlay-surface="light"]').click();
 await expect(page.getByRole('switch',{name:'Surface Tint',exact:true})).toHaveAttribute('aria-checked','true');
 await page.getByRole('combobox',{name:'Accent',exact:true}).selectOption('"custom"');
 await page.getByRole('button',{name:'Side Panel',exact:true}).click();
 await page.getByRole('combobox',{name:'Side Panel position',exact:true}).selectOption('"right"');
 await page.getByRole('combobox',{name:'Primary overlay',exact:true}).selectOption('"optiscaler"');
 await expect(page.getByRole('checkbox',{name:'Make this my default',exact:true})).not.toBeChecked();
 await page.getByRole('button',{name:"Review this game's preferences",exact:true}).click();
 await expect(page.getByRole('heading',{name:'Exact overlay fixture',exact:true})).toBeVisible();
 expect(Object.keys(reviewed)).toEqual(['game_overlay_settings']);
 expect(reviewed.game_overlay_settings.other).toEqual({panel_hotkey:'F8'});
 const value=reviewed.game_overlay_settings[source.games[0].path];
 expect(value.overlay_renderer).toBe('optiscaler');expect(value.optiscaler_ui).toBe(true);expect(value.reshade_ui).toBe(true);expect(value.optiscaler_hotkey).toBe('Insert');
 expect(value.overlay_appearance).toMatchObject({Theme:4,AccentCharacter:50,AccentMode:'custom',Layout:'floating',SidePanelSide:'right'});
 await page.getByRole('button',{name:'Back',exact:true}).click();
 await page.getByRole('checkbox',{name:'Make this my default',exact:true}).check();
 await page.getByRole('button',{name:"Review this game's preferences",exact:true}).click();
 await expect(page.getByRole('heading',{name:'Exact overlay fixture',exact:true})).toBeVisible();
 expect(reviewed.overlay_renderer).toBe('optiscaler');
 await page.getByRole('button',{name:'Back',exact:true}).click();
 await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Settings',exact:true}).click();
 await page.getByRole('navigation',{name:'Settings sections'}).getByRole('button',{name:'Overlay',exact:true}).click();
 await expect(page.getByRole('switch',{name:'Surface Tint',exact:true})).toHaveAttribute('aria-checked','true');
 await page.getByRole('button',{name:/Apply defaults to all overlays/}).click();
 await expect(page.getByRole('heading',{name:'Exact overlay fixture',exact:true})).toBeVisible();
 expect(reviewed).toEqual({game_overlay_settings:{}});
 expect(calls.some(c=>c.method==='run')).toBe(false);
 expect(errors).toEqual([]);
 console.log(JSON.stringify({passed:true,checks:['direct per-game load','shared surface/tint and accent editor','local native opt-out with default unchecked','other-game overrides preserved','review-only exact scoped changes']}));
}finally{await browser.close();}
