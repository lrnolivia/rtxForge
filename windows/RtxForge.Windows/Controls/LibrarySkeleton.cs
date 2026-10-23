using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.Controls;

/// <summary>Static layout-matched card placeholders with a loading toast at the bottom.</summary>
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
        // A toast at the bottom (MainWindow's ToastHost surface), not a title over the cards.
        var title = new TextBlock { Text = "Finding your games…", FontSize = 14 * scale, VerticalAlignment = VerticalAlignment.Center };
        AutomationProperties.SetLiveSetting(title, AutomationLiveSetting.Polite);
        var message = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12 * scale };
        message.Children.Add(new ProgressRing { IsActive = true, Width = 16 * scale, Height = 16 * scale });
        message.Children.Add(title);
        var status = new Border
        {
            Child = message, Padding = new Thickness(16 * scale, 10 * scale, 18 * scale, 10 * scale),
            Background = (Brush)Application.Current.Resources["SolidBackgroundFillColorTertiaryBrush"],
            CornerRadius = (CornerRadius)Application.Current.Resources["OverlayCornerRadius"],
            HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Bottom,
            Margin = new Thickness(24 * scale), Translation = new System.Numerics.Vector3(0, 0, 32), Shadow = new ThemeShadow(),
        };
        var root = new Grid(); root.Children.Add(grid); root.Children.Add(status); Content = root;
        Rebuild();
        Loaded += (_, _) => ArrangeCards(ActualWidth, ActualHeight);
        SizeChanged += (_, e) =>
        {
            Clip = new RectangleGeometry { Rect = new global::Windows.Foundation.Rect(0, 0, e.NewSize.Width, e.NewSize.Height) };
            ArrangeCards(e.NewSize.Width, e.NewSize.Height);
        };
    }

    public void Configure(string layout, double size = 1)
    {
        if (view == layout && Math.Abs(artScale - size) < .001) return;
        view = layout; artScale = size; Rebuild(); ArrangeCards(ActualWidth, ActualHeight);
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
    void ArrangeCards(double width, double height)
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
        var cardWidth = Math.Max(0, (width - grid.ColumnSpacing * (columns - 1)) / columns);
        var artHeight = view == "list" ? 0 : cardWidth * (view == "posters" ? 1.5 : 215.0 / 460);
        var cardHeight = artHeight + (view == "list" ? 53 : 63) * scale;
        var fullRows = Math.Max(0, (int)((height + grid.RowSpacing) / (cardHeight + grid.RowSpacing)));
        for (var i = 0; i < grid.Children.Count; i++)
        {
            var card = (Border)grid.Children[i];
            // Placeholders are a static loading preview, not scrollable content.
            // Show complete rows instead of cutting a card through its artwork.
            card.Visibility = i / columns < fullRows ? Visibility.Visible : Visibility.Collapsed;
            var body = (StackPanel)card.Child;
            var lines = (StackPanel)body.Children[^1];
            ((Border)lines.Children[0]).Width = Math.Min(120 * scale, Math.Max(0, cardWidth - 24 * scale));
            ((Border)lines.Children[1]).Width = Math.Min(66 * scale, Math.Max(0, cardWidth - 24 * scale));
            Grid.SetRow(card, i / columns); Grid.SetColumn(card, i % columns);
            if (view != "list" && body.Children[0] is Border art)
                art.Height = artHeight;
        }
    }
}
