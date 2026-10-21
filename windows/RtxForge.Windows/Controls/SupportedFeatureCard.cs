using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Controls;

public static class SupportedFeatureCard
{
    public static Border Create(OperationGameReview item, bool nr, bool mfg, string reason, double scale = 1)
    {
        var body = new StackPanel { Spacing = 10 * scale };
        body.Children.Add(new TextBlock { Text = item.Game.Name, FontSize = 15 * scale, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        var badges = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 * scale };
        badges.Children.Add(Badge("NR", nr, scale)); badges.Children.Add(Badge("MFG", mfg, scale)); body.Children.Add(badges);
        body.Children.Add(new TextBlock { Text = reason, TextWrapping = TextWrapping.Wrap, FontSize = 13 * scale, Opacity = .85 });
        body.Children.Add(new TextBlock { Text = item.Summary, TextWrapping = TextWrapping.Wrap, FontSize = 12 * scale, Opacity = .8 });
        return new Border { Child = body, Padding = new Thickness(16 * scale), CornerRadius = new CornerRadius(12 * scale), Background = new SolidColorBrush(global::Windows.UI.Color.FromArgb(20, 255, 255, 255)) };
    }
    static Border Badge(string label, bool available, double scale)
    {
        var colour = available ? global::Windows.UI.Color.FromArgb(255, 151, 215, 105) : global::Windows.UI.Color.FromArgb(255, 255, 151, 157);
        var brush = new SolidColorBrush(colour);
        var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 * scale };
        line.Children.Add(new FontIcon { Glyph = available ? "\uE73E" : "\uE733", FontSize = 12 * scale, Foreground = brush });
        line.Children.Add(new TextBlock { Text = label, FontSize = 12 * scale, FontWeight = FontWeights.SemiBold, Foreground = brush });
        var pill = new Border { Child = line, Padding = new Thickness(10 * scale, 5 * scale, 10 * scale, 5 * scale), CornerRadius = new CornerRadius(12 * scale), Background = new SolidColorBrush(global::Windows.UI.Color.FromArgb(24, colour.R, colour.G, colour.B)) };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(pill, label + (available ? " supported" : " unavailable"));
        return pill;
    }
}
