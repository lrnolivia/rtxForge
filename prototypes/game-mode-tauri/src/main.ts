import './style.css';
import { captureArrival, arrive } from './motion';
import { bindArtworkFailures, hydrateArtwork, clearArtworkCache } from './artwork';
// Artwork sources remain exact library identities.
import { appearanceDefaults, escape as e, readAppearance, readSnapshot, type Appearance, type Game, type Snapshot, type View } from './model';
import { operationFlow,operationStep,flowGame } from './operation-ui';
import { installInput } from './input';
import { artworkAccent, selectionInk, heroColors, heroBadge, sampleHero } from './art-accent';
import { enhanceSelects, closeSelectMenu, selectMenuOpen } from './select-menu';
import { settingsSections, settingsContent } from './settings-content';
import { engineRequest, engineStatus, type EngineRow, type EngineStatus, type Review } from './engine';

const symbols: Record<string, number> = { plus:58324, minus:58154, dots: 57854, books: 59224, package: 58256, wrench: 58836, gear: 57968, search: 58124,
  refresh: 57492, controller: 57966, arrow: 57432, check: 57730, folder: 57930, info: 58062, warning: 58592,
  palette: 59080, sliders: 58420, cpu: 58896, grid: 58006, list: 58096, keyboard: 58072, eye: 57888, download: 57868 };
const icon = (name: string, cls = '') => name==='posters'||name==='capsules' ? `<svg class="icon layout-icon ${cls}" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">${name==='posters'?'<rect x="3" y="3" width="7" height="18" rx="1.5"/><rect x="14" y="3" width="7" height="18" rx="1.5"/>':'<rect x="3" y="3" width="18" height="7" rx="1.5"/><rect x="3" y="14" width="18" height="7" rx="1.5"/>'}</svg>` : `<span class="icon ${cls}" aria-hidden="true">${String.fromCodePoint(symbols[name] || symbols.info)}</span>`;
const tabs: { id: View; label: string; icon: string }[] = [
  { id: 'library', label: 'Library', icon: 'books' }, { id: 'presets', label: 'Presets', icon: 'sliders' }, { id: 'packages', label: 'Packages', icon: 'package' },
  { id: 'extras', label: 'Extras', icon: 'wrench' }, { id: 'settings', label: 'Settings', icon: 'gear' },
];
const app = document.querySelector<HTMLElement>('#app')!;
let appearance = readAppearance(), view: View = 'library', selectedId = '', query = '', libraryView = 'grid';
let snapshot: Snapshot | null = null, loading = true, error = '', controller = false, controllerId = '';
const drafts = new Map<string, Record<string, string>>();
let extraKind = 'reshade-import', toolImportOpen = false;
let backend: EngineStatus = { enabled: false, reason: 'Checking the reviewed host adapter…' };
let engineRows: EngineRow[] = [], detailsSection = 'overview';
let operation: { stage: 'startup' | 'checking' | 'review' | 'running' | 'done' | 'error';kind?:string;targets?:Game[];cancelRequested?:boolean; title: string; review?: Review; execute: string; progress?: Record<string, unknown>; result?: unknown; error?: string; origin?: View; method?: string; changedKeys?: string[]; dismissed?: boolean } | null = null;
let settingsCategory = 'appearance', sharedPreferences: Record<string, unknown> | null = null;
const preferenceChanges: Record<string, unknown> = {};
let extraSource = '', extraRecords: Record<string, unknown>[] = [], packageSource = '';
let liveCatalog: (Record<string, unknown> & { id: string; name: string; version: string })[] | null = null;
const batchSelection = new Set<string>();
const noteDrafts = new Map<string, string>();
let hintsTimeout: ReturnType<typeof setTimeout> | undefined;
let toastTimeout: ReturnType<typeof setTimeout> | undefined;
let appliedZoom: number | undefined;
const notesLoaded = new Set<string>();
const reportEdits: Record<string, Record<string, string>> = {};
const gameOverlayDrafts = new Map<string, Record<string, unknown>>();
let artworkRole = 'poster', artworkPath = '', artworkQuery = '', artworkMatches: {id: number; name: string}[] = [];
let artworkAssets: Record<string, unknown>[] = [], artworkMessage = '', gridConnected: boolean | null = null;
let shellMenuOpen = false, detailsMenuOpen=false, presetSelection = false;
const presetId = '__library-presets__';
const gameAccentDrafts = new Map<string, string>();
const supportSelection = new Set<string>();
let heroResize: ResizeObserver | undefined;
let renderedView: View | undefined, renderedGame = '';
let preferencesLoading = false;
let libraryScroll = 0;
let pendingInstall:{params:Record<string,unknown>;settings:Record<string,unknown>;rows:EngineRow[]}|null=null;
let libraryFilter = 'all', libraryChecking = false, libraryMode: string | undefined;

