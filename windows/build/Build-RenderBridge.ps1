param(
    [Parameter(Mandatory=$true)][string]$SdkPath,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference = 'Stop'
$rtxRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$rtxSdk = (Resolve-Path -LiteralPath $SdkPath).Path
$rtxReceipt = Get-Content -LiteralPath (Join-Path $rtxRoot 'providers\render-bridge\source.json') -Raw | ConvertFrom-Json
$rtxSdkCommit = & git -C $rtxSdk rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $rtxSdkCommit -ne $rtxReceipt.sdk.commit) { throw 'ReShade SDK revision differs from the pinned source receipt' }
$rtxSdkChanges = & git -C $rtxSdk status --porcelain -- include LICENSE.md
if ($rtxSdkChanges) { throw 'Pinned ReShade SDK headers or license have local changes' }
$rtxOutput = [IO.Path]::GetFullPath($Output)
if ($rtxOutput.StartsWith($rtxRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Use an output directory outside the source checkout' }
New-Item -ItemType Directory -Path $rtxOutput -Force | Out-Null
$rtxBuild = Join-Path $rtxOutput 'build'
& cmake -S (Join-Path $rtxRoot 'windows\render-bridge') -B $rtxBuild -G 'Visual Studio 17 2022' -A x64 "-DRESHADE_SDK_DIR=$rtxSdk/include"
if ($LASTEXITCODE -ne 0) { throw 'Render bridge configuration failed' }
& cmake --build $rtxBuild --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw 'Render bridge build failed' }
& ctest --test-dir $rtxBuild -C Release --output-on-failure
if ($LASTEXITCODE -ne 0) { throw 'Render bridge lifetime tests failed' }
$rtxBinary = Join-Path $rtxBuild 'Release\rtxforge-render-bridge.addon64'
Copy-Item -LiteralPath $rtxBinary -Destination $rtxOutput
Copy-Item -LiteralPath (Join-Path $rtxBuild 'Release\render_bridge_harness.exe') -Destination $rtxOutput
Copy-Item -LiteralPath (Join-Path $rtxRoot 'windows\render-bridge\THIRD_PARTY_NOTICES.md') -Destination $rtxOutput
$rtxHead = & git -C $rtxRoot rev-parse HEAD
$rtxDirty = [bool](& git -C $rtxRoot status --porcelain -- windows/render-bridge windows/build/Build-RenderBridge.ps1 providers/render-bridge)
@{schema=1;source_commit=$rtxHead;source_dirty=$rtxDirty;sdk_commit=$rtxSdkCommit;stage='diagnostic';sr_implemented=$false;fg_implemented=$false;sha256=(Get-FileHash -LiteralPath $rtxBinary -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $rtxOutput 'build.json') -Encoding UTF8
Write-Output $rtxOutput
