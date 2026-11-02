import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const code=ts.transpileModule(readFileSync(new URL('../src/screenshot-crop.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {screenshotCrop,cropGeometry}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
function pixels(width,height,content){return Uint8ClampedArray.from(Array.from({length:width*height},(_,i)=>[...content(i%width,Math.floor(i/width)),255]).flat());}
test('removes matched letterbox and pillarbox bands including JPEG near-black',()=>{
 const w=160,h=100,data=pixels(w,h,(x,y)=>y<12||y>=88||x<10||x>=150?[6,7,8]:[80+x,120,140]);
 assert.deepEqual(screenshotCrop(data,w,h),{x:10/w,y:12/h,width:140/w,height:76/h});
 const crop=screenshotCrop(pixels(w,h,(_,y)=>y<12||y>=88?[0,0,0]:[90,100,110]),w,h);
 const geometry=cropGeometry(1600,1000,crop,1600,1000),[bw,bh]=geometry.size.split(' ').map(parseFloat),[x,y]=geometry.position.split(' ').map(parseFloat);
 assert.ok(y+bh*crop.y<=0&&y+bh*(crop.y+crop.height)>=1000,'Active image fills viewport vertically');
 assert.ok(x<=0&&x+bw>=1600,'Active image fills viewport horizontally');
});
test('does not zoom ordinary dark scenes, one-sided shadows or unletterboxed images',()=>{
 const w=160,h=100,full={x:0,y:0,width:1,height:1};
 for(const content of [()=>[7,8,10],(x,y)=>y<12?[0,0,0]:[80,100,150],(x,y)=>y<12||y>87?[8,9,10]:[13,15,17],()=>[80,100,150]])
   assert.deepEqual(screenshotCrop(pixels(w,h,content),w,h),full);
});
