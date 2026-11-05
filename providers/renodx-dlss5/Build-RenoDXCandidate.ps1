<#
.SYNOPSIS
    Builds the RenoDX DLSS5 add-on from its MIT source with rtxForge's live
    settings interface (rtxforge_live.hpp), as a candidate. Run on hosted CI
    after RenoDX's own shader tools and an MSVC x64 environment are set up.
.PARAMETER RenoDX
    A RenoDX checkout at source.json's commit, with submodules.
.PARAMETER AddonSource
    A RenoDX-DLSS5-Generic checkout at source.json's commit.
#>
param(
    [Parameter(Mandatory)][string]$RenoDX,
    [Parameter(Mandatory)][string]$AddonSource,
    [string]$Output
)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$spec = Get-Content -Raw -LiteralPath (Join-Path $here 'source.json') | ConvertFrom-Json
if (-not $Output) { $Output = Join-Path $here '..\..\windows\out\renodx-dlss5-candidate' }

function Head([string]$path) { (git -C $path rev-parse HEAD).Trim() }
if ((Head $RenoDX) -ne $spec.renodx.commit) { throw "RenoDX checkout is not at $($spec.renodx.commit)" }
if ((Head $AddonSource) -ne $spec.addon_source.commit) { throw "Add-on source is not at $($spec.addon_source.commit)" }

$reshade = Join-Path $RenoDX 'external\reshade'
if ((Head $reshade) -ne $spec.reshade.commit) { throw "RenoDX's ReShade submodule is not at $($spec.reshade.commit)" }

# The add-on lives at src/addons/dlss5; RenoDX builds every src/*/*/addon.cpp.
$target = Join-Path $RenoDX 'src\addons\dlss5'
if (Test-Path $target) { throw "$target already exists" }
New-Item -ItemType Directory -Force $target | Out-Null
Get-ChildItem -LiteralPath $AddonSource -Force | Where-Object Name -ne '.git' | Copy-Item -Destination $target -Recurse
$version = Select-String -LiteralPath (Join-Path $target 'dlssnr.hpp') -Pattern 'kAddonVersion\[\] = "([^"]+)"' | Select-Object -First 1
if (-not $version -or $version.Matches[0].Groups[1].Value -ne $spec.addon_version) { throw 'Add-on source version differs from source.json' }

Copy-Item -LiteralPath (Join-Path $here $spec.patch) -Destination $target
Copy-Item -LiteralPath (Join-Path $here $spec.compat) -Destination $target
$addon = Join-Path $target 'addon.cpp'
$text = [IO.File]::ReadAllText($addon)
if ($text -notmatch '#include "dlssnr.hpp"') { throw 'addon.cpp no longer includes dlssnr.hpp' }
$text = $text.Replace('#include "dlssnr.hpp"', "#include `"$($spec.compat)`"`n#include `"dlssnr.hpp`"")
[IO.File]::WriteAllText($addon, $text.TrimEnd() + "`n`n#include `"$($spec.patch)`"`n", [Text.UTF8Encoding]::new($false))

# rtxForge's glass overlay can draw the corner HUD itself (RenoDXNrHudV1Get);
# while it does, OnHudOverlay returns before drawing. Exactly one anchor.
$dlssnr = Join-Path $target 'dlssnr.hpp'
$source = [IO.File]::ReadAllText($dlssnr)
$anchor = '(?m)^(\s*)if \(hud_overlay_open\.load\(std::memory_order_relaxed\)\) return;(\r?\n)(\s*)RefreshUiLanguage\(\);'
$found = [regex]::Matches($source, $anchor)
if ($found.Count -ne 1) { throw "OnHudOverlay anchor found $($found.Count) times, expected 1" }
$source = [regex]::Replace($source, $anchor, '$1if (hud_overlay_open.load(std::memory_order_relaxed)) return;$2$1if (rtxforge_hud_hosted.load(std::memory_order_relaxed)) return;$2$3RefreshUiLanguage();')
[IO.File]::WriteAllText($dlssnr, $source, [Text.UTF8Encoding]::new($false))

Push-Location $RenoDX
try {
    cmake --preset ninja-x64
    if ($LASTEXITCODE) { throw 'RenoDX configure failed' }
    cmake --build --preset ninja-x64-release --target dlss5
    if ($LASTEXITCODE) { throw 'dlss5 build failed' }
} finally { Pop-Location }

$built = Get-ChildItem -LiteralPath (Join-Path $RenoDX 'build') -Recurse -Filter 'renodx-dlss5.addon64' | Select-Object -First 1
if (-not $built) { throw 'renodx-dlss5.addon64 was not produced' }
New-Item -ItemType Directory -Force $Output | Out-Null
Copy-Item -LiteralPath $built.FullName -Destination $Output -Force
$binary = Join-Path $Output 'renodx-dlss5.addon64'

# The interface must be exported, or the candidate is pointless.
$dumpbin = Get-Command dumpbin.exe -ErrorAction Stop
$exports = & $dumpbin.Source /exports $binary | Out-String
foreach ($name in 'RenoDXNrApiVersion', 'RenoDXNrGetV1', 'RenoDXNrSetV1', 'RenoDXNrAppliedGenerationV1', 'RenoDXNrHudV1Get', 'RenoDXNrHudV1Host') {
    if ($exports -notmatch "\b$name\b") { throw "Export $name is missing" }
}

$receipt = [ordered]@{
    schema = 1; id = $spec.id; addon_version = $spec.addon_version; api_version = $spec.api_version
    addon_source = $spec.addon_source.commit; renodx = $spec.renodx.commit; reshade = $spec.reshade.commit
    patch_sha256 = (Get-FileHash -LiteralPath (Join-Path $here $spec.patch) -Algorithm SHA256).Hash.ToLowerInvariant()
    compat_sha256 = (Get-FileHash -LiteralPath (Join-Path $here $spec.compat) -Algorithm SHA256).Hash.ToLowerInvariant()
    rtxforge_commit = (git -C (Join-Path $here '..\..') rev-parse HEAD).Trim()
    files = [ordered]@{ 'renodx-dlss5.addon64' = [ordered]@{
        sha256 = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
        size = (Get-Item -LiteralPath $binary).Length } }
    candidate_only = $true; runtime_verified = $false
}
$receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Output 'package.json') -Encoding utf8
Copy-Item -LiteralPath (Join-Path $AddonSource 'LICENSE') -Destination (Join-Path $Output 'LICENSE-RenoDX-DLSS5.txt')
Copy-Item -LiteralPath (Join-Path $RenoDX 'LICENSE') -Destination (Join-Path $Output 'LICENSE-RenoDX.txt')
Get-Content -LiteralPath (Join-Path $Output 'package.json')
