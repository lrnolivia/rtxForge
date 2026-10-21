using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.Controls;

/// <summary>A small disclosure inside a review row, with bounded, selectable diagnostic text.</summary>
internal static class TechnicalDetails
{
    public static UIElement Create(string text)
    {
        var details = new ScrollViewer
        {
            Visibility = Visibility.Collapsed, MaxHeight = 180, HorizontalScrollMode = ScrollMode.Disabled,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            Content = new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true,
                FontSize = 12, FontFamily = new FontFamily("Cascadia Mono, Consolas"), Margin = new Thickness(0, 4, 0, 8) },
        };
        var chevron = new FontIcon { Glyph = "", FontSize = 10 };
        var label = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
        label.Children.Add(chevron);
        label.Children.Add(new TextBlock { Text = "Technical details", FontSize = 12 });
        var toggle = new Button { Content = label, Background = null, BorderThickness = new Thickness(0),
            MinHeight = 28, Padding = new Thickness(0, 4, 4, 4), HorizontalAlignment = HorizontalAlignment.Left };
        AutomationProperties.SetName(toggle, "Technical details, collapsed");
        toggle.Click += (_, _) =>
        {
            var expanded = details.Visibility != Visibility.Visible;
            details.Visibility = expanded ? Visibility.Visible : Visibility.Collapsed;
            chevron.Glyph = expanded ? "" : "";
            AutomationProperties.SetName(toggle, "Technical details, " + (expanded ? "expanded" : "collapsed"));
        };
        return new StackPanel { Spacing = 2, Margin = new Thickness(0, 4, 0, 0), Children = { toggle, details } };
    }
}
