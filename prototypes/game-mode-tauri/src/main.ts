import {surfaceCards} from './surface-cards';
import {overlayStatusView,type OverlayStatus} from './overlay-status';
import {setupViewportArtwork} from './viewport-artwork';
import {surfaceTintControls} from './surface-tint';
import {colorPicker, bindColorPicker} from './color-picker';
import './style.css';
import { captureArrival, arrive } from './motion';
import { bindArtworkFailures, hydrateArtwork, clearArtworkCache, prioritizeArtwork } from './artwork';
// Artwork sources remain exact library identities.
import { accentSources, appearanceDefaults, forgeGreen, escape as e, readAppearance, readSnapshot, type Appearance, type Game, type OverviewCard, type Snapshot, type View } from './model';
import { bindReviewInfo, operationFlow,operationStep,flowSteps,flowGame,reviewRow } from './operation-ui';
import { activeSetup, changePicker, newPicker, splitChoice, splitPicker, splitPresetSelect, splitRenderDescription, type Catalog, type Picker, type Setup } from './split-render';
import { installInput } from './input';
import { setupLibraryLayout } from './library-layout';
import { heroCrop, analyzeHeroFocus } from './hero-focus';
import { thumbnailColor, applyStoreBackground, prepareStoreBackground, screenshotGallery, selectedScreenshots, chooseScreenshots, updateBackgroundContrast, type StoreScreenshot } from './store-background';
import { webviewZoom } from './display-scale';
import { bindScreenshotThumbnails } from './screenshot-crop';
import { controllerGlyph, type ControllerFamily } from './controller-glyphs';
import { artworkAccent, selectionInk, heroColors, heroBadge, sampleHero, sectionHeadingColor } from './art-accent';
import { enhanceSelects, closeSelectMenu, selectMenuOpen } from './select-menu';
import { settingsGroups, settingsContent } from './settings-content';
import {previewAccent,mergeOverlay, overlaySurface, surfaceChanges, overlayPreferenceChanges} from './overlay-settings';
let overlayPreviewId = '';

import { engineRequest, engineStatus, watchActivity, type EngineRow, type EngineStatus, type Review } from './engine';

const symbols: Record<string, number> = { plus:58324, minus:58154, dots: 57854, books: 59224, package: 58256, wrench: 58836, gear: 57968, search: 58124,
  refresh: 57492, controller: 57966, arrow: 57432, check: 57730, folder: 57930, info: 58062, warning: 58592,
  palette: 59080, sliders: 58420, cpu: 58896, grid: 58006, list: 58096, keyboard: 58072, eye: 57888, download: 57868 };
const icon = (name: string, cls = '') => name==="file" ? `<svg class="icon ${cls}" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M6 3h8l4 4v14H6zM14 3v5h4"/></svg>` : name==='posters'||name==='capsules' ? `<svg class="icon layout-icon ${cls}" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">${name==='posters'?'<rect x="3" y="3" width="7" height="18" rx="1.5"/><rect x="14" y="3" width="7" height="18" rx="1.5"/>':'<rect x="3" y="3" width="18" height="7" rx="1.5"/><rect x="3" y="14" width="18" height="7" rx="1.5"/>'}</svg>` : `<span class="icon ${cls}" aria-hidden="true">${String.fromCodePoint(symbols[name] || symbols.info)}</span>`;
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
let operation: { stage: 'startup' | 'checking' | 'review' | 'running' | 'done' | 'error';kind?:string;targets?:Game[];cancelRequested?:boolean; title: string; review?: Review; execute: string; progress?: Record<string, unknown>; result?: unknown; error?: string; origin?: View; method?: string; changedKeys?: string[]; dismissed?: boolean;
  overlayReportAction?:'Fix'|'Try again'; refreshOverlaysAfterRepair?:boolean;
  split?: { picker: Picker; revision: number; pending: boolean; error: string; rows: Record<string, unknown>[]; open: boolean };
  acceptedTrust?: boolean; chosenOffers?: Set<string>;
} | null = null;
let settingsCategory = 'appearance', sharedPreferences: Record<string, unknown> | null = null;
const preferenceChanges: Record<string, unknown> = {};
let extraSource = '', extraRecords: Record<string, unknown>[] = [], packageSource = '';
let liveCatalog: (Record<string, unknown> & { id: string; name: string; version: string })[] | null = null;
const batchSelection = new Set<string>();
interface DlssInventory { files: { title: string; path: string; current: string; provenance?: string }[]; blocked?: string }
const fileInventories = new Map<string,DlssInventory>();
const overviewChecks = new Map<string,{cards:OverviewCard[]; extras:string[]}>();
let modalOrigin: {view:View; content:number; details:number; results:number; focus:string|null} | undefined;
function focusSelector(node:HTMLElement|null){
  return node ? (node.id ? '#' + CSS.escape(node.id) : [...node.attributes].filter(a=>a.name.startsWith('data-')).map(a=>`[${a.name}="${CSS.escape(a.value)}"]`).join('')) : null;
}
let bulkMode=false;
const noteDrafts = new Map<string, string>();
let hintsTimeout: ReturnType<typeof setTimeout> | undefined;
let toastTimeout: ReturnType<typeof setTimeout> | undefined;
let appliedZoom: number | undefined;
let nativeSystemScale: number | undefined, nativeMonitorSize: {width:number;height:number} | undefined, nativeDisplay: Promise<void> | undefined;
const notesLoaded = new Set<string>();
const reportEdits: Record<string, Record<string, string>> = {};
const gameOverlayDrafts = new Map<string, Record<string, unknown>>();
let artworkRole = 'poster', artworkPath = '', artworkQuery = '', artworkMatches: {id: number; name: string}[] = [];
let artworkAssets: Record<string, unknown>[] = [], artworkMessage = '', gridConnected: boolean | null = null;
let librarySizeOpen = false;
let backgroundIntent:ReturnType<typeof setTimeout>|undefined;
let shellMenuOpen = false, detailsMenuOpen=false, presetSelection = false;
const presetId = '__library-presets__';
const gameAccentDrafts = new Map<string,string>();
const heroFocusDrafts=new Map<string,[number,number]>(),automaticHeroFocus=new Map<string,{source:string;point:[number,number]}>(),loadingHeroFocus=new Set<string>();const backgroundGalleries=new Map<string,StoreScreenshot[]>(),loadingGalleries=new Set<string>();
let heroAdjustment:{game:string;previous?:[number,number]}|undefined;
const supportSelection = new Set<string>();
let heroResize: ResizeObserver | undefined;
let renderedView: View | undefined, renderedGame = '';
let adaptiveMainSource="",adaptiveMainAccent="";
let preferencesLoading = false, steamAdded:boolean|undefined, steamChecking=false;
let libraryScroll = 0;
let appearanceReady=false,appearanceStored="",appearanceTimer:ReturnType<typeof setTimeout>|undefined;
let appearanceWrites:Promise<void>=Promise.resolve();
let disposeViewportArtwork=()=>{};
let pendingInstall:{params:Record<string,unknown>;settings:Record<string,unknown>;rows:EngineRow[]}|null=null;
let splitCatalog: Catalog | undefined;
const packagePicker = newPicker();
let splitPackageOpen = false, splitRemove = false, splitQuery = '', splitMatchRevision = 0, splitMatching = false, splitMatchError = '', splitMatchNotice = '';
const splitSelected = new Set<string>();
let splitMatches = new Map<string, { row: EngineRow; summary: string }>();
let splitTool: { game: string; row: EngineRow; catalog: Catalog; picker: Picker; installed: boolean; installedText: string;
  checked: boolean; reason: string; verdict: string; revision: number; busy: boolean; feederPass?: number; feederRole?: boolean; feederSkin?: number; feederMessage?: string } | undefined;
let splitToolError = '';
let splitPresetPackage = '', splitPresetRequest = 0, splitPresetError = '';
let splitPresetEditor: { catalog: Catalog; picker: Picker; name: string; checked: boolean; reason: string; revision: number; busy: boolean } | undefined;
let libraryFilter = 'all', libraryChecking = false, libraryMode: string | undefined;

function announce(message: string) {
  document.querySelector('#announcer')!.textContent = message;
  const toast = document.querySelector<HTMLElement>('#toast');
  if (toast) { toast.textContent = message; toast.title = message; toast.dataset.open = 'true'; if (toastTimeout) clearTimeout(toastTimeout); toastTimeout = setTimeout(() => { toast.dataset.open = 'false'; }, 3600); }
}
function showHints() { document.documentElement.dataset.hints = 'visible'; if (hintsTimeout) clearTimeout(hintsTimeout); if ((preferenceChanges.controller_hints ?? sharedPreferences?.controller_hints ?? snapshot?.defaults.controller_hints) === 'auto') hintsTimeout = setTimeout(() => { document.documentElement.dataset.hints = 'hidden'; }, 2500); }
let nativeAccent: string | undefined;
let readingSystemAccent = false;
const appAccent = () => appearance.accentSource === 'green' ? forgeGreen : appearance.accentSource === 'system' ? nativeAccent || forgeGreen : appearance.accent;

async function refreshSystemAccent() {
  if (readingSystemAccent || appearance.accentSource !== 'system' || !('__TAURI_INTERNALS__' in window)) return;
  readingSystemAccent = true;
  try {
    const color = await (await import('@tauri-apps/api/core')).invoke<string | null>('system_accent');
    const next = color && /^#[0-9a-f]{6}$/i.test(color) ? color : undefined;
    if (next !== nativeAccent) { nativeAccent = next; applyAppearance(); }
  } catch { /* Keep the current accent if the platform cannot be reached. */ }
  finally { readingSystemAccent = false; }
}

