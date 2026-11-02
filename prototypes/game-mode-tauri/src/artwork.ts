import type { Snapshot, Game } from './model';
import { artworkAccent } from './art-accent';
const steam='https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/';
/** Exact manifest/cache identities only; never search by a guessed title. */
export function completeArtwork(snapshot:Snapshot):Snapshot {
  for(const game of snapshot.games){
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

const localCache=new Map<string,{image:string;accent?:string|null}>();
export function clearArtworkCache(){localCache.clear();}
export async function hydrateArtwork(snapshot:Snapshot,changed:(game:Game,role:string)=>void){
  // Resolve the authoritative posters (and their colors) before loading heroes.
  const jobs=snapshot.games.flatMap(game=>(game.localArtwork||[]).map(role=>({game,role})))
    .sort((a,b)=>Number(b.role==='poster')-Number(a.role==='poster'));
  async function worker(){
    while(jobs.length){
      const {game,role}=jobs.shift()!,key=game.id+':'+role;
      try {
        let cached=localCache.get(key);
        if(!cached){
          const result='__TAURI_INTERNALS__' in window
            ? await (await import('@tauri-apps/api/core')).invoke<{image:string|null}>('artwork',{id:game.id,role})
            : await (await fetch('/api/artwork?'+new URLSearchParams({id:game.id,role}))).json();
          if(!result.image)continue;
          // Sample the original saved bytes, as Desktop does. A lossy display
          // thumbnail can pick a different winning color cluster.
          const accent=role==='poster'?await artworkAccent(game.id,result.image):undefined;
          const bitmap=await createImageBitmap(await(await fetch(result.image)).blob());
          const canvas=document.createElement('canvas'),scale=Math.min(1,(role==='poster'?600:1920)/bitmap.width);
          canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);
          canvas.getContext('2d')!.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
          cached={image:role==='poster'?result.image:canvas.toDataURL('image/webp',.9),accent};localCache.set(key,cached);
        }
        if(role==='poster'){game.art=cached.image;game.artworkAccent=cached.accent||'#b4b4b4';game.artworkAccentReady=true;}
        else if(role==='hero')game.hero=cached.image;else game.capsule=cached.image;
        changed(game,role);
      }catch{/* Preserve the cached/Steam fallback if an individual file is unavailable. */}
    }
  }
  await Promise.all([worker(),worker()]);
}
