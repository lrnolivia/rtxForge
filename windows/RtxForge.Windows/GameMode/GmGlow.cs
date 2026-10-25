using System.Numerics;
using System.Runtime.CompilerServices;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace RtxForge.Windows.GameMode;

/// <summary>Light follows selection and input focus without scaling the control.</summary>
static class GmGlow
{
    static readonly ConditionalWeakTable<Button, State> states = new();
    static readonly ConditionalWeakTable<Control, ArtworkLightLayer> destinations = new();
    internal static ArtworkLightLayer? Destination(Control target)
    {
        if (destinations.TryGetValue(target, out var layer)) return layer;
        for (DependencyObject? parent = target; parent is not null; parent = VisualTreeHelper.GetParent(parent))
            if (parent is Grid grid && grid.Children.OfType<ArtworkLightLayer>().FirstOrDefault() is { } nearest) return nearest;
        return null;
    }

    public static void Attach(Button button, GmTheme theme, SolidColorBrush accent, bool selected = false, ArtworkLightLayer? layer = null)
    {
        var state = new State(button, theme, accent, selected, layer);
        states.Add(button, state);
    }

    public static void Layer(Button button, ArtworkLightLayer layer)
    {
        destinations.Remove(button); destinations.Add(button, layer);
        if (states.TryGetValue(button, out var state)) state.SetLayer(layer);
    }
    internal static void Indicator(Button button)
    { if (states.TryGetValue(button, out var state)) state.ExternalSurface = true; }
    public static void Selected(Button button, bool selected)
    {
        if (states.TryGetValue(button, out var state)) { state.Selected = selected; state.Update(); }
    }

    public static void Artwork(Control target, Border artwork, global::Windows.UI.Color color, bool selected, GmTheme theme, string? source, ArtworkLightLayer? layer = null)
    {
        if (layer is not null && source is not null) { layer.Track(target, artwork, selected, theme, source); return; }
        if (artwork.Parent is not Grid overlay) return;
        Canvas? host = null;
        var mask = new Rectangle
        {
            Width = artwork.Width, Height = artwork.Height, Fill = GmTheme.B(Microsoft.UI.Colors.White),
            RadiusX = artwork.CornerRadius.TopLeft, RadiusY = artwork.CornerRadius.TopLeft, IsHitTestVisible = false,
        };
        overlay.Children.Insert(0, mask);
        GlowHalo? halo = null;
        var pointer = false;
        var inViewport = true;
        long enabledToken = 0;
        void Paint()
        {
            if (halo is null) return;
            var focused = target.FocusState != FocusState.Unfocused;
            var opacity = !target.IsEnabled ? 0 : focused ? .76f : selected ? .60f : pointer ? .38f : 0;
            halo.Set(color, opacity, inViewport);
        }
        void Load()
        {
            if (halo is not null) return;
            host = layer?.AddControl(artwork) ?? new Canvas { IsHitTestVisible = false };
            if (layer is null) overlay.Children.Insert(0, host);
            halo = new GlowHalo(host, mask.GetAlphaMask(), theme);
            halo.Resize(artwork.Width, artwork.Height, artwork.CornerRadius, layer is not null);
            enabledToken = target.RegisterPropertyChangedCallback(Control.IsEnabledProperty, (_, _) => Paint());
            Paint();
        }
        artwork.Loaded += (_, _) => Load();
        artwork.Unloaded += (_, _) =>
        {
            if (host is not null) ElementCompositionPreview.SetElementChildVisual(host, null);
            layer?.RemoveControl(artwork);
            if (layer is null && host is not null) overlay.Children.Remove(host);
            if (halo is not null) target.UnregisterPropertyChangedCallback(Control.IsEnabledProperty, enabledToken);
            halo?.Dispose(); halo = null;
        };
        artwork.EffectiveViewportChanged += (_, e) =>
        {
            layer?.RefreshControl(artwork);
            var visible = InViewport(artwork, e.EffectiveViewport);
            if (visible == inViewport) return;
            inViewport = visible; Paint();
        };
        target.GotFocus += (_, _) => Paint();
        target.LostFocus += (_, _) => Paint();
        target.PointerEntered += (_, _) => { pointer = true; Paint(); };
        target.PointerExited += (_, _) => { pointer = false; Paint(); };
        if (artwork.IsLoaded) Load();
    }

    sealed class State
    {
        readonly Button button;
        readonly GmTheme theme;
        readonly SolidColorBrush accent;
        ArtworkLightLayer? layer;
        Canvas? host;
        Shape? mask;
        Rectangle? fill;
        Microsoft.UI.Xaml.Shapes.Path? contour;
        Border? edge, focusRing, focusWash;
        GlowHalo? halo;
        long backgroundToken, accentToken, radiusToken, enabledToken, borderToken, thicknessToken, marginToken;
        Vector2 outlineSize;
        CornerRadius outlineCorners;
        bool pointer, loaded, inViewport = true;
        float edgeLevel = -1;
        public bool Selected;
        public bool ExternalSurface;

