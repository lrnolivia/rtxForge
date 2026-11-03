type Direction = 'left' | 'right' | 'up' | 'down';
export function moveFocus(direction: Direction): void {
  const scope=(document.querySelector('.color-editor:not([hidden])') || document.querySelector('.select-menu') || document.querySelector('.library-size-control[data-open=true]') || document.querySelector('.shell-menu:not([hidden])') || document.querySelector('.game-menu:not([hidden])') || document.querySelector('.operation-flow'))||document;
  const targets = [...scope.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href],summary')]
    .filter(node => node.getClientRects().length && !node.closest('[hidden]'));
  const active = document.activeElement as HTMLElement;
  if (!targets.includes(active)&&(!active?.closest('main')||!active.getClientRects().length||!scope.contains(active))) { (targets.find(node=>node.closest('main'))||targets[0])?.focus(); return; }
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
    const focalField=event.target as HTMLInputElement;
    if(focalField.matches('[data-hero-focus]')&&(event.key==='ArrowUp'||event.key==='ArrowDown')){
      event.preventDefault();
      document.querySelector<HTMLElement>(`[data-hero-focus="${event.key==='ArrowDown'?1:0}"]`)?.focus();
      return;
    }
    const editing = (event.target as HTMLElement).matches('input,select,textarea');
    if (event.key === 'Escape') { back(); return; }
    if (editing || event.altKey || event.ctrlKey || event.metaKey) return;
    const directions: Record<string, Direction> = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' };
    if (directions[event.key]) { event.preventDefault(); moveFocus(directions[event.key]); }
    if (event.key === '[' || event.key === ']') { event.preventDefault(); switchTab(event.key === '[' ? -1 : 1); }
  });
  let active = false, frame = 0, padIndex: number | undefined;
  let heldDirection = 0, repeatAt = 0, lastFrame = 0;
  const scrollWithStick = (axis: number, elapsed: number) => {
    const magnitude = Math.abs(axis);
    if (magnitude < .22) return;
    const modal = document.querySelector('.operation-modal');
    const candidates = modal ? [modal.querySelector('.flow-body'), modal] :
      [document.querySelector('#game-results'), document.querySelector('.details-scroll'), document.querySelector('#content')];
    const pane = candidates.find((node): node is HTMLElement => node instanceof HTMLElement && node.scrollHeight > node.clientHeight + 1);
    const speed = ((magnitude - .22) / .78) ** 1.5 * 1050;
    if(pane) pane.scrollTop += Math.sign(axis) * Math.max(1, speed * elapsed / 1000);
  };
  const directionKey = {12:'up',13:'down',14:'left',15:'right'} as const;
  const readPads = () => Array.from(navigator.getGamepads?.() ?? []).filter((pad): pad is Gamepad =>
    Boolean(pad && (pad.mapping === 'standard' || (!pad.mapping && pad.buttons.length >= 16 && pad.axes.length >= 2))));
  const seedFocus = () => {
    const focused = document.activeElement;
    if (focused instanceof HTMLElement && focused !== document.body && focused.getClientRects().length) return false;
    const firstCard = document.querySelector<HTMLElement>('#game-results .game-card');
    if (firstCard) firstCard.focus(); else moveFocus('down');
    return true;
  };
  const previous = new Set<number>();
  function poll(time: number) {
    if (!active) return;
    const elapsed=lastFrame ? Math.min(time-lastFrame,40) : 16; lastFrame=time;
    const pads = readPads();
    const engaged = pads.find(pad => pad.buttons.some(button => button.pressed) || Math.max(Math.abs(pad.axes[0] ?? 0),Math.abs(pad.axes[1] ?? 0),Math.abs(pad.axes[3] ?? 0)) > .6);
    const pad = engaged ?? pads.find(pad=>pad.index===padIndex) ?? pads[0];
    if (pad) {
      if (pad.index !== padIndex) {
        padIndex = pad.index; previous.clear(); heldDirection = 0;
        connected(true,pad.id);
      }
      const pressed = new Set(pad.buttons.map((button, i) => button.pressed ? i : -1).filter(i => i >= 0));
      const x=pad.axes[0] ?? 0, y=pad.axes[1] ?? 0;
      const dpad=[12,13,14,15].find(index=>pressed.has(index));
      const threshold=heldDirection ? .43 : .6;
      const stick=Math.abs(x)>=Math.abs(y) ? (Math.abs(x)>=threshold?(x<0?14:15):0) : (Math.abs(y)>=threshold?(y<0?12:13):0);
      for (const index of [12,13,14,15]) pressed.delete(index);
      const direction=dpad ?? stick;
      scrollWithStick(pad.axes[3] ?? 0,elapsed);
      if(direction)pressed.add(direction);
      if(direction!==heldDirection){heldDirection=direction;repeatAt=time+320;}
      for (const index of pressed) {
        const repeat = index===direction && time>=repeatAt;
        if (previous.has(index) && !repeat) continue;
        if (repeat) repeatAt=time+110;
        activity();
        if ((index===0||index===direction) && seedFocus()) continue;
        if (index === 0) (document.activeElement as HTMLElement)?.click();
        else if (index === 1) back();
        else if (index === 4 || index === 5) switchTab(index === 4 ? -1 : 1);
        else if (index >= 12 && index <= 15) {
          const field = document.activeElement;
          if(dpad && field instanceof HTMLElement&&field.matches('[data-focal-editor][aria-pressed=true],.artwork-sampler[aria-pressed=true]')){
            field.dispatchEvent(new KeyboardEvent('keydown',{key:({12:'ArrowUp',13:'ArrowDown',14:'ArrowLeft',15:'ArrowRight'} as const)[index as 12],bubbles:true,cancelable:true}));
          } else if(field instanceof HTMLInputElement&&field.matches('[data-hero-focus]')&&(index===12||index===13)){
            document.querySelector<HTMLElement>(`[data-hero-focus="${index===13?1:0}"]`)?.focus();
          } else if (dpad && field instanceof HTMLSelectElement && (index === 14 || index === 15)) {
            field.selectedIndex = Math.max(0, Math.min(field.options.length - 1, field.selectedIndex + (index === 14 ? -1 : 1)));
            field.dispatchEvent(new Event('change', { bubbles: true }));
          } else if(dpad && field instanceof HTMLInputElement&&field.type==='range'&&(index===14||index===15)){
            if(index===14)field.stepDown();else field.stepUp();field.dispatchEvent(new Event('input',{bubbles:true}));
          } else moveFocus(directionKey[index as keyof typeof directionKey]);
        }
      }
      previous.clear(); pressed.forEach(index => previous.add(index));
    }
    frame = requestAnimationFrame(poll);
  }
  function sync() {
    const selected = readPads()[0];
    const hasPad = Boolean(selected);
    connected(hasPad, selected?.id);
    const shouldPoll = hasPad && !document.hidden && document.hasFocus();
    if (shouldPoll && !active) { active = true; frame = requestAnimationFrame(poll); }
    if (!shouldPoll && active) { active = false; cancelAnimationFrame(frame); previous.clear(); heldDirection=0; lastFrame=0; padIndex=undefined; }
  }
  window.addEventListener('gamepadconnected', sync);
  window.addEventListener('gamepaddisconnected', sync);
  window.addEventListener('focus', sync);
  window.addEventListener('blur', sync);
  window.addEventListener('pointerdown', activity);
  document.addEventListener('visibilitychange', sync);
  sync();
}
