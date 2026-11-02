import type { Snapshot, Game } from './model';
import { artworkAccent } from './art-accent';
const steam='https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/';
interface Assets {active:boolean;urls:Set<string>;cache:Map<string,{image:string;accent?:string|null}>}
const assets = new WeakMap<Snapshot,Assets>();
function session(snapshot:Snapshot) {
  let found=assets.get(snapshot);
  if(!found){found={active:true,urls:new Set(),cache:new Map()};assets.set(snapshot,found);}
  return found;
}
function imageBlob(source:string) {
  const [header,encoded]=source.split(',',2),bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
  return new Blob([bytes],{type:header.slice(5).split(';')[0]});
}
function imageUrl(blob:Blob,state:Assets) {const url=URL.createObjectURL(blob);state.urls.add(url);return url;}
/** Exact manifest/cache identities only; never search by a guessed title. */
export function completeArtwork(snapshot:Snapshot):Snapshot {
  const state=session(snapshot),inline=new Map<string,string>();
  for(const game of snapshot.games){
    for(const role of ['art','hero','capsule'] as const){
      const source=game[role];
      if(source?.startsWith('data:image/')){
        let url=inline.get(source);if(!url){url=imageUrl(imageBlob(source),state);inline.set(source,url);}game[role]=url;
      }
    }
    if(!game.appid||!/^\d+$/.test(game.appid))continue;
    const base=steam+game.appid+'/';
    game.art ||= base+'library_600x900.jpg';
    game.hero ||= base+'library_hero.jpg';
    game.capsule ||= base+'header.jpg';
  }
  return snapshot;
}
export function bindArtworkFailures(root:HTMLElement){
  for(const img of root.querySelectorAll<HTMLImageElement>('img')){
    const failed=()=>{
      if(img.closest('.hero-artwork')){img.closest<HTMLElement>('.hero-artwork')!.hidden=true;return;}
      if(img.classList.contains('artwork-glow')||img.classList.contains('detail-artwork-light')){img.hidden=true;return;}
      if(img.closest('.poster')||img.classList.contains('detail-poster')){
        img.style.visibility='hidden';
        const frame=img.parentElement;frame?.classList.add('art-unavailable');
        if(frame&&!frame.querySelector('.artwork-unavailable')){const label=document.createElement('span');label.className='artwork-unavailable';label.textContent='Artwork unavailable';frame.append(label);}
      }
    };
    img.addEventListener('error',failed,{once:true});
    if(img.complete&&img.currentSrc&&!img.naturalWidth)failed();
  }
}

export function clearArtworkCache(snapshot:Snapshot){
  const state=assets.get(snapshot);if(!state)return;state.active=false;
  for(const url of state.urls)URL.revokeObjectURL(url);
  state.urls.clear();state.cache.clear();assets.delete(snapshot);
}
export async function hydrateArtwork(snapshot:Snapshot,changed:(game:Game,role:string)=>void){
  const state=session(snapshot);
  // Resolve the authoritative posters (and their colors) before loading heroes.
  const jobs=snapshot.games.flatMap(game=>(game.localArtwork||[]).map(role=>({game,role})))
    .sort((a,b)=>Number(b.role==='poster')-Number(a.role==='poster'));
  async function worker(){
    while(jobs.length&&state.active){
      const {game,role}=jobs.shift()!,key=game.id+':'+role;
      let raw:string|undefined;
      try {
        let cached=state.cache.get(key);
        if(!cached){
          const result='__TAURI_INTERNALS__' in window
            ? await (await import('@tauri-apps/api/core')).invoke<{image:string|null}>('artwork',{id:game.id,role})
            : await (await fetch('/api/artwork?'+new URLSearchParams({id:game.id,role}))).json();
          if(!result.image||!state.active)continue;
          // Sample the original saved bytes, as Desktop does. A lossy display
          // thumbnail can pick a different winning color cluster.
          const original=imageBlob(result.image);raw=imageUrl(original,state);
          const accent=role==='poster'&&!game.accent?await artworkAccent(game.id,raw):undefined;
          const bitmap=await createImageBitmap(original);
          const canvas=document.createElement('canvas'),scale=Math.min(1,(role==='poster'?600:1920)/bitmap.width);
          canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);
          canvas.getContext('2d')!.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
          const thumbnail=await new Promise<Blob|null>(resolve=>canvas.toBlob(resolve,'image/webp',.9));
          URL.revokeObjectURL(raw);state.urls.delete(raw);raw=undefined;
          if(!state.active)continue;
          cached={image:imageUrl(thumbnail||original,state),accent};state.cache.set(key,cached);
        }
        if(role==='poster'){game.art=cached.image;game.artworkAccent=cached.accent||'#b4b4b4';game.artworkAccentReady=true;}
        else if(role==='hero')game.hero=cached.image;else game.capsule=cached.image;
        changed(game,role);
      }catch{/* Preserve the cached/Steam fallback if an individual file is unavailable. */}
      finally{if(raw){URL.revokeObjectURL(raw);state.urls.delete(raw);}}
    }
  }
  await Promise.all([worker(),worker()]);
}
