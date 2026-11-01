import { completeArtwork } from './artwork';
export type View = 'library' | 'presets' | 'details' | 'packages' | 'extras' | 'settings' | 'operation';
export type Theme = 'clear' | 'light' | 'dark';
export interface Game { id: string; name: string; path: string; appid: string | null; source: string; status: string; art: string | null; hero?: string | null; capsule?: string | null; description?: string; developers?: string[] | string; release?: string; accent?: string; artworkAccent?: string | null; localArtwork?: string[]; heroFocus?: [number,number]; testStatus?: string; notes?: string; testActive?: boolean; savedRecord?: Record<string,unknown> }
export interface Package { id: string; name: string; version: string; repository: string; sha256: string; status: string }
export interface Snapshot {
  schema: number; source: string; platform: string; readOnly: boolean; capturedAt: string;
  games: Game[]; packages: Package[]; warnings: string[]; libraryCount: number; settingsFound: boolean;
  defaults: Record<string, unknown>; operations: { available: boolean; reason: string };
  preferences?: Record<string, unknown>; overlayDefaults?: Record<string, unknown>; overlayThemes?: Record<string, Record<string, unknown>>;
  overlayReport?: Record<string, unknown> | null;
  preferenceDefaults?: Record<string, unknown>;
  hardware?: Record<string, unknown>;
  controlSchema?: { groups: {name: string}[]; controls: {key: string; label: string; advanced?: string; group: string; kind: string; min: number; max: number; default: number; values?: number[]; choices?: string[]; step?: number; unit?: string}[] };
  catalog?: (Record<string, unknown> & {id: string; name: string; version: string})[];
}
export interface Appearance { theme: Theme; tint: boolean; accent: string; motion: boolean; text: 'standard' | 'large'; navigation: 'top' | 'bottom'; detailsNavigation: 'tabs' | 'sidebar'; scale: 'auto' | number; background?:string }
export const appearanceDefaults: Appearance = { theme: 'clear', tint: true, accent: '#d8d5ce', motion: true, text: 'standard', navigation: 'top', detailsNavigation: 'sidebar', scale: 'auto' };
export function readAppearance(): Appearance {
  try {
    const value = JSON.parse(localStorage.getItem('rtxforge-game-mode-prototype') || '{}');
    return { theme: ['clear', 'light', 'dark'].includes(value.theme) ? value.theme : 'clear',
      ...(typeof value.background==='string'&&value.background.length<1600000&&/^data:image\/(png|jpeg|webp);base64,[a-z0-9+/=]+$/i.test(value.background)?{background:value.background}:{}),
      tint: value.appearanceDefaultsVersion===2 ? value.tint === true : true, accent: /^#[0-9a-f]{6}$/i.test(value.accent) && !(value.appearanceDefaultsVersion!==2&&value.accent.toLowerCase()==='#f2cf5a') ? value.accent : appearanceDefaults.accent,
      motion: value.motion !== false, text: value.text === 'large' ? 'large' : 'standard', navigation: value.navigation === 'bottom' ? 'bottom' : 'top', detailsNavigation: value.detailsNavigationVersion===1&&value.detailsNavigation==='tabs'?'tabs':'sidebar', scale: [100, 125, 130, 150, 175, 200].includes(value.scale) ? value.scale : 'auto' };
  } catch { return { ...appearanceDefaults }; }
}
export function escape(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]!));
}
export async function readSnapshot(): Promise<Snapshot> {
  let result: Snapshot;
  if ('__TAURI_INTERNALS__' in window) {
    const { invoke } = await import('@tauri-apps/api/core');
    result = await invoke<Snapshot>('snapshot');
  } else {
    const response = await fetch('/api/snapshot', { cache: 'no-store' });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || 'The library reader is unavailable. Try refreshing.');
    result = body;
  }
  if (result.schema !== 1 || !Array.isArray(result.games) || !Array.isArray(result.packages)) throw new Error('The local reader uses an unsupported snapshot format.');
  return completeArtwork(result);
}
