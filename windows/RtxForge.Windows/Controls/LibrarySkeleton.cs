using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.Controls;

/// <summary>Static, decorative placeholders: no polling, image loads or animation loop.</summary>
public sealed class LibrarySkeleton : UserControl
{
    readonly Grid grid = new();
    readonly string view;
    readonly double scale;
    int arrangedColumns;
    public LibrarySkeleton() : this("capsules") { }
    public LibrarySkeleton(string view, Brush? surface = null, double scale = 1)
    {
        this.view = view; this.scale = scale;
        IsHitTestVisible = false;
        AutomationProperties.SetAccessibilityView(this, AccessibilityView.Raw);
        grid.ColumnSpacing = grid.RowSpacing = 16 * scale;
        var fill = surface ?? (Brush)Application.Current.Resources["ControlFillColorSecondaryBrush"];
        var ink = (Brush)Application.Current.Resources["ControlFillColorTertiaryBrush"];
        for (var i = 0; i < 8; i++)
        {
            var body = new StackPanel { Spacing = 10 * scale };
            if (view != "list") body.Children.Add(new Border
            { Height = (view == "posters" ? 240 : 124) * scale, Background = fill, CornerRadius = new CornerRadius(10 * scale) });
            var lines = new StackPanel { Spacing = 8 * scale, Padding = new Thickness(12 * scale) };
            lines.Children.Add(new Border { Width = 120 * scale, Height = 12 * scale, Background = ink,
                HorizontalAlignment = HorizontalAlignment.Left, CornerRadius = new CornerRadius(4) });
            lines.Children.Add(new Border { Width = 66 * scale, Height = 9 * scale, Background = ink,
                HorizontalAlignment = HorizontalAlignment.Left, CornerRadius = new CornerRadius(4) });
            body.Children.Add(lines);
            grid.Children.Add(new Border { Child = body, Background = fill, CornerRadius = new CornerRadius(12 * scale) });
        }
        Content = grid;
        Loaded += (_, _) => ArrangeCards(ActualWidth);
        SizeChanged += (_, e) => ArrangeCards(e.NewSize.Width);
    }
    void ArrangeCards(double width)
    {
        var columns = view == "list" ? 1 : Math.Clamp((int)((width + grid.ColumnSpacing) / (220 * scale + grid.ColumnSpacing)), 1, 5);
        if (columns == arrangedColumns) return;
        arrangedColumns = columns;
        grid.ColumnDefinitions.Clear(); grid.RowDefinitions.Clear();
        for (var i = 0; i < columns; i++) grid.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        for (var i = 0; i < (grid.Children.Count + columns - 1) / columns; i++) grid.RowDefinitions.Add(new() { Height = GridLength.Auto });
        for (var i = 0; i < grid.Children.Count; i++)
        { Grid.SetRow((FrameworkElement)grid.Children[i], i / columns); Grid.SetColumn((FrameworkElement)grid.Children[i], i % columns); }
    }
}
