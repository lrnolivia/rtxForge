// Same OKLab signature selection and UI gamut mapping as scripts/ui_colors.py
// and the native library's Services/ArtAccent.cs. Input is the actual cached art.
type Lab=[number,number,number];
const clamp=(value:number,low:number,high:number)=>Math.max(low,Math.min(high,value));
function lab(r:number,g:number,b:number):Lab {
  const linear=(v:number)=>(v/=255)<=.04045?v/12.92:((v+.055)/1.055)**2.4;
  r=linear(r);g=linear(g);b=linear(b);
  const l=Math.cbrt(.4122214708*r+.5363325363*g+.0514459929*b),m=Math.cbrt(.2119034982*r+.6806995451*g+.1073969566*b),s=Math.cbrt(.0883024619*r+.2817188376*g+.6299787005*b);
  return [.2104542553*l+.793617785*m-.0040720468*s,1.9779984951*l-2.428592205*m+.4505937099*s,.0259040371*l+.7827717662*m-.808675766*s];
}
function rgbFromLch(l:number,c:number,h:number) {
  for(let chroma=c;;chroma-=.005){
    const a=chroma*Math.cos(h),b=chroma*Math.sin(h);
    const lp=(l+.3963377774*a+.2158037573*b)**3,mp=(l-.1055613458*a-.0638541728*b)**3,sp=(l-.0894841775*a-1.291485548*b)**3;
    const rgb=[4.0767416621*lp-3.3077115913*mp+.2309699292*sp,-1.2684380046*lp+2.6097574011*mp-.3413193965*sp,-.0041960863*lp-.7034186147*mp+1.707614701*sp];
    if(chroma<=0||rgb.every(v=>v>=-.0005&&v<=1.0005))return rgb.map(v=>{v=clamp(v,0,1);return Math.round((v<=.0031308?12.92*v:1.055*v**(1/2.4)-.055)*255);});
  }
}
function hsv(rgb:number[]){
  const [r,g,b]=rgb.map(v=>v/255),max=Math.max(r,g,b),min=Math.min(r,g,b),d=max-min;
  let hue=d===0?0:max===r?((g-b)/d+6)%6:max===g?(b-r)/d+2:(r-g)/d+4;
  hue/=6;return [hue,max===0?0:d/max,max];
}
const hex=(rgb:number[])=>'#'+rgb.map(v=>v.toString(16).padStart(2,'0')).join('');
export function signatureColor(pixels:ArrayLike<number>):string|null {
  const size=108,score=Array(size).fill(0),weight=Array(size).fill(0),sums=Array.from({length:size},()=>[0,0,0]);
  let count=0,chromatic=0;
  for(let i=0;i+3<pixels.length;i+=4){
    if(pixels[i+3]<128)continue;count++;
    const [l,a,b]=lab(pixels[i],pixels[i+1],pixels[i+2]),c=Math.hypot(a,b),hue=(Math.atan2(b,a)/(2*Math.PI)+1)%1;
    if(c<.05||l<.18||l>.97)continue;chromatic++;
    const index=Math.floor(hue*36)%36*3+Math.min(2,Math.floor((l-.18)/(.79/3)));
    score[index]+=c*c*(1-Math.abs(l-.65)*.9);weight[index]+=c;
    sums[index][0]+=l*c;sums[index][1]+=a*c;sums[index][2]+=b*c;
  }
  if(!count||chromatic<count*.02)return null;
  const merged=score.map((v,i)=>v+.5*(score[(Math.floor(i/3)+35)%36*3+i%3]+score[(Math.floor(i/3)+1)%36*3+i%3]));
  const best=merged.indexOf(Math.max(...merged));if(merged[best]<=0||!weight[best])return null;
  const [l,a,b]=sums[best].map(v=>v/weight[best]),c=clamp(Math.hypot(a,b),.09,.24),h=Math.atan2(b,a);
  const [hue,saturation]=hsv(rgbFromLch(l,c,h)),upper=hue>=30/360&&hue<=100/360&&saturation>.25?.94:.84;
  let rgb=rgbFromLch(clamp(l,.62,upper),c,h);const [rh,rs,rv]=hsv(rgb);
  if(rh>=30/360&&rh<=100/360&&rs>.4&&rv<.9)rgb=rgbFromLch(.9,c,h);
  return hex(rgb);
}

