param([Parameter(Mandatory)][string]$RmlSource, [Parameter(Mandatory)][string]$FreetypeRoot, [Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
$pin='ae4e0dcb52b324a0d0fc36ed51f633c8c3fe06b7'
$head=(& git -C $RmlSource rev-parse HEAD).Trim()
if($LASTEXITCODE -or $head -ne $pin) { throw "Use the pinned RmlUi revision $pin." }
cmake -S $PSScriptRoot -B $Output -A x64 "-DRMLUI_SOURCE=$RmlSource" "-DFREETYPE_ROOT=$FreetypeRoot"
if($LASTEXITCODE) { throw 'RmlUi prototype configuration failed.' }
cmake --build $Output --config Release --parallel 6
if($LASTEXITCODE) { throw 'RmlUi prototype build failed.' }
Copy-Item -LiteralPath (Join-Path $RmlSource 'LICENSE.txt') -Destination $Output
