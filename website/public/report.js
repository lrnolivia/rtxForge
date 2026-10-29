import { initTheme } from './theme.mjs';

initTheme();
const form = document.getElementById('beta-report');
const platform = document.getElementById('platform');
const copy = document.getElementById('copy-report');
const preview = document.getElementById('report-preview');
const report = document.getElementById('report-text');
const status = document.getElementById('report-status');
let previousOS = '';
const fields = [
  ['platform', 'Operating system'], ['distribution', 'Distro / OS version'],
  ['gpu-series', 'RTX series'], ['gpu', 'GPU model and driver'],
  ['app-format', 'rtxForge app format'], ['app-build', 'rtxForge version / channel'],
  ['game', 'Game and version'], ['feature-package', 'Feature package / provider and version'],
  ['features', 'Features attempted'], ['nr-result', 'NR result'], ['mfg-result', 'MFG result']
];

function updateReport() {
  const os = platform.value.toLowerCase();
  const distribution = document.getElementById('distribution');
  if (previousOS && os !== previousOS) distribution.value = '';
  previousOS = os;
  for (const section of form.querySelectorAll('fieldset')) { section.hidden = !os; section.disabled = !os; }
  for (const option of document.querySelectorAll('[data-format-os]')) {
    option.hidden = option.disabled = option.dataset.formatOs !== os;
    if (option.disabled && option.selected) document.getElementById('app-format').value = '';
  }
  const data = new FormData(form);
  const value = id => String(data.get(id) || '').trim();
  document.documentElement.dataset.os = os;
  const guide = os ? `install.html?os=${os}` : 'install.html';
  document.getElementById('report-guide').href = guide;
  document.getElementById('report-footer-guide').href = guide;
  for (const link of document.querySelectorAll('[data-report-home]')) link.href = os ? `./?os=${os}` : './';
  document.getElementById('distribution-label').textContent = os === 'windows' ? 'Windows version' : 'Linux distro and version';
  distribution.placeholder = os === 'windows' ? 'e.g. Windows 11 25H2' : 'e.g. Bazzite 44';
  distribution.setAttribute('list', os === 'windows' ? 'windows-versions' : 'distros');
  document.getElementById('observations-hint').textContent = (os === 'linux' ? 'Include Proton version and game API if known. ' : 'Include your DirectX / game API version if known. ') + 'Add longer logs or reviewed support-report attachments on GitHub.';
  document.getElementById('os-hint').textContent = os ? `Showing ${platform.value} setup fields.` : 'Choose an OS to see its setup fields.';
  form.querySelector('[type=submit]').disabled = !os;
  const appImage = data.get('app-format') === 'AppImage';
  document.getElementById('appimage-help').hidden = !appImage;
  const game = value('game');
  document.getElementById('report-title').value = `[Beta report] ${game || platform.value}${game && os ? ` · ${platform.value}` : ''}`;
  report.value = '# rtxForge beta report\n\n' + fields.map(([id, label]) => `${id === 'distribution' && os ? document.getElementById('distribution-label').textContent : label}: ${value(id) || '[fill in]'}`).join('\n')
    + `\n\nSteps, expected result, and observed result:\n${value('observations') || '[fill in]'}\n\n`
    + `Installation guide: https://loew.fi/rtxforge/install${os ? `?os=${os}` : ''}\n`
    + (appImage ? 'AppImage host dependencies: https://loew.fi/rtxforge/install?os=linux#appimage\n' : '')
    + '\nAttach a reviewed support report on GitHub if available.\n';
  copy.textContent = fields.some(([id]) => id !== 'platform' && value(id)) || value('observations') ? 'Copy report' : 'Copy report template';
}
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
