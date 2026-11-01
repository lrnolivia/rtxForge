using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Controls;

/// <summary>Small screen diagrams showing where each overlay layout lives.</summary>
public sealed class OverlayLayoutPicker : UserControl
{
    public int SelectedIndex { get; private set; }
    public event EventHandler? SelectionChanged;

    public OverlayLayoutPicker(string selected, bool card = true)
    {
        var root = new StackPanel { Spacing = 12 };
        root.Children.Add(new TextBlock { Text = "Layout" });
        var choices = new Grid { ColumnSpacing = 12 };
        var group = "overlay-layout-" + Guid.NewGuid();
        string[] captions = ["Side Panel", "Advanced", "Bar"];
        SelectedIndex = Math.Max(0, Array.IndexOf(GlassAppearance.Layouts, selected));
        for (var i = 0; i < captions.Length; i++)
        {
            choices.ColumnDefinitions.Add(new ColumnDefinition());
            var body = new StackPanel { Spacing = 8, HorizontalAlignment = HorizontalAlignment.Stretch };
            body.Children.Add(new Viewbox { Child = Diagram(i), Height = 52, Stretch = Stretch.Uniform });
            body.Children.Add(new TextBlock { Text = captions[i], TextWrapping = TextWrapping.Wrap, TextAlignment = TextAlignment.Center, FontSize = 14 });
            var button = new RadioButton { Content = body, GroupName = group, IsChecked = i == SelectedIndex,
                Style = Prefs.GetStyle("ForgeSegmentStyle"), Padding = new Thickness(10, 12, 10, 12), HorizontalAlignment = HorizontalAlignment.Stretch };
            button.SetValue(AutomationProperties.NameProperty, captions[i]);
            var index = i;
            button.Checked += (_, _) => { SelectedIndex = index; SelectionChanged?.Invoke(this, EventArgs.Empty); };
            Grid.SetColumn(button, i); choices.Children.Add(button);
        }
        root.Children.Add(choices);
        Content = card ? new Border { Style = Prefs.GetStyle("ForgeSettingsCardStyle"), Child = root } : root;
    }

    static Canvas Diagram(int layout)
    {
        var canvas = new Canvas { Width = 180, Height = 104, IsHitTestVisible = false };
        Brush Brush(string key) => (Brush)Application.Current.Resources[key];
        void Shape(double x, double y, double width, double height, string resource, double opacity = 1, double radius = 3)
        {
            var shape = new Border { Width = width, Height = height, Background = Brush(resource), Opacity = opacity, CornerRadius = new CornerRadius(radius) };
            Canvas.SetLeft(shape, x); Canvas.SetTop(shape, y); canvas.Children.Add(shape);
        }
        Shape(0, 0, 180, 104, "ControlFillColorSecondaryBrush", radius: 7);
        if (layout == 0)
        {
            Shape(12, 10, 53, 84, "TextFillColorPrimaryBrush", .15, 5);
            Shape(20, 18, 26, 4, "AccentFillColorDefaultBrush");
            for (var row = 0; row < 3; row++) Shape(20, 30 + row * 18, 37, 12, "TextFillColorPrimaryBrush", .22);
            Shape(72, 39, 34, 43, "TextFillColorPrimaryBrush", .11, 5);
        }
        else if (layout == 1)
        {
            Shape(26, 16, 128, 72, "TextFillColorPrimaryBrush", .15, 5);
            Shape(34, 24, 25, 4, "AccentFillColorDefaultBrush");
            for (var row = 0; row < 4; row++) Shape(34, 37 + row * 10, 25, 4, "TextFillColorPrimaryBrush", .25);
            Shape(69, 25, 76, 19, "TextFillColorPrimaryBrush", .22);
            Shape(69, 51, 34, 27, "TextFillColorPrimaryBrush", .17);
            Shape(110, 51, 35, 27, "TextFillColorPrimaryBrush", .17);
        }
        else
        {
            Shape(14, 74, 152, 19, "TextFillColorPrimaryBrush", .18, 5);
            Shape(23, 81, 26, 4, "AccentFillColorDefaultBrush");
            for (var col = 0; col < 3; col++) Shape(61 + col * 31, 80, 24, 6, "TextFillColorPrimaryBrush", .28);
            Shape(92, 27, 55, 39, "TextFillColorPrimaryBrush", .14, 5);
            Shape(102, 35, 26, 4, "AccentFillColorDefaultBrush", .7);
            Shape(102, 46, 35, 11, "TextFillColorPrimaryBrush", .22);
        }
        return canvas;
    }
}
