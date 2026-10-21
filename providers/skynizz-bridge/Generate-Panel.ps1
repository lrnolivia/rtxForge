param([Parameter(Mandatory)][string]$SourceRoot)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$menu = Join-Path $SourceRoot 'OptiScaler\menu'
$schema = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $PSScriptRoot 'controls.json') | ConvertFrom-Json
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
    } elseif ($control.key -in 'dlss_preset', 'rr_preset') {
        # OptiScaler applies a render preset only with its override on; Game default turns it off.
        $override = if ($control.key -eq 'rr_preset') { 'DLSSDRenderPresetOverride' } else { 'RenderPresetOverride' }
        $get = '[](Config& c) { return c.' + $override + '.value_or_default() ? float(c.' + $member + '.value_or_default()) : 0.f; }'
        $set = '[](Config& c, float n, bool save) { const bool on = n > 0; const auto preset = static_cast<uint32_t>(n); if(save) { c.' + $override + ' = on; c.' + $member + ' = preset; } else { c.' + $override + '.set_volatile_value(on); c.' + $member + '.set_volatile_value(preset); } }'
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

# Both mappings must use the same Wine transport. Apply after all versioned
# patches, without changing the upstream patch stack or the Windows protocol.
$companion = Join-Path $SourceRoot 'OptiScaler\framegen\dlssg\Companion.h'
$text = [IO.File]::ReadAllText($companion)
$old = 'CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(Mailbox), name.c_str())'
if (-not $text.Contains($old)) { throw 'Companion mapping source changed; review the Wine transport integration.' }
$text = "#include <menu/ForgePanelChannel.h>`n" + $text.Replace($old, 'ForgeWineMapping::Create(L"controls", sizeof(Mailbox), name.c_str())')
[IO.File]::WriteAllText($companion, $text, [Text.UTF8Encoding]::new($false))
