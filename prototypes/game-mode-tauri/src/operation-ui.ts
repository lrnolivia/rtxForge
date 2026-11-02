import {escape as e,type Game} from './model';
import type {Review} from './engine';
export interface FlowState {
 stage:'startup'|'checking'|'review'|'running'|'done'|'error';title:string;kind?:string;origin?:string;
 review?:Review;progress?:Record<string,unknown>;result?:unknown;error?:string;cancelRequested?:boolean;targets?:Game[];
}
type Icon=(name:string)=>string;
const verb=(kind?:string)=>kind==='uninstall'?'Restoring':kind==='update-dlss'?'Updating':kind==='install'?'Installing':'Applying';
export function flowGame(item:Record<string,unknown>,games:Game[]) {
 const key=String(item.game||item.path||item.game_id||'').replaceAll('\\','/').toLowerCase();
 return games.find(game=>key&&(game.path.replaceAll('\\','/').toLowerCase()===key||game.id.toLowerCase()===key))||games.find(game=>game.name===String(item.name||item.title||''));
}
function reviewRow(item:Record<string,unknown>,games:Game[],icon:Icon,ready=true) {
 const game=flowGame(item,games),art=game?.capsule||game?.art,color=game?.accent||game?.artworkAccent;
 const title=String(item.name||item.title||game?.name||'Selected change'),detail=String(item.summary||item.detail||item.reason||'');
 const technical=String(item.details||item.technical||(item.summary?(item.detail||item.reason||''):'')),badge=String(item.badge||(ready?'Ready':'Skipped'));
 return `<article class="flow-review-row inner-card" ${color?`style="--row-accent:${e(color)}"`:''}><div class="flow-thumbnail">${art?`<img src="${e(art)}" alt=""/>`:icon(ready?'check':'warning')}</div><div class="flow-review-copy"><h3>${e(title)}</h3>${detail?`<p>${e(detail)}</p>`:''}${technical?`<details><summary>Technical details</summary><pre>${e(technical)}</pre></details>`:''}</div><span class="flow-badge ${ready?'':'flow-skipped'}">${icon(ready?'check':'warning')}${e(badge)}</span></article>`;
}
export function operationStep(state:FlowState,games:Game[],icon:Icon) {
 const p=state.progress||{},name=String(p.game||p.name||''),game=flowGame({game:name,name},games)||state.targets?.[0];
 const art=game?.art||game?.capsule,color=game?.accent||game?.artworkAccent;
 const total=Number(p.total),at=Number(p.index??p.current??p.checked),fraction=typeof p.fraction==='number'&&Number.isFinite(p.fraction)?Math.max(0,Math.min(1,p.fraction)):total>0&&Number.isFinite(at)?Math.max(0,Math.min(1,at/total)):null;
 const caption=state.stage==='checking'?'Preparing':verb(state.kind),counter=total>0&&Number.isFinite(at)?`${caption} ${Math.min(total,Math.max(1,at))} of ${total}`:caption+'…';
 const label=state.cancelRequested?'Waiting for the engine to stop safely…':String(p.label||p.phase||(state.stage==='checking'?'Checking the selected games and required packages…':'Waiting for the engine to report progress…'));
 return `<div class="operation-step" ${color?`style="--step-accent:${e(color)}"`:''}><div class="flow-poster">${art?`<img src="${e(art)}" alt=""/>`:icon('package')}</div><div class="operation-step-copy"><p class="flow-counter">${e(counter)}</p><h2>${e(game?.name||name||'Your selected games')}</h2><p role="status" class="flow-phase">${e(label)}</p><progress max="1" ${fraction!==null?`value="${fraction}"`:''} aria-label="${caption} progress"></progress>${fraction!==null?`<span class="flow-percentage">${Math.round(fraction*100)}%</span>`:''}</div></div>`;
}
export function operationFlow(state:FlowState,games:Game[],icon:Icon,startup='',supported='') {
 const review=state.review,rows=review?.rows||review?.items||[],blocked=review?.blocked||[],warnings=review?.warnings||[];
 const steps=['Startup settings','Review games','Install'];
 const current=state.stage==='startup'?0:state.stage==='review'||state.stage==='checking'?1:2;
 const title=state.stage==='startup'?'Install Features':state.stage==='review'?state.title:state.stage==='checking'?'Preparing':state.stage==='running'?verb(state.kind):state.stage==='error'?'Operation did not complete':(state.result as Record<string,unknown>)?.cancelled?'Cancelled':'Finished';
 let body='',footer='';
 if(state.stage==='startup') {
  body=`<p class="flow-intro">Choose startup settings. You can adjust them later.</p>${startup}`;
  footer='<button class="quiet" data-action="discard-review">Cancel</button><button class="primary" data-action="startup-review">Review games</button>';
 }else if(state.stage==='checking'||state.stage==='running'){
  body=operationStep(state,games,icon);
  footer=state.stage==='checking'?'<button class="quiet" data-action="discard-review">Cancel</button>':`<button class="quiet" data-action="cancel-operation" ${state.cancelRequested?'disabled':''}>${state.cancelRequested?'Cancellation requested':'Request cancellation'}</button>`;
 }else if(state.stage==='review'&&review){
  body=`<div class="flow-summary"><h2>${rows.length?`${rows.length} game${rows.length===1?'':'s'} ready`:'Nothing ready yet'}</h2>${review.summary?`<p>${e(review.summary)}</p>`:''}</div><div class="flow-review-list">${rows.map(row=>reviewRow(row,games,icon)).join('')}${blocked.length?`<h3 class="flow-attention">Needs attention · ${blocked.length}</h3>${blocked.map(row=>reviewRow(row,games,icon,false)).join('')}`:''}</div>${supported}${warnings.length?`<div class="flow-warnings">${warnings.map(row=>`<div>${icon('warning')}<p><strong>${e(row.name||row.title||'Review warning')}</strong>${e(row.reason||row.detail||'')}</p></div>`).join('')}</div>`:''}${review.note?`<p class="flow-note">${e(review.note)}</p>`:''}<p class="flow-assurance">Your files will only change after you review and confirm.</p>${review.trust?`<label class="trust-choice"><input id="review-trust" type="checkbox"/><span>${e(review.trust)}</span></label>`:''}`;
  footer=`<button class="quiet" data-action="discard-review">Back</button><button class="primary" data-action="confirm-operation" ${!rows.length||review.trust?'disabled':''}>${e(review.action||'Confirm changes')}</button>`;
 }else{
  const result=state.result as Record<string,unknown>|undefined,errors=Array.isArray(result?.errors)?result.errors:[];
  const cancelled=result?.cancelled===true,failed=state.stage==='error'||errors.length>0;
  const message=state.error||String(result?.message||(typeof result?.report==='string'?result.report:'')||(typeof state.result==='string'?state.result:cancelled?'The engine stopped this operation. Review the completed steps below.':failed?'Some changes need attention.':'The engine finished the reviewed operation.'));
  const reports=Array.isArray(result?.reports)?result.reports:[];
  body=`<div class="flow-result ${failed?'flow-result-error':''}">${icon(failed||cancelled?'warning':'check')}<div><h2>${failed?'Needs attention':cancelled?'Operation cancelled':'All done'}</h2><p role="status">${e(message)}</p>${typeof result?.completed_batches==='number'?`<p class="subtle">${result.completed_batches} reviewed batch${result.completed_batches===1?'':'es'} completed.</p>`:''}${errors.length?`<ul>${errors.map(error=>`<li>${e(error)}</li>`).join('')}</ul>`:''}</div></div>${reports.length?`<details class="flow-report"><summary>Operation details</summary>${reports.map(report=>`<pre>${e(typeof report==='string'?report:JSON.stringify(report,null,2))}</pre>`).join('')}</details>`:''}`;
  footer='<button class="primary" data-action="operation-back">Back to game</button>';
 }
 return `<div class="operation-flow" data-stage="${state.stage}"><header class="flow-heading"><h1 id="page-title" tabindex="-1">${e(title)}</h1>${state.kind==='install'?`<ol class="flow-steps" aria-label="Installation steps">${steps.map((step,i)=>`<li ${i===current?'aria-current="step"':''}><span>${i+1}</span>${step}</li>`).join('')}</ol>`:''}</header><section class="glass-section flow-panel">${['checking','running'].includes(state.stage)?'<div class="flow-artwork" aria-hidden="true"></div>':''}<div class="flow-body">${body}</div><footer class="operation-actions flow-actions">${footer}</footer></section></div>`;
}
