using System.Numerics;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.Controls;

/// <summary>
/// Hero artwork that fades to transparent toward the bottom (Linux
/// .banner-shade), so it blends into whatever is behind it — Mica, Light,
/// Dark or Night — instead of into a fixed color.
/// </summary>
public sealed class FadedImage : Grid
{
    SpriteVisual? sprite;
    CompositionSurfaceBrush? surface;
    LoadedImageSurface? image;

    /// <summary>Where the fade starts and how far it reaches (0 top, 1 bottom).</summary>
    public float FadeStart { get; set; } = 0.25f;

    public FadedImage()
    {
        SizeChanged += (_, _) => Resize();
        Unloaded += (_, _) => { image?.Dispose(); image = null; };
    }

    public void SetSource(string? source)
    {
        image?.Dispose();
        image = null;
        if (sprite is null) Build();
        if (source is null || surface is null) { if (surface is not null) surface.Surface = null; return; }
        image = source.StartsWith("https://", StringComparison.OrdinalIgnoreCase) || File.Exists(source)
            ? LoadedImageSurface.StartLoadFromUri(new Uri(source))
            : null;
        surface.Surface = image;
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
    }
}
