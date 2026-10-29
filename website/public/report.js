import { initTheme } from './theme.mjs';
import { initSiteControls } from './site-controls.mjs';

initTheme();
const form = document.getElementById('beta-report');
const platform = document.getElementById('platform');
const copy = document.getElementById('copy-report');
const preview = document.getElementById('report-preview');
const report = document.getElementById('report-text');
const status = document.getElementById('report-status');
let previousOS = '';
const site = initSiteControls(os => {
  platform.value = os === 'linux' ? 'Linux' : os === 'windows' ? 'Windows' : '';
  updateReport();
});
// The select remains a native, required form field for no-JavaScript visitors.
platform.closest('.report-os').hidden = true;
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
    if (option.disabled && option.selected) document.getElementById('app-format').value = 'Not sure';
  }
  const family = document.getElementById('gpu').value.match(/\bRTX\s*(20|30|40|50)\d{2}/i);
  document.getElementById('gpu-series').value = os && family ? `RTX ${family[1]}` : 'Not sure';
  const data = new FormData(form);
  const value = id => String(data.get(id) || '').trim();
  site.select(os, { notify: false });
  document.getElementById('report-os-prompt').hidden = Boolean(os);
  const guide = os ? `install.html?os=${os}` : 'install.html';
  document.getElementById('report-guide').href = guide;
  document.getElementById('footer-guide-link').href = guide;
  for (const link of document.querySelectorAll('[data-report-home]')) link.href = os ? `./?os=${os}` : './';
  document.getElementById('distribution-label').textContent = os === 'windows' ? 'Windows version' : 'Linux distro and version';
  distribution.placeholder = os === 'windows' ? 'e.g. Windows 11 25H2' : 'e.g. Bazzite 44';
  distribution.setAttribute('list', os === 'windows' ? 'windows-versions' : 'distros');
  document.getElementById('observations-hint').textContent = os === 'linux' ? 'An error message or Proton version can help. Add logs later on GitHub.' : 'An error message can help. Add logs later on GitHub.';
  document.getElementById('os-hint').hidden = Boolean(os);
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
  copy.textContent = os ? 'Copy report' : 'Copy blank template';
}
copy.hidden = false;
preview.hidden = false;
form.addEventListener('input', () => { status.textContent = ''; updateReport(); });
form.addEventListener('change', updateReport);
copy.addEventListener('click', async () => {
  const text = report.value;
  try {
    await navigator.clipboard.writeText(text);
    status.textContent = 'Copied. Paste it wherever you’re discussing the issue.';
  } catch {
    preview.open = true;
    report.focus(); report.select();
    status.textContent = 'Copy didn’t work. The text is selected. Use your browser’s Copy command.';
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
    status.replaceChildren('This is too long for a link. Copy the selected text, then ');
    const link = document.createElement('a');
    link.href = `${form.action}?template=beta-report.yml`;
    link.textContent = 'open the GitHub issue form';
    status.append(link, ' and paste your details there.');
  }
});
const requestedOS = () => new URL(location.href).searchParams.get('os');
site.select(requestedOS());
addEventListener('popstate', () => site.select(requestedOS()));
