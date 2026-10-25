using System.Numerics;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;

namespace RtxForge.Windows.GameMode;

/// <summary>Native selection fills with a moving glow that survives rebuilt page controls.</summary>
sealed class GmSelection
{
    readonly GmSpring x = new(GmMotionTokens.Focus / 1000d, GmMotionTokens.FocusDamping);
    readonly GmSpring width = new(GmMotionTokens.Focus / 1000d, GmMotionTokens.FocusDamping);
    bool placed;
    int revision;
    public double MeasuredHeight { get; private set; }

    public Grid Place(StackPanel line, Button selected, GmTheme theme, bool navigation = false)
    {
        var currentRevision = ++revision;
        MeasuredHeight = 0;
        var canvas = new Canvas { IsHitTestVisible = false };
        var buttons = line.Children.OfType<Button>().ToList();
        var group = new Grid(); group.Children.Add(canvas); group.Children.Add(line);
        // The fill belongs to the button for its entire lifetime. Animation
        // timing, unload/reload and compositor failure cannot strand dark ink.
        foreach (var button in buttons)
            button.Background = GmTheme.B(ReferenceEquals(button, selected)
                ? navigation ? theme.Active : theme.SegmentSelected
                : button.IsEnabled ? theme.Card : theme.Disabled);
        bool measured = false;
        double measuredHeight = 0;
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
            var now = GmMotion.Now;
            var immediate = !placed || !GmMotion.Enabled;
            var a = x.Retarget(left, now, immediate);
            var b = width.Retarget(targetWidth, now, immediate);
            pose.InsertScalar("Height", (float)selected.ActualHeight);
            measured = true; measuredHeight = selected.ActualHeight;
            MeasuredHeight = measuredHeight;
            Animate("X", a, left); Animate("Width", b, targetWidth); placed = true;
            void Animate(string key, (double Value, double Velocity) start, float target)
            {
                pose.StopAnimation(key); pose.InsertScalar(key, (float)start.Value);
                if (immediate) return;
                using var spring = pose.Compositor.CreateSpringScalarAnimation();
                spring.Period = TimeSpan.FromMilliseconds(GmMotionTokens.Focus);
                spring.DampingRatio = GmMotionTokens.FocusDamping;
                spring.InitialValue = (float)start.Value; spring.InitialVelocity = (float)start.Velocity; spring.FinalValue = target;
                pose.StartAnimation(key, spring);
            }
        }
        group.Loaded += (_, _) =>
        {
            var compositor = Microsoft.UI.Xaml.Media.CompositionTarget.GetCompositorForCurrentThread();
            pose = compositor.CreatePropertySet();
            pose.InsertScalar("X", (float)x.Sample(GmMotion.Now).Value);
            pose.InsertScalar("Width", (float)width.Sample(GmMotion.Now).Value); pose.InsertScalar("Height", 0);
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
        };
        selected.Loaded += (_, _) => Update();
        group.LayoutUpdated += (_, _) => { if (pose is not null && (!measured || measuredHeight != selected.ActualHeight || x.Target != selected.ActualOffset.X || width.Target != selected.ActualWidth)) Update(); };
        selected.SizeChanged += (_, _) => { if (!measured || measuredHeight != selected.ActualHeight || x.Target != selected.ActualOffset.X || width.Target != selected.ActualWidth) Update(); };
        group.Unloaded += (_, _) =>
        {
            GmMotion.Forget(group);
            ElementCompositionPreview.SetElementChildVisual(canvas, null);
            root?.Dispose(); root = null; glow?.Dispose(); shadow?.Dispose(); maskBrush?.Dispose(); surface?.Dispose(); mask?.Dispose();
            pose?.Dispose(); pose = null;
        };
        return group;
    }
}
