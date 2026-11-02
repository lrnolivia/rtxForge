import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const code=ts.transpileModule(readFileSync(new URL('../src/hero-focus.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText;
const {heroCrop,saliencyFocus}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
test('Desktop normalized focus stays visible in a short hero and moves higher',()=>{
  for(const width of [390,960,1920])for(const height of [128,270])for(const point of [[0,0],[.25,.3],[.75,.5],[1,1]]){
    const result=heroCrop(width,height,3840,1240,point);
    for(const value of [result.x,result.y,result.markerX,result.markerY])assert.ok(value>=-1e-9&&value<=100+1e-9);
  }
  const higher=heroCrop(1920,240,3840,1240,[.5,.5]),desktop=heroCrop(1920,240,3840,1240,[.5,.5],.4);
  assert.ok(higher.markerY<desktop.markerY);
  assert.ok(Math.abs(higher.markerY-30)<1e-6);
});
test('Desktop saliency centers a distinct subject and keeps its vertical default',()=>{
  const width=96,height=32,pixels=new Uint8ClampedArray(width*height*4);
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const subject=x>=65&&x<=80&&y>=4&&y<=27,value=subject?230:40,i=(y*width+x)*4;
    pixels.set([value,subject?80:value,subject?30:value,255],i);
  }
  const [x,y]=saliencyFocus(pixels,width,height);assert.ok(x>.65&&x<.85);assert.equal(y,.3);
  assert.deepEqual(saliencyFocus(new Uint8ClampedArray(width*height*4),width,height),[.5,.3]);
});