function applyAppearance() {
  const accent = appAccent();
  const root = document.documentElement;
  const gameDetails = view === 'details' || view === 'operation' && operation?.origin === 'details';
  root.dataset.theme = gameDetails && appearance.detailsTheme !== 'same' ? appearance.detailsTheme : appearance.theme;
  root.dataset.libraryScale=String(appearance.libraryScale);
  root.dataset.gameModePreview=String(Boolean(backend.preview));
  appearance.tint=appearance.accentMode!=='theme'&&appearance.tintStrength>0;
  root.dataset.tint = String(appearance.tint);
  root.style.setProperty('--surface-tint-level',String(appearance.tintStrength/50));
  if(appearance.accentMode==='adaptive'&&view!=='details'){const source=appearance.background||(appearance.theme==='light'?'/app-hero-light.png':'/app-hero-dark.png');if(source!==adaptiveMainSource){adaptiveMainSource=source;void thumbnailColor(source).then(color=>{if(adaptiveMainSource===source){adaptiveMainAccent=color||'';applyAppearance();}});}}
  const adaptive=view==='details'?document.querySelector<HTMLElement>('#scene')?.dataset.adaptiveAccent:adaptiveMainAccent;
  root.dataset.accentMode=appearance.accentMode;
  root.style.setProperty('--surface-accent',appearance.accentMode==='adaptive'&&adaptive?adaptive:accent);
  root.dataset.motion = String(appearance.motion);
  root.dataset.text = appearance.text;
  root.dataset.navigation = appearance.navigation;
  root.dataset.detailsNavigation = appearance.detailsNavigation;
  root.dataset.buttonGlyphs = String(currentPreferences().button_glyphs !== false);
  root.style.setProperty('--accent', accent);
  root.style.setProperty('--section-heading-color',sectionHeadingColor(accent,root.dataset.theme==='light'));
  root.style.setProperty('--shell-accent', accent);
  root.style.setProperty('--shell-primary-ink', selectionInk(accent));
  root.style.setProperty('--primary-ink',selectionInk(accent));
  root.dataset.customBackground=String(Boolean(appearance.background));
  if(appearance.background)root.style.setProperty('--custom-background',`url("${appearance.background}")`);else root.style.removeProperty('--custom-background');
  applyDetailsAccent();
  void updateBackgroundContrast();
  if ('__TAURI_INTERNALS__' in window) {
    if(nativeSystemScale===undefined){
      nativeDisplay??=import('@tauri-apps/api/window').then(async({getCurrentWindow,currentMonitor})=>{
        const windowHandle=getCurrentWindow();nativeSystemScale=await windowHandle.scaleFactor();
        nativeMonitorSize=(await currentMonitor())?.size;
        const moved=await windowHandle.onMoved(()=>{void currentMonitor().then(monitor=>{const size=monitor?.size;if(size?.width!==nativeMonitorSize?.width||size?.height!==nativeMonitorSize?.height){nativeMonitorSize=size;appliedZoom=undefined;applyAppearance();}});});
        window.addEventListener('pagehide',moved,{once:true});
        const stop=await windowHandle.onScaleChanged(({payload})=>{nativeSystemScale=payload.scaleFactor;void currentMonitor().then(monitor=>{nativeMonitorSize=monitor?.size;appliedZoom=undefined;applyAppearance();});});
        window.addEventListener('pagehide',stop,{once:true});applyAppearance();
      }).catch(()=>{nativeDisplay=undefined;announce('The display scale could not be read.');});
    }else{
      const zoom=webviewZoom(appearance.scale,nativeSystemScale,nativeMonitorSize)*(backend.preview&&!backend.fullscreen?0.88:1);
      if(appliedZoom!==zoom){appliedZoom=zoom;void import('@tauri-apps/api/webview').then(({getCurrentWebview})=>getCurrentWebview().setZoom(zoom)).catch(()=>{appliedZoom=undefined;announce('The interface scale could not be applied.');});}
    }
  }
  const stored=serializeAppearance();
  try { localStorage.setItem('rtxforge-game-mode-prototype',stored); } catch { /* Session preferences remain usable. */ }
  if(appearanceReady&&!backend.preview&&'__TAURI_INTERNALS__' in window){
    clearTimeout(appearanceTimer);
    appearanceTimer=setTimeout(()=>{void flushAppearance().catch(()=>announce('Appearance could not be saved to Desktop Mode. Try changing it again.'));},250);
  }
}
function serializeAppearance(){
  return JSON.stringify({...appearance,detailsNavigationVersion:1,appearanceDefaultsVersion:2,libraryScaleVersion:1});
}
function flushAppearance(){
  clearTimeout(appearanceTimer);
  if(backend.preview)return Promise.resolve();
  const pending=appearanceWrites.catch(()=>{}).then(async()=>{
    const stored=serializeAppearance();
    if(stored===appearanceStored)return;
    await (await import('@tauri-apps/api/core')).invoke('appearance_write',{value:JSON.parse(stored)});
    appearanceStored=stored;
  });
  appearanceWrites=pending;
  return pending;
}
function selectedGame(): Game | undefined { return snapshot?.games.find(game => game.id === selectedId) || snapshot?.games[0]; }
function setView(next: View, focus = true) {
  clearTimeout(backgroundIntent);
  if (operation?.stage === 'running' && next !== 'operation') { announce('The operation is running. Request cancellation to stop safely.'); return; }
  if (view === 'operation' && next !== 'operation' && operation?.stage === 'checking') operation.dismissed = true;
  const previousView = view;
  if(next==='operation'&&previousView!=='operation'&&operation?.kind){
    modalOrigin={view:previousView,content:app.querySelector('#content')?.scrollTop||0,details:app.querySelector('.details-scroll')?.scrollTop||0,results:app.querySelector('#game-results')?.scrollTop||0,focus:focusSelector(document.activeElement as HTMLElement|null)};
  }
  if(view==='details'&&next!=='details'){heroFocusDrafts.clear();gameAccentDrafts.clear();heroAdjustment=undefined;}
  if (view === 'library') libraryScroll=app.querySelector<HTMLElement>('#game-results')?.scrollTop||app.querySelector<HTMLElement>('#content')?.scrollTop||0;
  librarySizeOpen = false; shellMenuOpen = false; detailsMenuOpen=false; view = next; render();
  if (focus) document.querySelector<HTMLElement>('#page-title')?.focus();
  const content=app.querySelector<HTMLElement>('#content');if(content&&!(next==='operation'&&modalOrigin))content.scrollTop=next==='library'?libraryScroll:0;
  if(next==='library'){const results=app.querySelector<HTMLElement>('#game-results');if(results)results.scrollTop=libraryScroll;}
  if(next==='library'&&previousView==='details'&&focus) [...app.querySelectorAll<HTMLElement>('[data-game]')].find(node=>node.dataset.game===selectedId)?.focus({preventScroll:true});
  if(previousView==='operation'&&next!=='operation'&&modalOrigin){
    const origin=modalOrigin;modalOrigin=undefined;
    if(origin.view===next){
      for(const [selector,offset] of [['#content',origin.content],['.details-scroll',origin.details],['#game-results',origin.results]] as const){
        const pane=app.querySelector<HTMLElement>(selector);if(pane)pane.scrollTop=offset;
      }
      if(origin.focus)app.querySelector<HTMLElement>(origin.focus)?.focus({preventScroll:true});
    }
  }
  if (next === 'presets' && backend.enabled) void loadSplitPresets();
  if (next === 'settings' && backend.enabled && !sharedPreferences) void loadPreferences();
  if (next === 'packages' && backend.enabled) void loadSplitCatalog().then(() => { if (view === 'packages') { render(); if (splitPackageOpen || splitRemove) void matchSplitGames(); } })
    .catch(problem => announce(problem.message));
  if (next === 'details' && detailsSection === 'tools' && backend.enabled && selectedGame()) void loadSplitTool(selectedGame()!);
  if(next==='details'&&backend.enabled){const game=selectedGame();if(game)void getEngineRows(game).then(rows=>{if(view==='details'&&selectedId===game.id){render();if(detailsSection==='overview'&&rows[0])void loadOverviewExtras(game,rows[0]);}}).catch(problem=>announce(problem.message));}
}
async function loadPreferences() {
  if (preferencesLoading || !backend.enabled) return;
  preferencesLoading = true;
  try { sharedPreferences = await engineRequest<Record<string,unknown>>('settings_get'); if(view==='settings'||perGameOverlay()) render(); }
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
function featureRecord(game: Game) {
  return engineRows.find(row => pathKey(row.game) === pathKey(game.path)) || game.savedRecord;
}
function featureOperation(record: Record<string, unknown> | undefined): 'install' | 'update' {
  const os = snapshot?.platform?.toLowerCase();
  const otherOs = os === 'linux' ? 'windows' : 'linux';
  const foreign = record?.installed_on === otherOs;
  return record?.installed && !record.adoption_available && !foreign ? 'update' : 'install';
}
function libraryFeatureOperation(games: Game[], selected: boolean): 'install' | 'update' {
  const records = games.map(featureRecord);
  return records.some(record => featureOperation(record) === 'update')
    && (selected || records.every(record => record?.installed)) ? 'update' : 'install';
}
function library() {
  const games = snapshot?.games || [], filtered = filteredLibrary();
  const batchAction = libraryFeatureOperation(games.filter(game => batchSelection.has(game.id)), true);
  if (loading && !snapshot) return heading('Library', 'Reading your local game library…') + librarySkeleton();
  return heading('Library', snapshot ? `${games.length} ${games.length === 1 ? 'game' : 'games'} in your local library${!backend.enabled?' · Status from saved library checks':''}` : 'Your games, ready for a closer look.',
    `<button class="quiet" data-action="refresh" ${loading ? 'disabled' : ''}>${icon('refresh')}<span>${loading ? 'Refreshing…' : 'Refresh library'}</span></button>`) + `<div class="library-actions-host">${batchSelection.size?`<div class="library-actions-placeholder" aria-hidden="true" inert>${libraryOperations()}</div>`:libraryOperations()}${batchSelection.size?`<div class="selection-bar inner-card"><span>${batchSelection.size} selected</span>${presetSelection ? `<button class="primary" data-action="apply-selected-presets" ${!backend.enabled?'disabled':''}>Apply presets to selected</button><button class="quiet" data-action="end-preset-selection">End preset selection</button>` : ''}<button class="primary" data-operation="${batchAction}" data-batch="true" ${!backend.enabled ? 'disabled' : ''}>Review selected ${batchAction}</button><button class="quiet" data-operation="uninstall" data-batch="true" ${!backend.enabled ? 'disabled' : ''}>Review selected restore</button><button class="quiet" data-action="remove-selected-entries" ${!backend.enabled?'disabled':''}>Remove entries</button><button class="quiet" data-action="clear-selection">Clear selection</button></div>`:''}</div>` +
    (error ? notice('Library reader unavailable', e(error), 'warning') : '') +
    (snapshot?.warnings.length ? notice('Some library data is unavailable', snapshot.warnings.map(e).join(' '), 'warning') : '') +
    `<div class="library-tools"><label class="search">${icon('search')}<input id="library-search" type="search" placeholder="Search your library" aria-label="Search your library" value="${e(query)}" /></label><label class="library-filter"><span>Show</span><select id="library-filter" aria-label="Filter library" ${!backend.enabled||libraryChecking?'disabled':''}>${[['all','All games'],['available','Available'],['installed','Installed']].map(([key,label])=>`<option value="${key}" ${libraryFilter===key?'selected':''}>${label}</option>`).join('')}</select></label><div class="library-size-control" data-open="${librarySizeOpen}"><button id="library-size-button" class="library-size-button" data-action="library-size-menu" aria-label="Card size" aria-expanded="${librarySizeOpen}" aria-controls="library-size-panel" ${libraryView==='list'?'disabled':''}>${icon('sliders')}</button><div id="library-size-panel" class="library-size-panel"><label class="library-size"><span>Card size</span><input id="library-size" type="range" min="70" max="140" step="5" value="${appearance.libraryScale}" aria-label="Library item size" aria-valuetext="${appearance.libraryScale}%" ${libraryView==='list'?'disabled':''}/><output for="library-size">${appearance.libraryScale}%</output></label></div></div><div class="library-view-controls"><button class="quiet" data-action="bulk-select" aria-pressed="${bulkMode||presetSelection}" ${!backend.enabled?'disabled':''}>${bulkMode||presetSelection?'Done selecting':'Select games'}</button><div class="view-switch" role="group" aria-label="Library layout"><button data-layout="grid" aria-label="Poster grid" aria-pressed="${libraryView === 'grid'}">${icon('posters')}</button><button data-layout="capsules" aria-label="Wide capsules" aria-pressed="${libraryView === 'capsules'}">${icon('capsules')}</button><button data-layout="list" aria-label="Game list" aria-pressed="${libraryView === 'list'}">${icon('list')}</button></div></div></div>` +

    `<div id="game-results" aria-live="polite">${gameResults(filtered, games.length)}</div>`;
}
function librarySkeleton() {
  return `<div class="library-skeleton" aria-busy="true" aria-label="Reading your library"><span class="sr-only" role="status">Reading Steam manifests and saved game folders.</span><div class="skeleton-tools" aria-hidden="true"><i></i><i></i></div><div class="games skeleton-grid" aria-hidden="true">${Array.from({length:14},()=>'<div class="skeleton-card"><div class="skeleton-art"></div><div class="skeleton-copy"><i></i><i></i><i></i></div></div>').join('')}</div></div>`;
}
function libraryOperations() {
  const action = libraryFeatureOperation(filteredLibrary(), false);
  const modes=[['nr-only','NR Only'],['mfg-only','MFG Only'],['nr-mfg','NR + MFG']];
  const selected=libraryMode||String(snapshot?.defaults.default_profile||'mfg-only');
  const index=Math.max(0,modes.findIndex(([key])=>key===selected));
  return `<div class="library-operation-bar inner-card"><div class="library-feature-mode"><strong>Features</strong><div class="feature-mode-segments" role="group" aria-label="Feature mode" style="--selected-mode:${index}"><span class="feature-mode-indicator" aria-hidden="true"></span>${modes.map(([key,label])=>`<button data-library-mode="${key}" aria-pressed="${selected===key}">${label}</button>`).join('')}</div></div><div class="library-operation-actions"><button class="primary" data-operation="${action}" data-library-scope="true" ${!backend.enabled?'disabled':''}>${icon('download')}${action === 'update' ? 'Update Features' : 'Install Features'}</button><button class="quiet" data-operation="uninstall" data-library-scope="true" ${!backend.enabled?'disabled':''}>${icon('refresh')}Restore Original Files</button><button class="quiet" data-operation="update-dlss" data-library-scope="true" ${!backend.enabled?'disabled':''}>${icon('download')}Update DLSS</button></div></div>`;
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
    const color=detailsAccent(game)||'var(--ink)';
    return `<article class="game-item" data-library-game="${e(game.id)}" data-selected="${batchSelection.has(game.id)}" style="--game-accent:${e(color)};--game-selected-ink:${selectionInk(color)}">${art?`<img class="artwork-glow glow-core" loading="lazy" src="${e(art)}" alt="" aria-hidden="true"/><img class="artwork-glow glow-bloom" loading="lazy" src="${e(art)}" alt="" aria-hidden="true"/>`:''}<button class="game-card" data-game="${e(game.id)}" aria-label="Open ${e(game.name)} details"><div class="poster">${thumbnail({...game,art:art||null})}${libraryView==='list'?'':osBadges}</div><div class="game-copy"><h3 class="game-title">${e(game.name)}</h3><span class="game-source">${e(game.source)}</span>${libraryView!=='list'?`<span class="library-card-status" title="${actual?'Current engine check':'Saved library check'}">${icon(actual?.blocked?'warning':record?.installed?'check':'info')}<span>${e(record?.installed?profile:actual?state:'Not checked')}</span></span>`:''}</div>${libraryView==='list'?`<span class="library-profile-chip" title="${actual?'Current engine check':'Saved library check'}">${e(profile)}</span><span class="library-row-state" title="${actual?'Current engine check':'Saved library check'}"><i class="state-dot ${record?.installed?'configured':''}"></i><span>${e(state)}</span>${osBadges}</span><span class="library-open-chip">Details</span>`:''}</button>${libraryView==='list'||bulkMode||presetSelection?`<button class="select-game" data-select-game="${e(game.id)}" aria-label="Select ${e(game.name)} for batch review" aria-pressed="${batchSelection.has(game.id)}"><span class="selection-check" aria-hidden="true">${batchSelection.has(game.id)?icon('check'):''}</span></button>`:''}</article>`;
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
  return heading('Presets','Your defaults for new installs. Review games to apply them to existing packages.') + splitPresetsCard() +
    `<section class="glass-section preset-mfg"><div class="section-heading"><h2>Multi-Frame Generation</h2><label class="sr-only" for="preset-mfg-enabled">Multi-Frame Generation</label><select id="preset-mfg-enabled" data-preset-key="mfg_enabled" ${!backend.enabled ? 'disabled' : ''}><option value="true" ${values.mfg_enabled === 'true' ? 'selected' : ''}>On</option><option value="false" ${values.mfg_enabled === 'false' ? 'selected' : ''}>Off</option></select></div>${segments('mfg_mode',[['0','Automatic'],['1','Custom'],['2','Dynamic']])}${values.mfg_mode !== '0' && values.mfg_enabled !== 'false' ? `<p class="subtle">${values.mfg_mode === '2' ? 'Maximum multiplier' : 'Multiplier'}</p>${segments('multiplier',[2,3,4,5,6].map(value=>[String(value),value+'×']))}` : ''}</section>`+
    `<div class="preset-columns"><div>${card('Neural rendering',presetFields(['enabled','style','intensity','preset','passes']))}${card('DLSS presets',presetFields(['dlss_preset','rr_preset']),'<p>Applies when the game next starts DLSS. Game default keeps the game’s own choice.</p>')}</div><div>${card('Image tuning',presetFields(['detail','colour'])+`<details><summary>Fine tuning</summary>${presetFields(['structure','tone','skin','auto_mask'])}</details>`)}${card('Sharpening',presetFields(['sharpen','sharpen_shader','sharp_override','sharpness'])+`<details><summary>Motion sharpening</summary>${presetFields(['motion_sharpen','motion_sharpness'])}</details>`)}${card('Performance',presetFields(snapshot?.controlSchema?.controls.filter(control=>control.group==='Performance').map(control=>control.key)||[]))}</div></div>`+
    `<footer class="preset-footer glass-section"><span>${!backend.enabled ? 'Read-only preview · preset changes disabled.' : drafts.has(presetId) ? 'Unsaved changes.' : 'Library presets.'}</span><div class="operation-actions"><button class="quiet" data-action="reset-presets" ${!backend.enabled || !drafts.has(presetId) ? 'disabled' : ''}>Reset</button><button class="quiet" data-action="select-preset-games" ${!backend.enabled ? 'disabled' : ''}>Select games</button><button class="primary" data-action="apply-presets" ${!backend.enabled ? 'disabled' : ''}>Apply to all</button></div></footer>`;
}
function splitPresetsCard() {
  const editor = splitPresetEditor;
  if (editor?.catalog.enabled !== true) return '';
  return `<section class="glass-section split-section split-presets"><h2>${icon('sliders')} Split Render Presets</h2>
    <p>Set the environment, character and DLSS 5 model for a package. Use saved presets in installation reviews.</p>
    ${!backend.enabled ? '<p>Available in the installed app.</p>' : !editor ? `<p role="status">${e(splitPresetError || 'Loading Split Render presets…')}</p>` :
    `<label class="field"><span><strong>Package</strong></span><select id="split-preset-package" ${editor.busy ? 'disabled' : ''}>
      ${(editor.catalog.preset_packages || []).map(pkg => `<option value="${e(pkg.id)}" ${pkg.id === splitPresetPackage ? 'selected' : ''}>${e(pkg.label)}</option>`).join('')}
      </select></label>
      ${editor.catalog.blocked ? `<p role="status">${e(editor.catalog.blocked)} Open a Feeder game’s Tools to assign pass roles.</p>` :
      `${splitPicker(editor.catalog, editor.picker, 'presets', true)}
      <p role="status">${e(editor.reason || (editor.checked ? 'Ready to save.' : 'Checking setup…'))}</p>
      <div class="split-saved"><label>Preset name <input type="text" id="split-preset-name" maxlength="60" value="${e(editor.name)}"></label>
      <button class="primary" data-action="save-split-preset" ${editor.checked && !editor.reason && !editor.busy && editor.name.trim() ? '' : 'disabled'}>Save preset</button></div>`}`}</section>`;
}
async function loadSplitPresets(packageId = splitPresetPackage || (snapshot?.defaults.runtime_provider === 'skynizz' ? 'skynizz' : 'native')) {
  const request = ++splitPresetRequest;
  splitPresetError = '';
  try {
    const catalog = await engineRequest<Catalog>('nr_catalog', { package: packageId });
    if (request !== splitPresetRequest || view !== 'presets') return;
    if (catalog.enabled !== true) { splitPresetEditor = undefined; render(); return; }
    if (!catalog.preset_packages?.length || !catalog.combos) throw new Error('Split Render presets are unavailable.');
    splitPresetPackage = packageId;
    splitPresetEditor = { catalog, picker: newPicker(), name: '', checked: false, reason: '', revision: 0, busy: false };
    if (catalog.blocked) render();
    else await checkSplitPreset();
  } catch (problem) {
    if (request !== splitPresetRequest || view !== 'presets') return;
    splitPresetEditor = undefined;
    splitPresetError = problem instanceof Error ? problem.message : 'Split Render presets are unavailable.';
    render();
  }
}
async function checkSplitPreset() {
  const editor = splitPresetEditor;
  if (!editor) return;
  const ticket = ++editor.revision;
  editor.checked = false;
  editor.reason = '';
  render();
  try {
    const result = await engineRequest<{ok: boolean; reason?: string}>('nr_check',
      { package: splitPresetPackage, setup: activeSetup(editor.catalog, editor.picker) });
    if (editor.revision !== ticket) return;
    editor.reason = result.ok ? '' : result.reason || 'Choose a compatible setup.';
  } catch (problem) {
    if (editor.revision !== ticket) return;
    editor.reason = problem instanceof Error ? problem.message : 'The setup could not be checked.';
  }
  if (splitPresetEditor === editor && view === 'presets') { editor.checked = true; render(); }
}
async function saveSplitPreset() {
  const editor = splitPresetEditor;
  if (!editor?.checked || editor.reason || editor.busy || !editor.name.trim()) return;
  editor.busy = true;
  render();
  try {
    await engineRequest('nr_combo_save', { package: splitPresetPackage, name: editor.name.trim(),
      combo: activeSetup(editor.catalog, editor.picker) });
    announce('Split Render preset saved.');
    if (view === 'presets') await loadSplitPresets();
  } catch (problem) {
    editor.reason = problem instanceof Error ? problem.message : 'The preset could not be saved.';
  } finally {
    editor.busy = false;
    if (splitPresetEditor === editor && view === 'presets') render();
  }
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
    if(!game.accent&&!game.artworkAccentReady&&game.localArtwork?.includes('poster'))return;
    const accent=game.artworkAccentReady?game.artworkAccent:await artworkAccent(game.id,source);
    // A cached local poster can arrive while the remote fallback is still sampling.
    if(snapshot!==data||(game.art||game.capsule||game.hero)!==source)return;
    if(!game.artworkAccentReady){game.artworkAccent=accent||'#b4b4b4';game.artworkAccentReady=true;}
    const item=app.querySelector<HTMLElement>(`[data-library-game="${CSS.escape(game.id)}"]`);if(item){const color=detailsAccent(game);item.style.setProperty('--game-accent',color||'var(--ink)');item.style.setProperty('--game-selected-ink',selectionInk(color||'#b4b4b4'));}
    const card=item?.querySelector<HTMLElement>('.game-card');
    if(view==='library'&&game.appid&&currentPreferences().online_art!==false&&card&&(card.matches(':hover')||document.activeElement===card))void prepareStoreBackground(game.appid,game.id,detailsAccent(game));
    if(view==='settings'&&settingsCategory==='overlay'&&overlayPreviewGame()?.id===game.id){
      const glass={...snapshot?.overlayDefaults,...currentPreferences().overlay_appearance as Record<string,unknown>};
      app.querySelector<HTMLElement>('.overlay-screen')?.style.setProperty('--preview-accent',previewAccent(glass,game));
    }
    if(view==='details'&&selectedId===game.id){applyDetailsAccent();if(detailsSection==='appearance')render();else if(currentPreferences().online_art!==false)applyStoreBackground(game.appid,document.querySelector<HTMLElement>('#scene')!,game.id,detailsAccent(game));}
  }));
}
function details() {
  const game = selectedGame();
  if (!game) return heading('Game details', 'Choose a game from your library.');
  const row = engineRows.find(item => pathKey(item.game) === pathKey(game.path));
  const sections = [['overview','Overview','info'],['features','Features','sliders'],['files','DLSS Files','folder'],['tools','Tools','wrench'],['appearance','Appearance','palette'],['notes','Notes','keyboard']];
  const record = row || game.savedRecord;
  const action = featureOperation(record);
  const foreignLabel = record?.installed_on === 'windows' && snapshot?.platform?.toLowerCase() === 'linux' ? 'Adapt to Linux'
    : record?.installed_on === 'linux' && snapshot?.platform?.toLowerCase() === 'windows' ? 'Set Up for Windows' : '';
  const credit=gameCredits(game),credits=e(credit.line);
  const oses = Array.isArray(record?.installed_oses) ? record.installed_oses.filter(os=>['windows','linux'].includes(String(os))) : ['windows','linux'].includes(String(record?.installed_on)) ? [record?.installed_on] : [];
  const pills = [game.source, ...oses.map(os=>String(os) === 'windows' ? 'Windows' : 'Linux'), game.testStatus].filter(Boolean);
  const metadata = `${credits ? `<span class="hero-credits" title="${e(credit.full)}">${credits}</span>` : ''}${pills.map(pill=>`<span class="hero-pill" ${pill !== game.source ? 'title="From the saved library check"' : ''}>${e(pill)}</span>`).join('')}${!row && record && Object.keys(record).length ? '<span class="hero-cache-note">Saved library check</span>' : ''}`;
  const body = detailsSection === 'overview' ? overviewDetails(game, row) : detailsSection === 'features' ? detailFeatures(game, row) : detailsSection === 'appearance' ? detailAppearance(game) : detailTools(game, row);
  const poster = game.art ? `<div class="detail-artwork"><img class="detail-artwork-light glow-core" src="${e(game.art)}" alt="" aria-hidden="true" /><img class="detail-artwork-light glow-bloom" src="${e(game.art)}" alt="" aria-hidden="true" />${thumbnail(game, 'detail-poster')}</div>` : '';
  const status = record?.installed === true ? String(record.profile || 'Features installed') : undefined;
  return `<div class="details-page"><header class="details-hero">${game.hero ? `<div class="hero-artwork"><img class="details-hero-image" crossorigin="anonymous" src="${e(game.hero)}" alt="" /></div>` : ''}<button class="back quiet" data-route="library" aria-label="Back to Library" title="Back to Library">${icon('arrow')}<span>Back to Library</span></button><div class="details-identity">${poster}<div class="details-title-copy"><div class="details-name">${status ? `<span class="hero-status" title="${row?'Current engine check':'Saved library check'}">${e(status)}</span>` : ''}<h1 id="page-title" class="game-title ${game.name.length > 28 ? 'long-title' : ''}" title="${e(game.name)}" tabindex="-1">${e(game.name)}</h1><div class="hero-metadata hero-compact-metadata">${metadata}</div></div><div class="details-hero-bottom"><div class="details-hero-meta hero-info-card"><div class="hero-metadata">${metadata}</div>${game.description ? `<p class="hero-description">${e(game.description.replace(/<[^>]*>/g,''))}</p>` : ''}</div><div class="operation-actions hero-actions"><button class="primary" data-operation="${action}" ${!backend.enabled ? 'disabled' : ''}>${icon('download')}${action === 'update' ? 'Update Features' : foreignLabel || 'Install Features'}</button><button class="quiet" data-operation="uninstall" ${!backend.enabled || !row?.installed ? 'disabled' : ''}>${icon('refresh')}Restore Original Files</button><button class="quiet" data-contract="report_draft" ${!backend.enabled ? 'disabled' : ''}>${icon('warning')}Bug Report</button><div class="hero-more"><button class="quiet" data-action="game-menu" aria-label="More game options" aria-haspopup="menu" aria-expanded="${detailsMenuOpen}">${icon('dots')}</button><div class="game-menu glass-section" role="menu" ${detailsMenuOpen?'':'hidden'}><button role="menuitem" data-action="launch" ${!backend.enabled||!game.appid?'disabled':''}>${icon('controller')}Launch in Steam</button>
    <button role="menuitem" data-action="open-game-folder" ${!backend.enabled?'disabled':''}>${icon('folder')}Open folder</button>
    <button role="menuitem" data-action="copy-game-path">${icon('file')}Copy game location</button>
    <div class="menu-divider" role="separator"></div>
    <button role="menuitem" data-detail-section="overlay">${icon('sliders')}Overlay settings</button>
    <button role="menuitem" data-operation="update-dlss" ${!backend.enabled?'disabled':''}>${icon('download')}Update DLSS</button>
    ${action === 'update' ? `<button role="menuitem" data-operation="repair" ${!backend.enabled?'disabled':''}>${icon('wrench')}Repair Feature Files</button>` : ''}
    ${row?.adoption_available?`<button role="menuitem" data-operation="adopt">${icon('check')}Adopt with rtxForge</button><button role="menuitem" data-operation="adopt-clean">${icon('refresh')}Back up and clean install</button>`:''}
    <div class="menu-divider" role="separator"></div>
    <button role="menuitem" data-action="remove-current-entry" ${!backend.enabled?'disabled':''}>${icon('minus')}Remove from library</button></div></div></div></div></div></div></header><div class="details-layout"><nav class="detail-nav glass-section" aria-label="Game details">${sections.map(([key,label,glyph])=>`<button data-detail-section="${key}" aria-pressed="${detailsSection===key}">${icon(glyph)}<span>${label}</span></button>`).join('')}</nav><div class="details-scroll"><div class="hero-spacer" aria-hidden="true"></div><div class="detail-body">${body}</div></div></div></div>`;
}
async function loadOverviewExtras(game: Game, row: EngineRow) {
  try {
    const result = await engineRequest<{cards:OverviewCard[];extras:string[]}>('overview_inspect',{row});
    if(!Array.isArray(result?.cards) || !Array.isArray(result?.extras))return;
    overviewChecks.set(game.id,result);
    if(view==='details' && selectedId===game.id && detailsSection==='overview'){
      const facts = app.querySelector('#overview-facts');
      if(facts) facts.outerHTML=overviewFacts(result.cards,result.extras);
    }
  } catch {
    // Saved facts remain available when the optional live inspection fails.
  }
}
async function loadDlssFiles(game: Game) {
  try {
    let result: DlssInventory | DlssInventory[];
    if(backend.enabled){
      const rows=await getEngineRows(game);
      if(!rows[0])throw new Error('This installation is unavailable to the engine.');
      result=await engineRequest<DlssInventory|DlssInventory[]>('dlss_inventory',{row:rows[0]});
    } else if(!('__TAURI_INTERNALS__' in window)){
      const response=await fetch('/api/dll-inventory?id='+encodeURIComponent(game.id));
      if(!response.ok)throw new Error('File inventory is unavailable in this preview.');
      result=await response.json();
    } else return;
    fileInventories.set(game.id,Array.isArray(result)?result[0]:result);
  }catch(problem){
    fileInventories.set(game.id,{files:[],blocked:problem instanceof Error?problem.message:String(problem)});
  }
  if(view==='details'&&selectedId===game.id&&detailsSection==='files')render();
}
function overviewFacts(cards: OverviewCard[], extras: string[]) {
  const glyphs:Record<string,string>={Features:"package",Compatibility:"check","Neural rendering":"cpu","Multi-Frame Generation":"sliders"};
  const pills=(values:string[])=>values.map(value=>`<span class="hero-pill">${e(value)}</span>`).join('');
  return `<div id="overview-facts"><div class="fact-grid native-facts" data-facts="${cards.length}">
    ${cards.map(({title,values})=>`<article class="glass-section overview-fact"><div class="overview-heading">${icon(glyphs[title]||"info")}<strong>${e(title)}</strong></div><div class="overview-pills">${pills(values)}</div></article>`).join('')}
    </div>${extras.length?`<div class="inner-card overview-location overview-extras">${icon("wrench")}<div><strong>Extras</strong><div class="overview-pills">${pills(extras)}</div></div></div>`:''}</div>`;
}
function overviewDetails(game: Game, row?: EngineRow) {
  const saved = row || game.savedRecord;
  const current = overviewChecks.get(game.id);
  const cards = current?.cards || game.overviewCards || [{title:'Features',values:['Not checked']},{title:'Compatibility',values:['No compatibility result']}];
  const chooseExe = backend.enabled && snapshot?.platform==='Windows';
  return `${overviewFacts(cards,current?.extras||[])}
    <div class="overview-locations">
      <div class="inner-card overview-location">${icon('folder')}<div><strong>Game folder</strong><small class="path">${e(game.path)}</small></div><button class="quiet" data-action="open-game-folder" ${!backend.enabled?'disabled':''}>Open folder</button></div>
      <div class="inner-card overview-location">${icon('file')}<div><strong>Game executable</strong><small>${saved?.exe?e(saved.exe)+(saved.executable_selected?' · Selected by you':' · Detected automatically'):'No executable detected'}</small></div>
        <div class="operation-actions"><button class="quiet" data-action="executable-review" ${chooseExe?'':'disabled'}>Choose EXE…</button>${chooseExe&&saved?.executable_selected?`<button class="quiet" data-action="executable-reset">Use detected</button>`:''}</div>
      </div>
    </div><section class="glass-section"><h2>Testing</h2><p>How this game runs with rtxForge. Something wrong? Prepare a bug report.</p><div class="inner-card"><label class="field"><span><strong>Test result</strong><small>Bench keeps this game out of bulk installs and repairs.</small></span><select id="test-result" ${!backend.enabled?'disabled':''}>${!game.testStatus?'<option value="">No saved result</option>':''}${['Untested','Working','Problem','Bench'].map(value=>`<option ${game.testStatus===value?'selected':''}>${value}</option>`).join('')}</select></label><div class="detail-action-row"><div><strong>${game.testActive?'Test running':'Test session'}</strong><p>${game.testActive?'Play for a minute, then finish here to check each component.':'Check package files, NR, MFG, the panel and helper, with evidence and suggested fixes.'}</p></div><div class="operation-actions"><button class="quiet" data-contract="${game.testActive?'test_finish':'test_start'}" ${!backend.enabled?'disabled':''}>${game.testActive?'Finish Test':'Start Test'}</button><button class="quiet" data-contract="report_draft" ${!backend.enabled?'disabled':''}>Bug Report</button></div></div></div></section>`;
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
  if (view !== 'details' && !(view==='operation'&&operation?.kind&&operation.origin==='details')) return;
  const content = document.querySelector<HTMLElement>('#content');
  if (!content) return;
  const game=selectedGame(),accent=detailsAccent(game);
  const adaptive=document.querySelector<HTMLElement>('#scene')?.dataset.adaptiveAccent;
  content.style.setProperty('--surface-accent',appearance.accentMode==='adaptive'&&adaptive?adaptive:accent||appAccent());
  document.querySelector<HTMLElement>('#scene')?.style.setProperty('--game-accent',accent||'#808080');
  content.style.setProperty('--accent', accent || (appearance.theme === 'light' ? '#686663' : '#d8d5ce'));
  content.style.setProperty('--accent-ink', appearance.theme === 'light' ? 'var(--ink)' : accent || 'var(--ink)');
  content.style.setProperty('--primary-ink',selectionInk(accent||'#d8d5ce'));
  const page=content.querySelector<HTMLElement>('.details-page'),image=content.querySelector<HTMLImageElement>('.details-hero-image'),title=content.querySelector<HTMLElement>('.game-title');
  const titleRange=document.createRange();if(title)titleRange.selectNodeContents(title);
  const sampled=image&&title?sampleHero(image,titleRange.getBoundingClientRect(),true):null;
  const info=content.querySelector<HTMLElement>('.hero-info-card'),badge=content.querySelector<HTMLElement>('.hero-status');
  const artwork=content.querySelector<HTMLElement>('.hero-artwork');
  if(info&&artwork){
    const card=info.getBoundingClientRect(),art=artwork.closest('.details-hero')!.getBoundingClientRect();
    artwork.dataset.infoMask='true';
    artwork.style.setProperty('--info-mask-x',(card.left-art.left)+'px');artwork.style.setProperty('--info-mask-y',(card.top-art.top)+'px');
    artwork.style.setProperty('--info-mask-width',card.width+'px');artwork.style.setProperty('--info-mask-height',card.height+'px');
    artwork.style.setProperty('--info-mask',`url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="${card.width}" height="${card.height}"><rect width="100%" height="100%" rx="12" fill="black"/></svg>`)}")`);
  }
  const cardSample=image&&info?sampleHero(image,info.getBoundingClientRect()):null;
  const colors=heroColors(accent||'#d8d5ce',appearance.theme==='light',sampled||undefined,cardSample||undefined,appearance.tint);
  const badgeColors=heroBadge(image&&badge?sampleHero(image,badge.getBoundingClientRect())||undefined:undefined);
  content.style.setProperty('--game-title-color',colors.title);
  content.style.setProperty('--section-heading-color',sectionHeadingColor(accent||'#d8d5ce',document.documentElement.dataset.theme==='light'));
  content.style.setProperty('--title-veil',String(colors.titleVeil));
  content.style.setProperty('--hero-card-color',colors.card);
  content.style.setProperty('--hero-card-ink',colors.ink);
  if(appearance.theme==='light')content.style.setProperty('--soft-accent',colors.ink);else content.style.removeProperty('--soft-accent');
  content.style.setProperty('--hero-badge-surface',badgeColors.surface);
  content.style.setProperty('--hero-badge-ink',badgeColors.ink);
  if(page)page.dataset.heroCard=colors.light?'light':'dark';
  content.dataset.gameAccent = String(Boolean(accent));
}
function screenshotChoices(game:Game){
  if(!game.appid||currentPreferences().online_art===false)return '';
  const accent=detailsAccent(game),key=game.id+'|'+(accent||'neutral');
  const shots=backgroundGalleries.get(key);
  if(!shots&&!loadingGalleries.has(key)&&(game.accent||game.artworkAccentReady)){
    loadingGalleries.add(key);
    void screenshotGallery(game.appid,accent,game.id).then(gallery=>{backgroundGalleries.set(key,gallery);loadingGalleries.delete(key);if(view==='details'&&selectedId===game.id&&detailsSection==='appearance')render();});
  }
  const chosen=selectedScreenshots(game.id,shots||[]);
  return `<section class="glass-section"><h2>Page Background</h2><p>Choose one screenshot for this game.</p><div class="screenshot-choices" role="group" aria-label="Background screenshots">${(shots||[]).map((shot,index)=>`<button class="screenshot-choice" data-background-shot="${e(shot.id)}" aria-label="Screenshot ${index+1}" aria-pressed="${chosen.includes(shot.id)}">${shot.thumbnail?`<img loading="lazy" crossorigin="anonymous" src="${e(shot.thumbnail)}" alt=""/>`:''}<span>Screenshot ${index+1}</span>${chosen.includes(shot.id)?icon('check'):''}</button>`).join('')}</div>${!shots?'<p class="subtle">Loading Steam screenshots...</p>':!shots.length?'<p>No Steam screenshots are available for this game.</p>':''}</section>`;
}
function heroPoint(game:Game):[number,number]{
  const automatic=automaticHeroFocus.get(game.id);
  return heroFocusDrafts.get(game.id)||game.heroFocus||(automatic&&automatic.source===game.hero?automatic.point:[.5,.3]);
}
function heroFocusEditor(game:Game){
  if(!game.hero)return '';
  const point=heroPoint(game);
  return `<section class="glass-section hero-framing-editor"><div class="section-heading"><h2>Hero Framing</h2><span class="framing-state">${heroFocusDrafts.has(game.id)?'Unsaved framing':game.heroFocus?'Desktop framing':'Automatic framing'}</span></div><p>Keep your subject in view as the header gets shorter.</p><button id="hero-focal-preview" class="hero-focal-preview" data-focal-editor aria-label="Adjust hero framing" aria-pressed="${Boolean(heroAdjustment)}" aria-describedby="hero-framing-help"><img src="${e(game.hero)}" alt="Hero framing preview"/><i class="focal-point" aria-hidden="true"></i><span class="framing-preview-action">${icon('sliders')}<span class="framing-action-label">${heroAdjustment?'Done adjusting':'Adjust framing'}</span></span></button><div class="hero-framing-controls"><div class="hero-focus-sliders">${['Horizontal','Vertical'].map((axis,index)=>`<label class="library-size"><span>${axis}</span><input type="range" id="hero-focus-${index}" data-hero-focus="${index}" min="0" max="100" step="1" value="${Math.round(point[index]*100)}" aria-label="${axis} hero focal point"/><output for="hero-focus-${index}">${Math.round(point[index]*100)}%</output></label>`).join('')}</div><div class="operation-actions"><button class="quiet" data-action="reset-hero-framing">Use Desktop framing</button><button class="primary" data-action="save-hero-framing" ${!backend.enabled||!heroFocusDrafts.has(game.id)?'disabled':''}>Review hero framing</button></div></div><p id="hero-framing-help" class="framing-help">${framingHelp()}</p></section>`;
}
function framingHelp(){
  if(controller)return heroAdjustment?`D-pad moves the focal point. ${controllerGlyph(controllerFamily(),0)} Done ${controllerGlyph(controllerFamily(),1)} Cancel`:`${controllerGlyph(controllerFamily(),0)} Adjust on the preview. Sliders also work with the D-pad.`;
  return heroAdjustment?'Arrow keys move the focal point. Enter finishes; Escape cancels.':'Select the preview to adjust with arrow keys, or use the sliders.';
}
function updateHeroPoint(point:[number,number]){
  const game=selectedGame();if(!game)return;
  heroFocusDrafts.set(game.id,point.map(value=>Math.max(0,Math.min(1,value))) as [number,number]);
  applyHeroFraming();applyDetailsAccent();
  const status=app.querySelector('.framing-state');if(status)status.textContent='Unsaved framing';
  const save=app.querySelector<HTMLButtonElement>('[data-action="save-hero-framing"]');if(save)save.disabled=!backend.enabled;
}
function finishHeroAdjustment(cancel=false){
  if(!heroAdjustment)return;
  const state=heroAdjustment;heroAdjustment=undefined;
  if(cancel){if(state.previous)heroFocusDrafts.set(state.game,state.previous);else heroFocusDrafts.delete(state.game);}
  applyHeroFraming();applyDetailsAccent();
  const button=app.querySelector<HTMLButtonElement>('[data-focal-editor]');button?.setAttribute('aria-pressed','false');
  const label=button?.querySelector('.framing-action-label');if(label)label.textContent='Adjust framing';
  const help=app.querySelector('#hero-framing-help');if(help)help.innerHTML=framingHelp();
  const game=selectedGame(),status=app.querySelector('.framing-state');if(game&&status)status.textContent=heroFocusDrafts.has(game.id)?'Unsaved framing':game.heroFocus?'Desktop framing':'Automatic framing';
  const save=app.querySelector<HTMLButtonElement>('[data-action="save-hero-framing"]');if(save)save.disabled=!backend.enabled||!game||!heroFocusDrafts.has(game.id);
}
function applyHeroFraming(){
  const game=selectedGame(),hero=app.querySelector<HTMLElement>('.details-hero'),image=hero?.querySelector<HTMLImageElement>('.details-hero-image');
  if(!game||!hero||!image?.naturalWidth)return;
  const source=image.currentSrc||image.src,key=game.id+'|'+source;
  if(!game.heroFocus&&automaticHeroFocus.get(game.id)?.source!==game.hero&&!loadingHeroFocus.has(key)){
    loadingHeroFocus.add(key);
    void analyzeHeroFocus(image).then(point=>{loadingHeroFocus.delete(key);if(game.hero!==source)return;automaticHeroFocus.set(game.id,{source,point});if(image.isConnected&&selectedId===game.id){applyHeroFraming();applyDetailsAccent();}});
  }
  const point=heroPoint(game),crop=heroCrop(hero.clientWidth,hero.clientHeight,image.naturalWidth,image.naturalHeight,point);
  image.style.objectPosition=`${crop.x}% ${crop.y}%`;
  const preview=app.querySelector<HTMLElement>('.hero-focal-preview'),previewImage=preview?.querySelector<HTMLImageElement>('img');
  if(preview&&previewImage){
    const expanded=parseFloat(app.querySelector<HTMLElement>('.details-page')?.style.getPropertyValue('--hero-expanded')||'270');
    preview.style.aspectRatio=String(hero.clientWidth/expanded);
    const framing=heroCrop(preview.clientWidth,preview.clientHeight,image.naturalWidth,image.naturalHeight,point);
    previewImage.style.objectPosition=`${framing.x}% ${framing.y}%`;
    preview.style.setProperty('--focal-x',framing.markerX+'%');preview.style.setProperty('--focal-y',framing.markerY+'%');
    for(let index=0;index<2;index++){const field=app.querySelector<HTMLInputElement>(`#hero-focus-${index}`);if(field){field.value=String(Math.round(point[index]*100));const output=field.nextElementSibling as HTMLOutputElement;if(output)output.value=field.value+'%';}}
  }
}
function detailAppearance(game: Game) {
  const accent = detailsAccent(game);
  return `<section class="glass-section game-accent-section"><h2>Game Accent</h2><p>${game.accent ? `Saved in rtxForge · ${e(game.accent.toUpperCase())}` : game.artworkAccent ? 'Automatic color from your library poster.' : 'No artwork color available. This game uses neutral surfaces and controls.'}</p><div class="inner-card"><div class="field color-field"><span><strong>Game accent</strong><small>Preview a color, then save it to Desktop and Game Mode.</small></span>${colorPicker('game-accent-color',gameAccentDrafts.get(game.id)||accent||'#b4b4b4',game.art||'',!backend.enabled)}</div>${surfaceTintControls(appearance.accentMode,appearance.tintStrength)}</div><div class="operation-actions extra-actions"><button class="quiet" data-action="reset-game-accent" ${!backend.enabled||!game.accent?'disabled':''}>Use artwork color</button></div></section>${heroFocusEditor(game)}${screenshotChoices(game)}${artworkEditor(game)}`;
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
    if (page.clientWidth <= 760) { page.style.setProperty('--hero-contrast-visibility','1');page.style.setProperty('--hero-title-bright','100%');page.dataset.collapsing='false';page.dataset.heroCompact='false';page.dataset.heroScrolled='false';page.dataset.heroSummary='true';applyHeroFraming();applyDetailsAccent();return; }
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
    page.style.setProperty('--hero-contrast-visibility',String(Math.max(0,1-progress/.32)**2));
    page.style.setProperty('--hero-title-bright',Math.max(0,1-progress/.45)*100+'%');
    page.style.setProperty('--identity-left',(removed>0?94:30)+'px');
    page.style.setProperty('--back-top',(18+24*progress)+'px');
    page.dataset.heroScrolled=String(removed>0);
    page.dataset.heroCompact=String(progress>=.65);
    page.dataset.heroSummary=String(progress<.3);
    applyHeroFraming();
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
  return `<details class="schema-controls"><summary>${icon('sliders')}Advanced feature controls</summary><p class="subtle">The same control schema used by the overlay and existing Game Mode. Runtime units are preserved.</p>${schema.groups.filter(group => group.name !== 'Frame generation').map(group => {
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
  if (detailsSection === 'files') {
    const inventory=fileInventories.get(game.id);
    const files=inventory?.files || [];
    const byComponent=files.reduce((groups,file)=>{
      const copies=groups.get(file.title)||[];copies.push(file);groups.set(file.title,copies);return groups;
    },new Map<string,DlssInventory["files"]>());
    const cards=[...byComponent].map(([title, copies])=>`<article class="inner-card dlss-file-card">
      <h3>${e(title)}</h3>
      <ul>${[...new Map(copies.map(file=>{
        const name=file.path.split('/').at(-1)||file.title;
        return [name+'|'+file.current,{name,current:file.current}];
      })).values()].map(({name,current})=>`<li><strong class="dll-name">${e(name)}</strong><span class="hero-pill">${e(current==='Unknown'?'Version unavailable':current)}</span></li>`).join('')}</ul>
    </article>`).join('');
    return `<section class="glass-section"><h2 class="panel-heading">${icon('file')}Installed DLSS Files</h2>
      ${cards?`<div class="dlss-file-grid">${cards}</div>`:`<p>${e(inventory?.blocked || (inventory ? 'No supported DLSS DLLs were found.' : backend.enabled || !('__TAURI_INTERNALS__' in window) ? 'Checking installed DLLs…' : 'File inventory is available in the installed app.'))}</p>`}</section>
      <section class="glass-section"><h2 class="panel-heading">${icon('wrench')}File Management</h2><div class="package-columns detail-card-row">${actionCard('Update DLSS','Update older DLSS files. Backups are kept for restoration.','data-operation="update-dlss"','Update')}${actionCard('Restore original DLSS files','Review the existing updater backups for this game.','data-contract="dlss_restore_review"','Restore')}</div></section>`;
  }
  if (detailsSection === 'notes') return `<section class="glass-section"><h2>Your Notes</h2><p>Kept with this game in rtxForge. Included in bug reports when you choose.</p><label class="notes-field"><span>Notes</span><textarea id="game-notes" rows="10" ${!backend.enabled||!notesLoaded.has(game.id)?'disabled':''}>${e(noteDrafts.get(game.id) ?? game.notes ?? '')}</textarea></label><button class="primary extra-actions" data-action="save-notes" ${!backend.enabled||!notesLoaded.has(game.id)?'disabled':''}>Save Notes</button></section>`;
  return `<section class="glass-section"><h2>Tools</h2><div class="tool-utilities">${actionCard('Game Folder',game.path,'data-action="copy-game-path"','Copy location')}${actionCard('Diagnose NR','Read saved NR settings, runtime hashes and log evidence.','data-contract="diagnose"','Diagnose')}</div></section>
  ${splitToolCard(game)}<section class="glass-section reshade-tools"><h2>ReShade &amp; add-ons</h2><p>Manage ReShade, RenoDX, shaders and presets for this game.</p><div class="inner-card tool-options">
    <div class="detail-action-row"><div><strong>ReShade runtime</strong><p>Install the official runtime or import your own package, shaders or preset.</p></div><div class="operation-actions"><button class="primary" data-action="official-reshade" ${!backend.enabled?'disabled':''}>Install ReShade</button><button class="quiet" data-tool-kind="reshade-import" ${!backend.enabled?'disabled':''}>Import package&hellip;</button></div></div>
    <div class="detail-action-row"><div><strong>RenoDX</strong><p>Install the matching game add-on and its required ReShade files.</p></div><div class="operation-actions"><button class="quiet" data-contract="hdr_review" ${!backend.enabled?'disabled':''}>Install RenoDX</button><button class="quiet" data-contract="hdr_review" data-remove="true" ${!backend.enabled?'disabled':''}>Remove RenoDX</button><button class="quiet" data-tool-kind="hdr-custom" ${!backend.enabled?'disabled':''}>Use custom add-on&hellip;</button></div></div>
    <div class="detail-action-row"><div><strong>Other add-ons</strong><p>Choose a ReShade .addon64 file.</p></div><button class="quiet" data-tool-kind="addon" ${!backend.enabled?'disabled':''}>Choose add-on&hellip;</button></div>
  </div>${toolImportOpen?`<div class="inner-card tool-import"><label class="field"><span><strong>${extraKind==='hdr-custom'?'Custom RenoDX add-on':extraKind==='addon'?'Add-on file':'ReShade package'}</strong></span><input id="extra-source" type="text" value="${e(extraSource)}" ${!backend.enabled?'disabled':''}/></label><button class="primary" data-action="review-extra" ${!backend.enabled?'disabled':''}>Review installation</button></div>`:''}
  <div class="operation-actions extra-actions"><button class="quiet" data-action="extra-records" ${!backend.enabled?'disabled':''}>Recovery records</button></div><div class="tool-records">${extraRecords.map((record,index)=>`<button class="quiet" data-extra-restore="${index}" ${!backend.enabled?'disabled':''}>Restore ${e(record.title||record.kind)}</button>`).join('')}</div></section>`;
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
  const current = mergeOverlay({...snapshot?.preferences,...sharedPreferences},overrides[identity],gameOverlayDrafts.get(game.id));
  return `<div class="overlay-game-note"><p>${overrides[identity] ? 'This game has its own overlay settings.' : 'This game uses the app’s overlay settings.'}</p>${!sharedPreferences&&backend.enabled ? '<button class="quiet" data-action="load-settings">Load settings</button>' : ''}</div>${settingsContent({category:'overlay',preferences:current,changes:{},glassDefaults:snapshot?.overlayDefaults||{},enabled:backend.enabled&&Boolean(sharedPreferences),platform:snapshot?.platform,icon,gridConnected,games:snapshot?.games||[],game,reportSelection:supportSelection})}${current.overlay_renderer==='optiscaler'?`<section class="glass-section"><h3>Use native menus for this game</h3><p>The review will keep the original menus available. Other games keep their choices.</p><label><input id="overlay-make-default" type="checkbox"/> Make this my default</label></section>`:''}<div class="operation-actions extra-actions"><button class="primary" data-action="save-game-overlay" ${!backend.enabled || !sharedPreferences ? 'disabled' : ''}>Review this game's preferences</button><button class="quiet" data-action="inherit-game-overlay" ${!backend.enabled || !sharedPreferences ? 'disabled' : ''}>Use app settings</button><button class="quiet" data-action="apply-game-overlay" ${!backend.enabled || !sharedPreferences ? 'disabled' : ''}>Review overlay update</button></div>`;
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
  const content=app.querySelector<HTMLElement>('.operation-modal, #content:not(.shell[inert] #content)');if(content){
    for(const key of ['--accent','--accent-ink','--primary-ink'])content.style.removeProperty(key);
    if(accent){content.style.setProperty('--accent',accent);content.style.setProperty('--accent-ink',appearance.theme==='light'?'var(--ink)':accent);content.style.setProperty('--primary-ink',selectionInk(accent));}
    const stepColor=operation.targets?.length===1?detailsAccent(operation.targets[0]):null;
    content.style.setProperty('--flow-step-color',stepColor||appAccent());
    content.style.setProperty('--flow-step-ink',selectionInk(stepColor||appAccent()));
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
  if(state.method==='overlay_status'&&state.stage==='done')return heading('Overlay Status','Installed versions and recorded update times.')+overlayStatusView(state.result as OverlayStatus);
  if(state.kind)return operationFlow(state,snapshot?.games||[],icon,startupSettingsView(),supportedReviews(review),
    state.kind === 'install' && review && state.split && splitCatalog?.enabled === true && (review.rows?.length || review.supported?.length)
      ? splitInstallOptions(state.split) : '');
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
  return `<fieldset class="supported-reviews"><legend>Optional supported features</legend>${review.supported.map(offer => `<label class="supported-choice inner-card"><input type="checkbox" data-supported-token="${e(offer.token)}" ${operation?.chosenOffers?.has(offer.token) ? 'checked' : ''} /><span><strong>Include ${offer.nr && offer.mfg ? 'NR + MFG' : offer.nr ? 'NR only' : 'MFG only'}</strong><small>${e(offer.reason)}</small><small>${offer.rows.map(row => e(row.name)).join(' · ')}</small></span></label>`).join('')}</fieldset>`;
}
function syncReviewConfirm() {
  const state = operation, button = app.querySelector<HTMLButtonElement>('[data-action="confirm-operation"]');
  if (!state?.review || !button) return;
  const selectedOffers=[...app.querySelectorAll<HTMLInputElement>('[data-supported-token]:checked')].map(node=>state.review!.supported?.find(offer=>offer.token===node.dataset.supportedToken));
  const count=new Set([...(state.review.rows||state.review.items||[]),...selectedOffers.flatMap(offer=>offer?.rows||[])].map(row=>String(row.game||row.name))).size;
  const hasChanges = count>0;
  const summary=app.querySelector('.flow-summary h2');if(summary)summary.textContent=count?`${count} game${count===1?'':'s'} ready`:'Nothing ready yet';
  const acknowledged = !state.review.trust || Boolean(app.querySelector<HTMLInputElement>('#review-trust')?.checked);
  button.disabled = !hasChanges || !acknowledged || !!state.split?.pending || !!state.split?.error;
}

function overlayReportRows(report: Record<string,unknown>, key: string): Record<string,unknown>[] {
  const rows = report[key];
  return Array.isArray(rows) ? rows : [];
}

function overlayRepairGames(report: Record<string,unknown>) {
  const paths = new Set(overlayReportRows(report,'blocked').filter(item=>item.action==='repair' && typeof item.game==='string')
    .map(item=>pathKey(String(item.game))));
  return (snapshot?.games||[]).filter(game=>paths.has(pathKey(game.path)));
}

function showOverlayReport(report: Record<string,unknown>) {
  const title = 'Review Overlay Update';
  const updated = overlayReportRows(report,'updated_games');
  const skipped = overlayReportRows(report,'skipped');
  const attention = overlayReportRows(report,'blocked');
  const blocked: Record<string,unknown>[] = attention.map(item=>({...item,badge:item.action==='repair'?'Needs repair':item.action==='retry'?'Try again':'Check needed'}));
  if(report.error) blocked.push({title:'Overlay update',detail:String(report.error),badge:'Check needed'});
  const rows = [
    ...updated.map(item=>({...item,game:item.game||item.target,detail:'Overlay updated',badge:'Updated'})),
    ...skipped.map(item=>({...item,badge:item.badge||'Current'})),
  ];
  const repair = overlayRepairGames(report);
  const retry = report.status==='pending' && attention.some(item=>!item.action || item.action==='retry');
  const origin = view==='operation' ? operation?.origin : view;
  operation = {stage:'review',title,kind:'overlay-update-report',execute:'inspect',origin,
    review:{token:'',title,rows,blocked,summary:`${Number(report.updated)||0} updated · ${skipped.filter(item=>!item.badge).length} already current`},
    overlayReportAction:backend.enabled ? repair.length?'Fix':retry?'Try again':undefined : undefined};
  setView('operation');
}

async function fixOverlayReport() {
  const report = snapshot?.overlayReport;
  const state = operation;
  if (!report || !state?.overlayReportAction || !backend.enabled) return;
  if (state.overlayReportAction==='Try again') {
    state.stage='running'; render();
    try {
      const result = await engineRequest<Record<string,unknown>>('overlay_refresh_retry');
      if (result.status==='busy') throw new Error('An overlay update is already running. Try again when it finishes.');
      if (snapshot) snapshot.overlayReport = result;
      showOverlayReport(result);
    } catch (problem) {
      state.stage='error'; state.error=problem instanceof Error?problem.message:'Overlay update failed.'; render();
    }
    return;
  }
  state.stage='checking'; render();
  try {
    const games = overlayRepairGames(report);
    const rows: EngineRow[] = [];
    for (const game of games) {
      const matching = (await getEngineRows(game)).find(row=>pathKey(row.game)===pathKey(game.path));
      if (operation!==state || state.dismissed) return;
      if (matching?.installed && !matching.blocked && matching.installed_on !== (snapshot?.platform==='Windows'?'linux':'windows')) rows.push(matching);
    }
    if (operation!==state || state.dismissed) return;
    if (!rows.length) throw new Error('Refresh the library to verify which games can be repaired.');
    await withOperation('Review Feature Repair','prepare_routes',{rows,operation:'repair',
      mode:String(snapshot?.defaults.default_profile||'nr-mfg')},'execute_routes');
    if (operation?.kind==='repair' && operation.stage==='review') operation.refreshOverlaysAfterRepair=true;
  } catch (problem) {
    if (operation!==state || state.dismissed) return;
    state.stage='error'; state.error=problem instanceof Error?problem.message:'Could not prepare repairs.'; render();
  }
}
function reportForm(result: unknown) {
  const draft = result as ReportDraft;
  return `<h2>Your report</h2><p>Correct the engine’s recorded facts and add what you observed. You review redacted contents before a local ZIP is saved.</p>${draft.reports.map(report => `<h3 class="game-title">${e(report.name)}</h3><div class="inner-card">${draft.fields.map(field => `<label class="field"><span><strong>${e(field.label)}</strong>${field.required ? '<small>Required</small>' : ''}</span>${field.choices.length ? `<select data-report-id="${report.id}" data-report-field="${field.id}"><option value="">Choose…</option>${field.choices.map(choice => `<option ${choice === (reportEdits[report.id]?.[field.id] ?? report.fields[field.id]) ? 'selected' : ''}>${e(choice)}</option>`).join('')}</select>` : `<input type="text" data-report-id="${report.id}" data-report-field="${field.id}" value="${e(reportEdits[report.id]?.[field.id] ?? report.fields[field.id])}" maxlength="${field.max || 10000}" />`}</label>`).join('')}</div>`).join('')}<label class="trust-choice"><input type="checkbox" id="report-logs" />Include this session’s logs</label><label class="trust-choice"><input type="checkbox" id="report-notes" />Include my game notes</label><button class="primary" data-action="review-report">Review redacted report</button>`;
}
async function withOperation(title: string, method: string, params: Record<string, unknown>, execute = 'run') {
  const origin = view === 'operation' ? operation?.origin || 'details' : view;
  const kind=method==='prepare_routes'?String(params.operation||'apply'):method==='prepare_dlss'?'update-dlss':method==='nr_review'?(params.remove?'remove-nr-addons':'install-nr-addons'):execute==='run'?'review':undefined;
  const targets=kind?(snapshot?.games||[]).filter(game=>((params.rows||(params.row ? [params.row] : [])) as EngineRow[]).some(row=>pathKey(row.game)===pathKey(game.path))):undefined;
  const state = { stage: 'checking' as const, title, execute, origin, method,kind,targets, changedKeys: Object.keys((params.changes || {}) as object) };
  operation = state; setView('operation');
  try {
    if (kind === 'install') await loadSplitCatalog().catch(() => { splitCatalog = undefined; });
    const result = await engineRequest<Review>(method, params, progress => { if (operation) { operation.progress = progress; render(); } });
    if (!operation || operation !== state || operation.dismissed) {
      if (result?.token) await engineRequest(execute === 'execute_routes' ? 'discard_routes' : execute === 'run' ? 'discard' : 'discard_operation', execute === 'run' ? { token: result.token } : { tokens: [result.token] });
      return;
    }
    if (result?.token && execute !== 'inspect-package') { operation.review = result; operation.stage = 'review'; operation.title = result.title || title;
      if (kind === 'install' && splitCatalog?.enabled === true) operation.split = { picker: newPicker(), revision: 0, pending: false, error: '', rows: [], open: false }; }
    else { if (kind==='review') operation.kind=undefined; operation.stage = 'done'; operation.result = result; }
  } catch (problem) { if (operation === state && !operation.dismissed) { operation.stage = 'error'; operation.error = problem instanceof Error ? problem.message : 'The engine could not complete the request.'; } else return; }
  render(); document.querySelector<HTMLElement>('#page-title')?.focus();
}
async function loadSplitCatalog() {
  splitCatalog = await engineRequest<Catalog>('nr_catalog');
}
function splitInstallOptions(split: NonNullable<NonNullable<typeof operation>['split']>) {
  const chosen = operation?.chosenOffers || new Set<string>();
  const optional = new Set((operation?.review?.supported || []).filter(offer => !chosen.has(offer.token))
    .flatMap(offer => offer.rows.map(row => pathKey(String(row.game || '')))));
  const rows = split.rows.filter(row => !optional.has(pathKey(String(row.game || ''))));
  return `<details id="split-install-options" class="split-section inner-card" ${split.open ? 'open' : ''}>
    <summary>Split Render <span class="subtle">· Optional</span></summary>
    <p>Review the DLSS 5 NR setup each game will receive after its main package installs.</p>
    ${splitPicker(splitCatalog!, split.picker, 'install')}
    <div class="split-results">${split.pending || split.error ? `<p role="status">${e(split.error || 'Preparing Split Render…')}</p>`
      : rows.map(row => reviewRow(row, snapshot?.games || [], icon, !row.reason)).join('')}</div>
  </details>`;
}
async function reviewSplitChoices() {
  const state = operation, split = state?.split;
  if (!state?.review || state.stage !== 'review' || !split || !splitCatalog) return;
  const choice = splitChoice(splitCatalog, split.picker), revision = ++split.revision;
  split.pending = true;
  split.error = '';
  split.rows = [];
  render();
  await new Promise(resolve => setTimeout(resolve, 180));
  if (operation !== state || state.stage !== 'review' || revision !== split.revision || view !== 'operation') return;
  try {
    const result = await engineRequest<{rows: Record<string, unknown>[]}>('split_render_routes_review', { token: state.review.token, choice, revision });
    if (operation === state && revision === split.revision) split.rows = result.rows;
  } catch (problem) {
    if (operation === state && revision === split.revision)
      split.error = (problem instanceof Error ? problem.message : 'Split Render could not be reviewed.') + ' Change the setup or choose None to continue.';
  } finally {
    if (operation === state && revision === split.revision) {
      split.pending = false;
      if (view === 'operation') render();
    }
  }
}
function visibleSplitGames() {
  const choice = splitCatalog && splitChoice(splitCatalog, packagePicker);
  return (snapshot?.games || []).filter(game => ((!splitRemove && !choice) || splitMatches.has(game.id)) && game.name.toLowerCase().includes(splitQuery.trim().toLowerCase()))
    .sort((left, right) => left.name.localeCompare(right.name));
}
function splitGamePicker() {
  const games = visibleSplitGames(), query = splitQuery.trim();
  const empty = splitMatchError || (splitMatching ? (splitRemove ? 'Finding installed setups…' : 'Checking compatibility…') :
    !snapshot?.games.length ? 'There are no scanned games in your library.' :
    splitRemove && !splitMatches.size ? 'No scanned games have Split Render installed.' :
    !splitRemove && splitCatalog && splitChoice(splitCatalog, packagePicker) && !splitMatches.size ? 'No games can use this setup.' :
    query ? 'No games match your search.' : 'No games can use this setup.');
  return `<section class="split-games">
    <div class="split-games-toolbar">
      <label class="split-search">${icon('search')}<input id="split-game-search" type="search" aria-label="Search games" placeholder="Search games" value="${e(splitQuery)}"></label>
      <div class="operation-actions">
        <button class="quiet" data-action="split-select-all" ${splitMatching || !games.some(game => !splitSelected.has(game.id)) ? 'disabled' : ''}>${icon('check')}${query ? 'Select all results' : 'Select all'}</button>
        <button class="quiet" data-action="split-clear" ${splitSelected.size ? '' : 'disabled'}>${icon('minus')}Clear selection</button>
      </div>
    </div>
    <p class="split-selection-count subtle" role="status">${splitSelected.size} selected${splitMatchNotice ? ' · ' + e(splitMatchNotice) : ''}</p>
    <div class="split-game-list" aria-label="Games">${splitMatching || splitMatchError || !games.length ? `<p role="status">${e(empty)}</p>` : games.map(game => {
      const accent = detailsAccent(game) || '#b4b4b4', art = game.capsule || game.art;
      return `<label class="nr-target-choice" style="--game-accent:${e(accent)}">
        <input type="checkbox" data-nr-target="${e(game.id)}" aria-label="${e(game.name)}" ${splitSelected.has(game.id) ? 'checked' : ''} />
        <span class="selection-check" aria-hidden="true">${icon('check')}</span>
        <span class="flow-thumbnail">${art ? `<img src="${e(art)}" alt=""/>` : icon('controller')}</span>
        <span class="split-game-title"><strong>${e(game.name)}</strong><small>${e(splitMatches.get(game.id)?.summary || game.source)}</small></span>
      </label>`;
    }).join('')}</div>
  </section>`;
}
function nrPackageCard() {
  if (!backend.enabled) return '';
  const catalog = splitCatalog;
  const enabled = catalog?.enabled === true;
  const choice = enabled && splitChoice(catalog, packagePicker);
  return `<section class="glass-section"><h2>Split Render</h2>
    <p>${enabled ? e(splitRenderDescription) : 'New setups are paused while performance and image quality are improved.'}</p>
    <button class="quiet" data-action="open-split-removal">${icon('minus')}Remove Split Render</button>
    ${enabled && !splitRemove ? `<details id="split-packages" ${splitPackageOpen ? 'open' : ''}><summary>Choose games</summary>
      <div class="split-layout"><section><h3>${icon('gear')} Setup</h3>${splitPicker(catalog, packagePicker, 'packages')}</section>
      ${splitGamePicker()}</div>
      <button class="primary" data-action="review-nr-addons" ${splitMatching || !choice || !splitSelected.size ? 'disabled' : ''}>Review selection</button>
    </details>` : ''}</section>`;
}
function splitRemovalPicker() {
  return `<div class="split-removal-flow">
    <header><h1 id="page-title" tabindex="-1">Remove Split Render</h1>
      ${flowSteps('remove-nr-addons','start',true)}
      <p>Choose the games to review. Close any selected games before removing their setup.</p></header>
    ${splitGamePicker()}
    <footer class="operation-actions flow-actions">
      <button class="quiet" data-action="close-split-removal">Cancel</button>
      <button class="primary" data-action="review-nr-addons" ${splitMatching || !splitSelected.size ? 'disabled' : ''}>${icon('file')}Review selection</button>
    </footer>
  </div>`;
}
async function matchSplitGames() {
  const remove = splitRemove;
  if (!remove && splitCatalog?.enabled !== true) return;
  const choice = remove ? null : splitChoice(splitCatalog!, packagePicker);
  const revision = ++splitMatchRevision;
  splitMatching = remove || !!choice;
  splitMatchError = '';
  splitMatchNotice = '';
  if (!splitMatching) splitMatches.clear();
  if (view === 'packages') render();
  if (!splitMatching) return;
  await new Promise(resolve => setTimeout(resolve, 160));
  if (revision !== splitMatchRevision) return;
  try {
    const games = snapshot?.games || [], candidates: { game: Game; row: EngineRow }[] = [];
    for (const game of games) {
      if (revision !== splitMatchRevision) return;
      const row = engineRows.find(row => pathKey(row.game) === pathKey(game.path))
        || (await getEngineRows(game)).find(row => pathKey(row.game) === pathKey(game.path));
      if (row) candidates.push({ game, row });
    }
    if (revision !== splitMatchRevision) return;
    const results = await engineRequest<{index: number; summary: string}[]>('nr_match', { rows: candidates.map(item => item.row), choice, remove });
    if (revision !== splitMatchRevision) return;
    splitMatches = new Map(results.map(({index, summary}) => [candidates[index].game.id, { row: candidates[index].row, summary }]));
    const previousCount = splitSelected.size;
    for (const id of splitSelected) if (!splitMatches.has(id)) splitSelected.delete(id);
    const removed = previousCount - splitSelected.size;
    if (removed) splitMatchNotice = removed === 1 ? '1 game was deselected because it cannot use this setup.'
      : `${removed} games were deselected because they cannot use this setup.`;
  } catch (problem) {
    if (revision !== splitMatchRevision) return;
    splitMatchError = problem instanceof Error ? problem.message : 'Compatibility could not be checked.';
    splitMatches.clear();
    splitSelected.clear();
  } finally {
    if (revision === splitMatchRevision) {
      splitMatching = false;
      if (view === 'packages') render();
    }
  }
}
async function reviewNrPackage() {
  const choice = !splitRemove && splitCatalog?.enabled === true ? splitChoice(splitCatalog, packagePicker) : null;
  const rows = [...splitSelected].flatMap(id => splitMatches.get(id)?.row || []);
  if (!splitMatching && (splitRemove || choice) && rows.length && view === 'packages')
    await withOperation(splitRemove ? 'Review Split Render removal' : 'Review Split Render', 'nr_review',
      { rows, choice, remove: splitRemove });
}
function feederSelection(tool: NonNullable<typeof splitTool>) {
  const settings = tool.catalog.feeder_character;
  if (!settings?.available) return;
  const pass = settings.options.find(option => option.number === tool.feederPass) ?? settings.options[0];
  if (!pass) return;
  const character = tool.feederRole ?? pass.character;
  const inputSkin = tool.feederSkin ?? pass.skin;
  const skin = inputSkin < 0 ? -1 : inputSkin;
  const tuningChanged = character !== pass.character || (character && Math.abs(skin - pass.skin) > .005);
  return { settings, pass, character, inputSkin, skin, tuningChanged,
    changed: tuningChanged || pass.number > settings.passes };
}
function feederCharacterCard(tool: NonNullable<typeof splitTool>) {
  const chosen = feederSelection(tool);
  return `<section class="glass-section split-section"><h2>${icon('cpu')} Feeder NR passes</h2>
    <p>Each pass processes the whole frame. Character enables the mask so Skin detail can affect detected people.</p>
    ${chosen ? feederPassEditor(tool, chosen) : `<p role="status">${e(tool.catalog.feeder_character?.reason || '')}</p>`}</section>`;
}
function feederPassEditor(tool: NonNullable<typeof splitTool>, chosen: NonNullable<ReturnType<typeof feederSelection>>) {
  const { settings, pass, character, inputSkin, skin, tuningChanged, changed } = chosen;
  const extra = pass.number > settings.passes;
  const locked = tool.busy || !!settings.reason;
  const notice = extra ? `Full-frame passes · ${settings.passes} → ${pass.number}. Extra passes can lower frame rate.` :
    settings.nr_enabled ? 'Saves for the next launch.' : 'Saves for the next launch. Enable NR in the in-game Feeder panel to see the effect.';
  const inheritance = pass.inherited && tuningChanged ? 'Copies the main pass’s model settings before assigning this pass its own settings.' :
    pass.number === 1 ? 'Passes that follow the main settings also use this role.' : '';
  return `<fieldset class="feeder-choices"><legend>Pass · ${settings.passes} of ${settings.options.length} configured</legend>
    <div class="feeder-passes">${settings.options.map(option => `<button type="button" data-feeder-pass="${option.number}"
      aria-pressed="${option.number === pass.number}" ${locked ? 'disabled' : ''}>
      <span>${icon(option.character ? 'eye' : 'cpu')} Pass ${option.number}</span>
      <small>${option.character ? 'Character' : 'Standard'}${option.number > settings.passes ? ' · Inactive' : ''}</small></button>`).join('')}</div>
    </fieldset>
    <fieldset class="feeder-choices"><legend>Role</legend><div class="feeder-roles">
      <button type="button" data-feeder-role="standard" aria-pressed="${!character}" ${locked ? 'disabled' : ''}>${icon('cpu')} Standard</button>
      <button type="button" data-feeder-role="character" aria-pressed="${character}" ${locked ? 'disabled' : ''}>${icon('eye')} Character</button>
    </div></fieldset>
    ${inheritance ? `<p class="subtle">${e(inheritance)}</p>` : ''}
    ${character ? `<label class="field feeder-skin" for="feeder-skin"><span><strong>${icon('sliders')} Skin detail</strong>
      <small>Selected · <output id="feeder-skin-output">${skin < 0 ? 'Stock' : e(skin.toFixed(2))}</output></small></span>
      <input id="feeder-skin" type="range" min="-1" max="1" step=".01" value="${e(inputSkin)}" ${locked ? 'disabled' : ''}></label>` : ''}
    <p class="subtle" role="status">${e(tool.feederMessage || settings.reason || notice)}</p>
    <button class="primary" data-action="feeder-character-apply" ${!locked && changed ? '' : 'disabled'}>${icon('check')} Save pass role</button>`;
}
async function applyFeederCharacter() {
  const tool = splitTool;
  const chosen = tool && feederSelection(tool);
  if (!tool || !chosen || tool.busy || chosen.settings.reason || !chosen.changed) return;
  const { settings, pass, character, skin } = chosen;
  tool.busy = true;
  tool.feederMessage = `Saving Pass ${pass.number}…`;
  render();
  try {
    const result = await engineRequest<{message: string}>('feeder_character_apply', {
      row: tool.row, stamp: settings.stamp, pass_number: pass.number, character, skin: character ? skin : null,
    });
    const game = selectedGame();
    if (view === 'details' && detailsSection === 'tools' && game?.id === tool.game) {
      await loadSplitTool(game);
      if (splitTool?.game === tool.game) {
        splitTool.feederPass = pass.number;
        splitTool.feederMessage = result.message;
      }
    }
    announce(result.message);
  } catch (problem) {
    tool.feederMessage = problem instanceof Error ? problem.message : 'Could not save the Feeder NR pass role.';
  } finally {
    tool.busy = false;
    if (view === 'details' && detailsSection === 'tools' && selectedId === tool.game) render();
  }
}
function splitToolCard(game: Game) {
  const tool = splitTool?.game === game.id ? splitTool : undefined;
  if (!tool || (!tool.installed && tool.catalog.enabled !== true)) return '';
  if (tool.catalog.feeder_character && !tool.installed) return feederCharacterCard(tool);
  return `<section class="glass-section split-section"><h2>${icon('sliders')} Split Render</h2><p>${e(splitRenderDescription)}</p>
    ${!backend.enabled ? '' : !tool ? `<p role="status">${e(splitToolError || 'Checking this game…')}</p>` :
      tool.installed ? `<p role="status">${e(tool.installedText)}</p>
      <button class="quiet" data-action="split-tool-remove" ${tool.busy ? 'disabled' : ''}>Remove Split Render</button>` :
      tool.catalog.blocked ? `<p role="status">${e(tool.catalog.blocked)}</p>` :
      `<p class="subtle">Not installed in this game.</p>${splitPresetSelect(tool.catalog, tool.picker)}
      <p role="status">${e(tool.reason || (tool.checked ? tool.verdict : 'Checking compatibility…'))}</p>
      <div class="operation-actions"><button class="primary" data-action="split-tool-install" ${tool.checked && !tool.reason && !tool.busy ? '' : 'disabled'}>Review Split Render</button>
      </div>
`}</section>`;
}
async function loadSplitTool(game: Game) {
  splitToolError = '';
  try {
    const row = (await getEngineRows(game)).find(row => pathKey(row.game) === pathKey(game.path));
    if (!row) throw new Error('This installation is unavailable to the engine.');
    const [catalog, status] = await Promise.all([
      engineRequest<Catalog>('nr_catalog', { row }), engineRequest<{installed: boolean; setup?: Setup; default?: Setup; changed?: string[]; error?: string}>('nr_status', { row }),
    ]);
    if (selectedId !== game.id || view !== 'details' || detailsSection !== 'tools') return;
    if (status.error) throw new Error(status.error);
    const picker = splitTool?.game === game.id ? splitTool.picker : newPicker(status.default ||
      (catalog.runtime_nr ? { character: { addon: 'shortfuse' } } : { environment: { addon: 'lecram' } }));
    if (picker.preset && !catalog.combos[picker.preset]) picker.preset = '';
    const addonName = (id: string) => id === catalog.runtime_nr?.id ? catalog.runtime_nr.name :
      catalog.addons.find(addon => addon.id === id)?.name || id;
    const installedSetup = status.setup || {};
    const installedModel = installedSetup.environment?.model || installedSetup.character?.model || 'new';
    const parts = Object.entries(installedSetup).map(([role, slot]) =>
      `${role === 'environment' ? 'Environment' : 'Character detail'}: ${addonName(slot.addon)}`);
    parts.push(catalog.runtime_nr ? `DLSS 5 model shared with ${catalog.runtime_nr.name}` :
      catalog.models.find(model => model.id === installedModel)?.label || installedModel);
    if (status.changed?.length) parts.push(`${status.changed.length} file(s) changed since install`);
    splitTool = { game: game.id, row, catalog, picker, installed: status.installed, installedText: 'Installed · ' + parts.join(' · '),
      checked: false, reason: '', verdict: '', revision: 0, busy: false };
    if (status.installed || catalog.blocked || catalog.enabled !== true) render();
    else await checkSplitTool();
  } catch (problem) {
    if (view === 'details' && selectedId === game.id && detailsSection === 'tools') {
      splitTool = undefined;
      splitToolError = problem instanceof Error ? problem.message : 'Split Render is unavailable for this game.';
      render();
    }
  }
}
async function checkSplitTool() {
  const tool = splitTool;
  if (!tool) return;
  const revision = ++tool.revision;
  tool.checked = false;
  tool.reason = '';
  render();
  try {
    const setup = activeSetup(tool.catalog, tool.picker);
    if (!Object.values(setup).some(slot => slot.addon !== 'optiscaler')) throw new Error('Choose an environment or character setup.');
    const check = await engineRequest<{ok: boolean; reason?: string; verified?: boolean; world?: string; skipped?: unknown[]}>('nr_check', { row: tool.row, setup });
    if (!check.ok) throw new Error(check.reason || 'This setup is unavailable for this game.');
    if (tool.revision === revision)
      tool.verdict = [check.world ? `${check.world} covers the environment.` : '',
        check.verified ? 'Available to review.' : 'Available to review · this pairing has not been verified on a test copy.',
        check.skipped?.length ? 'Some settings are left out because they have not been verified for this provider.' : ''].filter(Boolean).join(' ');
  } catch (problem) {
    if (tool.revision === revision) tool.reason = problem instanceof Error ? problem.message : 'This setup could not be checked.';
  } finally {
    if (splitTool === tool && tool.revision === revision) {
      tool.checked = true;
      if (view === 'details' && selectedId === tool.game && detailsSection === 'tools') render();
    }
  }
}
async function applySplitTool(action: string) {
  const tool = splitTool;
  if (!tool || tool.busy) return;
  const setup = activeSetup(tool.catalog, tool.picker);
  const remove = action === 'split-tool-remove';
  if (remove ? !tool.installed : !tool.checked || !!tool.reason) return;
  await withOperation(remove ? 'Remove Split Render' : 'Review Split Render', 'nr_review', { row: tool.row, setup, remove });
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
    if (kind === 'install') {
      const checkedAction = rows.some(row => featureOperation(row) === 'update')
        && (batch || !scope || rows.every(row => row.installed));
      if (checkedAction) kind = 'update';
      else if (scope) {
        const fresh = rows.filter(row => featureOperation(row) === 'install');
        rows.splice(0, rows.length, ...fresh);
      }
    }
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
    await withOperation(kind === 'update' ? 'Review Feature Updates' : 'Review '+kind,kind==='update-dlss'?'prepare_dlss':'prepare_routes',params,kind==='update-dlss'?'update_dlss':'execute_routes');
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
  return heading('Packages','Choose what rtxForge installs. Every game change is reviewed before it is applied.')+`<div class="package-columns"><section class="glass-section"><h2>NR packages</h2><p>Choose one for games with DLSS. Feeder and Vulkan packages are used automatically for the games they cover.</p><div class="package-options">${nr.length?nr.map(item=>packageCard(item,Boolean(item.automatic))).join(''):fallback.filter(item=>item.id==='skynizz').map(item=>packageCard(item as unknown as Record<string,unknown>)).join('')}</div></section><section class="glass-section"><h2>MFG packages</h2><p>Native NVIDIA frame generation for Skynizz NR.</p><div class="package-options">${mfg.map(([id,name,kind,summary])=>`<article class="inner-card package-option"><div><h3 class="game-title">${name}</h3><p class="version">${e(versions[id]||kind)}</p></div><p>${summary}</p><button class="quiet" data-mfg-default="${id}" ${!backend.enabled?'disabled':''}>Use with Skynizz NR</button></article>`).join('')}</div></section></div>${nrPackageCard()}<div class="package-columns package-sources"><section class="glass-section unified-packages"><h2>Unified packages</h2><p>NR and MFG together in one package.</p><div class="package-options">${unified.map(item=>packageCard(item as Record<string,unknown>)).join('')}</div></section><section class="glass-section package-policy"><h2>Your own package</h2><p>Inspect a ZIP archive and review its settings before using it. Instructions are never run.</p><label class="field"><span><strong>Archive path</strong></span><input id="package-source" value="${e(packageSource)}" ${!backend.enabled?'disabled':''}/></label><button class="quiet" data-action="inspect-package" ${!backend.enabled?'disabled':''}>Choose archive</button></section></div>`;
}

function extras() {
  const tool = (title:string,copy:string,action:string,caption:string,glyph:string) => `<article class="glass-section tool-card"><div class="tool-heading"><h2 class="panel-heading">${icon(glyph)}${title}</h2></div><p>${copy}</p><button class="quiet" data-action="${action}" ${!backend.enabled?'disabled':''}>${caption}</button></article>`;
  return heading('Extras','Tools for your whole library. Every game change is reviewed before it is applied.')+`<div class="extra-top-tools">${tool('Update the rtxForge Overlay','Bring the in-game overlay in your installed games up to date. Tuning and restore backups are kept.','overlay-package-review','Review overlay updates','sliders')}${tool('Update DLSS files','Replace older DLSS files across your library. Originals are backed up.','extras-dlss','Review games','download')}${tool('Undo previous changes','Restore the files from an earlier install, update or restore.','recoveries','Show changes','refresh')}</div>${tool('RenoDX','Install the matching RenoDX add-on, or choose a custom add-on for a game.','extras-hdr','Choose game','palette')}<div class="package-columns extras-bottom"><section class="glass-section"><h2>Global Settings</h2><p>Turn neural rendering or frame generation on or off, or set the multiplier, in every game with a package installed. Defaults for future installs stay the same.</p><div class="inner-card"><label class="field"><span><strong>Neural rendering</strong></span><select id="global-nr" ${!backend.enabled?'disabled':''}><option value="keep">Leave as is</option><option value="false">Off</option><option value="true">On</option></select></label><label class="field"><span><strong>Multi-Frame Generation</strong></span><select id="global-mfg" ${!backend.enabled?'disabled':''}><option value="keep">Leave as is</option><option value="0">Off</option>${[2,3,4,5,6].map(value=>`<option value="${value}">${value}×</option>`).join('')}<option value="-1">Follow game</option></select></label></div><button class="primary extra-actions" data-action="global-review" ${!backend.enabled?'disabled':''}>Review changes</button></section>${tool('App storage','Downloads, backups and caches rtxForge keeps. Clean up what no game needs.','storage-inventory','View usage','folder')}</div>`;
}
function toggle(id: string, title: string, description: string, on: boolean) {
  return `<div class="field"><span><strong id="${id}-label">${title}</strong><small id="${id}-help">${description}</small></span><button class="toggle" role="switch" aria-labelledby="${id}-label" aria-describedby="${id}-help" aria-checked="${on}" data-toggle="${id}"><span></span></button></div>`;
}
function settings() {
  if(backend.enabled&&steamAdded===undefined&&!steamChecking){steamChecking=true;void engineRequest<{added:boolean}>('steam_status').then(status=>{steamAdded=status.added;if(view==='settings')render();}).catch(()=>{steamAdded=false;}).finally(()=>{steamChecking=false;});}

  const markup = originalSettings();
  const start = markup.indexOf('<nav class="settings-tabs"');
  const end = markup.indexOf('</nav>',start)+6;
  return markup.slice(0,start)+`<div class="settings-workspace">${markup.slice(start,end)}<div class="settings-body">${markup.slice(end)}</div></div>`;
}
function originalSettings() {
  const menu = `<nav class="settings-tabs" aria-label="Settings sections">${settingsGroups.map(([label,sections],index) =>
    `<div class="settings-tab-group" role="group" aria-labelledby="settings-group-${index}"><span id="settings-group-${index}" class="settings-tab-caption">${e(label)}</span>${sections.map(([category,name,glyph]) =>
      `<button data-settings-category="${category}" aria-pressed="${settingsCategory === category}">${icon(glyph)}<span>${name}</span></button>`).join('')}</div>`).join('')}</nav>`;
  return heading('Settings', 'Make room for the way you play.') + menu + (settingsCategory !== 'appearance' ? sharedSettings() :
    appearanceSettings());
}
function appearanceSettings() {
  const group=(title:string,copy:string,body:string,extra='')=>`<section class="glass-section setting-group ${extra}"><h2>${title}</h2>${copy?`<p>${copy}</p>`:''}${body}</section>`;
  const select=(id:string,title:string,copy:string,options:[string,string][],value:string)=>`<label class="field"><span><strong>${title}</strong>${copy?`<small>${copy}</small>`:''}</span><select id="${id}">${options.map(([key,label])=>`<option value="${key}" ${value===key?'selected':''}>${label}</option>`).join('')}</select></label>`;
  const themes=surfaceCards(appearance.theme, "theme-choice", "Color theme", icon);
  const scale='__TAURI_INTERNALS__' in window?select('display-scale','Interface scale','Size of the interface on this display.',[['auto','Automatic'],...[100,125,130,150,175,200].map(n=>[String(n),n+'%'] as [string,string])],String(appearance.scale)):'';
  return `<div class="settings-groups appearance-groups">${group('Surface','Choose the glass material for Game Mode.',themes,'appearance')}${group('Main interface','Color for the main navigation, buttons and focus.',`<div class="inner-card">${select('app-accent-source','Accent','',accentSources.map(([key,label])=>[key,label]),appearance.accentSource)}${appearance.accentSource==='custom'?`<label class="field color-field"><span><strong>Custom accent color</strong></span><input type="color" id="accent-color" value="${appearance.accent}" aria-label="Custom accent color" /></label>`:''}<div class="background-field"><span><strong>Background</strong><small>Your image for the main Game Mode interface.</small></span><div class="background-picker"><div class="background-preview"><img src="${e(appearance.background||(appearance.theme==='light'?'/app-hero-light.png':'/app-hero-dark.png'))}" alt="Current Game Mode background"/></div><div class="background-actions"><button class="quiet" data-action="choose-background">Choose image…</button><button class="quiet" data-action="reset-background" ${appearance.background?'':'disabled'}>Use default</button></div><input type="file" id="background-image-file" accept="image/png,image/jpeg,image/webp" hidden /></div></div></div>`)}${group('Game Details','Uses the color saved in your library for each game.',`<div class="inner-card">${select('details-theme','Game Details surface','',[['same','Match Game Mode'],['light','Light'],['clear','Clear'],['dark','Dark']],appearance.detailsTheme)}${surfaceTintControls(appearance.accentMode,appearance.tintStrength)}${select('details-navigation','Game Details navigation','',['sidebar','tabs'].map(key=>[key,key==='sidebar'?'Sidebar':'Tabs']),appearance.detailsNavigation)}</div>`)}${group('Reading and motion','',`<div class="inner-card">${select('text-size','Text size','',[['standard','Standard'],['large','Large']],appearance.text)}${toggle('motion','Motion','Follows your system’s reduced-motion preference.',appearance.motion)}</div>`)}${group('Layout','',`<div class="inner-card">${select('navigation-position','Navigation placement','Main sections at the top or bottom.',[['top','Top'],['bottom','Bottom']],appearance.navigation)}${scale}</div>`)}${group('Controls','',controlGuide())}${group('Library reader','',`<dl class="reader-facts"><dt>Connection</dt><dd>${loading?'Reading…':snapshot?'Connected · read-only':'Unavailable'}</dd><dt>Platform</dt><dd>${e(snapshot?.platform||'Not reported')}</dd><dt>Steam libraries</dt><dd>${snapshot?.libraryCount??'Not reported'}</dd><dt>Last snapshot</dt><dd>${snapshot?e(new Date(snapshot.capturedAt).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})):'Not reported'}</dd></dl><button class="quiet" data-action="refresh" ${loading?'disabled':''}>${icon('refresh')}Refresh reader</button>${error?`<p class="reader-error">${e(error)}</p>`:''}`)}<div class="appearance-reset"><span class="subtle">${backend.preview?'Appearance changes stay in this preview.':'Appearance changes are saved automatically.'}</span><button class="quiet" data-action="reset-appearance">Reset appearance</button></div></div>`;
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
    const next={...appearance,background:result,detailsNavigationVersion:1,appearanceDefaultsVersion:2,libraryScaleVersion:1};
    localStorage.setItem('rtxforge-game-mode-prototype',JSON.stringify(next));appearance.background=result;applyAppearance();render();announce('Game Mode background saved.');
  }catch(problem){announce(problem instanceof Error?problem.message:'This image could not be loaded.');}
  finally{URL.revokeObjectURL(source);}
}
function controlGuide() {
  const glyph=(index:number)=>controllerGlyph(controllerFamily(),index);
  const row=(action:string,keys:string)=>`<div><dt>${action}</dt><dd>${keys}</dd></div>`;
  return `<div class="control-guide"><section><h3>${icon('keyboard')}Keyboard</h3><dl>${row('Move','<kbd>Tab</kbd><span>or arrow keys</span>')}${row('Select','<kbd>Enter</kbd>')}${row('Back','<kbd>Esc</kbd>')}${row('Sections','<kbd>[</kbd><kbd>]</kbd>')}</dl></section><section><h3>${icon('controller')}Controller</h3><dl>${row('Move','<span>D-pad or left stick</span>')}${row('Select',glyph(0))}${row('Back',glyph(1))}${row('Sections',glyph(2)+glyph(3))}${row('Face buttons',glyph(4)+glyph(5))}</dl></section></div><p class="control-status subtle">${controller?'Controller connected.':'Connect a controller to navigate with a gamepad.'}</p>`;
}
function currentPreferences() { return { ...snapshot?.preferences, ...sharedPreferences, ...preferenceChanges }; }
function sharedSettings() {
  return `${!backend.enabled ? notice('Read-only preview', 'Showing saved settings. Game, Steam and shared preference actions are disabled.') : !sharedPreferences ? '<button class="quiet" data-action="load-settings">Load shared preferences</button>' : ''}${settingsContent({category:settingsCategory,steamAdded,preferences:{...snapshot?.preferences,...sharedPreferences},changes:preferenceChanges,glassDefaults:snapshot?.overlayDefaults||{},enabled:backend.enabled&&Boolean(sharedPreferences),platform:snapshot?.platform,icon,gridConnected,games:snapshot?.games||[],reportSelection:supportSelection,overlayReport:snapshot?.overlayReport,hardware:snapshot?.hardware,previewGame:overlayPreviewGame()})}<div class="section-footer"><span>Shared preferences change after review.</span><button class="primary" data-action="save-settings" ${!backend.enabled||!sharedPreferences||!Object.keys(preferenceChanges).length?'disabled':''}>Review preferences</button></div>`;
}
function overlayPreviewGame() {
  return snapshot?.games.find(game=>game.id===overlayPreviewId)||snapshot?.games[0];
}
function perGameOverlay() { return view==='details'&&detailsSection==='overlay' ? selectedGame() : undefined; }
function overlayWorkingPreferences() {
  const game=perGameOverlay();if(!game)return currentPreferences();
  const overrides=(sharedPreferences?.game_overlay_settings||{}) as Record<string,Record<string,unknown>>;
  const identity=Object.keys(overrides).find(key=>pathKey(key)===pathKey(game.path))||game.path;
  return mergeOverlay({...snapshot?.preferences,...sharedPreferences},overrides[identity],gameOverlayDrafts.get(game.id));
}
function editOverlayPreference(key:string,value:unknown) {
  const game=perGameOverlay();
  const changes=game ? {...gameOverlayDrafts.get(game.id),[key]:value} : {...preferenceChanges,[key]:value};
  if(key==='overlay_renderer'&&value==='optiscaler'){
    Object.assign(changes,{optiscaler_ui:true,reshade_ui:true});
    if(overlayWorkingPreferences().optiscaler_hotkey==='Disabled')changes.optiscaler_hotkey='Insert';
  }
  if(game)gameOverlayDrafts.set(game.id,changes);else Object.assign(preferenceChanges,changes);
}
function editGlass(key: string, value: unknown) {
  const current={...snapshot?.overlayDefaults,...overlayWorkingPreferences().overlay_appearance as Record<string,unknown>};
  current[key]=value;
  if(key==='AccentMode'&&value==='custom'){
    const game=perGameOverlay()||overlayPreviewGame();
    current.AccentColor=game?.accent||game?.artworkAccent||'#d8d5ce';
  }
  if (key==='AccentCharacter') { const x=Math.min(Number(value)/50,1); current.AccentTint=Math.round(20+60*x*x*(3-2*x)); }
  editOverlayPreference('overlay_appearance',current);
}
function editOverlaySurface(base:string,tint:boolean) {
  const glass={...snapshot?.overlayDefaults,...overlayWorkingPreferences().overlay_appearance as Record<string,unknown>};
  editOverlayPreference('overlay_theme',tint?'accent':base);
  editOverlayPreference('overlay_appearance',surfaceChanges(glass,base,tint,snapshot?.overlayThemes));
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
let disposeLibraryLayout = () => {};
function previewWindowActions() {
  if(!backend.preview)return '';
  const title=backend.fullscreen?'Exit full screen':'Enter full screen';
  const arrows=backend.fullscreen?'M4 20l6-6m0 0H5m5 0v5M20 4l-6 6m0 0h5m-5 0V5':'M10 14l-6 6m0 0v-5m0 5h5M14 10l6-6m0 0v5m0-5h-5';
  return `<button class="preview-fullscreen" data-action="toggle-window-mode" aria-label="${title}" title="${title}"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${arrows}"/></svg></button><button class="preview-close" data-action="exit-app" aria-label="Close preview" title="Close preview"><span aria-hidden="true">×</span></button>`;
}

function render() {
  const priorFocus = document.activeElement instanceof HTMLElement && app.contains(document.activeElement) ? document.activeElement : null;
  const focusKey = priorFocus ? (priorFocus.id ? `#${CSS.escape(priorFocus.id)}` : [...priorFocus.attributes].filter(a=>a.name.startsWith('data-')).map(a=>`[${a.name}="${CSS.escape(a.value)}"]`).join('')) : null;
  const nextArrival = `${view}:${view==='details'?selectedGame()?.id+':'+detailsSection:view==='settings'?settingsCategory:view==='operation'?operation?.stage:''}`;
  const arrival = nextArrival !== arrivalKey ? captureArrival(app) : null;
  closeSelectMenu(false);
  disposeLibraryLayout();
  const sameSurface = renderedView === view && (view !== 'details' || renderedGame === selectedGame()?.id);
  const contentScroll = view==='operation'&&modalOrigin ? modalOrigin.content : sameSurface ? app.querySelector<HTMLElement>('#content')?.scrollTop || 0 : 0;
  const detailsScroll = view==='operation'&&modalOrigin ? modalOrigin.details : sameSurface ? app.querySelector<HTMLElement>('.details-scroll')?.scrollTop || 0 : 0;
  const resultsScroll = view==='operation'&&modalOrigin ? modalOrigin.results : sameSurface ? app.querySelector<HTMLElement>('#game-results')?.scrollTop || 0 : 0;
  const splitListScroll = sameSurface ? app.querySelector<HTMLElement>('.split-game-list')?.scrollTop || 0 : 0;
  const flowScroll = operation?.stage === 'review' ? app.querySelector<HTMLElement>('.operation-flow[data-stage=review] .flow-body')?.scrollTop || 0 : 0;
  applyAppearance();
  const operationModal = view==='operation' && !!operation?.kind;
  const removalModal = view==='packages' && splitRemove;
  const modal = operationModal || removalModal;
  const surface = operationModal ? operation?.origin || 'library' : view;
  document.documentElement.dataset.surface = surface;
  const pageContent = surface === 'library' ? library() : surface === 'presets' ? presets() : surface === 'details' ? details() : surface === 'packages' ? packages() : surface === 'extras' ? extras() : surface === 'operation' ? operationView() : settings();
  const content = modal ? pageContent.replace('id="page-title"','id="background-page-title"') : pageContent;
  const removalReview = operationModal && operation?.kind === 'remove-nr-addons' && surface === 'packages';
  const modalClass = removalModal ? ' split-remove-modal' : removalReview ? ' split-remove-review' : '';
  const overlay = modal ? `<div class="operation-backdrop"><section class="operation-modal glass-section${modalClass}" role="dialog" aria-modal="true" aria-labelledby="page-title">${removalModal ? splitRemovalPicker() : operationView()}</section></div>` : '';
  app.innerHTML = `<div class="shell" ${modal?'inert aria-hidden="true"':''}><header class="app-header" data-tauri-drag-region><div class="brand"><img src="/logo-mark.png" alt="" /><span>rtxForge</span></div><nav class="glass main-nav" aria-label="Main navigation">${tabs.map(tab => `<button data-route="${tab.id}" ${surface === tab.id || surface === 'details' && tab.id === 'library' ? 'aria-current="page"' : ''}>${icon(tab.icon)}<span>${tab.label}</span></button>`).join('')}</nav><div class="shell-more"><button class="menu-button" id="shell-menu-button" data-action="shell-menu" aria-label="More options" aria-haspopup="menu" aria-expanded="${shellMenuOpen}">${icon('dots')}</button>${previewWindowActions()}<div class="shell-menu glass-section" id="shell-menu" role="menu" ${shellMenuOpen ? '' : 'hidden'}><button role="menuitem" data-route="library">${icon('books')}Library</button><button role="menuitem" data-action="menu-appearance">${icon('palette')}Appearance</button><button role="menuitem" data-action="refresh">${icon('refresh')}Refresh library</button><button role="menuitem" data-action="menu-library">${icon('folder')}Library options</button><button role="menuitem" data-action="menu-controls">${icon('controller')}Controls</button><div class="menu-divider"></div>${backend.preview?'':`<button role="menuitem" data-action="toggle-window-mode" ${!('__TAURI_INTERNALS__' in window)?'disabled':''}>${icon('grid')}${backend.fullscreen?'Switch to Windowed Mode':'Switch to Fullscreen'}</button>`}<button role="menuitem" data-action="minimize-app" ${!('__TAURI_INTERNALS__' in window)?'disabled':''}>${icon('minus')}Minimize</button><button role="menuitem" data-action="desktop-mode" ${!('__TAURI_INTERNALS__' in window)?'disabled':''}>${icon('grid')}Desktop mode</button><button role="menuitem" data-action="exit-app" ${!('__TAURI_INTERNALS__' in window)?'disabled':''}>${icon('arrow')}Exit rtxForge</button><span class="menu-preview">${backend.enabled?'Engine connected':'Read-only preview'}</span></div></div></header><main id="content" class="content glass" aria-label="${view === 'details' ? 'Game details' : tabs.find(tab => tab.id === view)?.label}">${content}</main><footer class="app-footer"><div id="input-hints">${hints()}</div></footer></div>${overlay}`;
  const game = selectedGame(), scene = document.querySelector<HTMLElement>('#scene')!;
  if(view==='details'&&snapshot&&game)prioritizeArtwork(snapshot,game.id);
  applyStoreBackground(surface==='details'&&currentPreferences().online_art!==false&&game&&(game.accent||game.artworkAccentReady)?game.appid:null,scene,game?.id,detailsAccent(game));
  applyDetailsAccent();
  applyOperationAccent();
  bind();
  setupHero();
  setupSettingsLayout();
  disposeLibraryLayout = setupLibraryLayout(app);disposeViewportArtwork();disposeViewportArtwork=setupViewportArtwork(app);
  enhanceSelects(app);
  bindArtworkFailures(app);
  bindScreenshotThumbnails(app);
  setupScrollFades();
  const main = app.querySelector<HTMLElement>('#content'); if(main)main.scrollTop=contentScroll;
  const results = app.querySelector<HTMLElement>('#game-results'); if(results)results.scrollTop=resultsScroll;
  const splitList = app.querySelector<HTMLElement>('.split-game-list'); if (splitList) splitList.scrollTop = splitListScroll;
  const flowBody = app.querySelector<HTMLElement>('.flow-body'); if (flowBody) flowBody.scrollTop = flowScroll;
  const scrollingDetails=app.querySelector<HTMLElement>('.details-scroll'); if(scrollingDetails) { scrollingDetails.scrollTop=detailsScroll; scrollingDetails.dispatchEvent(new Event('scroll')); }
  renderedView=view;renderedGame=selectedGame()?.id||'';
  if (arrival) arrive(app, arrival, view);
  if (sameSurface && focusKey) app.querySelector<HTMLElement>(focusKey)?.focus({preventScroll:true});
  arrivalKey = nextArrival;
  showHints();
}
function controllerFamily(): ControllerFamily {
  let family = String(preferenceChanges.controller_glyphs ?? sharedPreferences?.controller_glyphs ?? snapshot?.defaults.controller_glyphs ?? 'auto');
  if (family === 'auto') family = /dual|sony|playstation/i.test(controllerId) ? 'playstation' : /nintendo|switch/i.test(controllerId) ? 'nintendo' : /steam/i.test(controllerId) ? 'steam' : 'xbox';
  return (['xbox','playstation','nintendo','steam','generic'].includes(family) ? family : 'xbox') as ControllerFamily;
}
function hints() {
  const glyph=(index:number)=>controllerGlyph(controllerFamily(),index);
  return controller ? `<span>${glyph(0)} Select</span><span>${glyph(1)} Back</span><span>${glyph(2)}${glyph(3)} Sections</span>` : '<span><kbd>Enter</kbd> Select</span><span><kbd>Esc</kbd> Back</span><span><kbd>Tab</kbd> Navigate</span>';
}
const glyphRules: [RegExp, string][] = [
  [/restore|reset|recovery|refresh|reload|use detected|load settings/i,'refresh'],
  [/compatibility|verify|confirm|apply|save|done|use color/i,'check'],
  [/install|update|download/i,'download'],
  [/reshade|renodx|add-ons?|extras|tools|cleanup/i,'wrench'],
  [/uninstall|remove|clear selection|disable/i,'minus'],
  [/executable|files|notes|report|copy/i,'file'],
  [/open folder|storage|folders?/i,'folder'],
  [/appearance|theme|surface|accent|color|artwork|background/i,'palette'],
  [/controller|steam|launch|play/i,'controller'],
  [/features|presets|tuning|frame generation|graphics|controls/i,'sliders'],
  [/neural rendering|hardware|system/i,'cpu'],
  [/package|import/i,'package'],
  [/add |new |choose|browse/i,'plus'],
  [/about|guide|testing|details/i,'info'],
  [/back|cancel|close/i,'arrow'],
  [/library|layout/i,'grid'],
];
function consistentGlyph(label: string, fallback: string) {
  return glyphRules.find(([match])=>match.test(label))?.[1] || fallback;
}
function enhanceActionLabels() {
  for(const heading of app.querySelectorAll<HTMLElement>('#content :is(.glass-section,.inner-card,.action-card,.extra-detail) :is(h2,h3,h4), #content .glass-section>h2, #content .action-card>h3')) {
    if(heading.closest('.dlss-file-card'))continue;
    heading.classList.add('panel-heading');
    if(heading.querySelector('.icon') || heading.previousElementSibling?.classList.contains('icon'))continue;
    heading.insertAdjacentHTML('afterbegin',icon(consistentGlyph(heading.textContent||'', 'info')));
  }
  for(const button of app.querySelectorAll<HTMLButtonElement>('#content :is(.primary,.quiet,.setting-action), .operation-actions button')) {
    if(button.querySelector('.icon') || !button.textContent?.trim())continue;
    button.insertAdjacentHTML('afterbegin',icon(consistentGlyph(button.textContent,'arrow'),'button-glyph'));
  }
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
function bindSplitRender() {
  app.querySelector<HTMLDetailsElement>('#split-packages')?.addEventListener('toggle', event => {
    splitPackageOpen = (event.currentTarget as HTMLDetailsElement).open;
  });
  app.querySelector<HTMLDetailsElement>('#split-install-options')?.addEventListener('toggle', event => {
    if (operation?.split) operation.split.open = (event.currentTarget as HTMLDetailsElement).open;
  });
  app.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-split-field]').forEach(field => field.addEventListener('change', () => {
    const scope = field.closest<HTMLElement>('[data-split-picker]')?.dataset.splitPicker;
    const key = field.dataset.splitField!;
    if (scope === 'install' && splitCatalog && operation?.split) {
      changePicker(splitCatalog, operation.split.picker, key, field.value);
      operation.split.open = true;
      void reviewSplitChoices();
    } else if (scope === 'packages' && splitCatalog) {
      changePicker(splitCatalog, packagePicker, key, field.value);
      void matchSplitGames();
    } else if (scope === 'presets' && splitPresetEditor) {
      const editor = splitPresetEditor;
      changePicker(editor.catalog, editor.picker, key, field.value, true);
      if (key === 'preset') {
        const preset = editor.catalog.combos[field.value];
        editor.name = preset && !preset.builtin ? preset.name : '';
      }
      void checkSplitPreset();
    } else if (scope === 'tools' && splitTool) {
      changePicker(splitTool.catalog, splitTool.picker, key, field.value, true);
      void checkSplitTool();
    }
  }));
  app.querySelector<HTMLInputElement>('#split-game-search')?.addEventListener('input', event => {
    splitQuery = (event.target as HTMLInputElement).value;
    render();
  });
  app.querySelectorAll<HTMLInputElement>('[data-nr-target]').forEach(field => field.addEventListener('change', () => {
    const id = field.dataset.nrTarget!;
    if (field.checked) splitSelected.add(id);
    else splitSelected.delete(id);
    render();
  }));
  app.querySelectorAll<HTMLButtonElement>('[data-feeder-pass], [data-feeder-role]').forEach(button => {
    button.addEventListener('click', () => {
      if (!splitTool || splitTool.busy) return;
      const { feederPass, feederRole } = button.dataset;
      if (feederPass) {
        splitTool.feederPass = Number(feederPass);
        splitTool.feederRole = undefined;
        splitTool.feederSkin = undefined;
      } else splitTool.feederRole = feederRole === 'character';
      splitTool.feederMessage = undefined;
      render();
      const choice = feederPass ? `[data-feeder-pass="${feederPass}"]` : `[data-feeder-role="${feederRole}"]`;
      app.querySelector<HTMLButtonElement>(choice)?.focus();
    });
  });
  app.querySelector<HTMLInputElement>('#feeder-skin')?.addEventListener('input', event => {
    const tool = splitTool;
    if (!tool) return;
    tool.feederSkin = (event.target as HTMLInputElement).valueAsNumber;
    const chosen = feederSelection(tool);
    if (!chosen) return;
    const output = app.querySelector<HTMLOutputElement>('#feeder-skin-output');
    if (output) output.value = chosen.skin < 0 ? 'Stock' : chosen.skin.toFixed(2);
    const apply = app.querySelector<HTMLButtonElement>('[data-action="feeder-character-apply"]');
    if (apply) apply.disabled = tool.busy || !!chosen.settings.reason || !chosen.changed;
  });
  app.querySelector<HTMLSelectElement>('#split-preset-package')?.addEventListener('change', event =>
    void loadSplitPresets((event.target as HTMLSelectElement).value));
  app.querySelector<HTMLInputElement>('#split-preset-name')?.addEventListener('input', event => {
    const editor = splitPresetEditor;
    if (!editor) return;
    editor.name = (event.target as HTMLInputElement).value;
    const save = app.querySelector<HTMLButtonElement>('[data-action="save-split-preset"]');
    if (save) save.disabled = !editor.checked || !!editor.reason || editor.busy || !editor.name.trim();
  });
}
function bind() {
  bindReviewInfo(app);
  bindSplitRender();
  enhanceActionLabels();
  app.querySelectorAll<HTMLElement>('button:not(.review-info-button),input,select,textarea,summary,a[href]').forEach(node=>node.classList.add('ui-control'));
  app.querySelectorAll<HTMLElement>('[data-preset-control]').forEach(node=>node.dataset.presetKey='control-'+node.dataset.presetControl);
  app.querySelectorAll<HTMLSelectElement|HTMLInputElement>('[data-startup-control]').forEach(node=>node.addEventListener('change',()=>{if(!pendingInstall)return;const key=node.dataset.startupControl!;const controls={...pendingInstall.settings.feature_controls as Record<string,unknown>,[key]:Number(node.value)};pendingInstall.settings.feature_controls=controls;if(key==='intensity')pendingInstall.settings.nr_strength=Number(node.value);if(key==='sharpness')pendingInstall.settings.sharpening_strength=Number(node.value);if(key==='enabled')pendingInstall.settings.nr_on_launch=Number(node.value)!==0;}));
  app.querySelectorAll<HTMLElement>('[data-startup-mode]').forEach(node=>node.addEventListener('click',()=>{if(!pendingInstall)return;const mode=Number(node.dataset.startupMode),values=pendingInstall.settings;values.mfg_saved_mode=mode;values.mfg_multiplier=mode===0?'auto':values.mfg_saved_multiplier||2;values.dynamic_mfg=mode===2?1:0;render();app.querySelector<HTMLElement>(`[data-startup-mode="${mode}"]`)?.focus();}));
  app.querySelectorAll<HTMLElement>('[data-startup-ratio]').forEach(node=>node.addEventListener('click',()=>{if(!pendingInstall)return;const ratio=Number(node.dataset.startupRatio);pendingInstall.settings.mfg_saved_multiplier=ratio;pendingInstall.settings.mfg_multiplier=ratio;render();app.querySelector<HTMLElement>(`[data-startup-ratio="${ratio}"]`)?.focus();}));
  app.querySelector<HTMLSelectElement>('#startup-mfg-enabled')?.addEventListener('change',event=>{if(!pendingInstall)return;const values=pendingInstall.settings;values.mfg_multiplier=(event.target as HTMLSelectElement).value==='false'?0:values.mfg_saved_mode===0?'auto':values.mfg_saved_multiplier||2;render();app.querySelector<HTMLElement>('#startup-mfg-enabled')?.focus();});
  app.querySelector<HTMLInputElement>('#background-image-file')?.addEventListener('change',event=>{const file=(event.target as HTMLInputElement).files?.[0];if(file)void chooseBackground(file);});
  app.querySelectorAll<HTMLElement>('[data-tool-kind]').forEach(node=>node.addEventListener('click',()=>{ extraKind=node.dataset.toolKind!; extraSource=''; toolImportOpen=true; render(); app.querySelector<HTMLInputElement>('#extra-source')?.focus(); }));
  app.querySelector<HTMLSelectElement>('#test-result')?.addEventListener('change',event=>{ const game=selectedGame(); if(game) void engineRequest('notes_save',{game:game.path,status:(event.target as HTMLSelectElement).value,notes:noteDrafts.get(game.id)??game.notes??''}).then(()=>announce('Test result saved.')).catch(problem=>announce(problem.message)); });
  const accentGame=selectedGame();
  if(accentGame)bindColorPicker(app,'game-accent-color',accentGame.art||undefined,color=>{if(color===(accentGame.accent||accentGame.artworkAccent))gameAccentDrafts.delete(accentGame.id);else gameAccentDrafts.set(accentGame.id,color);applyAppearance();},color=>saveGameAccent(accentGame,color));
  app.querySelectorAll<HTMLInputElement|HTMLSelectElement|HTMLButtonElement>('[data-preset-key]').forEach(node => node.addEventListener(node instanceof HTMLButtonElement ? 'click' : 'change',()=>{ drafts.set(presetId,{...drafts.get(presetId),[node.dataset.presetKey!]:node.dataset.presetValue ?? node.value}); render(); app.querySelector<HTMLElement>(`[data-preset-key="${node.dataset.presetKey}"]${node.dataset.presetValue ? `[data-preset-value="${node.dataset.presetValue}"]` : ''}`)?.focus(); }));
  app.querySelectorAll<HTMLElement>('[data-route]').forEach(node => node.addEventListener('click', event => { event.preventDefault(); setView(node.dataset.route as View); }));
  app.querySelectorAll<HTMLElement>('[data-game]').forEach(node => node.addEventListener('click', () => { selectedId = node.dataset.game!; detailsSection='overview'; extraRecords=[];extraSource='';toolImportOpen=false; setView('details'); }));
  app.querySelectorAll<HTMLButtonElement>('[data-layout]').forEach(node => node.addEventListener('click', () => { libraryView = node.dataset.layout!; render(); app.querySelector<HTMLElement>(`[data-layout="${libraryView}"]`)?.focus(); }));
  app.querySelectorAll<HTMLElement>('[data-library-mode]').forEach(node=>node.addEventListener('click',()=>{libraryMode=node.dataset.libraryMode;const group=node.closest<HTMLElement>('.feature-mode-segments')!;group.style.setProperty('--selected-mode',String(['nr-only','mfg-only','nr-mfg'].indexOf(libraryMode!)));group.querySelectorAll<HTMLElement>('button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.libraryMode===libraryMode)));}));
  app.querySelector<HTMLSelectElement>('#library-filter')?.addEventListener('change',event=>void filterLibrary((event.target as HTMLSelectElement).value));
  app.querySelector<HTMLInputElement>('#library-size')?.addEventListener('input',event=>{const input=event.target as HTMLInputElement;appearance.libraryScale=Number(input.value);const results=app.querySelector<HTMLElement>('#game-results');if(results)results.scrollTop=0;input.setAttribute('aria-valuetext',input.value+'%');const output=app.querySelector<HTMLOutputElement>('.library-size output');if(output)output.value=input.value+'%';applyAppearance();disposeLibraryLayout();disposeLibraryLayout=setupLibraryLayout(app);requestAnimationFrame(()=>{if(results?.isConnected)results.scrollTop=0;});});
  app.querySelector<HTMLInputElement>('#library-search')?.addEventListener('input', event => { query = (event.target as HTMLInputElement).value; disposeLibraryLayout(); app.querySelector('#game-results')!.innerHTML = gameResults(filteredLibrary(), snapshot?.games.length || 0); bindResults(); disposeLibraryLayout = setupLibraryLayout(app);disposeViewportArtwork();disposeViewportArtwork=setupViewportArtwork(app); });
  app.querySelectorAll<HTMLElement>('[data-number-step]').forEach(node=>node.addEventListener('click',()=>{const field=node.parentElement?.querySelector<HTMLInputElement>('input[type=number]');if(!field||field.disabled)return; if(node.dataset.numberStep==='1')field.stepUp();else field.stepDown();field.dispatchEvent(new Event('change',{bubbles:true}));}));
  app.querySelectorAll<HTMLInputElement>('[data-hero-focus]').forEach(field=>field.addEventListener('input',()=>{const game=selectedGame();if(!game)return;const point=[...heroPoint(game)] as [number,number];point[Number(field.dataset.heroFocus)]=Number(field.value)/100;updateHeroPoint(point);}));
  const focalEditor=app.querySelector<HTMLButtonElement>('[data-focal-editor]');
  focalEditor?.addEventListener('click',()=>{
    if(heroAdjustment){finishHeroAdjustment();return;}
    const game=selectedGame();if(!game)return;
    const draft=heroFocusDrafts.get(game.id);heroAdjustment={game:game.id,previous:draft?[...draft]:undefined};
    focalEditor.setAttribute('aria-pressed','true');focalEditor.querySelector('.framing-action-label')!.textContent='Done adjusting';
    app.querySelector('#hero-framing-help')!.innerHTML=framingHelp();
  });
  focalEditor?.addEventListener('keydown',event=>{
    if(event.key==='Tab'){finishHeroAdjustment();return;}
    if(!heroAdjustment||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
    event.preventDefault();event.stopPropagation();
    const game=selectedGame();if(!game)return;const point=[...heroPoint(game)] as [number,number];
    point[event.key==='ArrowLeft'||event.key==='ArrowRight'?0:1]+=(event.key==='ArrowLeft'||event.key==='ArrowUp'?-.01:.01);updateHeroPoint(point);
  });
  app.querySelectorAll<HTMLButtonElement>('[data-background-shot]').forEach(button=>button.addEventListener('click',()=>{const game=selectedGame();if(!game)return;chooseScreenshots(game.id,[button.dataset.backgroundShot!]);render();app.querySelector<HTMLElement>(`[data-background-shot="${button.dataset.backgroundShot}"]`)?.focus({preventScroll:true});}));
  app.querySelectorAll<HTMLElement>('[data-action]').forEach(node => node.addEventListener('click', () => action(node.dataset.action!)));
  app.querySelectorAll<HTMLElement>('[data-theme-choice]').forEach(node => node.addEventListener('click', () => { appearance.theme = node.dataset.themeChoice as Appearance['theme']; applyAppearance(); render(); app.querySelector<HTMLElement>(`[data-theme-choice="${appearance.theme}"]`)?.focus(); }));
  app.querySelectorAll<HTMLElement>('[data-toggle]').forEach(node => node.addEventListener('click', () => { const key = node.dataset.toggle as 'motion' | 'tint'; appearance[key] = !appearance[key]; applyAppearance(); node.setAttribute('aria-checked', String(appearance[key])); }));
  app.querySelector<HTMLSelectElement>('#surface-accent-mode')?.addEventListener('change',event=>{appearance.accentMode=(event.target as HTMLSelectElement).value as Appearance['accentMode'];applyAppearance();render();app.querySelector<HTMLElement>('#surface-accent-mode')?.focus();});
  app.querySelector<HTMLInputElement>('#surface-tint-strength')?.addEventListener('input',event=>{const input=event.target as HTMLInputElement;appearance.tintStrength=Number(input.value);const output=input.parentElement?.querySelector('output');if(output)output.textContent=input.value+'%';applyAppearance();});
  app.querySelector<HTMLSelectElement>('#app-accent-source')?.addEventListener('change',event=>{
    appearance.accentSource=(event.target as HTMLSelectElement).value as Appearance['accentSource'];
    applyAppearance();render();app.querySelector<HTMLElement>('#app-accent-source')?.focus();
    void refreshSystemAccent();
  });
  app.querySelector<HTMLInputElement>('#accent-color')?.addEventListener('input', event => { appearance.accent = (event.target as HTMLInputElement).value; applyAppearance(); });
  app.querySelector<HTMLSelectElement>('#text-size')?.addEventListener('change', event => { appearance.text = (event.target as HTMLSelectElement).value as Appearance['text']; applyAppearance(); });
  app.querySelector<HTMLSelectElement>('#details-theme')?.addEventListener('change',event=>{appearance.detailsTheme=(event.target as HTMLSelectElement).value as Appearance['detailsTheme'];applyAppearance();});
  app.querySelector<HTMLSelectElement>('#details-navigation')?.addEventListener('change',event=>{appearance.detailsNavigation=(event.target as HTMLSelectElement).value as Appearance['detailsNavigation'];applyAppearance();});
  app.querySelector<HTMLSelectElement>('#navigation-position')?.addEventListener('change', event => { appearance.navigation = (event.target as HTMLSelectElement).value as Appearance['navigation']; applyAppearance(); });
  app.querySelector<HTMLSelectElement>('#display-scale')?.addEventListener('change', event => { const value = (event.target as HTMLSelectElement).value; appearance.scale = value === 'auto' ? 'auto' : Number(value); applyAppearance(); });
  app.querySelectorAll<HTMLSelectElement | HTMLInputElement>('[data-draft]').forEach(node => node.addEventListener('change', () => { const game = selectedGame(); if (!game) return; drafts.set(game.id, { ...drafts.get(game.id), [node.dataset.draft!]: node.value }); app.querySelector('#draft-label')!.textContent = 'Draft · not applied'; if (['mfg_mode', 'mfg_enabled', 'provider'].includes(node.dataset.draft!)) { render(); app.querySelector<HTMLElement>(`[data-draft="${node.dataset.draft}"]`)?.focus(); } announce('Preview choice changed. Nothing applied.'); }));
  app.querySelectorAll<HTMLElement>('[data-extra]').forEach(node => node.addEventListener('click', () => { extraKind = node.dataset.extra!; render(); app.querySelector<HTMLElement>(`[data-extra="${extraKind}"]`)?.focus(); }));
  app.querySelectorAll<HTMLElement>('[data-detail-section]').forEach(node => node.addEventListener('click', () => { if(detailsSection!==node.dataset.detailSection)gameAccentDrafts.clear(); detailsSection = node.dataset.detailSection!; detailsMenuOpen=false; render(); app.querySelector<HTMLElement>(`[data-detail-section="${detailsSection}"]`)?.focus(); const game = selectedGame(); if(detailsSection==='files'&&game)void loadDlssFiles(game); if(detailsSection==='tools'&&game&&backend.enabled)void loadSplitTool(game); if(detailsSection==='overview'&&game&&backend.enabled){const row=engineRows.find(record=>pathKey(record.game)===pathKey(game.path));if(row)void loadOverviewExtras(game,row);} if (detailsSection === 'notes' && backend.enabled && game && !notesLoaded.has(game.id)) void engineRequest<Record<string, unknown>>('notes_get', { game: game.path }).then(record => { if (!noteDrafts.has(game.id)) noteDrafts.set(game.id, String(record.notes || '')); notesLoaded.add(game.id); if (view === 'details' && detailsSection === 'notes' && selectedId === game.id) render(); }).catch(problem => announce(problem.message)); }));
  app.querySelectorAll<HTMLElement>('[data-operation]').forEach(node => node.addEventListener('click', () => void runOperation(node.dataset.operation!, node.dataset.batch === 'true', node.dataset.libraryScope === 'true')));
  app.querySelectorAll<HTMLElement>('[data-contract]').forEach(node => node.addEventListener('click', async () => {
    const game = selectedGame(); if (!game) return;
    try { const rows = await getEngineRows(); const row = rows.find(row => pathKey(row.game) === pathKey(game.path)); if (!row) throw new Error('This installation is unavailable to the engine.'); await withOperation(node.textContent?.trim() || 'Review', node.dataset.contract!, { ...(node.dataset.contract === 'report_draft' ? { rows: [row] } : { row }), ...(node.dataset.remove ? { remove: true } : {}) }, node.dataset.contract === 'report_draft' ? 'report-draft' : ['diagnose','dlss_inventory'].includes(node.dataset.contract!) ? 'inspect' : 'run'); }
    catch (problem) { announce(problem instanceof Error ? problem.message : 'The engine is unavailable.'); }
  }));
  app.querySelector<HTMLInputElement>('#review-trust')?.addEventListener('change', event => {
    if (operation) operation.acceptedTrust = (event.target as HTMLInputElement).checked;
    syncReviewConfirm();
  });
  app.querySelectorAll<HTMLInputElement>('[data-supported-token]').forEach(field => field.addEventListener('change', () => {
    if (!operation) return;
    operation.chosenOffers ??= new Set();
    if (field.checked) operation.chosenOffers.add(field.dataset.supportedToken!);
    else operation.chosenOffers.delete(field.dataset.supportedToken!);
    if (operation.split?.rows.length) render();
    else syncReviewConfirm();
  }));
  if (operation?.stage === 'review') syncReviewConfirm();
  app.querySelectorAll<HTMLElement>('[data-settings-category]').forEach(node => node.addEventListener('click', () => { settingsCategory = node.dataset.settingsCategory!; render(); app.querySelector<HTMLElement>(`[data-settings-category="${settingsCategory}"]`)?.focus(); }));
  app.querySelectorAll<HTMLSelectElement>('[data-preference]').forEach(node => node.addEventListener('change', () => { editOverlayPreference(node.dataset.preference!,JSON.parse(node.value)); render(); app.querySelector<HTMLElement>(`[data-preference="${node.dataset.preference}"]`)?.focus(); announce('Preference changed in draft. Review to save it.'); }));
  app.querySelectorAll<HTMLElement>('[data-preference-toggle]').forEach(node=>node.addEventListener('click',()=>{ const key=node.dataset.preferenceToggle!; editOverlayPreference(key,!overlayWorkingPreferences()[key]);render();app.querySelector<HTMLElement>(`[data-preference-toggle="${key}"]`)?.focus(); }));
  app.querySelectorAll<HTMLSelectElement>('[data-glass]').forEach(node=>node.addEventListener('change',()=>{if(node.dataset.glass==='AccentMode'){const glass={...snapshot?.overlayDefaults,...overlayWorkingPreferences().overlay_appearance as Record<string,unknown>};editOverlaySurface(overlaySurface(glass),JSON.parse(node.value)!=='theme');}editGlass(node.dataset.glass!,JSON.parse(node.value));render();app.querySelector<HTMLElement>(`[data-glass="${node.dataset.glass}"]`)?.focus();}));
  app.querySelectorAll<HTMLInputElement>('[data-glass-range]').forEach(node=>node.addEventListener('input',()=>{editGlass(node.dataset.glassRange!,Number(node.value));const output=node.parentElement?.querySelector('output');if(output)output.textContent=node.value+'%';const save=app.querySelector<HTMLButtonElement>('[data-action="save-settings"]');if(save)save.disabled=false;}));
  app.querySelectorAll<HTMLElement>('[data-overlay-layout]').forEach(node=>node.addEventListener('click',()=>{editGlass('Layout',node.dataset.overlayLayout);render();app.querySelector<HTMLElement>(`[data-overlay-layout="${node.dataset.overlayLayout}"]`)?.focus();}));
  app.querySelectorAll<HTMLElement>('[data-overlay-surface]').forEach(node=>node.addEventListener('click',()=>{
    const glass={...snapshot?.overlayDefaults,...overlayWorkingPreferences().overlay_appearance as Record<string,unknown>};
    editOverlaySurface(node.dataset.overlaySurface!,glass.Theme===4);render();app.querySelector<HTMLElement>(`[data-overlay-surface="${node.dataset.overlaySurface}"]`)?.focus();
  }));
  app.querySelector<HTMLElement>('[data-overlay-tint]')?.addEventListener('click',()=>{
    const glass={...snapshot?.overlayDefaults,...overlayWorkingPreferences().overlay_appearance as Record<string,unknown>};
    editOverlaySurface(overlaySurface(glass),glass.Theme!==4);render();app.querySelector<HTMLElement>('[data-overlay-tint]')?.focus();
  });
  app.querySelector<HTMLSelectElement>('#overlay-preview-game')?.addEventListener('change',event=>{
    overlayPreviewId=(event.target as HTMLSelectElement).value;
    render();app.querySelector<HTMLElement>('#overlay-preview-game')?.focus();
  });
  app.querySelector<HTMLInputElement>('#overlay-preview-search')?.addEventListener('input',event=>{
    const text=(event.target as HTMLInputElement).value.toLowerCase();
    app.querySelectorAll<HTMLOptionElement>('#overlay-preview-game option').forEach(option=>{option.hidden=!option.textContent?.toLowerCase().includes(text);});
  });
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
    (event.target as HTMLInputElement).value = value; editOverlayPreference('panel_hotkey',value);
  });
  app.querySelectorAll<HTMLElement>('[data-provider-default]').forEach(node => node.addEventListener('click', () => void withOperation('Review default package', 'settings_review', { changes: { runtime_provider: node.dataset.providerDefault } })));
  app.querySelectorAll<HTMLElement>('[data-mfg-default]').forEach(node => node.addEventListener('click', () => void withOperation('Review MFG package', 'settings_review', { changes: { mfg_provider: node.dataset.mfgDefault } })));
  if ('__TAURI_INTERNALS__' in window) {
    for (const [id, kind] of [['package-source', 'package'], ['extra-source', extraKind==='hdr-custom' ? 'renodx-addon' : extraKind==='addon' ? 'addon' : 'tool'], ['artwork-source', 'image']]) {
      const field = app.querySelector<HTMLInputElement>('#' + id);
      if (!field) continue;
      const browse = document.createElement('button'); browse.className = 'quiet'; browse.textContent = 'Browse…'; browse.type = 'button'; browse.disabled = !backend.enabled;
      browse.addEventListener('click', async event => { event.preventDefault(); const result = await (await import('@tauri-apps/api/core')).invoke<string | null>('choose_path', { kind }); if (result) { field.value = result; field.dispatchEvent(new Event('input')); } });
      field.parentElement?.append(browse);
    }
  }
  if (!backend.enabled) app.querySelectorAll<HTMLInputElement>('#package-source,#extra-source').forEach(field => { field.disabled = true; });
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
let appearanceSave:Promise<void>=Promise.resolve();
function saveGameAccent(game:Game,color:string|null):Promise<void>{
  const pending=appearanceSave.catch(()=>{}).then(async()=>{
    const settings=await engineRequest<Record<string,unknown>>('settings_get');
    const colors={...(settings.game_accents||{}) as Record<string,string>};
    const identity=Object.keys(colors).find(key=>pathKey(key)===pathKey(game.path))||game.path;
    if(color===null)delete colors[identity];else colors[identity]=color;
    const review=await engineRequest<Review>('settings_review',{changes:{game_accents:colors}});
    await engineRequest('run',{token:review.token,trusted:true});
    game.accent=color||undefined;gameAccentDrafts.delete(game.id);
    sharedPreferences={...settings,game_accents:colors};
    if(snapshot)snapshot.preferences={...snapshot.preferences,game_accents:colors};
    applyAppearance();
    const editingGame=view==='details'&&selectedId===game.id;
    const reset=editingGame?app.querySelector<HTMLButtonElement>('[data-action=reset-game-accent]'):null;if(reset)reset.disabled=!color;
    const description=editingGame?app.querySelector('.game-accent-section>p'):null;if(description)description.textContent=color?'Saved in rtxForge · '+color.toUpperCase():'Automatic color from your library poster.';
    announce(color?'Accent color saved.':'Artwork color restored.');
  });
  appearanceSave=pending;return pending;
}
function action(name: string) {
  if(name==='reset-hero-framing'){const game=selectedGame();if(game)heroFocusDrafts.delete(game.id);heroAdjustment=undefined;render();app.querySelector<HTMLElement>('[data-action="reset-hero-framing"]')?.focus();return;}
  if(name==='save-hero-framing'){const game=selectedGame(),point=game?heroFocusDrafts.get(game.id):undefined;if(!game||!point||!backend.enabled)return;void engineRequest<Record<string,unknown>>('settings_get').then(settings=>{const choices={...(settings.game_hero_focus||{}) as Record<string,number[]>};const identity=Object.keys(choices).find(key=>pathKey(key)===pathKey(game.path))||game.path;choices[identity]=point;return withOperation('Review hero framing','settings_review',{changes:{game_hero_focus:choices}});}).catch(problem=>announce(problem.message));return;}
  if(name==='toggle-window-mode'&&'__TAURI_INTERNALS__' in window){
    shellMenuOpen=false;
    void import('@tauri-apps/api/core').then(({invoke})=>invoke<boolean>('toggle_fullscreen')).then(fullscreen=>{
      backend.fullscreen=fullscreen;render();
      if(backend.preview)app.querySelector<HTMLElement>('.preview-fullscreen')?.focus({preventScroll:true});
    }).catch(problem=>announce(String(problem)));
    return;
  }
  if(name==='minimize-app'&&'__TAURI_INTERNALS__' in window){shellMenuOpen=false;void import('@tauri-apps/api/core').then(({invoke})=>invoke('minimize_app')).catch(problem=>announce(String(problem)));return;}
  if(name==='reset-game-accent'){const game=selectedGame();if(game&&backend.enabled)void saveGameAccent(game,null).then(()=>render()).catch(problem=>announce(problem.message));return;}
  if (name === 'reset-presets') { drafts.delete(presetId); render(); return; }
  if (name === 'select-preset-games') { presetSelection=true; batchSelection.clear(); setView('library'); announce('Select configured games, then review their preset changes.'); return; }
  if (name === 'end-preset-selection') { presetSelection=false; batchSelection.clear(); setView('presets'); return; }
  if (name === 'apply-presets' || name === 'apply-selected-presets') { void applyPresets(name === 'apply-selected-presets'); return; }
  if(name==='choose-background'){app.querySelector<HTMLInputElement>('#background-image-file')?.click();return;}
  if(name==='reset-background'){delete appearance.background;applyAppearance();render();return;}
  if(name==='desktop-mode'||name==='exit-app'){
    if(operation?.stage==='running'){announce('Wait for the operation to finish or request cancellation first.');return;}
    if('__TAURI_INTERNALS__' in window)void flushAppearance().then(()=>import('@tauri-apps/api/core')).then(({invoke})=>invoke(name==='desktop-mode'?'desktop_mode':'exit_app')).catch(problem=>announce(String(problem)));
    return;
  }
  if (name === 'library-size-menu') { librarySizeOpen=!librarySizeOpen; const control=app.querySelector<HTMLElement>('.library-size-control'); if(control)control.dataset.open=String(librarySizeOpen); app.querySelector('#library-size-button')?.setAttribute('aria-expanded',String(librarySizeOpen)); if(librarySizeOpen)app.querySelector<HTMLElement>('#library-size')?.focus(); return; }
  if (name === 'shell-menu') { shellMenuOpen = !shellMenuOpen; const menu = app.querySelector<HTMLElement>('#shell-menu'); if (menu) menu.hidden = !shellMenuOpen; app.querySelector('#shell-menu-button')?.setAttribute('aria-expanded', String(shellMenuOpen)); if (shellMenuOpen) menu?.querySelector<HTMLElement>('button')?.focus(); return; }
  if (name === 'menu-appearance' || name === 'menu-controls' || name === 'menu-library') { shellMenuOpen=false; settingsCategory=name==='menu-appearance'?'appearance':name==='menu-library'?'library':'gaming'; setView('settings'); return; }
  if (name === 'extras-hdr') { detailsSection='tools'; setView('details'); return; }
  if (name === 'extras-dlss') { void runOperation('update-dlss', true); return; }
  if (name === 'refresh') void refresh();
  if (name === 'clear-search') { query = ''; render(); app.querySelector<HTMLInputElement>('#library-search')?.focus(); }
  if (name === 'bulk-select') { if(presetSelection){action('end-preset-selection');return;} bulkMode=!bulkMode;if(!bulkMode)batchSelection.clear();render();app.querySelector<HTMLElement>('[data-action=bulk-select]')?.focus();return; }
  if (name === 'clear-selection') { batchSelection.clear(); render(); }
  if (name === 'reset-draft') { const game = selectedGame(); if (game) drafts.delete(game.id); render(); app.querySelector<HTMLElement>('[data-action="reset-draft"]')?.focus(); announce('Preview choices reset.'); }
  if (name === 'reset-appearance') { appearance = { ...appearanceDefaults }; applyAppearance(); render(); app.querySelector<HTMLElement>('[data-action="reset-appearance"]')?.focus(); announce('Appearance reset to Clear.'); }
  if (name === 'scan-engine') void getEngineRows().then(() => { render(); announce('Compatibility check completed.'); }).catch(problem => announce(problem.message));
  if(name==='startup-review'&&pendingInstall){void withOperation('Review Installation','prepare_routes',pendingInstall.params,'execute_routes');return;}
  if (name === 'open-split-removal') {
    splitRemove = true;
    splitPackageOpen = false;
    splitQuery = '';
    splitSelected.clear();
    splitMatches.clear();
    void matchSplitGames();
    app.querySelector<HTMLElement>('#page-title')?.focus({ preventScroll: true });
  }
  if (name === 'close-split-removal') {
    splitRemove = false;
    splitMatchRevision++;
    splitMatching = false;
    splitSelected.clear();
    splitMatches.clear();
    render();
    app.querySelector<HTMLElement>('[data-action="open-split-removal"]')?.focus({ preventScroll: true });
  }
  if (name === 'review-nr-addons') void reviewNrPackage().catch(problem => announce(problem.message));
  if (name === 'split-select-all') { for (const game of visibleSplitGames()) splitSelected.add(game.id); render(); }
  if (name === 'split-clear') { splitSelected.clear(); render(); }
  if (name === 'save-split-preset') { void saveSplitPreset(); return; }
  if (name.startsWith('split-tool-')) void applySplitTool(name);
  if (name === 'feeder-character-apply') void applyFeederCharacter();
  if (name === 'operation-back') {
    const origin = operation?.origin || 'details';
    if (origin === 'packages' && operation?.kind === 'remove-nr-addons') {
      splitRemove = false;
      splitSelected.clear();
      splitMatches.clear();
    }
    operation = null; pendingInstall=null; setView(origin);
  }
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
  if (name === 'reset-panel-shortcut' || name === 'disable-panel-shortcut') { const value=name==='disable-panel-shortcut'?'Disabled':snapshot?.preferenceDefaults?.panel_hotkey;if(typeof value==='string'){editOverlayPreference('panel_hotkey',value);render();} }
  if (name === 'inspect-package') void withOperation('Inspect local package', 'package_inspect', { path: packageSource }, 'inspect-package');
  if (name === 'use-package') { const result = operation?.result as Record<string, unknown>; if (result?.token && app.querySelector<HTMLInputElement>('#package-trust')?.checked) void withOperation('Choose package', 'package_use', { token: result.token, trusted: true }, 'inspect'); }
  if (name === 'copy-game-path') { const game=selectedGame(); if(game)void navigator.clipboard.writeText(game.path).then(()=>announce('Location copied.')).catch(()=>announce('Clipboard unavailable.')); }
  if (name === 'official-reshade') { extraKind='reshade'; extraSource=''; void extraAction('review-extra'); }
  if (name === 'review-extra' || name === 'extra-records') void extraAction(name);
  if (name === 'save-notes') { const game = selectedGame(); if (game) void engineRequest('notes_save', { game: game.path, notes: noteDrafts.get(game.id) || '' }).then(() => announce('Game notes saved.')).catch(problem => announce(problem.message)); }
  if (name === 'review-report') { const draft = operation?.result as ReportDraft; if (draft?.reports) void withOperation('Review bug report', 'report_preview', { ids: draft.reports.map(report => report.id), edits: reportEdits, logs: app.querySelector<HTMLInputElement>('#report-logs')?.checked, notes: app.querySelector<HTMLInputElement>('#report-notes')?.checked }); }
  if (name === 'global-review') { const nr = app.querySelector<HTMLSelectElement>('#global-nr')?.value, mfg = app.querySelector<HTMLSelectElement>('#global-mfg')?.value; void withOperation('Review bulk graphics changes', 'global_review', { ...(nr === 'keep' ? {} : { nr: nr === 'true' }), ...(mfg === 'keep' ? {} : { mfg: Number(mfg) }) }); }
  if (name === 'overlay-menu-review') { const values = { ...sharedPreferences, ...preferenceChanges }; void withOperation('Review game menus', 'overlay_ui_review', Object.fromEntries(['optiscaler_ui', 'optiscaler_intro', 'reshade_ui', 'reshade_intro', 'optiscaler_hotkey'].map(key => [key, values[key]]))); }
  if (name === 'overlay-defaults-all') void withOperation('Review applying overlay defaults to every game','settings_review',{changes:{...preferenceChanges,game_overlay_settings:{}}});
  if(name==='overlay-status')void withOperation('Overlay Status','overlay_status',{},'inspect');
  if(name==='overlay-update-report' && snapshot?.overlayReport)showOverlayReport(snapshot.overlayReport);
  if(name==='fix-overlay-report')void fixOverlayReport();
  if (name === 'overlay-package-review') void withOperation('Review overlay packages', 'overlay_package_review', { ...sharedPreferences, ...preferenceChanges });
  if (name === 'storage-inventory') void withOperation('App storage', 'storage_inventory', {}, 'inspect');
  if (name === 'storage-review') void withOperation('Review download cleanup', 'storage_review', {});
  if (name === 'update-check') void withOperation('Check app update', 'update_check', {});
  if (name === 'check-packages') void engineRequest<{catalog: typeof liveCatalog}>('packages').then(result => { liveCatalog = result.catalog; render(); announce('Engine package availability loaded.'); }).catch(problem => announce(problem.message));
  if (name === 'feeder-status') void withOperation('Managed Feeder files', 'feeder_storage', {}, 'inspect');
  if (name === 'feeder-legacy') void withOperation('Get managed DirectX support', 'feeder_storage', { legacy: true }, 'inspect');
  if (name === 'executable-review' || name === 'executable-reset') {
    const game = selectedGame();
    if(!game) return;
    void (async()=>{
      const path = name === 'executable-reset' ? null : '__TAURI_INTERNALS__' in window
        ? await (await import('@tauri-apps/api/core')).invoke<string|null>('choose_path',{kind:'executable'})
        : window.prompt('Game executable path');
      if(name==='executable-review' && !path?.trim()) return;
      const rows = await getEngineRows(game);
      if(!rows[0]) throw new Error('This game could not be inspected.');
      await withOperation('Review game executable','executable_review',{row:rows[0],path});
    })().catch(problem=>announce(problem.message));
  }
  if (['save-game-overlay', 'inherit-game-overlay', 'apply-game-overlay'].includes(name)) {
    const game = selectedGame(); if (!game || !sharedPreferences) return;
    const overrides = { ...(sharedPreferences.game_overlay_settings || {}) as Record<string, Record<string, unknown>> };
    const identity = Object.keys(overrides).find(key => pathKey(key) === pathKey(game.path)) || game.path;
    const changes=overlayPreferenceChanges(sharedPreferences,identity,overrides[identity]||{},gameOverlayDrafts.get(game.id)||{},name!=='inherit-game-overlay'&&app.querySelector<HTMLInputElement>('#overlay-make-default')?.checked===true);
    if (name === 'inherit-game-overlay') { delete overrides[identity];changes.game_overlay_settings=overrides; }
    if (name === 'apply-game-overlay') void withOperation('Review this game’s overlay', 'overlay_package_review', { ...sharedPreferences,...changes,target_games: [game.path] });
    else void withOperation('Review per-game overlay preferences', 'settings_review', { changes });
  }
  if (['artwork-store', 'artwork-reset', 'artwork-sync', 'sgdb-status', 'sgdb-connect', 'sgdb-disconnect', 'sgdb-search'].includes(name)) void artworkAction(name);
}
async function discardReview() {
  const state = operation;
  if (state) state.dismissed = true;
  pendingInstall = null;
  operation = null;
  setView(state?.origin || 'details');
  if (state?.review?.token) {
    const token = state.review.token;
    try { await engineRequest(state.execute === 'execute_routes' ? 'discard_routes' : state.execute === 'run' ? 'discard' : 'discard_operation', state.execute === 'run' ? { token } : { tokens: [token] }); }
    catch (problem) { announce(problem instanceof Error ? problem.message : 'Could not release this review.'); }
  }
}
async function confirmOperation() {
  const state = operation; if (!state?.review || state.stage !== 'review' || state.split?.pending || state.split?.error) return;
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
    engineRows = [];if(state.execute==='steam_install')steamAdded=true;else if(state.execute==='steam_remove')steamAdded=false;
    if (state.refreshOverlaysAfterRepair && !(state.result as Record<string,unknown>)?.cancelled) {
      try {
        const report = await engineRequest<Record<string,unknown>>('overlay_refresh_retry');
        if (snapshot && report.status!=='busy') snapshot.overlayReport = report;
      } catch (problem) { announce(problem instanceof Error ? problem.message : 'Could not refresh overlay results.'); }
    }
    state.stage = 'done';
    if(state.origin === 'presets' && !(state.result as Record<string,unknown>)?.cancelled) { drafts.delete(presetId); presetSelection=false; batchSelection.clear(); }
    if (['settings_review', 'executable_review', 'package_use'].includes(state.method || '') || state.origin === 'presets') {
      try {
        sharedPreferences = await engineRequest<Record<string, unknown>>('settings_get');
        if(state.changedKeys?.includes('game_overlay_settings'))gameOverlayDrafts.clear();
        for (const key of state.changedKeys || []) delete preferenceChanges[key];
        if (snapshot) for (const key of Object.keys(snapshot.defaults)) if (key in sharedPreferences) snapshot.defaults[key] = sharedPreferences[key];
        if(snapshot)snapshot.preferences={...snapshot.preferences,...sharedPreferences};
        if(state.changedKeys?.includes('library_view'))libraryView=sharedPreferences.library_view==='list'?'list':sharedPreferences.library_view==='capsules'?'capsules':'grid';
        if(state.changedKeys?.includes('navigation_position'))appearance.navigation=sharedPreferences.navigation_position==='bottom'?'bottom':'top';
        if(state.changedKeys?.includes('ui_scale'))appearance.scale=sharedPreferences.ui_scale==='auto'?'auto':Number(sharedPreferences.ui_scale);
        if(state.changedKeys?.some(key=>['game_accents','game_hero_focus'].includes(key))){gameAccentDrafts.clear();heroFocusDrafts.clear();await refresh();}
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
    operation.review = { token: summary.token, title: remove?'Remove rtxForge from Steam':'Review Steam shortcut', action: remove?'Remove shortcut':summary.created?'Add to Steam':'Update Steam Shortcut', rows: [{ name: 'rtxForge application shortcut', detail: remove?'Remove the exact existing application shortcut. Game shortcuts remain unchanged.':`Profile: ${summary.profile}. Artwork: ${JSON.stringify(summary.roles)}.` }] };
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
    else if(extraKind==='hdr-custom') await withOperation('Review custom RenoDX add-on','hdr_review',{row,custom_path:extraSource});
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
  document.documentElement.dataset.artworkReady='false';
  loading = true; error = ''; render();
  try {
    const previous=snapshot,firstRead=!snapshot;snapshot = await readSnapshot();
    if(previous)clearArtworkCache(previous);
    performance.mark('library-ready');
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
        item?.querySelectorAll<HTMLImageElement>('.poster>img,.artwork-glow').forEach(image=>{image.src=source;image.style.visibility='';image.hidden=false;image.parentElement?.classList.remove('art-unavailable');});
        item?.querySelector('.artwork-unavailable')?.remove();
      }
    }).then(async()=>{if(snapshot===captured){await resolveLibraryAccents(captured);document.documentElement.dataset.artworkReady='true';performance.mark('artwork-ready');}});
    announce(`Library refreshed. ${snapshot.games.length} games found.`);
  } catch (problem) { error = problem instanceof Error ? problem.message : 'The local reader is unavailable. Refresh to try again.'; announce(error); }
  finally { loading = false; render(); }
}
applyAppearance();

function prepareFocusedBackground(event:Event){
  const card=(event.target as HTMLElement).closest<HTMLElement>('.game-card');
  if(!card||view!=='library'||currentPreferences().online_art===false)return;
  if(event instanceof PointerEvent&&card.contains(event.relatedTarget as Node|null))return;
  clearTimeout(backgroundIntent);
  backgroundIntent=setTimeout(()=>{const game=snapshot?.games.find(game=>game.id===card.dataset.game);if(view==='library'&&game?.appid&&(game.accent||game.artworkAccentReady))void prepareStoreBackground(game.appid,game.id,detailsAccent(game));},250);
}
app.addEventListener('pointerover',prepareFocusedBackground);
app.addEventListener('focusin',prepareFocusedBackground);
for(const name of ['pointerout','focusout'])app.addEventListener(name,event=>{
  const card=(event.target as HTMLElement).closest('.game-card');
  if(card&&!card.contains((event as FocusEvent).relatedTarget as Node|null))clearTimeout(backgroundIntent);
});
document.addEventListener('pointerdown',event=>{
  const target=event.target as HTMLElement;
  if(heroAdjustment&&!target.closest('[data-focal-editor]'))finishHeroAdjustment();
  if(librarySizeOpen&&!target.closest('.library-size-control'))closeLibrarySize(false);
  if(shellMenuOpen&&!target.closest('.shell-more')){shellMenuOpen=false;const menu=app.querySelector<HTMLElement>('#shell-menu');if(menu)menu.hidden=true;app.querySelector('#shell-menu-button')?.setAttribute('aria-expanded','false');}
  if(detailsMenuOpen&&!target.closest('.hero-more')){detailsMenuOpen=false;const menu=app.querySelector<HTMLElement>('.game-menu');if(menu)menu.hidden=true;app.querySelector('[data-action="game-menu"]')?.setAttribute('aria-expanded','false');}
});
document.addEventListener('keydown',event=>{if(event.key==='F11'&&'__TAURI_INTERNALS__' in window){event.preventDefault();action('toggle-window-mode');}});
function closeLibrarySize(restoreFocus=true){librarySizeOpen=false;const control=app.querySelector<HTMLElement>('.library-size-control');if(control)control.dataset.open='false';app.querySelector('#library-size-button')?.setAttribute('aria-expanded','false');if(restoreFocus)app.querySelector<HTMLElement>('#library-size-button')?.focus();}
installInput(() => {
  const reviewInfo = app.querySelector<HTMLElement>('.review-info-popover:popover-open');
  if (reviewInfo) { reviewInfo.hidePopover(); return; }
  const colorCancel=app.querySelector<HTMLButtonElement>('.color-editor:not([hidden]) [data-color-cancel]');if(colorCancel){colorCancel.click();return;} if(heroAdjustment){finishHeroAdjustment(true);return;} if(librarySizeOpen){closeLibrarySize();return;} if(selectMenuOpen()){closeSelectMenu();return;} if(detailsMenuOpen){detailsMenuOpen=false;render();app.querySelector<HTMLElement>('[data-action="game-menu"]')?.focus();return;} if (shellMenuOpen) { shellMenuOpen=false; const menu=app.querySelector<HTMLElement>('#shell-menu'); if(menu)menu.hidden=true; app.querySelector('#shell-menu-button')?.setAttribute('aria-expanded','false'); app.querySelector<HTMLElement>('#shell-menu-button')?.focus(); return; } if (view === 'operation' && operation?.stage === 'running') { announce('The operation is running. Use Request cancellation to stop safely.'); return; } if (view === 'operation' && (operation?.stage === 'review'||operation?.stage==='startup'||operation?.stage==='checking')) { void discardReview(); return; } if(view==='operation'){action('operation-back');return;} if(splitRemove&&view==='packages'){action('close-split-removal');return;} if (view !== 'library') setView('library'); else app.querySelector<HTMLElement>('[data-route="library"]')?.focus(); }, delta => {
  if(app.querySelector('.color-editor:not([hidden])')||heroAdjustment||librarySizeOpen||selectMenuOpen()||shellMenuOpen||detailsMenuOpen||view==='operation'||(splitRemove&&view==='packages'))return;
  const index = tabs.findIndex(tab => tab.id === (view === 'details' ? 'library' : view));
  setView(tabs[(index + delta + tabs.length) % tabs.length].id);
}, (state, id) => { document.documentElement.dataset.controller=String(state); controller = state; controllerId = id || ''; const hint = app.querySelector('#input-hints'); if (hint) hint.innerHTML = hints(); const framing=app.querySelector('#hero-framing-help');if(framing)framing.innerHTML=framingHelp(); }, showHints);
async function initialize(){
  const statusReady=engineStatus().then(status=>{
    backend=status;
    if(status.appearance){settingsCategory='appearance';view='settings';}
    else if(status.preview==='details'){detailsSection='overview';view='details';}
    render();
  }).catch(()=>{backend={enabled:false,reason:'The reviewed host adapter is unavailable. Refresh the local preview.'};});
  if('__TAURI_INTERNALS__' in window){try{
    const saved=await (await import('@tauri-apps/api/core')).invoke<unknown>('appearance_read');
    if(saved){appearance=readAppearance(saved);appearanceStored=JSON.stringify({...appearance,detailsNavigationVersion:1,appearanceDefaultsVersion:2,libraryScaleVersion:1});}
  }catch{appearanceStored=JSON.stringify({...appearance,detailsNavigationVersion:1,appearanceDefaultsVersion:2,libraryScaleVersion:1});announce('Shared appearance is unavailable. Your existing preferences are retained.');}}
  await statusReady;
  appearanceReady=true;applyAppearance();void refreshSystemAccent();await refresh();
}
void initialize();
window.addEventListener('focus',()=>void refreshSystemAccent());
if('__TAURI_INTERNALS__' in window) void import('@tauri-apps/api/event').then(({listen})=>listen<'library'|'details'>('navigate-preview',({payload})=>{
  if(!backend.preview)return;
  if(payload==='details')detailsSection='overview';
  setView(payload);
}));

window.addEventListener('rtxforge-background-ready',()=>applyAppearance());

// The background-activity line, in the same words as the desktop apps (scripts/activity.py).
void watchActivity(text=>{
  const line=document.querySelector<HTMLElement>('#activity');if(!line)return;
  line.querySelector('.activity-text')!.textContent=text;line.hidden=!text;
}).then(stop=>window.addEventListener('pagehide',stop,{once:true}));

if('__TAURI_INTERNALS__' in window)void import('@tauri-apps/api/event').then(async({listen})=>{
  const stop=await listen('navigate-appearance',()=>{settingsCategory='appearance';setView('settings');});
  window.addEventListener('pagehide',stop,{once:true});
});
