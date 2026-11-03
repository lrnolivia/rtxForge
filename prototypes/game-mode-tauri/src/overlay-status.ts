import {escape as e} from './model';
export interface OverlayStatus {
  currentVersion?: string;
  games: {game:string;name:string;installedVersion?:string|null;currentVersion?:string|null;status:string;lastUpdated?:string|null;detail?:string}[];
  warnings?: string[];
}
export function overlayStatusView(status:OverlayStatus) {
  const labels:Record<string,string>={'current':'Current','update-available':'Update available','needs-attention':'Needs attention','unknown':'Version unknown','unavailable':'Unavailable'};
  return `<section class="glass-section"><h2>Installed overlays</h2>${status.games.length?`<div class="inner-card overlay-status-list">${status.games.map(game=>{
    const date=game.lastUpdated?new Date(game.lastUpdated):null;
    return `<article class="detail-action-row"><div><strong>${e(game.name)}</strong><p>${e(game.installedVersion||'Version not recorded')}${game.currentVersion?' · Latest '+e(game.currentVersion):''}</p><small>Last updated: ${date&&!Number.isNaN(date.valueOf())?e(date.toLocaleString()):'Not recorded'}</small>${game.detail?`<p>${e(game.detail)}</p>`:''}</div><span class="state-label">${e(labels[game.status]||labels.unknown)}</span></article>`;
  }).join('')}</div>`:'<p>No managed overlays were found.</p>'}${status.warnings?.map(warning=>`<p>${e(warning)}</p>`).join('')||''}<div class="operation-actions extra-actions"><button class="primary" data-action="overlay-package-review" ${status.games.length?'':'disabled'}>Update all</button><button class="quiet" data-action="operation-back">Close</button></div></section>`;
}
