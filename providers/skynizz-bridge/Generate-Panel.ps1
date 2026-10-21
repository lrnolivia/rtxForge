param([Parameter(Mandatory)][string]$SourceRoot)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$menu = Join-Path $SourceRoot 'OptiScaler\menu'
$schema = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'controls.json') | ConvertFrom-Json
function CppString([string]$value) {
    $result = [Text.StringBuilder]::new('"')
    foreach ($letter in [Text.Encoding]::UTF8.GetBytes($value)) {
        if ($letter -eq 34 -or $letter -eq 92) { [void]$result.Append('\').Append([char]$letter) }
        elseif ($letter -gt 126) { [void]$result.Append(('\x{0:x2}""' -f $letter)) }
        else { [void]$result.Append([char]$letter) }
    }
    [void]$result.Append('"'); $result.ToString()
}
function CppFloat($value) { ([double]$value).ToString('0.0########', [Globalization.CultureInfo]::InvariantCulture) + 'f' }
$lines = [Collections.Generic.List[string]]::new()
$lines.Add('// Generated from controls.json by Generate-Panel.ps1. Do not edit.')
foreach ($control in $schema.controls) {
    if ($control.kind -ne 'choice') { continue }
    $items = @()
    for ($index = 0; $index -lt $control.values.Count; $index++) {
        $items += '{ ' + (CppFloat $control.values[$index]) + ', ' + (CppString $control.choices[$index]) + ' }'
    }
    $lines.Add('inline constexpr Choice choices_' + $control.key + '[] = { ' + ($items -join ', ') + ' };')
}
$lines.Add('inline const Control controls[] = {')
foreach ($control in $schema.controls) {
    $member = $control.member
    if ($control.key -eq 'multiplier') {
        $get = '[](Config& c) { return !c.FGDLSSGOverrideInterpolationCount.has_value() ? -1.f : c.FGDLSSGOverrideInterpolationCount.value() == 0 ? 0.f : float(c.FGDLSSGOverrideInterpolationCount.value() + 1); }'
        $set = '[](Config& c, float n, bool save) { if(n < 0) c.FGDLSSGOverrideInterpolationCount = std::nullopt; else { int count = n == 0 ? 0 : int(n)-1; if(save) c.FGDLSSGOverrideInterpolationCount = count; else c.FGDLSSGOverrideInterpolationCount.set_volatile_value(count); if(count > 0) c.FGDLSSGInterpolationCount.set_volatile_value(count); } }'
    } else {
        $get = '[](Config& c) { return float(c.' + $member + '.value_or_default()); }'
        $cast = 'static_cast<typename std::decay_t<decltype(c.' + $member + ')>::value_type>(n)'
        $set = '[](Config& c, float n, bool save) { if(save) c.' + $member + ' = ' + $cast + '; else c.' + $member + '.set_volatile_value(' + $cast + '); }'
    }
    $choices = if ($control.kind -eq 'choice') { 'choices_' + $control.key + ', ' + $control.values.Count } else { 'nullptr, 0' }
    $lines.Add('  { ' + (CppString $control.key) + ', ' + (CppString $control.label) + ', ' + (CppString $control.advanced) + ', ' + (CppString $control.group) + ', Kind::' + $control.kind + ', ' + (CppFloat $control.min) + ', ' + (CppFloat $control.max) + ', ' + $get + ', ' + $set + ', ' + $choices + ' },')
}
$lines.Add('};')
[IO.File]::WriteAllLines((Join-Path $menu 'ForgePanelBindings.h'), $lines, [Text.UTF8Encoding]::new($false))
$font = [IO.File]::ReadAllBytes((Join-Path $repo 'windows\RtxForge.Windows\Assets\Fonts\InterVariable.ttf'))
$fontCode = 'inline unsigned char forgeInter[] = {' + (($font | ForEach-Object { $_.ToString() }) -join ',') + '};'
$semiBold = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'Inter-SemiBold.ttf'))
$fontCode += "`n" + 'inline unsigned char forgeInterSemiBold[] = {' + (($semiBold | ForEach-Object { $_.ToString() }) -join ',') + '};'
[IO.File]::WriteAllText((Join-Path $menu 'ForgePanelFont.h'), $fontCode, [Text.UTF8Encoding]::new($false))
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'ForgePanel.h') -Destination $menu
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'ForgePanelChannel.h') -Destination $menu
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'ForgePanelIcon.h') -Destination $menu
