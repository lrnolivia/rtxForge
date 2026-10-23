param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$output = [IO.Path]::GetFullPath($OutputDirectory)
& (Join-Path $PSScriptRoot 'Build-Loader.ps1') -OutputDirectory $output
New-Item -ItemType Directory -Force -Path (Join-Path $output 'NativeMods') | Out-Null
$fakeExports = @('EXPORTS')
foreach ($line in (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'exports.def'))) {
    if ($line -match '^([A-Za-z0-9_]+)\s+@(\d+)$') {
        $fakeExports += $matches[1] + '=Stub @' + $matches[2]
    }
}
[IO.File]::WriteAllText((Join-Path $output 'fake.def'), ($fakeExports -join "`n"), [Text.Encoding]::ASCII)
$command = @'
@echo off
call "%RTXFORGE_BG3_VSDEV%" -arch=x64 -no_logo
if errorlevel 1 exit /b %errorlevel%
cd /d "%RTXFORGE_BG3_OUT%"
cl /nologo /MT /LD /DFAKE_BINK "%RTXFORGE_BG3_SOURCE%\fixture.cpp" /link /DEF:fake.def /OUT:bink2w64_rtxforge_original.dll
if errorlevel 1 exit /b %errorlevel%
cl /nologo /MT /LD /DFAKE_FGVK "%RTXFORGE_BG3_SOURCE%\fixture.cpp" /link /OUT:NativeMods\fgvk.dll
if errorlevel 1 exit /b %errorlevel%
cl /nologo /MT "%RTXFORGE_BG3_SOURCE%\fixture.cpp" loader.lib /link /OUT:bg3.exe
if errorlevel 1 exit /b %errorlevel%
bg3.exe
exit /b %errorlevel%
'@
[IO.File]::WriteAllText((Join-Path $output 'test-loader.cmd'), $command, [Text.Encoding]::ASCII)
& $env:ComSpec /d /c (Join-Path $output 'test-loader.cmd')
if ($LASTEXITCODE -ne 0) { throw 'Early startup / Bink forwarding fixture failed.' }
Copy-Item -LiteralPath (Join-Path $output 'bg3.exe') -Destination (Join-Path $output 'bg3_dx11.exe')
& (Join-Path $output 'bg3_dx11.exe') --expect-no-fg
if ($LASTEXITCODE -ne 0) { throw 'DX11 must forward Bink without loading FG.' }
Move-Item -LiteralPath (Join-Path $output 'NativeMods\fgvk.dll') -Destination (Join-Path $output 'NativeMods\fgvk.fixture-off')
& (Join-Path $output 'bg3.exe') --expect-no-fg
if ($LASTEXITCODE -ne 0) { throw 'Missing plugin must preserve game startup.' }
'PASS: early module load, Bink forwarding, DX11 isolation and missing-plugin startup'
