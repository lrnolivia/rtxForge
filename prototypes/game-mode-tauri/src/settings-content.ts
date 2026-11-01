import { escape as e, type Game } from './model';

export const settingsSections = [
  ['graphics','Graphics','cpu'], ['overlay','Overlay','sliders'], ['appearance','Appearance','palette'],
  ['library','Library','books'], ['gaming','Gaming Mode','controller'], ['system','System','gear'],
  ['recovery','Recovery','refresh'], ['about','About','info'],
] as const;

interface Context {
  category: string; preferences: Record<string, unknown>; changes: Record<string, unknown>;
  glassDefaults: Record<string, unknown>; enabled: boolean; platform?: string;
  icon: (name: string) => string; gridConnected: boolean | null;
  games: Game[]; reportSelection: Set<string>; overlayReport?: Record<string, unknown> | null; hardware?: Record<string,unknown>;
}

// The same 180×104 screen diagrams as the desktop OverlayLayoutPicker.
export function layoutDiagram(layout: string, side = 'left', barPosition = 'bottom') {
  const shape = (x:number,y:number,w:number,h:number,alpha=.16,accent=false,radius=3) =>
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${radius}" fill="${accent?'var(--accent)':'currentColor'}" opacity="${alpha}"/>`;
  let shapes = shape(0,0,180,104,.06,false,7);
  if (layout === 'floating') {
    shapes += shape(12,10,53,84,.15,false,5)+shape(20,18,26,4,1,true);
    for(let row=0;row<3;row++) shapes += shape(20,30+row*18,37,12,.22);
    shapes += shape(72,39,34,43,.11,false,5);
  } else if(layout === 'centered') {
    shapes += shape(26,16,128,72,.15,false,5)+shape(34,24,25,4,1,true);
    for(let row=0;row<4;row++) shapes += shape(34,37+row*10,25,4,.25);
    shapes += shape(69,25,76,19,.22)+shape(69,51,34,27,.17)+shape(110,51,35,27,.17);
  } else {
    shapes += shape(14,74,152,19,.18,false,5)+shape(23,81,26,4,1,true);
    for(let col=0;col<3;col++) shapes += shape(61+col*31,80,24,6,.28);
    shapes += shape(92,27,55,39,.14,false,5)+shape(102,35,26,4,.7,true)+shape(102,46,35,11,.22);
  }
  const transform = layout === 'floating' && side === 'right' ? 'translate(180 0) scale(-1 1)'
    : layout === 'bar' && barPosition === 'top' ? 'translate(0 104) scale(1 -1)' : '';
  return `<svg viewBox="0 0 180 104" aria-hidden="true" focusable="false"><g${transform?` transform="${transform}"`:''}>${shapes}</g></svg>`;
}

