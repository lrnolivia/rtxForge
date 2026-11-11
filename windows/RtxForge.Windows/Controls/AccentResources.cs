using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Services;
using Windows.UI;
using Windows.UI.ViewManagement;

namespace RtxForge.Windows.Controls;

/// <summary>
/// A game's accent on the WinUI accent surfaces: primary buttons, sliders, toggles,
/// progress and selector pills. Used by Game Details and by any review or install
/// screen that works on that one game.
/// </summary>
public static class AccentResources
{
    internal static readonly string[] Sources = ["green", "system", "custom"];
    internal static readonly string[] Captions = ["rtxForge Green", "System", "Custom"];
    internal static readonly UISettings SystemSettings = new();
    internal static readonly Color Green = Color.FromArgb(255, 118, 185, 0);
    static readonly Dictionary<string, SolidColorBrush> appBrushes = [];

    internal static Color Resolve(string source, string custom) => source switch
    {
        "system" => SystemSettings.GetColorValue(UIColorType.Accent),
        "custom" when ArtAccent.TryParse(custom, out var color) => color,
        _ => Green,
    };

    internal static async Task<Color?> PickAsync(MainWindow shell, string title, Color color)
    {
        var picker = new ColorPicker { IsAlphaEnabled = false, Color = color,
            IsMoreButtonVisible = false, IsColorChannelTextInputVisible = true, IsHexInputVisible = true, MaxWidth = 340 };
        var dialog = shell.NewDialog();
        dialog.Title = title;
        dialog.Content = picker;
        dialog.PrimaryButtonText = "Use color";
        dialog.CloseButtonText = "Cancel";
        return await dialog.ShowAsync() == ContentDialogResult.Primary ? picker.Color : null;
    }

    internal static void ApplyApp(Models.ForgeSettings settings, bool dark)
    {
        var resources = Application.Current.Resources;
        var color = Resolve(settings.DesktopAccentSource, settings.DesktopAccentColor);
        var palette = ArtAccent.Palette(color);
        var surface = dark ? Color.FromArgb(255, 38, 38, 38) : Colors.White;
        var text = ArtAccent.Readable(color, surface);
        resources["SystemAccentColor"] = color;
        for (var level = 1; level <= 3; level++)
        {
            resources[$"SystemAccentColorLight{level}"] = ArtAccent.Mix(Colors.White, color, level * 0.16);
            resources[$"SystemAccentColorDark{level}"] = ArtAccent.Mix(Colors.Black, color, level * 0.17);
        }
        foreach (var key in new[] { "AccentTextFillColorPrimaryBrush", "AccentTextFillColorSecondaryBrush", "AccentTextFillColorTertiaryBrush" })
            SetBrush(resources, key, new SolidColorBrush(text), updateExisting: true);
        foreach (var key in new[] { "AccentFillColorSecondaryBrush", "AccentFillColorTertiaryBrush" })
            SetBrush(resources, key, palette.Brush(color, key == "AccentFillColorSecondaryBrush" ? 0.9 : 0.8), updateExisting: true);
        foreach (var key in new[] { "TextOnAccentFillColorPrimaryBrush", "TextOnAccentFillColorSecondaryBrush" })
            SetBrush(resources, key, palette.Brush(palette.AccentFg), updateExisting: true);
        Apply(resources, palette, updateExisting: true);
    }

    static void SetBrush(ResourceDictionary resources, string key, SolidColorBrush brush, bool updateExisting)
    {
        if (updateExisting && appBrushes.TryGetValue(key, out var existing))
        {
            existing.Color = brush.Color;
            existing.Opacity = brush.Opacity;
        }
        else
        {
            resources[key] = brush;
            if (updateExisting) appBrushes.Add(key, brush);
        }
    }

    public static void Apply(ResourceDictionary resources, AccentPalette palette, bool updateExisting = false)
    {
        var accent = palette.AccentBrush;
        var hover = palette.Brush(palette.Color, 0.9);
        var pressed = palette.Brush(palette.Color, 0.8);
        var accentFg = palette.Brush(palette.AccentFg);
        foreach (var (key, brush) in new (string, SolidColorBrush)[]
        {
            ("AccentFillColorDefaultBrush", accent),
            ("AccentButtonBackground", accent), ("AccentButtonBackgroundPointerOver", hover), ("AccentButtonBackgroundPressed", pressed),
            ("AccentButtonForeground", accentFg), ("AccentButtonForegroundPointerOver", accentFg), ("AccentButtonForegroundPressed", accentFg),
            ("SliderTrackValueFill", accent), ("SliderTrackValueFillPointerOver", hover), ("SliderTrackValueFillPressed", pressed),
            ("SliderThumbBackground", accent), ("SliderThumbBackgroundPointerOver", hover), ("SliderThumbBackgroundPressed", pressed),
            ("ToggleSwitchFillOn", accent), ("ToggleSwitchFillOnPointerOver", hover), ("ToggleSwitchFillOnPressed", pressed),
            ("ToggleSwitchKnobFillOn", accentFg), ("ProgressBarForeground", accent),
            ("SelectorBarItemPillFill", accent), ("NavigationViewSelectionIndicatorForeground", accent),
        })
            SetBrush(resources, key, brush, updateExisting);
        if (!updateExisting) resources["SelectorBarItemBackgroundSelected"] = palette.Brush(palette.Color, 0.10);
    }

    /// <summary>The single game a screen works on, or null when it covers several.</summary>
    public static Models.Game? Single(IReadOnlyList<Models.Game> targets) => targets.Count == 1 ? targets[0] : null;

    /// <summary>Applies the game's accent before a dialog opens; nothing for a library-wide screen.</summary>
    public static async Task ApplyAsync(ResourceDictionary resources, Models.Game? game)
    {
        if (game is null) return;
        if (await ArtAccent.ForGameAsync(game) is { } palette) Apply(resources, palette);
    }
}
