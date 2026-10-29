// A complete report as the app sends it.
export function sample(overrides = {}) {
  return {
    schema: 1,
    report_id: 'r20261029T120000-abc123',
    fields: {
      platform: 'Linux', distribution: 'Bazzite 43', 'gpu-series': 'RTX 40', gpu: 'NVIDIA GeForce RTX 4070 · driver 580.95',
      'app-format': 'AppImage', 'app-build': '1.0.0-beta.7 · Beta', game: 'Control', 'feature-package': 'Skynizz 2.1',
      features: 'NR + MFG', 'nr-result': 'Working in-game', 'mfg-result': 'Not working in-game',
      observations: 'MFG stays at 1x after enabling frame generation.',
      ...overrides,
    },
    details: ['Graphics API: d3d12', 'Steam app ID: 870780'],
  };
}
