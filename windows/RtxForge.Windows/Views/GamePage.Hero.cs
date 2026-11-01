using System.Runtime.InteropServices.WindowsRuntime;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Services;
using Windows.Graphics.Imaging;
using Windows.UI;

namespace RtxForge.Windows.Views;

public sealed partial class GamePage
{
    bool heroPresentationAttached, applyingHeroPresentation;
    string? sampledHeroSource;
    Color? sampledHeroBackground;

    void OnHeroPresentationLoaded(object sender, RoutedEventArgs args)
    {
        HeroImage.FadeStart = .46f;
        if (!heroPresentationAttached)
        {
            heroPresentationAttached = true;
            // Palette and layout updates remain owned by the existing page. Observe
            // their completed values so the same presentation works in both hosts.
            TitleText.RegisterPropertyChangedCallback(TextBlock.ForegroundProperty, (_, _) => ApplyHeroPresentation());
            TitleText.RegisterPropertyChangedCallback(TextBlock.TextProperty, (_, _) => { _ = SampleHeroPresentationAsync(); });
            HeroBanner.SizeChanged += (_, _) => ApplyHeroPresentation();
            ActualThemeChanged += (_, _) => ApplyHeroPresentation();
        }
        ApplyHeroPresentation();
        _ = SampleHeroPresentationAsync();
    }

    static Color HeroMix(Color accent, Color neutral, double amount) => Color.FromArgb(255,
        (byte)Math.Round(accent.R * amount + neutral.R * (1 - amount)),
        (byte)Math.Round(accent.G * amount + neutral.G * (1 - amount)),
        (byte)Math.Round(accent.B * amount + neutral.B * (1 - amount)));

    void ApplyHeroPresentation()
    {
        if (applyingHeroPresentation || game is null) return;
        applyingHeroPresentation = true;
        try
        {
            var light = ActualTheme == ElementTheme.Light;
            var accent = gamePalette?.Color ?? ArtAccent.NoArtwork;
            var card = HeroMix(accent, light ? Color.FromArgb(255, 246, 244, 239) : Color.FromArgb(255, 37, 43, 49), light ? .12 : .24);
            var ink = ArtAccent.Readable(HeroMix(accent, light ? Color.FromArgb(255, 22, 28, 34) : Color.FromArgb(255, 255, 253, 247), light ? .32 : .14), card);
            HeroInfoCard.Background = new AcrylicBrush
            {
                TintColor = card, TintOpacity = .88,
                FallbackColor = card
            };
            HeroInfoCard.BorderBrush = new SolidColorBrush(ink) { Opacity = light ? .10 : .14 };
            var brush = new SolidColorBrush(ink);
            MetaText.Foreground = SummaryText.Foreground = SourceBadge.Foreground = OsBadgeText.Foreground = TestBadgeText.Foreground = brush;
            OsBadgeIcons.Foreground = TestBadgeIcon.Foreground = brush;
            var background = sampledHeroBackground ?? (light ? Color.FromArgb(255, 235, 232, 226) : Color.FromArgb(255, 55, 60, 65));
            TitleText.Foreground = new SolidColorBrush(ArtAccent.Readable(accent, background, 3.1));
            if (heroProgress < .05 && PosterFrame.Visibility == Visibility.Visible)
            {
                PosterFrame.Height = Math.Round(Math.Clamp(heroExpandedHeight * .52, 156, 244));
                PosterFrame.Width = Math.Round(PosterFrame.Height * 2 / 3);
            }
        }
        finally { applyingHeroPresentation = false; }
    }

    async Task SampleHeroPresentationAsync()
    {
        var path = game?.HeroPath ?? game?.CapsulePath;
        if (path == sampledHeroSource) return;
        sampledHeroSource = path;
        sampledHeroBackground = null;
        ApplyHeroPresentation();
        // Analyze the same saved or cached/CDN image displayed by the page.
        // Remote preview artwork needs the same contrast adaptation as local art.
        if (path is null || (!File.Exists(path) && !path.StartsWith("https://", StringComparison.OrdinalIgnoreCase))) return;
        try
        {
            var color = await Task.Run(async () =>
            {
                if (File.Exists(path) && new FileInfo(path).Length > 16 * 1024 * 1024) return (Color?)null;
                var bytes = await ArtAccent.LoadAsync(path);
                if (bytes.Length > 16 * 1024 * 1024) return (Color?)null;
                using var stream = new MemoryStream(bytes);
                var decoder = await BitmapDecoder.CreateAsync(stream.AsRandomAccessStream());
                var transform = new BitmapTransform { ScaledWidth = 64, ScaledHeight = 32 };
                var pixels = (await decoder.GetPixelDataAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Straight, transform,
                    ExifOrientationMode.RespectExifOrientation, ColorManagementMode.ColorManageToSRgb)).DetachPixelData();
                long red = 0, green = 0, blue = 0, count = 0;
                // The title occupies the middle-left of the expanded hero.
                for (var y = 12; y < 25; y++) for (var x = 0; x < 35; x++)
                {
                    var i = (y * 64 + x) * 4;
                    if (pixels[i + 3] < 128) continue;
                    blue += pixels[i]; green += pixels[i + 1]; red += pixels[i + 2]; count++;
                }
                return count == 0 ? (Color?)null : Color.FromArgb(255, (byte)(red / count), (byte)(green / count), (byte)(blue / count));
            });
            if (sampledHeroSource != path || !IsLoaded) return;
            sampledHeroBackground = color;
            ApplyHeroPresentation();
        }
        catch { /* A missing or replaced image retains the theme-safe palette. */ }
    }
}
