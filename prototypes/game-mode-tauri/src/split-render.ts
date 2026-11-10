import { escape as e } from './model';

export const splitRenderDescription = 'Render the environment and characters with DLSS 5 NR, with a separate character pass where supported.';
export const roles = { environment: 'Environment', character: 'Character detail' } as const;
type Role = keyof typeof roles;
type Slot = { addon: string; model?: string; build?: string };
export type Setup = Partial<Record<Role, Slot>>;
type Combo = Setup & { name: string; builtin: boolean; beside_runtime_nr?: Setup };
export type FeederCharacter = { available: false; reason: string } | {
  available: true; reason?: string; stamp: string; passes: number; nr_enabled: boolean;
  options: { number: number; inherited: boolean; character: boolean; skin: number }[];
};
export type Catalog = {
  addons: { id: string; name: string; builds: { id: string; label: string; default: boolean }[] }[];
  models: { id: string; label: string }[];
  combos: Record<string, Combo>;
  runtime_nr?: { id: string; name: string } | null;
  blocked?: string | null;
  feeder_character?: FeederCharacter;
};
export type Choice = { auto: true; model: string } | { setup: Setup & { beside_runtime_nr?: Setup }; adapt: boolean };
export type Picker = { preset: string; model: string; manualModel: string; manual: Setup };
export const newPicker = (manual: Setup = {}): Picker => ({ preset: '', model: 'new', manualModel: 'new', manual });

export function activeSetup(catalog: Catalog, picker: Picker): Setup {
  const chosen = catalog.combos[picker.preset] ?? picker.manual;
  const setup: Setup = {};
  for (const role of Object.keys(roles) as Role[]) {
    const slot = chosen[role];
    if (slot) setup[role] = slot.addon === 'optiscaler' ? { addon: slot.addon } : { ...slot, model: picker.model };
  }
  if (catalog.runtime_nr) setup.environment = { addon: catalog.runtime_nr.id };
  return setup;
}

export function splitChoice(catalog: Catalog, picker: Picker): Choice | null {
  if (picker.preset === 'auto') return { auto: true, model: picker.model };
  const setup = activeSetup(catalog, picker);
  const beside = catalog.combos[picker.preset]?.beside_runtime_nr;
  return Object.values(setup).some(slot => slot.addon !== 'optiscaler')
    ? { setup: beside ? { ...setup, beside_runtime_nr: beside } : setup, adapt: !!picker.preset }
    : null;
}

export function changePicker(catalog: Catalog, picker: Picker, key: string, value: string, single = false) {
  if (single && key !== 'preset' && picker.preset) {
    picker.manual = activeSetup(catalog, picker);
    picker.manualModel = picker.model;
    picker.preset = '';
  }
  if (key === 'model') {
    picker.model = value;
    if (!picker.preset) picker.manualModel = value;
  } else if (key === 'preset') {
    picker.preset = value;
    const combo = catalog.combos[value];
    picker.model = combo ? combo.environment?.model || combo.character?.model || 'new' : picker.manualModel;
  } else if (key === 'environment' || key === 'character') {
    if (value) picker.manual[key] = { addon: value };
    else delete picker.manual[key];
  } else if (key === 'environment-build' || key === 'character-build') {
    const role = key === 'environment-build' ? 'environment' : 'character';
    const slot = picker.manual[role];
    if (slot) slot.build = value;
  }
}

export function splitPicker(catalog: Catalog, picker: Picker, scope: string, single = false) {
  const option = (value: string, label: string, selected: string) => `<option value="${e(value)}" ${value === selected ? 'selected' : ''}>${e(label)}</option>`;
  const field = (key: string, title: string, choices: string) => `<label class="field"><span><strong>${e(title)}</strong></span><select id="split-${scope}-${key}" data-split-field="${key}">${choices}</select></label>`;
  const preset = field('preset', 'Preset', option('', 'Choose manually', picker.preset)
    + (!single ? option('auto', 'Auto · match each game', picker.preset) : '')
    + Object.entries(catalog.combos).map(([key, combo]) => option(key, combo.name, picker.preset)).join(''));
  const runtime = catalog.runtime_nr;
  const setup = activeSetup(catalog, picker);
  const name = (id?: string) => id === runtime?.id ? runtime?.name : catalog.addons.find(addon => addon.id === id)?.name.split(' (')[0];
  const fields = (Object.keys(roles) as Role[]).map(role => {
    const slot = setup[role];
    const addon = catalog.addons.find(item => item.id === slot?.addon);
    if (role === 'environment' && runtime) return `<p class="field"><strong>Environment</strong><span>${e(runtime.name)}</span></p>`;
    return field(role, roles[role], option('', 'None', slot?.addon ?? '') + catalog.addons.map(item => option(item.id, name(item.id) || item.id, slot?.addon ?? '')).join(''))
      + (single && addon && addon.builds.length > 0 ? field(role + '-build', roles[role] + ' build',
        addon.builds.map(build => option(build.id, build.label, slot?.build || addon.builds.find(item => item.default)?.id || addon.builds[0].id)).join('')) : '');
  }).join('');
  const models = runtime
    ? `<p class="subtle">Both passes use the installed ${e(runtime.name)} model.</p>`
    : `<fieldset class="split-model"><legend>DLSS 5 model</legend>${catalog.models.map(model => `<label class="trust-choice"><input id="split-${scope}-model-${e(model.id)}" type="radio" name="split-${scope}-model" data-split-field="model" value="${e(model.id)}" ${model.id === picker.model ? 'checked' : ''} />${e(model.label.replace(' DLSS 5 (', ' · ').replace(/\)$/, ''))}</label>`).join('')}</fieldset>
      <p class="subtle">Both passes share this model. A game using Skynizz NR keeps its installed model.</p>`;
  const description = picker.preset === 'auto'
    ? 'Choose a compatible setup for each game. Review shows which passes each game will use.'
    : `Environment · ${name(setup.environment?.addon) || 'Installed NR'} · Character detail · ${name(setup.character?.addon) || 'None'}`;
  return `<div class="split-picker" data-split-picker="${scope}">${preset}${picker.preset && !single ? `<p class="subtle">${e(description)}</p>` : fields}${models}</div>`;
}
