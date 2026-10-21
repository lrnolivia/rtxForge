using System.Numerics;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Windows.UI;

namespace RtxForge.Windows.Views;

public sealed partial class GamePage
{
    Window? detailsWindow;
    bool overWindowActions;
    Microsoft.UI.Dispatching.DispatcherQueueTimer? windowActionsHideTimer;

    public void AttachWindow(Window window)
    {
        detailsWindow = window;
        window.SetTitleBar(WindowDragRegion);
        WindowActions.Visibility = Visibility.Visible;
        windowActionsHideTimer = DispatcherQueue.CreateTimer();
        windowActionsHideTimer.Interval = TimeSpan.FromMilliseconds(450);
        windowActionsHideTimer.Tick += (_, _) => { windowActionsHideTimer.Stop(); UpdateWindowActions(); };
        Unloaded += (_, _) => windowActionsHideTimer.Stop();
        ApplyWindowActionsTint();
        ElementCompositionPreview.SetIsTranslationEnabled(WindowMinimize, true);
        var visual = ElementCompositionPreview.GetElementVisual(WindowMinimize);
        visual.Opacity = 0;
        visual.Properties.InsertVector3("Translation", new Vector3(40, 0, 0));
    }

    void OnCloseWindow(object sender, RoutedEventArgs e) => detailsWindow?.Close();
    void OnMinimizeWindow(object sender, RoutedEventArgs e)
    {
        if (detailsWindow?.AppWindow.Presenter is Microsoft.UI.Windowing.OverlappedPresenter presenter) presenter.Minimize();
    }
    void OnWindowActionsEntered(object sender, PointerRoutedEventArgs e) { overWindowActions = true; windowActionsHideTimer?.Stop(); UpdateWindowActions(); }
    void OnWindowActionsExited(object sender, PointerRoutedEventArgs e) { overWindowActions = false; windowActionsHideTimer?.Start(); }
    void OnWindowActionFocus(object sender, RoutedEventArgs e) => DispatcherQueue.TryEnqueue(UpdateWindowActions);

    void UpdateWindowActions()
    {
        var show = overWindowActions || windowActionsHideTimer?.IsRunning == true
            || WindowClose.FocusState == FocusState.Keyboard || WindowMinimize.FocusState == FocusState.Keyboard;
        WindowMinimize.IsTabStop = WindowMinimize.IsHitTestVisible = show;
        var visual = ElementCompositionPreview.GetElementVisual(WindowMinimize);
        var opacity = visual.Compositor.CreateScalarKeyFrameAnimation();
        opacity.InsertExpressionKeyFrame(0, "this.StartingValue"); opacity.InsertKeyFrame(1, show ? 1 : 0);
        opacity.Duration = TimeSpan.FromMilliseconds(140);
        var translation = visual.Compositor.CreateVector3KeyFrameAnimation();
        translation.InsertExpressionKeyFrame(0, "this.StartingValue"); translation.InsertKeyFrame(1, new Vector3(show ? 0 : 40, 0, 0));
        translation.Duration = opacity.Duration;
        visual.StartAnimation("Opacity", opacity); visual.StartAnimation("Translation", translation);
    }

    void ApplyWindowActionsTint()
    {
        if (detailsWindow is null) return;
        var light = ActualTheme == ElementTheme.Light;
        var accent = gamePalette?.Color ?? Color.FromArgb(255, 128, 128, 128);
        var neutral = light ? Color.FromArgb(255, 244, 244, 244) : Color.FromArgb(255, 30, 30, 30);
        Color Tint(double amount, byte alpha) => Color.FromArgb(alpha,
            (byte)Math.Round(neutral.R + (accent.R - neutral.R) * amount),
            (byte)Math.Round(neutral.G + (accent.G - neutral.G) * amount),
            (byte)Math.Round(neutral.B + (accent.B - neutral.B) * amount));
        var normal = new SolidColorBrush(Tint(light ? .16 : .28, 244));
        var hover = new SolidColorBrush(Tint(light ? .26 : .42, 255));
        var pressed = new SolidColorBrush(Tint(.52, 255));
        var ink = new SolidColorBrush(light ? Microsoft.UI.Colors.Black : Microsoft.UI.Colors.White);
        var border = new SolidColorBrush(Tint(light ? .38 : .62, 255));
        foreach (var button in new[] { WindowClose, WindowMinimize })
        {
            button.Background = normal; button.Foreground = ink;
            button.BorderThickness = new Thickness(1); button.BorderBrush = border;
            button.Resources["ButtonBackgroundPointerOver"] = hover;
            button.Resources["ButtonBackgroundPressed"] = pressed;
            button.Resources["ButtonBorderBrushPointerOver"] = border;
            button.Resources["ButtonBorderBrushPressed"] = border;
            button.Resources["ButtonForegroundPointerOver"] = ink;
            button.Resources["ButtonForegroundPressed"] = ink;
        }
    }
}
