import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:990},reducedMotion:'reduce'}),errors=[];
page.on('pageerror',error=>errors.push(error.message));
await page.route('**/api/snapshot',async route=>{const response=await route.fetch(),data=await response.json();data.games=data.games.slice(0,3).map((game,i)=>({...game,accent:['#ff473a','#31b7c3','#ffff00'][i]}));await route.fulfill({json:data});});
const nav=name=>page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true});
const colors=selector=>page.locator(selector).evaluate(n=>{const c=document.createElement('canvas').getContext('2d');const rgb=color=>{c.clearRect(0,0,1,1);c.fillStyle=color;c.fillRect(0,0,1,1);return [...c.getImageData(0,0,1,1).data].slice(0,3);};const s=getComputedStyle(n),label=n.querySelector('.control-label');return {bg:rgb(s.backgroundColor),fg:rgb(getComputedStyle(label||n).color),blend:getComputedStyle(label||n).mixBlendMode};});
const contrast=({bg,fg})=>{const lum=rgb=>rgb.reduce((sum,c,i)=>{c/=255;return sum+[.2126,.7152,.0722][i]*(c<=.04045?c/12.92:((c+.055)/1.055)**2.4);},0);const a=lum(bg),b=lum(fg);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);};
try{
 await page.goto('http://127.0.0.1:1420');await page.waitForSelector('.game-card');
 await expect(page.locator('html')).toHaveAttribute('data-theme','clear');await expect(page.locator('html')).toHaveAttribute('data-tint','true');
 expect(await page.locator('html').evaluate(n=>getComputedStyle(n).getPropertyValue('--accent').trim())).toBe('#d8d5ce');
 for(const label of ['Presets','Packages','Extras','Settings']){
  const node=nav(label).locator('.control-label');expect(await node.evaluate(n=>getComputedStyle(n).color)).toBe(await page.locator('body').evaluate(n=>getComputedStyle(n).color));expect(await node.evaluate(n=>getComputedStyle(n).mixBlendMode)).toBe('normal');
 }
 expect(await nav('Library').locator('.control-label').evaluate(n=>getComputedStyle(n).mixBlendMode)).toBe('screen');
 await expect(page.locator('[data-layout=grid] svg rect')).toHaveCount(2);await expect(page.locator('[data-layout=capsules] svg rect')).toHaveCount(2);
 await page.locator('.select-game').first().click();
 const checkbox=await page.locator('.selection-check').first().boundingBox();expect(checkbox.width).toBe(22);expect(checkbox.height).toBe(22);
 expect(await page.locator('.selection-check .icon').first().evaluate(n=>getComputedStyle(n).color)).toBe('rgb(247, 243, 236)');
 await page.getByRole('button',{name:'Clear selection',exact:true}).click();
 await nav('Settings').click();await page.locator('#accent-color').fill('#31b7c3');
 const ratios=[];
 for(let i=0;i<3;i++){
  await nav('Library').click();await page.locator('.game-card').nth(i).click();
  const button=page.locator('.hero-actions .primary');await expect(button).toBeDisabled();
  const computed=await colors('.hero-actions .primary');expect(computed.blend).toBe('normal');ratios.push(contrast(computed));expect(ratios.at(-1)).toBeGreaterThanOrEqual(4.5);
  if(i===0){expect(computed.bg).toEqual([255,71,58]);expect(computed.fg[0]).toBeGreaterThan(computed.fg[2]);await page.screenshot({path:'.impeccable/review/red-button-readable.png'});}
 }
 await nav('Settings').click();await page.getByRole('button',{name:'Light',exact:true}).click();
 expect(await nav('Library').locator('.control-label').evaluate(n=>getComputedStyle(n).mixBlendMode)).toBe('normal');
 await page.getByRole('button',{name:'Reset appearance',exact:true}).click();
 await expect(page.locator('html')).toHaveAttribute('data-theme','clear');await expect(page.locator('html')).toHaveAttribute('data-tint','true');await expect(page.locator('#accent-color')).toHaveValue('#d8d5ce');
 await page.locator('#accent-color').fill('#a258cc');await page.reload();await page.waitForSelector('.game-card');
 expect(await page.locator('html').evaluate(n=>getComputedStyle(n).getPropertyValue('--accent').trim())).toBe('#a258cc');
 expect(errors).toEqual([]);console.log(JSON.stringify({passed:true,minimumFilledButtonContrast:Math.min(...ratios),checks:['Clear/tint-on/neutral defaults and reset','custom shell accent persists','inactive nav neutral; selected glass Screen','filled buttons scoped to game not shell; no Screen washout','red/cyan/yellow fill contrast >=4.5','small frosted checkbox','portrait/landscape view icons','Light uses normal blend','read-only actions remain disabled']}));
}finally{await browser.close();}
