using System.Numerics;
using Microsoft.Graphics.Canvas;
using Microsoft.Graphics.Canvas.Geometry;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;
using Windows.UI;

namespace RtxForge.Windows.GameMode;

/// <summary>Two fixed diffuse light pools; only their opacity responds to contact.</summary>
sealed class GlowHalo : IDisposable
{
    readonly ContainerVisual root;
    readonly SpriteVisual core, bloom;
    readonly DropShadow coreShadow, bloomShadow;
    readonly GmTheme theme;
    CanvasGeometry? geometry;
    CompositionPathGeometry? path;
    CompositionGeometricClip? cutout;
    Vector2 clipSize;
    CornerRadius clipCorners;
    float level = -1;

    public GlowHalo(Canvas host, CompositionBrush mask, GmTheme theme)
    {
        this.theme = theme;
        var compositor = ElementCompositionPreview.GetElementVisual(host).Compositor;
        root = compositor.CreateContainerVisual(); root.Opacity = 0;
        coreShadow = compositor.CreateDropShadow(); coreShadow.Mask = mask;
        bloomShadow = compositor.CreateDropShadow(); bloomShadow.Mask = mask;
        core = compositor.CreateSpriteVisual(); core.Shadow = coreShadow;
        bloom = compositor.CreateSpriteVisual(); bloom.Shadow = bloomShadow;
        root.Children.InsertAtBottom(bloom); root.Children.InsertAtTop(core);
        ElementCompositionPreview.SetElementChildVisual(host, root);
        SetStatic();
    }

    public void Resize(double width, double height, CornerRadius corners, bool outsideOnly = false)
    {
        root.Size = new Vector2((float)width, (float)height);
        core.Size = bloom.Size = new Vector2((float)width, (float)height);
        bloom.Offset = new Vector3(-(float)theme.Px(3), 0, 0);
        var size = new Vector2((float)width, (float)height);
        if (!outsideOnly || width <= 0 || height <= 0 || clipSize == size && clipCorners.Equals(corners)) return;
        clipSize = size; clipCorners = corners;
        root.Clip = null;
        cutout?.Dispose(); path?.Dispose(); geometry?.Dispose();
        var device = CanvasDevice.GetSharedDevice();
        var bleed = (float)theme.Px(160);
        using var outside = CanvasGeometry.CreateRectangle(device, -bleed, -bleed, (float)width + bleed * 2, (float)height + bleed * 2);
        using var inside = GmOutline.Surface(device, (float)width, (float)height, corners);
        geometry = outside.CombineWith(inside, Matrix3x2.Identity, CanvasGeometryCombine.Exclude);
        path = root.Compositor.CreatePathGeometry(new CompositionPath(geometry));
        cutout = root.Compositor.CreateGeometricClip(path); root.Clip = cutout;
    }

    public void SetMask(CompositionBrush mask) { coreShadow.Mask = mask; bloomShadow.Mask = mask; }

    public void Set(Color color, float intensity, bool visible)
    {
        coreShadow.Color = Richer(color);
        bloomShadow.Color = Richer(color);
        if (!visible) intensity = 0;
        if (theme.IsLight) intensity *= .52f;
        var animate = GmUi.Animations;
        if (level == intensity) return;
        level = intensity;
        root.StopAnimation("Opacity");
        if (!animate || !visible) { root.Opacity = intensity; return; }
        using var arrival = root.Compositor.CreateScalarKeyFrameAnimation();
        using var ease = GmMotion.Ease(root.Compositor);
        arrival.InsertExpressionKeyFrame(0, "this.StartingValue");
        arrival.InsertKeyFrame(1, intensity, ease);
        arrival.Duration = TimeSpan.FromMilliseconds(intensity > 0 ? GmMotionTokens.Focus : GmMotionTokens.Fade);
        root.StartAnimation("Opacity", arrival);
    }

    void SetStatic()
    {
        core.StopAnimation("Opacity"); bloom.StopAnimation("Opacity");
        bloom.StopAnimation("Offset"); coreShadow.StopAnimation("BlurRadius"); bloomShadow.StopAnimation("BlurRadius");
        core.Opacity = .74f; bloom.Opacity = .56f;
        coreShadow.BlurRadius = (float)theme.Px(21);
        bloomShadow.BlurRadius = (float)theme.Px(39);
        coreShadow.Offset = new Vector3(0, (float)theme.Px(1), 0);
        bloomShadow.Offset = new Vector3(0, (float)theme.Px(3), 0);
        bloom.Offset = new Vector3(-(float)theme.Px(3), 0, 0);
    }

    public static Color Richer(Color color)
    {
        var high = Math.Max(color.R, Math.Max(color.G, color.B)) / 255f;
        var low = Math.Min(color.R, Math.Min(color.G, color.B)) / 255f;
        var saturation = high == 0 ? 0 : (high - low) / high;
        if (saturation < .08f)
        {
            var value = Math.Max(high, .56f);
            byte Neutral(byte channel) => (byte)Math.Clamp(Math.Round((high > 0 ? channel / 255f / high : 1) * value * 255), 0, 255);
            return Color.FromArgb(255, Neutral(color.R), Neutral(color.G), Neutral(color.B));
        }
        var richer = Math.Min(1, saturation * 1.22f + .06f) / saturation;
        var brighter = Math.Max(.64f, Math.Min(1, high * 1.10f)) / high;
        byte Channel(byte channel) => (byte)Math.Clamp(Math.Round((high - (high - channel / 255f) * richer) * brighter * 255), 0, 255);
        return Color.FromArgb(255, Channel(color.R), Channel(color.G), Channel(color.B));
    }

    public void Dispose()
    {
        SetStatic(); root.StopAnimation("Opacity");
        root.Dispose(); core.Dispose(); bloom.Dispose(); coreShadow.Dispose(); bloomShadow.Dispose();
        cutout?.Dispose(); path?.Dispose(); geometry?.Dispose();
    }
}
