using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Controls;

public static class SupportedFeatureCard
{
    public static Border Create(OperationGameReview item, bool nr, bool mfg, string reason)
    {
        var body = new StackPanel { Spacing = 10 };
        body.Children.Add(new TextBlock { Text = item.Game.Name, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        var badges = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        badges.Children.Add(Badge("NR", nr)); badges.Children.Add(Badge("MFG", mfg)); body.Children.Add(badges);
        body.Children.Add(new TextBlock { Text = reason, TextWrapping = TextWrapping.Wrap, FontSize = 13, Opacity = .85 });
        body.Children.Add(new TextBlock { Text = item.Summary, TextWrapping = TextWrapping.Wrap, FontSize = 12, Opacity = .8 });
        return new Border { Child = body, Padding = new Thickness(16), CornerRadius = new CornerRadius(12), Background = new SolidColorBrush(global::Windows.UI.Color.FromArgb(20, 255, 255, 255)) };
    }
    static Border Badge(string label, bool available)
    {
        var colour = available ? global::Windows.UI.Color.FromArgb(255, 151, 215, 105) : global::Windows.UI.Color.FromArgb(255, 255, 151, 157);
        var brush = new SolidColorBrush(colour);
        var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
        line.Children.Add(new FontIcon { Glyph = available ? "\uE73E" : "\uE733", FontSize = 12, Foreground = brush });
        line.Children.Add(new TextBlock { Text = label, FontSize = 12, FontWeight = FontWeights.SemiBold, Foreground = brush });
        var pill = new Border { Child = line, Padding = new Thickness(10, 5, 10, 5), CornerRadius = new CornerRadius(12), Background = new SolidColorBrush(global::Windows.UI.Color.FromArgb(24, colour.R, colour.G, colour.B)) };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(pill, label + (available ? " supported" : " unavailable"));
        return pill;
    }
}