function announce(message: string) {
  document.querySelector('#announcer')!.textContent = message;
  const toast = document.querySelector<HTMLElement>('#toast');
  if (toast) { toast.textContent = message; toast.title = message; toast.dataset.open = 'true'; if (toastTimeout) clearTimeout(toastTimeout); toastTimeout = setTimeout(() => { toast.dataset.open = 'false'; }, 3600); }
}
function showHints() { document.documentElement.dataset.hints = 'visible'; if (hintsTimeout) clearTimeout(hintsTimeout); if ((preferenceChanges.controller_hints ?? sharedPreferences?.controller_hints ?? snapshot?.defaults.controller_hints) === 'auto') hintsTimeout = setTimeout(() => { document.documentElement.dataset.hints = 'hidden'; }, 2500); }
function applyAppearance() {
  const root = document.documentElement;
  root.dataset.theme = appearance.theme;
  root.dataset.tint = String(appearance.tint);
  root.dataset.motion = String(appearance.motion);
  root.dataset.text = appearance.text;
  root.dataset.navigation = appearance.navigation;
  root.dataset.detailsNavigation = appearance.detailsNavigation;
  root.dataset.buttonGlyphs = String(currentPreferences().button_glyphs !== false);
  root.style.setProperty('--accent', appearance.accent);
  root.style.setProperty('--shell-accent', appearance.accent);
  root.style.setProperty('--primary-ink',selectionInk(appearance.accent));
  root.dataset.customBackground=String(Boolean(appearance.background));
  if(appearance.background)root.style.setProperty('--custom-background',`url("${appearance.background}")`);else root.style.removeProperty('--custom-background');
  applyDetailsAccent();
  const zoom = appearance.scale === 'auto' ? 1 : appearance.scale / 100;
  if ('__TAURI_INTERNALS__' in window && appliedZoom !== zoom) { appliedZoom = zoom; void import('@tauri-apps/api/webview').then(({ getCurrentWebview }) => getCurrentWebview().setZoom(zoom)).catch(() => { appliedZoom = undefined; announce('The interface scale could not be applied.'); }); }
  try { localStorage.setItem('rtxforge-game-mode-prototype', JSON.stringify({...appearance,detailsNavigationVersion:1,appearanceDefaultsVersion:2})); } catch { /* Session preferences still work when storage is unavailable. */ }
}
function selectedGame(): Game | undefined { return snapshot?.games.find(game => game.id === selectedId) || snapshot?.games[0]; }
function setView(next: View, focus = true) {
  if (operation?.stage === 'running' && next !== 'operation') { announce('The operation is running. Request cancellation to stop safely.'); return; }
  if (view === 'operation' && next !== 'operation' && operation?.stage === 'checking') operation.dismissed = true;
  const previousView = view;
  if (view === 'library') libraryScroll=app.querySelector<HTMLElement>('#content')?.scrollTop||0;
  shellMenuOpen = false; detailsMenuOpen=false; view = next; render();
  if (focus) document.querySelector<HTMLElement>('#page-title')?.focus();
  const content=app.querySelector<HTMLElement>('#content');if(content)content.scrollTop=next==='library'?libraryScroll:0;
  if(next==='library'&&previousView==='details'&&focus) [...app.querySelectorAll<HTMLElement>('[data-game]')].find(node=>node.dataset.game===selectedId)?.focus({preventScroll:true});
  if (next === 'settings' && backend.enabled && !sharedPreferences) void loadPreferences();
  if(next==='details'&&backend.enabled){const game=selectedGame();if(game)void getEngineRows(game).then(()=>{if(view==='details'&&selectedId===game.id)render();}).catch(problem=>announce(problem.message));}
}
async function loadPreferences() {
  if (preferencesLoading || !backend.enabled) return;
  preferencesLoading = true;
  try { sharedPreferences = await engineRequest<Record<string,unknown>>('settings_get'); if(view==='settings') render(); }
  catch(problem) { announce(problem instanceof Error?problem.message:'Shared preferences could not be read.'); }
  finally { preferencesLoading = false; }
}
function thumbnail(game: Game, cls = '') {
  return game.art ? `<img class="${cls}" src="${e(game.art)}" alt="" loading="lazy" />`
    : `<div class="art-missing ${cls}" aria-hidden="true">${icon('controller')}<span>${e(game.name)}</span></div>`;
}
function notice(title: string, copy: string, kind = 'info') {
  return `<div class="notice">${icon(kind)}<div><strong>${title}</strong><p>${copy}</p></div></div>`;
}
function heading(title: string, description: string, action = '', gameTitle = false) {
  return `<header class="page-heading"><div><h1 id="page-title" class="${gameTitle ? 'game-title' : ''}" tabindex="-1">${title}</h1><p>${description}</p></div>${action}</header>`;
}
function filteredLibrary() {
  return (snapshot?.games||[]).filter(game=>{
    const row=engineRows.find(row=>pathKey(row.game)===pathKey(game.path));
    const match=libraryFilter==='all'||Boolean(row&&(libraryFilter==='installed'?row.installed:!row.installed&&!row.blocked));
    return match&&game.name.toLocaleLowerCase().includes(query.toLocaleLowerCase());
  });
}
async function filterLibrary(value: string) {
  if(!backend.enabled)return;
  libraryChecking=true;render();
  try {const preferences=currentPreferences();engineRows=await engineRequest<EngineRow[]>('scan',{folders:preferences.game_folders||preferences.extra_folders||[],library_folders:preferences.library_folders||[],runtime_provider:snapshot?.defaults.runtime_provider,game_executables:sharedPreferences?.game_executables});libraryFilter=value;}
  catch(problem){announce(problem instanceof Error?problem.message:'The library could not be checked.');}
  finally{libraryChecking=false;render();app.querySelector<HTMLElement>('#library-filter')?.focus();}
}
function library() {
  const games = snapshot?.games || [], filtered = filteredLibrary();
  if (loading && !snapshot) return heading('Library', 'Reading your local game library…') + librarySkeleton();
  return heading('Library', snapshot ? `${games.length} ${games.length === 1 ? 'game' : 'games'} in your local library${!backend.enabled?' · Status from saved library checks':''}` : 'Your games, ready for a closer look.',
    `<button class="quiet" data-action="refresh" ${loading ? 'disabled' : ''}>${icon('refresh')}<span>${loading ? 'Refreshing…' : 'Refresh library'}</span></button>`) + libraryOperations() +
    (error ? notice('Library reader unavailable', e(error), 'warning') : '') +
    (snapshot?.warnings.length ? notice('Some library data is unavailable', snapshot.warnings.map(e).join(' '), 'warning') : '') +
    `<div class="library-tools"><label class="search">${icon('search')}<input id="library-search" type="search" placeholder="Search your library" aria-label="Search your library" value="${e(query)}" /></label><label class="library-filter"><span>Show</span><select id="library-filter" aria-label="Filter library" ${!backend.enabled||libraryChecking?'disabled':''}>${[['all','All games'],['available','Available'],['installed','Installed']].map(([key,label])=>`<option value="${key}" ${libraryFilter===key?'selected':''}>${label}</option>`).join('')}</select></label><div class="view-switch" role="group" aria-label="Library layout"><button data-layout="grid" aria-label="Poster grid" aria-pressed="${libraryView === 'grid'}">${icon('posters')}</button><button data-layout="capsules" aria-label="Wide capsules" aria-pressed="${libraryView === 'capsules'}">${icon('capsules')}</button><button data-layout="list" aria-label="Game list" aria-pressed="${libraryView === 'list'}">${icon('list')}</button></div></div>` +
    (batchSelection.size ? `<div class="selection-bar inner-card"><span>${batchSelection.size} selected</span>${presetSelection ? `<button class="primary" data-action="apply-selected-presets" ${!backend.enabled?'disabled':''}>Apply presets to selected</button><button class="quiet" data-action="end-preset-selection">End preset selection</button>` : ''}<button class="primary" data-operation="install" data-batch="true" ${!backend.enabled ? 'disabled' : ''}>Review selected install</button><button class="quiet" data-operation="uninstall" data-batch="true" ${!backend.enabled ? 'disabled' : ''}>Review selected restore</button><button class="quiet" data-action="remove-selected-entries" ${!backend.enabled?'disabled':''}>Remove entries</button><button class="quiet" data-action="clear-selection">Clear selection</button></div>` : '') +
    `<div id="game-results" aria-live="polite">${gameResults(filtered, games.length)}</div>`;
}
function librarySkeleton() {
  return `<div class="library-skeleton" aria-busy="true" aria-label="Reading your library"><span class="sr-only" role="status">Reading Steam manifests and saved game folders.</span><div class="skeleton-tools" aria-hidden="true"><i></i><i></i></div><div class="games skeleton-grid" aria-hidden="true">${Array.from({length:14},()=>'<div class="skeleton-card"><div class="skeleton-art"></div><div class="skeleton-copy"><i></i><i></i><i></i></div></div>').join('')}</div></div>`;
}
function libraryOperations() {
  const modes=[['nr-only','NR Only'],['mfg-only','MFG Only'],['nr-mfg','NR + MFG']];
  const selected=libraryMode||String(snapshot?.defaults.default_profile||'mfg-only');
  const index=Math.max(0,modes.findIndex(([key])=>key===selected));
  return `<div class="library-operation-bar inner-card"><div class="library-feature-mode"><strong>Features</strong><div class="feature-mode-segments" role="group" aria-label="Feature mode" style="--selected-mode:${index}"><span class="feature-mode-indicator" aria-hidden="true"></span>${modes.map(([key,label])=>`<button data-library-mode="${key}" aria-pressed="${selected===key}">${label}</button>`).join('')}</div></div><div class="library-operation-actions"><button class="primary" data-operation="install" data-library-scope="true" ${!backend.enabled?'disabled':''}>${icon('download')}Install Features</button><button class="quiet" data-operation="uninstall" data-library-scope="true" ${!backend.enabled?'disabled':''}>${icon('refresh')}Restore Original Files</button><button class="quiet" data-operation="update-dlss" data-library-scope="true" ${!backend.enabled?'disabled':''}>${icon('download')}Update DLSS</button></div></div>`;
}
function gameResults(filtered: Game[], total: number) {
  if (!filtered.length) return `<div class="empty glass-section">${icon(total ? 'search' : 'books')}<h2>${total ? 'No matching games' : 'Your library starts here'}</h2><p>${total ? 'Try a different game title.' : 'No installed Steam games or saved game folders were found. Refresh after opening your usual library, or check the library reader in Settings.'}</p>${total ? '<button class="quiet" data-action="clear-search">Clear search</button>' : '<button class="quiet" data-route="settings">Library reader settings</button>'}</div>`;
  return `<div class="games ${libraryView==='list'?'game-list':libraryView==='capsules'?'game-capsules':''}" aria-label="Games">${filtered.map(game=>{
    const actual=engineRows.find(row=>pathKey(row.game)===pathKey(game.path)),record=actual||game.savedRecord;
    const art=libraryView==='grid'?game.art:game.capsule||game.art||game.hero;
    const oses=Array.isArray(record?.installed_oses)?record.installed_oses.filter(os=>['windows','linux'].includes(String(os))):['windows','linux'].includes(String(record?.installed_on))?[record?.installed_on]:[];
    const osBadges=oses.length?`<span class="library-os-badges" title="${actual?'Current engine check':'Saved library check'}">${oses.map(os=>`<img src="/icons/os-${os}.svg" alt="${String(os)==='windows'?'Windows':'Linux'}" width="16" height="16"/>`).join('')}</span>`:'';
    const profile=record?.installed?String(record.profile||'Configured'):record?.installed===false?'Not configured':'Not checked';
    const state=actual?actual.blocked?String(actual.blocked):actual.installed?'Installed':'Available':record?.installed?'Installed':'Not checked';
    const color=game.accent||game.artworkAccent||'var(--ink)';
    return `<article class="game-item" data-library-game="${e(game.id)}" data-selected="${batchSelection.has(game.id)}" style="--game-accent:${e(color)};--game-selected-ink:${selectionInk(color)}">${art?`<img class="artwork-glow glow-core" src="${e(art)}" alt="" aria-hidden="true"/><img class="artwork-glow glow-bloom" src="${e(art)}" alt="" aria-hidden="true"/>`:''}<button class="game-card" data-game="${e(game.id)}" aria-label="Open ${e(game.name)} details"><div class="poster">${thumbnail({...game,art:art||null})}${libraryView==='list'?'':osBadges}</div><div class="game-copy"><h3 class="game-title">${e(game.name)}</h3><span class="game-source">${e(game.source)}</span>${libraryView!=='list'?`<span class="library-card-status" title="${actual?'Current engine check':'Saved library check'}">${icon(actual?.blocked?'warning':record?.installed?'check':'info')}<span>${e(record?.installed?profile:actual?state:'Not checked')}</span></span>`:''}</div>${libraryView==='list'?`<span class="library-profile-chip" title="${actual?'Current engine check':'Saved library check'}">${e(profile)}</span><span class="library-row-state" title="${actual?'Current engine check':'Saved library check'}"><i class="state-dot ${record?.installed?'configured':''}"></i><span>${e(state)}</span>${osBadges}</span><span class="library-open-chip">Details</span>`:''}</button><button class="select-game" data-select-game="${e(game.id)}" aria-label="Select ${e(game.name)} for batch review" aria-pressed="${batchSelection.has(game.id)}"><span class="selection-check" aria-hidden="true">${batchSelection.has(game.id)?icon('check'):''}</span></button></article>`;
  }).join('')}</div>`;
}
function presetValues() {
  const saved = { ...snapshot?.defaults, ...sharedPreferences };
  const changes = drafts.get(presetId) || {};
  const multiplier = saved.mfg_multiplier ?? 'auto';
  return { provider: String(saved.runtime_provider || 'y4my'), mfg_enabled: String(multiplier !== 0),
    mfg_mode: String(multiplier === 0 ? saved.mfg_saved_mode ?? 0 : multiplier === 'auto' ? 0 : saved.dynamic_mfg ? 2 : 1),
    multiplier: String(typeof multiplier === 'number' && multiplier >= 2 ? multiplier : saved.mfg_saved_multiplier ?? 2),
    ...changes };
}
function presetSettings() {
  const values = presetValues();
  const saved = { ...snapshot?.defaults, ...sharedPreferences };
  const featureControls = { ...(saved.feature_controls || {}) as Record<string, number> };
  for (const [key,value] of Object.entries(drafts.get(presetId) || {})) if (key.startsWith('control-')) featureControls[key.slice(8)] = Number(value);
  const ratio = Number(values.multiplier), mode = Number(values.mfg_mode), enabled = values.mfg_enabled === 'true';
  return { nr_strength: Number(featureControls.intensity ?? saved.nr_strength ?? 2),
    sharpening_strength: Number(featureControls.sharpness ?? saved.sharpening_strength ?? .5),
    nr_on_launch: featureControls.enabled !== undefined ? Boolean(featureControls.enabled) : saved.nr_on_launch === true,
    mfg_multiplier: !enabled ? 0 : mode === 0 ? 'auto' : ratio, dynamic_mfg: enabled && mode === 2 ? 1 : 0,
    mfg_saved_mode: mode, mfg_saved_multiplier: ratio, feature_controls: featureControls };
}
function numberControl(input: string, disabled: boolean, title: string) {
  return `<span class="number-stepper" role="group" aria-label="${e(title)} adjustment"><button type="button" data-number-step="-1" aria-label="Decrease ${e(title)}" ${disabled?'disabled':''}>${icon('minus')}</button>${input}<button type="button" data-number-step="1" aria-label="Increase ${e(title)}" ${disabled?'disabled':''}>${icon('plus')}</button></span>`;
}
function tuningFields(keys:string[],values:Record<string,number>,disabled:(key:string)=>boolean,attribute:string) {
  return keys.map(key=>{
    const control=snapshot?.controlSchema?.controls.find(control=>control.key===key);if(!control)return '';
    const value=values[key]??control.default,off=disabled(key),options=control.values||(control.kind==='toggle'?[0,1]:null);
    const label=key==='enabled'?'Enable NR on launch':control.label.replaceAll('Colour','Color');
    return `<${options?'label':'div'} class="field preset-field"><span><strong>${e(label)}</strong></span>${options?`<select ${attribute}="${key}" ${off?'disabled':''}>${options.map((number,index)=>`<option value="${number}" ${number===value?'selected':''}>${e(control.choices?.[index]||(control.kind==='toggle'?['Off','On'][index]:number))}</option>`).join('')}</select>`:numberControl(`<input type="number" ${attribute}="${key}" min="${control.min}" max="${control.max}" step="${control.step||.01}" value="${value}" aria-label="${e(control.label)}" ${off?'disabled':''}/>`,off,control.label)}</${options?'label':'div'}>`;
  }).join('');
}
function presetFields(keys:string[]) {
  const saved={...snapshot?.defaults,...sharedPreferences},values=presetValues(),changes=drafts.get(presetId)||{},controls=(saved.feature_controls||{}) as Record<string,number>;
  const fields=Object.fromEntries(keys.map(key=>[key,Number(changes['control-'+key]??controls[key]??(key==='intensity'?saved.nr_strength:key==='sharpness'?saved.sharpening_strength:key==='enabled'?Number(saved.nr_on_launch===true):undefined)??snapshot?.controlSchema?.controls.find(c=>c.key===key)?.default)]));
  return tuningFields(keys,fields,key=>!backend.enabled||values.provider!=='skynizz'&&!['intensity','sharpness','enabled'].includes(key),'data-preset-control').replace(/data-preset-control="([^"]+)"/g,'data-preset-control="$1" data-preset-key="control-$1"');
}
function presets() {
  const values = presetValues();
  const segments = (key: string, options: [string,string][]) => `<div class="preset-segments" role="group" aria-label="${key === 'mfg_mode' ? 'MFG mode' : 'MFG multiplier'}">${options.map(([value,label])=>`<button data-preset-key="${key}" data-preset-value="${value}" aria-pressed="${values[key as keyof typeof values] === value}" ${!backend.enabled || values.mfg_enabled === 'false' || key === 'mfg_mode' && value === '2' && values.provider !== 'skynizz' ? 'disabled' : ''}>${label}</button>`).join('')}</div>`;
  const card = (title: string, fields: string, extra = '') => `<section class="glass-section preset-pod"><h2>${title}</h2>${extra}<div class="inner-card">${fields}</div></section>`;
  return heading('Presets','Your defaults for new installs. Review games to apply them to existing packages.') +
    `<section class="glass-section preset-mfg"><div class="section-heading"><h2>Multi-Frame Generation</h2><label class="sr-only" for="preset-mfg-enabled">Multi-Frame Generation</label><select id="preset-mfg-enabled" data-preset-key="mfg_enabled" ${!backend.enabled ? 'disabled' : ''}><option value="true" ${values.mfg_enabled === 'true' ? 'selected' : ''}>On</option><option value="false" ${values.mfg_enabled === 'false' ? 'selected' : ''}>Off</option></select></div>${segments('mfg_mode',[['0','Automatic'],['1','Custom'],['2','Dynamic']])}${values.mfg_mode !== '0' && values.mfg_enabled !== 'false' ? `<p class="subtle">${values.mfg_mode === '2' ? 'Maximum multiplier' : 'Multiplier'}</p>${segments('multiplier',[2,3,4,5,6].map(value=>[String(value),value+'×']))}` : ''}</section>`+
    `<div class="preset-columns"><div>${card('Neural rendering',presetFields(['enabled','style','intensity','preset','passes']))}${card('DLSS presets',presetFields(['dlss_preset','rr_preset']),'<p>Applies when the game next starts DLSS. Game default keeps the game’s own choice.</p>')}</div><div>${card('Image tuning',presetFields(['detail','colour'])+`<details><summary>Fine tuning</summary>${presetFields(['structure','tone','skin','auto_mask'])}</details>`)}${card('Sharpening',presetFields(['sharpen','sharpen_shader','sharp_override','sharpness'])+`<details><summary>Motion sharpening</summary>${presetFields(['motion_sharpen','motion_sharpness'])}</details>`)}${card('Performance',presetFields(snapshot?.controlSchema?.controls.filter(control=>control.group==='Performance').map(control=>control.key)||[]))}</div></div>`+
    `<footer class="preset-footer glass-section"><span>${!backend.enabled ? 'Read-only preview · preset changes disabled.' : drafts.has(presetId) ? 'Unsaved changes.' : 'Library presets.'}</span><div class="operation-actions"><button class="quiet" data-action="reset-presets" ${!backend.enabled || !drafts.has(presetId) ? 'disabled' : ''}>Reset</button><button class="quiet" data-action="select-preset-games" ${!backend.enabled ? 'disabled' : ''}>Select games</button><button class="primary" data-action="apply-presets" ${!backend.enabled ? 'disabled' : ''}>Apply to all</button></div></footer>`;
}
async function applyPresets(selected: boolean) {
  if (!backend.enabled) return;
  operation = { stage: 'checking', title: 'Review library presets', execute: 'execute_routes', origin: 'presets' };
  const state = operation; setView('operation');
  try {
    const all = await engineRequest<EngineRow[]>('scan');
    if (state.dismissed || operation !== state) return;
    const rows = all.filter(row => row.installed && !row.blocked && (!selected || snapshot?.games.some(game => batchSelection.has(game.id) && pathKey(game.path) === pathKey(row.game))));
    if (selected && !rows.length) throw new Error('No selected games have configured features available to update.');
    await withOperation('Review library presets','prepare_routes',{ rows, mode: String(sharedPreferences?.default_profile || snapshot?.defaults.default_profile || 'nr-mfg'), operation:'apply', settings:presetSettings(), defaults:presetSettings() },'execute_routes');
    if (operation) operation.origin = 'presets';
  } catch (problem) { state.stage='error'; state.error=problem instanceof Error ? problem.message : 'Library presets could not be reviewed.'; render(); }
}
function selectField(id: string, label: string, options: [string, string][], value: unknown, help: string, disabled = false) {
  return `<label class="field" for="${id}"><span><strong>${label}</strong><small>${help}</small></span><select id="${id}" data-draft="${id}" ${disabled ? 'disabled' : ''}>${options.map(([key, text]) => `<option value="${key}" ${String(value) === key ? 'selected' : ''}>${text}</option>`).join('')}</select></label>`;
}
function gameCredits(game:Game) {
  const raw=Array.isArray(game.developers)?game.developers.join(', '):game.developers||'';
  const suffixes=new Set(['inc','inc.','llc','l.l.c.','ltd','ltd.','limited','co.','co., ltd.','corp','corp.','corporation','gmbh','s.a.','sa','ab','oy','b.v.','bv','s.r.l.','srl','pty ltd','k.k.','a.s.','s.r.o.']);
  const names:string[]=[];for(const part of raw.split(/[,;]/).map(value=>value.trim()).filter(Boolean)){if(names.length&&suffixes.has(part.toLowerCase()))names[names.length-1]+=', '+part;else if(!names.some(name=>name.toLowerCase()===part.toLowerCase()))names.push(part);}
  const primary=/^Ubisoft(?: |$)/i.test(names[0]||'')?'Ubisoft':names[0];
  return {line:[primary,game.release].filter(Boolean).join(' · '),full:raw};
}
async function resolveLibraryAccents(data:Snapshot,games:Game[]=data.games) {
  await Promise.all(games.map(async game=>{
    if(game.accent)return;
    const source=game.art||game.capsule||game.hero;if(!source)return;
    const accent=await artworkAccent(game.id,source);
    // A cached local poster can arrive while the remote fallback is still sampling.
    if(snapshot!==data||(game.art||game.capsule||game.hero)!==source)return;
    game.artworkAccent=accent;
    const item=app.querySelector<HTMLElement>(`[data-library-game="${CSS.escape(game.id)}"]`);if(item){item.style.setProperty('--game-accent',game.artworkAccent||'var(--ink)');item.style.setProperty('--game-selected-ink',selectionInk(game.artworkAccent||'#b4b4b4'));}
    if(view==='details'&&selectedId===game.id){applyDetailsAccent();if(detailsSection==='appearance')render();}
  }));
}
function details() {
  const game = selectedGame();
  if (!game) return heading('Game details', 'Choose a game from your library.');
  const row = engineRows.find(item => pathKey(item.game) === pathKey(game.path));
  const sections = [['overview','Overview','info'],['features','Features','sliders'],['files','DLSS Files','folder'],['tools','Tools','wrench'],['appearance','Appearance','palette'],['notes','Notes','keyboard']];
  const record = row || game.savedRecord;
  const credit=gameCredits(game),credits=e(credit.line);
  const oses = Array.isArray(record?.installed_oses) ? record.installed_oses.filter(os=>['windows','linux'].includes(String(os))) : ['windows','linux'].includes(String(record?.installed_on)) ? [record?.installed_on] : [];
  const pills = [game.source, ...oses.map(os=>String(os) === 'windows' ? 'Windows' : 'Linux'), game.testStatus].filter(Boolean);
  const metadata = `${credits ? `<span class="hero-credits" title="${e(credit.full)}">${credits}</span>` : ''}${pills.map(pill=>`<span class="hero-pill" ${pill !== game.source ? 'title="From the saved library check"' : ''}>${e(pill)}</span>`).join('')}${!row && record && Object.keys(record).length ? '<span class="hero-cache-note">Saved library check</span>' : ''}`;
  const body = detailsSection === 'overview' ? overviewDetails(game, row) : detailsSection === 'features' ? detailFeatures(game, row) : detailsSection === 'appearance' ? detailAppearance(game) : detailTools(game, row);
  const poster = game.art ? `<div class="detail-artwork"><img class="detail-artwork-light glow-core" src="${e(game.art)}" alt="" aria-hidden="true" /><img class="detail-artwork-light glow-bloom" src="${e(game.art)}" alt="" aria-hidden="true" />${thumbnail(game, 'detail-poster')}</div>` : '';
  const status = record?.installed === true ? String(record.profile || 'Features installed') : undefined;
  return `<div class="details-page"><header class="details-hero">${game.hero ? `<div class="hero-artwork"><img class="details-hero-image" crossorigin="anonymous" src="${e(game.hero)}" alt="" /></div>` : ''}<button class="back quiet" data-route="library" aria-label="Back to Library" title="Back to Library">${icon('arrow')}<span>Back to Library</span></button><div class="details-identity">${poster}<div class="details-title-copy"><div class="details-name">${status ? `<span class="hero-status" title="${row?'Current engine check':'Saved library check'}">${e(status)}</span>` : ''}<h1 id="page-title" class="game-title ${game.name.length > 28 ? 'long-title' : ''}" title="${e(game.name)}" tabindex="-1">${e(game.name)}</h1><div class="hero-metadata hero-compact-metadata">${metadata}</div></div><div class="details-hero-bottom"><div class="details-hero-meta hero-info-card"><div class="hero-metadata">${metadata}</div>${game.description ? `<p class="hero-description">${e(game.description.replace(/<[^>]*>/g,''))}</p>` : ''}</div><div class="operation-actions hero-actions"><button class="primary" data-operation="install" ${!backend.enabled ? 'disabled' : ''}>${icon('download')}Install Features</button><button class="quiet" data-operation="uninstall" ${!backend.enabled || !row?.installed ? 'disabled' : ''}>Restore Original Files</button><button class="quiet" data-contract="report_draft" ${!backend.enabled ? 'disabled' : ''}>Bug Report</button><div class="hero-more"><button class="quiet" data-action="game-menu" aria-label="More game options" aria-haspopup="menu" aria-expanded="${detailsMenuOpen}">${icon('dots')}</button><div class="game-menu glass-section" role="menu" ${detailsMenuOpen?'':'hidden'}><button role="menuitem" data-operation="update-dlss" ${!backend.enabled?'disabled':''}>${icon('download')}Update DLSS</button>${row?.adoption_available?`<button role="menuitem" data-operation="adopt">${icon('check')}Adopt with rtxForge</button><button role="menuitem" data-operation="adopt-clean">${icon('refresh')}Back up and clean install</button>`:''}<button role="menuitem" data-action="launch" ${!backend.enabled||!game.appid?'disabled':''}>${icon('controller')}Launch in Steam</button><button role="menuitem" data-action="open-game-folder" ${!backend.enabled?'disabled':''}>${icon('folder')}Open Folder</button><button role="menuitem" data-action="remove-current-entry" ${!backend.enabled?'disabled':''}>${icon('minus')}Remove from library</button></div></div></div></div></div></div></header><div class="details-layout"><nav class="detail-nav glass-section" aria-label="Game details">${sections.map(([key,label,glyph])=>`<button data-detail-section="${key}" aria-pressed="${detailsSection===key}">${icon(glyph)}<span>${label}</span></button>`).join('')}</nav><div class="details-scroll"><div class="hero-spacer" aria-hidden="true"></div><div class="detail-body">${body}</div></div></div></div>`;
}
function overviewDetails(game: Game, row?: EngineRow) {
  const saved = row || game.savedRecord;
  const facts: [string,unknown][] = [];
  if (saved) {
    if (saved.installed === false) facts.push(['Feature package','Not installed']);
    else if (saved.runtime_provider) facts.push(['Feature package',snapshot?.catalog?.find(item=>item.id===saved.runtime_provider)?.name || saved.runtime_provider]);
    const compat = saved.compat as Record<string,unknown> | undefined;
    if (compat?.verdict) facts.push(['Compatibility',String(compat.verdict)+(compat.source==='list'?' · rtxForge list':' · your result')]);
    if(saved.dlss_version) facts.push(['DLSS file version',saved.dlss_version]);
  }
  return `<section class="glass-section"><h2>Testing</h2><p>How this game runs with rtxForge. Something wrong? Prepare a bug report.</p><div class="inner-card"><label class="field"><span><strong>Test result</strong><small>Bench keeps this game out of bulk installs and repairs.</small></span><select id="test-result" ${!backend.enabled?'disabled':''}>${!game.testStatus?'<option value="">No saved result</option>':''}${['Untested','Working','Problem','Bench'].map(value=>`<option ${game.testStatus===value?'selected':''}>${value}</option>`).join('')}</select></label><div class="detail-action-row"><div><strong>${game.testActive?'Test running':'Test session'}</strong><p>${game.testActive?'Play for a minute, then finish here to check each component.':'Check package files, NR, MFG, the panel and helper, with evidence and suggested fixes.'}</p></div><div class="operation-actions"><button class="quiet" data-contract="${game.testActive?'test_finish':'test_start'}" ${!backend.enabled?'disabled':''}>${game.testActive?'Finish Test':'Start Test'}</button><button class="quiet" data-contract="report_draft" ${!backend.enabled?'disabled':''}>Bug Report</button></div></div></div></section>${facts.length?`<div class="fact-grid native-facts">${facts.map(([label,value])=>`<article class="glass-section"><span>${label}</span><strong>${e(value)}</strong></article>`).join('')}</div>`:''}<section class="glass-section"><h2>Game folder</h2><div class="inner-card detail-action-row"><span class="path">${e(game.path)}</span><button class="quiet" data-action="copy-game-path" ${!backend.enabled?'disabled':''}>Copy location</button></div><label class="field"><span><strong>Game executable</strong><small>${saved?.exe?e(saved.exe):'No saved executable information'}</small></span><input id="executable-source" type="text" placeholder="Full or game-relative EXE path" ${!backend.enabled?'disabled':''}/></label><div class="operation-actions extra-actions"><button class="quiet" data-action="executable-review" ${!backend.enabled||snapshot?.platform!=='Windows'?'disabled':''}>Choose EXE…</button><button class="quiet" data-action="executable-reset" ${!backend.enabled||snapshot?.platform!=='Windows'?'disabled':''}>Use detected</button></div></section>`;
}

