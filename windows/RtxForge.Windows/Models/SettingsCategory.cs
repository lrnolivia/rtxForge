namespace RtxForge.Windows.Models;

public static class SettingsCategory
{
    public static string Glyph(string category) => category switch
    {
        "Graphics" => "\uE7F4", "Overlay" => "\uE8A7", "Appearance" => "\uE790", "Library" => "\uE8F1",
        "Gaming Mode" => "\uE7FC", "System" => "\uE770", "Recovery" => "\uE777", _ => "\uE946",
    };
}
