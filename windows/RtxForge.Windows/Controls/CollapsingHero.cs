using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace RtxForge.Windows.Controls;

/// <summary>Scroll-driven layout only: no timers, page rebuilds or engine requests.</summary>
public sealed class CollapsingHero
{
    readonly ScrollViewer scroll;
    readonly FrameworkElement hero;
    readonly FrameworkElement spacer;
    readonly FrameworkElement? navigation;
    readonly Thickness inset;
    readonly Action<double> changed;
    double expanded, compact;
    double previousHeight = -1;

    public CollapsingHero(ScrollViewer scroll, FrameworkElement hero, FrameworkElement spacer, Action<double> changed, FrameworkElement? navigation = null)
    {
        this.scroll = scroll; this.hero = hero; this.spacer = spacer; this.changed = changed; this.navigation = navigation;
        inset = scroll.Margin;
        scroll.ViewChanged += (_, _) => Apply();
        scroll.SizeChanged += (_, _) => Apply();
        if (navigation is not null)
        {
            navigation.SizeChanged += (_, _) => Apply();
            navigation.RegisterPropertyChangedCallback(UIElement.VisibilityProperty, (_, _) => Apply());
        }
    }

    public void SetRange(double fullHeight, double minimumHeight)
    {
        expanded = fullHeight; compact = Math.Min(fullHeight, minimumHeight);
        previousHeight = -1; Apply();
    }

    /// <summary>
    /// Off: the hero scrolls with the page (phone layouts), so the scroller keeps its own inset
    /// and the spacer takes no room. On again, the next layout restores the sticky range.
    /// </summary>
    public bool Enabled
    {
        get => enabled;
        set
        {
            if (enabled == value) return;
            enabled = value;
            previousHeight = -1;
            if (enabled) { Apply(); return; }
            scroll.Margin = inset;
            spacer.Height = 0;
            if (scroll.Content is FrameworkElement content) content.MinHeight = 0;
            changed(0);
        }
    }
    bool enabled = true;

    void Apply()
    {
        if (expanded <= 0 || !enabled) return;
        // The hero sits above the scroller. A fixed compact inset clips content
        // below it; a fixed spacer supplies only its expandable portion. Neither
        // changes with scrolling, so the scroll range cannot feed back on itself.
        var extra = navigation?.Visibility == Visibility.Visible
            ? navigation.ActualHeight + navigation.Margin.Top + navigation.Margin.Bottom : 0;
        scroll.Margin = new Thickness(inset.Left, inset.Top + compact + extra, inset.Right, inset.Bottom);
        spacer.Height = expanded - compact;
        // A short page must still be able to scroll the whole range, or the hero stalls
        // half-collapsed. The viewport does not depend on the offset, so this is stable.
        if (scroll.Content is FrameworkElement content && scroll.ViewportHeight > 0)
            content.MinHeight = scroll.ViewportHeight + expanded - compact;
        var removed = Math.Round(Math.Clamp(scroll.VerticalOffset, 0, expanded - compact));
        var height = expanded - removed;
        if (Math.Abs(previousHeight - height) < .5) return;
        previousHeight = height;
        hero.Height = height;
        changed(expanded == compact ? 0 : removed / (expanded - compact));
    }
}
