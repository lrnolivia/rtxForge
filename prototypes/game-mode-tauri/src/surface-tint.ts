export type AccentMode='theme'|'custom'|'adaptive';
/** Shared control for app and overlay tint; native ranges retain controller arrow-key input. */
export function surfaceTintControls(mode:AccentMode,strength:number,overlay=false,disabled=false){
  const attribute=overlay?'data-glass="AccentMode"':'id="surface-accent-mode"';
  const range=overlay?'data-glass-range="AccentTint"':'id="surface-tint-strength"';
  const off=disabled?'disabled':'';
  return `<label class="field"><span><strong>Accent source</strong><small>Configured uses your chosen color. Adaptive follows ${overlay?'the running game':'the background image'}.</small></span><select ${attribute} aria-label="Accent source" ${off}>${([['theme','None'],['adaptive','Adaptive'],['custom',overlay?'Game / custom':'Configured']] as const).map(([key,title])=>`<option value="${overlay?'&quot;'+key+'&quot;':key}" ${mode===key?'selected':''}>${title}</option>`).join('')}</select></label><label class="field surface-tint-control"><span><strong>Surface Tint</strong><small>Blend the accent into the glass surface.</small></span><input type="range" ${range} aria-label="Surface Tint" min="0" max="100" step="1" value="${strength}" ${disabled||mode==='theme'?'disabled':''}/><output>${strength}%</output></label>`;
}
