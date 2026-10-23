using System.Diagnostics;
using System.Numerics;
using System.Runtime.CompilerServices;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Input;
using Windows.System;

namespace RtxForge.Windows.GameMode;

static partial class GmMotion
{
    static readonly ConditionalWeakTable<FrameworkElement, Contact> contacts = new();
    static readonly global::Windows.UI.ViewManagement.UISettings system = new();
    public static Func<bool>? ReducedMotion;
    public static bool Enabled => system.AnimationsEnabled && ReducedMotion?.Invoke() != true;
    public static Action ObservePreferences(FrameworkElement root)
    {
        void Changed(global::Windows.UI.ViewManagement.UISettings sender, global::Windows.UI.ViewManagement.UISettingsAnimationsEnabledChangedEventArgs args) =>
            root.DispatcherQueue.TryEnqueue(() => RefreshPreferences(root));
        system.AnimationsEnabledChanged += Changed;
        return () => system.AnimationsEnabledChanged -= Changed;
    }
    static void RefreshPreferences(DependencyObject root)
    {
        if (root is FrameworkElement element)
        {
            if (contacts.TryGetValue(element, out var contact)) contact.Refresh();
            if (!Enabled && scenes.TryGetValue(element, out var stop)) stop();
        }
        for (var i = 0; i < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(root); i++)
            RefreshPreferences(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(root, i));
    }
    internal static double Now => (double)Stopwatch.GetTimestamp() / Stopwatch.Frequency;
    public static void Attach(Button button) => contacts.GetValue(button, b => new Contact((Button)b));
    public static void Card(Button button, double unit) { Attach(button); contacts.GetValue(button, b => new Contact((Button)b)).Profile(GmMotionTokens.CardScale, (float)(GmMotionTokens.CardLift * unit), GmMotionTokens.CardCompression); }
    public static void Flat(UIElement element)
    {
        if (element is Button button) { Attach(button); contacts.GetValue(button, b => new Contact((Button)b)).Profile(0, 0, 0); }
    }
    internal static bool Initialized(FrameworkElement element) => contacts.TryGetValue(element, out var state) && state.Initialized;
    public static void Acknowledge(FrameworkElement element) { if (contacts.TryGetValue(element, out var state)) state.Acknowledge(); }

    // Followers escape clipped panels but consume the same compositor pose as their owner.
    // Layout supplies the resting origin. No per-frame XAML layout or coordinate work is needed.
    public static void Follow(FrameworkElement owner, Visual follower, Vector3 offset, Vector3 pivot, bool layoutHost = false)
    {
        if (contacts.TryGetValue(owner, out var state)) state.Bind(follower, offset, pivot, layoutHost);
    }