export function settingsContent(c: Context) {
  const values = {...c.preferences,...c.changes};
  const glass = {...c.glassDefaults,...values.overlay_appearance as Record<string,unknown>};
  const disabled = c.enabled ? '' : 'disabled';
  const group = (title:string,description:string,rows:string,wide=false) => `<section class="glass-section setting-group${wide?' setting-group-wide':''}"><h2>${title}</h2>${description?`<p>${description}</p>`:''}<div class="inner-card">${rows}</div></section>`;
  const choice = (key:string,title:string,options:[unknown,string][],help='',attribute='data-preference',value=values[key]) => {
    const known = options.some(([option])=>JSON.stringify(option)===JSON.stringify(value));
    return `<label class="field"><span><strong>${title}</strong>${help?`<small>${help}</small>`:''}</span><select ${attribute}="${key}" aria-label="${title}" ${disabled}>${known?'':'<option value="" selected disabled>Not saved</option>'}${options.map(([option,label])=>`<option value="${e(JSON.stringify(option))}" ${JSON.stringify(option)===JSON.stringify(value)?'selected':''}>${label}</option>`).join('')}</select></label>`;
  };
  const toggle = (key:string,title:string,help='') => `<div class="field"><span><strong id="pref-${key}">${title}</strong>${help?`<small>${help}</small>`:''}</span><button class="toggle" role="switch" aria-labelledby="pref-${key}" aria-checked="${values[key]===true}" data-preference-toggle="${key}" ${disabled}><span></span></button></div>`;
  const action = (title:string,name:string,help='',glyph='arrow',enabled=true) => `<button class="setting-action" data-action="${name}" ${c.enabled&&enabled?'':'disabled'}>${c.icon(glyph)}<span><strong>${title}</strong>${help?`<small>${help}</small>`:''}</span>${c.icon('arrow')}</button>`;
  const glassChoice=(key:string,title:string,options:[unknown,string][])=>choice(key,title,options,'','data-glass',glass[key]);
  const leaf=(path:unknown)=>String(path).split(/[\\/]/).filter(Boolean).pop()||String(path);
  const folderRows=(paths:unknown,empty:string)=>Array.isArray(paths)&&paths.length?`<div class="folder-list">${paths.map(path=>`<div class="folder-row">${c.icon('folder')}<span><strong>${e(leaf(path))}</strong><small title="${e(path)}">${e(path)}</small></span></div>`).join('')}</div>`:`<p class="settings-empty">${empty}</p>`;
  const onOff: [unknown,string][]=[[1,'On'],[0,'Off']];
  const steamActions=action('Add rtxForge to Steam','steam-review','Review the shortcut and artwork before adding.','controller')+action('Remove rtxForge from Steam','steam-remove-review','Review the existing shortcut before removing.','controller');
  let body='';
  if(c.category==='graphics') {
    body=group('Install defaults','Applied to new installs; game changes are reviewed first.',
      choice('default_profile','Default mode',[['nr-only','NR Only'],['mfg-only','MFG Only'],['nr-mfg','NR + MFG']],'Features selected when rtxForge starts.')+
      toggle('nr_on_launch','Enable NR on launch','Leave off to enable NR later from the overlay.')+
      toggle('manage_dlss_files','Update DLSS files','Keep backups when updating older DLSS files.')+
      (c.platform==='Windows'?toggle('borderless_4k','Borderless on install','Use borderless in supported games, keeping their current resolution.'):'')+
      toggle('vulkan_experimental','Universal Experimental Vulkan','Opt in to the profiled BG3/RDR2 native Vulkan package. Gameplay qualification remains experimental.'))+
      group('Existing features','Register compatible feature packages already installed.',toggle('recognize_previous','Recognize existing features','Allow updates to compatible installations from other tools.'))+
      group('Global NR / MFG','One-time changes to installed games. Future install defaults stay separate.',
        `<label class="field"><span><strong>NR</strong></span><select id="global-nr" ${disabled}><option value="keep">Leave unchanged</option><option value="true">On</option><option value="false">Off</option></select></label><label class="field"><span><strong>MFG</strong></span><select id="global-mfg" ${disabled}><option value="keep">Leave unchanged</option><option value="-1">Automatic</option><option value="0">Off</option>${[2,3,4,5,6].map(n=>`<option value="${n}">${n}×</option>`).join('')}</select></label>`+action('Review bulk graphics changes','global-review','Review each target and skipped game.','sliders'));
  }
  if(c.category==='overlay') {
    const layouts=[['floating','Side Panel'],['centered','Advanced'],['bar','Bar']];
    const theme=({1:'light',2:'dark',3:'clear',4:'accent'} as Record<string,string>)[String(glass.Theme)] || values.overlay_theme;
    const layoutPicker=`<div class="layout-picker"><strong>Layout</strong><p>Choose how controls are arranged in your game.</p><div class="overlay-layout-choices" role="group" aria-label="Overlay layout">${layouts.map(([key,label])=>`<button class="layout-choice" data-overlay-layout="${key}" aria-label="${label}" aria-pressed="${glass.Layout===key}" ${disabled}>${layoutDiagram(key,String(glass.SidePanelSide||'left'),String(glass.BarPosition||'bottom'))}<span>${label}</span>${glass.Layout===key?c.icon('check'):''}</button>`).join('')}</div></div>`;
    // Older engine snapshots do not accept position keys in reviewed preferences.
    const position = glass.Layout==='floating' && Object.hasOwn(c.glassDefaults,'SidePanelSide')
      ? choice('SidePanelSide','Side Panel position',[['left','Left'],['right','Right']],'Choose which edge the Side Panel opens on.','data-glass',glass.SidePanelSide||'left')
      : glass.Layout==='bar' && Object.hasOwn(c.glassDefaults,'BarPosition')
        ? choice('BarPosition','Bar position',[['bottom','Bottom'],['top','Top']],'Open the Bar at the top or bottom of the screen.','data-glass',glass.BarPosition||'bottom') : '';
    body=group('rtxForge panel','',choice('overlay_renderer','Primary overlay',[['game','rtxForge'],['optiscaler','Native']],'Use the rtxForge panel in compatible packages, or the original OptiScaler, Feeder or ReShade menus.')+layoutPicker+position,true)+
      group('Appearance','',`<div class="field"><span><strong>Theme</strong><small>Selecting a theme restores its material defaults.</small></span><div class="overlay-theme-segments" role="group" aria-label="Overlay theme">${['clear','light','dark','accent'].map(mode=>`<button data-overlay-theme="${mode}" aria-pressed="${theme===mode}" ${disabled}>${mode[0].toUpperCase()+mode.slice(1)}</button>`).join('')}</div></div>`+
        (theme==='accent'?`<label class="field"><span><strong>Accent character</strong><small>Clear → Light → Dark</small></span><input type="range" data-glass-range="AccentCharacter" min="0" max="100" step="1" value="${e(glass.AccentCharacter)}" aria-label="Accent character" ${disabled}/></label>`:'')+
        glassChoice('TextSize','Text size',[[18,'Aa Smaller'],[22,'Aa Default'],[26,'Aa Larger']])+glassChoice('Motion','Motion effects',onOff))+
      group('Status and notifications','',glassChoice('ShowNotifications','Hotkey notifications',onOff)+toggle('overlay_live_stats','Live feature statistics','Measured activity beside NR and frame generation controls.')+toggle('overlay_welcome','Welcome message','Show the rtxForge logo and assigned shortcut at game startup.')+choice('overlay_welcome_position','Welcome position',[['top-center','Top center'],['top-left','Top left'],['top-right','Top right'],['bottom-left','Bottom left'],['bottom-right','Bottom right']],'Applies when the game starts.'))+
      group('Shortcuts and helper','',`<label class="field"><span><strong>rtxForge shortcut</strong><small>Choose an unused key or combination. Other overlays keep their shortcuts.</small></span><input id="panel-shortcut" aria-label="Panel shortcut" value="${e(values.panel_hotkey)}" ${disabled}/></label><div class="shortcut-actions"><button class="quiet" data-action="reset-panel-shortcut" ${disabled}>Reset</button><button class="quiet" data-action="disable-panel-shortcut" ${disabled}>Disable</button></div>`+toggle('overlay_helper','Background overlay helper','Keep saved presets and panel settings available after closing the manager.')+(c.platform==='Windows'?toggle('overlay_start_with_windows','Start helper with Windows','Starts the helper for the rtxForge panel.'):'') )+
      group('OptiScaler','Menu access and the welcome message are independent.',toggle('optiscaler_ui','OptiScaler menu','Keep NR and MFG installed when the menu is off.')+choice('optiscaler_hotkey','OptiScaler shortcut',[['Insert','Insert'],['F8','F8'],['Disabled','Disabled']],'Applies next game launch.')+toggle('optiscaler_intro','OptiScaler intro','Startup message only.'))+
      group('ReShade','Menu access and the welcome message are independent.',toggle('reshade_ui','ReShade menu','Feeder NR and effects keep running when this is off.')+toggle('reshade_intro','ReShade welcome','ReShade guide and RenoDX welcome dialog. Loading notices are separate.'))+
      group('Vulkan MFG overlay','',toggle('vulkan_mfg_native_menu','Native MFG menu and hint','Optional advanced menu. Frame generation keeps running when it is off.'))+
      group('Apply to games','Menu and welcome changes take effect next launch.',action('Update Overlays','overlay-package-review','Review overlay packages, menus, welcome messages and shortcuts for every installed game.','sliders')+action('Review game menus','overlay-menu-review','Review the native menu choices for installed games.','sliders')+`<details class="last-overlay-update"><summary>Last overlay update</summary>${overlayUpdate(c.overlayReport)}</details>`);
  }
  if(c.category==='library') body=group('Library view','',choice('library_view','Library layout',[['posters','Posters'],['capsules','Wide Capsule'],['list','List']]))+
    group('Artwork and game information','',toggle('online_art','Download missing artwork','Cached images stay available offline.')+toggle('steam_metadata','Download game information','Descriptions, developers, and release dates from Steam.')+action('Refresh artwork','library-art-refresh','Refresh the artwork for your library.','refresh'))+
    group('Steam integration','',action('Sync artwork to Steam','library-art-sync','Review and sync artwork for your library.','books')+action('Steam artwork profile','steam-art-profiles','Choose which local Steam account receives artwork.','controller')+steamActions)+
    group('SteamGridDB','Connect your account to browse custom artwork.',`<div class="connection-status">${c.icon(c.gridConnected?'check':'info')}<p>${c.gridConnected===null?'Connection has not been checked.':c.gridConnected?'Account connected.':'Account disconnected.'}</p></div>${c.gridConnected?'':`<label class="connection-key"><span>API key</span><input id="sgdb-key" type="password" autocomplete="off" aria-label="SteamGridDB API key" ${disabled}/></label>`}<div class="connection-actions"><button class="quiet" data-action="sgdb-status" ${disabled}>Check connection</button>${c.gridConnected?`<button class="quiet" data-action="sgdb-disconnect" ${disabled}>Disconnect</button>`:`<button class="primary" data-action="sgdb-connect" ${disabled}>Connect</button>`}</div>`)+
    group('Library folders','Add one game, or a library containing several games.',`<div class="folder-section"><strong>Game folders</strong>${folderRows(values[c.platform==='Windows'?'game_folders':'extra_folders'],'No game folders added.')}<button class="quiet" data-action="add-game-folder" ${disabled}>${c.icon('plus')}Add game folder</button></div><div class="folder-section"><strong>Library folders</strong>${folderRows(values.library_folders,'No library folders added.')}<button class="quiet" data-action="add-library-folder" ${disabled}>${c.icon('plus')}Add library folder</button></div>`)+
    group('Removed games','Show an entry again without changing its files or recovery backups.',Array.isArray(values.removed_games)&&values.removed_games.length?`<div class="removed-games">${values.removed_games.map(path=>`<div class="removed-game"><span><strong>${e(leaf(path))}</strong><small title="${e(path)}">${e(path)}</small></span><button class="quiet" data-show-game="${e(path)}" aria-label="Show ${e(leaf(path))} again" ${disabled}>Show again</button></div>`).join('')}</div>`:'<p class="settings-empty">No removed games.</p>');
  if(c.category==='gaming') body=group('Interface','Mouse, keyboard, and controller input keep your chosen interface.',`<div class="field"><span><strong>Interface</strong><small>The Desktop interface remains in the existing native application.</small></span><span class="state-label">Gaming Mode</span></div>`)+
    group('Layout and labels','',choice('ui_scale','Game Mode scale',[['auto','Automatic'],[100,'100%'],[125,'125%'],[130,'130%'],[150,'150%'],[175,'175%'],[200,'200%']],'Automatic uses a 130% reference at 4K and adapts to the window.')+choice('navigation_position','Navigation placement',[['top','Top'],['bottom','Bottom']])+toggle('button_glyphs','Button glyphs','Show icons beside action labels.'))+
    group('Controller','',choice('controller_glyphs','Controller labels',[['auto','Automatic'],['xbox','Xbox'],['playstation','PlayStation'],['nintendo','Nintendo'],['steam','Steam Controller'],['generic','Generic']],'Match your controller family.')+choice('controller_hints','Controller hints',[['always','Always visible'],['auto','Hide when idle']])+`<details class="input-reference"><summary>${c.icon('controller')}Controller buttons</summary><dl><dt>Move</dt><dd>D-pad / left stick</dd><dt>Select / Back</dt><dd>Accept / Back button</dd><dt>Switch pages</dt><dd>LB / RB</dd><dt>Adjust a value</dt><dd>D-pad left / right</dd></dl></details><details class="input-reference"><summary>${c.icon('keyboard')}Keyboard shortcuts</summary><dl><dt>Move</dt><dd>Arrow keys / Tab</dd><dt>Select</dt><dd>Enter</dd><dt>Back</dt><dd>Escape</dd><dt>Switch pages</dt><dd>[ / ]</dd></dl></details>`)+group('Steam integration','',steamActions);
  if(c.category==='system') body=group('Hardware','',`<dl class="hardware-facts"><dt>Graphics card</dt><dd>${e(c.hardware?.gpu||'Unavailable')}</dd><dt>Driver</dt><dd>${e(c.hardware?.driver||'Unavailable')}</dd></dl>`)+(c.platform==='Windows'?group('App storage','Restore backups, original game files and settings are kept.',action('Inspect app storage','storage-inventory','','folder')+action('Review download cleanup','storage-review','','wrench')):'');
  if(c.category==='recovery') body=group('Previous changes','Browse available original-file recovery records.',action('Previous changes','recoveries','Review earlier changes before restoring.','refresh'))+group('Cleanup','',action('Old NR files','cleanup-review','Review legacy files before removal. Every file is backed up first.','wrench'));
  if(c.category==='about') body=group('App and updates','This isolated prototype does not replace the installed application.',`<div class="field"><span><strong>Automatic updates</strong><small>Available in the installed application. This prototype never installs an app update.</small></span><button class="toggle" role="switch" aria-label="Automatic updates" aria-checked="${values.auto_update===true}" disabled><span></span></button></div>`+action('Check for updates','update-check','Check the existing application’s update source.','refresh',c.platform==='Windows'))+
    group('Report a bug','Choose games, say what happened and review a redacted ZIP before anything is saved.',`<details class="report-game-picker"><summary>Choose games (${c.reportSelection.size} selected)</summary>${c.games.map(game=>`<label><input type="checkbox" data-support-game="${e(game.id)}" ${c.reportSelection.has(game.id)?'checked':''} ${disabled}/><span>${e(game.name)}</span></label>`).join('')}</details>`+action('Prepare bug report','support-report','Review facts and choose whether to include logs or notes.','warning',c.reportSelection.size>0));
  return `<div class="settings-groups">${body}</div>`;
}

function overlayUpdate(report?:Record<string,unknown>|null) {
  if(!report) return '<p>No saved overlay update report is available.</p>';
  const list=(key:string,label:string)=>Array.isArray(report[key])?(report[key] as Record<string,unknown>[]).map(row=>`<p><strong>${label} · ${e(row.title||row.name)}</strong>${row.detail?`<br>${e(row.detail)}`:''}</p>`).join(''):'';
  return `<p>${e(report.updated??0)} updated · ${Array.isArray(report.skipped)?report.skipped.length:0} already current</p>${report.error?`<p>${e(report.error)}</p>`:''}${list('updated_games','Updated')}${list('blocked','Needs repair')}`;
}
