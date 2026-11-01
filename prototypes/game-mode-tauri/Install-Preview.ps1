[CmdletBinding()]
param([string]$SourcePath = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$source = [IO.Path]::GetFullPath($SourcePath)
if (-not (Test-Path -LiteralPath (Join-Path $source 'build.json'))) {
    $source = Join-Path $PSScriptRoot 'out/rtxForge-Game-Mode-Preview-win-x64'
}
$receipt = Get-Content -LiteralPath (Join-Path $source 'build.json') -Raw | ConvertFrom-Json
if ($receipt.source -notmatch '^[a-f0-9]{40}$' -or $receipt.version -notmatch '^[0-9A-Za-z.-]+$') { throw 'Invalid preview build receipt.' }
$exe = Join-Path $source 'rtxforge-game-mode.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Extract the complete portable preview before installing.' }
$root = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs/rtxForge Game Mode Preview'))
$version = $receipt.version + '-' + $receipt.source.Substring(0, 8)
$destination = [IO.Path]::GetFullPath((Join-Path $root "versions/$version"))
if (-not $destination.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid preview destination.' }
if (Test-Path -LiteralPath $destination) {
    $installedExe = Join-Path $destination 'rtxforge-game-mode.exe'
    if (-not (Test-Path -LiteralPath $installedExe) -or (Get-FileHash -LiteralPath $installedExe).Hash -ne (Get-FileHash -LiteralPath $exe).Hash) {
        throw 'A different build already occupies this version. Install from a new source revision.'
    }
} else {
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $destination -Recurse -Force
}
$programs = [Environment]::GetFolderPath('Programs')
$shortcutPath = Join-Path $programs 'rtxForge Game Mode Preview.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $destination 'rtxforge-game-mode.exe'
$shortcut.WorkingDirectory = $destination
$shortcut.Description = 'rtxForge Game Mode preview. Read-only by default.'
$shortcut.IconLocation = $shortcut.TargetPath + ',0'
$shortcut.Save()
@{ installedAt=[DateTime]::UtcNow.ToString('o'); source=$receipt.source; version=$receipt.version; path=$destination; shortcut=$shortcutPath } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'installed.json') -Encoding utf8
Write-Output $destination
