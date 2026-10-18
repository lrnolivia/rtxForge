<#
.SYNOPSIS
    Adds the rtxForge engine and a private Python to a published Windows app.

.DESCRIPTION
    rtxForge for Windows runs the shared Python engine (engine/, scripts/)
    through windows/engine-host. Users never install Python: the official
    python.org "embeddable package" (no installer, no PATH or registry
    changes) is unpacked into <app>\python, and the engine files are copied
    into <app>\engine. EngineForgeService looks for both next to rtxForge.exe.

    Runs automatically after `dotnet publish` (RtxForge.Windows.csproj) and
    in CI. Downloads are pinned by SHA-256 and cached under obj\.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Output,
    [Parameter(Mandatory)] [ValidateSet('win-x64', 'win-arm64')] [string] $RuntimeIdentifier,
    [string] $Cache
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 has no $PSScriptRoot inside param() defaults.
if (-not $Cache) { $Cache = Join-Path $PSScriptRoot '..\RtxForge.Windows\obj\python-embed' }
$ProgressPreference = 'SilentlyContinue'

# Pinned private runtime: python.org embeddable package.
$PythonVersion = '3.14.5'
$Embeds = @{
    'win-x64'   = @{ Arch = 'amd64'; Sha256 = 'ba6bd811c4eedb19195cf275770ef127e893d63701e24152606e2cb76f6d876a' }
    'win-arm64' = @{ Arch = 'arm64'; Sha256 = '0c078f7646c3b13c2dce0bb690994e431ed5269788803deffb459ee9e78b684e' }
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Output = [IO.Path]::GetFullPath($Output)
$embed = $Embeds[$RuntimeIdentifier]

# .NET instead of Get-FileHash / Expand-Archive: those live in script modules
# that fail to load when Windows PowerShell inherits PowerShell 7's module path.
function Get-Sha256([string] $Path) {
    $stream = [IO.File]::OpenRead($Path)
    try { ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($stream)) -replace '-', '').ToLowerInvariant() }
    finally { $stream.Dispose() }
}
Add-Type -AssemblyName System.IO.Compression.FileSystem

# ---------- Python ----------
New-Item -ItemType Directory -Force $Cache | Out-Null
$zipName = "python-$PythonVersion-embed-$($embed.Arch).zip"
$zip = Join-Path $Cache $zipName
if (-not (Test-Path $zip) -or (Get-Sha256 $zip) -ne $embed.Sha256) {
    Write-Host "Downloading $zipName"
    Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersion/$zipName" -OutFile "$zip.part" -UseBasicParsing
    $hash = Get-Sha256 "$zip.part"
    if ($hash -ne $embed.Sha256) { Remove-Item "$zip.part"; throw "$zipName hash mismatch: $hash" }
    Move-Item "$zip.part" $zip -Force
}
$python = Join-Path $Output 'python'
if (Test-Path $python) { Remove-Item $python -Recurse -Force }
[IO.Compression.ZipFile]::ExtractToDirectory($zip, $python)
Write-Host "Python $PythonVersion ($($embed.Arch)) -> $python"

# ---------- Engine ----------
$engine = Join-Path $Output 'engine'
if (Test-Path $engine) { Remove-Item $engine -Recurse -Force }
$copy = @(
    @{ From = 'engine\rtxengine.py' }
    @{ From = 'engine\SOURCE.json' }
    @{ From = 'scripts'; Filter = '*.py' }
    @{ From = 'providers'; Filter = '*.json' }
    @{ From = 'provider.json' }
    @{ From = 'VERSION' }
    @{ From = 'windows\engine-host'; Filter = '*.py' }
    # Add rtxForge to Steam (steam_self_install): app icon and Steam artwork.
    @{ From = 'gui\icons\hicolor\scalable\apps\io.github.lrnolivia.RTXForge.svg' }
    @{ From = 'packaging\steam-artwork\exports'; Filter = '*.png' }  # Steam grid takes PNG/JPEG only
)
foreach ($item in $copy) {
    $source = Join-Path $repo $item.From
    if (-not (Test-Path $source)) { Write-Warning "Skipping missing $($item.From)"; continue }
    if ((Get-Item $source).PSIsContainer) {
        Get-ChildItem $source -Filter $item.Filter -File -Recurse | ForEach-Object {
            $relative = $_.FullName.Substring($repo.Length + 1)
            $target = Join-Path $engine $relative
            New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
            Copy-Item $_.FullName $target
        }
    } else {
        $target = Join-Path $engine $item.From
        New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
        Copy-Item $source $target
    }
}
# The combined C++ dependency has its own source/patch and payload receipt.
# Ordinary development builds may omit it; NR+MFG then refuses with a clear reason.
$bridgeRoot = Join-Path $repo 'windows\out\skynizz-bridge'
$bridgeReceipt = Join-Path $bridgeRoot 'package.json'
if ($RuntimeIdentifier -eq 'win-x64' -and (Test-Path -LiteralPath $bridgeReceipt)) {
    $receipt = Get-Content -LiteralPath $bridgeReceipt -Raw | ConvertFrom-Json
    $expectedName = 'rtxForge-Skynizz-' + $receipt.tag + '-MFG.zip'
    if ($receipt.archive -ne $expectedName -or $receipt.variant -ne 'nr-mfg-bridge') { throw 'Unsafe combined bridge receipt' }
    $archive = Join-Path $bridgeRoot $expectedName
    if ((Get-Sha256 $archive) -ne $receipt.sha256) { throw 'Combined bridge archive changed before bundling' }
    $target = Join-Path $engine 'providers\skynizz-bridge'
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -LiteralPath $bridgeReceipt -Destination $target
    Copy-Item -LiteralPath $archive -Destination $target
}
$count = (Get-ChildItem $engine -Recurse -File).Count
Write-Host "Engine ($count files) -> $engine"
