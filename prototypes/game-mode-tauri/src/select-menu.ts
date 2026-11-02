let active: {owner:HTMLSelectElement; menu:HTMLElement; events:AbortController} | undefined;
export const selectMenuOpen=()=>Boolean(active);
export function closeSelectMenu(focus=true) {
  const previous=active;if(!previous)return;active=undefined;
  previous.events.abort();previous.menu.remove();previous.owner.setAttribute('aria-expanded','false');
  previous.owner.removeAttribute('aria-controls');
  if(focus&&previous.owner.isConnected)previous.owner.focus({preventScroll:true});
}

function open(select:HTMLSelectElement) {
  if(select.disabled)return;
  if(active?.owner===select){closeSelectMenu();return;}
  closeSelectMenu(false);
  const menu=document.createElement('div'),events=new AbortController();
  menu.className='select-menu';menu.id='select-options';menu.role='listbox';
  menu.setAttribute('aria-label',select.getAttribute('aria-label')||select.labels?.[0]?.querySelector('strong')?.textContent||'Options');
  menu.style.font=getComputedStyle(select).font;
  select.setAttribute('aria-expanded','true');select.setAttribute('aria-controls',menu.id);
  const choices:HTMLButtonElement[]=[];
  for(const option of select.options) {
    if(option.hidden)continue;
    const button=document.createElement('button');button.className='ui-control';button.type='button';button.role='option';button.tabIndex=-1;
    button.textContent=option.text;button.title=option.text;button.disabled=option.disabled;
    button.setAttribute('aria-selected',String(option.selected));
    button.addEventListener('click',()=>{closeSelectMenu(false);select.value=option.value;select.focus({preventScroll:true});select.dispatchEvent(new Event('change',{bubbles:true}));});
    menu.append(button);if(!button.disabled)choices.push(button);
  }
  document.body.append(menu);active={owner:select,menu,events};
  const rect=select.getBoundingClientRect(),height=Math.min(320,menu.scrollHeight);
  const below=innerHeight-rect.bottom-8,above=rect.top-8,up=below<height&&above>below;
  const available=Math.max(60,(up?above:below)-8),shown=Math.min(height,available);
  menu.style.width=rect.width+'px';menu.style.maxHeight=shown+'px';
  menu.style.left=Math.max(8,Math.min(rect.left,innerWidth-rect.width-8))+'px';
  menu.style.top=(up?Math.max(8,rect.top-shown-6):rect.bottom+6)+'px';
  const chosen=choices.find(button=>button.getAttribute('aria-selected')==='true')||choices[0];
  chosen?.focus({preventScroll:true});if(chosen)menu.scrollTop=Math.max(0,chosen.offsetTop-menu.clientHeight/2+chosen.offsetHeight/2);
  document.addEventListener('pointerdown',event=>{if(!menu.contains(event.target as Node)&&event.target!==select)closeSelectMenu(false);},{capture:true,signal:events.signal});
  document.addEventListener('wheel',event=>{if(!menu.contains(event.target as Node))closeSelectMenu(false);},{capture:true,passive:true,signal:events.signal});
  document.addEventListener('touchmove',event=>{if(!menu.contains(event.target as Node))closeSelectMenu(false);},{capture:true,passive:true,signal:events.signal});
  window.addEventListener('resize',()=>closeSelectMenu(false),{signal:events.signal});
  document.addEventListener('keydown',event=>{
    if(!active)return;
    const index=Math.max(0,choices.indexOf(document.activeElement as HTMLButtonElement));
    if(['ArrowUp','ArrowDown','Home','End'].includes(event.key)){
      event.preventDefault();event.stopImmediatePropagation();
      const next=event.key==='Home'?0:event.key==='End'?choices.length-1:Math.max(0,Math.min(choices.length-1,index+(event.key==='ArrowUp'?-1:1)));
      const choice=choices[next];choice?.focus({preventScroll:true});if(choice)menu.scrollTop=Math.max(0,choice.offsetTop-menu.clientHeight/2+choice.offsetHeight/2);
    } else if(event.key==='Enter'||event.key===' '){event.preventDefault();event.stopImmediatePropagation();choices[index]?.click();}
    else if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();closeSelectMenu();}
    else if(event.key==='Tab')closeSelectMenu();
  },{capture:true,signal:events.signal});
}

export function enhanceSelects(root:HTMLElement) {
  for(const select of root.querySelectorAll<HTMLSelectElement>('select')) {
    const wrapper=document.createElement('span');wrapper.className='select-shell';select.replaceWith(wrapper);wrapper.append(select);
    select.setAttribute('aria-haspopup','listbox');select.setAttribute('aria-expanded','false');
    select.addEventListener('pointerdown',event=>event.preventDefault());
    select.addEventListener('mousedown',event=>event.preventDefault());
    select.addEventListener('click',event=>{event.preventDefault();open(select);});
    select.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)||event.altKey&&event.key==='ArrowDown'){event.preventDefault();event.stopPropagation();open(select);}});
  }
}
