param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference = 'Stop'
$schema = Get-Content (Join-Path $PSScriptRoot '../../providers/skynizz-bridge/controls.json') -Raw | ConvertFrom-Json
$pages = @{
    pre_sr='neural'; reduced='neural'; work_scale='neural'; edge_aware='neural'; cache='neural'; interval='neural'
    structure='look'; skin='look'; auto_mask='look'; sharpen='look'; sharpen_shader='look'; sharp_override='look'; sharpness='look'; motion_sharpen='look'; motion_sharpness='look'
    dlss_preset='neural'; rr_preset='neural'
}
$names = @{
    pre_sr='Processing stage'; reduced='Smaller model'; work_scale='Render resolution'; edge_aware='Preserve edges'; cache='Reuse enhancements'; interval='Refresh interval'
    structure='Texture detail'; skin='Skin detail'; auto_mask='Protect skin automatically'; sharpen='Sharpen image'; sharpen_shader='Sharpening filter'; sharp_override='Use custom sharpening'; sharpness='Sharpening strength'; motion_sharpen='Sharpen moving detail'; motion_sharpness='Motion sharpening'
    dlss_preset='Upscaling model'; rr_preset='Ray Reconstruction model'
}
function Quote([string]$Value) { '"' + $Value.Replace('\','\\').Replace('"','\"').Replace("`r",'').Replace("`n",'\n') + '"' }
function Options($Control) {
    if($Control.key -eq 'pre_sr') { return '<option value="1">Before upscaling</option><option value="0">After upscaling</option>' }
    $result = ''
    for($i=0; $i -lt $Control.choices.Count; $i++) {
        $label = [Security.SecurityElement]::Escape($Control.choices[$i])
        $result += '<option value="'+$Control.values[$i]+'">'+$label+'</option>'
    }
    $result
}
$rows = [Collections.Generic.List[string]]::new()
foreach($control in $schema.controls) {
    if(-not $pages.ContainsKey($control.key)) { continue }
    $kind = if($control.key -eq 'pre_sr') { 'choice' } elseif($control.kind -eq 'number') { 'slider' } else { $control.kind }
    $options = Options $control
    $numbers = @($control.min,$control.max,$control.step,$control.default) | ForEach-Object { ([double]$_).ToString('0.####',[Globalization.CultureInfo]::InvariantCulture)+'f' }
    # C++ floating literals require a decimal point when written with an f suffix.
    $numbers = $numbers | ForEach-Object { if($_ -match '^(-?\d+)f$') { $Matches[1]+'.0f' } else { $_ } }
    $rows.Add('    {'+(Quote $control.key)+','+(Quote $names[$control.key])+','+(Quote $pages[$control.key])+','+(Quote $kind)+','+($numbers -join ',')+','+(Quote $options)+',"bridge"},')
}
# These controls exist in the pinned upstream menu but are not in mailbox v8.
# They remain prototype values until a capability-gated runtime binding exists.
$rows.Add('    {"area","Area","neural","choice",0.f,2.f,1.f,0.f,"<option value=\"0\">Whole frame</option><option value=\"1\">Background</option><option value=\"2\">Foreground</option>","upstream"},')
$rows.Add('    {"area_distance","Distance","neural","slider",2.f,2000.f,1.f,40.f,"","upstream"},')
$rows.Add('    {"area_softness","Edge softness","neural","slider",.05f,2.f,.05f,.5f,"","upstream"},')
$rows.Add('    {"area_strength","Area strength","neural","slider",0.f,1.f,.01f,1.f,"","upstream"},')
$rows.Add('    {"show_area","Show affected area","neural","toggle",0.f,1.f,1.f,0.f,"","upstream"},')
$rows.Add('    {"fg_auto","Adjust multiplier automatically","frame","toggle",0.f,1.f,1.f,0.f,"","upstream"},')
$rows.Add('    {"fg_target","Target frame rate · 0 follows display","frame","slider",0.f,480.f,1.f,0.f,"","upstream"},')
$rows.Add('    {"fg_meter","Show frame-generation statistics","frame","toggle",0.f,1.f,1.f,0.f,"","upstream"},')
$rows.Add('    {"fg_cleanup","Reduce dots during fast movement","frame","toggle",0.f,1.f,1.f,0.f,"","upstream"},')
$rows.Add('    {"fg_cleanup_strength","Cleanup strength","frame","slider",0.f,1.f,.01f,.5f,"","upstream"},')
$rows.Add('    {"fg_game_version","Use game-bundled frame generation","frame","toggle",0.f,1.f,1.f,0.f,"","upstream"},')
for($i=0;$i -lt $rows.Count;$i++) {
    $key = [regex]::Match($rows[$i],'^\s*\{"([^"]+)"').Groups[1].Value
    $group = if($key -like 'area*' -or $key -eq 'show_area') { 'Area' } elseif($key -in @('dlss_preset','rr_preset')) { 'Upscaling' } elseif($key -like 'fg_cleanup*') { 'Clarity' } elseif($key -eq 'fg_game_version') { 'Compatibility' } elseif($key -like 'fg_*') { 'Frame delivery' } elseif($key -like '*sharpen*' -or $key -in @('sharp_override','sharpness')) { 'Sharpening' } elseif($pages[$key] -eq 'look') { 'Texture detail' } else { 'Processing' }
    $advanced = ($schema.controls | Where-Object key -eq $key | Select-Object -First 1).advanced
    if(-not $advanced) { $advanced = [regex]::Match($rows[$i],'^\s*\{"[^"]+","([^"]+)"').Groups[1].Value }
    $rows[$i] = $rows[$i].Substring(0,$rows[$i].Length-2) + ',' + (Quote $group) + ',' + (Quote $advanced) + '},'
}
$header = @'
#pragma once
// Shared control bounds come from controls.json. Extra upstream controls are
// explicitly identified, so a preview never implies a mailbox capability.
struct ExtraControl { const char* key; const char* label; const char* page; const char* kind; float minimum,maximum,step,initial; const char* options; const char* binding; const char* section; const char* advanced; };
inline const ExtraControl ExtraControls[] = {
'@ + "`n" + ($rows -join "`n") + "`n};`n"
$header += "struct ScenePreset { int app; const char* title; const char* file; unsigned accent; };`ninline const ScenePreset ScenePresets[] = {`n"
foreach($scene in (Get-Content (Join-Path $PSScriptRoot 'scenes.json') -Raw | ConvertFrom-Json)) {
    $header += '    {'+$scene.app+','+(Quote $scene.title)+','+(Quote $scene.file)+',0x'+$scene.accent.TrimStart('#')+'},'+"`n"
}
$header += "};`n"
$hdrProfile = (Get-Content (Join-Path $PSScriptRoot '../../providers/renodx-hdr-settings.json') -Raw | ConvertFrom-Json).profiles[0]
$header += "struct PreviewHdrField { const char* key; const char* label; const char* section; const char* kind; const char* options; const char* unit; float minimum,maximum,step,initial; bool reset; };`ninline const PreviewHdrField PreviewHdrFields[] = {`n"
foreach($field in $hdrProfile.controls) {
    $options='';for($i=0;$i -lt $field.choices.Count;$i++){$options += '<option value="'+$i+'">'+[Security.SecurityElement]::Escape($field.choices[$i])+'</option>'}
    $numbers=@($field.min,$field.max,$field.step,$field.default)|ForEach-Object{([double]$_).ToString('0.0###',[Globalization.CultureInfo]::InvariantCulture)+'f'}
    $header += '    {'+((@($field.key,$field.label,$field.section,$field.kind,$options,$field.unit)|ForEach-Object{Quote $_}) -join ',')+','+($numbers -join ',')+','+([string]([bool]$field.reset)).ToLowerInvariant()+'},'+"`n"
}
$header += "};`n"
$header += "struct ControlLabel { const char* key; const char* friendly; const char* original; };`ninline const ControlLabel ControlLabels[] = {`n"
# Verbatim display names from the pinned OptiScaler NR menu. Other bridge
# controls use the shared schema's upstream name; shader/add-on labels arrive
# from ReShade itself and are preserved by the reflected controls.
$originalNames = @{
    enabled='Enable Neural Rendering'; style='Model style'; pre_sr='Run before the upscaler'
    cache="Reuse the model's edit between runs (edit cache)"; interval='Max frames between runs'
}
$friendlyNames = @{
    intensity='Strength'; preset='Model'; passes='Passes'; colour='Color'; detail='Detail'
    structure='Texture detail'; skin='Skin detail'; pre_sr='Processing stage'
}
foreach($control in $schema.controls) {
    $friendly = if($names.ContainsKey($control.key)) { $names[$control.key] } elseif($friendlyNames.ContainsKey($control.key)) { $friendlyNames[$control.key] } else { $control.label }
    $original = if($originalNames.ContainsKey($control.key)) { $originalNames[$control.key] } else { $control.advanced }
    $header += '    {'+(Quote $control.key)+','+(Quote $friendly)+','+(Quote $original)+'},'+"`n"
}
foreach($row in @(
    @('area','Area','Region'), @('area_distance','Distance','Near distance'), @('area_softness','Edge softness','Edge softness'),
    @('area_strength','Area strength','Mask strength'), @('show_area','Show affected area','Show mask'),
    @('fg_auto','Adjust multiplier automatically','Auto multiplier'), @('fg_target','Target frame rate · 0 follows display','Target fps (0 = display)'),
    @('fg_meter','Show frame-generation statistics','Frame generation meter'), @('fg_cleanup','Reduce dots during fast movement','Speckle cleanup (dots on fast turns)'),
    @('fg_cleanup_strength','Cleanup strength','Cleanup strength'), @('fg_game_version','Use game-bundled frame generation',"Use the game's DLSS-G version")
)) { $header += '    {'+(($row | ForEach-Object { Quote $_ }) -join ',')+'},'+"`n" }
$header += "};`n"
[IO.File]::WriteAllText($Output,$header,[Text.UTF8Encoding]::new($false))
