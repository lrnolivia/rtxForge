<#
.SYNOPSIS
    Builds rtxForge's in-game panel for Feeder NR games (two ReShade add-ons).

.DESCRIPTION
    rtxforge-panel.addon64 hosts the same panel OptiScaler shows
    (providers/skynizz-bridge/ForgePanel.h), compiled against OptiScaler's own
    Dear ImGui and FreeType from the admitted Skynizz source, with Feeder
    bindings generated from controls.json. rtxforge-quiet.addon64 hides
    ReShade's startup banner with ReShade's ImGui, which the panel must not
    share. ReShade 6.8.0 add-on headers are downloaded by commit and checked by
    SHA-256.

    Output: <Output>\rtxforge-panel.addon64, rtxforge-quiet.addon64 and
    package.json, which Bundle-Engine.ps1 copies into the app and
    feeder_provider.py verifies.
#>
[CmdletBinding()]
param(
    [string] $Output,
    # A checkout of Skynizz/optiscaler-dlss5 at providers/skynizz-bridge/source.json's commit.
    [string] $SourceRoot
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Output) { $Output = Join-Path $repo 'windows\out\feeder-panel' }
$Output = [IO.Path]::GetFullPath($Output)
$bridge = Join-Path $repo 'providers\skynizz-bridge'
if (-not $SourceRoot) {
    $SourceRoot = @('windows\out\skynizz-source', 'windows\out\skynizz-placement-source') |
        ForEach-Object { Join-Path $repo $_ } | Where-Object { Test-Path (Join-Path $_ 'OptiScaler\include\imgui\imgui.h') } | Select-Object -First 1
}
if (-not $SourceRoot) { throw 'Check out the Skynizz OptiScaler source (see providers/skynizz-bridge/source.json) and pass -SourceRoot.' }
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$spec = Get-Content -LiteralPath (Join-Path $bridge 'source.json') -Raw | ConvertFrom-Json
$head = (& git -C $SourceRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -or $head -ne $spec.upstream.commit) { throw "OptiScaler source is $head, not the admitted $($spec.upstream.commit)" }

$ReShade = '18deaa52de0c425a78b329e9cb3c497281cd00ec'  # crosire/reshade v6.8.0
$ReShadeImGui = '3912b3d9a9c1b3f17431aebafd86d2f40ee6e59c'  # ocornut/imgui, ReShade 6.8.0's deps/imgui
$Headers = [ordered]@{
    'reshade\reshade.hpp'              = @("crosire/reshade/$ReShade/include/reshade.hpp", 'cf3cd150920ea310b4b1e2e4f11ab8d7221a9fc18755f4891a026563311b524c')
    'reshade\reshade_api.hpp'          = @("crosire/reshade/$ReShade/include/reshade_api.hpp", '8d83ec8a620c48da7a20d975bd27b3345b24d3f0d5b78ae4c4fe633d61b804eb')
    'reshade\reshade_api_device.hpp'   = @("crosire/reshade/$ReShade/include/reshade_api_device.hpp", 'a716c44b6fbb064dbbb0826687728f21aa71ed45e13564e4dc1cdf36da5bdfa0')
    'reshade\reshade_api_format.hpp'   = @("crosire/reshade/$ReShade/include/reshade_api_format.hpp", '68caa17fef712043e810ab88770c15af009aa3c7693e5c115ddc324f2d0809a7')
    'reshade\reshade_api_pipeline.hpp' = @("crosire/reshade/$ReShade/include/reshade_api_pipeline.hpp", '5bda8e07260c2c60f0fd18a78b11782aed8f69e5d24b5757874614caafdf416f')
    'reshade\reshade_api_resource.hpp' = @("crosire/reshade/$ReShade/include/reshade_api_resource.hpp", '32cdafe6d783813f3ac72ad43e426638d8d0fef56bcb558fad218a14cfb75ee3')
    'reshade\reshade_events.hpp'       = @("crosire/reshade/$ReShade/include/reshade_events.hpp", '2717f56e2bd89af6d708c9c316353d6581c5a41d4526629fadba51d13be57a89')
    'reshade\reshade_overlay.hpp'      = @("crosire/reshade/$ReShade/include/reshade_overlay.hpp", 'ed914b12fbc41ed038287b0163c0bc934772afcff2c22392044c6008adc5ae79')
    'reshade-imgui\imgui.h'            = @("ocornut/imgui/$ReShadeImGui/imgui.h", '07562842049eaca4e47c3fcdcc9d8eafd442695b9856d6f6639e92e1bb6c737e')
    'reshade-imgui\imconfig.h'         = @("ocornut/imgui/$ReShadeImGui/imconfig.h", '6e5687893594ebfaf8569280cfea83d025904a8a4e23bec073086f6c5bc8f7fb')
}

