$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$output = Join-Path $repo 'windows\out\overlay-startup-test'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $installation) { throw 'Visual Studio x64 C++ tools are required' }
$developer = Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
$source = Join-Path $PSScriptRoot 'UploadQueue.cpp'
$compile = '"' + $developer + '" -arch=x64 -host_arch=x64 && cl /nologo /std:c++20 /EHsc "' + $source + '" /Fe:"' + $output + '\UploadQueue.exe" /Fo:"' + $output + '\UploadQueue.obj" /link d3d12.lib dxgi.lib'
& cmd.exe /d /s /c $compile
if ($LASTEXITCODE -ne 0) { throw 'Native startup test did not compile' }
& (Join-Path $output 'UploadQueue.exe')
if ($LASTEXITCODE -ne 0) { throw 'Native queue independence check failed' }
