using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.Controls;

/// <summary>Static layout-matched card placeholders with a centered loading label.</summary>
public sealed class LibrarySkeleton : UserControl
{
    readonly Grid grid = new();
    readonly Brush fill, ink;
    string view;
    readonly double scale;
    double artScale = 1;
    int arrangedColumns;
    public LibrarySkeleton() : this("capsules") { }
    public LibrarySkeleton(string view, Brush? surface = null, double scale = 1)
    {
        this.view = view; this.scale = scale;
        IsHitTestVisible = false;
        AutomationProperties.SetAccessibilityView(grid, AccessibilityView.Raw);
        grid.ColumnSpacing = grid.RowSpacing = 16 * scale;
        fill = surface ?? (Brush)Application.Current.Resources["ControlFillColorSecondaryBrush"];
        ink = (Brush)Application.Current.Resources["ControlFillColorTertiaryBrush"];
        grid.Opacity = .45;
        grid.VerticalAlignment = VerticalAlignment.Top;
        var title = new TextBlock { Text = "Finding your games", FontSize = 24 * scale,
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, TextAlignment = TextAlignment.Center,
            TextWrapping = TextWrapping.Wrap, HorizontalAlignment = HorizontalAlignment.Center };
        AutomationProperties.SetLiveSetting(title, AutomationLiveSetting.Polite);
        var status = new StackPanel { Spacing = 16 * scale, HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(24 * scale) };
        status.Children.Add(title);
        var root = new Grid(); root.Children.Add(grid); root.Children.Add(status); Content = root;
        Rebuild();
        Loaded += (_, _) => ArrangeCards(ActualWidth);
        SizeChanged += (_, e) =>
        {
            Clip = new RectangleGeometry { Rect = new global::Windows.Foundation.Rect(0, 0, e.NewSize.Width, e.NewSize.Height) };
            ArrangeCards(e.NewSize.Width);
        };
    }

    public void Configure(string layout, double size = 1)
    {
        if (view == layout && Math.Abs(artScale - size) < .001) return;
        view = layout; artScale = size; Rebuild(); ArrangeCards(ActualWidth);
    }

    void Rebuild()
    {
        grid.Children.Clear(); arrangedColumns = 0;
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
    }
    void ArrangeCards(double width)
    {
        var preferred = (view == "capsules" ? 300 : 212) * scale * artScale;
        var columns = view == "list" ? 1 : Math.Clamp((int)((width + grid.ColumnSpacing) / (preferred + grid.ColumnSpacing)), 1, 8);
        if (columns != arrangedColumns)
        {
            arrangedColumns = columns;
            grid.ColumnDefinitions.Clear(); grid.RowDefinitions.Clear();
            for (var i = 0; i < columns; i++) grid.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            for (var i = 0; i < (grid.Children.Count + columns - 1) / columns; i++) grid.RowDefinitions.Add(new() { Height = GridLength.Auto });
        }
        for (var i = 0; i < grid.Children.Count; i++)
        {
            var card = (Border)grid.Children[i];
            var cardWidth = Math.Max(0, (width - grid.ColumnSpacing * (columns - 1)) / columns);
            var body = (StackPanel)card.Child;
            var lines = (StackPanel)body.Children[^1];
            ((Border)lines.Children[0]).Width = Math.Min(120 * scale, Math.Max(0, cardWidth - 24 * scale));
            ((Border)lines.Children[1]).Width = Math.Min(66 * scale, Math.Max(0, cardWidth - 24 * scale));
            Grid.SetRow(card, i / columns); Grid.SetColumn(card, i % columns);
            if (view != "list" && body.Children[0] is Border art)
                art.Height = cardWidth * (view == "posters" ? 1.5 : 215.0 / 460);
        }
    }
}
