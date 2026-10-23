param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$output = [IO.Path]::GetFullPath($OutputDirectory)
if ($output -eq $PSScriptRoot -or $output.StartsWith($PSScriptRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose an output directory outside the provider source.'
}
New-Item -ItemType Directory -Force -Path $output | Out-Null
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$visualStudio = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $visualStudio) { throw 'MSVC x64 build tools are required.' }
$dev = Join-Path $visualStudio 'Common7\Tools\VsDevCmd.bat'
# Build paths are passed as environment values rather than interpolated shell commands.
$env:RTXFORGE_BG3_SOURCE = $PSScriptRoot
$env:RTXFORGE_BG3_OUT = $output
$env:RTXFORGE_BG3_VSDEV = $dev
$command = @'
@echo off
call "%RTXFORGE_BG3_VSDEV%" -arch=x64 -no_logo
if errorlevel 1 exit /b %errorlevel%
cd /d "%RTXFORGE_BG3_OUT%"
ml64 /nologo /c /Foexports.obj "%RTXFORGE_BG3_SOURCE%\jmp.asm"
if errorlevel 1 exit /b %errorlevel%
cl /nologo /std:c++17 /W4 /WX /O2 /MT /Brepro /LD "%RTXFORGE_BG3_SOURCE%\loader.cpp" exports.obj /link /DEF:"%RTXFORGE_BG3_SOURCE%\exports.def" /OUT:bink2w64.dll /Brepro
exit /b %errorlevel%
'@
$cmdFile = Join-Path $output 'build-loader.cmd'
[IO.File]::WriteAllText($cmdFile, $command, [Text.Encoding]::ASCII)
& $env:ComSpec /d /c $cmdFile
if ($LASTEXITCODE -ne 0) { throw 'Loader build failed.' }
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $output 'bink2w64.dll')
