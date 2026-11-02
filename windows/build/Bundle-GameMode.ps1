[CmdletBinding()]
param([Parameter(Mandatory)][string]$SourcePath,
      [Parameter(Mandatory)][string]$Output,
      [string]$ExpectedSource)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $SourcePath).Path
$record = Get-Content -LiteralPath (Join-Path $source 'build.json') -Raw | ConvertFrom-Json
if ($record.schema -ne 2 -or $record.dirty -or $record.desktopIntegration -ne 1 -or $record.platform -ne 'win-x64') { throw 'Invalid integrated Game Mode package.' }
if ($ExpectedSource -and $record.source -ne $ExpectedSource) { throw 'Game Mode was built from a different source revision.' }
& (Join-Path $source 'python/python.exe') (Join-Path $source 'package_bundle.py') --verify $source
if ($LASTEXITCODE) { throw 'Game Mode source verification failed.' }
$destination = Join-Path $Output 'game-mode'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $destination -Recurse -Force
& (Join-Path $destination 'python/python.exe') (Join-Path $destination 'package_bundle.py') --verify $destination
if ($LASTEXITCODE) { throw 'Game Mode staged verification failed.' }
