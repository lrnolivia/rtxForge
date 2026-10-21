using System.Numerics;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Media;
using Windows.Graphics.Imaging;

namespace RtxForge.Windows.Controls;

/// <summary>
/// Hero artwork that fades to transparent toward the bottom (Linux
/// .banner-shade), so it blends into whatever is behind it — Mica, Light,
/// Dark or Night — instead of into a fixed color. The crop follows the art's
/// focal point, so its subject stays in view as the window resizes.
/// </summary>
public sealed class FadedImage : Grid
{
    SpriteVisual? sprite;
    CompositionSurfaceBrush? surface;
    LoadedImageSurface? image;

    /// <summary>Where the fade starts and how far it reaches (0 top, 1 bottom).</summary>
    public float FadeStart { get; set; } = 0.25f;

    /// <summary>Where the focal point sits vertically when the crop allows (0 top, 1 bottom), above text over the fade.</summary>
    public float FocusHeight { get; set; } = 0.4f;

    static readonly Vector2 DefaultFocus = new(0.5f, 0.3f);
    static readonly Dictionary<string, Vector2> Foci = [];
    string? source;
    Vector2 focus = DefaultFocus;
    Vector2 natural;

    public FadedImage()
    {
        SizeChanged += (_, _) => Resize();
        // A move between parents can raise Loaded before Unloaded; release the art only once it is really gone.
        Unloaded += (_, _) => DispatcherQueue.TryEnqueue(() => { if (!IsLoaded) { image?.Dispose(); image = null; } });
        // Moving the hero between layouts unloads and reloads it; reattach the art.
        Loaded += (_, _) => Reattach();
    }

    /// <summary>After the element moves to another parent: attach the art visual again, sized to the new slot.</summary>
    public void Reattach()
    {
        if (sprite is not null) { ElementCompositionPreview.SetElementChildVisual(this, sprite); Resize(); }
        if (image is null && source is not null) SetSource(source);
    }

    public void SetSource(string? source)
    {
        var changed = this.source != source;
        this.source = source;
        image?.Dispose();
        image = null;
        if (changed) { focus = DefaultFocus; natural = default; }
        if (sprite is null) Build();
        if (source is null || surface is null) { if (surface is not null) surface.Surface = null; return; }
        image = source.StartsWith("https://", StringComparison.OrdinalIgnoreCase) || File.Exists(source)
            ? LoadedImageSurface.StartLoadFromUri(new Uri(source))
            : null;
        if (image is not null)
            image.LoadCompleted += (loaded, e) =>
            {
                if (loaded != image || e.Status != LoadedImageSourceLoadStatus.Success) return;
                natural = new((float)loaded.NaturalSize.Width, (float)loaded.NaturalSize.Height);
                Align();
            };
        surface.Surface = image;
        _ = FindFocusAsync(source);
    }

    void Build()
    {
        var compositor = ElementCompositionPreview.GetElementVisual(this).Compositor;
        surface = compositor.CreateSurfaceBrush();
        surface.Stretch = CompositionStretch.UniformToFill;
        surface.HorizontalAlignmentRatio = 0.5f;
        surface.VerticalAlignmentRatio = 0.3f;

        var fade = compositor.CreateLinearGradientBrush();
        fade.StartPoint = new Vector2(0, 0);
        fade.EndPoint = new Vector2(0, 1);
        // Smootherstep from FadeStart to the bottom; many stops so the linear
        // interpolation between them never shows a visible band or knee.
        fade.ColorStops.Add(compositor.CreateColorGradientStop(0f, Opaque(1)));
        const int steps = 16;
        for (var i = 0; i <= steps; i++)
        {
            var t = i / (float)steps;
            var eased = t * t * t * (t * (t * 6 - 15) + 10);
            fade.ColorStops.Add(compositor.CreateColorGradientStop(FadeStart + (1 - FadeStart) * t, Opaque(1 - eased)));
        }

        var mask = compositor.CreateMaskBrush();
        mask.Source = surface;
        mask.Mask = fade;

        sprite = compositor.CreateSpriteVisual();
        sprite.Brush = mask;
        ElementCompositionPreview.SetElementChildVisual(this, sprite);
        Resize();
    }

