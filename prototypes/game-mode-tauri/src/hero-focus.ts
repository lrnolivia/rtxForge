/** Desktop stores normalized coordinates in the original artwork. */
export function heroCrop(width:number,height:number,imageWidth:number,imageHeight:number,focus:readonly number[],anchorY=.3){
  if(!width||!height||!imageWidth||!imageHeight)return {x:50,y:30,markerX:50,markerY:30};
  const scale=Math.max(width/imageWidth,height/imageHeight),shownWidth=imageWidth*scale,shownHeight=imageHeight*scale;
  const fx=Math.max(0,Math.min(1,focus[0])),fy=Math.max(0,Math.min(1,focus[1]));
  const ratio=(view:number,extent:number,point:number,target:number)=>extent-view<.5?.5:Math.max(0,Math.min(1,(target*view-point*extent)/(view-extent)));
  const x=ratio(width,shownWidth,fx,.5),y=ratio(height,shownHeight,fy,anchorY);
  return {x:x*100,y:y*100,markerX:((width-shownWidth)*x+fx*shownWidth)/width*100,markerY:((height-shownHeight)*y+fy*shownHeight)/height*100};
}

/** The same 96-column saliency calculation as Desktop's FadedImage. */
export function saliencyFocus(pixels:ArrayLike<number>,width:number,height:number):[number,number]{
  const count=width*height;if(width<3||height<3||pixels.length<count*4)return [.5,.3];
  const light=new Float64Array(count),rgb=new Float64Array(count*3),mean=[0,0,0];
  for(let i=0;i<count;i++){const r=pixels[i*4]/255,g=pixels[i*4+1]/255,b=pixels[i*4+2]/255;rgb.set([r,g,b],i*3);light[i]=.299*r+.587*g+.114*b;mean[0]+=r;mean[1]+=g;mean[2]+=b;}
  for(let c=0;c<3;c++)mean[c]/=count;
  const columns=new Float64Array(width),smooth=new Float64Array(width);
  for(let y=Math.max(1,Math.floor(height*.08));y<=Math.min(height-2,Math.floor(height*.92));y++)for(let x=1;x<width-1;x++){
    const i=y*width+x,edge=Math.abs(light[i+1]-light[i-1])+Math.abs(light[i+width]-light[i-width]);
    const distinct=Math.hypot(rgb[i*3]-mean[0],rgb[i*3+1]-mean[1],rgb[i*3+2]-mean[2]);columns[x]+=edge*distinct;
  }
  for(let x=0;x<width;x++){let total=0,n=0;for(let k=Math.max(0,x-6);k<=Math.min(width-1,x+6);k++){total+=columns[k];n++;}smooth[x]=total/n;}
  const peak=Math.max(...smooth);if(peak<=0)return [.5,.3];
  let weighted=0,total=0;for(let x=0;x<width;x++){const weight=(smooth[x]/peak)**8;weighted+=x*weight;total+=weight;}
  return [weighted/total/(width-1),.3];
}
const analyzed=new Map<string,Promise<[number,number]>>();
export function analyzeHeroFocus(image:HTMLImageElement):Promise<[number,number]>{
  const source=image.currentSrc||image.src;let found=analyzed.get(source);
  if(!found){found=(async()=>{
    try{
      const canvas=document.createElement('canvas');canvas.width=96;canvas.height=Math.max(3,Math.round(96*image.naturalHeight/image.naturalWidth));
      const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)return [.5,.3] as [number,number];
      context.imageSmoothingQuality='high';context.drawImage(image,0,0,canvas.width,canvas.height);
      const point=saliencyFocus(context.getImageData(0,0,canvas.width,canvas.height).data,canvas.width,canvas.height);
      // Where the host exposes on-device face detection, use Desktop's same check.
      const Detector=(window as unknown as {FaceDetector?:new()=>{detect(image:HTMLImageElement):Promise<{boundingBox:DOMRect}[]>}}).FaceDetector;
      if(Detector){
        const faces=await new Detector().detect(image),largest=Math.max(0,...faces.map(face=>face.boundingBox.width));let x=0,total=0;
        for(const {boundingBox:box} of faces)if(box.width>=largest*.7){const area=box.width*box.height;x+=(box.x+box.width/2)*area;total+=area;}
        if(total&&Math.abs(x/total/image.naturalWidth-point[0])>largest/image.naturalWidth*.75)point[0]=x/total/image.naturalWidth;
      }
      return point;
    }catch{return [.5,.3] as [number,number];}
  })();analyzed.set(source,found);if(analyzed.size>24)analyzed.delete(analyzed.keys().next().value!);}
  return found;
}
