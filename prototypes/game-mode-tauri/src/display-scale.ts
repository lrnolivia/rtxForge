/** A chosen percentage is the total physical scale, independent of OS DPI. */
export function webviewZoom(scale:'auto'|number,systemScale:number,monitor?:{width:number;height:number}) {
  const dpi=Number.isFinite(systemScale)&&systemScale>0?systemScale:1;
  if(scale!=='auto')return scale/100/dpi;
  // Use the display resolution, not the already scaled webview dimensions.
  const fourK=monitor&&Math.max(monitor.width,monitor.height)>=3840&&Math.min(monitor.width,monitor.height)>=2160;
  return fourK?2/dpi:1;
}
