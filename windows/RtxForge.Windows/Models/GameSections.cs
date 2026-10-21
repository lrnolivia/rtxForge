namespace RtxForge.Windows.Models;

public static class GameSections
{
    public static string Glyph(string name) => name switch
    {
        "Overview" => "\uE80F", "Features" or "Presets" => "\uE9E9", "DLSS Files" => "\uE8A5",
        "Tools" => "\uE90F", "Appearance" => "\uE790", "Notes" => "\uE70B", _ => "\uE713",
    };
}
