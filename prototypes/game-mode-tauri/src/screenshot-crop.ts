export interface ScreenshotCrop {x:number;y:number;width:number;height:number}
const full:ScreenshotCrop={x:0,y:0,width:1,height:1};

/** Only remove matched, almost-black edge bands with a clear image boundary. */
export function screenshotCrop(data:ArrayLike<number>,width:number,height:number):ScreenshotCrop {
  if(width<16||height<16)return {...full};
  const brightness=(x:number,y:number)=>Math.max(data[(y*width+x)*4],data[(y*width+x)*4+1],data[(y*width+x)*4+2]);
  const band=(vertical:boolean,position:number,start:number,end:number)=>{
    let dark=0,total=0;
    for(let i=start;i<end;i++){const v=vertical?brightness(position,i):brightness(i,position);dark+=Number(v<=18);total+=v;}
    return dark/(end-start)>=.98&&total/(end-start)<=12;
  };
  const boundary=(vertical:boolean,position:number,start:number,end:number)=>{
    let total=0;for(let i=start;i<end;i++)total+=vertical?brightness(position,i):brightness(i,position);
    return total/(end-start)>24;
  };
  function paired(vertical:boolean,size:number,start:number,end:number):[number,number]{
    let a=0,b=0;const limit=Math.floor(size*.25);
    while(a<limit&&band(vertical,a,start,end))a++;
    while(b<limit&&band(vertical,size-1-b,start,end))b++;
    if(a<2||b<2||a===limit||b===limit||Math.abs(a-b)>Math.max(2,size*.03)
      ||!boundary(vertical,a+1,start,end)||!boundary(vertical,size-b-2,start,end))return [0,0];
    return [a,b];
  }
  const [top,bottom]=paired(false,height,0,width);
  const [left,right]=paired(true,width,top,height-bottom);
  return {x:left/width,y:top/height,width:(width-left-right)/width,height:(height-top-bottom)/height};
}

export function imageCrop(image:HTMLImageElement):ScreenshotCrop {
  try{
    const canvas=document.createElement('canvas');canvas.width=192;canvas.height=Math.max(16,Math.round(192*image.naturalHeight/image.naturalWidth));
    const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)return {...full};
    context.drawImage(image,0,0,canvas.width,canvas.height);
    const crop=screenshotCrop(context.getImageData(0,0,canvas.width,canvas.height).data,canvas.width,canvas.height);
    // Step past the resampled black/content seam as well as the solid bars.
    if(crop.y>0){crop.y+=1/canvas.height;crop.height-=2/canvas.height;}
    if(crop.x>0){crop.x+=1/canvas.width;crop.width-=2/canvas.width;}
    return crop;
  }catch{return {...full};}
}

export function cropGeometry(width:number,height:number,crop:ScreenshotCrop,boxWidth:number,boxHeight:number){
  const scale=Math.max(boxWidth/(width*crop.width),boxHeight/(height*crop.height));
  return {size:`${width*scale}px ${height*scale}px`,position:`${(boxWidth-width*crop.width*scale)/2-width*crop.x*scale}px ${(boxHeight-height*crop.height*scale)/2-height*crop.y*scale}px`};
}

const thumbnails=new Map<string,string>();
export function bindScreenshotThumbnails(root:HTMLElement){
  for(const image of root.querySelectorAll<HTMLImageElement>('.screenshot-choice img')){
    const source=image.src,cached=thumbnails.get(source);
    if(cached){image.src=cached;continue;}
    const crop=()=>{
      if(!image.isConnected||!image.naturalWidth)return;
      const rect=imageCrop(image);if(rect.width===1&&rect.height===1){thumbnails.set(source,source);if(thumbnails.size>80)thumbnails.delete(thumbnails.keys().next().value!);return;}
      const canvas=document.createElement('canvas');canvas.width=Math.min(600,Math.round(image.naturalWidth*rect.width));canvas.height=Math.round(canvas.width*image.naturalHeight*rect.height/(image.naturalWidth*rect.width));
      const context=canvas.getContext('2d');if(!context)return;
      context.drawImage(image,image.naturalWidth*rect.x,image.naturalHeight*rect.y,image.naturalWidth*rect.width,image.naturalHeight*rect.height,0,0,canvas.width,canvas.height);
      const result=canvas.toDataURL('image/jpeg',.9);thumbnails.set(source,result);if(thumbnails.size>80)thumbnails.delete(thumbnails.keys().next().value!);image.src=result;
    };
    if(image.complete)crop();else image.addEventListener('load',crop,{once:true});
  }
}
