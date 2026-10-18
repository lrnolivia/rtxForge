namespace RtxForge.Windows.Services;

public static class OverlayShortcut
{
    public static readonly string[] Choices = ["Insert", "F8", "Ctrl+Shift+R", "Ctrl+Alt+R", "Ctrl+Shift+F10", "Disabled"];
    public static (uint Modifiers, uint Key) Decode(string value) => value switch
    {
        "Insert" => (0, 0x2D), "F8" => (0, 0x77), "Ctrl+Alt+R" => (3, 0x52),
        "Ctrl+Shift+R" => (6, 0x52), "Ctrl+Shift+F10" => (6, 0x79),
        "Disabled" => (0, 0), _ => (0, 0x2D),
    };
}
