using System.Numerics;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Input;

namespace RtxForge.Windows.Views;

public sealed partial class GamePage
{
    Window? detailsWindow;
    bool overWindowActions;

    public void AttachWindow(Window window)
    {
        detailsWindow = window;
        window.SetTitleBar(WindowDragRegion);
        WindowActions.Visibility = Visibility.Visible;
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
    void OnWindowActionsEntered(object sender, PointerRoutedEventArgs e) { overWindowActions = true; UpdateWindowActions(); }
    void OnWindowActionsExited(object sender, PointerRoutedEventArgs e) { overWindowActions = false; UpdateWindowActions(); }
    void OnWindowActionFocus(object sender, RoutedEventArgs e) => DispatcherQueue.TryEnqueue(UpdateWindowActions);

    void UpdateWindowActions()
    {
        var show = overWindowActions || WindowClose.FocusState == FocusState.Keyboard || WindowMinimize.FocusState == FocusState.Keyboard;
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
}