const cache=new Map<string,{source:string;color:string|null}>();
export async function artworkAccent(id:string,source:string):Promise<string|null> {
  const prior=cache.get(id);if(prior?.source===source)return prior.color;
  if(!source.startsWith('data:image/')&&!source.startsWith('blob:')&&!source.startsWith('https://shared.akamai.steamstatic.com/'))return null;
  let timer:ReturnType<typeof setTimeout>|undefined;
  try {
    const image=new Image();if(source.startsWith('https:'))image.crossOrigin='anonymous';image.src=source;
    await Promise.race([image.decode(),new Promise<never>((_resolve,reject)=>{timer=setTimeout(()=>{image.src='';reject(new Error('Artwork sampling timed out.'));},8000);})]);
    const canvas=document.createElement('canvas');canvas.width=64;canvas.height=64;
    const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)return null;
    context.drawImage(image,0,0,64,64);
    const color=signatureColor(context.getImageData(0,0,64,64).data);cache.set(id,{source,color});return color;
  }catch{cache.set(id,{source,color:null});return null;}
  finally{clearTimeout(timer);}
}

// Selected Library cards and rows use the native library's solid accent and
// HSV-derived dark ink. Very dark custom colors fall back to readable ink.
export function selectionInk(color:string):string {
  if(!/^#[0-9a-f]{6}$/i.test(color))return '#242424';
  const rgb=[1,3,5].map(i=>parseInt(color.slice(i,i+2),16));
  const [h,s,v]=hsv(rgb),yellow=h>=45/360&&h<=100/360,sat=yellow?.04:s<.08?0:clamp(s*1.12,.78,1),value=clamp(v*.42,.2,.34);
  const f=(n:number)=>{const k=(n+h*6)%6;return Math.round(value*(1-sat*Math.max(0,Math.min(k,4-k,1)))*255);};
  const dark=[f(5),f(3),f(1)];
  const lum=(c:number[])=>c.reduce((sum,x,i)=>{x/=255;return sum+[.2126,.7152,.0722][i]*(x<=.04045?x/12.92:((x+.055)/1.055)**2.4);},0);
  const bg=lum(rgb),contrast=(ink:number[])=>(Math.max(lum(ink),bg)+.05)/(Math.min(lum(ink),bg)+.05);
  if(contrast(dark)>=4.5)return hex(dark);
  if(contrast([0,0,0])>=4.5){for(let step=1;step<=30;step++){const candidate=dark.map(v=>Math.round(v*(1-step/30)));if(contrast(candidate)>=4.5)return hex(candidate);}}
  return '#ffffff';
}


// Hero colors stay in the game's hue family. Text is never blended with art.
const luminance=(rgb:number[])=>rgb.reduce((sum,value,index)=>{const x=value/255;return sum+[.2126,.7152,.0722][index]*(x<=.04045?x/12.92:((x+.055)/1.055)**2.4);},0);
const parse=(color:string)=>[1,3,5].map(i=>parseInt(color.slice(i,i+2),16));
const mix=(a:number[],b:number[],amount:number)=>a.map((v,i)=>Math.round(v*amount+b[i]*(1-amount)));
export function accentHarmony(accent:string,color:string|null):number {
  const [light,a,b]=lab(...parse(accent) as [number,number,number]),chroma=Math.hypot(a,b);
  if(!color)return chroma<.04?0:.8;
  const [otherLight,x,y]=lab(...parse(color) as [number,number,number]),otherChroma=Math.hypot(x,y);
  if(chroma<.04)return otherChroma+Math.abs(light-otherLight)*.1;
  const hue=(1-Math.cos(Math.atan2(b,a)-Math.atan2(y,x)))/2;
  return hue*.8+Math.abs(chroma-otherChroma)*.5+Math.abs(light-otherLight)*.1;
}
export function backdropInk(pixels:ArrayLike<number>,width:number,height:number,viewWidth:number,viewHeight:number,area:{x:number;y:number;width:number;height:number},accent:string|null,light:boolean):string {
  const scale=Math.max(viewWidth/width,viewHeight/height),offsetX=(width*scale-viewWidth)/2,offsetY=(height*scale-viewHeight)/2;
  const tint=accent&&/^#[0-9a-f]{6}$/i.test(accent)?parse(accent).map(v=>v/255):null;
  const soft=(base:number,color:number)=>color<=.5?base-(1-2*color)*base*(1-base):base+(2*color-1)*((base<=.25?((16*base-12)*base+4)*base:Math.sqrt(base))-base);
  const sum=[0,0,0];
  for(let y=0;y<4;y++)for(let x=0;x<8;x++){
    const px=Math.max(0,Math.min(width-1,Math.floor((area.x+(x+.5)*area.width/8+offsetX)/scale))),py=Math.max(0,Math.min(height-1,Math.floor((area.y+(y+.5)*area.height/4+offsetY)/scale))),index=(py*width+px)*4;
    let color=[0,1,2].map(c=>pixels[index+c]/255);if(tint)color=color.map((v,c)=>soft(v,tint[c]));
    if(light)color=color.map(v=>v*.84+.16);
    const gray=color[0]*.2126+color[1]*.7152+color[2]*.0722;
    color=color.map(v=>(gray+(v-gray)*.8)*(light?.85:.58));
    for(let c=0;c<3;c++)sum[c]+=color[c]*255/32;
  }
  const background=luminance(sum);
  return (background+.05)/.05>1.05/(background+.05)?'#000000':'#ffffff';
}
export function lightAccentInk(accent:string):string {
  const rgb=parse(/^#[0-9a-f]{6}$/i.test(accent)?accent:'#d8d5ce');
  const [,a,b]=lab(...rgb as [number,number,number]);
  return hex(rgbFromLch(.3,Math.min(Math.hypot(a,b),.1),Math.atan2(b,a)));
}
export function sectionHeadingColor(accent:string,light=false):string {
  if(light)return lightAccentInk(accent);
  const rgb=parse(/^#[0-9a-f]{6}$/i.test(accent)?accent:'#d8d5ce');
  const [l,a,b]=lab(...rgb as [number,number,number]);
  return hex(rgbFromLch(Math.max(l,.9),Math.min(Math.hypot(a,b),.12),Math.atan2(b,a)));
}
export function heroColors(accent:string,light:boolean,background:number[]=[65,70,75],cardBackground=background,tinted=true) {
  const rgb=parse(/^#[0-9a-f]{6}$/i.test(accent)?accent:'#d8d5ce');
  const [l,a,b]=lab(...rgb as [number,number,number]),c=Math.hypot(a,b),h=Math.atan2(b,a);
  const against=(ink:number[],surface:number[])=>(Math.max(luminance(ink),luminance(surface))+.05)/(Math.min(luminance(ink),luminance(surface))+.05);
  // Titles keep a bright version of the game's hue in every UI theme.
  // Protect their backdrop instead of turning bright yellow into grey ink.
  const title=c<.025?rgbFromLch(.97,c,h):rgbFromLch(Math.max(l,.8),Math.min(c,.24),h);
  let titleVeil=0;
  while(titleVeil<.94&&against(title,mix([12,18,23],background,titleVeil))<4.5)titleVeil+=.02;
  return {title:hex(title),titleVeil,card:tinted?hex(mix(rgb,[255,255,255],.8)):'#ffffff',ink:light?lightAccentInk(accent):'#f8f6f1',light};
}
export function heroBadge(background:number[]=[65,70,75]) {
  return luminance(background)>.35
    ? {surface:'rgb(246 245 241 / .78)',ink:'#292d32'}
    : {surface:'rgb(28 32 38 / .68)',ink:'#f8f6f1'};
}
export function sampleHero(image:HTMLImageElement,area:DOMRect,includeVeil=false):number[]|null {
  try {
    if(!image.naturalWidth)return null;
    const bounds=image.getBoundingClientRect(),scale=Math.max(bounds.width/image.naturalWidth,bounds.height/image.naturalHeight);
    const position=getComputedStyle(image).objectPosition.split(' ').map(parseFloat);
    const left=(bounds.width-image.naturalWidth*scale)*(position[0]/100),top=(bounds.height-image.naturalHeight*scale)*(position[1]/100);
    const canvas=document.createElement('canvas');canvas.width=24;canvas.height=8;
    const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)return null;
    context.drawImage(image,(area.x-bounds.x-left)/scale,(area.y-bounds.y-top)/scale,area.width/scale,area.height/scale,0,0,24,8);
    const pixels=context.getImageData(0,0,24,8).data,sums=[0,0,0];let count=0;
    // Match the existing .hero-artwork:after veil, including its compact-state
    // opacity. Sampling the uncomposited image can incorrectly choose dark ink.
    const opacity=includeVeil&&image.parentElement?Number(getComputedStyle(image.parentElement,':after').opacity):0;
    const angle=32*Math.PI/180,dx=Math.sin(angle),dy=-Math.cos(angle),length=Math.abs(bounds.width*dx)+Math.abs(bounds.height*dy);
    for(let i=0;i<pixels.length;i+=4){
      if(pixels[i+3]<128)continue;count++;
      const pixel=i/4,x=area.x+(pixel%24+.5)*area.width/24,y=area.y+(Math.floor(pixel/24)+.5)*area.height/8;
      const t=clamp(.5+((x-bounds.x-bounds.width/2)*dx+(y-bounds.y-bounds.height/2)*dy)/length,0,1);
      const alpha=opacity*(t<.28?.94+(.6-.94)*t/.28:t<.55?.6*(.55-t)/.27:0);
      for(let j=0;j<3;j++)sums[j]+=pixels[i+j]*(1-alpha)+[12,18,23][j]*alpha;
    }
    return count?sums.map(v=>v/count):null;
  }catch{return null;}
}
