using System.Numerics;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using System.Runtime.CompilerServices;
using Microsoft.UI.Xaml.Controls;

namespace RtxForge.Windows.GameMode;

static partial class GmMotion
{
    public static CompositionEasingFunction Ease(Compositor compositor) =>
        compositor.CreateCubicBezierEasingFunction(new Vector2(.16f, 1), new Vector2(.3f, 1));

    static readonly ConditionalWeakTable<FrameworkElement, Action> scenes = new();

    // Each region arrives immediately, with a short travel and a different settling profile.
    // The page frame never zooms and there is no delayed or hidden content.
    public static void Page(UIElement element, double unit = 1, bool contentOnly = false)
    {
        if (element is not Panel panel) { if (element is FrameworkElement item) Enter(item, (float)(10 * unit), 1, GmMotionTokens.Surface, .92f); return; }
        var regions = panel.Children.ToArray();
        if (regions.Length > 6) return;
        panel.Children.Clear();
        for (var i = 0; i < regions.Length; i++)
        {
            var region = regions[i];
            if (region is not FrameworkElement frame) { panel.Children.Add(region); continue; }
            var scene = new Grid();
            Grid.SetRow(scene, Grid.GetRow(frame)); Grid.SetColumn(scene, Grid.GetColumn(frame));
            Grid.SetRowSpan(scene, Grid.GetRowSpan(frame)); Grid.SetColumnSpan(scene, Grid.GetColumnSpan(frame));
            Canvas.SetZIndex(scene, Canvas.GetZIndex(region));
            scene.Children.Add(region); panel.Children.Add(scene);
            if (contentOnly && i < regions.Length - 1) continue;
            var profile = GmMotionTokens.Region(i);
            Reveal(scene, i, unit);
        }
    }

    static IEnumerable<Button> Buttons(DependencyObject root)
    {
        if (root is Button button) yield return button;
        for (var i = 0; i < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(root); i++)
            foreach (var child in Buttons(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(root, i))) yield return child;
        // Before loading, the visual tree has no template children. Walk the authored containers too.
        if (root is Panel panel && Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(root) == 0)
            foreach (var child in panel.Children) foreach (var found in Buttons(child)) yield return found;
        else if (root is ContentControl content && content.Content is DependencyObject value && Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(root) == 0)
            foreach (var found in Buttons(value)) yield return found;
        else if (root is Border border && border.Child is { } body && Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(root) == 0)
            foreach (var found in Buttons(body)) yield return found;
    }

    internal static void PreferenceChanged(FrameworkElement element, Action changed)
    { scenes.Remove(element); scenes.Add(element, changed); }
    internal static void Forget(FrameworkElement element) => scenes.Remove(element);

    public static void Exit(FrameworkElement element, double unit, Action finished)
    {
        if (!Enabled) { finished(); return; }
        var compositor = Microsoft.UI.Xaml.Media.CompositionTarget.GetCompositorForCurrentThread();
        var opacity = compositor.CreateScalarKeyFrameAnimation(); opacity.Target = "Opacity";
        opacity.InsertKeyFrame(1, 0); opacity.Duration = TimeSpan.FromMilliseconds(180);
        element.StartAnimation(opacity);
        var scale = compositor.CreateVector3KeyFrameAnimation(); scale.Target = "Scale";
        scale.InsertKeyFrame(0, Vector3.One); scale.InsertKeyFrame(1, new(.985f, .985f, 1));
        scale.Duration = opacity.Duration;
        element.CenterPoint = new((float)element.ActualWidth / 2, (float)element.ActualHeight / 2, 0);
        element.StartAnimation(scale);
        var timer = element.DispatcherQueue.CreateTimer(); timer.IsRepeating = false;
        timer.Interval = opacity.Duration;
        timer.Tick += (_, _) =>
        {
            timer.Stop(); element.StopAnimation(opacity); element.StopAnimation(scale);
            opacity.Dispose(); scale.Dispose(); finished();
        };
        timer.Start();
    }

