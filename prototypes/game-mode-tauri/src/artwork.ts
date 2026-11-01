import type { Snapshot, Game } from './model';
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
    img.addEventListener('error',()=>{
      if(img.closest('.hero-artwork')){img.closest<HTMLElement>('.hero-artwork')!.hidden=true;return;}
      if(img.classList.contains('artwork-glow')||img.classList.contains('detail-artwork-light')){img.hidden=true;return;}
      if(img.closest('.poster')||img.classList.contains('detail-poster')){img.style.visibility='hidden';img.parentElement?.classList.add('art-unavailable');}
    },{once:true});
  }
}

const localCache=new Map<string,string>();
export function clearArtworkCache(){localCache.clear();}
export async function hydrateArtwork(snapshot:Snapshot,changed:(game:Game,role:string)=>void){
  const jobs=snapshot.games.flatMap(game=>(game.localArtwork||[]).map(role=>({game,role})));
  async function worker(){
    while(jobs.length){
      const {game,role}=jobs.shift()!,key=game.id+':'+role;
      try {
        let image=localCache.get(key);
        if(!image){
          const result='__TAURI_INTERNALS__' in window
            ? await (await import('@tauri-apps/api/core')).invoke<{image:string|null}>('artwork',{id:game.id,role})
            : await (await fetch('/api/artwork?'+new URLSearchParams({id:game.id,role}))).json();
          if(!result.image)continue;
          const bitmap=await createImageBitmap(await(await fetch(result.image)).blob());
          const canvas=document.createElement('canvas'),scale=Math.min(1,(role==='poster'?600:1920)/bitmap.width);
          canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);
          canvas.getContext('2d')!.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
          image=canvas.toDataURL('image/webp',.9);localCache.set(key,image);
        }
        if(role==='poster')game.art=image;else if(role==='hero')game.hero=image;else game.capsule=image;
        changed(game,role);
      }catch{/* Preserve the cached/Steam fallback if an individual file is unavailable. */}
    }
  }
  await Promise.all([worker(),worker()]);
}
