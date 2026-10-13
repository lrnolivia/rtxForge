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

    /// <summary>Prototype --unit: 26px, 22px ≤1500 wide, 20px ≤1050, 46px ≥3000 (effective pixels).</summary>
    public double Unit { get; private set; } = 26;
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
            : width >= 3000 ? 46 : width <= 1050 ? 20 : width <= 1500 ? 22 : 26;
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
        Window = Hex("#242424"), View = Hex("#2a2a2a"), Panel = Hex("#303030"), Card = Hex("#383838"),
        Fg = Hex("#f2f2f2"), Muted = Hex("#c5c5c5"), Focus = Hex("#fafafa"),
        Danger = Hex("#ffc1c6"), DangerBg = Hex("#4b2328"), Line = Hex("#454545"),
        Active = Hex("#505050"), ActiveFg = Hex("#ffffff"), SegmentSelected = Hex("#575757"), RowFocus = Hex("#414141"),
        // The prototype's disabled #2a2a2a equals Dark's --view; one step up keeps disabled controls visible.
        Disabled = Hex("#333333"), DisabledFg = Hex("#9fa2a8"),
        DlssSurface = Hex("#474747"), DlssInk = Hex("#ffffff"), DlssBorder = Hex("#999999"),
    };

    static GmTheme Night() => new()
    {
        Name = "night",
        // --view: color-mix(window 50%, panel)
        Window = Hex("#080808"), View = Hex("#0f0f0f"), Panel = Hex("#171717"), Card = Hex("#252525"),
        Fg = Hex("#f2f2f2"), Muted = Hex("#c5c5c5"), Focus = Hex("#fafafa"),
        Danger = Hex("#ffc1c6"), DangerBg = Hex("#4b2328"), Line = Hex("#454545"),
        Active = Hex("#505050"), ActiveFg = Hex("#ffffff"), SegmentSelected = Hex("#575757"), RowFocus = Hex("#414141"),
        Disabled = Hex("#2a2a2a"), DisabledFg = Hex("#9fa2a8"),
        DlssSurface = Hex("#363636"), DlssInk = Hex("#f2f2f2"), DlssBorder = Hex("#888888"),
    };

    static GmTheme Light() => new()
    {
        Name = "light",
        Window = Hex("#f5f5f5"), View = Hex("#fafafa"), Panel = Hex("#ebebeb"), Card = Hex("#ffffff"),
        Fg = Hex("#222222"), Muted = Hex("#555555"), Focus = Hex("#222222"),
        Danger = Hex("#8b2029"), DangerBg = Hex("#f6dce0"), Line = Hex("#cecece"),
        Active = Hex("#d2d2d2"), ActiveFg = Hex("#222222"), SegmentSelected = Hex("#d4d4d4"), RowFocus = Hex("#dedede"),
        Disabled = Hex("#e5e5e5"), DisabledFg = Hex("#666666"),
        DlssSurface = Hex("#ffffff"), DlssInk = Hex("#222222"), DlssBorder = Hex("#707070"),
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
