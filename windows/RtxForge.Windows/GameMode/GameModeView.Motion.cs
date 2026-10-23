using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Animation;

namespace RtxForge.Windows.GameMode;

public sealed partial class GameModeView
{
    Border? detailsPoster;
    double lastNavigation;
    bool rapidNavigation;

    void PrepareArtwork(FrameworkElement? artwork)
    {
        var service = ConnectedAnimationService.GetForCurrentView();
        service.GetAnimation("gm-artwork")?.Cancel();
        if (!GmMotion.Enabled || artwork is null || !artwork.IsLoaded || artwork.ActualHeight < 1) return;
        // Only matching poster geometry travels. Wide capsules and missing artwork use a crisp dissolve.
        if (Math.Abs(artwork.ActualWidth / artwork.ActualHeight - 2d / 3) > .08) return;
        if (artwork is not Border { Child: Border { Background: ImageBrush } }) return;
        service.DefaultDuration = TimeSpan.FromMilliseconds(GmMotionTokens.Surface);
        service.PrepareToAnimate("gm-artwork", artwork).Configuration = new DirectConnectedAnimationConfiguration();
    }

    void ReceiveArtwork(Border artwork)
    {
        void Receive()
        {
            if (!GmMotion.Enabled) { ConnectedAnimationService.GetForCurrentView().GetAnimation("gm-artwork")?.Cancel(); return; }
            if (artwork.IsLoaded) ConnectedAnimationService.GetForCurrentView().GetAnimation("gm-artwork")?.TryStart(artwork);
        }
        if (artwork.IsLoaded) Receive();
        else artwork.Loaded += Loaded;
        void Loaded(object sender, RoutedEventArgs args) { artwork.Loaded -= Loaded; Receive(); }
    }


    bool MoveVirtualRow(DependencyObject? focused, int step)
    {
        if (focused is null) return false;
        DependencyObject item = focused;
        while (Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(item) is { } parent)
        {
            if (parent is ItemsRepeater repeater && repeater.ItemsSource is IList<UIElement> rows)
            {
                var index = repeater.GetElementIndex((UIElement)item);
                if (index < 0) return false;
                for (var next = index + step; next >= 0 && next < rows.Count; next += step)
                {
                    if (rows[next] is not Control { IsEnabled: true, IsTabStop: true }) continue;
                    var target = (Control)repeater.GetOrCreateElement(next);
                    target.StartBringIntoView(new BringIntoViewOptions { AnimationDesired = GmMotion.Enabled && !rapidNavigation });
                    return target.Focus(FocusState.Keyboard);
                }
                return false;
            }
            item = parent;
        }
        return false;
    }

    void NavigationMotion()
    {
        var now = GmMotion.Now; rapidNavigation = now - lastNavigation < .12; lastNavigation = now;
    }
    void PolishScroll(ScrollViewer scroll)
    {
        scroll.BringIntoViewRequested += (_, e) =>
        {
            // During repeats/reversals, make the new focused destination visible immediately.
            // No delayed callback is allowed to restore an older scroll target.
            e.AnimationDesired = GmMotion.Enabled && !rapidNavigation;
        };
    }
}
