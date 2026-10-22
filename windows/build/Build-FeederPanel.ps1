<#
.SYNOPSIS
    Builds rtxForge's in-game panel for Feeder NR games (a ReShade add-on).

.DESCRIPTION
    Compiles windows/feeder-panel/rtxforge-panel.cpp against the ReShade 6.8.0
    add-on headers and the Dear ImGui revision ReShade 6.8.0 ships. Headers are
    downloaded by commit and checked by SHA-256. MSVC is used when Visual Studio
    is installed (CI); MinGW-w64 g++ otherwise.

    Output: <Output>\rtxforge-panel.addon64 and <Output>\package.json, which
    Bundle-Engine.ps1 copies into the app and feeder_provider.py verifies.
#>
[CmdletBinding()]
param(
    [string] $Output,
    [ValidateSet('auto', 'msvc', 'mingw')] [string] $Compiler = 'auto'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Output) { $Output = Join-Path $repo 'windows\out\feeder-panel' }
$Output = [IO.Path]::GetFullPath($Output)

$ReShade = '18deaa52de0c425a78b329e9cb3c497281cd00ec'  # crosire/reshade v6.8.0
$ImGui = '3912b3d9a9c1b3f17431aebafd86d2f40ee6e59c'    # ocornut/imgui, ReShade 6.8.0's deps/imgui
$Headers = [ordered]@{
    'reshade.hpp'              = @("crosire/reshade/$ReShade/include/reshade.hpp", 'cf3cd150920ea310b4b1e2e4f11ab8d7221a9fc18755f4891a026563311b524c')
    'reshade_api.hpp'          = @("crosire/reshade/$ReShade/include/reshade_api.hpp", '8d83ec8a620c48da7a20d975bd27b3345b24d3f0d5b78ae4c4fe633d61b804eb')
    'reshade_api_device.hpp'   = @("crosire/reshade/$ReShade/include/reshade_api_device.hpp", 'a716c44b6fbb064dbbb0826687728f21aa71ed45e13564e4dc1cdf36da5bdfa0')
    'reshade_api_format.hpp'   = @("crosire/reshade/$ReShade/include/reshade_api_format.hpp", '68caa17fef712043e810ab88770c15af009aa3c7693e5c115ddc324f2d0809a7')
    'reshade_api_pipeline.hpp' = @("crosire/reshade/$ReShade/include/reshade_api_pipeline.hpp", '5bda8e07260c2c60f0fd18a78b11782aed8f69e5d24b5757874614caafdf416f')
    'reshade_api_resource.hpp' = @("crosire/reshade/$ReShade/include/reshade_api_resource.hpp", '32cdafe6d783813f3ac72ad43e426638d8d0fef56bcb558fad218a14cfb75ee3')
    'reshade_events.hpp'       = @("crosire/reshade/$ReShade/include/reshade_events.hpp", '2717f56e2bd89af6d708c9c316353d6581c5a41d4526629fadba51d13be57a89')
    'reshade_overlay.hpp'      = @("crosire/reshade/$ReShade/include/reshade_overlay.hpp", 'ed914b12fbc41ed038287b0163c0bc934772afcff2c22392044c6008adc5ae79')
    'imgui.h'                  = @("ocornut/imgui/$ImGui/imgui.h", '07562842049eaca4e47c3fcdcc9d8eafd442695b9856d6f6639e92e1bb6c737e')
    'imconfig.h'               = @("ocornut/imgui/$ImGui/imconfig.h", '6e5687893594ebfaf8569280cfea83d025904a8a4e23bec073086f6c5bc8f7fb')
}

function Get-Sha256([string] $Path) {
    $stream = [IO.File]::OpenRead($Path)
    try { ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($stream)) -replace '-', '').ToLowerInvariant() }
    finally { $stream.Dispose() }
}

$sdk = Join-Path $Output 'sdk'
New-Item -ItemType Directory -Force $sdk | Out-Null
foreach ($name in $Headers.Keys) {
    $target = Join-Path $sdk $name
    $source, $expected = $Headers[$name]
    if (-not (Test-Path $target) -or (Get-Sha256 $target) -ne $expected) {
        Invoke-WebRequest "https://raw.githubusercontent.com/$source" -OutFile "$target.part" -UseBasicParsing
        $hash = Get-Sha256 "$target.part"
        if ($hash -ne $expected) { Remove-Item "$target.part"; throw "$name hash mismatch: $hash" }
        Move-Item "$target.part" $target -Force
    }
}

$source = Join-Path $repo 'windows\feeder-panel\rtxforge-panel.cpp'
$addon = Join-Path $Output 'rtxforge-panel.addon64'
if (Test-Path $addon) { Remove-Item $addon }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vcvars = if ($Compiler -ne 'mingw' -and (Test-Path $vswhere)) {
    & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find 'VC\Auxiliary\Build\vcvars64.bat' | Select-Object -First 1
}
if ($vcvars) {
    $obj = Join-Path $Output 'obj'
    New-Item -ItemType Directory -Force $obj | Out-Null
    cmd /c "`"$vcvars`" >nul && cl /nologo /O2 /std:c++20 /EHsc /MT /LD /W3 /I`"$sdk`" /Fo`"$obj\\`" `"$source`" /Fe`"$addon`" /link user32.lib advapi32.lib"
    $built = 'msvc'
} elseif ($Compiler -ne 'msvc' -and (Get-Command g++ -ErrorAction SilentlyContinue)) {
    # Warnings stay on stderr; PowerShell 5.1 would turn them into errors.
    cmd /c "g++ -shared -O2 -std=c++20 -w -I`"$sdk`" `"$source`" -o `"$addon`" -static -s -luser32 -ladvapi32 2>&1"
    $built = 'mingw'
} else { throw 'Install Visual Studio C++ build tools or MinGW-w64 g++ to build the Feeder panel.' }
if ($LASTEXITCODE -or -not (Test-Path $addon)) { throw "Feeder panel build failed ($built)" }

$receipt = [ordered]@{
    schema = 1; name = 'rtxforge-panel.addon64'; sha256 = (Get-Sha256 $addon); size = (Get-Item $addon).Length
    compiler = $built; reshade = $ReShade; imgui = $ImGui
}
[IO.File]::WriteAllText((Join-Path $Output 'package.json'), ($receipt | ConvertTo-Json) + "`n", (New-Object Text.UTF8Encoding $false))
Write-Host "Feeder panel ($built, $($receipt.size) bytes, $($receipt.sha256)) -> $addon"
