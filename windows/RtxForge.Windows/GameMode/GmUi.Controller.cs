using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace RtxForge.Windows.GameMode;

public sealed partial class GmUi
{
    /// <summary>One vector button vocabulary in the footer and the controls guide.</summary>
    public UIElement ControllerKey(string family, string action, double em = .85)
    {
        if (action == "shoulders")
        {
            var pair = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(6) };
            pair.Children.Add(ControllerKey(family, "previous", em));
            pair.Children.Add(ControllerKey(family, "next", em));
            return pair;
        }
        var prompt = ControllerPrompt.For(family, action);
        var ink = GmTheme.B(GmTheme.Hex(prompt.Color));
        var canvas = new Canvas { Width = 32, Height = 32 };
        var outline = new Ellipse { Width = 30, Height = 30, Fill = GmTheme.B(GmTheme.Hex("#24272c")), Stroke = ink, StrokeThickness = 1.6 };
        Canvas.SetLeft(outline, 1); Canvas.SetTop(outline, 1); canvas.Children.Add(outline);
        void Line(double x1, double y1, double x2, double y2) => canvas.Children.Add(new Line
        { X1 = x1, Y1 = y1, X2 = x2, Y2 = y2, Stroke = ink, StrokeThickness = 2, StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round });
        void Box(double x, double y, double width, double height)
        {
            var shape = new Rectangle { Width = width, Height = height, Stroke = ink, StrokeThickness = 1.8, RadiusX = 1, RadiusY = 1 };
            Canvas.SetLeft(shape, x); Canvas.SetTop(shape, y); canvas.Children.Add(shape);
        }
        switch (prompt.Shape)
        {
            case "cross": Line(10, 10, 22, 22); Line(22, 10, 10, 22); break;
            case "circle":
                var ring = new Ellipse { Width = 16, Height = 16, Stroke = ink, StrokeThickness = 2 };
                Canvas.SetLeft(ring, 8); Canvas.SetTop(ring, 8); canvas.Children.Add(ring); break;
            case "square": Box(9, 9, 14, 14); break;
            case "triangle": Line(16, 8, 25, 23); Line(25, 23, 7, 23); Line(7, 23, 16, 8); break;
            case "menu": Line(10, 11, 22, 11); Line(10, 16, 22, 16); Line(10, 21, 22, 21); break;
            case "view": Box(9, 10, 10, 9); Box(13, 14, 10, 9); break;
            case "plus": Line(16, 9, 16, 23); Line(9, 16, 23, 16); break;
            case "minus": Line(9, 16, 23, 16); break;
            case "dpad": Line(16, 8, 16, 24); Line(8, 16, 24, 16); break;
            default:
                if (prompt.Shape.StartsWith("position"))
                {
                    var selected = int.Parse(prompt.Shape[^1..]);
                    (double X, double Y)[] positions = [(16, 23), (23, 16), (9, 16), (16, 9)];
                    for (var index = 0; index < positions.Length; index++)
                    {
                        var dot = new Ellipse { Width = 5, Height = 5, Stroke = ink, StrokeThickness = 1,
                            Fill = index == selected ? ink : null };
                        Canvas.SetLeft(dot, positions[index].X - 2.5); Canvas.SetTop(dot, positions[index].Y - 2.5); canvas.Children.Add(dot);
                    }
                }
                else
                {
                    var text = new TextBlock { Text = prompt.Label, FontFamily = new FontFamily("Segoe UI"), FontSize = prompt.Shape == "shoulder" ? 11 : 17,
                        FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, Foreground = ink, Width = 32, Height = 28,
                        TextAlignment = TextAlignment.Center, Padding = new Thickness(0, prompt.Shape == "shoulder" ? 8 : 3, 0, 0) };
                    canvas.Children.Add(text);
                }
                break;
        }
        var glyph = new Viewbox { Child = canvas, Width = t.Px(32 * em / .85), Height = t.Px(32 * em / .85), VerticalAlignment = VerticalAlignment.Center };
        AutomationProperties.SetName(glyph, $"{family}: {prompt.Label}");
        ToolTipService.SetToolTip(glyph, prompt.Label);
        return glyph;
    }
}
