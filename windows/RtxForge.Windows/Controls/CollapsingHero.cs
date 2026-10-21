using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace RtxForge.Windows.Controls;

/// <summary>Scroll-driven layout only: no timers, page rebuilds or engine requests.</summary>
public sealed class CollapsingHero
{
    readonly ScrollViewer scroll;
    readonly FrameworkElement hero;
    readonly StackPanel workspace;
    readonly Thickness inset;
    readonly Action<double> changed;
    double expanded, compact;
    double previousHeight = -1;

    public CollapsingHero(ScrollViewer scroll, FrameworkElement hero, StackPanel workspace, Action<double> changed)
    {
        this.scroll = scroll; this.hero = hero; this.workspace = workspace; this.changed = changed;
        inset = workspace.Padding;
        scroll.ViewChanged += (_, _) => Apply();
    }

    public void SetRange(double fullHeight, double minimumHeight)
    {
        expanded = fullHeight; compact = Math.Min(fullHeight, minimumHeight);
        previousHeight = -1; Apply();
    }

    void Apply()
    {
        if (expanded <= 0) return;
        var removed = Math.Round(Math.Clamp(scroll.VerticalOffset, 0, expanded - compact));
        var height = expanded - removed;
        var previousInset = workspace.Padding.Bottom - inset.Bottom;
        var unclampedRange = scroll.ExtentHeight - previousInset - scroll.ViewportHeight;
        // Long pages already have enough body below the compact hero. They need no
        // compensation (and must not end in a large empty area).
        var compensation = removed >= expanded - compact && unclampedRange > expanded - compact + 32 ? 0 : removed;
        if (Math.Abs(previousHeight - height) < .5 && Math.Abs(previousInset - compensation) < .5) return;
        previousHeight = height;
        hero.Height = height;
        // Keep the original scroll range. Shrinking the header near the bottom must
        // not clamp the offset and repeatedly expand/collapse the header again.
        workspace.Padding = new Thickness(inset.Left, inset.Top, inset.Right, inset.Bottom + compensation);
        changed(expanded == compact ? 0 : removed / (expanded - compact));
    }
}