    static global::Windows.UI.Color Opaque(float alpha) => global::Windows.UI.Color.FromArgb((byte)(alpha * 255), 255, 255, 255);

    void Resize()
    {
        if (sprite is not null) sprite.Size = new Vector2((float)ActualWidth, (float)ActualHeight);
        Align();
    }

    /// <summary>
    /// Places the crop so the focal point sits at the center (and FocusHeight) of the view when
    /// the art overflows it; where it cannot, the crop stops at the art's edge. Either way the
    /// subject stays in view at any size.
    /// </summary>
    void Align()
    {
        if (surface is null || natural.X <= 0 || natural.Y <= 0 || ActualWidth <= 0 || ActualHeight <= 0) return;
        float width = (float)ActualWidth, height = (float)ActualHeight;
        var scale = Math.Max(width / natural.X, height / natural.Y);
        surface.HorizontalAlignmentRatio = Ratio(width, natural.X * scale, focus.X, 0.5f);
        surface.VerticalAlignmentRatio = Ratio(height, natural.Y * scale, focus.Y, FocusHeight);
    }

    // The art's offset is (view - shown) * ratio; solve for the focal point landing at target * view.
    static float Ratio(float view, float shown, float focal, float target) =>
        shown - view < 0.5f ? 0.5f : Math.Clamp((target * view - focal * shown) / (view - shown), 0f, 1f);

    async Task FindFocusAsync(string path)
    {
        if (!File.Exists(path)) return;
        if (!Foci.TryGetValue(path, out var found))
        {
            try { found = await Task.Run(() => Analyze(path)); }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException or InvalidOperationException
                                          or System.Runtime.InteropServices.COMException) { return; }
            Foci[path] = found;
        }
        if (path != source) return;
        focus = found;
        Align();
    }

    /// <summary>
    /// The art's visual focus from a small copy: the centroid of edge contrast, weighted toward
    /// saturated color, so a character or subject outweighs flat sky and empty logo space.
    /// </summary>
    static Vector2 Analyze(string path)
    {
        using var file = File.OpenRead(path);
        var decoder = BitmapDecoder.CreateAsync(file.AsRandomAccessStream()).AsTask().GetAwaiter().GetResult();
        const int width = 96;
        var height = Math.Max(3, (int)Math.Round(width * (double)decoder.PixelHeight / decoder.PixelWidth));
        var data = decoder.GetPixelDataAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Ignore,
            new BitmapTransform { ScaledWidth = width, ScaledHeight = (uint)height, InterpolationMode = BitmapInterpolationMode.Fant },
            ExifOrientationMode.RespectExifOrientation, ColorManagementMode.DoNotColorManage).AsTask().GetAwaiter().GetResult();
        var pixels = data.DetachPixelData();
        var light = new float[width * height];
        var color = new float[width * height];
        for (var i = 0; i < light.Length; i++)
        {
            int b = pixels[i * 4], g = pixels[i * 4 + 1], r = pixels[i * 4 + 2];
            light[i] = (0.299f * r + 0.587f * g + 0.114f * b) / 255f;
            color[i] = (Math.Max(r, Math.Max(g, b)) - Math.Min(r, Math.Min(g, b))) / 255f;
        }
        double sumX = 0, sumY = 0, total = 0;
        for (var y = 1; y < height - 1; y++)
            for (var x = 1; x < width - 1; x++)
            {
                var i = y * width + x;
                var edge = Math.Abs(light[i + 1] - light[i - 1]) + Math.Abs(light[i + width] - light[i - width]);
                var weight = Math.Pow(edge * (0.5 + color[i]), 2);
                sumX += x * weight; sumY += y * weight; total += weight;
            }
        return total <= 0 ? DefaultFocus
            : new((float)(sumX / total / (width - 1)), (float)(sumY / total / (height - 1)));
    }
}
