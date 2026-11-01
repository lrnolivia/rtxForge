param([switch]$Native, [switch]$Build, [switch]$Engine)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if ($Engine) { $env:RTXFORGE_ENGINE_BRIDGE = '1'; Remove-Item Env:RTXFORGE_PREVIEW_READ_ONLY -ErrorAction SilentlyContinue }
    else { $env:RTXFORGE_PREVIEW_READ_ONLY = '1'; Remove-Item Env:RTXFORGE_ENGINE_BRIDGE -ErrorAction SilentlyContinue }
    if (-not $env:RTXFORGE_ROOT) { $env:RTXFORGE_ROOT = (Resolve-Path ../..).Path }
    $nodePath = if ($env:RTXFORGE_NODE) { $env:RTXFORGE_NODE } else { (Get-Command node -ErrorAction Stop).Source }
    $env:PATH = (Split-Path $nodePath) + [IO.Path]::PathSeparator + $env:PATH
    if (Test-Path .tools/cargo/bin/cargo.exe) {
        $env:RUSTUP_HOME = Join-Path $PSScriptRoot '.tools/rustup'
        $env:CARGO_HOME = Join-Path $PSScriptRoot '.tools/cargo'
        $env:PATH = (Join-Path $PSScriptRoot '.tools/cargo/bin') + [IO.Path]::PathSeparator + $env:PATH
    }
    if (-not (Test-Path node_modules/vite/bin/vite.js)) { throw 'Install project dependencies with npm ci before running this prototype.' }
    if ($Build) { & $nodePath node_modules/@tauri-apps/cli/tauri.js build --no-bundle }
    elseif ($Native) { & $nodePath node_modules/@tauri-apps/cli/tauri.js dev }
    else { & $nodePath node_modules/vite/bin/vite.js --host 127.0.0.1 --port 1420 --strictPort --configLoader native }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Pop-Location }
