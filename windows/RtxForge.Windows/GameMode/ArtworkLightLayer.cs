using System.Numerics;
using Microsoft.Graphics.Canvas;
using Microsoft.Graphics.Canvas.UI.Composition;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.Graphics.DirectX;

namespace RtxForge.Windows.GameMode;

/// <summary>Shared light overlay: control halos and blurred artwork escape their surrounding panels.</summary>
sealed class ArtworkLightLayer : Canvas
{
    // Artwork light is below the foreground; control halos use an outside-only mask above it.
    public Canvas Artwork { get; } = new() { IsHitTestVisible = false };
    sealed record Entry(Control Target, Border Artwork, GmTheme Theme, string Source, bool Hovered);
    readonly Dictionary<Control, Entry> active = [];
    readonly Dictionary<FrameworkElement, Canvas> controls = [];
    Entry? current;
    CompositionGraphicsDevice? graphics;
    CompositionDrawingSurface? surface;
    CompositionSurfaceBrush? source;
    SpriteVisual? light;
    CanvasBitmap? image;
    readonly Dictionary<string, CanvasBitmap> bitmapCache = [];
    readonly Queue<string> bitmapOrder = [];
    int generation;
    Vector2 lastSize;
    float level = -1;

    public ArtworkLightLayer()
    {
        IsHitTestVisible = false;
        LayoutUpdated += (_, _) => RefreshPositions();
        Unloaded += (_, _) => { active.Clear(); current = null; Release(); foreach (var bitmap in bitmapCache.Values) bitmap.Dispose(); bitmapCache.Clear(); bitmapOrder.Clear(); graphics?.Dispose(); graphics = null; };
    }

    public Canvas AddControl(FrameworkElement target)
    {
        var host = new Canvas { IsHitTestVisible = false };
        controls.Add(target, host); Children.Add(host);
        Position(target, host);
        return host;
    }

    public void RemoveControl(FrameworkElement target)
    {
        if (controls.Remove(target, out var host)) Children.Remove(host);
    }

    public void RefreshPositions()
    {
        foreach (var (target, host) in controls) Position(target, host);
        Reposition();
    }

    public void RefreshControl(FrameworkElement target)
    {
        if (controls.TryGetValue(target, out var host)) Position(target, host);
    }

    void Position(FrameworkElement target, Canvas host)
    {
        if (!target.IsLoaded || !IsLoaded) return;
        var point = RestPoint(target);
        if (GetLeft(host) != point.X) SetLeft(host, point.X);
        if (GetTop(host) != point.Y) SetTop(host, point.Y);
        if (ElementCompositionPreview.GetElementChildVisual(host) is { } haloVisual)
            GmMotion.Follow(target, haloVisual, Vector3.Zero,
                new((float)target.ActualWidth / 2, (float)target.ActualHeight / 2, 0), true);
    }

    global::Windows.Foundation.Point RestPoint(FrameworkElement target)
    {
        if (Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(target) is not UIElement parent)
            return target.TransformToVisual(this).TransformPoint(new(0, 0));
        return parent.TransformToVisual(this).TransformPoint(new(target.ActualOffset.X, target.ActualOffset.Y));
    }

    public void Track(Control target, Border artwork, bool selected, GmTheme theme, string imageSource)
    {
        bool pointer = false, visible = true;
        ArtworkLightLayer Destination() => GmGlow.Destination(target) ?? this;
        void Update()
        {
            if (target.IsEnabled && artwork.IsLoaded && visible &&
                (pointer || selected || target.FocusState != FocusState.Unfocused))
                Destination().Show(new Entry(target, artwork, theme, imageSource, pointer));
            else Destination().Hide(target);
        }
        target.GotFocus += (_, _) => Update();
        target.LostFocus += (_, _) => Update();
        target.PointerEntered += (_, _) => { pointer = true; Update(); };
        target.PointerExited += (_, _) => { pointer = false; Update(); };
        target.PointerMoved += (_, _) => { if (!pointer) { pointer = true; Update(); } };
        long enabledToken = 0;
        artwork.Loaded += (_, _) =>
        {
            enabledToken = target.RegisterPropertyChangedCallback(Control.IsEnabledProperty, (_, _) => Update());
            Update();
        };
        artwork.Unloaded += (_, _) =>
        {
            if (enabledToken != 0) target.UnregisterPropertyChangedCallback(Control.IsEnabledProperty, enabledToken);
            enabledToken = 0; Destination().Hide(target);
        };
        artwork.EffectiveViewportChanged += (_, e) =>
        {
            var v = e.EffectiveViewport;
            visible = v.Width > 0 && v.Height > 0 && v.X < artwork.ActualWidth && v.Y < artwork.ActualHeight
                && v.X + v.Width > 0 && v.Y + v.Height > 0;
            Update(); Destination().Reposition();
        };
        if (artwork.IsLoaded)
            enabledToken = target.RegisterPropertyChangedCallback(Control.IsEnabledProperty, (_, _) => Update());
        Update();
    }

    void Show(Entry entry)
    {
        active.Remove(entry.Target); active[entry.Target] = entry;
        Display(Owner());
    }

    Entry? Owner() => active.Values.LastOrDefault(entry => entry.Hovered) ?? active.Values.LastOrDefault();

