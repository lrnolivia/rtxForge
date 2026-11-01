import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:990},reducedMotion:'reduce'});const calls=[];let games=[];
await page.route('**/api/snapshot',async route=>{const response=await route.fetch();const data=await response.json();data.games=data.games.slice(0,3);games=data.games;await route.fulfill({json:data});});
await page.route('**/api/engine/status',route=>route.fulfill({json:{enabled:true,reason:'Contract fixture only'}}));
const row=(game,index)=>({name:game.name,game:game.path,installed:index===1,blocked:index===2?'Fixture blocked':'',exe:'fixture.exe'});
await page.route('**/api/engine',async route=>{const request=route.request().postDataJSON();calls.push(request);let result={};
 if(request.method==='scan')result=games.map(row);
 if(request.method==='scan_game')result=games.filter(game=>game.path===request.params.folder).map((game)=>({...row(game,games.indexOf(game)),adoption_available:true}));
 if(request.method==='prepare_routes')result={token:'library-scope-exact',title:'Exact library fixture',rows:request.params.rows};
 if(request.method==='settings_review')result={token:'removed-exact',title:'Hide exact entries fixture',rows:[{name:'Hide selected entries'}]};
 if(request.method==='settings_get')result={removed_games:['C:/Fixture/Previously hidden'],default_profile:'mfg-only'};
 await route.fulfill({json:{result}});
});
try{
 await page.goto('http://127.0.0.1:1420');await page.waitForSelector('.game-card');
 await page.getByRole('combobox',{name:'Filter library'}).selectOption('available');await expect(page.locator('.game-card')).toHaveCount(1);
 await page.locator('[data-library-scope][data-operation=install]').click();await page.getByRole('button',{name:'Review games',exact:true}).click();await expect(page.getByRole('heading',{name:'Exact library fixture'})).toBeVisible();
 const review=calls.find(call=>call.method==='prepare_routes');expect(review.params.rows.map(row=>row.game)).toEqual([games[0].path]);
 expect(calls.some(call=>['execute_routes','run'].includes(call.method))).toBe(false);
 await page.getByRole('button',{name:'Back',exact:true}).click();
 await page.getByRole('combobox',{name:'Filter library'}).selectOption('installed');await expect(page.locator('.game-card')).toHaveCount(1);
 await expect(page.locator('.game-card')).toHaveAttribute('data-game',games[1].id);
 await page.locator('.game-card').click();await page.getByRole('button',{name:'More game options'}).click();
 await expect(page.getByRole('menuitem',{name:'Adopt with rtxForge',exact:true})).toBeVisible();
 await page.keyboard.press('Escape');await expect(page.getByRole('menuitem',{name:'Adopt with rtxForge',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Back to Library'}).click();await expect(page.locator('.game-card')).toBeFocused();
 console.log(JSON.stringify({passed:true,checks:['filters require fresh scan','filtered bulk review retains exact game','no execute during review','fresh adoption actions reachable','Escape closes game menu before leaving Details','Back restores card focus','no actual mutations']}));
}finally{await browser.close();}
