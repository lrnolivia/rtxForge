import {signatureColor,accentHarmony,backdropInk} from './art-accent';
import {imageCrop,cropGeometry,type ScreenshotCrop} from './screenshot-crop';
export interface StoreScreenshot {id:string;full:string;thumbnail:string}
interface StoreBackground {image:string|null}
interface CachedBackground {url:string;width:number;height:number;crop:ScreenshotCrop;sample?:ImageData}
interface BackgroundSelection {appid:string;game:string;accent?:string|null;scene:HTMLElement;ids:string[];current?:string}
const cache=new Map<string,Promise<CachedBackground|null>>(),catalogs=new Map<string,Promise<StoreScreenshot[]>>();
const urls=new Set<string>(),choices=new Map<string,string[]>();
const palettes=new Map<string,Promise<string|null>>(),harmonious=new Map<string,Promise<StoreScreenshot[]>>();
let active:BackgroundSelection|undefined,fade:ReturnType<typeof setTimeout>|undefined,disposed=false,preparing=false;
const reduced=matchMedia('(prefers-reduced-motion:reduce)');
try{for(const [game,ids] of Object.entries(JSON.parse(localStorage.getItem('rtxforge-game-mode-backgrounds')||'{}')))if(Array.isArray(ids))choices.set(game,ids.filter(id=>typeof id==='string'&&/^[0-9]{1,6}$/.test(id)).slice(0,1));}catch{/* Use the first Store screenshot. */}

