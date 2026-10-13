using System.Runtime.InteropServices.WindowsRuntime;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;
using Windows.Graphics.Imaging;
using Windows.Storage.Streams;
using Windows.UI;

namespace RtxForge.Windows.Services;

/// <summary>
/// Per-game colors, computed exactly as rtxforge_gtk.py artwork_accent() does
/// for its .art-* CSS classes. Names follow the Linux variables.
/// </summary>
public sealed record AccentPalette(
    Color Color,          // color: card/row selection fill, rings, bars, sliders, accent buttons
    Color AccentFg,       // accent_fg: text on accent buttons / checked toggles
    Color AccentDark,     // accent_dark: text and checks on a selected row
    Color AccentShadow,   // accent_shadow: selected card test pill
    Color ButtonFg,       // button_fg: Details button on a selected card
    Color SelectedTitle,  // selected_title: card title while selected
    Color SourceBg,       // source_bg: source pill on a selected card
    Color SourceFg,       // source_fg
    Color NavAccent,      // nav_accent: selected section label
    Color HeroAccent,     // hero_accent: game banner title
    Color CardHoverTitle, // .game-card:hover .card-title
    Color RowHoverTitle,  // list row hover title
    Color BadgeFg,        // .review-badge
    Color BadgeBg)
{
    public SolidColorBrush Brush(Color c, double opacity = 1) => new(c) { Opacity = opacity };
    public SolidColorBrush AccentBrush => new(Color);
}

