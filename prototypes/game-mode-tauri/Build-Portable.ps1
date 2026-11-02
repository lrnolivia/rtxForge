[CmdletBinding()]
param([switch]$SkipBuild,
      [string]$OutputPath,
      [Parameter(Mandatory)][string]$ScreeningPath)
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath($PSScriptRoot)
$repo = [IO.Path]::GetFullPath((Join-Path $project '../..'))
if (-not $OutputPath) {
    $scratch = if (Test-Path -LiteralPath 'G:/BuildScratch') { 'G:/BuildScratch' } else { [IO.Path]::GetTempPath() }
    $OutputPath = Join-Path $scratch ('rtxforge-game-mode-package-' + [Guid]::NewGuid().ToString('N'))
}
$output = [IO.Path]::GetFullPath($OutputPath)
if ($output -eq $repo -or $output -eq $project -or $project.StartsWith($output + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Choose a distinct package directory.' }
foreach ($name in @('python','engine')) {
    $target = [IO.Path]::GetFullPath((Join-Path $output $name))
    if (-not $target.StartsWith($output + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Bundle target escapes its package.' }
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
Copy-Item -LiteralPath (Join-Path $project 'Install.ps1') -Destination $output -Force
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
python (Join-Path $project 'package_bundle.py') --output $output --screening $ScreeningPath
if ($LASTEXITCODE -ne 0) { throw 'Portable payload validation failed.' }
Write-Output $output
