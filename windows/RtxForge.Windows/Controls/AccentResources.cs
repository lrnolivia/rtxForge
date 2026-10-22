using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Controls;

/// <summary>
/// A game's accent on the WinUI accent surfaces: primary buttons, sliders, toggles,
/// progress and selector pills. Used by Game Details and by any review or install
/// screen that works on that one game.
/// </summary>
public static class AccentResources
{
    public static void Apply(ResourceDictionary resources, AccentPalette palette)
    {
        var accent = palette.AccentBrush;
        var hover = palette.Brush(palette.Color, 0.9);
        var pressed = palette.Brush(palette.Color, 0.8);
        var accentFg = palette.Brush(palette.AccentFg);
        foreach (var (key, brush) in new (string, Brush)[]
        {
            ("AccentFillColorDefaultBrush", accent),
            ("AccentButtonBackground", accent), ("AccentButtonBackgroundPointerOver", hover), ("AccentButtonBackgroundPressed", pressed),
            ("AccentButtonForeground", accentFg), ("AccentButtonForegroundPointerOver", accentFg), ("AccentButtonForegroundPressed", accentFg),
            ("SliderTrackValueFill", accent), ("SliderTrackValueFillPointerOver", hover), ("SliderTrackValueFillPressed", pressed),
            ("SliderThumbBackground", accent), ("SliderThumbBackgroundPointerOver", hover), ("SliderThumbBackgroundPressed", pressed),
            ("ToggleSwitchFillOn", accent), ("ToggleSwitchFillOnPointerOver", hover), ("ToggleSwitchFillOnPressed", pressed),
            ("ToggleSwitchKnobFillOn", accentFg), ("ProgressBarForeground", accent),
            ("SelectorBarItemPillFill", accent),
            ("SelectorBarItemBackgroundSelected", palette.Brush(palette.Color, 0.10)),
        })
            resources[key] = brush;
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
