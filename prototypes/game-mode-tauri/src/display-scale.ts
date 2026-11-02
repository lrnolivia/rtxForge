/** A chosen percentage is the total physical scale, independent of OS DPI. */
export function webviewZoom(scale:'auto'|number,systemScale:number) {
  return scale==='auto'?1:scale/100/(Number.isFinite(systemScale)&&systemScale>0?systemScale:1);
}