        public State(Button button, GmTheme theme, SolidColorBrush accent, bool selected, ArtworkLightLayer? layer)
        {
            this.button = button; this.theme = theme; this.accent = accent; this.layer = layer; Selected = selected;
            button.Loaded += (_, _) => Load();
            button.Unloaded += (_, _) => Unload();
            button.SizeChanged += (_, _) => Resize();
            button.GotFocus += (_, _) => Update();
            button.LostFocus += (_, _) => Update();
            button.PointerEntered += (_, _) => { pointer = true; Update(); };
            button.PointerExited += (_, _) => { pointer = false; Update(); };
            button.EffectiveViewportChanged += (_, e) =>
            {
                layer?.RefreshControl(button);
                var visible = InViewport(button, e.EffectiveViewport);
                if (visible == inViewport) return;
                inViewport = visible; Update();
            };
        }

        public void SetLayer(ArtworkLightLayer value) { if (!loaded) layer = value; }

        void Load()
        {
            if (loaded) return;
            layer = Destination(button) ?? layer;
            button.ApplyTemplate();
            var templateHost = Find<Canvas>(button, "GlowHost");
            fill = Find<Rectangle>(button, "GlowMask");
            contour = Find<Microsoft.UI.Xaml.Shapes.Path>(button, "GlowContour");
            mask = fill;
            edge = Find<Border>(button, "GlowEdge");
            focusRing = Find<Border>(button, "FocusRing");
            focusWash = Find<Border>(button, "FocusWash");
            if (templateHost is null || mask is null) return;
            loaded = true;
            backgroundToken = button.RegisterPropertyChangedCallback(Control.BackgroundProperty, (_, _) => Update());
            radiusToken = button.RegisterPropertyChangedCallback(Control.CornerRadiusProperty, (_, _) => Resize());
            enabledToken = button.RegisterPropertyChangedCallback(Control.IsEnabledProperty, (_, _) => Update());
            accentToken = accent.RegisterPropertyChangedCallback(SolidColorBrush.ColorProperty, (_, _) => Update());
            borderToken = button.RegisterPropertyChangedCallback(Control.BorderBrushProperty, (_, _) => Update());
            thicknessToken = button.RegisterPropertyChangedCallback(Control.BorderThicknessProperty, (_, _) => Update());
            marginToken = button.RegisterPropertyChangedCallback(Control.FocusVisualMarginProperty, (_, _) => Resize());
            Resize(); Update();
        }

        void Unload()
        {
            if (!loaded) return;
            loaded = false; pointer = false;
            button.UnregisterPropertyChangedCallback(Control.BackgroundProperty, backgroundToken);
            button.UnregisterPropertyChangedCallback(Control.CornerRadiusProperty, radiusToken);
            button.UnregisterPropertyChangedCallback(Control.IsEnabledProperty, enabledToken);
            accent.UnregisterPropertyChangedCallback(SolidColorBrush.ColorProperty, accentToken);
            button.UnregisterPropertyChangedCallback(Control.BorderBrushProperty, borderToken);
            button.UnregisterPropertyChangedCallback(Control.BorderThicknessProperty, thicknessToken);
            button.UnregisterPropertyChangedCallback(Control.FocusVisualMarginProperty, marginToken);
            if (host is not null) ElementCompositionPreview.SetElementChildVisual(host, null);
            layer?.RemoveControl(button);
            halo?.Dispose();
            if (edge is not null) ElementCompositionPreview.GetElementVisual(edge).StopAnimation("Opacity");
            halo = null; mask = null; fill = null; contour = null; host = null; edge = null; focusRing = null; focusWash = null; edgeLevel = -1;
            outlineSize = default; outlineCorners = default;
        }

        void Resize()
        {
            if (mask is null) return;
            var size = new Vector2((float)button.ActualWidth, (float)button.ActualHeight);
            var corners = button.CornerRadius;
            if (size.X <= 0 || size.Y <= 0) return;
            var asymmetric = corners.TopLeft != corners.TopRight || corners.TopLeft != corners.BottomRight || corners.TopLeft != corners.BottomLeft;
            if (outlineSize != size || !outlineCorners.Equals(corners))
            {
                if (asymmetric && contour is not null) contour.Data = GmOutline.Mask(size.X, size.Y, corners);
                else if (fill is not null) fill.RadiusX = fill.RadiusY = Math.Min(corners.TopLeft, Math.Min(size.X, size.Y) / 2);
                outlineSize = size; outlineCorners = corners;
            }
            var shape = asymmetric && contour is not null ? (Shape)contour : fill!;
            if (!ReferenceEquals(mask, shape))
            {
                mask = shape;
                mask.Fill = button.Background;
                fill!.Visibility = ReferenceEquals(mask, fill) ? Visibility.Visible : Visibility.Collapsed;
                if (contour is not null) contour.Visibility = ReferenceEquals(mask, contour) ? Visibility.Visible : Visibility.Collapsed;
                halo?.SetMask(mask.GetAlphaMask());
            }
            halo?.Resize(button.ActualWidth, button.ActualHeight, corners, layer is not null);
            var innerFocus = GmOutline.Inset(corners, button.FocusVisualMargin);
            if (focusRing is not null) focusRing.CornerRadius = innerFocus;
            if (focusWash is not null) focusWash.CornerRadius = innerFocus;
            if (edge is not null)
            {
                var inset = theme.Px(1);
                edge.Margin = new Thickness(inset);
                edge.BorderThickness = new Thickness(Math.Max(.75, theme.Px(.9)));
                edge.CornerRadius = GmOutline.Inset(corners, new Thickness(inset));
            }
        }

