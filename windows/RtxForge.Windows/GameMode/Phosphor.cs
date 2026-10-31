using System.Reflection;
using System.Text.Json;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.GameMode;

internal static class Phosphor
{
    static readonly JsonDocument Manifest = JsonDocument.Parse(Assembly.GetExecutingAssembly().GetManifestResourceStream("RtxForge.GameMode.Icons.json")!);
    internal static FontFamily Font { get; } = new("ms-appx:///Assets/GameMode/Icons/Phosphor.ttf#Phosphor");

    internal static string Resolve(string legacy)
    {
        var root = Manifest.RootElement;
        var name = legacy.Length == 1 && root.GetProperty("windows").TryGetProperty(((int)legacy[0]).ToString("X4"), out var symbol)
            ? symbol.GetString()! : "gear";
        return char.ConvertFromUtf32(root.GetProperty("codepoints").GetProperty(name).GetInt32());
    }
}
