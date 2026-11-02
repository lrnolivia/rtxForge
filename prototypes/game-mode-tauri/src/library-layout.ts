/** Fit complete rows without changing artwork ratios, type size or native zoom. */
export function libraryColumns(width: number, height: number, footer: number, ratio: number, gap: number, size=100) {
  const minimum = ratio > 1 ? 120 : 240;
  const minimumRow=(minimum-10)*ratio+footer;
  const preferredRow=ratio>1?360:300;
  const rows=height>=3*preferredRow+2*gap?3:height>=2*minimumRow+gap?2:1;
  const rowHeight = (height - (rows - 1) * gap) / rows;
  const maximum = ratio > 1 ? 280 : 560;
  const artworkWidth = (rowHeight - footer) / ratio + 10;
  const target = Math.max(minimum*.7, Math.min(maximum*1.4, artworkWidth*size/100));
  const columns=Math.max(1,Math.ceil((width+gap)/(target+gap)));
  const actualWidth=(width-(columns-1)*gap)/columns;
  const actualHeight=(actualWidth-10)*ratio+footer;
  return {columns,rows:Math.max(1,Math.min(4,Math.floor((height+gap)/(actualHeight+gap))))};
}

export function setupLibraryLayout(root: HTMLElement): () => void {
  const content = root.querySelector<HTMLElement>('#content');
  const grid = root.querySelector<HTMLElement>('.games:not(.game-list)');
  const results = root.querySelector<HTMLElement>('#game-results');
  if (results) results.style.removeProperty('max-height');
  if (!content || !grid) return () => {};
  let frame = 0, disposed = false;
  const arrange = () => {
    frame = 0;
    if (disposed || !grid.isConnected) return;
    const style = getComputedStyle(grid), padding = getComputedStyle(content);
    // offset geometry is independent of screen-arrival animation transforms.
    let top = 0, node: HTMLElement | null = grid;
    while (node && node !== content) { top += node.offsetTop; node = node.offsetParent as HTMLElement | null; }
    const height = content.clientHeight - top - parseFloat(padding.paddingBottom) - 8;
    const copy = grid.querySelector<HTMLElement>('.game-copy,.skeleton-copy');
    const footer = (copy?.offsetHeight || 94) + 5;
    const gap = parseFloat(style.columnGap) || 24;
    const wide = grid.classList.contains('game-capsules');
    const result = libraryColumns(grid.clientWidth - 4, height, footer, wide ? 43 / 92 : 1.5, gap,Number(document.documentElement.dataset.libraryScale)||100);
    grid.style.setProperty('--library-columns', String(result.columns));
    grid.dataset.visibleRows = String(result.rows);
  };
  const schedule = () => { if (!disposed && !frame) frame = requestAnimationFrame(arrange); };
  const observer = new ResizeObserver(schedule);
  observer.observe(content); observer.observe(grid);
  root.querySelectorAll<HTMLElement>('.page-heading,.library-tools,.library-operation-bar,.selection-bar,.notice').forEach(node => observer.observe(node));
  void document.fonts.ready.then(schedule);
  arrange();
  return () => { disposed = true; observer.disconnect(); cancelAnimationFrame(frame); };
}
