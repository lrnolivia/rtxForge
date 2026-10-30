"""Application-only update handoff. Runs outside the installation being replaced."""
import json
import os
from pathlib import Path
import subprocess
import uuid

import auto_update


RUNNER = r'''
param([string]$Receipt)
$ErrorActionPreference = 'Stop'
$p = Get-Content -LiteralPath $Receipt -Raw | ConvertFrom-Json
$updateMutex = New-Object System.Threading.Mutex($false, 'Local\rtxForge.ApplicationUpdate')
$ownsUpdate = $false
$recoveryReady = $false
$setupStarted = $false
$backup = Join-Path (Split-Path -Parent $Receipt) 'previous-installation'
# Both mirror destinations are resolved and bounded before robocopy can remove
# obsolete files. The app path comes from the installed executable, never a URL.
$updateRoot = [IO.Path]::GetFullPath((Split-Path -Parent $Receipt)).TrimEnd('\') + '\'
$backup = [IO.Path]::GetFullPath($backup)
if (!$backup.StartsWith($updateRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid recovery directory.' }
if ([IO.Path]::GetFullPath($p.folder) -ne (Split-Path -Parent ([IO.Path]::GetFullPath($p.exe)))) { throw 'Invalid installation directory.' }
try {
    try { $ownsUpdate = $updateMutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $ownsUpdate = $true }
    if (!$ownsUpdate) { throw 'Another update is already installing.' }
    $old = Get-Process -Id $p.pid -ErrorAction SilentlyContinue
    if ($old -and !$old.WaitForExit(120000)) { throw 'The application did not close. Update postponed.' }
    $otherApps = Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -eq $p.exe -and $_.CommandLine -notmatch '--overlay-helper'
    }
    if ($otherApps) { throw 'Close other rtxForge windows before updating.' }
    $installedVersion = (Get-Content -LiteralPath (Join-Path $p.folder 'engine\VERSION') -Raw).Trim()
    if ($installedVersion -ne $p.from_version) { throw 'The installed version changed. Check for updates again.' }
    if ((Get-FileHash -LiteralPath $p.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $p.sha256) {
        throw 'The staged installer changed. Nothing was installed.'
    }
    & robocopy $p.folder $backup /MIR /XJ /R:1 /W:1 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw 'Could not preserve the previous app. Nothing was installed.' }
    $recoveryReady = $true
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/SP-', '/NORESTART',
        ('/DIR="' + $p.folder + '"'), ('/LOG="' + $p.log + '"'))
    $setupStarted = $true
    $setup = Start-Process -FilePath $p.path -ArgumentList $arguments -PassThru -Wait -WindowStyle Hidden
    if ($setup.ExitCode -ne 0) { throw ('Setup failed with code ' + $setup.ExitCode + '. See ' + $p.log) }
    if ($p.restart) {
        if ($p.game_mode) { Start-Process -FilePath $p.exe -ArgumentList '--game-mode' }
        else { Start-Process -FilePath $p.exe }
    } elseif ($p.helper) {
        Start-Process -FilePath $p.exe -ArgumentList '--overlay-helper' -WindowStyle Hidden
    }
    @{ok=$true; version=$p.version} | ConvertTo-Json | Set-Content -LiteralPath $p.result -Encoding UTF8
} catch {
    $failure = $_.Exception.Message
    if ($setupStarted -and $recoveryReady) {
        & robocopy $backup $p.folder /MIR /XJ /R:1 /W:1 /NFL /NDL /NJH /NJS | Out-Null
        if ($LASTEXITCODE -ge 8) { $failure += ' Recovery failed; reinstall from the release page. Backups remain in your profile.' }
        else { $failure += ' The previous application was restored.' }
    }
    @{ok=$false; error=$failure} | ConvertTo-Json | Set-Content -LiteralPath $p.result -Encoding UTF8
} finally {
    if ($ownsUpdate) { $updateMutex.ReleaseMutex() }
    $updateMutex.Dispose()
}
'''


def installed_executable():
    exe = Path(os.environ.get('RTXFORGE_APP_EXE', ''))
    if not exe.is_absolute() or exe.name.lower() != 'rtxforge.exe' or not (exe.parent / 'unins000.exe').is_file():
        raise RuntimeError('Automatic installation requires the installed Windows app. Update a portable copy by extracting the new ZIP.')
    return exe


def previous_failure(folder):
    result = Path(folder) / 'last-result.json'
    if not result.is_file():
        return None
    try:
        record = json.loads(result.read_text(encoding='utf-8-sig'))
        return record.get('error') if record.get('ok') is False else None
    finally:
        result.unlink(missing_ok=True)


def launch(info, path, *, pid, restart, game_mode, helper, folder):
    exe = installed_executable()
    if not auto_update.verified(path, info):
        raise RuntimeError('The staged update changed. Check for updates again.')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex
    runner = folder / ('apply-' + key + '.ps1')
    receipt = folder / ('apply-' + key + '.json')
    runner.write_text(RUNNER, encoding='utf-8')
    receipt.write_text(json.dumps({**info, 'path': str(path), 'pid': int(pid), 'exe': str(exe),
                                  'folder': str(exe.parent), 'restart': bool(restart), 'game_mode': bool(game_mode),
                                  'helper': bool(helper), 'log': str(folder / 'setup.log'),
                                  'result': str(folder / 'last-result.json')}), encoding='utf-8')
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.Popen([str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                      '-File', str(runner), '-Receipt', str(receipt)], close_fds=True,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
    return {'message': 'Update will install after rtxForge closes.'}
