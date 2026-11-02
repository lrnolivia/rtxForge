/** Collapse shell chrome from real scrolling, without an idle animation loop. */
export function setupShellLayout(root: HTMLElement): () => void {
  const shell = root.querySelector<HTMLElement>('.shell');
  if (!shell) return () => {};
  const scrollers = [...root.querySelectorAll<HTMLElement>('#content,#game-results,.details-scroll')];
  let frame = 0;
  const update = () => {
    frame = 0;
    const top = Math.max(0, ...scrollers.map(node => node.scrollTop));
    const collapsed = shell.dataset.headerCollapsed === 'true';
    if (top > 96 || collapsed && top > 8) shell.dataset.headerCollapsed = 'true';
    else shell.dataset.headerCollapsed = 'false';
  };
  const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
  scrollers.forEach(node => node.addEventListener('scroll', schedule, {passive:true}));
  schedule();
  return () => { cancelAnimationFrame(frame); scrollers.forEach(node => node.removeEventListener('scroll', schedule)); };
}