    sealed class Contact
    {
        readonly Button button;
        readonly GmSpring focus = new(GmMotionTokens.Focus / 1000d, GmMotionTokens.FocusDamping);
        readonly GmSpring press = new(GmMotionTokens.Press / 1000d, GmMotionTokens.PressDamping);
        readonly ConditionalWeakTable<Visual, object> followers = new();
        Microsoft.UI.Dispatching.DispatcherQueueTimer? release;
        ExpressionAnimation? scaleExpression, travelExpression;
        CompositionPropertySet? pose;
        SpringScalarNaturalMotionAnimation? focusAnimation, pressAnimation;
        bool hovered;
        float enlargement, lift, compression = GmMotionTokens.ButtonCompression;
        public Contact(Button button)
        {
            this.button = button;
            button.Loaded += (_, _) => UpdateFocus(); button.Unloaded += (_, _) => Unload();
            button.SizeChanged += (_, _) => Center();
            button.GotFocus += (_, _) => UpdateFocus();
            button.LostFocus += (_, _) => { SetPress(false); UpdateFocus(); };
            button.PointerEntered += (_, _) => { hovered = true; UpdateFocus(); };
            button.PointerExited += (_, _) => { hovered = false; SetPress(false); UpdateFocus(); };
            button.AddHandler(UIElement.PointerPressedEvent, new PointerEventHandler((_, _) => SetPress(true)), true);
            button.AddHandler(UIElement.PointerReleasedEvent, new PointerEventHandler((_, _) => SetPress(false)), true);
            button.AddHandler(UIElement.PointerCanceledEvent, new PointerEventHandler((_, _) => SetPress(false)), true);
            button.AddHandler(UIElement.PointerCaptureLostEvent, new PointerEventHandler((_, _) => SetPress(false)), true);
            button.AddHandler(UIElement.KeyDownEvent, new KeyEventHandler((_, e) => { if (e.Key is VirtualKey.Enter or VirtualKey.Space) SetPress(true); }), true);
            button.AddHandler(UIElement.KeyUpEvent, new KeyEventHandler((_, e) => { if (e.Key is VirtualKey.Enter or VirtualKey.Space) SetPress(false); }), true);
            button.Click += (_, _) => Acknowledge();
            button.IsEnabledChanged += (_, _) => { if (!button.IsEnabled) SetPress(false); UpdateFocus(); };
            if (button.IsLoaded) UpdateFocus();
        }
        public void Profile(float scale, float y, float down)
        {
            enlargement = scale; lift = y; compression = down;
            if (pose is not null) Parameters();
        }
        public bool Initialized => pose is not null;
        void Parameters() { pose!.InsertScalar("Growth", enlargement); pose.InsertScalar("Lift", lift); pose.InsertScalar("Compression", compression); }
        void Load()
        {
            try { LoadCore(); }
            catch (Exception error) when (error is System.Runtime.InteropServices.COMException or UnauthorizedAccessException)
            {
                // Optional visual feedback must never bring down the utility.
                Debug.WriteLine("Contact animation unavailable: " + error);
                Unload();
            }
        }
        void LoadCore()
        {
            if (pose is not null) return;
            // Use the supported UIElement path. A hand-out Visual cannot coexist with
            // XAML transform/transition properties, even after they are assigned null.
            var compositor = Microsoft.UI.Xaml.Media.CompositionTarget.GetCompositorForCurrentThread();
            pose = compositor.CreatePropertySet();
            pose.InsertScalar("Focus", 0); pose.InsertScalar("Press", 0); Parameters();
            focusAnimation = compositor.CreateSpringScalarAnimation();
            focusAnimation.Period = TimeSpan.FromMilliseconds(GmMotionTokens.Focus); focusAnimation.DampingRatio = GmMotionTokens.FocusDamping;
            pressAnimation = compositor.CreateSpringScalarAnimation();
            pressAnimation.Period = TimeSpan.FromMilliseconds(GmMotionTokens.Press); pressAnimation.DampingRatio = GmMotionTokens.PressDamping;
            scaleExpression = compositor.CreateExpressionAnimation("Vector3(1 + pose.Focus * pose.Growth - pose.Press * pose.Compression, 1 + pose.Focus * pose.Growth - pose.Press * pose.Compression, 1)");
            scaleExpression.Target = "Scale"; scaleExpression.SetReferenceParameter("pose", pose);
            travelExpression = compositor.CreateExpressionAnimation("Vector3(0, pose.Focus * pose.Lift, 0)");
            travelExpression.Target = "Translation"; travelExpression.SetReferenceParameter("pose", pose);
            Center(); button.StartAnimation(scaleExpression); button.StartAnimation(travelExpression); UpdateFocus();
        }
        void Center() => button.CenterPoint = new((float)button.ActualWidth / 2, (float)button.ActualHeight / 2, 0);
        public void Bind(Visual follower, Vector3 offset, Vector3 pivot, bool layoutHost)
        {
            if (pose is null) return;
            follower.CenterPoint = pivot;
            follower.Properties.InsertVector3("MotionOrigin", offset);
            if (followers.TryGetValue(follower, out _)) return;
            followers.Add(follower, new object());
            using var scale = follower.Compositor.CreateExpressionAnimation("Vector3(1 + pose.Focus * pose.Growth - pose.Press * pose.Compression, 1 + pose.Focus * pose.Growth - pose.Press * pose.Compression, 1)");
            scale.SetReferenceParameter("pose", pose); follower.StartAnimation("Scale", scale);
            using var travel = follower.Compositor.CreateExpressionAnimation(layoutHost
                ? "Vector3(0, pose.Focus * pose.Lift, 0)"
                : "origin.MotionOrigin + Vector3(0, pose.Focus * pose.Lift, 0)");
            travel.SetReferenceParameter("pose", pose); travel.SetReferenceParameter("origin", follower.Properties);
            // Translation is an enabled visual property, independent of the XAML layout offset.
            follower.StartAnimation("Offset", travel);
        }
        void UpdateFocus()
        {
            var on = button.IsEnabled && (hovered || button.FocusState is FocusState.Keyboard or FocusState.Programmatic);
            if (on && pose is null && button.IsLoaded) Load();
            Set("Focus", focus, focusAnimation, on ? 1 : 0);
        }
        public void Refresh() { SetPress(false); UpdateFocus(); }
        void SetPress(bool down) { if (down && pose is null && button.IsLoaded) Load(); release?.Stop(); Set("Press", press, pressAnimation, down && button.IsEnabled ? 1 : 0); }
        void Set(string property, GmSpring spring, SpringScalarNaturalMotionAnimation? animation, float value)
        {
            if (pose is null || animation is null) return;
            var immediate = !Enabled;
            if (immediate) value = 0;
            if (spring.Target == value && !immediate) return;
            var sample = spring.Retarget(value, Now, immediate);
            if (immediate) { pose.StopAnimation(property); pose.InsertScalar(property, value); return; }
            animation.InitialValue = (float)sample.Value; animation.InitialVelocity = (float)sample.Velocity; animation.FinalValue = value;
            pose.StartAnimation(property, animation);
        }
        public void Acknowledge()
        {
            SetPress(true); release ??= button.DispatcherQueue.CreateTimer();
            release.Interval = TimeSpan.FromMilliseconds(GmMotionTokens.Press * .65); release.IsRepeating = false;
            release.Tick -= Released; release.Tick += Released; release.Start();
        }
        void Released(Microsoft.UI.Dispatching.DispatcherQueueTimer timer, object args) => SetPress(false);
        void Unload()
        {
            release?.Stop(); hovered = false;
            if (scaleExpression is not null) { button.StopAnimation(scaleExpression); scaleExpression.Dispose(); scaleExpression = null; }
            if (travelExpression is not null) { button.StopAnimation(travelExpression); travelExpression.Dispose(); travelExpression = null; }
            button.Scale = Vector3.One; button.Translation = Vector3.Zero;
            focus.Retarget(0, Now, true); press.Retarget(0, Now, true);
            pose?.Dispose(); pose = null; focusAnimation?.Dispose(); pressAnimation?.Dispose();
        }
    }
}
