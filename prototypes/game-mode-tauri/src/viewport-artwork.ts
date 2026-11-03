/** Keep blur surfaces near the viewport without containing or clipping their glow. */
export function setupViewportArtwork(root: HTMLElement): () => void {
  const viewport = root.querySelector<HTMLElement>('#game-results');
  if (!viewport || !('IntersectionObserver' in window)) return () => {};
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) (entry.target as HTMLElement).dataset.artVisible = String(entry.isIntersecting);
  }, {root: viewport, rootMargin: '128px'});
  viewport.querySelectorAll<HTMLElement>('.game-item').forEach(item => {
    item.dataset.artVisible = 'false'; observer.observe(item);
  });
  return () => observer.disconnect();
}
