using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Services;
using Windows.UI;

namespace RtxForge.Windows.GameMode;

/// <summary>
/// Game Mode palette and scale from the approved prototype
/// (MagicPath radiant-rock-8795, .rf-prototype tokens). Night is the
/// default; Dark and Light follow the same roles. Branding (accent, Bakbak
/// wordmark, icon) is shared; everything else is the Windows adapter.
/// </summary>
public sealed class GmTheme
{
    public required string Name { get; init; }
    public required Color Window { get; init; }
    public required Color View { get; init; }
    public required Color Panel { get; init; }
    public required Color Card { get; init; }
    public required Color Fg { get; init; }
    public required Color Muted { get; init; }
    public required Color Focus { get; init; }
    public required Color Danger { get; init; }
    public required Color DangerBg { get; init; }
    public required Color Line { get; init; }
    public required Color Active { get; init; }       // .rf-button.rf-active / .rf-selected
    public required Color ActiveFg { get; init; }
    public required Color SegmentSelected { get; init; }
    public required Color RowFocus { get; init; }
    public required Color Disabled { get; init; }
    public required Color DisabledFg { get; init; }
    public required Color DlssSurface { get; init; }
    public required Color DlssInk { get; init; }
    public required Color DlssBorder { get; init; }
    public bool IsLight => Name == "light";

    public static readonly Color Accent = Hex("#76b900");
    public static readonly Color AccentInk = Hex("#151c07");

    /// <summary>Responsive scale with a 130% reference at the 4K desktop's effective viewport.</summary>
    public double Unit { get; private set; } = 22.5;
    /// <summary>Pixel sizes in the prototype are authored at --unit 26; S scales them.</summary>
    public double S => Unit / 26;
    /// <summary>The prototype's short-window compaction (max-height 800, max-width 2000).</summary>
    public bool Compact { get; private set; }

    /// <summary>Settings › UI scale: "auto" follows the breakpoints; a percentage scales from 150% = unit 26.</summary>
    public string Scale { get; set; } = "auto";

    public bool Resize(double width, double height)
    {
        var unit = Scale != "auto" && int.TryParse(Scale, out var percent)
            ? Math.Round(26.0 * percent / 150, 1)
            : Math.Round((width >= 3000 ? 46 : width <= 1050 ? 20 : width <= 1500 ? 22 : 26) * 130.0 / 150, 1);
        var compact = height <= 800 && width <= 2000;
        if (unit == Unit && compact == Compact) return false;
        Unit = unit;
        Compact = compact;
        return true;
    }

    public double Em(double em) => Math.Round(Unit * em, 1);
    public double Px(double px) => Math.Round(px * S, 1);

    public static GmTheme For(string appTheme) => appTheme switch
    {
        "light" => Light(),
        "dark" => Dark(),
        _ => Night(),   // Night is the Game Mode default (system follows it too)
    };

    static GmTheme Dark() => new()
    {
        Name = "dark",
        Window = Hex("#181818"), View = Hex("#222222"), Panel = Hex("#2b2b2b"), Card = Hex("#363636"),
        Fg = Hex("#f5f5f5"), Muted = Hex("#c3c3c3"), Focus = Hex("#c4c4c4"),
        Danger = Hex("#ffc6cc"), DangerBg = Hex("#4b2932"), Line = Hex("#494949"),
        Active = Hex("#ededed"), ActiveFg = Hex("#171717"), SegmentSelected = Hex("#e0e0e0"), RowFocus = Hex("#424242"),
        Disabled = Hex("#303030"), DisabledFg = Hex("#a3a3a3"),
        DlssSurface = Hex("#343434"), DlssInk = Hex("#ededed"), DlssBorder = Hex("#5a5a5a"),
    };

    static GmTheme Night() => new()
    {
        Name = "night",
        Window = Hex("#080c0f"), View = Hex("#0f1519"), Panel = Hex("#192228"), Card = Hex("#27343c"),
        Fg = Hex("#e8f0f4"), Muted = Hex("#bfd0da"), Focus = Hex("#adc5d3"),
        Danger = Hex("#ffc0cb"), DangerBg = Hex("#3e202b"), Line = Hex("#3e535f"),
        Active = Hex("#344c59"), ActiveFg = Hex("#f4f9fc"), SegmentSelected = Hex("#384f5d"), RowFocus = Hex("#30424d"),
        Disabled = Hex("#202c33"), DisabledFg = Hex("#8eabbc"),
        DlssSurface = Hex("#2e424f"), DlssInk = Hex("#e8f0f4"), DlssBorder = Hex("#7d9bab"),
    };

    static GmTheme Light() => new()
    {
        Name = "light",
        Window = Hex("#e2e9e5"), View = Hex("#f2f5f2"), Panel = Hex("#e6ece7"), Card = Hex("#ffffff"),
        Fg = Hex("#1c2b25"), Muted = Hex("#3d5043"), Focus = Hex("#566f61"),
        Danger = Hex("#7b2030"), DangerBg = Hex("#f5dfe3"), Line = Hex("#bdcac1"),
        Active = Hex("#c4d2c9"), ActiveFg = Hex("#192b20"), SegmentSelected = Hex("#c9d8ce"), RowFocus = Hex("#d6e1d9"),
        Disabled = Hex("#dbe3dd"), DisabledFg = Hex("#67776c"),
        DlssSurface = Hex("#f9fcfa"), DlssInk = Hex("#253c2e"), DlssBorder = Hex("#748b7c"),
    };

    public static Color Hex(string hex) => ArtAccent.TryParse(hex, out var c) ? c : Microsoft.UI.Colors.Magenta;
    public static SolidColorBrush B(Color c, double opacity = 1) => new(c) { Opacity = opacity };

    /// <summary>Per-game roles (--game-accent, --game-title, --game-tint, --game-pill, --game-ink).</summary>
    public GameColors GameColors(AccentPalette? palette)
    {
        var accent = palette?.Color ?? Hex("#b4b4b4");
        var title = IsLight ? ArtAccent.Readable(accent, View) : ArtAccent.VibrantReadable(accent, View, 4.5);
        var tint = ArtAccent.Mix(accent, Panel, IsLight ? 0.18 : 0.24);
        var ink = ArtAccent.Readable(ArtAccent.Mix(Hex("#000000"), accent, 0.82), accent);
        return new GameColors(accent, title, tint, accent, ink, ArtAccent.Readable(accent, tint));
    }
}

public sealed record GameColors(Color Accent, Color Title, Color Tint, Color Pill, Color Ink, Color TintText);
