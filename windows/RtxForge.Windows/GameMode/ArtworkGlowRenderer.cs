using System.Numerics;
using Microsoft.Graphics.Canvas;
using Microsoft.Graphics.Canvas.Effects;
using Microsoft.UI;
using Windows.Foundation;

namespace RtxForge.Windows.GameMode;

/// <summary>Steam-style light from the artwork's pixels, with transparent room for its blur.</summary>
static class ArtworkGlowRenderer
{
    public static float Bleed(float blur, float offset) => MathF.Ceiling(blur * 2.35f * 3 + offset);

    public static CanvasRenderTarget Render(CanvasBitmap image, float width, float height, float radius, float blur, float offset)
    {
        var device = image.Device;
        var bleed = Bleed(blur, offset);
        using var crop = new CanvasRenderTarget(device, width * .96f, height * .96f, 96);
        using (var drawing = crop.CreateDrawingSession())
        {
            drawing.Clear(Colors.Transparent);
            var scale = Math.Max(crop.Size.Width / image.Size.Width, crop.Size.Height / image.Size.Height);
            var sourceWidth = crop.Size.Width / scale;
            var sourceHeight = crop.Size.Height / scale;
            var sourceRect = new Rect((image.Size.Width - sourceWidth) / 2, (image.Size.Height - sourceHeight) / 2, sourceWidth, sourceHeight);
            drawing.DrawImage(image, new Rect(0, 0, crop.Size.Width, crop.Size.Height), sourceRect);
        }
        using var saturation = new SaturationEffect { Saturation = 1.6f, Source = crop };
        using var brightness = new ColorMatrixEffect
        {
            ColorMatrix = new Matrix5x4 { M11 = 1.35f, M22 = 1.35f, M33 = 1.35f, M44 = 1 },
            ClampOutput = true, Source = saturation,
        };
        using var softened = new GaussianBlurEffect { BlurAmount = blur, BorderMode = EffectBorderMode.Soft, Source = brightness };
        using var spread = new Transform2DEffect { Source = brightness, TransformMatrix = Matrix3x2.CreateScale(1.10f) };
        using var bloom = new GaussianBlurEffect { BlurAmount = blur * 2.35f, BorderMode = EffectBorderMode.Soft, Source = spread };
        var output = new CanvasRenderTarget(device, MathF.Ceiling(width + bleed * 2), MathF.Ceiling(height + bleed * 2), 96);
        using (var drawing = output.CreateDrawingSession())
        {
            drawing.Clear(Colors.Transparent);
            using (drawing.CreateLayer(.55f))
                drawing.DrawImage(bloom, new Vector2(bleed + (width - (float)crop.Size.Width * 1.10f) / 2,
                    bleed + (height - (float)crop.Size.Height * 1.10f) / 2 + offset));
            drawing.DrawImage(softened, new Vector2(bleed + width * .02f, bleed + height * .02f + offset));
            // Light is composited above the page. Cut out its owner so the image and its stroke remain crisp.
            drawing.Blend = CanvasBlend.Copy;
            drawing.FillRoundedRectangle(bleed, bleed, width, height, radius, radius, Colors.Transparent);
        }
        return output;
    }
}