function detailFeatures(game: Game, row?: EngineRow) {
  row = row || (game.savedRecord ? {name:game.name,game:game.path,...game.savedRecord} as EngineRow : undefined);
  const multiplier = row?.mfg_multiplier ?? snapshot?.defaults.mfg_multiplier ?? 'auto';
  const values = {provider:String(row?.runtime_provider || snapshot?.defaults.runtime_provider || 'y4my'), profile:String(row?.feature_mode || row?.profile || 'mfg-only'), multiplier:String(typeof multiplier==='number'&&multiplier>=2?multiplier:row?.mfg_saved_multiplier??snapshot?.defaults.mfg_saved_multiplier??2), mfg_enabled:String(multiplier!==0&&multiplier!=='0'),mfg_mode:String(multiplier===0||multiplier==='0'?row?.mfg_saved_mode??snapshot?.defaults.mfg_saved_mode??0:multiplier==='auto'?0:row?.dynamic_mfg?2:1),nr:String(row?.nr_on_launch??snapshot?.defaults.nr_on_launch??false),...drafts.get(game.id)};
  const external = values.provider==='feeder'||values.provider==='vulkan-native';
  return `<section class="glass-section"><div class="section-heading"><h2>Package</h2><span class="state-label" id="draft-label">${drafts.has(game.id)?'Draft · not applied':!backend.enabled?'Read-only preview':''}</span></div><div class="inner-card">${selectField('provider','Feature package',[['y4my','OptiScaler'],['skynizz','Skynizz NR'],['dlss-unlocked','DLSS-Unlocked'],['feeder','Feeder NR'],...(values.provider==='vulkan-native'||row?.vulkan_available?[['vulkan-native','Native Vulkan'] as [string,string]]:[])],values.provider,row?.installed?'Another package applies after you restore this game.':'Games without DLSS get their NR package automatically.',!backend.enabled||Boolean(row?.installed))}${selectField('profile','Feature mode',[['mfg-only','MFG only'],['nr-only','NR only'],['nr-mfg','NR + MFG']],values.profile,'',!backend.enabled||Boolean(row?.installed))}</div><button class="quiet extra-actions" data-detail-section="overlay">${icon('sliders')}Overlay settings</button></section><section class="glass-section"><h2>Features</h2>${external?`<p>${values.provider==='feeder'?'Use ReShade’s NR panel in the running game to adjust passes, resolution, tone and structure.':'Adjust Vulkan NR and MFG in the running game’s rtxForge overlay.'}</p>`:`<div class="inner-card">${selectField('mfg_enabled','Frame generation',[['true','On'],['false','Off']],values.mfg_enabled,'',!backend.enabled)}${selectField('mfg_mode','MFG mode',[['0','Automatic'],['1','Custom'],...(row?.dynamic_mfg_available?[['2','Dynamic'] as [string,string]]:[])],values.mfg_mode,'',!backend.enabled||values.mfg_enabled==='false')}${selectField('multiplier','MFG multiplier',[['2','2×'],['3','3×'],['4','4×'],['5','5×'],['6','6×']],values.multiplier,'',!backend.enabled||values.mfg_enabled==='false'||values.mfg_mode==='0')}${selectField('nr','Enable NR on launch',[['false','Off'],['true','On']],values.nr,'',!backend.enabled)}</div>${schemaControls(game,values.provider)}`}<div class="section-footer"><button class="quiet" data-operation="reset" ${!backend.enabled||!row?.installed?'disabled':''}>Use library defaults</button><button class="primary" data-operation="apply" ${!backend.enabled||!row?.installed?'disabled':''}>Apply to this game</button></div></section>`;
}
function detailsAccent(game?: Game) {
  const accent = game && (gameAccentDrafts.get(game.id) || game.accent || game.artworkAccent);
  return accent && /^#[0-9a-f]{6}$/i.test(accent) ? accent : null;
}
function applyDetailsAccent() {
  if (view !== 'details') return;
  const content = document.querySelector<HTMLElement>('#content');
  if (!content) return;
  const game=selectedGame(),accent=detailsAccent(game);
  content.style.setProperty('--accent', accent || (appearance.theme === 'light' ? '#686663' : '#d8d5ce'));
  content.style.setProperty('--accent-ink', appearance.theme === 'light' ? 'var(--ink)' : accent || 'var(--ink)');
  content.style.setProperty('--primary-ink',selectionInk(accent||'#d8d5ce'));
  const page=content.querySelector<HTMLElement>('.details-page'),image=content.querySelector<HTMLImageElement>('.details-hero-image'),title=content.querySelector<HTMLElement>('.game-title');
  const titleRange=document.createRange();if(title)titleRange.selectNodeContents(title);
  const sampled=image&&title?sampleHero(image,titleRange.getBoundingClientRect(),true):null;
  const info=content.querySelector<HTMLElement>('.hero-info-card'),badge=content.querySelector<HTMLElement>('.hero-status');
  const cardSample=image&&info?sampleHero(image,info.getBoundingClientRect()):null;
  const colors=heroColors(accent||'#d8d5ce',appearance.theme==='light',sampled||undefined,cardSample||undefined);
  const badgeColors=heroBadge(image&&badge?sampleHero(image,badge.getBoundingClientRect())||undefined:undefined);
  content.style.setProperty('--game-title-color',colors.title);
  content.style.setProperty('--hero-card-color',colors.card);
  content.style.setProperty('--hero-card-ink',colors.ink);
  content.style.setProperty('--hero-badge-surface',badgeColors.surface);
  content.style.setProperty('--hero-badge-ink',badgeColors.ink);
  if(page)page.dataset.heroCard=colors.light?'light':'dark';
  content.dataset.gameAccent = String(Boolean(accent));
}
function detailAppearance(game: Game) {
  const accent = detailsAccent(game);
  return `<section class="glass-section"><h2>Game Accent</h2><p>${gameAccentDrafts.has(game.id) ? 'Local preview color. The saved game accent has not changed.' : game.accent ? `Saved library color · ${e(game.accent.toUpperCase())}` : game.artworkAccent ? `Artwork color from your library · ${e(game.artworkAccent.toUpperCase())}` : 'No artwork color available. This game uses neutral surfaces and controls.'}</p><div class="inner-card"><label class="field"><span><strong>Preview game accent</strong><small>Try a color in this preview.</small></span><input type="color" id="game-accent-color" value="${accent || '#d8d5ce'}" aria-label="Preview game accent" /></label>${toggle('tint','Accent tint','Tint these surfaces with this game’s configured or preview color.',appearance.tint)}</div><button class="quiet extra-actions" data-action="reset-game-accent" ${gameAccentDrafts.has(game.id)?'':'disabled'}>Use saved accent</button></section>${artworkEditor(game)}`;
}
function setupHero() {
  heroResize?.disconnect();
  const page = app.querySelector<HTMLElement>('.details-page'), scroller = app.querySelector<HTMLElement>('.details-scroll');
  const hero = app.querySelector<HTMLElement>('.details-hero'), nav = app.querySelector<HTMLElement>('.detail-nav');
  if (!page || !scroller || !hero || !nav) return;
  let expanded=270, compact=128, frame=0, measuredWidth=-1;
  const measure = () => {
    const identity=hero.querySelector<HTMLElement>('.details-identity');
    const back=hero.querySelector<HTMLElement>('.back');
    if (!identity || !back) return;
    // Measure the complete expanded header, even when resizing a collapsed one.
    const previousCompact=page.dataset.heroCompact, previousSummary=page.dataset.heroSummary;
    const previousLeft=page.style.getPropertyValue('--identity-left');
    page.dataset.heroCompact='false';page.dataset.heroSummary='true';
    page.style.setProperty('--identity-left','30px');
    const mobile=page.clientWidth<=760;
    expanded=Math.max(mobile?260:Math.max(240,Math.min(300,page.clientWidth*.2)),
      (mobile?16:18)+back.offsetHeight+18+identity.offsetHeight+(mobile?20:18));
    page.style.setProperty('--hero-expanded',expanded+'px');
    if(previousCompact===undefined)delete page.dataset.heroCompact;else page.dataset.heroCompact=previousCompact;
    if(previousSummary===undefined)delete page.dataset.heroSummary;else page.dataset.heroSummary=previousSummary;
    if(previousLeft)page.style.setProperty('--identity-left',previousLeft);else page.style.removeProperty('--identity-left');
    measuredWidth=page.clientWidth;
  };
  const apply = () => {
    frame=0;
    if(page.clientWidth!==measuredWidth)measure();
    if (page.clientWidth <= 760) { page.dataset.collapsing='false';page.dataset.heroCompact='false';page.dataset.heroScrolled='false';page.dataset.heroSummary='true';applyDetailsAccent();return; }
    page.dataset.collapsing='true';
    const removed=Math.min(scroller.scrollTop,expanded-compact), progress=removed/(expanded-compact);
    page.style.setProperty('--hero-expanded',expanded+'px');
    page.style.setProperty('--hero-compact',compact+'px');
    page.style.setProperty('--hero-height',expanded-removed+'px');
    page.style.setProperty('--hero-nav-height',(appearance.detailsNavigation==='sidebar'?20:nav.offsetHeight)+'px');
    page.style.setProperty('--poster-height',140-84*progress+'px');
    page.style.setProperty('--poster-radius',10-4*progress+'px');
    page.style.setProperty('--title-size',(selectedGame()!.name.length>28 ? 31-7*progress : 38-12*progress)+'px');
    page.style.setProperty('--art-opacity',String(.92*(1-progress)**2));
    page.style.setProperty('--identity-left',(removed>0?94:30)+'px');
    page.style.setProperty('--back-top',(18+24*progress)+'px');
    page.dataset.heroScrolled=String(removed>0);
    page.dataset.heroCompact=String(progress>=.65);
    page.dataset.heroSummary=String(progress<.3);
    const image=hero.querySelector<HTMLImageElement>('.details-hero-image');
    const chosen=selectedGame()?.heroFocus || [.5,.3];
    if (image && image.naturalWidth) {
      const shown=Math.max(hero.clientWidth/image.naturalWidth,hero.clientHeight/image.naturalHeight);
      const ratio=(view:number,extent:number,focus:number,target:number)=>extent-view<.5?.5:Math.min(1,Math.max(0,(target*view-focus*extent)/(view-extent)));
      image.style.objectPosition=`${ratio(hero.clientWidth,image.naturalWidth*shown,chosen[0],.5)*100}% ${ratio(hero.clientHeight,image.naturalHeight*shown,chosen[1],.4)*100}%`;
    }
    applyDetailsAccent();
  };
  scroller.addEventListener('scroll',()=>{if(!frame)frame=requestAnimationFrame(apply);},{passive:true});
  hero.querySelector('img')?.addEventListener('load',apply,{once:true});
  heroResize=new ResizeObserver(apply);heroResize.observe(page);apply();
  const image=hero.querySelector<HTMLImageElement>('.details-hero-image');if(image){image.crossOrigin='anonymous';image.addEventListener('load',()=>applyDetailsAccent(),{once:true});}requestAnimationFrame(()=>applyDetailsAccent());
  void document.fonts.ready.then(()=>{if(page.isConnected){measure();apply();}});
}

function schemaControls(game: Game, provider: string) {
  if (provider === 'feeder' || provider === 'vulkan-native') return '';
  const schema = snapshot?.controlSchema;
  if (!schema) return '';
  const row = engineRows.find(row => pathKey(row.game) === pathKey(game.path));
  const saved = (row?.feature_controls || snapshot?.defaults.feature_controls || {}) as Record<string, number>;
  const draft = drafts.get(game.id) || {};
  return `<details class="schema-controls"><summary>Advanced feature controls</summary><p class="subtle">The same control schema used by the overlay and existing Game Mode. Runtime units are preserved.</p>${schema.groups.filter(group => group.name !== 'Frame generation').map(group => {
    const controls = schema.controls.filter(control => control.group === group.name);
    if (!controls.length) return '';
    return `<section class="schema-group"><h3>${e(group.name)}</h3><div class="inner-card">${controls.map(control => {
      const value = Number(draft['control-' + control.key] ?? saved[control.key] ?? control.default);
      const disabled = !backend.enabled || provider !== 'skynizz' && !['intensity', 'sharpness'].includes(control.key);
      const label = `<span><strong>${e(control.label.replaceAll('Colour', 'Color'))}</strong><small>${e(control.advanced || '')}${disabled ? ' · Skynizz controls' : ''}</small></span>`;
      if (control.values || control.kind === 'toggle') {
        const values = control.values || [0, 1], names = control.choices || ['Off', 'On'];
        return `<label class="field">${label}<select data-draft="control-${control.key}" ${disabled ? 'disabled' : ''}>${values.map((number, index) => `<option value="${number}" ${number === value ? 'selected' : ''}>${e(names[index] || number)}</option>`).join('')}</select></label>`;
      }
      return `<div class="field">${label}${numberControl(`<input class="control-number" type="number" data-draft="control-${control.key}" min="${control.min}" max="${control.max}" step="${control.step || .01}" value="${value}" aria-label="${e(control.label)}" ${disabled ? 'disabled' : ''} />`,disabled,control.label)}</div>`;
    }).join('')}</div></section>`;
  }).join('')}</details>`;
}
function pathKey(value: string) { const key = value.replace(/\\/g, '/'); return snapshot?.platform === 'Windows' ? key.toLocaleLowerCase() : key; }
function detailTools(game: Game, row?: EngineRow) {
  if (detailsSection === 'artwork') return artworkEditor(game);
  if (detailsSection === 'overlay') return gameOverlaySettings(game);
  const actionCard=(title:string,copy:string,attributes:string,caption:string)=>`<article class="inner-card action-card"><div><h3>${title}</h3><p>${e(copy)}</p></div><button class="quiet" ${attributes} ${!backend.enabled?'disabled':''}>${caption}</button></article>`;
  if (detailsSection === 'files') return `<section class="glass-section"><h2>File Management</h2><div class="package-columns detail-card-row">${actionCard('Update DLSS','Update older DLSS files. Backups are kept for restoration.','data-operation="update-dlss"','Update')}${actionCard('Restore original DLSS files','Review the existing updater backups for this game.','data-contract="dlss_restore_review"','Restore')}</div></section><section class="glass-section"><h2>Installed DLSS Files</h2><div class="inner-card detail-action-row"><span>${e(row?.dlss_version || game.savedRecord?.dlss_version || 'File inventory has not been loaded in this preview.')}</span><button class="quiet" data-contract="dlss_inventory" ${!backend.enabled?'disabled':''}>Inspect files</button></div></section>`;
  if (detailsSection === 'notes') return `<section class="glass-section"><h2>Your Notes</h2><p>Kept with this game in rtxForge. Included in bug reports when you choose.</p><label class="notes-field"><span>Notes</span><textarea id="game-notes" rows="10" ${!backend.enabled||!notesLoaded.has(game.id)?'disabled':''}>${e(noteDrafts.get(game.id) ?? game.notes ?? '')}</textarea></label><button class="primary extra-actions" data-action="save-notes" ${!backend.enabled||!notesLoaded.has(game.id)?'disabled':''}>Save Notes</button></section>`;
  return `<section class="glass-section"><h2>Tools</h2><div class="package-columns detail-card-row">${actionCard('Game Folder',game.path,'data-action="copy-game-path"','Copy location')}${actionCard('Diagnose NR','Read the saved NR settings, runtime hashes and log evidence.','data-contract="diagnose"','Diagnose')}</div></section><section class="glass-section"><h2>RenoDX HDR</h2><p>The matching HDR mod and its dependencies, managed together.</p><div class="inner-card detail-action-row"><div><strong>HDR enhancement</strong><p>Review the matching mod and required ReShade files for this game.</p></div><div class="operation-actions"><button class="quiet" data-contract="hdr_review" ${!backend.enabled?'disabled':''}>Install HDR</button><button class="quiet" data-contract="hdr_review" data-remove="true" ${!backend.enabled?'disabled':''}>Remove HDR</button></div></div><div class="inner-card detail-action-row extra-actions"><div><strong>Custom HDR package</strong><p>Choose a RenoDX .addon64 or .addon32 file. Architecture and exact files are checked before installation.</p></div><button class="quiet" data-tool-kind="hdr-custom" ${!backend.enabled?'disabled':''}>Use custom package…</button></div></section><section class="glass-section"><h2>Graphics Tools</h2><p>Check NR or add ReShade to this game. Existing graphics files are kept safe.</p><div class="package-columns detail-card-row">${actionCard('Install ReShade','Download and install the official ReShade runtime for this game.','data-action="official-reshade"','Install')}${actionCard('Import ReShade package','Add a ZIP, custom runtime, add-on, shader or preset INI. Review the exact files before importing.','data-tool-kind="reshade-import"','Choose…')}${actionCard('Install Add-on','Choose another .addon64 file. RenoDX HDR is managed above.','data-tool-kind="addon"','Choose…')}</div>${toolImportOpen?`<div class="inner-card tool-import"><label class="field"><span><strong>${extraKind==='hdr-custom'?'Custom RenoDX package':extraKind==='addon'?'Add-on file':'ReShade package'}</strong></span><input id="extra-source" type="text" value="${e(extraSource)}" ${!backend.enabled?'disabled':''}/></label><button class="primary" data-action="review-extra" ${!backend.enabled||!extraSource?'disabled':''}>Review exact files</button></div>`:''}<div class="operation-actions extra-actions"><button class="quiet" data-action="extra-records" ${!backend.enabled?'disabled':''}>Show tool recovery records</button></div><div class="tool-records">${extraRecords.map((record,index)=>`<button class="quiet" data-extra-restore="${index}" ${!backend.enabled?'disabled':''}>Restore ${e(record.title||record.kind)}</button>`).join('')}</div></section>`;
}

