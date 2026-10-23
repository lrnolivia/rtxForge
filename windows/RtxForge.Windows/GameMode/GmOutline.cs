using System.Numerics;
using Microsoft.Graphics.Canvas;
using Microsoft.Graphics.Canvas.Geometry;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.GameMode;

/// <summary>The same four corners for a surface, its focus stroke, and its light.</summary>
static class GmOutline
{
    public static CornerRadius Inset(CornerRadius radius, Thickness inset) => new(
        Math.Max(0, radius.TopLeft - Math.Max(inset.Top, inset.Left)),
        Math.Max(0, radius.TopRight - Math.Max(inset.Top, inset.Right)),
        Math.Max(0, radius.BottomRight - Math.Max(inset.Bottom, inset.Right)),
        Math.Max(0, radius.BottomLeft - Math.Max(inset.Bottom, inset.Left)));

    public static PathGeometry Mask(double width, double height, CornerRadius corners)
    {
        var limit = Math.Min(width, height) / 2;
        double R(double value) => Math.Clamp(value, 0, limit);
        var tl = R(corners.TopLeft); var tr = R(corners.TopRight);
        var br = R(corners.BottomRight); var bl = R(corners.BottomLeft);
        var figure = new PathFigure { StartPoint = new(tl, 0), IsClosed = true, IsFilled = true };
        void Line(double x, double y) => figure.Segments.Add(new LineSegment { Point = new(x, y) });
        void Arc(double x, double y, double radius)
        {
            if (radius == 0) { Line(x, y); return; }
            figure.Segments.Add(new ArcSegment { Point = new(x, y), Size = new(radius, radius), SweepDirection = SweepDirection.Clockwise });
        }
        Line(width - tr, 0); Arc(width, tr, tr);
        Line(width, height - br); Arc(width - br, height, br);
        Line(bl, height); Arc(0, height - bl, bl);
        Line(0, tl); Arc(tl, 0, tl);
        var geometry = new PathGeometry { Transform = new ScaleTransform { ScaleX = 1 / width, ScaleY = 1 / height } };
        geometry.Figures.Add(figure);
        return geometry;
    }

    public static CanvasGeometry Surface(CanvasDevice device, float width, float height, CornerRadius corners)
    {
        var limit = Math.Min(width, height) / 2;
        float R(double value) => (float)Math.Clamp(value, 0, limit);
        var tl = R(corners.TopLeft); var tr = R(corners.TopRight);
        var br = R(corners.BottomRight); var bl = R(corners.BottomLeft);
        if (tl == tr && tl == br && tl == bl)
            return CanvasGeometry.CreateRoundedRectangle(device, 0, 0, width, height, tl, tl);
        var outline = CanvasGeometry.CreateRectangle(device, 0, 0, width, height);
        void Round(float x, float y, float centerX, float centerY, float radius)
        {
            if (radius <= 0) return;
            using var square = CanvasGeometry.CreateRectangle(device, x, y, radius, radius);
            using var circle = CanvasGeometry.CreateEllipse(device, centerX, centerY, radius, radius);
            using var excess = square.CombineWith(circle, Matrix3x2.Identity, CanvasGeometryCombine.Exclude);
            var rounded = outline.CombineWith(excess, Matrix3x2.Identity, CanvasGeometryCombine.Exclude);
            outline.Dispose(); outline = rounded;
        }
        Round(0, 0, tl, tl, tl);
        Round(width - tr, 0, width - tr, tr, tr);
        Round(width - br, height - br, width - br, height - br, br);
        Round(0, height - bl, bl, height - bl, bl);
        return outline;
    }
}
