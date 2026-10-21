<#
.SYNOPSIS
    Publishes rtxForge for Windows and wraps it in a setup .exe.

.DESCRIPTION
    1. `dotnet publish` (self-contained; the BundleEngine target adds the
       engine and the private Python).
    2. Inno Setup compiles windows/installer/rtxForge.iss over that folder.

    Inno Setup comes from the pinned Tools.InnoSetup NuGet package (portable,
    nothing is installed) unless -Iscc points at an existing ISCC.exe.
    The same script runs in .github/workflows/windows-build.yml.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File windows\build\Build-Installer.ps1 -RuntimeIdentifier win-x64
#>
[CmdletBinding()]
param(
    [ValidateSet('win-x64', 'win-arm64')] [string] $RuntimeIdentifier = 'win-x64',
    [string] $Output,
    [string] $Iscc,
    # Skip `dotnet publish` and package an existing publish folder.
    [string] $PublishDir
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Output) { $Output = Join-Path $Root 'windows\out' }
$Platform = @{ 'win-x64' = 'x64'; 'win-arm64' = 'ARM64' }[$RuntimeIdentifier]
$Arch = @{ 'win-x64' = 'x64'; 'win-arm64' = 'arm64' }[$RuntimeIdentifier]
$Version = (Get-Content (Join-Path $Root 'VERSION') -Raw).Trim()

# Pinned compiler: Inno Setup 7.1.0 (Tools.InnoSetup on nuget.org).
$InnoVersion = '7.1.0'
$InnoSha256 = 'aad15c662593c6f5656457a5c001f4591babd72820cacf63f9706d4af5d93b75'

if (-not $PublishDir) {
    $PublishDir = Join-Path $Output "rtxForge-windows-$Arch"
    dotnet publish (Join-Path $Root 'windows\RtxForge.Windows\RtxForge.Windows.csproj') `
        -c Release -r $RuntimeIdentifier -p:Platform=$Platform -p:SelfContained=true -o $PublishDir
    if ($LASTEXITCODE) { throw "dotnet publish failed ($LASTEXITCODE)" }
}
foreach ($required in 'rtxForge.exe', 'python\python.exe', 'engine\windows\engine-host\rtxforge_win_host.py') {
    if (-not (Test-Path (Join-Path $PublishDir $required))) { throw "Publish folder is missing $required" }
}
# A supplied -PublishDir must meet the same runtime contract as our own publish.
# Stale runtime DLLs in that folder do not make a framework-dependent app private.
$runtimeConfig = Join-Path $PublishDir 'rtxForge.runtimeconfig.json'
if (-not (Test-Path -LiteralPath $runtimeConfig)) { throw 'Publish folder is missing rtxForge.runtimeconfig.json' }
$runtimeOptions = (Get-Content -LiteralPath $runtimeConfig -Raw | ConvertFrom-Json).runtimeOptions
if ($runtimeOptions.framework -or $runtimeOptions.frameworks -or
    -not @($runtimeOptions.includedFrameworks | Where-Object { $_.name -eq 'Microsoft.NETCore.App' }).Count) {
    throw 'The installer requires a self-contained publish with its private .NET runtime. Publish with -p:SelfContained=true.'
}
foreach ($runtimeFile in 'coreclr.dll', 'hostfxr.dll', 'hostpolicy.dll', 'System.Private.CoreLib.dll') {
    if (-not (Test-Path -LiteralPath (Join-Path $PublishDir $runtimeFile))) { throw "Private .NET runtime is missing $runtimeFile" }
}

if (-not $Iscc) {
    $cache = Join-Path $Root "windows\RtxForge.Windows\obj\innosetup-$InnoVersion"
    $Iscc = Join-Path $cache 'tools\ISCC.exe'
    if (-not (Test-Path $Iscc)) {
        New-Item -ItemType Directory -Force $cache | Out-Null
        # A .nupkg is a zip; Windows PowerShell's Expand-Archive only accepts the .zip name.
        $package = Join-Path $cache 'tools.innosetup.zip'
        Invoke-WebRequest "https://api.nuget.org/v3-flatcontainer/tools.innosetup/$InnoVersion/tools.innosetup.$InnoVersion.nupkg" -OutFile $package
        $actual = (Get-FileHash $package -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $InnoSha256) { Remove-Item $package; throw "Inno Setup package hash mismatch: $actual" }
        Expand-Archive $package $cache -Force
    }
}

& $Iscc /Q "/DAppVersion=$Version" "/DArch=$Arch" "/DSourceDir=$((Resolve-Path $PublishDir).Path)" "/O$Output" `
    (Join-Path $Root 'windows\installer\rtxForge.iss')
if ($LASTEXITCODE) { throw "Inno Setup failed ($LASTEXITCODE)" }

$setup = Join-Path $Output "rtxForge-Setup-$Version-$Arch.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $(Split-Path $setup -Leaf)" | Set-Content -Encoding ascii "$setup.sha256"
Write-Host "Built $setup"
Write-Host "SHA-256 $hash"
