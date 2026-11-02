type Values = Record<string, unknown>;
export function mergeOverlay(defaults: Values, local: Values = {}, draft: Values = {}): Values {
  return {...defaults, ...local, ...draft, overlay_appearance: {
    ...defaults.overlay_appearance as Values, ...local.overlay_appearance as Values,
    ...draft.overlay_appearance as Values,
  }};
}
export function overlaySurface(glass: Values): 'clear' | 'light' | 'dark' {
  return glass.Theme === 4 ? Number(glass.AccentCharacter) < 20 ? 'clear'
    : Number(glass.AccentCharacter) < 72 ? 'light' : 'dark'
    : glass.Theme === 1 ? 'light' : glass.Theme === 2 ? 'dark' : 'clear';
}
export function surfaceChanges(glass: Values, base: string, tint: boolean, themes: Record<string, Values> = {}): Values {
  const mode = tint ? 'accent' : base;
  const defaults = themes[mode] || {};
  const material = Object.fromEntries(['Custom','LightTint','DarkTint','ClearTint','AccentTint','Blur','Grain','BlendStrength','SurfaceBlend','InvertDark','TextDepth'].filter(key => key in defaults).map(key => [key,defaults[key]]));
  return {...glass, ...material, Theme: tint ? 4 : base === 'light' ? 1 : base === 'dark' ? 2 : 3,
    ...(tint ? {AccentCharacter: base === 'light' ? 50 : base === 'dark' ? 100 : 10,
      AccentSaturation: base === 'dark' ? 94 : 200} : {})};
}
export function overlayPreferenceChanges(shared: Values, game: string, local: Values, draft: Values, makeDefault = false): Values {
  const overrides = {...shared.game_overlay_settings as Record<string,Values>};
  overrides[game] = {...local, ...draft, ...(draft.overlay_appearance ? {overlay_appearance: {
    ...local.overlay_appearance as Values, ...draft.overlay_appearance as Values,
  }} : {})};
  return {game_overlay_settings: overrides, ...(makeDefault ? draft : {})};
}
