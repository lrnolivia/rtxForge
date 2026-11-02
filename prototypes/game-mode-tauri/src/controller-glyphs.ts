export type ControllerFamily = 'xbox' | 'playstation' | 'nintendo' | 'steam' | 'generic';
const labels: Record<ControllerFamily, string[]> = {
  xbox: ['A', 'B', 'LB', 'RB', 'X', 'Y'],
  playstation: ['Cross', 'Circle', 'L1', 'R1', 'Square', 'Triangle'],
  nintendo: ['B', 'A', 'L', 'R', 'Y', 'X'],
  steam: ['A', 'B', 'L1', 'R1', 'X', 'Y'],
  generic: ['South', 'East', 'L', 'R', 'West', 'North'],
};
export const controllerLabels = (family: ControllerFamily) => labels[family] || labels.xbox;
export function controllerGlyph(family: ControllerFamily, index: number) {
  const label = controllerLabels(family)[index];
  if (index === 2 || index === 3) return `<kbd class="pad-shoulder">${label}</kbd>`;
  let art: string;
  if (family === 'playstation') {
    art = index === 0 ? '<path d="m9 9 14 14m0-14L9 23" stroke="#98b8ff"/>'
      : index === 1 ? '<circle cx="16" cy="16" r="9" stroke="#ff8992"/>'
      : index === 4 ? '<rect x="8" y="8" width="16" height="16" rx="1" stroke="#f6a9df"/>'
      : '<path d="m16 6 11 19H5Z" stroke="#73e0bf"/>';
    art = `<circle cx="16" cy="16" r="15" fill="#252b34" stroke="#737b89" stroke-width="1"/><g fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">${art}</g>`;
  } else {
    const color = family === 'xbox' || family === 'steam' ? ({ A: '#65c87a', B: '#ff7a82', X: '#75b9ff', Y: '#f6d15e' } as Record<string,string>)[label] : '#f1f0eb';
    art = `<circle cx="16" cy="16" r="15" fill="${color || '#f1f0eb'}"/><text x="16" y="21.5" text-anchor="middle" fill="#20252b" font-family="Roboto,sans-serif" font-size="17" font-weight="700">${family==='generic'?label[0]:label}</text>`;
  }
  return `<span class="pad-glyph" role="img" aria-label="${label}"><svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">${art}</svg></span>`;
}
