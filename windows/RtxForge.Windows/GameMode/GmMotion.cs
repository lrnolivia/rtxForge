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
            var light = new ArtworkLightLayer();
            scene.Children.Add(light.Artwork); scene.Children.Add(region); scene.Children.Add(light); panel.Children.Add(scene);
            foreach (var button in Buttons(region)) GmGlow.Layer(button, light);
            if (contentOnly && i < regions.Length - 1) continue;
            var profile = GmMotionTokens.Region(i);
            Enter(scene, (float)(profile.Travel * unit), 1, profile.Period, .92f);
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
        using var opacity = compositor.CreateScalarKeyFrameAnimation(); opacity.Target = "Opacity";
        opacity.InsertKeyFrame(1, 0); opacity.Duration = TimeSpan.FromMilliseconds(GmMotionTokens.Exit);
        element.StartAnimation(opacity);
        using var travel = compositor.CreateSpringVector3Animation(); travel.Target = "Translation";
        travel.FinalValue = new(0, (float)(-6 * unit), 0); travel.DampingRatio = 1;
        travel.Period = TimeSpan.FromMilliseconds(GmMotionTokens.Focus); element.StartAnimation(travel);
        var timer = element.DispatcherQueue.CreateTimer(); timer.IsRepeating = false;
        timer.Interval = TimeSpan.FromMilliseconds(GmMotionTokens.Exit);
        timer.Tick += (_, _) => { timer.Stop(); finished(); };
        timer.Start();
    }

    public static void Dialog(FrameworkElement element, double unit = 1) => Enter(element, (float)(GmMotionTokens.DialogTravel * unit), GmMotionTokens.DialogScale, GmMotionTokens.Surface, .90f);

    public static void Dissolve(FrameworkElement element) => OnLoaded(element, () =>
    {
        if (Enabled) Fade(element, .78f, GmMotionTokens.Fade);
    });

    static void Enter(FrameworkElement element, float distance, float fromScale, int period, float fromOpacity) => OnLoaded(element, () =>
    {
        if (!Enabled) return;
        var compositor = Microsoft.UI.Xaml.Media.CompositionTarget.GetCompositorForCurrentThread();
        element.CenterPoint = new((float)element.ActualWidth / 2, (float)element.ActualHeight / 2, 0);
        var slide = compositor.CreateSpringVector3Animation(); slide.Target = "Translation";
        slide.InitialValue = new(0, distance, 0); slide.FinalValue = Vector3.Zero;
        slide.DampingRatio = GmMotionTokens.SceneDamping; slide.Period = TimeSpan.FromMilliseconds(period);
        var scale = compositor.CreateSpringVector3Animation(); scale.Target = "Scale";
        scale.InitialValue = new(fromScale, fromScale, 1); scale.FinalValue = Vector3.One;
        scale.DampingRatio = GmMotionTokens.SceneDamping; scale.Period = TimeSpan.FromMilliseconds(period);
        element.StartAnimation(slide);
        if (fromScale != 1) element.StartAnimation(scale);
        Fade(element, fromOpacity, GmMotionTokens.Fade);
        scenes.Remove(element); scenes.Add(element, Stop);
        element.Unloaded += Unloaded;
        void Unloaded(object sender, RoutedEventArgs args)
        {
            element.Unloaded -= Unloaded;
            Stop(); scenes.Remove(element); slide.Dispose(); scale.Dispose();
        }
        void Stop()
        {
            element.StopAnimation(slide); element.StopAnimation(scale);
            element.Scale = Vector3.One; element.Translation = Vector3.Zero; element.Opacity = 1;
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
