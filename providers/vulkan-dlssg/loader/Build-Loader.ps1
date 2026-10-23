param(
    [ValidateSet('bg3','rdr2','universal')][string]$Profile = 'universal',
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [switch]$Test
)
$ErrorActionPreference = 'Stop'
$output = [IO.Path]::GetFullPath($OutputDirectory)
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
if ($output -eq $sourceRoot -or $output.StartsWith($sourceRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)) {
    throw 'Choose a new output directory outside the product checkout.'
}
New-Item -ItemType Directory -Path $output | Out-Null
$stage = Join-Path $output 'source'
New-Item -ItemType Directory -Path $stage | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'loader.cpp'),(Join-Path $PSScriptRoot 'fixture.cpp'),(Join-Path $PSScriptRoot 'LICENSE.exports.txt') -Destination $stage
$specs = @('bg3','rdr2') | ForEach-Object { Get-Content -LiteralPath (Join-Path $PSScriptRoot ($_ + '.json')) -Raw | ConvertFrom-Json }
$spec = if ($Profile -eq 'universal') {
    # Stable named-export union. BG3 ordinal values are retained only where
    # compatible; the loader rejects incompatible executable ordinal imports.
    $entries = @($specs[0].exports); $next = 1 + ($entries.ordinal | Measure-Object -Maximum).Maximum
    foreach ($entry in $specs[1].exports) {
        if ($entries.name -notcontains $entry.name) { $entries += [pscustomobject]@{name=$entry.name;ordinal=$next}; $next++ }
    }
    [pscustomobject]@{schema=1;profile='universal';exports=$entries}
} else { $specs | Where-Object profile -eq $Profile }
if ($spec.profile -ne $Profile -or $spec.schema -ne 1) { throw 'Loader profile identity differs.' }
$names = @(); $ordinals = @(); $header = @('#pragma once','static const char* const exportNames[] = {')
$definitions = @('LIBRARY bink2w64','EXPORTS'); $assembly = @('.code','extern ImportFuncTbl:QWORD'); $fake = @('EXPORTS')
$index = 0
foreach ($entry in $spec.exports) {
    if ($entry.name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$' -or $entry.ordinal -lt 1 -or $entry.ordinal -gt 65535 -or $names -contains $entry.name -or $ordinals -contains $entry.ordinal) { throw 'Invalid export table.' }
    $names += $entry.name; $ordinals += $entry.ordinal
    $header += '    "' + $entry.name + '",'
    $definitions += $entry.name + ' @' + $entry.ordinal
    $assembly += $entry.name + ' PROC'; $assembly += '    jmp ImportFuncTbl[' + $index + ' * 8]'; $assembly += $entry.name + ' ENDP'
    $stub = if ($entry.name -eq 'BinkClose') {'CloseStub'} elseif ($entry.name -eq 'BinkGetError') {'ErrorStub'} else {'Stub'}
    $fake += $entry.name + '=' + $stub + ' @' + $entry.ordinal
    $index++
}
$header += '};'; $header += 'static const unsigned short exportOrdinals[] = {' + ($ordinals -join ',') + '};'; $assembly += 'END'
foreach ($item in @(@('exports.h',$header),@('exports.def',$definitions),@('jmp.asm',$assembly),@('fake.def',$fake))) {
    [IO.File]::WriteAllText((Join-Path $stage $item[0]), ($item[1] -join "`n"), [Text.Encoding]::ASCII)
}
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$visualStudio = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $visualStudio) { throw 'MSVC x64 build tools are required.' }
$env:RTXFORGE_VK_VSDEV = Join-Path $visualStudio 'Common7\Tools\VsDevCmd.bat'
$env:RTXFORGE_VK_OUT = $output
$command = @'
@echo off
call "%RTXFORGE_VK_VSDEV%" -arch=x64 -no_logo
if errorlevel 1 exit /b %errorlevel%
cd /d "%RTXFORGE_VK_OUT%"
ml64 /nologo /c /Foexports.obj source\jmp.asm
if errorlevel 1 exit /b %errorlevel%
cl /nologo /std:c++17 /W4 /WX /O2 /MT /Brepro /LD source\loader.cpp exports.obj /link /DEF:source\exports.def /OUT:bink2w64.dll /IMPLIB:bink2w64.lib /Brepro
exit /b %errorlevel%
'@
[IO.File]::WriteAllText((Join-Path $output 'build.cmd'), $command, [Text.Encoding]::ASCII)
& $env:ComSpec /d /c (Join-Path $output 'build.cmd')
if ($LASTEXITCODE -ne 0) { throw 'Loader build failed.' }
if ($Test) {
    New-Item -ItemType Directory -Path (Join-Path $output 'NativeMods') | Out-Null
    [IO.File]::WriteAllText((Join-Path $stage 'named-import.def'), "LIBRARY bink2w64`nEXPORTS`nBinkClose`nBinkGetError`n", [Text.Encoding]::ASCII)
    $command = @'
@echo off
call "%RTXFORGE_VK_VSDEV%" -arch=x64 -no_logo
if errorlevel 1 exit /b %errorlevel%
cd /d "%RTXFORGE_VK_OUT%"
cl /nologo /MT /LD /DFAKE_BINK source\fixture.cpp /link /DEF:source\fake.def /OUT:bink2w64_rtxforge_original.dll
if errorlevel 1 exit /b %errorlevel%
cl /nologo /MT /LD /DFAKE_FGVK source\fixture.cpp /link /OUT:NativeMods\fgvk.dll
if errorlevel 1 exit /b %errorlevel%
cl /nologo /MT /LD /DFAKE_VULKAN source\fixture.cpp /link /OUT:vulkan-1.dll
if errorlevel 1 exit /b %errorlevel%
lib /nologo /def:source\named-import.def /machine:x64 /out:named-import.lib
if errorlevel 1 exit /b %errorlevel%
cl /nologo /MT source\fixture.cpp named-import.lib /link /OUT:bg3.exe
if errorlevel 1 exit /b %errorlevel%
bg3.exe
exit /b %errorlevel%
'@
    [IO.File]::WriteAllText((Join-Path $output 'test.cmd'), $command, [Text.Encoding]::ASCII)
    & $env:ComSpec /d /c (Join-Path $output 'test.cmd')
    if ($LASTEXITCODE -ne 0) { throw 'BG3 startup/forwarding/small-stack fixture failed.' }
    Copy-Item -LiteralPath (Join-Path $output 'bg3.exe') -Destination (Join-Path $output 'RDR2.exe')
    & (Join-Path $output 'RDR2.exe')
    if ($LASTEXITCODE -ne 0) { throw 'RDR2 startup fixture failed.' }
    Copy-Item -LiteralPath (Join-Path $output 'bg3.exe') -Destination (Join-Path $output 'bg3_dx11.exe')
    & (Join-Path $output 'bg3_dx11.exe') --expect-no-fg
    if ($LASTEXITCODE -ne 0) { throw 'DX11 isolation fixture failed.' }
    $plugin = [IO.Path]::GetFullPath((Join-Path $output 'NativeMods\fgvk.dll'))
    $off = [IO.Path]::GetFullPath((Join-Path $output 'NativeMods\fgvk.fixture-off'))
    if (!$plugin.StartsWith($output + '\') -or !$off.StartsWith($output + '\')) { throw 'Fixture path escaped output.' }
    Move-Item -LiteralPath $plugin -Destination $off
    & (Join-Path $output 'RDR2.exe') --expect-no-fg
    if ($LASTEXITCODE -ne 0) { throw 'Missing-provider startup fixture failed.' }
    # Repeat forwarding with each actual game's export table and the SAME
    # built proxy. The RDR2 table has fewer APIs and different ordinals.
    foreach ($original in $specs) {
        $fake = @('EXPORTS')
        foreach ($entry in $original.exports) {
            $stub = if ($entry.name -eq 'BinkClose') {'CloseStub'} elseif ($entry.name -eq 'BinkGetError') {'ErrorStub'} else {'Stub'}
            $fake += $entry.name + '=' + $stub + ' @' + $entry.ordinal
        }
        [IO.File]::WriteAllText((Join-Path $stage 'fake.def'), ($fake -join "`n"), [Text.Encoding]::ASCII)
        & $env:ComSpec /d /c (Join-Path $output 'test.cmd')
        if ($LASTEXITCODE -ne 0) { throw ($original.profile + ' union-export forwarding fixture failed.') }
    }
}
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $output 'bink2w64.dll')
