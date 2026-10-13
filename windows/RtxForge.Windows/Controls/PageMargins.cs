using Microsoft.UI.Xaml;

namespace RtxForge.Windows.Controls;

/// <summary>
/// One layout rule for every desktop page: content fills the window with side margins that
/// scale with it (3% of the width, 16–56 px), and on very wide windows becomes a centered
/// column (at most <see cref="MaxColumn"/> wide) with equal margins, as Game Mode's pages do.
/// </summary>
public static class PageMargins
{
    public const double MaxColumn = 1600;

    /// <summary>The side margin for a page of this width.</summary>
    public static double Side(double width) =>
        Math.Round(Math.Max(Math.Clamp(width * 0.03, 16, 56), (width - MaxColumn) / 2));

    public static Thickness For(double width, double top = 12, double bottom = 48)
    {
        var side = Side(width);
        return new Thickness(side, top, side, bottom);
    }
}
