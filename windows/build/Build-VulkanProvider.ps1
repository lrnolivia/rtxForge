<# Bundles the reviewed native Vulkan runtime, approved NR model, loaders and notices. #>
param([string]$Output)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Output) { $Output = Join-Path $repo 'windows\out\vulkan-provider' }
python -X utf8 (Join-Path $repo 'providers\vulkan-dlssg\distribution.py') --output $Output
if ($LASTEXITCODE) { throw 'Vulkan provider bundle verification failed.' }
