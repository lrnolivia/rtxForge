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
    Vector2? chosen;

    /// <summary>A focal point the person chose for this art (fractions of it); null follows the automatic one.</summary>
    public Vector2? ChosenFocus
    {
        get => chosen;
        set { chosen = value; Align(); }
    }

    /// <summary>The stored choice for a game, from Settings › game_hero_focus.</summary>
    public static Vector2? Stored(IReadOnlyDictionary<string, double[]> choices, string gameId) =>
        choices.TryGetValue(gameId, out var point) && point is [var x, var y] && x is >= 0 and <= 1 && y is >= 0 and <= 1
            ? new Vector2((float)x, (float)y) : null;

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
        var point = chosen ?? focus;
        surface.HorizontalAlignmentRatio = Ratio(width, natural.X * scale, point.X, 0.5f);
        surface.VerticalAlignmentRatio = Ratio(height, natural.Y * scale, point.Y, FocusHeight);
    }

    // The art's offset is (view - shown) * ratio; solve for the focal point landing at target * view.
    static float Ratio(float view, float shown, float focal, float target) =>
        shown - view < 0.5f ? 0.5f : Math.Clamp((target * view - focal * shown) / (view - shown), 0f, 1f);

    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(10) };

    async Task FindFocusAsync(string path)
    {
        var remote = path.StartsWith("https://", StringComparison.OrdinalIgnoreCase);
        if (!remote && !File.Exists(path)) return;
        if (!Foci.TryGetValue(path, out var found))
        {
            try
            {
                // Store art (and preview art) arrives by URL; local art is read from disk.
                var data = remote ? await Http.GetByteArrayAsync(path) : null;
                found = await Task.Run(async () =>
                {
                    using Stream stream = data is null ? File.OpenRead(path) : new MemoryStream(data);
                    return await AnalyzeAsync(stream);
                });
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException or InvalidOperationException
                                          or HttpRequestException or TaskCanceledException or System.Runtime.InteropServices.COMException) { return; }
            Foci[path] = found;
        }
        if (path != source) return;
        focus = found;
        Align();
    }

    /// <summary>
    /// The art's focal point. Saliency frames the whole subject (a character's body, not just
    /// their face), so it leads. A detected face checks it: when saliency lands more than three
    /// quarters of a face away, it was pulled off the subject (other figures, painted backdrops),
    /// and the face leads instead.
    /// </summary>
    static async Task<Vector2> AnalyzeAsync(Stream file)
    {
        var decoder = await BitmapDecoder.CreateAsync(file.AsRandomAccessStream());
        var salient = await SaliencyFocusAsync(decoder);
        return await FaceFocusAsync(decoder) is { } face && Math.Abs(face.Center.X - salient.X) > face.Width * .75f
            ? new(face.Center.X, salient.Y)
            : salient;
    }

    /// <summary>
    /// Faces in the art (the on-device Windows face detector; it finds human faces only). The
    /// largest face leads; others close to its size pull the center toward a group.
    /// </summary>
    static async Task<(Vector2 Center, float Width)?> FaceFocusAsync(BitmapDecoder decoder)
    {
        if (!global::Windows.Media.FaceAnalysis.FaceDetector.IsSupported) return null;
        const int width = 1600;
        var height = Math.Max(1, (int)Math.Round(width * (double)decoder.PixelHeight / decoder.PixelWidth));
        using var color = await decoder.GetSoftwareBitmapAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Ignore,
            new BitmapTransform { ScaledWidth = width, ScaledHeight = (uint)height, InterpolationMode = BitmapInterpolationMode.Fant },
            ExifOrientationMode.RespectExifOrientation, ColorManagementMode.DoNotColorManage);
        using var gray = SoftwareBitmap.Convert(color, BitmapPixelFormat.Gray8);
        var detector = await global::Windows.Media.FaceAnalysis.FaceDetector.CreateAsync();
        detector.MinDetectableFaceSize = new BitmapSize { Width = 24, Height = 24 };
        var faces = await detector.DetectFacesAsync(gray);
        if (faces.Count == 0) return null;
        var largest = faces.Max(face => face.FaceBox.Width);
        double x = 0, y = 0, total = 0;
        foreach (var box in faces.Select(face => face.FaceBox).Where(box => box.Width >= largest * .7))
        {
            double area = box.Width * (double)box.Height;
            x += (box.X + box.Width / 2.0) * area; y += (box.Y + box.Height / 2.0) * area; total += area;
        }
        return (new((float)(x / total / width), (float)(y / total / height)), (float)(largest / (double)width));
    }

    /// <summary>
    /// The art's horizontal focus from a small copy. Each column scores local contrast times how far
    /// its colors stand from the image's average color, so a character outweighs a textured backdrop
    /// in the art's own palette (city, foliage, snow). The smoothed profile is sharpened toward its
    /// peak before taking its center. Hero art is wide, so only the horizontal
    /// crop needs it; the vertical position keeps the default, clear of the outer rows' letterbox
    /// bars and logo strips.
    /// </summary>
    static async Task<Vector2> SaliencyFocusAsync(BitmapDecoder decoder)
    {
        const int width = 96;
        var height = Math.Max(3, (int)Math.Round(width * (double)decoder.PixelHeight / decoder.PixelWidth));
        var data = await decoder.GetPixelDataAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Ignore,
            new BitmapTransform { ScaledWidth = width, ScaledHeight = (uint)height, InterpolationMode = BitmapInterpolationMode.Fant },
            ExifOrientationMode.RespectExifOrientation, ColorManagementMode.DoNotColorManage);
        var pixels = data.DetachPixelData();
        var count = width * height;
        var light = new double[count];
        var rgb = new (double R, double G, double B)[count];
        double meanR = 0, meanG = 0, meanB = 0;
        for (var i = 0; i < count; i++)
        {
            double b = pixels[i * 4] / 255.0, g = pixels[i * 4 + 1] / 255.0, r = pixels[i * 4 + 2] / 255.0;
            rgb[i] = (r, g, b);
            light[i] = 0.299 * r + 0.587 * g + 0.114 * b;
            meanR += r; meanG += g; meanB += b;
        }
        meanR /= count; meanG /= count; meanB /= count;

        var columns = new double[width];
        int top = Math.Max(1, (int)(height * .08)), bottom = Math.Min(height - 2, (int)(height * .92));
        for (var y = top; y <= bottom; y++)
            for (var x = 1; x < width - 1; x++)
            {
                var i = y * width + x;
                var edge = Math.Abs(light[i + 1] - light[i - 1]) + Math.Abs(light[i + width] - light[i - width]);
                var (r, g, b) = rgb[i];
                var distinct = Math.Sqrt((r - meanR) * (r - meanR) + (g - meanG) * (g - meanG) + (b - meanB) * (b - meanB));
                columns[x] += edge * distinct;
            }

        const int radius = 6;
        var smooth = new double[width];
        for (var x = 0; x < width; x++)
        {
            double sum = 0; var n = 0;
            for (var k = Math.Max(0, x - radius); k <= Math.Min(width - 1, x + radius); k++) { sum += columns[k]; n++; }
            smooth[x] = sum / n;
        }
        var peak = smooth.Max();
        if (peak <= 0) return DefaultFocus;
        double weighted = 0, total = 0;
        for (var x = 0; x < width; x++)
        {
            var weight = Math.Pow(smooth[x] / peak, 8);
            weighted += x * weight; total += weight;
        }
        return new((float)(weighted / total / (width - 1)), DefaultFocus.Y);
    }
}