        public void Update()
        {
            if (!loaded || mask is null) return;
            if (ExternalSurface)
            {
                mask.Fill = button.Background;
                halo?.Set(theme.Active, 0, inViewport); SetEdge(theme.Active, 0); return;
            }
            var focused = button.FocusState is FocusState.Keyboard or FocusState.Programmatic;
            var selected = Selected || button.Background is SolidColorBrush brush &&
                (brush.Color == theme.Active || brush.Color == theme.SegmentSelected);
            var on = button.IsEnabled && inViewport && (focused || selected || pointer);
            if (on && halo is null)
            {
                host = layer?.AddControl(button) ?? Find<Canvas>(button, "GlowHost");
                if (host is not null) { halo = new GlowHalo(host, mask.GetAlphaMask(), theme); Resize(); }
            }
            if (halo is null) return;
            layer?.RefreshControl(button);
            // Transparent controls get a quiet focus surface; the mask is also their visible fill.
            mask.Fill = on && button.Background is SolidColorBrush { Color.A: 0 }
                ? GmTheme.B(theme.RowFocus)
                : button.Background;
            var color = (button.Content is Border contentSurface ? Surface(contentSurface.Background) : null)
                ?? Surface(button.Background)
                ?? Surface(mask.Fill) ?? theme.Card;
            var opacity = !on ? 0f : focused ? .85f : selected ? .72f : .64f;
            halo.Set(color, opacity, inViewport);
            // Artwork and outlined controls already have an edge. Keyboard focus has its own ring.
            var needsEdge = on && !focused && !HasStroke(button.BorderBrush, button.BorderThickness)
                && !(button.Content is Border content && HasStroke(content.BorderBrush, content.BorderThickness));
            SetEdge(color, needsEdge ? theme.IsLight ? .27f : .21f : 0);
        }

        void SetEdge(global::Windows.UI.Color color, float opacity)
        {
            if (edge is null) return;
            edge.BorderBrush = GmTheme.B(GlowHalo.Richer(color));
            if (edgeLevel == opacity) return;
            edgeLevel = opacity;
            var visual = ElementCompositionPreview.GetElementVisual(edge);
            visual.StopAnimation("Opacity");
            if (!GmUi.Animations || !inViewport) { visual.Opacity = opacity; return; }
            using var transition = visual.Compositor.CreateScalarKeyFrameAnimation();
            using var ease = GmMotion.Ease(visual.Compositor);
            transition.InsertExpressionKeyFrame(0, "this.StartingValue");
            transition.InsertKeyFrame(1, opacity, ease);
            transition.Duration = TimeSpan.FromMilliseconds(150);
            visual.StartAnimation("Opacity", transition);
        }
    }

    static bool HasStroke(Brush? brush, Thickness thickness) => brush is not null && brush.Opacity > 0
        && (brush is not SolidColorBrush solid || solid.Color.A > 0)
        && (thickness.Left > 0 || thickness.Top > 0 || thickness.Right > 0 || thickness.Bottom > 0);

    static global::Windows.UI.Color? Surface(Brush? brush) => brush switch
    {
        SolidColorBrush solid when solid.Color.A > 0 && solid.Opacity > 0 => solid.Color,
        AcrylicBrush acrylic when acrylic.Opacity > 0 => acrylic.TintColor,
        _ => null,
    };

    static bool InViewport(FrameworkElement element, global::Windows.Foundation.Rect viewport) =>
        viewport.Width > 0 && viewport.Height > 0 && viewport.X < element.ActualWidth && viewport.Y < element.ActualHeight
        && viewport.X + viewport.Width > 0 && viewport.Y + viewport.Height > 0;

    static T? Find<T>(DependencyObject root, string name) where T : FrameworkElement
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++)
        {
            var child = VisualTreeHelper.GetChild(root, i);
            if (child is T item && item.Name == name) return item;
            if (Find<T>(child, name) is { } nested) return nested;
        }
        return null;
    }
}
