type Direction = 'left' | 'right' | 'up' | 'down';
export function moveFocus(direction: Direction): void {
  const scope=(document.querySelector('.select-menu') || document.querySelector('.shell-menu:not([hidden])') || document.querySelector('.game-menu:not([hidden])') || document.querySelector('.operation-flow'))||document;
  const targets = [...scope.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href],summary')]
    .filter(node => node.getClientRects().length && !node.closest('[hidden]'));
  const active = document.activeElement as HTMLElement;
  if (!targets.includes(active)&&(!active?.closest('main')||!active.getClientRects().length)) { (targets.find(node=>node.closest('main'))||targets[0])?.focus(); return; }
  const rect = active.getBoundingClientRect(), x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
  const horizontal = direction === 'left' || direction === 'right';
  const positive = direction === 'right' || direction === 'down';
  const candidates = targets.filter(node => node !== active).map(node => {
    const r = node.getBoundingClientRect(), dx = r.x + r.width / 2 - x, dy = r.y + r.height / 2 - y;
    const major = horizontal ? dx : dy, minor = horizontal ? dy : dx;
    return { node, major, minor, score: Math.abs(major) + Math.abs(minor) * 2.4 };
  }).filter(item => positive ? item.major > 4 : item.major < -4).sort((a, b) => a.score - b.score);
  candidates[0]?.node.focus({ preventScroll: true });
  candidates[0]?.node.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
}
export function installInput(back: () => void, switchTab: (delta: number) => void, connected: (state: boolean, id?: string) => void, activity: () => void = () => {}) {
  document.addEventListener('keydown', event => {
    activity();
    const editing = (event.target as HTMLElement).matches('input,select,textarea');
    if (event.key === 'Escape') { back(); return; }
    if (editing || event.altKey || event.ctrlKey || event.metaKey) return;
    const directions: Record<string, Direction> = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' };
    if (directions[event.key]) { event.preventDefault(); moveFocus(directions[event.key]); }
    if (event.key === '[' || event.key === ']') { event.preventDefault(); switchTab(event.key === '[' ? -1 : 1); }
  });
  let active = false, frame = 0, lastTime = 0;
  const previous = new Set<number>();
  function poll(time: number) {
    if (!active) return;
    const pad = [...navigator.getGamepads()].find(Boolean);
    if (pad) {
      const pressed = new Set(pad.buttons.map((button, i) => button.pressed ? i : -1).filter(i => i >= 0));
      if (pad.axes[0] < -.55) pressed.add(14);
      if (pad.axes[0] > .55) pressed.add(15);
      if (pad.axes[1] < -.55) pressed.add(12);
      if (pad.axes[1] > .55) pressed.add(13);
      for (const index of pressed) {
        const repeat = index >= 12 && time - lastTime > 180;
        if (previous.has(index) && !repeat) continue;
        activity();
        if (index === 0) (document.activeElement as HTMLElement)?.click();
        else if (index === 1) back();
        else if (index === 4 || index === 5) switchTab(index === 4 ? -1 : 1);
        else if (index >= 12 && index <= 15) {
          const field = document.activeElement;
          if (field instanceof HTMLSelectElement && (index === 14 || index === 15)) {
            field.selectedIndex = Math.max(0, Math.min(field.options.length - 1, field.selectedIndex + (index === 14 ? -1 : 1)));
            field.dispatchEvent(new Event('change', { bubbles: true }));
          } else moveFocus(({ 12: 'up', 13: 'down', 14: 'left', 15: 'right' } as const)[index as 12]);
        }
        lastTime = time;
      }
      previous.clear(); pressed.forEach(index => previous.add(index));
    }
    frame = requestAnimationFrame(poll);
  }
  function sync() {
    const selected = [...navigator.getGamepads?.() || []].find(Boolean);
    const hasPad = Boolean(selected);
    connected(hasPad, selected?.id);
    const shouldPoll = hasPad && !document.hidden && document.hasFocus();
    if (shouldPoll && !active) { active = true; frame = requestAnimationFrame(poll); }
    if (!shouldPoll && active) { active = false; cancelAnimationFrame(frame); previous.clear(); }
  }
  window.addEventListener('gamepadconnected', sync);
  window.addEventListener('gamepaddisconnected', sync);
  window.addEventListener('focus', sync);
  window.addEventListener('blur', sync);
  window.addEventListener('pointerdown', activity);
  document.addEventListener('visibilitychange', sync);
  sync();
}
