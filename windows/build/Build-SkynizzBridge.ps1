param(
    [Parameter(Mandatory)][string]$SourceRoot,
    [string]$Output = (Join-Path $PSScriptRoot '..\out\skynizz-bridge'),
    [switch]$PlacementCandidate,
    [switch]$PanelCandidate
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$source = (Resolve-Path -LiteralPath $SourceRoot).Path
$specRoot = Join-Path $repo 'providers\skynizz-bridge'
if ($PanelCandidate) { $PlacementCandidate = $true }
$spec = Get-Content -LiteralPath (Join-Path $specRoot 'source.json') -Raw | ConvertFrom-Json
$patch = Join-Path $specRoot $spec.patch
if ((Get-FileHash -LiteralPath $patch -Algorithm SHA256).Hash.ToLowerInvariant() -ne $spec.patch_sha256) { throw 'Bridge patch digest mismatch' }
$head = (& git -C $source rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $spec.upstream.commit) { throw 'Skynizz source is not the admitted commit' }
if (& git -C $source status --porcelain --untracked-files=no) { throw 'Skynizz checkout has tracked edits before patching' }
& git -C $source apply --check -- $patch
if ($LASTEXITCODE -ne 0) { throw 'Bridge patch does not apply to the exact source' }
& git -C $source apply -- $patch
if ($LASTEXITCODE -ne 0) { throw 'Bridge source patch failed' }
$candidate = $null
if ($PlacementCandidate) {
    if (-not $PSBoundParameters.ContainsKey('Output')) { $Output = Join-Path $PSScriptRoot '..\out\skynizz-placement-candidate' }
    $candidate = Get-Content -Raw -LiteralPath (Join-Path $specRoot 'placement-candidate.json') | ConvertFrom-Json
    if ($candidate.base_bridge_id -ne $spec.id -or $candidate.base_patch_sha256 -ne $spec.patch_sha256) { throw 'Placement candidate has a different base bridge' }
    foreach ($entry in @(@{name=$candidate.patch; hash=$candidate.patch_sha256}, @{name=$candidate.header; hash=$candidate.header_sha256})) {
        if ((Get-FileHash -LiteralPath (Join-Path $specRoot $entry.name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.hash) { throw 'Placement candidate source digest mismatch' }
    }
    & git -C $source apply --check -- (Join-Path $specRoot $candidate.patch)
    if ($LASTEXITCODE -ne 0) { throw 'Placement candidate does not apply to the admitted base' }
    & git -C $source apply -- (Join-Path $specRoot $candidate.patch)
    if ($LASTEXITCODE -ne 0) { throw 'Placement candidate patch failed' }
    Copy-Item -LiteralPath (Join-Path $specRoot $candidate.header) -Destination (Join-Path $source 'OptiScaler\dlssnr\ForgeNrRoute.h')
}
$panel = $null
if ($PanelCandidate) {
    if (-not $PSBoundParameters.ContainsKey('Output')) { $Output = Join-Path $PSScriptRoot '..\out\skynizz-panel-candidate' }
    $panel = Get-Content -Raw -LiteralPath (Join-Path $specRoot 'panel-candidate.json') | ConvertFrom-Json
    if ($panel.base_bridge_id -ne $candidate.id) { throw 'Panel candidate has a different placement bridge' }
    foreach ($entry in $panel.sources.PSObject.Properties) {
        if ((Get-FileHash -LiteralPath (Join-Path $repo $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw "Panel source digest mismatch: $($entry.Name)" }
    }
    & git -C $source apply --check -- (Join-Path $specRoot $panel.patch)
    if ($LASTEXITCODE -ne 0) { throw 'Panel candidate does not apply to the admitted source' }
    & git -C $source apply -- (Join-Path $specRoot $panel.patch)
    if ($LASTEXITCODE -ne 0) { throw 'Panel candidate patch failed' }
    & (Join-Path $specRoot 'Generate-Panel.ps1') -SourceRoot $source
}
$msbuild = (Get-Command MSBuild.exe -ErrorAction SilentlyContinue).Source
if (-not $msbuild) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Visual Studio C++ Build Tools are required' }
    $msbuild = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find 'MSBuild\**\Bin\MSBuild.exe' | Select-Object -First 1
}
if (-not $msbuild) { throw 'MSBuild with the x64 C++ toolset was not found' }
$Output = [IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path $Output | Out-Null
$compiled = Join-Path $Output 'compiled'
$common = @('/m', '/v:minimal', '/p:Configuration=Release', '/p:Platform=x64', '/p:PlatformToolset=v143', "/p:SolutionDir=$source\", '/p:PostBuildEventUseInBuild=false')
& $msbuild (Join-Path $source 'OptiScaler\OptiScaler.vcxproj') @common "/p:OutDir=$compiled\main\" "/p:IntDir=$compiled\obj-main\"
if ($LASTEXITCODE -ne 0) { throw 'Combined OptiScaler build failed' }
& $msbuild (Join-Path $source 'OptiScaler\dlssnr\forwarder\dlssnr_forwarder.vcxproj') @common "/p:OutDir=$compiled\forwarder\" "/p:IntDir=$compiled\obj-forwarder\"
if ($LASTEXITCODE -ne 0) { throw 'NR forwarder build failed' }
$stage = Join-Path $Output ('stage-' + [Guid]::NewGuid().ToString('N'))
$payload = Join-Path $stage 'DLSS5-Optimised'
New-Item -ItemType Directory -Force -Path $payload | Out-Null
Copy-Item -LiteralPath (Join-Path $compiled 'main\OptiScaler.dll') -Destination (Join-Path $payload 'OptiScaler.dll')
Copy-Item -LiteralPath (Join-Path $compiled 'forwarder\nvngx.dll_dlssnr.dll') -Destination $payload
Copy-Item -LiteralPath (Join-Path $source 'OptiScaler.ini') -Destination $payload
Copy-Item -LiteralPath (Join-Path $specRoot 'LICENSE') -Destination $payload
Copy-Item -LiteralPath $patch -Destination $payload
if ($candidate) {
    Copy-Item -LiteralPath (Join-Path $specRoot $candidate.patch) -Destination $payload
    Copy-Item -LiteralPath (Join-Path $specRoot $candidate.header) -Destination $payload
}
if ($panel) {
    foreach ($name in @($panel.patch, 'ForgePanel.h', 'Generate-Panel.ps1', 'controls.json', 'panel-candidate.json')) {
        Copy-Item -LiteralPath (Join-Path $specRoot $name) -Destination $payload
    }
    Copy-Item -LiteralPath (Join-Path $repo 'windows\RtxForge.Windows\Assets\Fonts\OFL-Inter.txt') -Destination $payload
}
$productHead = (& git -C $repo rev-parse HEAD).Trim()
$receipt = [ordered]@{
    schema = 1; variant = 'nr-mfg-bridge'; id = 'skynizz'; family = 'skynizz'; name = 'Skynizz NR + Ada MFG bridge'
    repo = 'lrnolivia/rtxForge'; tag = $spec.upstream.tag; commit = $productHead
    upstream = $spec.upstream; mfg_source = $spec.mfg_source; patch_sha256 = $spec.patch_sha256
    bridge_id = $spec.id; runtime_verified = $false; selected_source = 'bundled-bridge'
    license = $spec.license; source_url = "https://github.com/lrnolivia/rtxForge/tree/$productHead/providers/skynizz-bridge"
}
if ($candidate) {
    $receipt.bridge_id = $candidate.id
    $receipt.base_bridge_id = $spec.id
    $receipt.base_patch_sha256 = $spec.patch_sha256
    $receipt.patch_sha256 = $candidate.patch_sha256
    $receipt.route_header_sha256 = $candidate.header_sha256
    $receipt.candidate_only = $true
    $receipt.default_promoted = $false
}
if ($panel) {
    $receipt.bridge_id = $panel.id
    $receipt.panel_sources = $panel.sources
    $receipt.panel_candidate = $true
    $receipt.panel_renderer = 'in-game'
    $receipt.performance_verified = $false
}
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $payload 'rtxforge-bridge.json') -Encoding utf8
$archiveName = 'rtxForge-Skynizz-' + $spec.upstream.tag + '-MFG.zip'
$archive = Join-Path $Output $archiveName
Compress-Archive -LiteralPath $payload -DestinationPath $archive -Force
$receipt.archive = $archiveName
$receipt.url = 'bundled:providers/skynizz-bridge/' + $archiveName
$receipt.sha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
$receipt.release_size = (Get-Item -LiteralPath $archive).Length
$receipt.files = @{}
Get-ChildItem -LiteralPath $payload -File | ForEach-Object { $receipt.files[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Output 'package.json') -Encoding utf8
Write-Host "Combined NR+MFG candidate: $archive"
Write-Host "SHA-256: $($receipt.sha256)"
