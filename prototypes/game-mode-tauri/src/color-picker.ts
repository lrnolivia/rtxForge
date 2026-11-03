const valid = (value: string) => /^#[\da-f]{6}$/i.test(value);
const rgb = (hex: string) => [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16));
const hex = (values: number[]) => '#' + values.map(value => Math.round(value).toString(16).padStart(2, '0')).join('');

/** An in-app picker works in WebView2 and WebKit without a screen-capture API. */
export function colorPicker(id: string, value: string, artwork = '', disabled = false) {
  return `<div class="color-picker" data-color-picker="${id}" style="--picked-color:${value}">
    <button class="color-swatch quiet" aria-label="Choose accent color" aria-expanded="false" ${disabled ? 'disabled' : ''}><span></span></button>
    <div class="color-editor" hidden>
      <label class="color-hex">Hex color<input id="${id}" aria-label="Accent hex color" type="text" value="${value}" maxlength="7" spellcheck="false" /></label>
      <div class="color-channels">${['Red', 'Green', 'Blue'].map((name, index) => `<label>${name}<input type="range" aria-label="${name}" data-channel="${index}" min="0" max="255" step="1" value="${rgb(value)[index]}"/><output>${rgb(value)[index]}</output></label>`).join('')}</div>
      ${artwork ? `<div class="artwork-color-picker"><button class="artwork-sampler" aria-label="Pick a color from artwork. Arrow keys move the picker; select to use the color."><canvas></canvas><span class="color-crosshair" aria-hidden="true"></span></button><p>Pick from artwork. Use the arrows to move, then select.</p></div>` : ''}
      <p class="color-picker-status" role="status" aria-live="polite"></p>
      <div class="operation-actions"><button class="primary" data-color-save ${disabled ? 'disabled' : ''}>Save color</button><button class="quiet" data-color-cancel>Cancel</button></div>
    </div>
  </div>`;
}

export function bindColorPicker(root: HTMLElement, id: string, artwork: string | undefined, preview: (color: string) => void, save: (color: string) => Promise<void>) {
  const host = root.querySelector<HTMLElement>(`[data-color-picker="${id}"]`);
  if (!host) return;
  const editor = host.querySelector<HTMLElement>('.color-editor')!;
  const toggle = host.querySelector<HTMLButtonElement>('.color-swatch')!;
  const input = host.querySelector<HTMLInputElement>('.color-hex input')!;
  const status = host.querySelector<HTMLElement>('.color-picker-status')!;
  const channels = [...host.querySelectorAll<HTMLInputElement>('[data-channel]')];
  let original = input.value, color = original, loaded = false;
  const update = (value: string) => {
    if (!valid(value)) { input.setAttribute('aria-invalid', 'true'); status.textContent = 'Enter a hex color such as #AE3CEC.'; return; }
    input.removeAttribute('aria-invalid'); status.textContent = ''; color = value.toLowerCase(); input.value = color;
    host.style.setProperty('--picked-color', color);
    channels.forEach((channel, index) => { channel.value = String(rgb(color)[index]); channel.nextElementSibling!.textContent = channel.value; });
    preview(color);
  };
  const close = () => { editor.hidden = true; toggle.setAttribute('aria-expanded', 'false'); toggle.focus(); };
  input.addEventListener('input', () => update(input.value));
  channels.forEach(channel => channel.addEventListener('input', () => update(hex(channels.map(field => Number(field.value))))));
  const sampler = host.querySelector<HTMLButtonElement>('.artwork-sampler');
  const canvas = sampler?.querySelector('canvas');
  let point = [.5, .5];
  const mark = () => { sampler?.style.setProperty('--pick-x', `${point[0] * 100}%`); sampler?.style.setProperty('--pick-y', `${point[1] * 100}%`); };
  const sample = () => {
    if (!loaded || !canvas) return;
    const pixel = canvas.getContext('2d', {willReadFrequently: true})!.getImageData(Math.min(canvas.width - 1, Math.round(point[0] * canvas.width)), Math.min(canvas.height - 1, Math.round(point[1] * canvas.height)), 1, 1).data;
    update(hex([...pixel].slice(0, 3)));
  };
  sampler?.addEventListener('click', event => { if (event.detail) { const rect = sampler.getBoundingClientRect(); point = [(event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height]; mark(); } sample(); });
  sampler?.addEventListener('keydown', event => {
    const delta: Record<string, number[]> = {ArrowLeft: [-.01, 0], ArrowRight: [.01, 0], ArrowUp: [0, -.01], ArrowDown: [0, .01]};
    if (!delta[event.key]) return;
    event.preventDefault(); event.stopPropagation(); point = point.map((value, axis) => Math.max(0, Math.min(1, value + delta[event.key][axis]))); mark();
  });
  toggle.addEventListener('click', () => {
    editor.hidden = !editor.hidden; toggle.setAttribute('aria-expanded', String(!editor.hidden));
    if (editor.hidden) return;
    original = color; channels[0].focus();
    if (artwork && canvas && !loaded) {
      const image = new Image(); image.crossOrigin = 'anonymous';
      image.onload = () => { try { const scale = Math.min(1, 480 / image.naturalWidth); canvas.width = Math.round(image.naturalWidth * scale); canvas.height = Math.round(image.naturalHeight * scale); canvas.getContext('2d', {willReadFrequently: true})!.drawImage(image, 0, 0, canvas.width, canvas.height); canvas.getContext('2d')!.getImageData(0, 0, 1, 1); loaded = true; } catch { sampler!.disabled = true; status.textContent = 'This artwork cannot be sampled. Use the color sliders or hex value.'; } };
      image.onerror = () => { sampler!.disabled = true; status.textContent = 'Artwork is unavailable. Use the color sliders or hex value.'; }; image.src = artwork;
    }
  });
  host.querySelector('[data-color-cancel]')?.addEventListener('click', () => { update(original); close(); });
  editor.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); update(original); close(); } });
  host.querySelector<HTMLButtonElement>('[data-color-save]')!.addEventListener('click', async event => {
    if (!valid(input.value)) { update(input.value); input.focus(); return; }
    const button = event.currentTarget as HTMLButtonElement; button.disabled = true; status.textContent = 'Saving color…';
    try { await save(color); original = color; close(); }
    catch (error) { status.textContent = error instanceof Error ? error.message : 'Color could not be saved. Try again.'; }
    finally { button.disabled = false; }
  });
}
