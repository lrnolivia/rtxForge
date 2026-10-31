param(
  [Parameter(Mandatory)][string]$RmlSource,
  [Parameter(Mandatory)][string]$FreetypeRoot,
  [string]$Output=(Join-Path $PSScriptRoot '../out/glass-overlay')
)
$ErrorActionPreference='Stop'
$RmlSource=(Resolve-Path -LiteralPath $RmlSource).Path
$FreetypeRoot=(Resolve-Path -LiteralPath $FreetypeRoot).Path
$pin='ae4e0dcb52b324a0d0fc36ed51f633c8c3fe06b7'
$head=(& git -C $RmlSource rev-parse HEAD).Trim()
if($LASTEXITCODE -or $head -ne $pin){throw "Glass overlay requires pinned RmlUi $pin"}
$repo=Split-Path (Split-Path $PSScriptRoot)
$policy=Get-Content -LiteralPath (Join-Path $repo 'providers/glass-overlay/rollout-policy.json') -Raw | ConvertFrom-Json
if($policy.schema -ne 1 -or $policy.revision -lt 1){throw 'Invalid glass overlay revision policy'}
$build=Join-Path $Output 'build'
cmake -S (Join-Path $repo 'windows/overlay-rmlui') -B $build -A x64 "-DRMLUI_SOURCE=$RmlSource" "-DFREETYPE_ROOT=$FreetypeRoot"
if($LASTEXITCODE){throw 'Glass overlay configuration failed'}
cmake --build $build --config Release --parallel 6
if($LASTEXITCODE){throw 'Glass overlay build failed'}
& (Join-Path $build 'Release/GlassSmokeTest.exe') (Join-Path $build 'Release/rtxforge-glass.dll')
if($LASTEXITCODE){throw 'Glass overlay render/state checks failed'}
Copy-Item -LiteralPath (Join-Path $build 'Release/rtxforge-glass.dll') -Destination $Output -Force
$notices=Join-Path $Output 'notices'
New-Item -ItemType Directory -Force -Path $notices | Out-Null
Copy-Item -LiteralPath (Join-Path $RmlSource 'LICENSE.txt') -Destination (Join-Path $notices 'RmlUi.txt') -Force
Get-ChildItem -LiteralPath (Join-Path $repo 'providers/glass-overlay/notices') -File | Copy-Item -Destination $notices -Force
foreach($file in 'gui/fonts/OFL-Roboto.txt','gui/fonts/OFL-BakbakOne.txt','windows/RtxForge.Windows/Assets/Fonts/OFL-Inter.txt','prototypes/overlay-rmlui/icons/LICENSE') {
  $source=Join-Path $repo $file
  if(-not (Test-Path -LiteralPath $source)){throw "Missing dependency notice: $file"}
  Copy-Item -LiteralPath $source -Destination $notices -Force
}
$dll=Get-Item -LiteralPath (Join-Path $Output 'rtxforge-glass.dll')
$receipt=[ordered]@{schema=1;renderer='rmlui';abi=2;revision=$policy.revision;commit=(& git -C $repo rev-parse HEAD).Trim();rmlui=$pin;api_acceptance=@('dx11-single-threaded-fixture','dx11-sdr-fixture','dx11-scrgb-fixture','dx11-hdr10-fixture','dx12-interop-fixture','dx12-hdr10-interop-fixture');gameplay_verified=$false;files=@{'rtxforge-glass.dll'=@{sha256=(Get-FileHash -LiteralPath $dll.FullName -Algorithm SHA256).Hash.ToLowerInvariant();size=$dll.Length}}}
[IO.File]::WriteAllText((Join-Path $Output 'package.json'),($receipt|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