function Get-Sha256([string] $Path) {
    $stream = [IO.File]::OpenRead($Path)
    try { ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($stream)) -replace '-', '').ToLowerInvariant() }
    finally { $stream.Dispose() }
}

$sdk = Join-Path $Output 'sdk'
foreach ($name in $Headers.Keys) {
    $target = Join-Path $sdk $name
    $source, $expected = $Headers[$name]
    New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
    if (-not (Test-Path $target) -or (Get-Sha256 $target) -ne $expected) {
        Invoke-WebRequest "https://raw.githubusercontent.com/$source" -OutFile "$target.part" -UseBasicParsing
        $hash = Get-Sha256 "$target.part"
        if ($hash -ne $expected) { Remove-Item "$target.part"; throw "$name hash mismatch: $hash" }
        Move-Item "$target.part" $target -Force
    }
}

# Feeder bindings, generated like Generate-Panel.ps1 from the same controls.json,
# so labels, groups and choices match the panel in OptiScaler games.
function CppString([string]$value) {
    $result = [Text.StringBuilder]::new('"')
    foreach ($letter in [Text.Encoding]::UTF8.GetBytes($value)) {
        if ($letter -eq 34 -or $letter -eq 92) { [void]$result.Append('\').Append([char]$letter) }
        elseif ($letter -gt 126) { [void]$result.Append(('\x{0:x2}""' -f $letter)) }
        else { [void]$result.Append([char]$letter) }
    }
    [void]$result.Append('"'); $result.ToString()
}
function CppFloat($value) { ([double]$value).ToString('0.0########', [Globalization.CultureInfo]::InvariantCulture) + 'f' }
# Controls RenoDX DLSS5 has, and its [RenoDX.DLSS5] keys and limits.
$feeder = [ordered]@{
    enabled = @{ ini = 'NeuralUplift' }
    style = @{ ini = 'NRStyle' }
    intensity = @{ ini = 'NRIntensity' }
    preset = @{ ini = 'NRPreset' }
    passes = @{ ini = 'NRPasses'; max = 4; values = @(1, 2, 3, 4); choices = @('1 pass', '2 passes', '3 passes', '4 passes') }
    structure = @{ ini = 'NRLocalStructure' }
    work_scale = @{ ini = 'NRResolutionScale'; max = 1 }
}
$schema = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $bridge 'controls.json') | ConvertFrom-Json
$gen = Join-Path $Output 'gen'
New-Item -ItemType Directory -Force $gen | Out-Null
$lines = [Collections.Generic.List[string]]::new()
$lines.Add('// Generated for Feeder NR from controls.json by Build-FeederPanel.ps1. Do not edit.')
$rows = [Collections.Generic.List[string]]::new()
foreach ($control in $schema.controls) {
    if (-not $feeder.Contains($control.key)) { continue }
    $map = $feeder[$control.key]
    $max = if ($map.ContainsKey('max')) { $map.max } else { $control.max }
    $values = if ($map.ContainsKey('values')) { $map.values } else { $control.values }
    $labels = if ($map.ContainsKey('choices')) { $map.choices } else { $control.choices }
    $choices = 'nullptr, 0'
    if ($control.kind -eq 'choice') {
        $items = for ($i = 0; $i -lt $values.Count; $i++) { '{ ' + (CppFloat $values[$i]) + ', ' + (CppString $labels[$i]) + ' }' }
        $lines.Add('inline constexpr Choice choices_' + $control.key + '[] = { ' + ($items -join ', ') + ' };')
        $choices = 'choices_' + $control.key + ', ' + $values.Count
    }
    $get = '[](Config& c) { return c.Get("' + $map.ini + '", ' + (CppFloat $control.default) + '); }'
    $set = if ($control.key -eq 'enabled') { '[](Config& c, float n, bool) { c.SetNeuralRendering(n); }' }
           else { '[](Config& c, float n, bool) { c.Set("' + $map.ini + '", n, ' + ($(if ($control.kind -eq 'slider') { 'false' } else { 'true' })) + '); }' }
    $rows.Add('  { ' + (CppString $control.key) + ', ' + (CppString $control.label) + ', ' + (CppString $control.advanced) + ', ' + (CppString $control.group) +
              ', Kind::' + $control.kind + ', ' + (CppFloat $control.min) + ', ' + (CppFloat $max) + ', ' + $get + ', ' + $set + ', ' + $choices + ' },')
}
$lines.Add('inline const Control controls[] = {'); $lines.AddRange($rows); $lines.Add('};')
[IO.File]::WriteAllLines((Join-Path $gen 'ForgePanelBindings.h'), $lines, [Text.UTF8Encoding]::new($false))
$font = [IO.File]::ReadAllBytes((Join-Path $repo 'windows\RtxForge.Windows\Assets\Fonts\InterVariable.ttf'))
$semiBold = [IO.File]::ReadAllBytes((Join-Path $bridge 'Inter-SemiBold.ttf'))
$fontCode = 'inline unsigned char forgeInter[] = {' + (($font | ForEach-Object { $_.ToString() }) -join ',') + '};' + "`n" +
            'inline unsigned char forgeInterSemiBold[] = {' + (($semiBold | ForEach-Object { $_.ToString() }) -join ',') + '};'
$brandFont = [IO.File]::ReadAllBytes((Join-Path $repo 'gui\fonts\BakbakOne-Regular.ttf'))
$fontCode += "`n" + 'inline unsigned char forgeBakbak[] = {' + (($brandFont | ForEach-Object { $_.ToString() }) -join ',') + '};'
[IO.File]::WriteAllText((Join-Path $gen 'ForgePanelFont.h'), $fontCode, [Text.UTF8Encoding]::new($false))

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vcvars = if (Test-Path $vswhere) {
    & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find 'VC\Auxiliary\Build\vcvars64.bat' | Select-Object -First 1
}
if (-not $vcvars) { throw 'Visual Studio C++ build tools are required to build the Feeder panel.' }
$here = Join-Path $repo 'windows\feeder-panel'
$imgui = Join-Path $SourceRoot 'OptiScaler\include\imgui'
$freetype = Join-Path $SourceRoot 'external\freetype'
$obj = Join-Path $Output 'obj'
New-Item -ItemType Directory -Force (Join-Path $obj 'panel'), (Join-Path $obj 'quiet') | Out-Null
$common = '/nologo /O2 /std:c++latest /utf-8 /EHsc /MT /LD /W3 /DNOMINMAX /DUNICODE /D_UNICODE /DIMGUI_ENABLE_STB_TRUETYPE'
function Invoke-Cl([string] $arguments, [string] $addon) {
    if (Test-Path $addon) { Remove-Item $addon }
    cmd /c "`"$vcvars`" >nul 2>nul && cl $common $arguments"
    if ($LASTEXITCODE -or -not (Test-Path $addon)) { throw "Build failed: $addon" }
}
$panel = Join-Path $Output 'rtxforge-panel.addon64'
$panelSources = @("$here\rtxforge-panel.cpp", "$here\panel.cpp") + (@('imgui.cpp', 'imgui_draw.cpp', 'imgui_tables.cpp', 'imgui_widgets.cpp', 'imgui_impl_dx11.cpp', 'misc\freetype\imgui_freetype.cpp') | ForEach-Object { Join-Path $imgui $_ })
$includes = @("$here\shim", $gen, $bridge, "$sdk\reshade", (Join-Path $SourceRoot 'OptiScaler\include'), $imgui, $freetype, (Join-Path $SourceRoot 'external\nlohmann'))
Invoke-Cl ((($includes | ForEach-Object { "/I`"$_`"" }) -join ' ') + ' /Fo"' + "$obj\panel\\" + '" ' + (($panelSources | ForEach-Object { "`"$_`"" }) -join ' ') +
           " /Fe`"$panel`" /link /LIBPATH:`"$freetype`" freetype.lib d3d11.lib d3dcompiler.lib user32.lib advapi32.lib") $panel
