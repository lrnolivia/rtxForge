param([string]$Executable=(Join-Path $PSScriptRoot '../../windows/out/overlay-rmlui/Release/OverlayPrototype.exe'))
$ErrorActionPreference='Stop'
if(-not (Test-Path -LiteralPath $Executable -PathType Leaf)){throw 'Build the preview first, or supply -Executable with its local path.'}
$repo=Split-Path (Split-Path $PSScriptRoot)
$font=Join-Path $repo 'gui/fonts/RobotoVariable.ttf'
$arguments=@('--assets',"`"$PSScriptRoot`"",'--background',"`"$(Join-Path $repo 'website/public/assets/screenshots/windows-control-overlay.webp')`"",'--font',"`"$font`"",'--crop-left','.25','--accent','#d58975','--welcome')
Start-Process -FilePath $Executable -ArgumentList $arguments -WorkingDirectory $repo