function approvedImageUrl(raw: unknown) {
  try { const url = new URL(String(raw)); return url.protocol === 'https:' && ['cdn2.steamgriddb.com', 'cdn.steamgriddb.com'].includes(url.hostname) ? url.href : ''; } catch { return ''; }
}
function artworkEditor(game: Game) {
  return `<section class="glass-section"><h2>Game artwork</h2><p>Choose your own artwork or browse SteamGridDB. Saved artwork belongs to this installation; Steam sync is a separate review.</p><div class="inner-card"><label class="field"><span><strong>Artwork role</strong></span><select id="artwork-role">${['poster', 'capsule', 'hero', 'logo'].map(role => `<option value="${role}" ${role === artworkRole ? 'selected' : ''}>${role[0].toUpperCase() + role.slice(1)}</option>`).join('')}</select></label><label class="field"><span><strong>Image file</strong><small>Use a portrait poster or a landscape capsule/hero.</small></span><input id="artwork-source" type="text" value="${e(artworkPath)}" ${!backend.enabled ? 'disabled' : ''} /></label></div><div class="operation-actions extra-actions"><button class="primary" data-action="artwork-store" ${!backend.enabled ? 'disabled' : ''}>Use image file</button><button class="quiet" data-action="artwork-reset" ${!backend.enabled ? 'disabled' : ''}>Use automatic artwork</button><button class="quiet" data-action="artwork-sync" ${!backend.enabled || snapshot?.platform !== 'Windows' ? 'disabled' : ''}>Review Steam sync</button></div>${artworkMessage ? `<p role="status">${e(artworkMessage)}</p>` : ''}</section><section class="glass-section"><h2>SteamGridDB</h2><p>${gridConnected === null ? 'Check your existing account connection to browse artwork.' : gridConnected ? 'Connected through the existing credential service.' : 'Connect your own API key through the existing secure credential store.'}</p><div class="operation-actions"><button class="quiet" data-action="sgdb-status" ${!backend.enabled ? 'disabled' : ''}>Check connection</button>${gridConnected ? `<button class="quiet" data-action="sgdb-disconnect" ${!backend.enabled ? 'disabled' : ''}>Disconnect</button>` : `<input id="sgdb-key" type="password" autocomplete="off" aria-label="SteamGridDB API key" placeholder="SteamGridDB API key" ${!backend.enabled ? 'disabled' : ''} /><button class="quiet" data-action="sgdb-connect" ${!backend.enabled ? 'disabled' : ''}>Connect</button>`}</div><label class="field"><span><strong>Find game artwork</strong></span><input id="artwork-query" type="search" value="${e(artworkQuery || game.name)}" ${!backend.enabled ? 'disabled' : ''} /></label><button class="quiet" data-action="sgdb-search" ${!backend.enabled || !gridConnected ? 'disabled' : ''}>Search SteamGridDB</button><div class="artwork-matches">${artworkMatches.map(match => `<button class="quiet" data-artwork-game="${match.id}">${e(match.name)}</button>`).join('')}</div><div class="artwork-assets">${artworkAssets.map((asset, index) => `<button class="artwork-asset" data-artwork-asset="${index}" aria-label="Use artwork by ${e(asset.author)}">${approvedImageUrl(asset.thumb) ? `<img src="${e(approvedImageUrl(asset.thumb))}" alt="" loading="lazy" />` : icon('palette')}<span>${e(asset.author)}<small>${e(asset.width)} × ${e(asset.height)}</small></span></button>`).join('')}</div></section>`;
}
function gameOverlaySettings(game: Game) {
  const overrides = (sharedPreferences?.game_overlay_settings || {}) as Record<string, Record<string, unknown>>;
  const identity = Object.keys(overrides).find(key => pathKey(key) === pathKey(game.path)) || game.path;
  const current = { ...sharedPreferences, ...overrides[identity], ...gameOverlayDrafts.get(game.id) };
  const fields: [string, string, [unknown, string][]][] = [
    ['overlay_controls', 'Controls', [['unified', 'Unified'], ['classic', 'Advanced']]],
    ['overlay_welcome', 'Welcome message', [[false, 'Off'], [true, 'On']]],
    ['overlay_live_stats', 'Live statistics', [[false, 'Off'], [true, 'On']]],
    ['optiscaler_ui', 'OptiScaler menu', [[false, 'Off'], [true, 'On']]],
    ['optiscaler_intro', 'OptiScaler intro', [[false, 'Off'], [true, 'On']]],
    ['optiscaler_hotkey', 'OptiScaler shortcut', [['Insert', 'Insert'], ['F8', 'F8'], ['Disabled', 'Disabled']]],
    ['reshade_ui', 'ReShade menu', [[false, 'Off'], [true, 'On']]],
    ['reshade_intro', 'ReShade welcome', [[false, 'Off'], [true, 'On']]],
  ];
  return `<section class="glass-section"><h2>Overlay for this game</h2><p>${overrides[identity] ? 'This game has its own overlay choices.' : 'This game currently inherits app settings.'} Native menu changes take effect after restarting the game.</p>${!sharedPreferences ? '<button class="quiet" data-action="load-settings">Load current overlay settings</button>' : ''}<div class="inner-card">${fields.map(([key, title, options]) => `<label class="field"><span><strong>${title}</strong></span><select data-game-overlay="${key}" ${!sharedPreferences ? 'disabled' : ''}>${options.map(([value, label]) => `<option value="${e(JSON.stringify(value))}" ${JSON.stringify(value) === JSON.stringify(current[key]) ? 'selected' : ''}>${label}</option>`).join('')}</select></label>`).join('')}</div><div class="operation-actions extra-actions"><button class="primary" data-action="save-game-overlay" ${!backend.enabled || !sharedPreferences ? 'disabled' : ''}>Review this game’s preferences</button><button class="quiet" data-action="inherit-game-overlay" ${!backend.enabled || !sharedPreferences ? 'disabled' : ''}>Use app settings</button><button class="quiet" data-action="apply-game-overlay" ${!backend.enabled || !sharedPreferences ? 'disabled' : ''}>Review overlay update</button></div></section>`;
}
function startupSettingsView() {
  if(!pendingInstall)return '';
  const values=pendingInstall.settings,provider=String(values.runtime_provider),featureMode=String(pendingInstall.params.mode),controls=values.feature_controls as Record<string,number>||{},mfg=values.mfg_multiplier!==0,mode=Number(values.mfg_saved_mode||0);
  const fields=(keys:string[])=>tuningFields(keys,Object.fromEntries(keys.map(key=>[key,Number(controls[key]??(key==='intensity'?values.nr_strength:key==='sharpness'?values.sharpening_strength:key==='enabled'?Number(values.nr_on_launch):undefined)??snapshot?.controlSchema?.controls.find(c=>c.key===key)?.default)])),key=>provider!=='skynizz'&&!['enabled','intensity','sharpness'].includes(key),'data-startup-control');
  const dynamic=pendingInstall.rows.every(row=>row.dynamic_mfg_available===true);
  const segments=(kind:string,options:[number,string][])=>`<div class="preset-segments" role="group" aria-label="${kind==='mode'?'MFG mode':'MFG multiplier'}">${options.map(([key,label])=>`<button data-startup-${kind}="${key}" aria-pressed="${kind==='mode'?mode===key:Number(values.mfg_saved_multiplier)===key}" ${!mfg?'disabled':''}>${label}</button>`).join('')}</div>`;
  const card=(title:string,body:string)=>`<section class="inner-card startup-group preset-pod"><h2>${title}</h2>${body}</section>`;
  const frame=`<section class="inner-card startup-group preset-pod"><div class="section-heading"><h2>Multi-Frame Generation</h2><select id="startup-mfg-enabled" aria-label="Multi-Frame Generation"><option value="true" ${mfg?'selected':''}>On</option><option value="false" ${!mfg?'selected':''}>Off</option></select></div>${segments('mode',[[0,'Automatic'],[1,'Custom'],...(dynamic?[[2,'Dynamic'] as [number,string]]:[])])}${mode!==0&&mfg?`<p class="subtle">${mode===2?'Maximum multiplier':'Multiplier'}</p>${segments('ratio',[2,3,4,5,6].map(n=>[n,n+'×']))}`:''}</section>`;
  const nr=provider==='feeder'?'<p>Adjust neural rendering in the running game’s ReShade panel.</p>':fields(['enabled','style','intensity','preset','passes']);
  return `<div class="startup-columns">${featureMode!=='nr-only'?frame:''}${featureMode!=='mfg-only'?card('Neural rendering',nr):''}</div>${provider==='feeder'?'':`<details class="startup-more"><summary>More settings</summary><div class="preset-columns"><div>${card('DLSS presets',fields(['dlss_preset','rr_preset']))}${card('Image tuning',fields(['detail','colour'])+`<details><summary>Fine tuning</summary>${fields(['structure','tone','skin','auto_mask'])}</details>`)}</div><div>${card('Sharpening',fields(['sharpen','sharpen_shader','sharp_override','sharpness'])+`<details><summary>Motion sharpening</summary>${fields(['motion_sharpen','motion_sharpness'])}</details>`)}${card('Performance',fields(snapshot?.controlSchema?.controls.filter(item=>item.group==='Performance').map(item=>item.key)||[]))}</div></div></details>`}`;

}
function applyOperationAccent() {
  if(view!=='operation'||!operation?.kind)return;
  const progress=operation.progress||{},game=flowGame({...progress,name:progress.game||progress.name},snapshot?.games||[])||(operation.targets?.length===1?operation.targets[0]:undefined),accent=game?detailsAccent(game):null;
  const content=app.querySelector<HTMLElement>('#content');if(content){
    for(const key of ['--accent','--accent-ink','--primary-ink'])content.style.removeProperty(key);
    if(accent){content.style.setProperty('--accent',accent);content.style.setProperty('--accent-ink',appearance.theme==='light'?'var(--ink)':accent);content.style.setProperty('--primary-ink',selectionInk(accent));}
  }
  const backdrop=app.querySelector<HTMLElement>('.flow-artwork'),source=game?.hero;
  if(!backdrop)return;
  if(!source){backdrop.querySelectorAll('img').forEach(img=>img.remove());delete backdrop.dataset.source;return;}
  if(backdrop.dataset.source===source)return;
  backdrop.dataset.source=source;const before=[...backdrop.querySelectorAll('img')],next=new Image();next.alt='';next.src=source;next.dataset.visible='false';
  next.onload=()=>{if(!backdrop.isConnected)return;requestAnimationFrame(()=>{next.dataset.visible='true';for(const old of before)old.dataset.visible='false';});setTimeout(()=>before.forEach(old=>old.remove()),700);};
  backdrop.append(next);if(next.complete)next.dispatchEvent(new Event('load'));
}
function operationView() {
  if (!operation) return heading('Operations', 'No operation is active.');
  const state = operation, review = state.review;
  if(state.kind)return operationFlow(state,snapshot?.games||[],icon,startupSettingsView(),supportedReviews(review));
  const entries = review?.rows || review?.items || [];
  return heading(e(state.title), state.stage === 'checking' ? 'Checking the exact selection with the shared engine…' : state.stage === 'running' ? 'The existing engine is applying the reviewed changes.' : state.stage === 'review' ? 'Your files change only after you confirm this exact review.' : '') +
    `<section class="operation-workspace glass-section">${state.stage === 'checking' || state.stage === 'running' ? `<div class="operation-progress">${icon('refresh')}<h2>${state.stage === 'checking' ? 'Preparing review' : 'Working'}</h2><p role="status">${e(state.progress?.label || state.progress?.phase || 'Waiting for the engine to report progress…')}</p>${typeof state.progress?.fraction === 'number' ? `<progress max="1" value="${state.progress.fraction}" aria-label="Engine progress"></progress>` : ''}<p class="subtle">${e(state.progress?.game || '')}</p></div>` : ''}
    ${state.stage === 'review' && review ? `${review.summary ? `<p>${e(review.summary)}</p>` : ''}<div class="review-items">${entries.map(item => `<article class="inner-card"><strong>${e(item.name || item.title || 'Selected change')}</strong><p>${e(item.detail || item.summary || item.badge || '')}</p>${item.game ? `<p class="path">${e(item.game)}</p>` : ''}${item.details ? `<pre>${e(item.details)}</pre>` : ''}</article>`).join('')}</div>${supportedReviews(review)}${review.blocked?.length ? notice('Skipped by the engine', review.blocked.map(item => `${e(item.name || item.title)}: ${e(item.reason || item.detail)}`).join('<br>'), 'warning') : ''}${review.warnings?.length ? notice('Review warnings', review.warnings.map(item => `${e(item.name)}: ${e(item.reason)}`).join('<br>'), 'warning') : ''}${review.note ? `<p>${e(review.note)}</p>` : ''}${review.trust ? `<label class="trust-choice"><input id="review-trust" type="checkbox" />${e(review.trust)}</label>` : ''}<div class="operation-actions"><button class="quiet" data-action="discard-review">Back</button><button class="primary" data-action="confirm-operation" ${!entries.length || review.trust ? 'disabled' : ''}>${e(review.action || 'Confirm changes')}</button></div>` : ''}
    ${state.stage === 'running' && review ? '<button class="quiet" data-action="cancel-operation">Request cancellation</button>' : ''}
    ${state.stage === 'done' ? `${state.execute === 'report-draft' ? reportForm(state.result) : `<h2>Engine result</h2><pre class="result-output">${e(typeof state.result === 'string' ? state.result : JSON.stringify(state.result, null, 2))}</pre>`}${state.execute === 'recoveries' && Array.isArray(state.result) ? `<div class="operation-actions">${state.result.map((record, index) => `<button class="quiet" data-recovery="${index}">Review ${e(record.name || 'recovery')}</button>`).join('')}</div>` : ''}${state.execute === 'art-profiles' && Array.isArray(state.result) ? `<div class="profile-choices">${state.result.map((profile,index)=>`<button class="quiet" data-steam-profile="${index}">${e(profile.userid)}${profile.selected?' · Selected':''}<small>${e(profile.root)}</small></button>`).join('')}</div>` : ''}${state.execute === 'inspect-package' && (state.result as Record<string, unknown>)?.deployable ? '<label class="trust-choice"><input id="package-trust" type="checkbox" />I trust the source of this exact package.</label><button class="primary" data-action="use-package" disabled>Use this package</button>' : ''}<button class="primary" data-action="operation-back">Back to game</button>` : ''}
    ${state.stage === 'error' ? `${notice('Operation did not complete', e(state.error), 'warning')}<button class="quiet" data-action="operation-back">Back to game</button>` : ''}</section>`;
}
type ReportDraft = { reports: { id: string; name: string; fields: Record<string, string> }[]; fields: { id: string; label: string; choices: string[]; required: boolean; max: number }[] };
function supportedReviews(review?: Review) {
  if (!review?.supported?.length) return '';
  return `<fieldset class="supported-reviews"><legend>Optional supported features</legend>${review.supported.map(offer => `<label class="supported-choice inner-card"><input type="checkbox" data-supported-token="${e(offer.token)}" /><span><strong>Include ${offer.nr && offer.mfg ? 'NR + MFG' : offer.nr ? 'NR only' : 'MFG only'}</strong><small>${e(offer.reason)}</small><small>${offer.rows.map(row => e(row.name)).join(' · ')}</small></span></label>`).join('')}</fieldset>`;
}
function syncReviewConfirm() {
  const state = operation, button = app.querySelector<HTMLButtonElement>('[data-action="confirm-operation"]');
  if (!state?.review || !button) return;
  const selectedOffers=[...app.querySelectorAll<HTMLInputElement>('[data-supported-token]:checked')].map(node=>state.review!.supported?.find(offer=>offer.token===node.dataset.supportedToken));
  const count=new Set([...(state.review.rows||state.review.items||[]),...selectedOffers.flatMap(offer=>offer?.rows||[])].map(row=>String(row.game||row.name))).size;
  const hasChanges = count>0;
  const summary=app.querySelector('.flow-summary h2');if(summary)summary.textContent=count?`${count} game${count===1?'':'s'} ready`:'Nothing ready yet';
  const acknowledged = !state.review.trust || Boolean(app.querySelector<HTMLInputElement>('#review-trust')?.checked);
  button.disabled = !hasChanges || !acknowledged;
}
function reportForm(result: unknown) {
  const draft = result as ReportDraft;
  return `<h2>Your report</h2><p>Correct the engine’s recorded facts and add what you observed. You review redacted contents before a local ZIP is saved.</p>${draft.reports.map(report => `<h3 class="game-title">${e(report.name)}</h3><div class="inner-card">${draft.fields.map(field => `<label class="field"><span><strong>${e(field.label)}</strong>${field.required ? '<small>Required</small>' : ''}</span>${field.choices.length ? `<select data-report-id="${report.id}" data-report-field="${field.id}"><option value="">Choose…</option>${field.choices.map(choice => `<option ${choice === (reportEdits[report.id]?.[field.id] ?? report.fields[field.id]) ? 'selected' : ''}>${e(choice)}</option>`).join('')}</select>` : `<input type="text" data-report-id="${report.id}" data-report-field="${field.id}" value="${e(reportEdits[report.id]?.[field.id] ?? report.fields[field.id])}" maxlength="${field.max || 10000}" />`}</label>`).join('')}</div>`).join('')}<label class="trust-choice"><input type="checkbox" id="report-logs" />Include this session’s logs</label><label class="trust-choice"><input type="checkbox" id="report-notes" />Include my game notes</label><button class="primary" data-action="review-report">Review redacted report</button>`;
}
async function withOperation(title: string, method: string, params: Record<string, unknown>, execute = 'run') {
  const origin = view === 'operation' ? operation?.origin || 'details' : view;
  const kind=method==='prepare_routes'?String(params.operation||'apply'):method==='prepare_dlss'?'update-dlss':undefined;
  const targets=kind?(snapshot?.games||[]).filter(game=>((params.rows||[]) as EngineRow[]).some(row=>pathKey(row.game)===pathKey(game.path))):undefined;
  const state = { stage: 'checking' as const, title, execute, origin, method,kind,targets, changedKeys: Object.keys((params.changes || {}) as object) };
  operation = state; setView('operation');
  try {
    const result = await engineRequest<Review>(method, params, progress => { if (operation) { operation.progress = progress; render(); } });
    if (!operation || operation !== state || operation.dismissed) {
      if (result?.token) await engineRequest(execute === 'execute_routes' ? 'discard_routes' : execute === 'run' ? 'discard' : 'discard_operation', execute === 'run' ? { token: result.token } : { tokens: [result.token] });
      return;
    }
    if (result?.token && execute !== 'inspect-package') { operation.review = result; operation.stage = 'review'; operation.title = result.title || title; }
    else { operation.stage = 'done'; operation.result = result; }
  } catch (problem) { if (operation === state && !operation.dismissed) { operation.stage = 'error'; operation.error = problem instanceof Error ? problem.message : 'The engine could not complete the request.'; } else return; }
  render(); document.querySelector<HTMLElement>('#page-title')?.focus();
}
async function getEngineRows(target?: Game) {
  if (!backend.enabled) throw new Error(backend.reason);
  const game = target || selectedGame();
  if (!game) return [];
  const draft = drafts.get(game.id) || {};
  const rows = await engineRequest<EngineRow[]>('scan_game', { folder: game.path, runtime_provider: draft.provider || snapshot?.defaults.runtime_provider || 'y4my', feature_mode: draft.profile || 'mfg-only' });
  engineRows = [...engineRows.filter(row => !rows.some(next => pathKey(next.game) === pathKey(row.game))), ...rows];
  return rows;
}
async function runOperation(kind: string, batch = false, scope = false) {
  const game = selectedGame(); if (!game) return;
  operation = { stage: 'checking', title: 'Preparing', execute: 'execute',kind,targets:batch||scope?filteredLibrary():[game], origin: view }; const state = operation; setView('operation');
  try {
    const targets = batch || scope&&batchSelection.size ? (snapshot?.games.filter(game => batchSelection.has(game.id)) || []) : scope ? filteredLibrary() : [game];
    const rows: EngineRow[] = [];
    for (const target of targets) rows.push(...await getEngineRows(target));
    if (state.dismissed || operation !== state) return;
    if(kind==='uninstall'){const installed=rows.filter(row=>row.installed);rows.splice(0,rows.length,...installed);}
    const row = rows[0];
    if (!row) throw new Error('The engine could not verify this installation. Refresh the library and check its executable in the existing app.');
    const draft = drafts.get(game.id) || {};
    const currentMultiplier = row.mfg_multiplier ?? snapshot?.defaults.mfg_multiplier ?? 'auto';
    const currentMode = currentMultiplier === 0 ? row.mfg_saved_mode ?? snapshot?.defaults.mfg_saved_mode ?? 0 : currentMultiplier === 'auto' ? 0 : row.dynamic_mfg ? 2 : 1;
    const mode = Number(draft.mfg_mode ?? currentMode);
    const ratio = Number(draft.multiplier ?? (typeof currentMultiplier === 'number' && currentMultiplier >= 2 ? currentMultiplier : row.mfg_saved_multiplier ?? snapshot?.defaults.mfg_saved_multiplier ?? 2));
    const enabled = draft.mfg_enabled !== undefined ? draft.mfg_enabled === 'true' : (row.mfg_multiplier ?? snapshot?.defaults.mfg_multiplier) !== 0;
    const settings = { runtime_provider: draft.provider || row.runtime_provider || snapshot?.defaults.runtime_provider || 'y4my',
      mfg_provider: snapshot?.defaults.mfg_provider || 'universal', nr_on_launch: draft.nr ? draft.nr === 'true' : snapshot?.defaults.nr_on_launch === true,
      mfg_multiplier: !enabled ? 0 : mode === 0 ? 'auto' : ratio,
      dynamic_mfg: enabled && mode === 2 ? 1 : 0, mfg_saved_mode: mode, mfg_saved_multiplier: ratio,
      nr_strength: Number(draft['control-intensity'] ?? row.nr_strength ?? snapshot?.defaults.nr_strength ?? 2),
      sharpening_strength: Number(draft['control-sharpness'] ?? row.sharpening_strength ?? snapshot?.defaults.sharpening_strength ?? .5),
      feature_controls: { ...(row.feature_controls as Record<string, unknown> || {}), ...Object.fromEntries(Object.entries(draft).filter(([key]) => key.startsWith('control-')).map(([key, value]) => [key.slice(8), Number(value)])) } };
    const params=kind==='update-dlss'?{rows}:{rows,mode:scope||batch?libraryMode||String(snapshot?.defaults.default_profile||'mfg-only'):draft.profile||String(row.feature_mode||row.profile||'mfg-only'),operation:kind,settings};
    if(kind==='install'){
      pendingInstall={params,settings,rows};state.targets=targets;state.stage='startup';state.title='Install Features';render();app.querySelector<HTMLElement>('#page-title')?.focus();return;
    }
    await withOperation('Review '+kind,kind==='update-dlss'?'prepare_dlss':'prepare_routes',params,kind==='update-dlss'?'update_dlss':'execute_routes');
  } catch (problem) { if (operation) { operation.stage = 'error'; operation.error = problem instanceof Error ? problem.message : 'Review failed.'; render(); } }
}
function packages() {
  const records = liveCatalog || snapshot?.catalog || [];
  const fallback = snapshot?.packages || [];
  const packageCard = (item: Record<string,unknown>, automatic=false) => `<article class="inner-card package-option"><div><h3 class="game-title">${e(item.name)}</h3><p class="version">${e(item.version || '')}</p></div>${item.summary ? `<p>${e(item.summary)}</p>` : ''}<button class="quiet" data-provider-default="${e(item.id)}" ${!backend.enabled||automatic||!item.available?'disabled':''}>${automatic?'Used automatically':'Use for DLSS games'}</button></article>`;
  const nr = records.filter(item=>item.id==='skynizz'||item.automatic);
  const unified = records.length ? records.filter(item=>['dlss-unlocked','y4my'].includes(item.id)) : fallback.filter(item=>['dlss-unlocked','y4my'].includes(item.id));
  const pair = records.find(item=>item.id==='skynizz');
  const versions = (pair?.mfg_versions||{}) as Record<string,string>;
  const mfg = [['universal','Universal MFG','OptiScaler plugin','Keeps NVIDIA’s DLSS Frame Generation and unlocks 3× to 6× where the driver allows 2×.'],['integrated','Integrated MFG unlock','Built into the bridge','Patches NVIDIA’s DLSS Frame Generation for 3× to 6× with no extra plugin.'],['mfg-unlock','MFG Unlock','ReShade add-on','Raises NVIDIA’s DLSS Frame Generation multiplier through ReShade.']];
  return heading('Packages','Choose what rtxForge installs. Every game change is reviewed before it is applied.')+`<div class="package-columns"><section class="glass-section"><h2>NR packages</h2><p>Choose one for games with DLSS. Feeder and Vulkan packages are used automatically for the games they cover.</p><div class="package-options">${nr.length?nr.map(item=>packageCard(item,Boolean(item.automatic))).join(''):fallback.filter(item=>item.id==='skynizz').map(item=>packageCard(item as unknown as Record<string,unknown>)).join('')}</div></section><section class="glass-section"><h2>MFG packages</h2><p>Native NVIDIA frame generation for Skynizz NR.</p><div class="package-options">${mfg.map(([id,name,kind,summary])=>`<article class="inner-card package-option"><div><h3 class="game-title">${name}</h3><p class="version">${e(versions[id]||kind)}</p></div><p>${summary}</p><button class="quiet" data-mfg-default="${id}" ${!backend.enabled?'disabled':''}>Use with Skynizz NR</button></article>`).join('')}</div></section></div><section class="glass-section unified-packages"><h2>Unified packages</h2><p>NR and MFG together in one package.</p><div class="package-columns">${unified.map(item=>packageCard(item as Record<string,unknown>)).join('')}</div></section><section class="glass-section package-policy"><h2>Your own package</h2><p>Inspect a ZIP archive and review its settings before using it. Instructions are never run.</p><label class="field"><span><strong>Archive path</strong></span><input id="package-source" value="${e(packageSource)}" ${!backend.enabled?'disabled':''}/></label><button class="quiet" data-action="inspect-package" ${!backend.enabled?'disabled':''}>Choose archive</button></section>`;
}

