import { platformFromLocation } from './platforms.mjs';
import { initTheme } from './theme.mjs';

initTheme();
const form = document.getElementById('beta-report');
const platform = document.getElementById('platform');
const copy = document.getElementById('copy-report');
const preview = document.getElementById('report-preview');
const report = document.getElementById('report-text');
const status = document.getElementById('report-status');
const fields = [
  ['platform', 'Operating system'], ['distribution', 'Distro / OS version'],
  ['gpu-series', 'RTX series'], ['gpu', 'GPU model and driver'],
  ['app-format', 'rtxForge app format'], ['app-build', 'rtxForge version / channel'],
  ['game', 'Game and version'], ['feature-package', 'Feature package / provider and version'],
  ['features', 'Features attempted'], ['nr-result', 'NR result'], ['mfg-result', 'MFG result']
];

function updateReport() {
  const data = new FormData(form);
  const os = platform.value === 'Windows' ? 'windows' : 'linux';
  document.documentElement.dataset.os = os;
  const guide = `install.html?os=${os}`;
  document.getElementById('report-guide').href = guide;
  document.getElementById('report-footer-guide').href = guide;
  for (const link of document.querySelectorAll('[data-report-home]')) link.href = `./?os=${os}`;
  document.getElementById('distribution').placeholder = os === 'linux' ? 'e.g. Bazzite 44' : 'e.g. Windows 11 25H2';
  const appImage = data.get('app-format') === 'AppImage';
  document.getElementById('appimage-help').hidden = os !== 'linux' && !appImage;
  const game = data.get('game').trim();
  document.getElementById('report-title').value = `[Beta report] ${game || platform.value}${game ? ` · ${platform.value}` : ''}`;
  report.value = '# rtxForge beta report\n\n' + fields.map(([id, label]) => `${label}: ${data.get(id).trim() || '[fill in]'}`).join('\n')
    + `\n\nSteps, expected result, and observed result:\n${data.get('observations').trim() || '[fill in]'}\n\n`
    + `Installation guide: https://loew.fi/rtxforge/install?os=${os}\n`
    + (os === 'linux' || appImage ? 'AppImage host dependencies: https://loew.fi/rtxforge/install?os=linux#appimage\n' : '')
    + '\nAttach a reviewed support report on GitHub if available.\n';
  copy.textContent = fields.some(([id]) => id !== 'platform' && data.get(id).trim()) || data.get('observations').trim() ? 'Copy report' : 'Copy report template';
}
platform.value = platformFromLocation() === 'windows' ? 'Windows' : 'Linux';
copy.hidden = false;
preview.hidden = false;
form.addEventListener('input', () => { status.textContent = ''; updateReport(); });
form.addEventListener('change', updateReport);
copy.addEventListener('click', async () => {
  const text = report.value;
  try {
    await navigator.clipboard.writeText(text);
    status.textContent = 'Report copied. Paste it into GitHub or your discussion.';
  } catch {
    preview.open = true;
    report.focus(); report.select();
    status.textContent = 'Automatic copying is unavailable. The report text is selected; copy it with your browser’s Copy command.';
  }
});
form.addEventListener('submit', event => {
  updateReport();
  const destination = new URL(form.action);
  destination.search = new URLSearchParams(new FormData(form)).toString();
  // GitHub rejects oversized query strings. Keep the complete report available to copy.
  if (destination.href.length > 7000) {
    event.preventDefault();
    preview.open = true;
    report.focus(); report.select();
    status.replaceChildren('This report is too long for a GitHub link. Copy the selected text, then ');
    const link = document.createElement('a');
    link.href = `${form.action}?template=beta-report.yml`;
    link.textContent = 'open the GitHub issue form';
    status.append(link, ' and paste your details there.');
  }
});
updateReport();
