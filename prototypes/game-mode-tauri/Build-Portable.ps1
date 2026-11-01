[CmdletBinding()]
param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath($PSScriptRoot)
$repo = [IO.Path]::GetFullPath((Join-Path $project '../..'))
$output = [IO.Path]::GetFullPath((Join-Path $project 'out/rtxForge-Game-Mode-Preview-win-x64'))
# The shared bundler refreshes python/ and engine/. Validate its recursive targets.
foreach ($name in @('python', 'engine')) {
    $target = [IO.Path]::GetFullPath((Join-Path $output $name))
    if (-not $target.StartsWith($project + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Bundle target escapes the project: $target"
    }
}
if (-not $SkipBuild) {
    & (Join-Path $project 'Run.ps1') -Build
    if ($LASTEXITCODE -ne 0) { throw 'Native build failed.' }
}
New-Item -ItemType Directory -Force -Path $output | Out-Null
& (Join-Path $repo 'windows/build/Bundle-Engine.ps1') -Output $output -RuntimeIdentifier win-x64 -Cache (Join-Path $project '.tools/python-embed')
Copy-Item -LiteralPath (Join-Path $project 'src-tauri/target/release/rtxforge-game-mode.exe') -Destination $output -Force
$bridge = Join-Path $output 'bridge'
New-Item -ItemType Directory -Force -Path $bridge | Out-Null
Get-ChildItem -LiteralPath (Join-Path $project 'bridge') -Filter '*.py' -File | Copy-Item -Destination $bridge -Force
Copy-Item -LiteralPath (Join-Path $repo 'LICENSE'),(Join-Path $project 'README.md'),(Join-Path $project 'FEATURE_PARITY.md'),(Join-Path $project 'VALIDATION.md'),(Join-Path $project 'ASSETS.md') -Destination $output -Force
Copy-Item -LiteralPath (Join-Path $project 'Install-Preview.ps1') -Destination $output -Force
$notices = Join-Path $output 'notices'
New-Item -ItemType Directory -Force -Path $notices | Out-Null
Get-ChildItem -LiteralPath (Join-Path $project 'public/fonts') -Filter '*.txt' -File | Copy-Item -Destination $notices -Force
Copy-Item -LiteralPath (Join-Path $project 'node_modules/@tauri-apps/api/LICENSE-MIT'),(Join-Path $project 'node_modules/@tauri-apps/api/LICENSE-APACHE-2.0') -Destination $notices -Force
Get-ChildItem -LiteralPath (Join-Path $repo 'providers') -Recurse -File | Where-Object { $_.Name -match 'LICENSE|NOTICE|COPYING' } | ForEach-Object {
    $relative = $_.FullName.Substring($repo.Length + 1)
    $destination = Join-Path $notices $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
}
# Retain the license texts for the crates compiled into the Windows executable.
$registry = Join-Path $project '.tools/cargo/registry/src'
if (-not (Test-Path -LiteralPath $registry)) { $registry = Join-Path $env:USERPROFILE '.cargo/registry/src' }
$locks = Get-Content -LiteralPath (Join-Path $project 'src-tauri/Cargo.lock') -Raw
foreach ($entry in [regex]::Matches($locks, '(?ms)^name = "([^"]+)"\r?\nversion = "([^"]+)"')) {
    $crate = $entry.Groups[1].Value + '-' + $entry.Groups[2].Value
    Get-ChildItem -Path (Join-Path $registry "*/$crate/*") -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^(LICENSE|COPYING|NOTICE)' } | ForEach-Object {
        $destination = Join-Path $notices "rust/$crate"
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
    }
}
$revision = (& git -C $repo rev-parse HEAD).Trim()
@{ version='0.1.0-preview.1'; source=$revision; platform='win-x64'; readOnlyDefault=$true; python='3.14.5' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'build.json') -Encoding utf8
Write-Output $output
