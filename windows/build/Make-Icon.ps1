<#
.SYNOPSIS
    Builds the Windows app icon (.ico) and title-bar PNG from the shared brand icon.

.DESCRIPTION
    One source of truth with the Linux build: the scalable app icon in
    gui/icons/hicolor/scalable/apps (the current artwork, with the padded logo
    on its plate). Microsoft Edge renders the SVG headless at 512 px; every ICO
    frame (16-256 px) and the 64 px title-bar PNG are high-quality downscales
    of that render. Without Edge the 512 px hicolor PNG is used instead.
    Runs before build (RtxForge.Windows.csproj, MakeIcon target) when the
    outputs are missing.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Output,
    [string] $PngOutput
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$hicolor = Join-Path $PSScriptRoot '..\..\gui\icons\hicolor'
$svg = (Resolve-Path (Join-Path $hicolor 'scalable\apps\io.github.lrnolivia.RTXForge.svg')).Path
$work = Join-Path ([IO.Path]::GetTempPath()) ("rtxforge-icon-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $work | Out-Null

function Render-Svg([string] $Path, [int] $Size) {
    $edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") |
        Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $edge) { return $null }
    $html = Join-Path $work 'icon.html'
    $png = Join-Path $work "icon-$Size.png"
    $page = "<!doctype html><html><body style=`"margin:0;background:transparent;overflow:hidden`">" +
        "<img src=`"$([Uri]::new($Path).AbsoluteUri)`" width=`"$Size`" height=`"$Size`" style=`"display:block`"></body></html>"
    [IO.File]::WriteAllText($html, $page)
    $arguments = @('--headless=new', '--disable-gpu', '--hide-scrollbars', '--default-background-color=00000000',
        "--user-data-dir=`"$(Join-Path $work 'profile')`"", "--window-size=$Size,$Size", "--screenshot=`"$png`"", [Uri]::new($html).AbsoluteUri)
    $process = Start-Process $edge -ArgumentList $arguments -PassThru -WindowStyle Hidden
    if (-not $process.WaitForExit(60000)) { $process.Kill(); return $null }
    if (-not (Test-Path $png)) { return $null }
    return $png
}

function Scale([Drawing.Image] $Image, [int] $Size) {
    $bitmap = New-Object Drawing.Bitmap $Size, $Size
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    $graphics.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.PixelOffsetMode = [Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $graphics.CompositingQuality = [Drawing.Drawing2D.CompositingQuality]::HighQuality
    $graphics.DrawImage($Image, 0, 0, $Size, $Size)
    $graphics.Dispose()
    $stream = New-Object IO.MemoryStream
    $bitmap.Save($stream, [Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
    return , $stream.ToArray()
}

try {
    $rendered = Render-Svg $svg 512
    if ($rendered) { Write-Host "Icon artwork: $svg (rendered with Edge)" }
    else {
        $rendered = (Resolve-Path (Join-Path $hicolor '512x512\apps\io.github.lrnolivia.RTXForge.png')).Path
        Write-Warning "Microsoft Edge is unavailable; using $rendered for the icon."
    }
    $source = [Drawing.Image]::FromFile($rendered)
    $sizes = 16, 20, 24, 32, 40, 48, 64, 128, 256
    $frames = foreach ($size in $sizes) { , (Scale $source $size) }
    if ($PngOutput) {
        New-Item -ItemType Directory -Force (Split-Path $PngOutput) | Out-Null
        [IO.File]::WriteAllBytes($PngOutput, (Scale $source 64))
    }
    $source.Dispose()

    # ICONDIR, one ICONDIRENTRY per frame, then the PNG data.
    $stream = New-Object IO.MemoryStream
    $writer = New-Object IO.BinaryWriter $stream
    $writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]$frames.Count)
    $offset = 6 + 16 * $frames.Count
    for ($i = 0; $i -lt $frames.Count; $i++) {
        $edge = if ($sizes[$i] -ge 256) { 0 } else { $sizes[$i] }
        $writer.Write([byte]$edge); $writer.Write([byte]$edge); $writer.Write([byte]0); $writer.Write([byte]0)
        $writer.Write([uint16]1); $writer.Write([uint16]32)
        $writer.Write([uint32]$frames[$i].Length); $writer.Write([uint32]$offset)
        $offset += $frames[$i].Length
    }
    foreach ($frame in $frames) { $writer.Write([byte[]]$frame) }
    $writer.Flush()
    New-Item -ItemType Directory -Force (Split-Path $Output) | Out-Null
    [IO.File]::WriteAllBytes($Output, $stream.ToArray())
    Write-Host "Icon ($($frames.Count) frames) -> $Output"
}
finally {
    Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
}
