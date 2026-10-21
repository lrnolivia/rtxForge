using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.Controls;

/// <summary>Fixed-size information action; diagnostics never expand the surrounding row.</summary>
internal static class TechnicalDetails
{
    public static Button Create(string text, double scale = 1, Action? show = null)
    {
        var button = new Button
        {
            Content = new FontIcon { Glyph = "", FontSize = 16 * scale },
            Width = 36 * scale, Height = 36 * scale, MinWidth = 0, MinHeight = 0,
            Padding = new Thickness(6 * scale), CornerRadius = new CornerRadius(18 * scale),
            Background = null, BorderThickness = new Thickness(0), VerticalAlignment = VerticalAlignment.Center,
        };
        AutomationProperties.SetName(button, "Show details");
        ToolTipService.SetToolTip(button, "Details");
        if (show is not null) button.Click += (_, _) => show();
        else
        {
            var details = new ScrollViewer
            {
                HorizontalScrollMode = ScrollMode.Disabled, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Content = new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true,
                    FontSize = 12, FontFamily = new FontFamily("Cascadia Mono, Consolas") },
            };
            var body = new StackPanel { Spacing = 12 };
            body.Children.Add(new TextBlock { Text = "Details", FontWeight = Microsoft.UI.Text.FontWeights.SemiBold });
            body.Children.Add(details);
            var popup = new Flyout { Content = body, Placement = FlyoutPlacementMode.BottomEdgeAlignedRight };
            button.Click += (_, _) =>
            {
                var size = button.XamlRoot?.Size ?? new global::Windows.Foundation.Size(640, 480);
                details.Width = Math.Max(200, Math.Min(480, size.Width - 96));
                details.MaxHeight = Math.Max(120, Math.Min(340, size.Height - 160));
                popup.ShowAt(button);
            };
        }
        return button;
    }
}