function thumbnailColor(source:string):Promise<string|null>{
  let pending=palettes.get(source);if(pending)return pending;
  pending=(async()=>{
    const image=new Image();image.crossOrigin='anonymous';image.src=source;
    let timer:ReturnType<typeof setTimeout>|undefined;
    try{
      await Promise.race([image.decode(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Thumbnail unavailable')),3500);})]);
      const canvas=document.createElement('canvas');canvas.width=64;canvas.height=64;
      const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)return null;
      const crop=imageCrop(image);context.drawImage(image,image.naturalWidth*crop.x,image.naturalHeight*crop.y,image.naturalWidth*crop.width,image.naturalHeight*crop.height,0,0,64,64);return signatureColor(context.getImageData(0,0,64,64).data);
    }catch{return null;}finally{clearTimeout(timer);image.src='';}
  })();palettes.set(source,pending);if(palettes.size>32)palettes.delete(palettes.keys().next().value!);return pending;
}
export async function screenshotGallery(appid:string,accent?:string|null,game?:string):Promise<StoreScreenshot[]>{
  let result=catalogs.get(appid);
  if(!result){result=(async()=>{
    try{
      const data:{screenshots?:StoreScreenshot[]}='__TAURI_INTERNALS__' in window
        ? await (await import('@tauri-apps/api/core')).invoke('store_screenshots',{appid})
        : await (await fetch('/api/store-screenshots?'+new URLSearchParams({appid}))).json();
      return Array.isArray(data.screenshots)?data.screenshots.slice(0,100):[];
    }catch{return [];}
  })();catalogs.set(appid,result);}
  const gallery=await result;
  if(!accent||!/^#[0-9a-f]{6}$/i.test(accent)||game&&choices.get(game)?.some(id=>gallery.some(shot=>shot.id===id)))return gallery;
  const key=appid+'|'+accent;let ranked=harmonious.get(key);
  if(!ranked){ranked=(async()=>{
    const candidates=gallery.slice(0,8),scores=new Map<string,number>();let index=0;
    async function worker(){while(index<candidates.length){const shot=candidates[index++];scores.set(shot.id,accentHarmony(accent!,await thumbnailColor(shot.thumbnail)));}}
    await Promise.all([worker(),worker()]);
    return [...gallery].sort((a,b)=>(scores.get(a.id)??2)-(scores.get(b.id)??2));
  })();harmonious.set(key,ranked);if(harmonious.size>32)harmonious.delete(harmonious.keys().next().value!);}
  return ranked;
}
export function selectedScreenshots(game:string,gallery:StoreScreenshot[]):string[]{
  const valid=new Set(gallery.map(shot=>shot.id));
  const saved=choices.get(game)?.filter(id=>valid.has(id)).slice(0,1);
  return saved?.length?saved:gallery.slice(0,1).map(shot=>shot.id);
}
export function chooseScreenshots(game:string,ids:string[]){
  const chosen=[...new Set(ids)].filter(id=>/^[0-9]{1,6}$/.test(id)).slice(0,1);
  if(!chosen.length)return;
  choices.set(game,chosen);
  try{localStorage.setItem('rtxforge-game-mode-backgrounds',JSON.stringify(Object.fromEntries(choices)));}catch{/* Session choices remain available. */}
  if(active?.game===game){const state=active;clearFade();state.ids=chosen;void display(state);}
}
/** Warm only the game the person has paused on, never the entire library. */
export async function prepareStoreBackground(appid:string,game:string,accent?:string|null){
  if(preparing||disposed)return;
  preparing=true;
  try{const gallery=await screenshotGallery(appid,accent,game);if(gallery.length)await load(appid,selectedScreenshots(game,gallery)[0]);}
  finally{preparing=false;}
}
async function load(appid:string,id?:string):Promise<CachedBackground|null>{
  const key=appid+':'+(id||'default');let pending=cache.get(key);
  if(pending){cache.delete(key);cache.set(key,pending);return pending;}
  pending=(async()=>{
    try{
      const result:StoreBackground='__TAURI_INTERNALS__' in window
        ? await (await import('@tauri-apps/api/core')).invoke('store_background',{appid,screenshotId:id||null})
        : await (await fetch('/api/store-background?'+new URLSearchParams({appid,...(id?{screenshot:id}:{})}))).json();
      if(disposed||!result.image||!/^data:image\/(jpeg|png);base64,/.test(result.image))return null;
      const [header,encoded]=result.image.split(',',2);
      const blob=new Blob([Uint8Array.from(atob(encoded),c=>c.charCodeAt(0))],{type:header.slice(5).split(';')[0]});
      const url=URL.createObjectURL(blob);urls.add(url);
      const image=new Image();image.src=url;
      try{await image.decode();}catch{URL.revokeObjectURL(url);urls.delete(url);return null;}
      if(disposed){URL.revokeObjectURL(url);urls.delete(url);return null;}
      const crop=imageCrop(image),canvas=document.createElement('canvas');canvas.width=96;canvas.height=Math.max(3,Math.round(96*image.naturalHeight*crop.height/(image.naturalWidth*crop.width)));
      const context=canvas.getContext('2d',{willReadFrequently:true});context?.drawImage(image,image.naturalWidth*crop.x,image.naturalHeight*crop.y,image.naturalWidth*crop.width,image.naturalHeight*crop.height,0,0,canvas.width,canvas.height);
      return {url,width:image.naturalWidth,height:image.naturalHeight,crop,sample:context?.getImageData(0,0,canvas.width,canvas.height)};
    }catch{return null;}
  })();cache.set(key,pending);
  if(cache.size>6){const oldest=[...cache.keys()].find(candidate=>candidate!==active?.current)!;const previous=cache.get(oldest);cache.delete(oldest);void previous?.then(image=>{if(image){URL.revokeObjectURL(image.url);urls.delete(image.url);}});}
  return pending;
}
function clearFade(){clearTimeout(fade);fade=undefined;active?.scene.querySelector('.scene-next')?.remove();}
function canFade(){return !document.hidden&&!reduced.matches&&document.documentElement.dataset.motion!=='false';}
export async function updateBackgroundContrast(){
  const key=active?.current,root=document.documentElement;
  if(!key){for(const name of ['brand','more','footer'])root.style.removeProperty('--'+name+'-ink');return;}
  const image=await cache.get(key);if(active?.current!==key||!image?.sample)return;
  fitScreenshot(active.scene,image);
  const {data,width,height}=image.sample,tint=root.dataset.tint==='true'?active.accent||null:null,light=root.dataset.theme==='light';
  for(const [name,selector] of [['brand','.brand'],['more','.shell-more>.menu-button'],['footer','.app-footer']] as const){
    const target=document.querySelector(selector);if(!target)continue;
    root.style.setProperty('--'+name+'-ink',backdropInk(data,width,height,innerWidth,innerHeight,target.getBoundingClientRect(),tint,light));
  }
}
function fitScreenshot(layer:HTMLElement,image:CachedBackground){
  if(image.crop.width===1&&image.crop.height===1){layer.style.backgroundSize='cover';layer.style.backgroundPosition='center';return;}
  const bounds=layer.getBoundingClientRect(),geometry=cropGeometry(image.width,image.height,image.crop,bounds.width,bounds.height);
  layer.style.backgroundSize=geometry.size;layer.style.backgroundPosition=geometry.position;
}
let contrastFrame=0;
window.addEventListener('resize',()=>{if(!contrastFrame)contrastFrame=requestAnimationFrame(()=>{contrastFrame=0;void updateBackgroundContrast();});},{passive:true});
async function display(state:BackgroundSelection){
  const id=state.ids[0],image=await load(state.appid,id);
  if(disposed||active!==state||state.ids[0]!==id)return;
  state.scene.dataset.backgroundState=image?'ready':'unavailable';
  if(image){
    const scene=state.scene,source=`url("${image.url}")`,quality=image.width>=3840&&image.height>=2160?'native':'soft';
    const commit=()=>{
      if(active!==state)return;
      scene.style.backgroundImage=source;scene.dataset.hero='true';scene.dataset.storeQuality=quality;
      fitScreenshot(scene,image);
      scene.dataset.backgroundWidth=String(image.width);scene.dataset.backgroundHeight=String(image.height);
      scene.dataset.screenshotId=id||'default';scene.querySelector('.scene-next')?.remove();state.current=state.appid+':'+(id||'default');
      void updateBackgroundContrast();
    };
    clearTimeout(fade);scene.querySelector('.scene-next')?.remove();
    if(scene.style.backgroundImage!==source&&canFade()){
      const next=document.createElement('div');next.className='scene-next';next.dataset.quality=quality;next.style.backgroundImage=source;scene.append(next);fitScreenshot(next,image);
      requestAnimationFrame(()=>requestAnimationFrame(()=>{if(next.isConnected)next.style.opacity='1';}));fade=setTimeout(commit,750);
    }else commit();
  }
}
/** One chosen screenshot per game; there is no rotation timer or background prefetch. */
export function applyStoreBackground(appid:string|null|undefined,scene:HTMLElement,game=appid||'',accent?:string|null){
  const key=appid&&/^[1-9][0-9]{0,9}$/.test(appid)?appid:'';
  if(active?.appid===key&&active.game===game&&active.scene===scene&&active.accent===accent)return;
  clearFade();active=undefined;
  void updateBackgroundContrast();
  scene.style.backgroundImage='';scene.style.backgroundSize='cover';scene.style.backgroundPosition='center';scene.dataset.hero='false';delete scene.dataset.storeQuality;
  scene.dataset.backgroundGame=key;scene.dataset.backgroundState=key?'loading':'none';
  if(!key)return;
  const state:BackgroundSelection={appid:key,game,accent,scene,ids:[]};active=state;
  void screenshotGallery(key,accent,game).then(gallery=>{if(active!==state)return;state.ids=selectedScreenshots(game,gallery);void display(state);});
}
window.addEventListener('pagehide',()=>{disposed=true;clearFade();for(const url of urls)URL.revokeObjectURL(url);urls.clear();cache.clear();catalogs.clear();palettes.clear();harmonious.clear();},{once:true});
