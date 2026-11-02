import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const code=ts.transpileModule(readFileSync(new URL('../src/display-scale.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText;
const {webviewZoom}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
test('150% has the same physical size at 100%, 150% and 200% desktop DPI',()=>{
  for(const dpi of [1,1.5,2]){
    const zoom=webviewZoom(150,dpi);
    assert.equal(zoom*dpi,1.5);
    assert.equal(3840/(zoom*dpi),2560);
    assert.equal(2160/(zoom*dpi),1440);
  }
});
test('Automatic follows the OS and manual scale survives a monitor change',()=>{
  for(const dpi of [1,1.25,1.5,2])assert.equal(webviewZoom('auto',dpi),1);
  assert.equal(webviewZoom(100,2),.5);
  assert.equal(webviewZoom(200,1),2);
  assert.equal(webviewZoom(150,0),1.5);
});
