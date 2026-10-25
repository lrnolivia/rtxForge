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
    public static double ArtworkStroke => GmMotionTokens.ArtworkStroke;
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
    public int HeaderDensity { get; private set; }

    /// <summary>Settings â€º UI scale: "auto" follows the breakpoints; a percentage scales from 150% = unit 26.</summary>
    public string Scale { get; set; } = "auto";

    public bool Resize(double width, double height)
    {
        var unit = Scale != "auto" && int.TryParse(Scale, out var percent)
            ? Math.Round(26.0 * percent / 150, 1)
            : Math.Round((width >= 3000 ? 46 : width <= 1050 ? 20 : width <= 1500 ? 22 : 26) * 130.0 / 150, 1);
        var compact = height <= 800 && width <= 2000;
        var designWidth = width * 26 / unit;
        var density = designWidth < 1320 ? 2 : designWidth < 1700 ? 1 : 0;
        if (unit == Unit && compact == Compact && density == HeaderDensity) return false;
        Unit = unit;
        Compact = compact;
        HeaderDensity = density;
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
        Window = Hex("#050505"), View = Hex("#0b0b0b"), Panel = Hex("#131313"), Card = Hex("#1c1c1c"),
        Fg = Hex("#dedede"), Muted = Hex("#b5b5b5"), Focus = Hex("#b0b0b0"),
        Danger = Hex("#f7bbc2"), DangerBg = Hex("#2e1920"), Line = Hex("#303030"),
        Active = Hex("#c9c9c9"), ActiveFg = Hex("#101010"), SegmentSelected = Hex("#bdbdbd"), RowFocus = Hex("#292929"),
        Disabled = Hex("#181818"), DisabledFg = Hex("#959595"),
        DlssSurface = Hex("#1b1b1b"), DlssInk = Hex("#dfdfdf"), DlssBorder = Hex("#444444"),
    };

    static GmTheme Light() => new()
    {
        Name = "light",
        Window = Hex("#e5e5e5"), View = Hex("#f4f4f4"), Panel = Hex("#e9e9e9"), Card = Hex("#ffffff"),
        Fg = Hex("#242424"), Muted = Hex("#535353"), Focus = Hex("#5c5c5c"),
        Danger = Hex("#7b2030"), DangerBg = Hex("#f5dfe3"), Line = Hex("#c6c6c6"),
        Active = Hex("#d1d1d1"), ActiveFg = Hex("#202020"), SegmentSelected = Hex("#d7d7d7"), RowFocus = Hex("#dddddd"),
        Disabled = Hex("#e3e3e3"), DisabledFg = Hex("#737373"),
        DlssSurface = Hex("#fafafa"), DlssInk = Hex("#343434"), DlssBorder = Hex("#7f7f7f"),
    };

    public static Color Hex(string hex) => ArtAccent.TryParse(hex, out var c) ? c : Microsoft.UI.Colors.Magenta;
    public static SolidColorBrush B(Color c, double opacity = 1) => new(c) { Opacity = opacity };
    /// <summary>Frosted card material; text and child controls remain fully opaque.</summary>
    readonly List<(WeakReference<AcrylicBrush> Brush, bool Navigation)> surfaces = [];
    public int CardOpacity { get; private set; } = 10;
    public int NavbarOpacity => Math.Max(0, CardOpacity - 15);
    public AcrylicBrush Surface(Color color, bool navigation = false)
    {
        var brush = new AcrylicBrush { TintColor = color,
            TintOpacity = (navigation ? NavbarOpacity : CardOpacity) / 100d, Opacity = 1, FallbackColor = color };
        surfaces.Add((new(brush), navigation));
        return brush;
    }

    public void SetCardOpacity(int percent)
    {
        CardOpacity = Math.Clamp(percent, 0, 100);
        for (var i = surfaces.Count - 1; i >= 0; i--)
        {
            if (surfaces[i].Brush.TryGetTarget(out var brush))
                brush.TintOpacity = (surfaces[i].Navigation ? NavbarOpacity : CardOpacity) / 100d;
            else surfaces.RemoveAt(i);
        }
    }

    public (AcrylicBrush Surface, SolidColorBrush Ink) Highlight(Color accent)
    {
        var surface = Surface(GlowHalo.Richer(accent));
        var ink = B(Fg);
        void Refresh() => ink.Color = ArtAccent.Readable(Fg, ArtAccent.Mix(surface.TintColor, Panel, surface.Opacity * surface.TintOpacity));
        surface.RegisterPropertyChangedCallback(AcrylicBrush.TintOpacityProperty, (_, _) => Refresh());
        surface.RegisterPropertyChangedCallback(AcrylicBrush.TintColorProperty, (_, _) => Refresh());
        Refresh();
        return (surface, ink);
    }

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
