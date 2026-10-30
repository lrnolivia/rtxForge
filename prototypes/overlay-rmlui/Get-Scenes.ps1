param([string]$Cache = (Join-Path $env:LOCALAPPDATA 'rtxForge/prototypes/scenes'))
$ErrorActionPreference = 'Stop'
$scenes = Get-Content (Join-Path $PSScriptRoot 'scenes.json') -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Path $Cache -Force | Out-Null
foreach($scene in $scenes) {
    if($scene.file -notmatch '^\d+\.jpg$' -or $scene.source -notlike 'https://shared.akamai.steamstatic.com/*') { throw 'Invalid screenshot source.' }
    $target = Join-Path $Cache $scene.file
    if((Test-Path -LiteralPath $target) -and (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -eq $scene.sha256) { continue }
    $temporary = $target + '.download'
    Invoke-WebRequest -Uri $scene.source -OutFile $temporary
    if((Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash -ne $scene.sha256) { throw "Screenshot content changed: $($scene.title)." }
    Move-Item -LiteralPath $temporary -Destination $target -Force
}
Write-Output "Preview screenshots ready in $Cache"
