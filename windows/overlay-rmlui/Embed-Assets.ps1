param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
$repo=Split-Path (Split-Path $PSScriptRoot)
$ui=Join-Path $repo 'prototypes/overlay-rmlui'
New-Item -ItemType Directory -Force -Path $Output | Out-Null
$items=[ordered]@{
  'overlay.rml'=(Join-Path $ui 'overlay.rml')
  'overlay.rcss'=(Join-Path $ui 'overlay.rcss')
  'logo-mark.png'=(Join-Path $ui 'logo-mark.png')
  'fonts/RobotoVariable.ttf'=(Join-Path $repo 'gui/fonts/RobotoVariable.ttf')
  'fonts/BakbakOne-Regular.ttf'=(Join-Path $repo 'gui/fonts/BakbakOne-Regular.ttf')
  'fonts/InterVariable.ttf'=(Join-Path $repo 'windows/RtxForge.Windows/Assets/Fonts/InterVariable.ttf')
}
Get-ChildItem -LiteralPath (Join-Path $ui 'icons') -Filter '*-light.png' | Sort-Object Name | ForEach-Object {$items['icons/'+$_.Name]=$_.FullName}
$resource=[Collections.Generic.List[string]]::new()
$header=[Collections.Generic.List[string]]::new()
$header.Add('#pragma once')
$header.Add('struct EmbeddedAsset {const char* name;int id;};')
$header.Add('inline constexpr EmbeddedAsset EmbeddedAssets[]={')
$index=100
foreach($entry in $items.GetEnumerator()) {
  $file=[IO.Path]::GetFullPath($entry.Value).Replace('\','/')
  if(-not (Test-Path -LiteralPath $file -PathType Leaf)){throw "Missing glass overlay asset: $file"}
  $resource.Add("$index RCDATA `"$file`"")
  $header.Add("{`"$($entry.Key)`",$index},")
  $index++
}
$header.Add('};')
[IO.File]::WriteAllLines((Join-Path $Output 'GlassAssets.rc'),$resource,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllLines((Join-Path $Output 'GlassAssets.generated.h'),$header,[Text.UTF8Encoding]::new($false))
