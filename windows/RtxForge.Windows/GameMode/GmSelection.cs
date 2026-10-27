using System.Numerics;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;

namespace RtxForge.Windows.GameMode;

/// <summary>Native selection fills with a stationary glow on the shared light layer.</summary>
sealed class GmSelection
{
    int revision;
    public double MeasuredHeight { get; private set; }

    public Grid Place(StackPanel line, Button selected, GmTheme theme, bool navigation = false, int glowDelay = 0)
    {
        var currentRevision = ++revision;
        MeasuredHeight = 0;
        Canvas? canvas = null;
        ArtworkLightLayer? layer = null;
        var buttons = line.Children.OfType<Button>().ToList();
        var group = new Grid(); group.Children.Add(line);
        // The fill belongs to the button for its entire lifetime. Animation
        // timing, unload/reload and compositor failure cannot strand dark ink.
        foreach (var button in buttons)
            button.Background = GmTheme.B(ReferenceEquals(button, selected)
                ? navigation ? theme.Active : theme.SegmentSelected
                : button.IsEnabled ? theme.Card : theme.Disabled);
        bool measured = false;
        double measuredHeight = 0;
        double measuredLeft = -1, measuredWidth = -1;
        CompositionPropertySet? pose = null;
        ShapeVisual? mask = null;
        ContainerVisual? root = null;
        SpriteVisual? glow = null;
        CompositionVisualSurface? surface = null;
        CompositionSurfaceBrush? maskBrush = null;
        DropShadow? shadow = null;
        void Update()
        {
            if (currentRevision != revision || selected.ActualHeight <= 0 || selected.ActualWidth <= 0 || pose is null) return;
            var left = selected.ActualOffset.X;
            var targetWidth = (float)selected.ActualWidth;
            measuredLeft = left; measuredWidth = targetWidth;
            pose.InsertScalar("X", (float)left); pose.InsertScalar("Width", targetWidth);
            pose.InsertScalar("Height", (float)selected.ActualHeight);
            measured = true; measuredHeight = selected.ActualHeight;
            MeasuredHeight = measuredHeight;
        }
        group.Loaded += (_, _) =>
        {
            layer = GmGlow.Destination(selected);
            canvas = layer?.AddControl(line, behind: true) ?? new Canvas { IsHitTestVisible = false };
            if (layer is null) group.Children.Insert(0, canvas);
            var compositor = Microsoft.UI.Xaml.Media.CompositionTarget.GetCompositorForCurrentThread();
            pose = compositor.CreatePropertySet();
            pose.InsertScalar("X", 0); pose.InsertScalar("Width", 0); pose.InsertScalar("Height", 0);
            var geometry = compositor.CreateRoundedRectangleGeometry();
            ExpressionAnimation Expression(string text)
            {
                var expression = compositor.CreateExpressionAnimation(text); expression.SetReferenceParameter("pose", pose); return expression;
            }
            using (var expression = Expression("Vector2(pose.Width, pose.Height)"))
                geometry.StartAnimation("Size", expression);
            using (var expression = Expression("Vector2(pose.Height / 2, pose.Height / 2)")) geometry.StartAnimation("CornerRadius", expression);
            // Capture only the capsule's alpha once; fixed blur follows the same native pose.
            mask = compositor.CreateShapeVisual();
            var maskShape = compositor.CreateSpriteShape(geometry); maskShape.FillBrush = compositor.CreateColorBrush(Microsoft.UI.Colors.White);
            mask.Shapes.Add(maskShape);
            surface = compositor.CreateVisualSurface(); surface.SourceVisual = mask;
            using (var expression = Expression("Vector2(pose.Width, pose.Height)"))
            { mask.StartAnimation("Size", expression); surface.StartAnimation("SourceSize", expression); }
            maskBrush = compositor.CreateSurfaceBrush(surface); maskBrush.Stretch = CompositionStretch.Fill;
            shadow = compositor.CreateDropShadow(); shadow.Mask = maskBrush;
            shadow.Color = navigation ? theme.Active : theme.SegmentSelected; shadow.BlurRadius = (float)theme.Px(20); shadow.Opacity = .62f;
            glow = compositor.CreateSpriteVisual(); glow.Shadow = shadow;
            using (var expression = Expression("Vector3(pose.X, 0, 0)")) glow.StartAnimation("Offset", expression);
            using (var expression = Expression("Vector2(pose.Width, pose.Height)")) glow.StartAnimation("Size", expression);
            root = compositor.CreateContainerVisual(); root.Children.InsertAtBottom(glow);
            ElementCompositionPreview.SetElementChildVisual(canvas, root);
            GmMotion.PreferenceChanged(group, Update);
            Update();
            GmMotion.GlowArrival(canvas, glowDelay);
        };
        selected.Loaded += (_, _) => Update();
        group.LayoutUpdated += (_, _) => { if (pose is not null && (!measured || measuredHeight != selected.ActualHeight || measuredLeft != selected.ActualOffset.X || measuredWidth != selected.ActualWidth)) Update(); };
        selected.SizeChanged += (_, _) => { if (!measured || measuredHeight != selected.ActualHeight || measuredLeft != selected.ActualOffset.X || measuredWidth != selected.ActualWidth) Update(); };
        group.Unloaded += (_, _) =>
        {
            GmMotion.Forget(group);
            if (canvas is not null) ElementCompositionPreview.SetElementChildVisual(canvas, null);
            layer?.RemoveControl(line);
            root?.Dispose(); root = null; glow?.Dispose(); shadow?.Dispose(); maskBrush?.Dispose(); surface?.Dispose(); mask?.Dispose();
            pose?.Dispose(); pose = null;
        };
        return group;
    }
}
