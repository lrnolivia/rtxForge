using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Services;
using Windows.UI;

namespace RtxForge.Windows;

public sealed record SampleBadgeColors(Color Surface, Color Ink, Color Stroke);

public static class SampleBadgeTheme
{
    public static SampleBadgeColors Light(Color hue)
    {
        var white = Color.FromArgb(255, 255, 255, 255);
        var surface = ArtAccent.Mix(hue, white, .12);
        var ink = ArtAccent.Readable(hue, surface, 4.6);
        return new(surface, ink, ArtAccent.Mix(ink, white, .35));
    }

    public static void AttachLight(Border pill, Color hue)
    {
        var background = pill.Background;
        var stroke = pill.BorderBrush;
        var thickness = pill.BorderThickness;
        var texts = Leaves(pill).OfType<TextBlock>().Select(x => (Element: x, x.Foreground)).ToArray();
        var icons = Leaves(pill).OfType<FontIcon>().Select(x => (Element: x, x.Foreground)).ToArray();
        var wasLight = false;
        void Refresh()
        {
            if (pill.ActualTheme == ElementTheme.Light)
            {
                var colors = Light(hue);
                pill.Background = new SolidColorBrush(colors.Surface);
                pill.BorderBrush = new SolidColorBrush(colors.Stroke);
                pill.BorderThickness = new Thickness(1);
                foreach (var (element, _) in texts) element.Foreground = new SolidColorBrush(colors.Ink);
                foreach (var (element, _) in icons) element.Foreground = new SolidColorBrush(colors.Ink);
                wasLight = true;
            }
            else if (wasLight)
            {
                pill.Background = background; pill.BorderBrush = stroke; pill.BorderThickness = thickness;
                foreach (var (element, foreground) in texts) element.Foreground = foreground;
                foreach (var (element, foreground) in icons) element.Foreground = foreground;
                wasLight = false;
            }
        }
        pill.Loaded += (_, _) => Refresh();
        pill.ActualThemeChanged += (_, _) => Refresh();
        Refresh();
    }

    static IEnumerable<UIElement> Leaves(UIElement root)
    {
        yield return root;
        if (root is Border { Child: { } child }) foreach (var leaf in Leaves(child)) yield return leaf;
        if (root is Panel panel) foreach (var item in panel.Children) foreach (var leaf in Leaves(item)) yield return leaf;
    }
}
