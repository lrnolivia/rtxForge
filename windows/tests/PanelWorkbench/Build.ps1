param([Parameter(Mandatory)][string]$SourceRoot, [Parameter(Mandatory)][string]$Output)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$bridge = Join-Path $repo 'providers\skynizz-bridge'
$Output = [IO.Path]::GetFullPath($Output)
$menu = Join-Path $Output 'OptiScaler\menu'
New-Item -ItemType Directory -Force $menu | Out-Null
& (Join-Path $bridge 'Generate-Panel.ps1') -SourceRoot $Output
# A memory-only Config adapter exercises the actual generated panel bindings.
# It reads no installed settings and never opens a game or helper mapping.
$shim = Get-Content (Join-Path $repo 'windows\feeder-panel\shim\Config.h') -Raw
$shim = $shim.Substring(0,$shim.IndexOf('class Config'))
$shim += @'
template<class T> struct TestValue {
    using value_type=T;
    T n{}; bool present=true;
    TestValue(T value):n(value){}
    bool has_value() const { return present; }
    T value() const { return n; }
    T value_or_default() const { return n; }
    void set_volatile_value(T value) { n=value; present=true; }
    TestValue& operator=(T value) { set_volatile_value(value); return *this; }
    TestValue& operator=(std::nullopt_t) { present=false; return *this; }
};
class Config {
public:
    static Config* Instance() { static Config value; return &value; }
    TestValue<bool> FGDLSSGOverrideForceDMFG{false}, RenderPresetOverride{false}, DLSSDRenderPresetOverride{false};
    TestValue<int> FGDLSSGInterpolationCount{1};
'@
$schema = Get-Content (Join-Path $bridge 'controls.json') -Raw | ConvertFrom-Json
foreach($field in $schema.controls) {
    $type = if($field.kind -eq 'slider') {'float'} elseif($field.kind -eq 'toggle') {'bool'} else {'int'}
    $value = if($type -eq 'bool') {if($field.default) {'true'} else {'false'}}
             else {([double]$field.default).ToString('0.0####',[Globalization.CultureInfo]::InvariantCulture)+$(if($type -eq 'float') {'f'} else {''})}
    if($type -eq 'int') {$value=[int]$field.default}
    $shim += "`n    TestValue<$type> $($field.member){$value};"
}
$shim += "`n};`n"
[IO.File]::WriteAllText((Join-Path $menu 'Config.h'),$shim,[Text.UTF8Encoding]::new($false))
foreach($name in @('Logger.h','Util.h')) { Copy-Item -LiteralPath (Join-Path $repo "windows\feeder-panel\shim\$name") -Destination $menu }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vcvars = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find 'VC\Auxiliary\Build\vcvars64.bat' | Select-Object -First 1
if(!$vcvars) { throw 'C++ build tools are required.' }
$imgui = Join-Path $SourceRoot 'OptiScaler\include\imgui'
$freetype = Join-Path $SourceRoot 'external\freetype'
$json = Join-Path $SourceRoot 'external\nlohmann'
$sources = @((Join-Path $PSScriptRoot 'Render.cpp'), "$imgui\imgui.cpp", "$imgui\imgui_draw.cpp", "$imgui\imgui_widgets.cpp", "$imgui\imgui_tables.cpp", "$imgui\imgui_impl_dx11.cpp", "$imgui\misc\freetype\imgui_freetype.cpp")
$quoted = ($sources | ForEach-Object {'"'+$_+'"'}) -join ' '
$command = '"'+$vcvars+'" >nul && cl /nologo /std:c++latest /EHsc /MT /utf-8 /DNOMINMAX /DUNICODE /D_UNICODE /DIMGUI_ENABLE_STB_TRUETYPE /I"'+$menu+'" /I"'+(Join-Path $SourceRoot 'OptiScaler\include')+'" /I"'+$freetype+'" /I"'+$json+'" '+$quoted+' /Fe:"'+(Join-Path $Output 'PanelWorkbench.exe')+'" /Fo:"'+$Output+'/" /link d3d11.lib dxgi.lib d3dcompiler.lib user32.lib advapi32.lib ole32.lib windowscodecs.lib "'+$freetype+'\freetype.lib"'
& $env:ComSpec /d /s /c $command
if($LASTEXITCODE) { throw 'Panel fixture build failed.' }