public static class ArtAccent
{
    // libadwaita dark palette values the Linux contrast checks run against,
    // matched to the Windows surfaces the colors sit on.
    static readonly Color Window = Color.FromArgb(255, 0x20, 0x20, 0x20);
    static readonly Color Card = Color.FromArgb(255, 0x2B, 0x2B, 0x2B);
    static readonly Color Sidebar = Color.FromArgb(255, 0x2C, 0x2C, 0x2C);
    static readonly Color White = Color.FromArgb(255, 255, 255, 255);
    /// <summary>Accent for games without usable artwork: a light neutral grey.</summary>
    public static readonly Color NoArtwork = Color.FromArgb(255, 0xB4, 0xB4, 0xB4);

    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(10) };
    static readonly Dictionary<string, Task<AccentPalette?>> Cache = [];

    /// <summary>
    /// Cached accent for a game: the custom color from Settings › game_accents
    /// when set, otherwise derived from artwork; muted for unsupported games.
    /// </summary>
    public static Task<AccentPalette?> ForGameAsync(Game game, string? custom = null)
    {
        custom ??= App.Main?.Settings.GameAccents.GetValueOrDefault(game.Id);
        var source = game.PosterPath ?? game.CapsulePath ?? game.HeroPath;
        var key = $"{game.Id}|{custom}|{game.Blocked}";
        if (!Cache.TryGetValue(key, out var task))
            Cache[key] = task = ComputeAsync(source, custom, game.Blocked);
        return task;
    }

    static async Task<AccentPalette?> ComputeAsync(string? source, string? custom, bool muted)
    {
        try
        {
            Color accent;
            if (custom is not null && TryParse(custom, out var picked)) accent = picked;
            else if (source is null) accent = NoArtwork; // neutral, never the brand green
            else
            {
                accent = await SignatureColorAsync(await LoadAsync(source)) ?? NoArtwork;
            }
            if (muted)
            {
                var (h, s, v) = ToHsv(accent);
                accent = FromHsv(h, s * 0.1, v);
            }
            return Palette(accent);
        }
        catch (Exception error) when (error is HttpRequestException or IOException or TaskCanceledException
                                      or UnauthorizedAccessException or ArgumentException or System.Runtime.InteropServices.COMException)
        {
            return null;
        }
    }

    public static async Task<byte[]> LoadAsync(string source) =>
        source.StartsWith("https://", StringComparison.OrdinalIgnoreCase)
            ? await Http.GetByteArrayAsync(source)
            : await File.ReadAllBytesAsync(source);

    /// <summary>
    /// The artwork's signature color, chosen perceptually (OKLab / OKLCH) rather
    /// than snapped to a fixed hue table:
    ///  1. Sample 64×64 and group pixels into 36 hue × 3 lightness clusters.
    ///  2. Score each cluster by area × vividness (chroma²), with a gentle
    ///     preference for mid lightness, so a vivid logo or key light beats a
    ///     large hazy sky or a dark backdrop.
    ///  3. Use the chroma-weighted average of the real pixels in the winner, so
    ///     two red posters get their own reds.
    ///  4. Keep the hue, bring lightness and chroma into a range that works as
    ///     a UI accent in every theme, and gamut-map back to sRGB.
    /// Returns null when the artwork has no meaningful color (greyscale art).
    /// </summary>
    public static async Task<Color?> SignatureColorAsync(byte[] bytes) =>
        Analyze(await SampleAsync(bytes)).Signature is { } s ? UiAccent(s) : null;

    /// <summary>A suggested accent for the picker (desktop and Game Mode).</summary>
    public sealed record AccentSuggestion(string Label, Color Color);

    /// <summary>
    /// Accent suggestions from one poster, most characteristic first:
    /// Signature (the automatic pick), Background (the largest tone, neutral or
    /// not), Alternate (the next vivid color in a clearly different hue), and
    /// Light / Deep variants of the signature. Near-duplicates are dropped.
    /// </summary>
    public static async Task<IReadOnlyList<AccentSuggestion>> SuggestionsAsync(byte[] bytes)
    {
        var analysis = Analyze(await SampleAsync(bytes));
        var list = new List<(string Label, (double L, double C, double H) Lch)>();
        if (analysis.Signature is { } sig)
        {
            var ui = ToLch(UiAccent(sig));
            list.Add(("Signature", ui));
            if (analysis.Background is { } bg) list.Add(("Background", BackgroundTone(bg)));
            if (analysis.Alternate is { } alt) list.Add(("Alternate", ToLch(UiAccent(alt))));
            list.Add(("Light", (0.88, Math.Min(ui.C, 0.10), ui.H)));
            list.Add(("Deep", (0.52, Math.Max(ui.C, 0.14), ui.H)));
        }
        else if (analysis.Background is { } bg) list.Add(("Background", BackgroundTone(bg)));

        var result = new List<AccentSuggestion>();
        foreach (var (label, (l, c, h)) in list)
        {
            if (result.Any(r => DeltaE(ToLch(r.Color), (l, c, h)) < 0.045)) continue;
            result.Add(new AccentSuggestion(label, FromOklch(l, c, h)));
        }
        return result;
    }

    /// <summary>The background tone as an accent: its own hue and chroma, lifted into a readable lightness.</summary>
    static (double L, double C, double H) BackgroundTone((double L, double A, double B) lab) =>
        (Math.Clamp(lab.L, 0.6, 0.9), Math.Sqrt(lab.A * lab.A + lab.B * lab.B), Math.Atan2(lab.B, lab.A));

    static Color UiAccent((double L, double A, double B) lab) =>
        // UI accent range: readable on dark and light surfaces, still the artwork's color.
        FromOklch(Math.Clamp(lab.L, 0.62, 0.84), Math.Clamp(Math.Sqrt(lab.A * lab.A + lab.B * lab.B), 0.09, 0.24), Math.Atan2(lab.B, lab.A));

    static (double L, double C, double H) ToLch(Color c)
    {
        var (l, a, b) = ToOklab(c.R, c.G, c.B);
        return (l, Math.Sqrt(a * a + b * b), Math.Atan2(b, a));
    }

    static double DeltaE((double L, double C, double H) x, (double L, double C, double H) y)
    {
        double ax = x.C * Math.Cos(x.H), bx = x.C * Math.Sin(x.H), ay = y.C * Math.Cos(y.H), by = y.C * Math.Sin(y.H);
        return Math.Sqrt((x.L - y.L) * (x.L - y.L) + (ax - ay) * (ax - ay) + (bx - by) * (bx - by));
    }

    static async Task<List<(double L, double A, double B)>> SampleAsync(byte[] bytes)
    {
        var (pixels, _, _) = await DecodeAsync(bytes, 64, 64);
        var samples = new List<(double, double, double)>(64 * 64);
        for (var i = 0; i + 3 < pixels.Length; i += 4)
            if (pixels[i + 3] >= 128) samples.Add(ToOklab(pixels[i + 2], pixels[i + 1], pixels[i]));
        return samples;
    }

    sealed record Analysis((double L, double A, double B)? Signature, (double L, double A, double B)? Alternate, (double L, double A, double B)? Background);

    static Analysis Analyze(List<(double L, double A, double B)> samples)
    {
        const int hues = 36, levels = 3;
        var score = new double[hues * levels];
        var sumL = new double[hues * levels];
        var sumA = new double[hues * levels];
        var sumB = new double[hues * levels];
        var weight = new double[hues * levels];
        // Background: area only, every pixel (neutrals by lightness; colors by 12 hues × 4 lightness).
        const int areaHues = 12, areaLevels = 4, neutralBins = 6;
        var area = new double[areaHues * areaLevels + neutralBins];
        var areaL = new double[area.Length];
        var areaA = new double[area.Length];
        var areaB = new double[area.Length];
        var chromatic = 0;
        foreach (var (l, a, b) in samples)
        {
            var c = Math.Sqrt(a * a + b * b);
            var hue = (Math.Atan2(b, a) / (2 * Math.PI) + 1) % 1;
            var abin = c < 0.04
                ? areaHues * areaLevels + Math.Min(neutralBins - 1, (int)(l * neutralBins))
                : (int)(hue * areaHues) % areaHues * areaLevels + Math.Min(areaLevels - 1, (int)(l * areaLevels));
            area[abin]++; areaL[abin] += l; areaA[abin] += a; areaB[abin] += b;

            if (c < 0.05 || l < 0.18 || l > 0.97) continue;    // neutral or near-neutral (cream, grey), near-black, blown out
            chromatic++;
            var bin = (int)(hue * hues) % hues * levels + Math.Min(levels - 1, (int)((l - 0.18) / (0.79 / levels)));
            var midness = 1 - Math.Abs(l - 0.65) * 0.9;              // favor colors that read as color
            score[bin] += c * c * midness;
            sumL[bin] += l * c; sumA[bin] += a * c; sumB[bin] += b * c; weight[bin] += c;
        }

        (double, double, double)? background = null;
        var top = Array.IndexOf(area, area.Max());
        if (area[top] > 0) background = (areaL[top] / area[top], areaA[top] / area[top], areaB[top] / area[top]);
        // Greyscale artwork keeps the neutral accent instead of inventing a hue.
        if (samples.Count == 0 || chromatic < samples.Count * 0.02) return new Analysis(null, null, background);

        // Merge each cluster with its hue neighbours before ranking, so a color
        // split across a bin edge is not undercounted.
        var merged = new double[score.Length];
        for (var bin = 0; bin < score.Length; bin++)
        {
            var h = bin / levels;
            merged[bin] = score[bin] + 0.5 * (score[(h + hues - 1) % hues * levels + bin % levels] + score[(h + 1) % hues * levels + bin % levels]);
        }
        (double, double, double)? Mean(int bin) => weight[bin] > 0 ? (sumL[bin] / weight[bin], sumA[bin] / weight[bin], sumB[bin] / weight[bin]) : null;
        var best = Enumerable.Range(0, merged.Length).MaxBy(i => merged[i]);
        if (merged[best] <= 0) return new Analysis(null, null, background);
        // Alternate: strongest cluster at least 4 hue steps (40°) away from the signature.
        int HueGap(int x, int y) { var d = Math.Abs(x / levels - y / levels); return Math.Min(d, hues - d); }
        var alternates = Enumerable.Range(0, merged.Length).Where(i => HueGap(i, best) >= 4 && merged[i] > merged[best] * 0.08);
        int? alternate = alternates.Any() ? alternates.MaxBy(i => merged[i]) : null;
        return new Analysis(Mean(best), alternate is { } a2 ? Mean(a2) : null, background);
    }
    static double Linear(byte channel)
    {
        var v = channel / 255.0;
        return v <= 0.04045 ? v / 12.92 : Math.Pow((v + 0.055) / 1.055, 2.4);
    }

    static (double L, double A, double B) ToOklab(byte r8, byte g8, byte b8)
    {
        double r = Linear(r8), g = Linear(g8), b = Linear(b8);
        var l = Math.Cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
        var m = Math.Cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
        var s = Math.Cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
        return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
                1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
                0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s);
    }

    /// <summary>OKLCH to sRGB, reducing chroma until the color is inside the sRGB gamut.</summary>
    static Color FromOklch(double l, double c, double h)
    {
        for (var chroma = c; ; chroma -= 0.005)
        {
            var (a, b) = (chroma * Math.Cos(h), chroma * Math.Sin(h));
            var lp = Math.Pow(l + 0.3963377774 * a + 0.2158037573 * b, 3);
            var mp = Math.Pow(l - 0.1055613458 * a - 0.0638541728 * b, 3);
            var sp = Math.Pow(l - 0.0894841775 * a - 1.2914855480 * b, 3);
            var r = 4.0767416621 * lp - 3.3077115913 * mp + 0.2309699292 * sp;
            var g = -1.2684380046 * lp + 2.6097574011 * mp - 0.3413193965 * sp;
            var bl = -0.0041960863 * lp - 0.7034186147 * mp + 1.7076147010 * sp;
            const double e = 0.0005;
            if ((r >= -e && r <= 1 + e && g >= -e && g <= 1 + e && bl >= -e && bl <= 1 + e) || chroma <= 0)
                return Color.FromArgb(255, Gamma(r), Gamma(g), Gamma(bl));
        }
    }

    static byte Gamma(double v)
    {
        v = Math.Clamp(v, 0, 1);
        var s = v <= 0.0031308 ? 12.92 * v : 1.055 * Math.Pow(v, 1 / 2.4) - 0.055;
        return (byte)Math.Round(s * 255);
    }

    /// <summary>BGRA8 pixels; scaled when width/height are given.</summary>
    public static async Task<(byte[] Pixels, uint Width, uint Height)> DecodeAsync(byte[] bytes, uint width = 0, uint height = 0)
    {
        using var stream = new InMemoryRandomAccessStream();
        await stream.WriteAsync(bytes.AsBuffer());
        stream.Seek(0);
        var decoder = await BitmapDecoder.CreateAsync(stream);
        var transform = new BitmapTransform { InterpolationMode = BitmapInterpolationMode.Linear };
        if (width > 0) { transform.ScaledWidth = width; transform.ScaledHeight = height; }
        else { width = decoder.OrientedPixelWidth; height = decoder.OrientedPixelHeight; }
        var data = await decoder.GetPixelDataAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Straight, transform,
            ExifOrientationMode.IgnoreExifOrientation, ColorManagementMode.DoNotColorManage);
        return (data.DetachPixelData(), width, height);
    }

    /// <summary>artwork_accent(): every derived color, line for line.</summary>
    public static AccentPalette Palette(Color color)
    {
        var (fh, fs, fv) = ToHsv(color);
        // Linear (not gamma) luminance, as the Linux code computes it.
        var luminance = 0.2126 * color.R / 255 + 0.7152 * color.G / 255 + 0.0722 * color.B / 255;
        var accentFg = luminance >= 0.48 ? FromHsv(fh, Math.Clamp(fs * 1.05, 0.55, 1.0), 0.20) : White;
        var accentDark = FromHsv(fh, Math.Clamp(fs * 1.12, 0.78, 1.0), Math.Clamp(fv * 0.42, 0.20, 0.34));
        if (fs < 0.08)
        {
            accentFg = luminance >= 0.48 ? Color.FromArgb(255, 0x33, 0x33, 0x33) : White;
            var gray = (byte)Math.Round(Math.Clamp(fv * 0.42, 0.20, 0.34) * 255);
            accentDark = Color.FromArgb(255, gray, gray, gray);
        }

        var navAccent = Readable(color, Mix(color, Sidebar, 0.10));
        var accentShadow = accentDark;
        accentFg = Readable(accentFg, color);
        accentDark = Readable(accentDark, color);
        var buttonFg = Readable(accentDark, Mix(White, color, 0.44));
        var selectedTitle = accentDark.R + accentDark.G + accentDark.B > 600 ? Mix(White, color, 0.88) : accentDark;
        var sourceBg = Mix(White, color, 0.26);
        var sourceFg = Readable(accentShadow, sourceBg);
        var heroAccent = VibrantReadable(color, Window, 3.0);
        return new AccentPalette(color, accentFg, accentDark, accentShadow, buttonFg, selectedTitle, sourceBg, sourceFg,
            navAccent, heroAccent,
            CardHoverTitle: Readable(Mix(White, color, 0.78), Card),
            RowHoverTitle: Readable(color, Card),
            BadgeFg: Readable(color, Card),
            BadgeBg: Mix(color, Card, 0.10));
    }

    public static bool TryParse(string hex, out Color color)
    {
        color = default;
        var raw = hex.TrimStart('#');
        if (raw.Length != 6 || !int.TryParse(raw, System.Globalization.NumberStyles.HexNumber, null, out var value)) return false;
        color = Color.FromArgb(255, (byte)(value >> 16), (byte)(value >> 8), (byte)value);
        return true;
    }

    public static string Hex(Color c) => $"#{c.R:x2}{c.G:x2}{c.B:x2}";

    public static Color Mix(Color foreground, Color background, double opacity) => Color.FromArgb(255,
        (byte)Math.Round(foreground.R * opacity + background.R * (1 - opacity)),
        (byte)Math.Round(foreground.G * opacity + background.G * (1 - opacity)),
        (byte)Math.Round(foreground.B * opacity + background.B * (1 - opacity)));

    // ---------- ui_colors.py ----------

    static double Channel(byte c)
    {
        var v = c / 255.0;
        return v <= 0.04045 ? v / 12.92 : Math.Pow((v + 0.055) / 1.055, 2.4);
    }

    public static double Luminance(Color c) => 0.2126 * Channel(c.R) + 0.7152 * Channel(c.G) + 0.0722 * Channel(c.B);

    public static double Contrast(Color a, Color b)
    {
        var (x, y) = (Luminance(a), Luminance(b));
        return (Math.Max(x, y) + 0.05) / (Math.Min(x, y) + 0.05);
    }

    /// <summary>Nearest passing lightness, keeping hue and saturation.</summary>
    public static Color Readable(Color color, Color background, double minimum = 4.5)
    {
        if (Contrast(color, background) >= minimum) return color;
        var (h, l, s) = ToHls(color);
        Color? best = null;
        var bestDistance = double.MaxValue;
        foreach (var endpoint in new[] { 0.0, 1.0 })
        {
            if (Contrast(FromHls(h, endpoint, s), background) < minimum) continue;
            double low = 0, high = 1;
            for (var i = 0; i < 24; i++)
            {
                var amount = (low + high) / 2;
                if (Contrast(FromHls(h, l + (endpoint - l) * amount, s), background) >= minimum) high = amount;
                else low = amount;
            }
            var distance = Math.Abs(endpoint - l) * high;
            if (distance < bestDistance) { bestDistance = distance; best = FromHls(h, l + (endpoint - l) * high, s); }
        }
        if (best is { } found) return found;
        var black = Color.FromArgb(255, 0, 0, 0);
        var white = Color.FromArgb(255, 255, 255, 255);
        return Contrast(black, background) >= Contrast(white, background) ? black : white;
    }

    /// <summary>Prefer lifting value over washing out saturation for large accent text.</summary>
    public static Color VibrantReadable(Color color, Color background, double minimum = 3.0)
    {
        if (Contrast(color, background) >= minimum) return color;
        var (h, s, v) = ToHsv(color);
        for (var step = 1; step <= 100; step++)
        {
            var candidate = FromHsv(h, s, v + (1 - v) * step / 100.0);
            if (Contrast(candidate, background) >= minimum) return candidate;
        }
        return Readable(color, background, minimum);
    }

    // ---------- color space helpers ----------

    static (double H, double S, double V) ToHsv(Color c)
    {
        double r = c.R / 255.0, g = c.G / 255.0, b = c.B / 255.0;
        double max = Math.Max(r, Math.Max(g, b)), min = Math.Min(r, Math.Min(g, b)), d = max - min;
        double h = 0;
        if (d > 0)
        {
            if (max == r) h = ((g - b) / d % 6 + 6) % 6;
            else if (max == g) h = (b - r) / d + 2;
            else h = (r - g) / d + 4;
            h /= 6;
        }
        return (h, max == 0 ? 0 : d / max, max);
    }

    static Color FromHsv(double h, double s, double v)
    {
        h = (h % 1 + 1) % 1 * 6;
        var i = (int)Math.Floor(h);
        var f = h - i;
        double p = v * (1 - s), q = v * (1 - s * f), t = v * (1 - s * (1 - f));
        var (r, g, b) = i switch
        {
            0 => (v, t, p), 1 => (q, v, p), 2 => (p, v, t),
            3 => (p, q, v), 4 => (t, p, v), _ => (v, p, q),
        };
        return Color.FromArgb(255, (byte)Math.Round(r * 255), (byte)Math.Round(g * 255), (byte)Math.Round(b * 255));
    }

    static (double H, double L, double S) ToHls(Color c)
    {
        double r = c.R / 255.0, g = c.G / 255.0, b = c.B / 255.0;
        double max = Math.Max(r, Math.Max(g, b)), min = Math.Min(r, Math.Min(g, b));
        var l = (max + min) / 2;
        if (max == min) return (0, l, 0);
        var d = max - min;
        var s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        var (h, _, _) = ToHsv(c);
        return (h, l, s);
    }

    static Color FromHls(double h, double l, double s)
    {
        l = Math.Clamp(l, 0, 1);
        if (s == 0) { var gray = (byte)Math.Round(l * 255); return Color.FromArgb(255, gray, gray, gray); }
        var q = l < 0.5 ? l * (1 + s) : l + s - l * s;
        var p = 2 * l - q;
        double Hue(double t)
        {
            t = (t % 1 + 1) % 1;
            return t < 1.0 / 6 ? p + (q - p) * 6 * t : t < 0.5 ? q : t < 2.0 / 3 ? p + (q - p) * (2.0 / 3 - t) * 6 : p;
        }
        return Color.FromArgb(255, (byte)Math.Round(Hue(h + 1.0 / 3) * 255), (byte)Math.Round(Hue(h) * 255), (byte)Math.Round(Hue(h - 1.0 / 3) * 255));
    }
}