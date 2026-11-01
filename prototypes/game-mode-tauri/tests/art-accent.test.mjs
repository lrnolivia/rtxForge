import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';
const source=readFileSync(new URL('../src/art-accent.ts',import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {signatureColor,selectionInk,heroColors}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
test('artwork signature matches the real shared library algorithm',()=>{
 const solid=color=>Array.from({length:100},()=>[...color,255]);
 const fixtures=[solid([225,40,30]),solid([32,106,235]),solid([230,199,60]),solid([165,63,186]),solid([128,128,128]),[...solid([70,170,70]),...solid([220,45,30]).slice(0,30)],[...solid([250,250,250]),...solid([10,10,10])],Array.from({length:250},(_,i)=>[(i*37)%256,(i*73)%256,(i*113)%256,i%3?255:0])];
 const script="import sys,json;sys.path.insert(0,sys.argv[1]);import ui_colors;print(json.dumps([ui_colors.signature_color(p) for p in json.load(sys.stdin)]))";
 const expected=JSON.parse(execFileSync(process.env.RTXFORGE_PYTHON||(process.platform==='win32'?'python':'python3'),['-B','-c',script,fileURLToPath(new URL('../../../scripts/',import.meta.url))],{input:JSON.stringify(fixtures),encoding:'utf8',windowsHide:true}));
 assert.deepEqual(fixtures.map(pixels=>signatureColor(pixels.flat())),expected);
 assert.equal(expected[4],null,'Greyscale artwork must retain a neutral fallback');
});

test('solid selected-card fills retain readable ink for vivid and custom colors',()=>{
 const colors=['#ff473a','#ffd950','#ffffff','#000000','#17ff67','#307de8','#dc5ed1','#ff0000','#110d04'];
 const lum=hex=>[1,3,5].reduce((sum,i,k)=>{let c=parseInt(hex.slice(i,i+2),16)/255;return sum+[.2126,.7152,.0722][k]*(c<=.04045?c/12.92:((c+.055)/1.055)**2.4);},0);
 for(const color of colors){const a=lum(color),b=lum(selectionInk(color));assert.ok((Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5,color);}
});

const luminance=rgb=>rgb.reduce((sum,v,i)=>{v/=255;return sum+[.2126,.7152,.0722][i]*(v<=.04045?v/12.92:((v+.055)/1.055)**2.4);},0);
const rgb=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
const contrast=(a,b)=>(Math.max(luminance(a),luminance(b))+.05)/(Math.min(luminance(a),luminance(b))+.05);
test('hero text adapts to artwork and cards retain contrast across themes',()=>{
 for(const color of ['#ffffff','#000000','#ffd950','#ff473a','#307de8','#dc5ed1','#d8d5ce'])for(const light of [true,false])for(const background of [[240,238,230],[28,32,36],[120,120,120]]){
  const result=heroColors(color,light,background);
  assert.ok(contrast(rgb(result.title),background)>=3,color+' title '+JSON.stringify(background));
  assert.ok(contrast(rgb(result.ink),rgb(result.card))>=4.5,color+' card');
 }
});
