using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.UI;

namespace RtxForge.Windows.Services;

/// <summary>
/// App Theme: System / Light / Dark / Night. Light, Dark and System sit on
/// Mica like any Windows 11 app; Night (Linux's neutral black palette) turns
/// Mica off and uses a true black window.
/// </summary>
public static class ThemeController
{
    public static readonly string[] Keys = ["system", "light", "dark", "night"];
    public static readonly string[] Captions = ["Use system setting", "Light", "Dark", "Night"];

    public static void Apply(Window window, Panel root, string theme)
    {
        root.RequestedTheme = theme switch
        {
            "light" => ElementTheme.Light,
            "dark" or "night" => ElementTheme.Dark,
            _ => ElementTheme.Default,
        };

        if (theme == "night")
        {
            window.SystemBackdrop = null;
            root.Background = new SolidColorBrush(Colors.Black);
        }
        else
        {
            if (window.SystemBackdrop is not MicaBackdrop) window.SystemBackdrop = new MicaBackdrop();
            root.Background = new SolidColorBrush(Colors.Transparent);
        }

        // Caption buttons follow the effective theme.
        var dark = root.ActualTheme == ElementTheme.Dark;
        var bar = window.AppWindow.TitleBar;
        bar.ButtonBackgroundColor = Colors.Transparent;
        bar.ButtonInactiveBackgroundColor = Colors.Transparent;
        bar.ButtonForegroundColor = dark ? Colors.White : Colors.Black;
        bar.ButtonHoverBackgroundColor = dark ? Color.FromArgb(0x18, 0xFF, 0xFF, 0xFF) : Color.FromArgb(0x12, 0, 0, 0);
        bar.ButtonHoverForegroundColor = dark ? Colors.White : Colors.Black;
    }
}