    void Display(Entry? entry)
    {
        if (ReferenceEquals(current?.Target, entry?.Target)) { current = entry; Reposition(); return; }
        current = entry;
        if (entry is null) { SetOpacity(0); return; }
        Release();
        _ = LoadAsync(entry, generation);
    }

    async Task LoadAsync(Entry entry, int request)
    {
        CanvasBitmap? loaded = null;
        try
        {
            if (bitmapCache.TryGetValue(entry.Source, out var cached)) image = cached;
            else
            {
                var device = CanvasDevice.GetSharedDevice();
                loaded = entry.Source.StartsWith("https://", StringComparison.OrdinalIgnoreCase)
                    ? await CanvasBitmap.LoadAsync(device, new Uri(entry.Source))
                    : await CanvasBitmap.LoadAsync(device, entry.Source);
                if (request != generation || !ReferenceEquals(current?.Target, entry.Target)) { loaded.Dispose(); return; }
                image = loaded; bitmapCache[entry.Source] = loaded; bitmapOrder.Enqueue(entry.Source); loaded = null;
                while (bitmapOrder.Count > 6)
                {
                    var oldest = bitmapOrder.Dequeue();
                    if (bitmapCache.Remove(oldest, out var expired)) expired.Dispose();
                }
            }
            Draw(entry);
            Reposition();
            SetOpacity(.72f);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException or System.Runtime.InteropServices.COMException)
        {
            loaded?.Dispose();
            if (request == generation) { Release(); current = null; }
            System.Diagnostics.Debug.WriteLine($"Artwork light: {error.Message}");
        }
    }

    void Draw(Entry entry)
    {
        if (image is null || !entry.Artwork.IsLoaded) return;
        var width = (float)entry.Artwork.ActualWidth;
        var height = (float)entry.Artwork.ActualHeight;
        if (width <= 0 || height <= 0) return;
        var compositor = ElementCompositionPreview.GetElementVisual(Artwork).Compositor;
        graphics ??= CanvasComposition.CreateCompositionGraphicsDevice(compositor, image.Device);
        using var rendered = ArtworkGlowRenderer.Render(image, width, height, (float)entry.Artwork.CornerRadius.TopLeft,
            (float)entry.Theme.Px(24), (float)entry.Theme.Px(16));
        if (surface is null)
        {
            surface = graphics.CreateDrawingSurface(rendered.Size, DirectXPixelFormat.B8G8R8A8UIntNormalized, DirectXAlphaMode.Premultiplied);
            source = compositor.CreateSurfaceBrush(surface);
            light = compositor.CreateSpriteVisual(); light.Brush = source; light.Opacity = 0;
            ElementCompositionPreview.SetElementChildVisual(Artwork, light);
        }
        else CanvasComposition.Resize(surface, rendered.Size);
        using (var drawing = CanvasComposition.CreateDrawingSession(surface))
        {
            drawing.Clear(Microsoft.UI.Colors.Transparent);
            drawing.DrawImage(rendered);
        }
        lastSize = new(width, height);
        light!.Size = new((float)rendered.Size.Width, (float)rendered.Size.Height);
    }

    void Hide(Control target)
    {
        active.Remove(target);
        Display(Owner());
    }

    public void Reposition()
    {
        if (current is not { } entry || image is null) return;
        var art = entry.Artwork;
        if (!art.IsLoaded || art.ActualWidth <= 0 || art.ActualHeight <= 0) return;
        var owner = RestPoint(entry.Target);
        var local = art.TransformToVisual(entry.Target).TransformPoint(new(0, 0));
        var point = new global::Windows.Foundation.Point(owner.X + local.X, owner.Y + local.Y);
        var width = (float)art.ActualWidth; var height = (float)art.ActualHeight;
        var size = new Vector2(width, height);
        if (lastSize != size) Draw(entry);
        var bleed = ArtworkGlowRenderer.Bleed((float)entry.Theme.Px(24), (float)entry.Theme.Px(16));
        if (light is not null)
        {
            var offset = new Vector3((float)point.X - bleed, (float)point.Y - bleed, 0);
            light.Offset = offset;
            GmMotion.Follow(entry.Target, light, offset,
                new((float)owner.X + (float)entry.Target.ActualWidth / 2 - offset.X,
                    (float)owner.Y + (float)entry.Target.ActualHeight / 2 - offset.Y, 0));
        }
    }

    void SetOpacity(float opacity)
    {
        if (light is null || level == opacity) return;
        level = opacity; light.StopAnimation("Opacity");
        if (!GmUi.Animations) { light.Opacity = opacity; return; }
        using var fade = light.Compositor.CreateScalarKeyFrameAnimation();
        using var ease = GmMotion.Ease(light.Compositor);
        fade.InsertExpressionKeyFrame(0, "this.StartingValue"); fade.InsertKeyFrame(1, opacity, ease);
        fade.Duration = TimeSpan.FromMilliseconds(140); light.StartAnimation("Opacity", fade);
    }

    void Release()
    {
        generation++;
        ElementCompositionPreview.SetElementChildVisual(Artwork, null);
        light?.Dispose(); source?.Dispose(); surface?.Dispose();
        light = null; source = null; surface = null; image = null;
        lastSize = default; level = -1;
    }
}
