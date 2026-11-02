[CmdletBinding()]
param([string]$SourcePath = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$source = [IO.Path]::GetFullPath($SourcePath)
$receiptPath = Join-Path $source 'build.json'
$receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
if ($receipt.schema -ne 2 -or $receipt.source -notmatch '^[a-f0-9]{40}$' -or $receipt.dirty -ne $false) { throw 'Install a complete build from committed source.' }
$python = Join-Path $source 'python/python.exe'
& $python -B (Join-Path $source 'package_bundle.py') --verify $source
if ($LASTEXITCODE -ne 0) { throw 'Application payload verification failed.' }
$root = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs/rtxForge Game Mode'))
$payload = (Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.Substring(0,8).ToLowerInvariant()
$version = $receipt.version + '-' + $receipt.source.Substring(0,8) + '-' + $payload
$destination = [IO.Path]::GetFullPath((Join-Path $root "versions/$version"))
$staging = [IO.Path]::GetFullPath((Join-Path $root ('versions/.staging-' + [Guid]::NewGuid().ToString('N'))))
foreach ($target in @($staging,$destination)) {
    if (-not $target.StartsWith($root + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid installation target.' }
}
if (Test-Path -LiteralPath $destination) {
    & (Join-Path $destination 'python/python.exe') -B (Join-Path $destination 'package_bundle.py') --verify $destination
    if ($LASTEXITCODE -ne 0) { throw 'This installed version has changed. The active shortcut was preserved.' }
} else {
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
    Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $staging -Recurse -Force
    & (Join-Path $staging 'python/python.exe') -B (Join-Path $staging 'package_bundle.py') --verify $staging
    if ($LASTEXITCODE -ne 0) { throw "Staged payload failed verification: $staging" }
    & (Join-Path $staging 'python/python.exe') -B (Join-Path $staging 'package_bundle.py') --smoke $staging
    if ($LASTEXITCODE -ne 0) { throw "Installed host smoke test failed. Previous version preserved; staged files: $staging" }
    Move-Item -LiteralPath $staging -Destination $destination
}
$programs = [Environment]::GetFolderPath('Programs')
$shortcutPath = Join-Path $programs 'rtxForge Game Mode.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $destination 'rtxforge-game-mode.exe'
$shortcut.WorkingDirectory = $destination
$shortcut.Description = 'rtxForge Game Mode'
$shortcut.IconLocation = $shortcut.TargetPath + ',0'
$shortcut.Save()
$installed = Join-Path $root 'installed.json'
if (Test-Path -LiteralPath $installed) { Copy-Item -LiteralPath $installed -Destination (Join-Path $root 'previous.json') -Force }
@{installedAt=[DateTime]::UtcNow.ToString('o');source=$receipt.source;version=$receipt.version;path=$destination;shortcut=$shortcutPath;payload=$payload} |
    ConvertTo-Json | Set-Content -LiteralPath ($installed + '.new') -Encoding utf8
Move-Item -LiteralPath ($installed + '.new') -Destination $installed -Force
Write-Output $destination
