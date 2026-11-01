using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

namespace RtxForge.Windows.Models;

/// <summary>The exact preference file read and written by the native glass renderer.</summary>
public sealed class GlassAppearance
{
    public static string FilePath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "overlay-appearance.ini");
    public static readonly string[] Layouts = ["floating", "centered", "bar"];
    public static readonly string[] Themes = ["clear", "light", "dark", "accent"];
    public static readonly string[] Blends = ["normal", "overlay", "soft-light", "multiply", "screen", "hard-light", "darken", "lighten", "color", "luminosity", "difference"];
    public static string BlendLabel(string value) => CultureInfo.InvariantCulture.TextInfo.ToTitleCase(value.Replace('-', ' '));
    readonly Dictionary<string, string> values;
    GlassAppearance(Dictionary<string, string> values) => this.values = values;
    public int Number(string key, int fallback, int min, int max) => Math.Clamp(int.TryParse(Get(key, ""), out var n) ? n : fallback, min, max);
    public string Get(string key, string fallback) => values.GetValueOrDefault(key, fallback);
    public bool On(string key, bool fallback = true) => Number(key, fallback ? 1 : 0, 0, 1) != 0;
    public string Theme => Number("ThemeVersion", 0, 0, 4) != 4 ? "clear" : Number("Theme", 3, 1, 4) switch { 1 => "light", 2 => "dark", 4 => "accent", _ => "clear" };
    public bool AccentEnabled => Theme == "accent";
    public string BaseTheme => !AccentEnabled ? Theme : Number("AccentCharacter",35,0,100) < 20 ? "clear" : Number("AccentCharacter",35,0,100) < 72 ? "light" : "dark";
    public static void UseAppearance(string? baseTheme = null, bool? tint = null, string? path = null)
    {
        var previous=Load(path);baseTheme ??= previous.BaseTheme;tint ??= previous.AccentEnabled;
        if(baseTheme is not ("clear" or "light" or "dark"))throw new ArgumentException("Choose Clear, Light or Dark.");
        UseTheme(tint.Value?"accent":baseTheme,path);
        if(tint.Value){Set("AccentCharacter",baseTheme=="clear"?10:baseTheme=="light"?50:100,path:path);Set("AccentSaturation",baseTheme=="dark"?94:200,path:path);}
    }
    public string Layout => Layouts.Contains(Get("Layout", "floating")) ? Get("Layout", "floating") : "floating";
    public string SidePanelSide => Get("SidePanelSide", "left") == "right" ? "right" : "left";
    public int Tint => Number(Theme == "light" ? "LightTint" : Theme == "dark" ? "DarkTint" : Theme == "accent" ? "AccentTint" : "ClearTint", Theme == "light" ? 100 : Theme == "dark" ? 80 : 20, 0, 100);
    public bool Custom => On("Custom", false);
    static readonly Dictionary<string, (int Low, int High, int Default)> Ranges = new()
    {
        ["ThemeVersion"]=(4,4,4), ["Theme"]=(1,4,3), ["Custom"]=(0,1,0), ["TextSize"]=(16,26,22),
        ["Scale"]=(70,150,100), ["ScaleBaseline"]=(120,120,120), ["LightTint"]=(0,100,100),
        ["DarkTint"]=(0,100,80), ["ClearTint"]=(0,100,20), ["AccentCharacter"]=(0,100,35), ["AccentTint"]=(0,100,67), ["AccentSaturation"]=(0,200,100), ["Blur"]=(16,48,48), ["Grain"]=(0,80,40),
        ["BlendStrength"]=(0,100,50), ["OriginalLabels"]=(0,1,0), ["TextDepth"]=(0,1,1), ["InvertDark"]=(0,1,0), ["ToastPill"]=(0,1,0),
        ["Motion"]=(0,1,1), ["ShowNotifications"]=(0,1,1),
    };
    static readonly Dictionary<string, string[]> Options = new()
    { ["Layout"]=Layouts, ["SidePanelSide"]=["left","right"], ["TextFont"]=["roboto","inter"], ["SurfaceBlend"]=Blends };
    public JsonObject ToJson()
    {
        var result = new JsonObject();
        foreach (var (key, range) in Ranges) result[key] = Number(key, range.Default, range.Low, range.High);
        result["Theme"] = Theme == "light" ? 1 : Theme == "dark" ? 2 : Theme == "accent" ? 4 : 3;
        foreach (var (key, options) in Options)
        {
            var fallback = key == "Layout" ? "floating" : key == "SidePanelSide" ? "left" : key == "TextFont" ? "roboto" : "soft-light";
            var value = Get(key, fallback); result[key] = options.Contains(value) ? value : fallback;
        }
        return result;
    }
    public static JsonObject Validate(JsonObject values)
    {
        foreach (var (key, value) in values)
        {
            if (Ranges.TryGetValue(key, out var range))
            {
                if (value is not JsonValue number || !number.TryGetValue<int>(out var n) || n < range.Low || n > range.High)
                    throw new InvalidOperationException("Overlay " + key + " is outside its supported range.");
            }
            else if (!Options.TryGetValue(key, out var choices) || value is not JsonValue text || !text.TryGetValue<string>(out var s) || !choices.Contains(s))
                throw new InvalidOperationException("Choose a supported overlay appearance option.");
        }
        return (JsonObject)values.DeepClone();
    }
    public static void Import(JsonObject values)
    {
        foreach (var (key, value) in Validate(values)) Set(key, value!.ToString());
    }

    public static GlassAppearance Load(string? path = null)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        try
        {
            bool appearance = false;
            foreach (var line in File.ReadAllLines(path ?? FilePath))
            {
                var text = line.Trim();
                if (text.StartsWith('[')) { appearance = text.Equals("[Appearance]", StringComparison.OrdinalIgnoreCase); continue; }
                if (!appearance || text.StartsWith(';') || text.StartsWith('#')) continue;
                var split = text.IndexOf('=');
                if (split > 0) values[text[..split].Trim()] = text[(split + 1)..].Trim();
            }
        }
        catch (IOException) { }
        return new(values);
    }

    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool WritePrivateProfileString(string section, string key, string value, string path);
    public static void Set(string key, object value, bool custom = false, string? path = null)
    {
        path ??= FilePath;
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        if (key != "ThemeVersion") Set("ThemeVersion", 4, path: path);
        if (!WritePrivateProfileString("Appearance", key, Convert.ToString(value, CultureInfo.InvariantCulture)!, path))
            throw new IOException("Could not save overlay appearance.");
        if (key == "AccentCharacter")
        {
            var x = Math.Clamp(Convert.ToDouble(value, CultureInfo.InvariantCulture) / 50, 0, 1);
            Set("AccentTint", (int)Math.Round(20 + 60 * x * x * (3 - 2 * x)), path: path);
        }
        if (custom) Set("Custom", 1, path: path);
    }
    public static void UseTheme(string theme, string? path = null)
    {
        if (!Themes.Contains(theme)) throw new ArgumentException("Choose Clear, Light, Dark or Accent.");
        foreach (var (key, value) in new Dictionary<string, object> {
            ["ThemeVersion"]=4, ["Theme"]=theme=="light"?1:theme=="dark"?2:theme=="accent"?4:3,
            ["LightTint"]=100, ["DarkTint"]=80, ["ClearTint"]=20, ["AccentCharacter"]=35, ["AccentTint"]=67, ["AccentSaturation"]=100,
            ["Blur"]=theme=="light"?44:48, ["Grain"]=40, ["BlendStrength"]=theme=="light"?35:theme=="dark"?15:theme=="accent"?0:50,
            ["SurfaceBlend"]=theme=="accent"?"normal":theme=="clear"?"soft-light":"overlay", ["Custom"]=0, ["InvertDark"]=0, ["TextDepth"]=1 }) Set(key, value, path: path);
    }
}