    public static void Dialog(FrameworkElement element, double unit = 1) => Enter(element, 0, GmMotionTokens.DialogScale, 140, 0);

    public static void Dissolve(FrameworkElement element) => OnLoaded(element, () =>
    {
        if (Enabled) Fade(element, .78f, GmMotionTokens.Fade);
    });

    static void Enter(FrameworkElement element, float distance, float fromScale, int period, float fromOpacity, int delay = 0) => OnLoaded(element, () =>
    {
        if (!Enabled) return;
        var compositor = Microsoft.UI.Xaml.Media.CompositionTarget.GetCompositorForCurrentThread();
        element.CenterPoint = new((float)element.ActualWidth / 2, (float)element.ActualHeight / 2, 0);
        using var ease = Ease(compositor);
        var slide = compositor.CreateVector3KeyFrameAnimation(); slide.Target = "Translation";
        slide.InsertKeyFrame(0, new(0, distance, 0)); slide.InsertKeyFrame(1, Vector3.Zero, ease);
        slide.Duration = TimeSpan.FromMilliseconds(period); slide.DelayTime = TimeSpan.FromMilliseconds(delay);
        var scale = compositor.CreateVector3KeyFrameAnimation(); scale.Target = "Scale";
        scale.InsertKeyFrame(0, new(fromScale, fromScale, 1)); scale.InsertKeyFrame(1, Vector3.One, ease);
        scale.Duration = slide.Duration; scale.DelayTime = slide.DelayTime;
        var opacity = compositor.CreateScalarKeyFrameAnimation(); opacity.Target = "Opacity";
        opacity.InsertKeyFrame(0, fromOpacity); opacity.InsertKeyFrame(1, 1, ease);
        opacity.Duration = slide.Duration; opacity.DelayTime = slide.DelayTime;
        element.Opacity = fromOpacity;
        element.StartAnimation(slide);
        if (fromScale != 1) element.StartAnimation(scale);
        element.StartAnimation(opacity);
        var timer = element.DispatcherQueue.CreateTimer(); timer.IsRepeating = false;
        timer.Interval = TimeSpan.FromMilliseconds(period + delay);
        bool stopped = false;
        scenes.Remove(element); scenes.Add(element, Stop);
        element.Unloaded += Unloaded;
        timer.Tick += (_, _) => Stop(); timer.Start();
        void Unloaded(object sender, RoutedEventArgs args)
        {
            element.Unloaded -= Unloaded;
            Stop();
        }
        void Stop()
        {
            if (stopped) return;
            stopped = true; timer.Stop(); element.Unloaded -= Unloaded; scenes.Remove(element);
            element.StopAnimation(slide); element.StopAnimation(scale); element.StopAnimation(opacity);
            element.Scale = Vector3.One; element.Translation = Vector3.Zero; element.Opacity = 1;
            slide.Dispose(); scale.Dispose(); opacity.Dispose();
        }
    });

    static void Fade(UIElement element, float from, int milliseconds)
    {
        var compositor = Microsoft.UI.Xaml.Media.CompositionTarget.GetCompositorForCurrentThread();
        using var opacity = compositor.CreateScalarKeyFrameAnimation(); opacity.Target = "Opacity";
        opacity.InsertKeyFrame(0, from);
        using var ease = Ease(compositor);
        opacity.InsertKeyFrame(1, 1, ease);
        opacity.Duration = TimeSpan.FromMilliseconds(milliseconds);
        element.StartAnimation(opacity);
    }

    public static void Feedback(FrameworkElement element) => OnLoaded(element, () =>
    {
        if (Enabled) Fade(element, .65f, GmMotionTokens.Feedback);
    });

    static void OnLoaded(FrameworkElement element, Action action)
    {
        if (element.IsLoaded) { action(); return; }
        void Loaded(object sender, RoutedEventArgs args) { element.Loaded -= Loaded; action(); }
        element.Loaded += Loaded;
    }
}
