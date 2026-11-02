import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const code=ts.transpileModule(readFileSync(new URL('../src/overlay-settings.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {mergeOverlay,overlaySurface,surfaceChanges,overlayPreferenceChanges}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
test('per-game appearance inherits unmodified defaults and preserves other games',()=>{
 const defaults={panel_hotkey:'Delete',overlay_appearance:{Layout:'floating',AccentMode:'adaptive',Theme:4}};
 const local={overlay_appearance:{SidePanelSide:'right'}};
 const draft={overlay_appearance:{TextSize:26}};
 assert.deepEqual(mergeOverlay(defaults,local,draft).overlay_appearance,{Layout:'floating',AccentMode:'adaptive',Theme:4,SidePanelSide:'right',TextSize:26});
 const shared={...defaults,game_overlay_settings:{other:{panel_hotkey:'F8'}}};
 const changes=overlayPreferenceChanges(shared,'game',local,draft);
 assert.deepEqual(Object.keys(changes),['game_overlay_settings']);
 assert.equal(changes.game_overlay_settings.other.panel_hotkey,'F8');
 assert.deepEqual(changes.game_overlay_settings.game.overlay_appearance,{SidePanelSide:'right',TextSize:26});
 assert.equal(shared.game_overlay_settings.game,undefined);
});
test('changing defaults is explicit and includes only the reviewed game draft',()=>{
 const changes=overlayPreferenceChanges({game_overlay_settings:{}},'game',{}, {overlay_renderer:'optiscaler',optiscaler_ui:true},true);
 assert.equal(changes.overlay_renderer,'optiscaler');
 assert.equal(changes.optiscaler_ui,true);
 assert.equal(changes.game_overlay_settings.game.overlay_renderer,'optiscaler');
 assert.equal(changes.panel_hotkey,undefined);
});
test('surface and tint are independent while layout and accent selection survive',()=>{
 let glass={Theme:4,AccentCharacter:10,AccentMode:'adaptive',Layout:'bar',BarPosition:'top',TextSize:26};
 assert.equal(overlaySurface(glass),'clear');
 glass=surfaceChanges(glass,'light',true,{accent:{Blur:48,Custom:0}});
 assert.equal(glass.Theme,4);assert.equal(overlaySurface(glass),'light');
 glass=surfaceChanges(glass,'light',false,{light:{Blur:44,Custom:0}});
 assert.equal(glass.Theme,1);assert.equal(glass.Blur,44);
 assert.equal(glass.Layout,'bar');assert.equal(glass.BarPosition,'top');assert.equal(glass.TextSize,26);assert.equal(glass.AccentMode,'adaptive');
 assert.equal(overlaySurface(surfaceChanges(glass,'dark',true)),'dark');
});
