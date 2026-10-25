using System.Numerics;
using Microsoft.Graphics.Canvas.Effects;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;

namespace RtxForge.Windows.GameMode;

static partial class GmMotion
{
    public const int SlideArrival = 340;
    public static void GlowArrival(FrameworkElement element, int delay = 0)
    {
        element.Opacity = 1;
        Enter(element, 0, 1, 180, 0, delay);
    }

    // Native content remains interactive. The short-lived blur copy is removed
    // when the slide finishes; it never becomes the permanent page surface.
    public static void Horizontal(Grid host, int direction, double unit, bool outgoing = false, Action? completed = null) => OnLoaded(host, () =>
    {
        if (!Enabled) { completed?.Invoke(); return; }
        var compositor = Microsoft.UI.Xaml.Media.CompositionTarget.GetCompositorForCurrentThread();
        var duration = TimeSpan.FromMilliseconds(outgoing ? 280 : SlideArrival);
        var distance = (float)(Math.Min(240 * unit, Math.Max(80, host.ActualWidth * .16)) * (direction < 0 ? -1 : 1));
        using var ease = compositor.CreateCubicBezierEasingFunction(new(.25f, .1f), new(.25f, 1));
        var travel = compositor.CreateVector3KeyFrameAnimation(); travel.Target = "Translation";
        travel.InsertKeyFrame(0, outgoing ? Vector3.Zero : new(distance, 0, 0));
        travel.InsertKeyFrame(1, outgoing ? new(-distance, 0, 0) : Vector3.Zero, ease); travel.Duration = duration;
        var opacity = compositor.CreateScalarKeyFrameAnimation(); opacity.Target = "Opacity";
        opacity.InsertKeyFrame(0, outgoing ? 1 : .35f); opacity.InsertKeyFrame(1, outgoing ? 0 : 1, ease); opacity.Duration = duration;
        host.StartAnimation(travel); host.StartAnimation(opacity);
        var releaseBlur = MotionBlur(host, duration, unit);
        var timer = host.DispatcherQueue.CreateTimer(); timer.IsRepeating = false; timer.Interval = duration;
        var stopped = false;
        void Stop()
        {
            if (stopped) return;
            stopped = true; timer.Stop(); host.Unloaded -= Unloaded;
            host.StopAnimation(travel); host.StopAnimation(opacity);
            host.Translation = Vector3.Zero; host.Opacity = outgoing ? 0 : 1;
            releaseBlur(); travel.Dispose(); opacity.Dispose(); scenes.Remove(host);
            completed?.Invoke();
        }
        void Unloaded(object sender, RoutedEventArgs args) => Stop();
        host.Unloaded += Unloaded; scenes.Remove(host); scenes.Add(host, Stop);
        timer.Tick += (_, _) => Stop(); timer.Start();
    });

    static Action MotionBlur(Grid host, TimeSpan duration, double unit)
    {
        if (host.Children.FirstOrDefault() is not FrameworkElement content || content.ActualWidth <= 0 || content.ActualHeight <= 0) return () => { };
        Canvas? overlay = null;
        CompositionVisualSurface? surface = null;
        CompositionSurfaceBrush? source = null;
        CompositionEffectFactory? factory = null;
        CompositionEffectBrush? brush = null;
        SpriteVisual? sprite = null;
        Visual? original = null;
        float opacity = 1;
        void Release()
        {
            if (original is not null) original.Opacity = opacity;
            if (overlay is not null) { ElementCompositionPreview.SetElementChildVisual(overlay, null); host.Children.Remove(overlay); }
            sprite?.Dispose(); brush?.Dispose(); factory?.Dispose(); source?.Dispose(); surface?.Dispose();
        }
        try
        {
            original = ElementCompositionPreview.GetElementVisual(content); opacity = original.Opacity;
            var compositor = original.Compositor;
            surface = compositor.CreateVisualSurface(); surface.SourceVisual = original;
            surface.SourceSize = new((float)content.ActualWidth, (float)content.ActualHeight);
            source = compositor.CreateSurfaceBrush(surface);
            using var effect = new GaussianBlurEffect { Name = "SlideBlur", BlurAmount = 0,
                BorderMode = EffectBorderMode.Hard, Source = new CompositionEffectSourceParameter("Page") };
            factory = compositor.CreateEffectFactory(effect, ["SlideBlur.BlurAmount"]);
            brush = factory.CreateBrush(); brush.SetSourceParameter("Page", source);
            using var blur = compositor.CreateScalarKeyFrameAnimation();
            blur.InsertKeyFrame(0, 0); blur.InsertKeyFrame(.26f, (float)(7 * unit));
            blur.InsertKeyFrame(.65f, (float)(3 * unit)); blur.InsertKeyFrame(1, 0); blur.Duration = duration;
            brush.StartAnimation("SlideBlur.BlurAmount", blur);
            sprite = compositor.CreateSpriteVisual(); sprite.Size = surface.SourceSize; sprite.Brush = brush;
            overlay = new Canvas { IsHitTestVisible = false }; host.Children.Add(overlay);
            ElementCompositionPreview.SetElementChildVisual(overlay, sprite);
            // Keep native geometry in the hit-test tree during the transient copy.
            original.Opacity = .001f;
            return Release;
        }
        catch (Exception error) when (error is System.Runtime.InteropServices.COMException or UnauthorizedAccessException or ArgumentException)
        {
            Release(); return () => { };
        }
    }

    public static void Reveal(FrameworkElement element, int order, double unit = 1) =>
        Enter(element, (float)(-16 * unit), .955f, 280, 0, Math.Min(order * 40, 360));
}
