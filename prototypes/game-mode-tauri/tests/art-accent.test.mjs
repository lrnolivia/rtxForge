import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';
const source=readFileSync(new URL('../src/art-accent.ts',import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {signatureColor,selectionInk,heroColors,heroBadge}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
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
  const protectedBackground=background.map((v,i)=>v*(1-result.titleVeil)+[12,18,23][i]*result.titleVeil);
  assert.ok(contrast(rgb(result.title),protectedBackground)>=3,color+' title '+JSON.stringify(background));
  const opacity=result.cardOpacity,composite=rgb(result.card).map((v,i)=>v*opacity+background[i]*result.cardBrightness*(1-opacity));
  assert.ok(contrast(rgb(result.ink),composite)>=4.5,color+' translucent card');
  if(!light&&color!=='#ffd950')assert.ok(luminance(rgb(result.ink))>.8,'Non-yellow Clear/Dark hero cards keep pale text');
 }
});

test('yellow titles remain bright with a protected backdrop, and badges follow local artwork',()=>{
 for(const color of ['#fffb00','#ffd950']){
  const result=heroColors(color,true,[250,250,240]),title=rgb(result.title);
  assert.ok(title[0]>220&&title[1]>180&&title[2]<140,'Yellow title stays bright');
  assert.ok(result.titleVeil>0,'Bright artwork receives a protective veil');
  const ink=rgb(selectionInk(color));assert.ok(Math.max(...ink)-Math.min(...ink)<10);
 }
 assert.notEqual(heroBadge([245,240,230]).ink,heroBadge([20,30,40]).ink);
});

test('Avatar mid-tone hero keeps a pale readable title in both themes',()=>{
 for(const [accent,background] of [['#4b8fb5',[71,106,126]],['#4191af',[141.0625,149.8333,144.5833]],['#4191af',[141.39872520683807,143.43357177424272,134.2694220455464]]]){
 const clear=heroColors(accent,false,background),light=heroColors(accent,true,background);
 assert.equal(clear.title,light.title,'Artwork contrast is independent of the surrounding UI theme');
 assert.ok(luminance(rgb(clear.title))>.45,'Avoid the dark teal title on the blue hero');
 const protectedBackground=background.map((v,i)=>v*(1-clear.titleVeil)+[12,18,23][i]*clear.titleVeil);
 assert.ok(contrast(rgb(clear.title),protectedBackground)>=3);
 }
});

test('info cards keep soft accent frost and pale readable text for every accent',()=>{
 for(const color of ['#fffb00','#ffd950','#307de8','#ff473a'])for(const light of [false,true])for(const background of [[255,255,255],[28,32,36],[120,120,120]]){
  const result=heroColors(color,light,background),card=rgb(result.card),ink=rgb(result.ink);
  assert.deepEqual(card,rgb(color).map(value=>Math.round(value*.8+255*.2)),'The frost retains a soft game-accent tint');
  assert.ok(result.cardOpacity<=.2,'Keep the accent translucent');
  assert.ok(luminance(ink)>.8,'Info text stays pale');
  const opacity=result.cardOpacity,composite=card.map((v,i)=>v*opacity+background[i]*result.cardBrightness*(1-opacity));
  assert.ok(contrast(ink,composite)>=4.5,'Light frost retains text contrast over bright artwork');
 }
});