function extras() {
  const tool = (title:string,copy:string,action:string,caption:string,glyph:string) => `<article class="glass-section tool-card"><div class="tool-heading">${icon(glyph)}<h2>${title}</h2></div><p>${copy}</p><button class="quiet" data-action="${action}" ${!backend.enabled?'disabled':''}>${caption}</button></article>`;
  return heading('Extras','Tools for your whole library. Every game change is reviewed before it is applied.')+`<div class="extra-top-tools">${tool('Update the rtxForge Overlay','Bring the in-game overlay in your installed games up to date. Tuning and restore backups are kept.','overlay-package-review','Review overlay updates','sliders')}${tool('Update DLSS files','Replace older DLSS files across your library. Originals are backed up.','extras-dlss','Review games','download')}${tool('Undo previous changes','Restore the files from an earlier install, update or restore.','recoveries','Show changes','refresh')}</div>${tool('RenoDX HDR','Install matching HDR mods automatically, or import a custom RenoDX package for a game.','extras-hdr','Choose game','palette')}<div class="package-columns extras-bottom"><section class="glass-section"><h2>Global Settings</h2><p>Turn neural rendering or frame generation on or off, or set the multiplier, in every game with a package installed. Defaults for future installs stay the same.</p><div class="inner-card"><label class="field"><span><strong>Neural rendering</strong></span><select id="global-nr" ${!backend.enabled?'disabled':''}><option value="keep">Leave as is</option><option value="false">Off</option><option value="true">On</option></select></label><label class="field"><span><strong>Multi-Frame Generation</strong></span><select id="global-mfg" ${!backend.enabled?'disabled':''}><option value="keep">Leave as is</option><option value="0">Off</option>${[2,3,4,5,6].map(value=>`<option value="${value}">${value}×</option>`).join('')}<option value="-1">Follow game</option></select></label></div><button class="primary extra-actions" data-action="global-review" ${!backend.enabled?'disabled':''}>Review changes</button></section>${tool('App storage','Downloads, backups and caches rtxForge keeps. Clean up what no game needs.','storage-inventory','View usage','folder')}</div>`;
}
function toggle(id: string, title: string, description: string, on: boolean) {
  return `<div class="field"><span><strong id="${id}-label">${title}</strong><small id="${id}-help">${description}</small></span><button class="toggle" role="switch" aria-labelledby="${id}-label" aria-describedby="${id}-help" aria-checked="${on}" data-toggle="${id}"><span></span></button></div>`;
}
function settings() {
  const markup = originalSettings();
  const start = markup.indexOf('<nav class="settings-tabs"');
  const end = markup.indexOf('</nav>',start)+6;
  return markup.slice(0,start)+`<div class="settings-workspace">${markup.slice(start,end)}<div class="settings-body">${markup.slice(end)}</div></div>`;
}
function originalSettings() {
  const menu = `<nav class="settings-tabs" aria-label="Settings sections">${settingsSections.map(([category,label,glyph]) => `<button data-settings-category="${category}" aria-pressed="${settingsCategory === category}">${icon(glyph)}<span>${label}</span></button>`).join('')}</nav>`;
  return heading('Settings', 'Make room for the way you play.') + menu + (settingsCategory !== 'appearance' ? sharedSettings() :
    appearanceSettings());
}
function appearanceSettings() {
  const group=(title:string,copy:string,body:string,extra='')=>`<section class="glass-section setting-group ${extra}"><h2>${title}</h2>${copy?`<p>${copy}</p>`:''}${body}</section>`;
  const select=(id:string,title:string,copy:string,options:[string,string][],value:string)=>`<label class="field"><span><strong>${title}</strong>${copy?`<small>${copy}</small>`:''}</span><select id="${id}">${options.map(([key,label])=>`<option value="${key}" ${value===key?'selected':''}>${label}</option>`).join('')}</select></label>`;
  const themes=`<div class="theme-options" role="group" aria-label="Color theme">${(['clear','light','dark'] as const).map(theme=>`<button class="theme-choice theme-${theme}" data-theme-choice="${theme}" aria-pressed="${appearance.theme===theme}"><span class="material-sample" aria-hidden="true"><i></i><i></i></span><span>${theme[0].toUpperCase()+theme.slice(1)}</span>${appearance.theme===theme?icon('check'):''}</button>`).join('')}</div>`;
  const scale='__TAURI_INTERNALS__' in window?select('display-scale','Interface scale','Size of the interface on this display.',[['auto','Automatic'],...[100,125,130,150,175,200].map(n=>[String(n),n+'%'] as [string,string])],String(appearance.scale)):'';
  return `<div class="settings-groups appearance-groups">${group('Surface','Choose the glass material for Game Mode.',themes,'appearance')}${group('Main interface','Color for the main navigation, buttons and focus.',`<div class="inner-card"><label class="field color-field"><span><strong>Accent color</strong><small>Independent of each game’s artwork color.</small></span><input type="color" id="accent-color" value="${appearance.accent}" aria-label="Accent color" /></label><div class="background-field"><span><strong>Background</strong><small>Your image for the main Game Mode interface.</small></span><div class="background-picker"><div class="background-preview"><img src="${e(appearance.background||(appearance.theme==='light'?'/app-hero-light.png':'/app-hero-dark.png'))}" alt="Current Game Mode background"/></div><div class="background-actions"><button class="quiet" data-action="choose-background">Choose image…</button><button class="quiet" data-action="reset-background" ${appearance.background?'':'disabled'}>Use default</button></div><input type="file" id="background-image-file" accept="image/png,image/jpeg,image/webp" hidden /></div></div></div>`)}${group('Game Details','Uses the color saved in your library for each game.',`<div class="inner-card">${toggle('tint','Accent tint','Tint the Details workspace with that game’s color.',appearance.tint)}${select('details-navigation','Game Details navigation','',['sidebar','tabs'].map(key=>[key,key==='sidebar'?'Sidebar':'Tabs']),appearance.detailsNavigation)}</div>`)}${group('Reading and motion','',`<div class="inner-card">${select('text-size','Text size','',[['standard','Standard'],['large','Large']],appearance.text)}${toggle('motion','Motion','Follows your system’s reduced-motion preference.',appearance.motion)}</div>`)}${group('Layout','',`<div class="inner-card">${select('navigation-position','Navigation placement','Main sections at the top or bottom.',[['top','Top'],['bottom','Bottom']],appearance.navigation)}${scale}</div>`)}${group('Controls','',controlGuide())}${group('Library reader','',`<dl class="reader-facts"><dt>Connection</dt><dd>${loading?'Reading…':snapshot?'Connected · read-only':'Unavailable'}</dd><dt>Platform</dt><dd>${e(snapshot?.platform||'Not reported')}</dd><dt>Steam libraries</dt><dd>${snapshot?.libraryCount??'Not reported'}</dd><dt>Last snapshot</dt><dd>${snapshot?e(new Date(snapshot.capturedAt).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})):'Not reported'}</dd></dl><button class="quiet" data-action="refresh" ${loading?'disabled':''}>${icon('refresh')}Refresh reader</button>${error?`<p class="reader-error">${e(error)}</p>`:''}`)}<div class="appearance-reset"><span class="subtle">Appearance changes are saved automatically.</span><button class="quiet" data-action="reset-appearance">Reset appearance</button></div></div>`;
}
async function chooseBackground(file:File) {
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>24*1024*1024){announce('Choose a PNG, JPEG or WebP image under 24 MB.');return;}
  const source=URL.createObjectURL(file);
  try{
    const image=new Image();image.src=source;await image.decode();
    const scale=Math.min(1,2560/Math.max(image.naturalWidth,image.naturalHeight));
    const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));
    const ctx=canvas.getContext('2d');if(!ctx)throw new Error('Image preview is unavailable.');ctx.drawImage(image,0,0,canvas.width,canvas.height);
    let result='';for(const quality of [.88,.75,.6,.45]){result=canvas.toDataURL('image/webp',quality);if(result.length<1500000)break;}
    if(result.length>=1500000)throw new Error('This image is too detailed to save locally. Choose a smaller image.');
    const next={...appearance,background:result,detailsNavigationVersion:1,appearanceDefaultsVersion:2};
    localStorage.setItem('rtxforge-game-mode-prototype',JSON.stringify(next));appearance.background=result;applyAppearance();render();announce('Game Mode background saved.');
  }catch(problem){announce(problem instanceof Error?problem.message:'This image could not be loaded.');}
  finally{URL.revokeObjectURL(source);}
}
function controlGuide() {
  const [accept,back,previous,next]=controllerLabels();
  const row=(action:string,keys:string)=>`<div><dt>${action}</dt><dd>${keys}</dd></div>`;
  return `<div class="control-guide"><section><h3>${icon('keyboard')}Keyboard</h3><dl>${row('Move','<kbd>Tab</kbd><span>or arrow keys</span>')}${row('Select','<kbd>Enter</kbd>')}${row('Back','<kbd>Esc</kbd>')}${row('Sections','<kbd>[</kbd><kbd>]</kbd>')}</dl></section><section><h3>${icon('controller')}Controller</h3><dl>${row('Move','<span>D-pad or left stick</span>')}${row('Select',`<kbd>${accept}</kbd>`)}${row('Back',`<kbd>${back}</kbd>`)}${row('Sections',`<kbd>${previous}</kbd><kbd>${next}</kbd>`)}</dl></section></div><p class="control-status subtle">${controller?'Controller connected.':'Connect a controller to navigate with a gamepad.'}</p>`;
}
function currentPreferences() { return { ...snapshot?.preferences, ...sharedPreferences, ...preferenceChanges }; }
function sharedSettings() {
  return `${!backend.enabled ? notice('Read-only preview', 'Showing saved settings. Game, Steam and shared preference actions are disabled.') : !sharedPreferences ? '<button class="quiet" data-action="load-settings">Load shared preferences</button>' : ''}${settingsContent({category:settingsCategory,preferences:{...snapshot?.preferences,...sharedPreferences},changes:preferenceChanges,glassDefaults:snapshot?.overlayDefaults||{},enabled:backend.enabled&&Boolean(sharedPreferences),platform:snapshot?.platform,icon,gridConnected,games:snapshot?.games||[],reportSelection:supportSelection,overlayReport:snapshot?.overlayReport,hardware:snapshot?.hardware})}<div class="section-footer"><span>Shared preferences change after review.</span><button class="primary" data-action="save-settings" ${!backend.enabled||!sharedPreferences||!Object.keys(preferenceChanges).length?'disabled':''}>Review preferences</button></div>`;
}
function editGlass(key: string, value: unknown) {
  const current={...snapshot?.overlayDefaults,...currentPreferences().overlay_appearance as Record<string,unknown>};
  current[key]=value;
  if (key==='AccentCharacter') { const x=Math.min(Number(value)/50,1); current.AccentTint=Math.round(20+60*x*x*(3-2*x)); }
  preferenceChanges.overlay_appearance=current;
}
let settingsLayout: ResizeObserver | undefined;
function setupSettingsLayout() {
  settingsLayout?.disconnect();
  const grid=app.querySelector<HTMLElement>('.settings-groups');if(!grid)return;
  const cards=[...grid.querySelectorAll<HTMLElement>(':scope > .setting-group,:scope > .appearance-reset')];
  const arrange=()=>{
    if(!grid.isConnected)return;
    const columns=matchMedia('(min-width:1251px)').matches?2:1;
    for(const card of cards)card.style.gridColumn=card.classList.contains('setting-group-wide')||card.classList.contains('appearance-reset')?'1 / -1':'1';
    const bottoms=Array(columns).fill(0);
    for(const card of cards){
      const wide=card.classList.contains('setting-group-wide')||card.classList.contains('appearance-reset');
      const column=wide?0:bottoms.indexOf(Math.min(...bottoms));
      const top=wide?Math.max(...bottoms):bottoms[column];
      card.style.gridColumn=wide?'1 / -1':String(column+1);
      const height=Math.ceil(card.getBoundingClientRect().height);
      card.style.gridRow=`${top+1} / span ${height}`;
      if(wide)bottoms.fill(top+height+24);else bottoms[column]=top+height+24;
    }
  };
  arrange();settingsLayout=new ResizeObserver(arrange);settingsLayout.observe(grid);
  for(const card of cards)settingsLayout.observe(card);
}
let scrollFades:ResizeObserver|undefined;
function setupScrollFades() {
  scrollFades?.disconnect();scrollFades=new ResizeObserver(entries=>{for(const entry of entries){const scroller=(entry.target as HTMLElement).closest<HTMLElement>('.details-scroll,.detail-nav,.flow-body');if(scroller)update(scroller);}});
  function update(node:HTMLElement){
    const distance=Math.min(56,node.clientHeight*.12),top=Math.min(distance,Math.max(0,node.scrollTop)),bottom=Math.min(distance,Math.max(0,node.scrollHeight-node.clientHeight-node.scrollTop));
    node.style.setProperty('--fade-top',top+'px');node.style.setProperty('--fade-bottom',bottom+'px');
  }
  for(const node of app.querySelectorAll<HTMLElement>('.details-scroll,.details-layout>.detail-nav,.flow-body')) {
    node.classList.add('scroll-fade');node.addEventListener('scroll',()=>update(node),{passive:true});scrollFades.observe(node);if(node.firstElementChild)scrollFades.observe(node.firstElementChild);if(node.lastElementChild)scrollFades.observe(node.lastElementChild);update(node);
  }
}
let arrivalKey = '';
function render() {
  const priorFocus = document.activeElement instanceof HTMLElement && app.contains(document.activeElement) ? document.activeElement : null;
  const focusKey = priorFocus ? (priorFocus.id ? `#${CSS.escape(priorFocus.id)}` : [...priorFocus.attributes].filter(a=>a.name.startsWith('data-')).map(a=>`[${a.name}="${CSS.escape(a.value)}"]`).join('')) : null;
  const nextArrival = `${view}:${view==='details'?selectedGame()?.id+':'+detailsSection:view==='settings'?settingsCategory:view==='operation'?operation?.stage:''}`;
  const arrival = nextArrival !== arrivalKey ? captureArrival(app) : null;
  closeSelectMenu(false);
  const sameSurface = renderedView === view && (view !== 'details' || renderedGame === selectedGame()?.id);
  const contentScroll = sameSurface ? app.querySelector<HTMLElement>('#content')?.scrollTop || 0 : 0;
  const detailsScroll = sameSurface ? app.querySelector<HTMLElement>('.details-scroll')?.scrollTop || 0 : 0;
  applyAppearance();
  document.documentElement.dataset.surface = view;
  const content = view === 'library' ? library() : view === 'presets' ? presets() : view === 'details' ? details() : view === 'packages' ? packages() : view === 'extras' ? extras() : view === 'operation' ? operationView() : settings();
  app.innerHTML = `<div class="shell"><header class="app-header"><a href="#library" class="brand" data-route="library" aria-label="rtxForge library"><img src="/logo-mark.png" alt="" /><span>rtxForge</span></a><nav class="glass main-nav" aria-label="Main navigation">${tabs.map(tab => `<button data-route="${tab.id}" ${view === tab.id || view === 'details' && tab.id === 'library' ? 'aria-current="page"' : ''}>${icon(tab.icon)}<span>${tab.label}</span></button>`).join('')}</nav><div class="shell-more"><button class="menu-button" id="shell-menu-button" data-action="shell-menu" aria-label="More options" aria-haspopup="menu" aria-expanded="${shellMenuOpen}">${icon('dots')}</button><div class="shell-menu glass-section" id="shell-menu" role="menu" ${shellMenuOpen ? '' : 'hidden'}><button role="menuitem" data-route="library">${icon('books')}Library</button><button role="menuitem" data-action="menu-appearance">${icon('palette')}Appearance</button><button role="menuitem" data-action="refresh">${icon('refresh')}Refresh library</button><button role="menuitem" data-action="menu-library">${icon('folder')}Library options</button><button role="menuitem" data-action="menu-controls">${icon('controller')}Controls</button><div class="menu-divider"></div><button role="menuitem" data-action="desktop-mode" ${!('__TAURI_INTERNALS__' in window)?'disabled':''}>${icon('grid')}Desktop mode</button><button role="menuitem" data-action="exit-app" ${!('__TAURI_INTERNALS__' in window)?'disabled':''}>${icon('arrow')}Exit rtxForge</button><span class="menu-preview">${backend.enabled?'Engine connected':'Read-only preview'}</span></div></div></header><main id="content" class="content glass" aria-label="${view === 'details' ? 'Game details' : tabs.find(tab => tab.id === view)?.label}">${content}</main><footer class="app-footer"><span>${icon('eye')}<span>Read-only preview</span></span><div id="input-hints">${hints()}</div><span class="reader-state"><i class="${snapshot ? 'connected' : ''}"></i>${loading ? 'Reading library' : snapshot ? 'Local library loaded' : 'Reader unavailable'}</span></footer></div>`;
  const game = selectedGame(), scene = document.querySelector<HTMLElement>('#scene')!;
  scene.style.backgroundImage = '';
  scene.dataset.hero = 'false';
  applyDetailsAccent();
  applyOperationAccent();
  bind();
  setupHero();
  setupSettingsLayout();
  enhanceSelects(app);
  bindArtworkFailures(app);
  setupScrollFades();
  const main = app.querySelector<HTMLElement>('#content'); if(main)main.scrollTop=contentScroll;
  const scrollingDetails=app.querySelector<HTMLElement>('.details-scroll'); if(scrollingDetails) { scrollingDetails.scrollTop=detailsScroll; scrollingDetails.dispatchEvent(new Event('scroll')); }
  renderedView=view;renderedGame=selectedGame()?.id||'';
  if (arrival) arrive(app, arrival, view);
  arrivalKey = nextArrival;
  showHints();
}
function controllerLabels() {
  let family = String(preferenceChanges.controller_glyphs ?? sharedPreferences?.controller_glyphs ?? snapshot?.defaults.controller_glyphs ?? 'auto');
  if (family === 'auto') family = /dual|sony|playstation/i.test(controllerId) ? 'playstation' : /nintendo|switch/i.test(controllerId) ? 'nintendo' : /steam/i.test(controllerId) ? 'steam' : 'xbox';
  const labels = ({ xbox: ['A', 'B', 'LB', 'RB'], playstation: ['Cross', 'Circle', 'L1', 'R1'], nintendo: ['B', 'A', 'L', 'R'], steam: ['A', 'B', 'L1', 'R1'], generic: ['South', 'East', 'L', 'R'] } as Record<string, string[]>)[family] || ['A', 'B', 'LB', 'RB'];
  return labels;
}
function hints() {
  const labels=controllerLabels();
  return controller ? `<span><kbd>${labels[0]}</kbd> Select</span><span><kbd>${labels[1]}</kbd> Back</span><span><kbd>${labels[2]}</kbd><kbd>${labels[3]}</kbd> Sections</span>` : '<span><kbd>Enter</kbd> Select</span><span><kbd>Esc</kbd> Back</span><span><kbd>Tab</kbd> Navigate</span>';
}
function enhanceActionLabels() {
  const selector='.operation-actions button,.library-operation-actions button,.selection-bar button,.page-heading>button,.shortcut-actions button,button.extra-actions,.detail-nav button,.app-header nav button,.settings-tabs button';
  for(const button of app.querySelectorAll<HTMLButtonElement>(selector)) {
    button.classList.add('accent-label-control');if(button.closest('nav'))button.classList.add('accent-nav-control');
    for(const child of [...button.childNodes]) {
      if(child.nodeType===Node.TEXT_NODE&&child.textContent?.trim()) {
        const label=document.createElement('span');label.className='control-label';label.textContent=child.textContent;child.replaceWith(label);
      }else if(child instanceof HTMLSpanElement&&!child.classList.contains('icon'))child.classList.add('control-label');
    }
  }
}
function bind() {
  enhanceActionLabels();
  app.querySelectorAll<HTMLElement>('button,input,select,textarea,summary,a[href]').forEach(node=>node.classList.add('ui-control'));
  app.querySelectorAll<HTMLElement>('[data-preset-control]').forEach(node=>node.dataset.presetKey='control-'+node.dataset.presetControl);
  app.querySelectorAll<HTMLSelectElement|HTMLInputElement>('[data-startup-control]').forEach(node=>node.addEventListener('change',()=>{if(!pendingInstall)return;const key=node.dataset.startupControl!;const controls={...pendingInstall.settings.feature_controls as Record<string,unknown>,[key]:Number(node.value)};pendingInstall.settings.feature_controls=controls;if(key==='intensity')pendingInstall.settings.nr_strength=Number(node.value);if(key==='sharpness')pendingInstall.settings.sharpening_strength=Number(node.value);if(key==='enabled')pendingInstall.settings.nr_on_launch=Number(node.value)!==0;}));
  app.querySelectorAll<HTMLElement>('[data-startup-mode]').forEach(node=>node.addEventListener('click',()=>{if(!pendingInstall)return;const mode=Number(node.dataset.startupMode),values=pendingInstall.settings;values.mfg_saved_mode=mode;values.mfg_multiplier=mode===0?'auto':values.mfg_saved_multiplier||2;values.dynamic_mfg=mode===2?1:0;render();app.querySelector<HTMLElement>(`[data-startup-mode="${mode}"]`)?.focus();}));
  app.querySelectorAll<HTMLElement>('[data-startup-ratio]').forEach(node=>node.addEventListener('click',()=>{if(!pendingInstall)return;const ratio=Number(node.dataset.startupRatio);pendingInstall.settings.mfg_saved_multiplier=ratio;pendingInstall.settings.mfg_multiplier=ratio;render();app.querySelector<HTMLElement>(`[data-startup-ratio="${ratio}"]`)?.focus();}));
  app.querySelector<HTMLSelectElement>('#startup-mfg-enabled')?.addEventListener('change',event=>{if(!pendingInstall)return;const values=pendingInstall.settings;values.mfg_multiplier=(event.target as HTMLSelectElement).value==='false'?0:values.mfg_saved_mode===0?'auto':values.mfg_saved_multiplier||2;render();app.querySelector<HTMLElement>('#startup-mfg-enabled')?.focus();});
  app.querySelector<HTMLInputElement>('#background-image-file')?.addEventListener('change',event=>{const file=(event.target as HTMLInputElement).files?.[0];if(file)void chooseBackground(file);});
  app.querySelectorAll<HTMLElement>('[data-tool-kind]').forEach(node=>node.addEventListener('click',()=>{ extraKind=node.dataset.toolKind!; extraSource=''; toolImportOpen=true; render(); app.querySelector<HTMLInputElement>('#extra-source')?.focus(); }));
  app.querySelector<HTMLSelectElement>('#test-result')?.addEventListener('change',event=>{ const game=selectedGame(); if(game) void engineRequest('notes_save',{game:game.path,status:(event.target as HTMLSelectElement).value,notes:noteDrafts.get(game.id)??game.notes??''}).then(()=>announce('Test result saved.')).catch(problem=>announce(problem.message)); });
  app.querySelector<HTMLInputElement>('#game-accent-color')?.addEventListener('input',event=>{ const game=selectedGame(); if(game)gameAccentDrafts.set(game.id,(event.target as HTMLInputElement).value); applyDetailsAccent(); });
  app.querySelectorAll<HTMLInputElement|HTMLSelectElement|HTMLButtonElement>('[data-preset-key]').forEach(node => node.addEventListener(node instanceof HTMLButtonElement ? 'click' : 'change',()=>{ drafts.set(presetId,{...drafts.get(presetId),[node.dataset.presetKey!]:node.dataset.presetValue ?? node.value}); render(); app.querySelector<HTMLElement>(`[data-preset-key="${node.dataset.presetKey}"]${node.dataset.presetValue ? `[data-preset-value="${node.dataset.presetValue}"]` : ''}`)?.focus(); }));
  app.querySelectorAll<HTMLElement>('[data-route]').forEach(node => node.addEventListener('click', event => { event.preventDefault(); setView(node.dataset.route as View); }));
  app.querySelectorAll<HTMLElement>('[data-game]').forEach(node => node.addEventListener('click', () => { selectedId = node.dataset.game!; detailsSection='overview'; extraRecords=[];extraSource='';toolImportOpen=false; setView('details'); }));
  app.querySelectorAll<HTMLButtonElement>('[data-layout]').forEach(node => node.addEventListener('click', () => { libraryView = node.dataset.layout!; render(); app.querySelector<HTMLElement>(`[data-layout="${libraryView}"]`)?.focus(); }));
  app.querySelectorAll<HTMLElement>('[data-library-mode]').forEach(node=>node.addEventListener('click',()=>{libraryMode=node.dataset.libraryMode;const group=node.closest<HTMLElement>('.feature-mode-segments')!;group.style.setProperty('--selected-mode',String(['nr-only','mfg-only','nr-mfg'].indexOf(libraryMode!)));group.querySelectorAll<HTMLElement>('button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.libraryMode===libraryMode)));}));
  app.querySelector<HTMLSelectElement>('#library-filter')?.addEventListener('change',event=>void filterLibrary((event.target as HTMLSelectElement).value));
  app.querySelector<HTMLInputElement>('#library-search')?.addEventListener('input', event => { query = (event.target as HTMLInputElement).value; app.querySelector('#game-results')!.innerHTML = gameResults(filteredLibrary(), snapshot?.games.length || 0); bindResults(); });
  app.querySelectorAll<HTMLElement>('[data-number-step]').forEach(node=>node.addEventListener('click',()=>{const field=node.parentElement?.querySelector<HTMLInputElement>('input[type=number]');if(!field||field.disabled)return; if(node.dataset.numberStep==='1')field.stepUp();else field.stepDown();field.dispatchEvent(new Event('change',{bubbles:true}));}));
  app.querySelectorAll<HTMLElement>('[data-action]').forEach(node => node.addEventListener('click', () => action(node.dataset.action!)));
  app.querySelectorAll<HTMLElement>('[data-theme-choice]').forEach(node => node.addEventListener('click', () => { appearance.theme = node.dataset.themeChoice as Appearance['theme']; applyAppearance(); render(); app.querySelector<HTMLElement>(`[data-theme-choice="${appearance.theme}"]`)?.focus(); }));
  app.querySelectorAll<HTMLElement>('[data-toggle]').forEach(node => node.addEventListener('click', () => { const key = node.dataset.toggle as 'motion' | 'tint'; appearance[key] = !appearance[key]; applyAppearance(); node.setAttribute('aria-checked', String(appearance[key])); }));
  app.querySelector<HTMLInputElement>('#accent-color')?.addEventListener('input', event => { appearance.accent = (event.target as HTMLInputElement).value; applyAppearance(); });
  app.querySelector<HTMLSelectElement>('#text-size')?.addEventListener('change', event => { appearance.text = (event.target as HTMLSelectElement).value as Appearance['text']; applyAppearance(); });
  app.querySelector<HTMLSelectElement>('#details-navigation')?.addEventListener('change',event=>{appearance.detailsNavigation=(event.target as HTMLSelectElement).value as Appearance['detailsNavigation'];applyAppearance();});
  app.querySelector<HTMLSelectElement>('#navigation-position')?.addEventListener('change', event => { appearance.navigation = (event.target as HTMLSelectElement).value as Appearance['navigation']; applyAppearance(); });
  app.querySelector<HTMLSelectElement>('#display-scale')?.addEventListener('change', event => { const value = (event.target as HTMLSelectElement).value; appearance.scale = value === 'auto' ? 'auto' : Number(value); applyAppearance(); });
  app.querySelectorAll<HTMLSelectElement | HTMLInputElement>('[data-draft]').forEach(node => node.addEventListener('change', () => { const game = selectedGame(); if (!game) return; drafts.set(game.id, { ...drafts.get(game.id), [node.dataset.draft!]: node.value }); app.querySelector('#draft-label')!.textContent = 'Draft · not applied'; if (['mfg_mode', 'mfg_enabled', 'provider'].includes(node.dataset.draft!)) { render(); app.querySelector<HTMLElement>(`[data-draft="${node.dataset.draft}"]`)?.focus(); } announce('Preview choice changed. Nothing applied.'); }));
  app.querySelectorAll<HTMLElement>('[data-extra]').forEach(node => node.addEventListener('click', () => { extraKind = node.dataset.extra!; render(); app.querySelector<HTMLElement>(`[data-extra="${extraKind}"]`)?.focus(); }));
  app.querySelectorAll<HTMLElement>('[data-detail-section]').forEach(node => node.addEventListener('click', () => { detailsSection = node.dataset.detailSection!; render(); app.querySelector<HTMLElement>(`[data-detail-section="${detailsSection}"]`)?.focus(); const game = selectedGame(); if (detailsSection === 'notes' && backend.enabled && game && !notesLoaded.has(game.id)) void engineRequest<Record<string, unknown>>('notes_get', { game: game.path }).then(record => { if (!noteDrafts.has(game.id)) noteDrafts.set(game.id, String(record.notes || '')); notesLoaded.add(game.id); if (view === 'details' && detailsSection === 'notes' && selectedId === game.id) render(); }).catch(problem => announce(problem.message)); }));
  app.querySelectorAll<HTMLElement>('[data-operation]').forEach(node => node.addEventListener('click', () => void runOperation(node.dataset.operation!, node.dataset.batch === 'true', node.dataset.libraryScope === 'true')));
  app.querySelectorAll<HTMLElement>('[data-contract]').forEach(node => node.addEventListener('click', async () => {
    const game = selectedGame(); if (!game) return;
    try { const rows = await getEngineRows(); const row = rows.find(row => pathKey(row.game) === pathKey(game.path)); if (!row) throw new Error('This installation is unavailable to the engine.'); await withOperation(node.textContent?.trim() || 'Review', node.dataset.contract!, { ...(node.dataset.contract === 'report_draft' ? { rows: [row] } : { row }), ...(node.dataset.remove ? { remove: true } : {}) }, node.dataset.contract === 'report_draft' ? 'report-draft' : ['diagnose','dlss_inventory'].includes(node.dataset.contract!) ? 'inspect' : 'run'); }
    catch (problem) { announce(problem instanceof Error ? problem.message : 'The engine is unavailable.'); }
  }));
  app.querySelector<HTMLInputElement>('#review-trust')?.addEventListener('change', syncReviewConfirm);
  app.querySelectorAll<HTMLInputElement>('[data-supported-token]').forEach(field => field.addEventListener('change', syncReviewConfirm));
  app.querySelectorAll<HTMLElement>('[data-settings-category]').forEach(node => node.addEventListener('click', () => { settingsCategory = node.dataset.settingsCategory!; render(); app.querySelector<HTMLElement>(`[data-settings-category="${settingsCategory}"]`)?.focus(); }));
  app.querySelectorAll<HTMLSelectElement>('[data-preference]').forEach(node => node.addEventListener('change', () => { preferenceChanges[node.dataset.preference!] = JSON.parse(node.value); render(); app.querySelector<HTMLElement>(`[data-preference="${node.dataset.preference}"]`)?.focus(); announce('Preference changed in draft. Review to save it.'); }));
  app.querySelectorAll<HTMLElement>('[data-preference-toggle]').forEach(node=>node.addEventListener('click',()=>{ const key=node.dataset.preferenceToggle!; preferenceChanges[key]=!currentPreferences()[key];render();app.querySelector<HTMLElement>(`[data-preference-toggle="${key}"]`)?.focus(); }));
  app.querySelectorAll<HTMLSelectElement>('[data-glass]').forEach(node=>node.addEventListener('change',()=>{editGlass(node.dataset.glass!,JSON.parse(node.value));render();app.querySelector<HTMLElement>(`[data-glass="${node.dataset.glass}"]`)?.focus();}));
  app.querySelectorAll<HTMLInputElement>('[data-glass-range]').forEach(node=>node.addEventListener('input',()=>{editGlass(node.dataset.glassRange!,Number(node.value));const save=app.querySelector<HTMLButtonElement>('[data-action="save-settings"]');if(save)save.disabled=false;}));
  app.querySelectorAll<HTMLElement>('[data-overlay-layout]').forEach(node=>node.addEventListener('click',()=>{editGlass('Layout',node.dataset.overlayLayout);render();app.querySelector<HTMLElement>(`[data-overlay-layout="${node.dataset.overlayLayout}"]`)?.focus();}));
  app.querySelectorAll<HTMLElement>('[data-overlay-theme]').forEach(node=>node.addEventListener('click',()=>{
    const theme=node.dataset.overlayTheme!, defaults=snapshot?.overlayThemes?.[theme];if(!defaults)return;
    const keys=['Theme','Custom','LightTint','DarkTint','ClearTint','AccentTint','Blur','Grain','BlendStrength','SurfaceBlend','InvertDark','TextDepth','AccentCharacter'];
    preferenceChanges.overlay_theme=theme;for(const key of keys)editGlass(key,defaults[key]);
    render();app.querySelector<HTMLElement>(`[data-overlay-theme="${theme}"]`)?.focus();
  }));
  app.querySelectorAll<HTMLInputElement>('[data-support-game]').forEach(node=>node.addEventListener('change',()=>{if(node.checked)supportSelection.add(node.dataset.supportGame!);else supportSelection.delete(node.dataset.supportGame!);const button=app.querySelector<HTMLButtonElement>('[data-action="support-report"]');if(button)button.disabled=!supportSelection.size||!backend.enabled;}));
  app.querySelectorAll<HTMLElement>('[data-show-game]').forEach(node=>node.addEventListener('click',()=>{const removed=(currentPreferences().removed_games||[]) as string[];void withOperation('Show removed game','settings_review',{changes:{removed_games:removed.filter(path=>pathKey(path)!==pathKey(node.dataset.showGame!))}});}));
  app.querySelectorAll<HTMLElement>('[data-steam-profile]').forEach(node=>node.addEventListener('click',()=>{ const profile=(operation?.result as Record<string,unknown>[])[Number(node.dataset.steamProfile)];if(profile)void withOperation('Review Steam artwork profile','settings_review',{changes:{steam_artwork_profile:{root:profile.root,userid:profile.userid}}}); }));
  app.querySelectorAll<HTMLElement>('[data-recovery]').forEach(node => node.addEventListener('click', () => { const row = (operation?.result as Record<string, unknown>[])?.[Number(node.dataset.recovery)]; if (row) void withOperation('Review recovery', 'recovery_review', { row, record: row }); }));
  app.querySelector<HTMLInputElement>('#extra-source')?.addEventListener('input', event => { extraSource = (event.target as HTMLInputElement).value; });
  app.querySelector<HTMLInputElement>('#package-source')?.addEventListener('input', event => { packageSource = (event.target as HTMLInputElement).value; });
  app.querySelector<HTMLSelectElement>('#extra-game')?.addEventListener('change', event => { selectedId = (event.target as HTMLSelectElement).value; extraRecords = []; });
  app.querySelectorAll<HTMLElement>('[data-extra-restore]').forEach(node => node.addEventListener('click', () => { const record = extraRecords[Number(node.dataset.extraRestore)]; if (record) void withOperation('Review tool restore', 'extra_restore_review', { path: record.path }); }));
  app.querySelector<HTMLInputElement>('#package-trust')?.addEventListener('change', event => { const button = app.querySelector<HTMLButtonElement>('[data-action="use-package"]'); if (button) button.disabled = !(event.target as HTMLInputElement).checked; });
  app.querySelector<HTMLTextAreaElement>('#game-notes')?.addEventListener('input', event => { const game = selectedGame(); if (game) noteDrafts.set(game.id, (event.target as HTMLTextAreaElement).value); });
  app.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-report-field]').forEach(node => node.addEventListener('change', () => { reportEdits[node.dataset.reportId!] = { ...reportEdits[node.dataset.reportId!], [node.dataset.reportField!]: node.value }; }));
  app.querySelectorAll<HTMLSelectElement>('[data-game-overlay]').forEach(node => node.addEventListener('change', () => { const game = selectedGame(); if (game) gameOverlayDrafts.set(game.id, { ...gameOverlayDrafts.get(game.id), [node.dataset.gameOverlay!]: JSON.parse(node.value) }); announce('Per-game overlay choice changed in draft.'); }));
  app.querySelector<HTMLSelectElement>('#artwork-role')?.addEventListener('change', event => { artworkRole = (event.target as HTMLSelectElement).value; artworkAssets = []; });
  app.querySelector<HTMLInputElement>('#artwork-source')?.addEventListener('input', event => { artworkPath = (event.target as HTMLInputElement).value; });
  app.querySelector<HTMLInputElement>('#artwork-query')?.addEventListener('input', event => { artworkQuery = (event.target as HTMLInputElement).value; });
  app.querySelectorAll<HTMLElement>('[data-artwork-game]').forEach(node => node.addEventListener('click', () => void engineRequest<Record<string, unknown>[]>('sgdb_artwork', { game_id: Number(node.dataset.artworkGame), role: artworkRole, mime: 'image/png' }).then(assets => { artworkAssets = assets; render(); }).catch(problem => announce(problem.message))));
  app.querySelectorAll<HTMLElement>('[data-artwork-asset]').forEach(node => node.addEventListener('click', () => void chooseArtworkAsset(Number(node.dataset.artworkAsset))));
  app.querySelector<HTMLInputElement>('#panel-shortcut')?.addEventListener('keydown', event => {
    if (event.key === 'Tab') return;
    if (event.key === 'Escape') { event.stopPropagation(); (event.target as HTMLInputElement).blur(); return; }
    event.preventDefault(); event.stopPropagation();
    if (['Control', 'Alt', 'Shift', 'Meta'].includes(event.key)) return;
    const key = event.key.length === 1 ? event.key.toUpperCase() : event.key;
    const value = [event.ctrlKey ? 'Ctrl' : '', event.altKey ? 'Alt' : '', event.shiftKey ? 'Shift' : '', key].filter(Boolean).join('+');
    (event.target as HTMLInputElement).value = value; preferenceChanges.panel_hotkey = value;
  });
  app.querySelectorAll<HTMLElement>('[data-provider-default]').forEach(node => node.addEventListener('click', () => void withOperation('Review default package', 'settings_review', { changes: { runtime_provider: node.dataset.providerDefault } })));
  app.querySelectorAll<HTMLElement>('[data-mfg-default]').forEach(node => node.addEventListener('click', () => void withOperation('Review MFG package', 'settings_review', { changes: { mfg_provider: node.dataset.mfgDefault } })));
  if ('__TAURI_INTERNALS__' in window) {
    for (const [id, kind] of [['package-source', 'package'], ['extra-source', ['hdr-custom','addon'].includes(extraKind) ? 'addon' : 'tool'], ['executable-source', 'executable'], ['artwork-source', 'image']]) {
      const field = app.querySelector<HTMLInputElement>('#' + id);
      if (!field) continue;
      const browse = document.createElement('button'); browse.className = 'quiet'; browse.textContent = 'Browse…'; browse.type = 'button'; browse.disabled = !backend.enabled;
      browse.addEventListener('click', async event => { event.preventDefault(); const result = await (await import('@tauri-apps/api/core')).invoke<string | null>('choose_path', { kind }); if (result) { field.value = result; field.dispatchEvent(new Event('input')); } });
      field.parentElement?.append(browse);
    }
  }
  if (!backend.enabled) app.querySelectorAll<HTMLInputElement>('#package-source,#extra-source,#executable-source').forEach(field => { field.disabled = true; });
  bindSelections();
}
function bindResults() {
  app.querySelectorAll<HTMLElement>('#game-results [data-game]').forEach(node => node.addEventListener('click', () => { selectedId = node.dataset.game!; detailsSection='overview'; extraRecords=[];extraSource='';toolImportOpen=false; setView('details'); }));
  app.querySelectorAll<HTMLElement>('#game-results [data-action]').forEach(node => node.addEventListener('click', () => action(node.dataset.action!)));
  bindSelections();
}
function bindSelections() {
  app.querySelectorAll<HTMLElement>('[data-select-game]').forEach(node => node.addEventListener('click', () => { const id = node.dataset.selectGame!; if (batchSelection.has(id)) batchSelection.delete(id); else batchSelection.add(id); render(); app.querySelector<HTMLElement>(`[data-select-game="${CSS.escape(id)}"]`)?.focus(); }));
}
function action(name: string) {
  if (name === 'reset-game-accent') { const game=selectedGame(); if(game)gameAccentDrafts.delete(game.id); render(); return; }
  if (name === 'reset-presets') { drafts.delete(presetId); render(); return; }
  if (name === 'select-preset-games') { presetSelection=true; batchSelection.clear(); setView('library'); announce('Select configured games, then review their preset changes.'); return; }
  if (name === 'end-preset-selection') { presetSelection=false; batchSelection.clear(); setView('presets'); return; }
  if (name === 'apply-presets' || name === 'apply-selected-presets') { void applyPresets(name === 'apply-selected-presets'); return; }
  if(name==='choose-background'){app.querySelector<HTMLInputElement>('#background-image-file')?.click();return;}
  if(name==='reset-background'){delete appearance.background;applyAppearance();render();return;}
  if(name==='desktop-mode'||name==='exit-app'){
    if(operation?.stage==='running'){announce('Wait for the operation to finish or request cancellation first.');return;}
    if('__TAURI_INTERNALS__' in window)void import('@tauri-apps/api/core').then(({invoke})=>invoke(name==='desktop-mode'?'desktop_mode':'exit_app')).catch(problem=>announce(String(problem)));
    return;
  }
  if (name === 'shell-menu') { shellMenuOpen = !shellMenuOpen; const menu = app.querySelector<HTMLElement>('#shell-menu'); if (menu) menu.hidden = !shellMenuOpen; app.querySelector('#shell-menu-button')?.setAttribute('aria-expanded', String(shellMenuOpen)); if (shellMenuOpen) menu?.querySelector<HTMLElement>('button')?.focus(); return; }
  if (name === 'menu-appearance' || name === 'menu-controls' || name === 'menu-library') { shellMenuOpen=false; settingsCategory=name==='menu-appearance'?'appearance':name==='menu-library'?'library':'gaming'; setView('settings'); return; }
  if (name === 'extras-hdr') { detailsSection='tools'; setView('details'); return; }
  if (name === 'extras-dlss') { void runOperation('update-dlss', true); return; }
  if (name === 'refresh') void refresh();
  if (name === 'clear-search') { query = ''; render(); app.querySelector<HTMLInputElement>('#library-search')?.focus(); }
  if (name === 'clear-selection') { batchSelection.clear(); render(); }
  if (name === 'reset-draft') { const game = selectedGame(); if (game) drafts.delete(game.id); render(); app.querySelector<HTMLElement>('[data-action="reset-draft"]')?.focus(); announce('Preview choices reset.'); }
  if (name === 'reset-appearance') { appearance = { ...appearanceDefaults }; applyAppearance(); render(); app.querySelector<HTMLElement>('[data-action="reset-appearance"]')?.focus(); announce('Appearance reset to Clear.'); }
  if (name === 'scan-engine') void getEngineRows().then(() => { render(); announce('Compatibility check completed.'); }).catch(problem => announce(problem.message));
  if(name==='startup-review'&&pendingInstall){void withOperation('Review Installation','prepare_routes',pendingInstall.params,'execute_routes');return;}
  if (name === 'operation-back') { const origin = operation?.origin || 'details'; operation = null; pendingInstall=null; setView(origin); }
  if (name === 'discard-review') void discardReview();
  if (name === 'cancel-operation' && operation?.review){const state=operation;state.cancelRequested=true;render();void engineRequest(state.execute==='execute_routes'?'cancel_routes':'cancel',{token:state.review!.token}).then(()=>announce('Cancellation requested. The engine will stop at a safe boundary.')).catch(problem=>{state.cancelRequested=false;render();announce(String(problem));});}
  if (name === 'confirm-operation') void confirmOperation();
  if (name === 'launch') { const game = selectedGame(); if (game?.appid) void engineRequest('launch_game', { appid: game.appid }).then(() => announce('Launch request sent to Steam.')).catch(problem => announce(problem.message)); }
  if (name === 'add-game-folder' || name === 'add-library-folder') void addLibraryFolder(name==='add-library-folder');
  if (name === 'remove-selected-entries') {const removed=[...((currentPreferences().removed_games||[]) as string[])];for(const game of snapshot?.games||[])if(batchSelection.has(game.id)&&!removed.some(path=>pathKey(path)===pathKey(game.path)))removed.push(game.path);void withOperation('Hide selected library entries','settings_review',{changes:{removed_games:removed}});}
  if(name==='game-menu'){detailsMenuOpen=!detailsMenuOpen;render();app.querySelector<HTMLElement>('[data-action="game-menu"]')?.focus();return;}
  if(name==='remove-current-entry'){const game=selectedGame();if(game){const removed=[...((currentPreferences().removed_games||[]) as string[]),game.path];void withOperation('Hide this library entry','settings_review',{changes:{removed_games:[...new Set(removed)]}});}}
  if(name==='open-game-folder'){void getEngineRows().then(rows=>{const row=rows.find(row=>pathKey(row.game)===pathKey(selectedGame()!.path));if(!row)throw new Error('This game folder is not available.');return engineRequest('open_game_folder',{row});}).catch(problem=>announce(problem.message));}
  if (name === 'load-settings') void loadPreferences();
  if (name === 'save-settings') void withOperation('Review preferences', 'settings_review', { changes: preferenceChanges });
  if (name === 'hardware') void withOperation('System information', 'hardware', {}, 'inspect');
  if (name === 'recoveries') void withOperation('Recovery records', 'recoveries', {}, 'recoveries');
  if (name === 'cleanup-review') void withOperation('Remove old NR files','cleanup_review',{});
  if (name === 'steam-status') void withOperation('Steam shortcut', 'steam_status', {}, 'inspect');
  if (name === 'steam-review') void reviewSteam();
  if (name === 'steam-remove-review') void reviewSteam(true);
  if (name === 'steam-art-profiles') void withOperation('Steam artwork profile','art_profiles',{},'art-profiles');
  if (name === 'library-art-refresh') void withOperation('Refresh artwork','media',{rows:(snapshot?.games||[]).map(game=>({game:game.path,name:game.name,appid:game.appid,source:game.source})),refresh:true},'inspect');
  if (name === 'library-art-sync') void withOperation('Review library artwork sync','art_sync_review',{rows:(snapshot?.games||[]).map(game=>({game:game.path,name:game.name,appid:game.appid,source:game.source}))});
  if (name === 'support-report') void (async()=>{try{const rows:EngineRow[]=[];for(const game of snapshot?.games||[])if(supportSelection.has(game.id))rows.push(...await getEngineRows(game));if(!rows.length)throw new Error('Choose at least one available game.');await withOperation('Prepare bug report','report_draft',{rows},'report-draft');}catch(problem){announce(problem instanceof Error?problem.message:'The report could not be prepared.');}})();
  if (name === 'reset-panel-shortcut' || name === 'disable-panel-shortcut') { const value=name==='disable-panel-shortcut'?'Disabled':snapshot?.preferenceDefaults?.panel_hotkey;if(typeof value==='string'){preferenceChanges.panel_hotkey=value;render();} }
  if (name === 'inspect-package') void withOperation('Inspect local package', 'package_inspect', { path: packageSource }, 'inspect-package');
  if (name === 'use-package') { const result = operation?.result as Record<string, unknown>; if (result?.token && app.querySelector<HTMLInputElement>('#package-trust')?.checked) void withOperation('Choose package', 'package_use', { token: result.token, trusted: true }, 'inspect'); }
  if (name === 'copy-game-path') { const game=selectedGame(); if(game&&backend.enabled)void navigator.clipboard.writeText(game.path).then(()=>announce('Location copied.')).catch(()=>announce('Clipboard unavailable.')); }
  if (name === 'official-reshade') { extraKind='reshade'; extraSource=''; void extraAction('review-extra'); }
  if (name === 'review-extra' || name === 'extra-records') void extraAction(name);
  if (name === 'save-notes') { const game = selectedGame(); if (game) void engineRequest('notes_save', { game: game.path, notes: noteDrafts.get(game.id) || '' }).then(() => announce('Game notes saved.')).catch(problem => announce(problem.message)); }
  if (name === 'review-report') { const draft = operation?.result as ReportDraft; if (draft?.reports) void withOperation('Review bug report', 'report_preview', { ids: draft.reports.map(report => report.id), edits: reportEdits, logs: app.querySelector<HTMLInputElement>('#report-logs')?.checked, notes: app.querySelector<HTMLInputElement>('#report-notes')?.checked }); }
  if (name === 'global-review') { const nr = app.querySelector<HTMLSelectElement>('#global-nr')?.value, mfg = app.querySelector<HTMLSelectElement>('#global-mfg')?.value; void withOperation('Review bulk graphics changes', 'global_review', { ...(nr === 'keep' ? {} : { nr: nr === 'true' }), ...(mfg === 'keep' ? {} : { mfg: Number(mfg) }) }); }
  if (name === 'overlay-menu-review') { const values = { ...sharedPreferences, ...preferenceChanges }; void withOperation('Review game menus', 'overlay_ui_review', Object.fromEntries(['optiscaler_ui', 'optiscaler_intro', 'reshade_ui', 'reshade_intro', 'optiscaler_hotkey'].map(key => [key, values[key]]))); }
  if (name === 'overlay-package-review') void withOperation('Review overlay packages', 'overlay_package_review', { ...sharedPreferences, ...preferenceChanges });
  if (name === 'storage-inventory') void withOperation('App storage', 'storage_inventory', {}, 'inspect');
  if (name === 'storage-review') void withOperation('Review download cleanup', 'storage_review', {});
  if (name === 'update-check') void withOperation('Check app update', 'update_check', {});
  if (name === 'check-packages') void engineRequest<{catalog: typeof liveCatalog}>('packages').then(result => { liveCatalog = result.catalog; render(); announce('Engine package availability loaded.'); }).catch(problem => announce(problem.message));
  if (name === 'feeder-status') void withOperation('Managed Feeder files', 'feeder_storage', {}, 'inspect');
  if (name === 'feeder-legacy') void withOperation('Get managed DirectX support', 'feeder_storage', { legacy: true }, 'inspect');
  if (name === 'executable-review' || name === 'executable-reset') { const path = name === 'executable-reset' ? null : app.querySelector<HTMLInputElement>('#executable-source')?.value; void getEngineRows().then(rows => { if (!rows[0]) throw new Error('This game could not be inspected.'); return withOperation('Review game executable', 'executable_review', { row: rows[0], path }); }).catch(problem => announce(problem.message)); }
  if (['save-game-overlay', 'inherit-game-overlay', 'apply-game-overlay'].includes(name)) {
    const game = selectedGame(); if (!game || !sharedPreferences) return;
    const overrides = { ...(sharedPreferences.game_overlay_settings || {}) as Record<string, Record<string, unknown>> };
    const identity = Object.keys(overrides).find(key => pathKey(key) === pathKey(game.path)) || game.path;
    if (name === 'inherit-game-overlay') delete overrides[identity];
    else overrides[identity] = { ...overrides[identity], ...gameOverlayDrafts.get(game.id) };
    if (name === 'apply-game-overlay') void withOperation('Review this game’s overlay', 'overlay_package_review', { ...sharedPreferences, game_overlay_settings: overrides, target_games: [game.path] });
    else void withOperation('Review per-game overlay preferences', 'settings_review', { changes: { game_overlay_settings: overrides } });
  }
  if (['artwork-store', 'artwork-reset', 'artwork-sync', 'sgdb-status', 'sgdb-connect', 'sgdb-disconnect', 'sgdb-search'].includes(name)) void artworkAction(name);
}
async function discardReview() {
  const origin = operation?.origin || 'details';
  if (operation?.review) {
    const token = operation.review.token;
    try { await engineRequest(operation.execute === 'execute_routes' ? 'discard_routes' : operation.execute === 'run' ? 'discard' : 'discard_operation', operation.execute === 'run' ? { token } : { tokens: [token] }); }
    catch (problem) { announce(problem instanceof Error ? problem.message : 'Could not release this review.'); }
  }
  pendingInstall=null;operation = null; setView(origin);
}
async function confirmOperation() {
  const state = operation; if (!state?.review || state.stage !== 'review') return;
  if (state.review.trust && !app.querySelector<HTMLInputElement>('#review-trust')?.checked) return;
  const supported = [...app.querySelectorAll<HTMLInputElement>('[data-supported-token]:checked')].map(field => field.dataset.supportedToken!);
  state.stage = 'running'; render();
  try {
    state.result = await engineRequest(state.execute, { token: state.review.token, trusted: true, offline_acknowledged: Boolean(state.review.trust), supported }, progress => {
      state.progress = progress;
      const label = app.querySelector('.operation-progress [role="status"]');
      if(state.kind){const step=app.querySelector('.operation-step');if(step)step.outerHTML=operationStep(state,snapshot?.games||[],icon);applyOperationAccent();}
      else if (label) label.textContent = String(progress.label || progress.phase || 'Working…');
    });
    state.stage = 'done'; engineRows = [];
    if(state.origin === 'presets' && !(state.result as Record<string,unknown>)?.cancelled) { drafts.delete(presetId); presetSelection=false; batchSelection.clear(); }
    if (['settings_review', 'executable_review', 'package_use'].includes(state.method || '') || state.origin === 'presets') {
      try {
        sharedPreferences = await engineRequest<Record<string, unknown>>('settings_get');
        for (const key of state.changedKeys || []) delete preferenceChanges[key];
        if (snapshot) for (const key of Object.keys(snapshot.defaults)) if (key in sharedPreferences) snapshot.defaults[key] = sharedPreferences[key];
        if(snapshot)snapshot.preferences={...snapshot.preferences,...sharedPreferences};
        if(state.changedKeys?.includes('library_view'))libraryView=sharedPreferences.library_view==='list'?'list':sharedPreferences.library_view==='capsules'?'capsules':'grid';
        if(state.changedKeys?.includes('navigation_position'))appearance.navigation=sharedPreferences.navigation_position==='bottom'?'bottom':'top';
        if(state.changedKeys?.includes('ui_scale'))appearance.scale=sharedPreferences.ui_scale==='auto'?'auto':Number(sharedPreferences.ui_scale);
        if(state.changedKeys?.some(key=>['game_folders','extra_folders','library_folders','removed_games'].includes(key))){snapshot=await readSnapshot();batchSelection.clear();}
      } catch { /* The completed operation result remains authoritative if refreshing preferences fails. */ }
    }
  } catch (problem) { state.stage = 'error'; state.error = problem instanceof Error ? problem.message : 'The engine operation failed.'; }
  render(); document.querySelector<HTMLElement>('#page-title')?.focus();
}
async function addLibraryFolder(collection: boolean) {
  if(!backend.enabled)return;
  if(!('__TAURI_INTERNALS__' in window)){announce('Folder selection is available in the native window. You can also edit the folder list.');return;}
  try {const {invoke}=await import('@tauri-apps/api/core');const path=await invoke<string|null>('choose_path',{kind:'folder'});if(!path)return;
    const key=collection?'library_folders':snapshot?.platform==='Windows'?'game_folders':'extra_folders';
    const folders=(currentPreferences()[key]||[]) as string[];
    preferenceChanges[key]=folders.some(folder=>pathKey(folder)===pathKey(path))?folders:[...folders,path];
    if(!collection)preferenceChanges.removed_games=((currentPreferences().removed_games||[]) as string[]).filter(folder=>pathKey(folder)!==pathKey(path));
    await withOperation(collection?'Add library folder':'Add game folder','settings_review',{changes:{[key]:preferenceChanges[key],...(!collection?{removed_games:preferenceChanges.removed_games}:{})}});
  }catch(problem){announce(problem instanceof Error?problem.message:'Folder selection could not be opened.');}
}
async function reviewSteam(remove = false) {
  operation = { stage: 'checking', title: 'Review Steam shortcut', execute: remove?'steam_remove':'steam_install', origin: 'settings' }; setView('operation');
  try {
    const summary = await engineRequest<{ token: string; profile: string; roles: unknown; created: unknown; added?:boolean }>(remove?'steam_status':'steam_review');
    if(remove && !summary.added){operation.stage='done';operation.result={message:'rtxForge is not currently added to Steam.'};render();return;}
    operation.review = { token: summary.token, title: remove?'Remove rtxForge from Steam':'Review Steam shortcut', action: remove?'Remove shortcut':'Add to Steam', rows: [{ name: 'rtxForge application shortcut', detail: remove?'Remove the exact existing application shortcut. Game shortcuts remain unchanged.':`Profile: ${summary.profile}. Artwork: ${JSON.stringify(summary.roles)}.` }] };
    operation.stage = 'review';
  } catch (problem) { operation.stage = 'error'; operation.error = problem instanceof Error ? problem.message : 'The Steam shortcut could not be reviewed.'; }
  render();
}
async function extraAction(name: string) {
  const game = selectedGame(); if (!game) return;
  try {
    const rows = await getEngineRows();
    const row = rows.find(row => pathKey(row.game) === pathKey(game.path));
    if (!row) throw new Error('This game is unavailable to the engine. Check its executable in the existing app.');
    if (name === 'extra-records') { extraRecords = await engineRequest('extras_list', { row }); render(); announce(extraRecords.length ? 'Tool recovery records loaded.' : 'No tool recovery records for this game.'); }
    else if(extraKind==='hdr-custom') await withOperation('Review custom RenoDX HDR','hdr_review',{row,custom_path:extraSource});
    else await withOperation('Review tool installation', 'extra_review', { row, path: extraSource, kind: extraKind });
  } catch (problem) { announce(problem instanceof Error ? problem.message : 'The extra could not be reviewed.'); }
}
function artworkRow() { const game = selectedGame(); return game ? { game: game.path, name: game.name, appid: game.appid, source: game.source } : null; }
async function artworkAction(name: string) {
  const row = artworkRow();
  try {
    if (name === 'sgdb-status') { const status = await engineRequest<{connected: boolean}>('sgdb_status'); gridConnected = status.connected; render(); return; }
    if (name === 'sgdb-connect') { const field = app.querySelector<HTMLInputElement>('#sgdb-key'); const key = field?.value || ''; if (field) field.value = ''; await engineRequest('sgdb_connect', { key }); gridConnected = true; render(); return; }
    if (name === 'sgdb-disconnect') { await engineRequest('sgdb_disconnect'); gridConnected = false; artworkAssets = []; artworkMatches = []; render(); return; }
    if (!row) throw new Error('Choose a game for artwork.');
    if (name === 'sgdb-search') { artworkMatches = await engineRequest('sgdb_search', { term: artworkQuery || selectedGame()?.name || '' }); artworkAssets = []; render(); return; }
    if (name === 'artwork-sync') { await withOperation('Review artwork sync', 'art_sync_review', { rows: [row], single: true }); return; }
    if (name === 'artwork-store') await engineRequest('art_store', { row, role: artworkRole, path: artworkPath });
    if (name === 'artwork-reset') await engineRequest('art_reset', { row, role: artworkRole });
    artworkMessage = name === 'artwork-reset' ? 'Automatic artwork restored. Steam sync remains a separate review.' : 'Artwork saved for this game. Steam sync remains a separate review.';
    await refresh();
  } catch (problem) { artworkMessage = problem instanceof Error ? problem.message : 'Artwork could not be updated.'; render(); announce(artworkMessage); }
}
async function chooseArtworkAsset(index: number) {
  const asset = artworkAssets[index], row = artworkRow(); if (!asset || !row) return;
  try {
    const downloaded = await engineRequest<{path: string}>('sgdb_download', { asset });
    await engineRequest('art_store', { row, role: artworkRole, path: downloaded.path, credit: asset.author, link: asset.url });
    artworkMessage = 'Artwork saved with its artist credit. Steam sync remains a separate review.'; await refresh();
  } catch (problem) { artworkMessage = problem instanceof Error ? problem.message : 'Artwork could not be saved.'; render(); }
}
async function refresh() {
  clearArtworkCache();
  loading = true; error = ''; render();
  try {
    const firstRead=!snapshot;snapshot = await readSnapshot();
    if(firstRead)libraryView=snapshot.preferences?.library_view==='list'?'list':snapshot.preferences?.library_view==='capsules'?'capsules':'grid';
    if (!selectedId) selectedId = snapshot.games[0]?.id || '';
    void resolveLibraryAccents(snapshot);
    const captured=snapshot;
    void hydrateArtwork(captured,(game,role)=>{
      if(snapshot!==captured)return;
      if(role==='poster')void resolveLibraryAccents(captured,[game]);
      if(view==='details'&&selectedId===game.id)render();
      else if(view==='library'){
        const item=app.querySelector<HTMLElement>(`[data-library-game="${CSS.escape(game.id)}"]`);
        const source=libraryView==='grid'?game.art:game.capsule||game.art;
        if(role==='hero'||!source)return;
        item?.querySelectorAll<HTMLImageElement>('img').forEach(image=>{image.src=source;image.style.visibility='';image.hidden=false;image.parentElement?.classList.remove('art-unavailable');});
      }
    }).then(()=>{if(snapshot===captured)void resolveLibraryAccents(captured);});
    announce(`Library refreshed. ${snapshot.games.length} games found.`);
  } catch (problem) { error = problem instanceof Error ? problem.message : 'The local reader is unavailable. Refresh to try again.'; announce(error); }
  finally { loading = false; render(); }
}
applyAppearance();
document.addEventListener('pointerdown',event=>{
  const target=event.target as HTMLElement;
  if(shellMenuOpen&&!target.closest('.shell-more')){shellMenuOpen=false;const menu=app.querySelector<HTMLElement>('#shell-menu');if(menu)menu.hidden=true;app.querySelector('#shell-menu-button')?.setAttribute('aria-expanded','false');}
  if(detailsMenuOpen&&!target.closest('.hero-more')){detailsMenuOpen=false;const menu=app.querySelector<HTMLElement>('.game-menu');if(menu)menu.hidden=true;app.querySelector('[data-action="game-menu"]')?.setAttribute('aria-expanded','false');}
});
installInput(() => { if(selectMenuOpen()){closeSelectMenu();return;} if(detailsMenuOpen){detailsMenuOpen=false;render();app.querySelector<HTMLElement>('[data-action="game-menu"]')?.focus();return;} if (shellMenuOpen) { shellMenuOpen=false; const menu=app.querySelector<HTMLElement>('#shell-menu'); if(menu)menu.hidden=true; app.querySelector<HTMLElement>('#shell-menu-button')?.focus(); return; } if (view === 'operation' && operation?.stage === 'running') { announce('The operation is running. Use Request cancellation to stop safely.'); return; } if (view === 'operation' && (operation?.stage === 'review'||operation?.stage==='startup'||operation?.stage==='checking')) { void discardReview(); return; } if (view !== 'library') setView('library'); else app.querySelector<HTMLElement>('[data-route="library"]')?.focus(); }, delta => {
  if(selectMenuOpen()||shellMenuOpen||detailsMenuOpen||view==='operation')return;
  const index = tabs.findIndex(tab => tab.id === (view === 'details' ? 'library' : view));
  setView(tabs[(index + delta + tabs.length) % tabs.length].id);
}, (state, id) => { document.documentElement.dataset.controller=String(state); controller = state; controllerId = id || ''; const hint = app.querySelector('#input-hints'); if (hint) hint.innerHTML = hints(); }, showHints);
void refresh();
void engineStatus().then(status => { backend = status; render(); }).catch(() => { backend = { enabled: false, reason: 'The reviewed host adapter is unavailable. Refresh the local preview.' }; });
