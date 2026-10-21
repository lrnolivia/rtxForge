using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Foundation;

namespace RtxForge.Windows.Controls;

/// <summary>
/// Left-to-right items that wrap onto the next line when the row runs out of width, each line
/// starting at the left edge and its items centered on the line (the hero credit line: developer
/// · release, then the source / OS / test badges inline after it).
/// </summary>
public sealed class WrapRow : Panel
{
    public double Spacing { get; set; } = 8;
    public double LineSpacing { get; set; } = 6;

    protected override Size MeasureOverride(Size available)
    {
        double x = 0, y = 0, line = 0, width = 0;
        foreach (var child in Children)
        {
            child.Measure(new Size(available.Width, double.PositiveInfinity));
            var size = child.DesiredSize;
            if (size.Width == 0 && size.Height == 0) continue;
            if (x > 0 && x + Spacing + size.Width > available.Width) { y += line + LineSpacing; x = 0; line = 0; }
            x += (x > 0 ? Spacing : 0) + size.Width;
            line = Math.Max(line, size.Height);
            width = Math.Max(width, x);
        }
        return new Size(double.IsInfinity(available.Width) ? width : Math.Min(width, available.Width), y + line);
    }

    protected override Size ArrangeOverride(Size final)
    {
        var lines = new List<(List<UIElement> Items, double Height)>();
        double x = 0;
        foreach (var child in Children)
        {
            var size = child.DesiredSize;
            if (size.Width == 0 && size.Height == 0) { child.Arrange(default); continue; }
            if (lines.Count == 0 || (x > 0 && x + Spacing + size.Width > final.Width)) { lines.Add(([], 0)); x = 0; }
            var current = lines[^1];
            current.Items.Add(child);
            lines[^1] = (current.Items, Math.Max(current.Height, size.Height));
            x += (x > 0 ? Spacing : 0) + size.Width;
        }
        double y = 0;
        foreach (var (items, height) in lines)
        {
            x = 0;
            foreach (var child in items)
            {
                var size = child.DesiredSize;
                var w = Math.Min(size.Width, final.Width);
                child.Arrange(new Rect(x, y + (height - size.Height) / 2, w, size.Height));
                x += w + Spacing;
            }
            y += height + LineSpacing;
        }
        return final;
    }
}
