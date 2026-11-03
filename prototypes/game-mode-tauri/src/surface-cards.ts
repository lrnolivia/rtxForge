export function surfaceCards(
  selected: string,
  action: 'theme-choice' | 'overlay-surface',
  label: string,
  icon: (name: 'check') => string,
  disabled = false,
) {
  return `<div class="theme-options" role="group" aria-label="${label}">${['light', 'clear', 'dark'].map(theme => `
    <button class="theme-choice theme-${theme}" data-${action}="${theme}" aria-pressed="${selected === theme}" ${disabled ? 'disabled' : ''}>
      <span class="material-sample" aria-hidden="true"><i></i><i></i></span>
      <span>${theme[0].toUpperCase() + theme.slice(1)}</span>
      ${selected === theme ? icon('check') : ''}
    </button>`).join('')}</div>`;
}