$quiet = Join-Path $Output 'rtxforge-quiet.addon64'
Invoke-Cl ("/I`"$sdk\reshade-imgui`" /I`"$sdk\reshade`" /Fo`"$obj\quiet\\`" `"$here\rtxforge-quiet.cpp`" /Fe`"$quiet`" /link user32.lib advapi32.lib") $quiet

$receipt = [ordered]@{
    schema = 2; files = [ordered]@{}; reshade = $ReShade; reshade_imgui = $ReShadeImGui; optiscaler = $head
    panel_source = (Get-Sha256 (Join-Path $bridge 'ForgePanel.h'))
}
foreach ($addon in $panel, $quiet) {
    $receipt.files[(Split-Path $addon -Leaf)] = [ordered]@{ sha256 = (Get-Sha256 $addon); size = (Get-Item $addon).Length }
}
foreach ($license in @('windows\RtxForge.Windows\Assets\Fonts\OFL-Inter.txt','gui\fonts\OFL-BakbakOne.txt')) {
    $target=Join-Path $Output (Split-Path $license -Leaf)
    Copy-Item -LiteralPath (Join-Path $repo $license) -Destination $target
}
[IO.File]::WriteAllText((Join-Path $Output 'package.json'), ($receipt | ConvertTo-Json -Depth 4) + "`n", (New-Object Text.UTF8Encoding $false))
foreach ($name in $receipt.files.Keys) { Write-Host "$name $($receipt.files[$name].size) bytes $($receipt.files[$name].sha256)" }
