import type { View } from './model';
interface Arrival { surface:string; art?:DOMRect; }
const running = new Set<Animation>();
const reduced = () => document.documentElement.dataset.motion === 'false' || matchMedia('(prefers-reduced-motion: reduce)').matches;
export function captureArrival(app:HTMLElement):Arrival {
  for (const animation of running) animation.cancel();
  running.clear();
  const art = app.querySelector<HTMLElement>('.game-card:focus .poster,.game-card:hover .poster,.detail-artwork');
  return {surface:document.documentElement.dataset.surface || '',art:art?.getBoundingClientRect()};
}
function play(node:Element,frames:Keyframe[],duration:number,delay=0) {
  const animation=node.animate(frames,{duration,delay,easing:'cubic-bezier(.16,1,.3,1)',fill:'backwards'});
  running.add(animation);animation.finished.catch(()=>{}).finally(()=>running.delete(animation));
}
export function arrive(app:HTMLElement,previous:Arrival,view:View) {
  const main=app.querySelector<HTMLElement>('#content');if(!main)return;
  if(reduced()){play(main,[{opacity:.82},{opacity:1}],100);return;}
  // Pages settle quickly; opening a game carries its artwork into the hero.
  const entering=view==='details'&&previous.surface!=='details';
  const layer=main.querySelector('.detail-body,.settings-body,.flow-body')||main;
  play(layer,[{opacity:.5,transform:`translate3d(${view==='library'?-14:18}px,0,0) scale(.995)`},{opacity:1,transform:'translate3d(0,0,0) scale(1)'}],320);
  if(entering){
    const art=main.querySelector<HTMLElement>('.detail-artwork');
    const image=main.querySelector('.hero-artwork');
    if(image)play(image,[{opacity:.35,transform:'scale(1.035)',filter:'blur(3px)'},{opacity:1,transform:'scale(1)',filter:'blur(0px)'}],480);
    if(art&&previous.art){const r=art.getBoundingClientRect(),p=previous.art;if(r.width&&r.height)play(art,[{transformOrigin:'0 0',transform:`translate(${p.x-r.x}px,${p.y-r.y}px) scale(${p.width/r.width},${p.height/r.height})`},{transformOrigin:'0 0',transform:'translate(0,0) scale(1,1)'}],440);}
    const copy=main.querySelector('.details-title-copy');if(copy)play(copy,[{opacity:.1,transform:'translateY(12px)',filter:'blur(2px)'},{opacity:1,transform:'translateY(0)',filter:'blur(0px)'}],360,45);
  } else if(view==='library') {
    for(const [i,card] of [...main.querySelectorAll('.game-item')].slice(0,12).entries())play(card,[{opacity:.45,transform:'translateY(14px) scale(.97)'},{opacity:1,transform:'translateY(0) scale(1)'}],340,Math.min(i*18,108));
  }
}
