using System.Numerics;
using System.Runtime.CompilerServices;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.GameMode;

/// <summary>Live viewport alpha mask. Original controls retain scrolling, focus and accessibility.</summary>
static class GmScrollFade
{
    static readonly ConditionalWeakTable<ScrollViewer, Attachment> attachments = new();
    public static void Attach(ScrollViewer scroll, double unit) =>
        attachments.GetValue(scroll, key => new Attachment(key, unit));

    internal static CompositionLinearGradientBrush CreateGradient(Compositor compositor)
    {
        var gradient = compositor.CreateLinearGradientBrush();
        gradient.StartPoint = Vector2.Zero; gradient.EndPoint = new Vector2(0, 1);
        for (var i = 0; i < 2 * (GmMotionTokens.ScrollFadeSamples + 1); i++)
            gradient.ColorStops.Add(compositor.CreateColorGradientStop(0, Microsoft.UI.Colors.White));
        return gradient;
    }

    internal static void UpdateGradient(CompositionLinearGradientBrush gradient, ScrollFadeProfile profile)
    {
        if (profile.Height <= 0) return;
        var samples = GmMotionTokens.ScrollFadeSamples;
        for (var i = 0; i < gradient.ColorStops.Count; i++)
        {
            var y = i <= samples ? profile.Depth * i / samples
                : profile.Height - profile.Depth + profile.Depth * (i - samples - 1) / samples;
            gradient.ColorStops[i].Offset = (float)(y / profile.Height);
            gradient.ColorStops[i].Color = global::Windows.UI.Color.FromArgb((byte)Math.Round(255 * profile.Alpha(y)), 255, 255, 255);
        }
    }

    sealed class Attachment
    {
        readonly ScrollViewer scroll;
        readonly double unit;
        ScrollContentPresenter? presenter;
        Visual? sourceVisual;
        CompositionVisualSurface? surface;
        CompositionSurfaceBrush? source;
        CompositionLinearGradientBrush? gradient;
        CompositionMaskBrush? mask;
        SpriteVisual? sprite;
        float originalOpacity;

        public Attachment(ScrollViewer scroll, double unit)
        {
            this.scroll = scroll; this.unit = unit;
            scroll.Loaded += (_, _) => Connect();
            scroll.Unloaded += (_, _) => Disconnect();
            scroll.SizeChanged += (_, _) => Update();
            scroll.ViewChanged += (_, _) => Update();
            scroll.RegisterPropertyChangedCallback(ScrollViewer.ScrollableHeightProperty, (_, _) => Update());
            if (scroll.IsLoaded) Connect();
        }

        static T? Find<T>(DependencyObject parent) where T : DependencyObject
        {
            for (var i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
            {
                var child = VisualTreeHelper.GetChild(parent, i);
                if (child is T match) return match;
                if (Find<T>(child) is { } nested) return nested;
            }
            return null;
        }

        void Connect()
        {
            if (sprite is not null) return;
            scroll.ApplyTemplate();
            presenter = Find<ScrollContentPresenter>(scroll);
            if (presenter is null) return;
            try
            {
                sourceVisual = ElementCompositionPreview.GetElementVisual(presenter);
                originalOpacity = sourceVisual.Opacity;
                var compositor = sourceVisual.Compositor;
                surface = compositor.CreateVisualSurface();
                surface.SourceVisual = sourceVisual;
                source = compositor.CreateSurfaceBrush(surface);
                gradient = CreateGradient(compositor);
                mask = compositor.CreateMaskBrush(); mask.Source = source; mask.Mask = gradient;
                sprite = compositor.CreateSpriteVisual(); sprite.Brush = mask;
                ElementCompositionPreview.SetElementChildVisual(scroll, sprite);
                presenter.SizeChanged += PresenterSizeChanged;
                Update();
            }
            catch (System.Runtime.InteropServices.COMException) { Disconnect(); }
        }

        void PresenterSizeChanged(object sender, SizeChangedEventArgs e) => Update();

        void Update()
        {
            if (sprite is null || presenter is null || sourceVisual is null) return;
            var height = presenter.ActualHeight;
            var profile = ScrollFadeProfile.Create(height, scroll.VerticalOffset, scroll.ScrollableHeight, unit);
            var active = height > 0 && presenter.ActualWidth > 0 && (profile.Top > 0 || profile.Bottom > 0);
            sprite.IsVisible = active;
            sourceVisual.Opacity = active ? 0 : originalOpacity;
            if (!active) return;
            var size = new Vector2((float)presenter.ActualWidth, (float)height);
            surface!.SourceSize = sprite.Size = size;
            var origin = presenter.TransformToVisual(scroll).TransformPoint(new global::Windows.Foundation.Point());
            sprite.Offset = new Vector3((float)origin.X, (float)origin.Y, 0);
            UpdateGradient(gradient!, profile);
        }

        void Disconnect()
        {
            if (presenter is not null) presenter.SizeChanged -= PresenterSizeChanged;
            if (sourceVisual is not null) sourceVisual.Opacity = originalOpacity;
            if (sprite is not null) ElementCompositionPreview.SetElementChildVisual(scroll, null);
            sprite?.Dispose(); mask?.Dispose(); gradient?.Dispose(); source?.Dispose(); surface?.Dispose();
            sprite = null; mask = null; gradient = null; source = null; surface = null; sourceVisual = null; presenter = null;
        }
    }
}
