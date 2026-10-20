using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using System.Numerics;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Composition.SystemBackdrops;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Hosting;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using RtxForge.Windows.Controls;
using Windows.Graphics;
using WinRT;

namespace RtxForge.Windows.Views;

public sealed partial class CompanionWindow : Window
{
    readonly EngineForgeService service;
    readonly Func<string?> shortcutProblem;
    readonly Action preferencesChanged;
    readonly OverlayWindowHost nativeWindow;
    bool settingsShown;
    bool globalShown;
    bool opening;
    bool Classic => service.Settings.OverlayControls == "classic";
    IReadOnlyList<Game> games = [];
    DateTime targetsUpdated;
    DesktopAcrylicController? acrylic;
    MicaController? mica;
    string? pipelinesRendered;
    int visibilityRevision;
    bool windowVisible;
    RectInt32 openingArea;
    nint invokingWindow;
    uint invokingProcess;
    long anchorUntil;
    readonly DispatcherQueueTimer pollTimer, editTimer;
    Game? game;
    JsonObject? status;
    int pid, multiplier = -1, style, generation;
    bool syncing = true, dirty, requesting, polling, disposed, dragging;
    public bool IsShown { get; private set; }

    public CompanionWindow(EngineForgeService engine, Func<string?> getShortcutProblem, Action reloadPreferences)
    {
        service = engine; shortcutProblem = getShortcutProblem; preferencesChanged = reloadPreferences;
        InitializeComponent();
        ApplyMaterial(engine.Settings.OverlayMaterial);
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(DragBar);
        AppWindow.IsShownInSwitchers = false;
        if (AppWindow.Presenter is OverlappedPresenter presenter)
        {
            presenter.IsAlwaysOnTop = true;
            presenter.IsMaximizable = presenter.IsMinimizable = presenter.IsResizable = false;
            presenter.SetBorderAndTitleBar(true, false);
        }
        var handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        nativeWindow = new OverlayWindowHost(handle);
        AppWindow.Changed += (_, e) =>
        {
            // Some desktop arrangers center newly shown windows asynchronously.
            // Settle only during opening; no polling or restriction on later dragging.
            if (!disposed && IsShown && e.DidPositionChange && Environment.TickCount64 < anchorUntil)
                PositionAtLeft(openingArea);
        };
        var rounded = 2;
        DwmSetWindowAttribute(handle, 33, ref rounded, sizeof(int));
        var noBorder = unchecked((int)0xFFFFFFFE);
        DwmSetWindowAttribute(handle, 34, ref noBorder, sizeof(int));
        Root.KeyDown += (_, e) =>
        {
            if (e.Key == global::Windows.System.VirtualKey.Escape)
            { e.Handled = true; if (settingsShown && service.Settings.OverlayRenderer != "optiscaler") ShowSettings(false); else HidePanel(); }
        };
        AppWindow.Closing += (_, e) => { if (!disposed) { e.Cancel = true; HidePanel(); } };
        pollTimer = DispatcherQueue.CreateTimer();
        pollTimer.Interval = TimeSpan.FromSeconds(1);
        pollTimer.Tick += async (_, _) => await RefreshAsync();
        editTimer = DispatcherQueue.CreateTimer();
        editTimer.IsRepeating = false;
        editTimer.Interval = TimeSpan.FromMilliseconds(350);
        editTimer.Tick += async (_, _) => await ApplyEditsAsync();
        foreach (var slider in new[] { Strength, Structure, Tone, Skin, Detail, Colour, WorkScale, Sharpness, MotionSharpness })
        {
            slider.AddHandler(UIElement.PointerPressedEvent, new PointerEventHandler((_, _) => dragging = true), true);
            slider.AddHandler(UIElement.PointerReleasedEvent, new PointerEventHandler((_, _) => { dragging = false; QueueApply(); }), true);
            slider.AddHandler(UIElement.PointerCanceledEvent, new PointerEventHandler((_, _) => { dragging = false; QueueApply(); }), true);
            slider.AddHandler(UIElement.PointerCaptureLostEvent, new PointerEventHandler((_, _) => { dragging = false; QueueApply(); }), true);
        }
        syncing = false;
        ApplyPreferences();
        RenderPipelines();
        SetAvailability();
    }

    public async void Present(bool settingsOnly = false)
    {
        if (opening || disposed) return;
        // Keep the invoking display/game even if the asynchronous ownership
        // lookup completes after foreground focus has moved elsewhere.
        var foregroundWindow = GetForegroundWindow();
        var foreground = MainWindow.ForegroundProcessId();
        if (foregroundWindow != 0 && foreground != (uint)Environment.ProcessId)
        { invokingWindow = foregroundWindow; invokingProcess = foreground; }
        var windowId = foregroundWindow == 0 ? AppWindow.Id : Microsoft.UI.Win32Interop.GetWindowIdFromWindow(foregroundWindow);
        var area = DisplayArea.GetFromWindowId(windowId, DisplayAreaFallback.Primary).OuterBounds;
        opening = true;
        try
        {
            if (!settingsOnly)
            {
                // A global hotkey must never summon game controls over the
                // desktop, or guess the only running game in the background.
                if (service.Settings.OverlayRenderer == "game") return;
                var targets = await service.CompanionTargetsAsync();
                var active = await service.ActiveCompanionAsync(targets, foreground, 0);
                if (disposed || foreground == 0 || Int(active, "pid") != foreground || active["row"] is not JsonObject
                    || GetForegroundWindow() != foregroundWindow) return;
                games = targets; targetsUpdated = DateTime.UtcNow;
            }
            if (disposed) return;
            PresentCore(area, foreground);
            if (game is not null) _ = ApplyGameAccentAsync(game, generation);
        }
        catch (Exception error) { if (!disposed && settingsOnly) { Feedback.Text = error.Message; PresentCore(area, foreground); } }
        finally { opening = false; }
    }
    void PositionAtLeft(RectInt32 area)
    {
        // Our per-monitor-aware HWND supplies the display's scale even when
        // the game itself is DPI-unaware. Moving first updates it on display changes.
        var scale = Math.Max(96u, GetDpiForWindow(WinRT.Interop.WindowNative.GetWindowHandle(this))) / 96.0;
        var edge = (int)Math.Round(24 * scale);
        var width = Math.Min((int)Math.Round(420 * scale), area.Width - 2 * edge);
        var bounds = new RectInt32(area.X + edge, area.Y + edge, width, area.Height - 2 * edge);
        if (AppWindow.Position.X != bounds.X || AppWindow.Position.Y != bounds.Y
            || AppWindow.Size.Width != bounds.Width || AppWindow.Size.Height != bounds.Height)
            AppWindow.MoveAndResize(bounds);
    }
    void PresentCore(RectInt32 area, uint foreground)
    {
        openingArea = area;
        anchorUntil = Environment.TickCount64 + 500;
        // Re-anchor on every open, including an already visible Global/settings
        // panel. Repeat after showing so first-show placement and monitor DPI
        // changes cannot leave it centered or at a previous dragged position.
        PositionAtLeft(area);
        nativeWindow.SetKeyboardInteraction(settingsShown || globalShown);
        nativeWindow.SetFullscreen(OverlayWindowHost.CoversDisplay(invokingWindow, area.X, area.Y, area.Width, area.Height));
        ShortcutHint.Text = shortcutProblem() ?? (service.Settings.PanelHotkey == "Disabled"
            ? "Close to return to your game" : $"{service.Settings.PanelHotkey} · show or hide");
        IsShown = true;
        if (service.Settings.OverlayRenderer == "optiscaler" && !globalShown) ShowSettings(true);
        AnimateVisibility(true);
        // Keep the game in the foreground. Activating this separate window
        // tells the shell the user left fullscreen and can raise the taskbar.
        // Mouse interaction can still focus controls when the user chooses it.
        AppWindow.Show(activateWindow: false);
        PositionAtLeft(area);
        if (!string.IsNullOrEmpty(nativeWindow.ShellError)) Feedback.Text = "Windows overlay integration: " + nativeWindow.ShellError;
        if (!settingsShown && !globalShown) { pollTimer.Start(); _ = RefreshAsync(foreground); }
    }

    public void HidePanel()
    {
        anchorUntil = 0; editTimer.Stop(); pollTimer.Stop(); dirty = dragging = false; IsShown = false;
        RestoreCallerFocus();
        nativeWindow.SetFullscreen(false);
        AnimateVisibility(false);
    }
    void RestoreCallerFocus()
    {
        // Only return focus after interaction with our own panel. An Alt-Tab
        // to another app must never be undone by a late hide or animation.
        GetWindowThreadProcessId(GetForegroundWindow(), out var foreground);
        if (foreground == (uint)Environment.ProcessId && IsWindow(invokingWindow) && !IsIconic(invokingWindow))
        {
            GetWindowThreadProcessId(invokingWindow, out var owner);
            if (owner == invokingProcess) SetForegroundWindow(invokingWindow);
        }
    }

    void AnimateVisibility(bool show)
    {
        var ticket = ++visibilityRevision;
        var visual = ElementCompositionPreview.GetElementVisual(Surface);
        var compositor = visual.Compositor;
        if (!new global::Windows.UI.ViewManagement.UISettings().AnimationsEnabled)
        {
            visual.StopAnimation("Opacity"); visual.StopAnimation("Scale");
            visual.Opacity = 1; visual.Scale = Vector3.One;
            if (!show) AppWindow.Hide(); windowVisible = show; return;
        }
        if (show && !windowVisible)
        { visual.Opacity = 0; visual.Scale = new Vector3(.97f, .97f, 1); }
        visual.CenterPoint = new Vector3(0, (float)Surface.ActualHeight / 2, 0);
        windowVisible = true;
        var easing = compositor.CreateCubicBezierEasingFunction(new Vector2(.16f, 1), new Vector2(.3f, 1));
        var duration = TimeSpan.FromMilliseconds(show ? 160 : 110);
        var fade = compositor.CreateScalarKeyFrameAnimation();
        fade.Duration = duration; fade.InsertExpressionKeyFrame(0, "this.StartingValue"); fade.InsertKeyFrame(1, show ? 1 : 0, easing);
        var scale = compositor.CreateVector3KeyFrameAnimation();
        scale.Duration = duration; scale.InsertExpressionKeyFrame(0, "this.StartingValue"); scale.InsertKeyFrame(1, show ? Vector3.One : new Vector3(.98f, .98f, 1), easing);
        var batch = compositor.CreateScopedBatch(Microsoft.UI.Composition.CompositionBatchTypes.Animation);
        visual.StartAnimation("Opacity", fade); visual.StartAnimation("Scale", scale);
        batch.Completed += (_, _) =>
        {
            batch.Dispose();
            if (disposed || ticket != visibilityRevision || show || IsShown) return;
            AppWindow.Hide(); windowVisible = false;
        };
        batch.End();
    }
    public void Shutdown() { disposed = true; editTimer.Stop(); pollTimer.Stop(); nativeWindow.Dispose(); acrylic?.Dispose(); mica?.Dispose(); Close(); }

    public void ApplyMaterial(string material)
    {
        acrylic?.Dispose(); mica?.Dispose(); acrylic = null; mica = null;
        var config = new SystemBackdropConfiguration { IsInputActive = true, Theme = SystemBackdropTheme.Dark };
        var target = this.As<Microsoft.UI.Composition.ICompositionSupportsSystemBackdrop>();
        if (material == "mica" && MicaController.IsSupported())
        {
            mica = new MicaController { Kind = MicaKind.BaseAlt };
            mica.SetSystemBackdropConfiguration(config); mica.AddSystemBackdropTarget(target);
        }
        else if (DesktopAcrylicController.IsSupported())
        {
            acrylic = new DesktopAcrylicController { TintColor = global::Windows.UI.Color.FromArgb(255, 12, 12, 12), TintOpacity = 0.45f, LuminosityOpacity = 0.65f };
            acrylic.SetSystemBackdropConfiguration(config); acrylic.AddSystemBackdropTarget(target);
        }
        else Root.Background = new SolidColorBrush(global::Windows.UI.Color.FromArgb(255, 24, 24, 24));
    }
    void OnHide(object sender, RoutedEventArgs e) => HidePanel();
    void OnSettings(object sender, RoutedEventArgs e) => ShowSettings(!settingsShown);
    void OnGlobal(object sender, RoutedEventArgs e)
    {
        globalShown = !globalShown; ShowSettings(false);
    }
    public void OpenSettings() { ShowSettings(true); Present(settingsOnly: true); }
    void ShowSettings(bool show)
    {
        if (!show && !globalShown && service.Settings.OverlayRenderer == "optiscaler") { HidePanel(); return; }
        settingsShown = show;
        nativeWindow.SetKeyboardInteraction(show || globalShown);
        if (IsShown && (show || globalShown))
        {
            nativeWindow.SetFullscreen(OverlayWindowHost.CoversDisplay(invokingWindow, openingArea.X, openingArea.Y, openingArea.Width, openingArea.Height));
            Activate(); // Explicit settings interaction, never the show/hide hotkey.
        }
        else if (IsShown) RestoreCallerFocus();
        GlobalButton.IsChecked = globalShown;
        ControlsScroll.Visibility = PresetFooter.Visibility = show || globalShown ? Visibility.Collapsed : Visibility.Visible;
        SettingsScroll.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
        GlobalScroll.Visibility = globalShown && !show ? Visibility.Visible : Visibility.Collapsed;
        PipelinePills.Visibility = globalShown ? Visibility.Collapsed : Visibility.Visible;
        if (show)
        {
            // Settings are independent of game rendering and suspend status polling.
            pollTimer.Stop(); editTimer.Stop(); dirty = dragging = false;
            SettingsHost.Children.Clear();
            SettingsHost.Children.Add(new OverlayPreferencesView(fresh =>
            { service.Settings.CopyOverlayFrom(fresh); preferencesChanged(); }, service));
            SettingsButton.Focus(FocusState.Programmatic);
        }
        else if (globalShown)
        {
            pollTimer.Stop(); editTimer.Stop(); dirty = dragging = false;
            GameName.Text = "All installed games"; ConnectionText.Text = "One-time changes · review before applying";
            ApplyAccent(ArtAccent.Palette(ArtAccent.NoArtwork));
            if (GlobalHost.Children.Count == 0) GlobalHost.Children.Add(new GlobalControlsView(service));
        }
        else if (IsShown) { pollTimer.Start(); _ = RefreshAsync(); if (game is not null) _ = ApplyGameAccentAsync(game, generation); }
    }
    public void ApplyPreferences()
    {
        ApplyMaterial(service.Settings.OverlayMaterial);
        var wasSyncing = syncing; syncing = true;
        StrengthLabel.Text = Classic ? "Intensity" : "Model strength";
        DetailLabel.Text = Classic ? "Detail strength" : "Detail";
        ColourLabel.Text = Classic ? "Colour strength" : "Colour";
        PreSr.Header = Classic ? "Run before the upscaler" : "Run before super resolution";
        ToolTipService.SetToolTip(PreSr, "Requests before-upscale placement. The live report below shows where NR actually ran; some routes use the finished image.");
        Reduced.Header = Classic ? "Reduced model before the upscaler" : "Use reduced model resolution";
        Cache.Header = Classic ? "Reuse the model’s edit between runs" : "Reuse NR between frames";
        Interval.Header = Classic ? "Max frames between runs" : "Run NR every N frames";
        AutoMask.Header = Classic ? "Auto skin mask" : "Automatic skin mask";
        MfgHeading.Text = Classic ? "Override DLSSG Ratio" : "Frame generation";
        var automatic = MultiplierChoices.Children.OfType<ToggleButton>().First();
        automatic.Content = Classic ? "Default" : "Auto";
        if (NrPreset.Items.Count > 0 && !Equals(NrPreset.Items[0], Classic ? "Default" : "Automatic"))
            NrPreset.Items[0] = Classic ? "Default" : "Automatic";
        SharpFilter.Header = Classic ? "Method" : "Filter";
        SharpFilter.Items[1] = Classic ? "Depth Aware (RCAS)" : "Depth aware";
        SharpFilter.Items[2] = Classic ? "Depth Aware (DAS)" : "Local contrast depth aware";
        // Layout preferences never quantize a game's current values.
        foreach (var slider in new[] { Strength, Structure, Tone, Skin, Detail, Colour })
            slider.StepFrequency = .01;
        // Model resolution is a percentage in OptiScaler itself.
        WorkScale.StepFrequency = .01;
        syncing = wasSyncing; UpdateLabels();
        ShortcutHint.Text = shortcutProblem() ?? (service.Settings.PanelHotkey == "Disabled"
            ? "Esc to return to your game" : $"{service.Settings.PanelHotkey} · show or hide");
    }
    static int Int(JsonObject? data, string key, int fallback = 0) => data?[key]?.GetValue<int>() ?? fallback;
    static bool Flag(JsonObject? data, string key) => data?[key]?.GetValue<bool>() == true;
    static string Text(JsonObject? data, string key) => data?[key]?.GetValue<string>() ?? "";
    static double Number(JsonObject? data, string key, double fallback = 1) => data?[key]?.GetValue<double>() ?? fallback;

    async Task RefreshAsync(uint? observedForeground = null)
    {
        if (requesting || polling || disposed || !IsShown || settingsShown || globalShown) return;
        polling = true;
        try
        {
            if (DateTime.UtcNow - targetsUpdated > TimeSpan.FromSeconds(5))
            { games = await service.CompanionTargetsAsync(); targetsUpdated = DateTime.UtcNow; }
            var foreground = observedForeground ?? MainWindow.ForegroundProcessId();
            var retained = foreground == (uint)Environment.ProcessId ? pid : 0;
            var active = await service.ActiveCompanionAsync(games, foreground, retained);
            if (disposed || requesting || !IsShown || settingsShown || globalShown) return;
            var location = (active["row"] as JsonObject)?["game"]?.GetValue<string>();
            var next = games.FirstOrDefault(g => string.Equals(g.Id, location, StringComparison.OrdinalIgnoreCase));
            var nextPid = Int(active, "pid");
            if (game?.Id != next?.Id || pid != nextPid)
            {
                generation++; editTimer.Stop(); dirty = dragging = false;
                game = next; pid = nextPid; Feedback.Text = "";
                if (next is not null) _ = ApplyGameAccentAsync(next, generation);
                else ApplyAccent(ArtAccent.Palette(ArtAccent.NoArtwork));
            }
            var ticket = generation;
            var result = game is null ? active : await service.CompanionAsync("status", game);
            if (ticket != generation || disposed || requesting || !IsShown || settingsShown || globalShown) return;
            status = result;
            pollTimer.Interval = TimeSpan.FromSeconds(game is null ? 3 : 1);
            GameName.Text = game?.Name ?? "Ready when you are";
            ConnectionText.Text = game is null ? Text(result, "detail")
                : Text(result, "state") == "running" ? "Connected · changes apply live" : Text(result, "detail");
            if (!dirty && game is not null && Flag(result, "can_edit") && result["values"] is JsonObject values) LoadValues(values);
            RenderStatus();
        }
        catch (Exception error)
        {
            status = null;
            ConnectionText.Text = "Connection unavailable";
            Feedback.Text = error.Message;
        }
        finally { polling = false; SetAvailability(); }
    }

    async Task ApplyGameAccentAsync(Game target, int ticket)
    {
        var palette = await OverlayAccent.ForGameAsync(target);
        if (!disposed && !globalShown && ticket == generation && game?.Id == target.Id) ApplyAccent(palette);
    }
    void ApplyAccent(AccentPalette palette)
    {
        void Paint(string key, global::Windows.UI.Color colour)
        {
            if (Root.Resources.TryGetValue(key, out var resource) && resource is SolidColorBrush brush) brush.Color = colour;
            else Root.Resources[key] = new SolidColorBrush(colour);
        }
        var dark = global::Windows.UI.Color.FromArgb(255, 40, 40, 40);
        var white = global::Windows.UI.Color.FromArgb(255, 238, 238, 238);
        var selected = ArtAccent.Mix(palette.Color, dark, .28);
        var selectedHover = ArtAccent.Mix(palette.Color, dark, .38);
        var selectedPressed = ArtAccent.Mix(palette.Color, dark, .20);
        var selectedText = ArtAccent.Mix(palette.Color, white, .16);
        var control = ArtAccent.Mix(palette.Color, white, .55);
        var controlHover = ArtAccent.Mix(palette.Color, white, .40);
        var save = ArtAccent.Mix(palette.Color, dark, .55);
        var saveHover = ArtAccent.Mix(palette.Color, dark, .65);
        var savePressed = ArtAccent.Mix(palette.Color, dark, .45);
        var saveText = ArtAccent.Readable(white, save);
        // Game identity is the strongest color; chrome, headings and icons stay
        // neutral. State fills use quieter shades of the same artwork accent.
        Paint("OverlayGameTitleBrush", palette.HeroAccent);
        foreach (var key in new[] { "AccentFillColorDefaultBrush", "AccentFillColorSecondaryBrush", "ToggleButtonBackgroundChecked" }) Paint(key, selected);
        Paint("ToggleButtonBackgroundCheckedPointerOver", selectedHover);
        Paint("ToggleButtonBackgroundCheckedPressed", selectedPressed);
        foreach (var key in new[] { "SliderTrackValueFill", "SliderThumbBackground", "ToggleSwitchFillOn" }) Paint(key, control);
        foreach (var key in new[] { "SliderTrackValueFillPointerOver", "SliderThumbBackgroundPointerOver", "ToggleSwitchFillOnPointerOver" }) Paint(key, controlHover);
        foreach (var key in new[] { "SliderTrackValueFillPressed", "SliderThumbBackgroundPressed", "ToggleSwitchFillOnPressed" }) Paint(key, control);
        Paint("TextOnAccentFillColorPrimaryBrush", ArtAccent.Readable(selectedText, selected));
        Paint("ToggleButtonForegroundChecked", ArtAccent.Readable(selectedText, selected));
        Paint("ToggleButtonForegroundCheckedPointerOver", ArtAccent.Readable(selectedText, selectedHover));
        Paint("ToggleButtonForegroundCheckedPressed", ArtAccent.Readable(selectedText, selectedPressed));
        Paint("ToggleSwitchKnobFillOn", ArtAccent.Readable(dark, control));
        Paint("ComboBoxDropDownGlyphForeground", global::Windows.UI.Color.FromArgb(255, 196, 196, 196));
        SavePreset.Background = palette.Brush(save); SavePreset.Foreground = palette.Brush(saveText);
        ((SolidColorBrush)SavePreset.Resources["ButtonBackgroundPointerOver"]).Color = saveHover;
        ((SolidColorBrush)SavePreset.Resources["ButtonBackgroundPressed"]).Color = savePressed;
        ((SolidColorBrush)SavePreset.Resources["ButtonForegroundPointerOver"]).Color = ArtAccent.Readable(white, saveHover);
        ((SolidColorBrush)SavePreset.Resources["ButtonForegroundPressed"]).Color = ArtAccent.Readable(white, savePressed);
    }

    void RenderStatus()
    {
        RenderPipelines();
        var running = Text(status, "state") == "running";
        MfgActual.Text = !running ? "Output appears when your game connects."
            : !Flag(status, "can_mfg") ? "This package controls FG in the game."
            : !Flag(status, "native_fresh") ? "Requested above · waiting for a fresh output report."
            : Int(status, "native_status") != 0 ? "The game reports a frame generation issue."
            : Int(status, "native_mode", -1) == 0 ? "Frame generation is off in the game."
            : Int(status, "native_presented") > 1 ? $"{Int(status, "native_presented")} frames presented · confirmed by game"
            : "Enabled · waiting for generated output.";
        NrActual.Text = !running ? "Waiting for the game" : Flag(status, "nr_running") ? "NR active" : "NR is not evaluating";
        if (running && status?["rendered_fps"] is JsonNode fps)
            NrActual.Text += $" · {fps.GetValue<double>():0.#} rendered FPS";
        TelemetryText.Text = running && status?["nr_ms"] is JsonNode timing
            ? $"NR GPU time · {timing.GetValue<double>():0.00} ms" : "NR GPU timing is unavailable.";
        if (running)
        {
            TelemetryText.Text += "\n" + Text(status, "nr_placement_label");
            if (Flag(status, "nr_placement_verified"))
            {
                var requested = Flag(status, "nr_requested_before") ? "before" : "after";
                TelemetryText.Text += $" · requested {requested}";
                var width = Int(status, "nr_model_width"); var height = Int(status, "nr_model_height");
                if (width > 0 && height > 0 && Int(status, "nr_placement") is 2 or 3)
                    TelemetryText.Text += $"\nModel · {width} × {height}";
            }
            if (status?["values"] is JsonObject liveValues && Int(liveValues, "reduced") == 1 && Int(liveValues, "pre_sr") == 1)
                TelemetryText.Text += "\nReduced pre-SR · " + (!Flag(status, "nr_placement_verified") ? "unverified"
                    : Flag(status, "nr_reduced") ? "active" : "not active on this route");
            if (Text(status, "nr_placement_detail") is { Length: > 0 } placementDetail)
                TelemetryText.Text += "\n" + placementDetail;
        }
        if (Flag(status, "saved") && !Flag(status, "preset_compatible"))
            Feedback.Text = "The package changed. Save this preset again to use it with the new package.";
        else if (Text(status, "preset_error") is { Length: > 0 } error) Feedback.Text = "Preset could not apply: " + error;
    }

    void RenderPipelines()
    {
        var identity = status?["pipelines"]?.ToJsonString() ?? "idle";
        if (identity == pipelinesRendered) return;
        pipelinesRendered = identity;
        PipelinePills.Children.Clear();
        PipelinePills.Children.Add(new TextBlock { Text = "DLSS files", FontSize = 11, Foreground = new SolidColorBrush(global::Windows.UI.Color.FromArgb(190, 255, 255, 255)), VerticalAlignment = VerticalAlignment.Center });
        foreach (var label in new[] { "SR", "RR", "NR", "FG" })
        {
            var found = status?["pipelines"]?[label];
            var state = found?["state"]?.ToString();
            var colour = state switch
            {
                "managed" => global::Windows.UI.Color.FromArgb(255, 151, 215, 105),
                "other" => global::Windows.UI.Color.FromArgb(255, 244, 198, 98),
                "changed" => global::Windows.UI.Color.FromArgb(255, 255, 135, 142),
                _ => global::Windows.UI.Color.FromArgb(255, 170, 170, 170),
            };
            var brush = new SolidColorBrush(colour);
            var content = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 5 };
            content.Children.Add(new Microsoft.UI.Xaml.Shapes.Ellipse { Width = 5, Height = 5, Fill = brush, VerticalAlignment = VerticalAlignment.Center });
            content.Children.Add(new TextBlock { Text = label, FontSize = 11, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, Foreground = brush });
            var pill = new Border { Child = content, Padding = new Thickness(8, 4, 8, 4), CornerRadius = new CornerRadius(12), Background = new SolidColorBrush(global::Windows.UI.Color.FromArgb(20, colour.R, colour.G, colour.B)) };
            var detail = found?["detail"]?.ToString() ?? "Waiting for a supported game. Installed DLL status appears when it connects.";
            ToolTipService.SetToolTip(pill, detail);
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(pill, label + ": " + detail);
            PipelinePills.Children.Add(pill);
        }
    }

    void LoadValues(JsonObject values)
    {
        syncing = true;
        Colour.Maximum = Int(status, "version") >= 5 ? 4 : 2;
        multiplier = Int(values, "multiplier", -1); style = Int(values, "style");
        NrEnabled.IsOn = Int(values, "enabled", 1) == 1;
        Strength.Value = Number(values, "intensity");
        Structure.Value = Number(values, "structure"); Tone.Value = Number(values, "tone");
        Skin.Value = Number(values, "skin", -1); Detail.Value = Number(values, "detail"); Colour.Value = Number(values, "colour");
        WorkScale.Value = Number(values, "work_scale");
        NrPreset.SelectedIndex = Int(values, "preset"); Passes.SelectedIndex = Int(values, "passes", 1) - 1;
        PreSr.IsOn = Int(values, "pre_sr", 1) == 1; Cache.IsOn = Int(values, "cache") == 1;
        Reduced.IsOn = Int(values, "reduced") == 1; EdgeAware.IsOn = Int(values, "edge_aware") == 1;
        AutoMask.IsOn = Int(values, "auto_mask", 1) == 1; Interval.Value = Int(values, "interval", 1);
        HigherMultiplier.SelectedIndex = multiplier > 4 ? multiplier - 4 : 0;
        if (Int(status, "version") >= 4)
        {
            SharpEnabled.IsOn = Int(values, "sharpen") == 1;
            SharpOverride.IsOn = Int(values, "sharp_override") == 1;
            SharpFilter.SelectedIndex = Int(values, "sharpen_shader");
            MotionSharpEnabled.IsOn = Int(values, "motion_sharpen") == 1;
            Sharpness.Value = Number(values, "sharpness", .5);
            MotionSharpness.Value = Number(values, "motion_sharpness", .2);
        }
        UpdateLabels(); SetChoices(MultiplierChoices, multiplier); SetChoices(StyleChoices, style);
        syncing = false;
    }

    JsonObject Values()
    {
        var result = new JsonObject
        {
            ["enabled"] = NrEnabled.IsOn ? 1 : 0, ["intensity"] = Strength.Value,
            ["pre_sr"] = PreSr.IsOn ? 1 : 0, ["cache"] = Cache.IsOn ? 1 : 0,
            ["interval"] = (int)Interval.Value, ["style"] = style, ["structure"] = Structure.Value,
            ["tone"] = Tone.Value, ["preset"] = Math.Max(0, NrPreset.SelectedIndex)
        };
        if (Int(status, "version") >= 3)
        {
            result["work_scale"] = WorkScale.Value; result["passes"] = Passes.SelectedIndex + 1;
            result["skin"] = Skin.Value; result["auto_mask"] = AutoMask.IsOn ? 1 : 0;
            result["detail"] = Detail.Value; result["colour"] = Colour.Value;
            result["reduced"] = Reduced.IsOn ? 1 : 0; result["edge_aware"] = EdgeAware.IsOn ? 1 : 0;
        }
        if (Flag(status, "can_mfg")) result["multiplier"] = multiplier;
        if (Int(status, "version") >= 4)
        {
            result["sharpen"] = SharpEnabled.IsOn ? 1 : 0;
            result["sharp_override"] = SharpOverride.IsOn ? 1 : 0;
            result["sharpen_shader"] = Math.Max(0, SharpFilter.SelectedIndex);
            result["motion_sharpen"] = MotionSharpEnabled.IsOn ? 1 : 0;
            result["sharpness"] = Sharpness.Value;
            result["motion_sharpness"] = MotionSharpness.Value;
        }
        return result;
    }

    void SetAvailability()
    {
        if (Controls is null) return;
        var session = game is not null && Flag(status, "can_edit");
        var connected = session && !requesting;
        var nrConnected = connected && Flag(status, "can_nr");
        var expanded = Int(status, "version") >= 3;
        var sharpening = Int(status, "version") >= 4;
        SharpeningGroup.Visibility = game is null || sharpening ? Visibility.Visible : Visibility.Collapsed;
        foreach (var control in new Control[] { SharpEnabled, SharpFilter, SharpOverride, MotionSharpEnabled })
            control.IsEnabled = connected && sharpening;
        Sharpness.IsEnabled = connected && sharpening && SharpEnabled.IsOn && SharpOverride.IsOn;
        MotionSharpness.IsEnabled = connected && sharpening && SharpEnabled.IsOn && MotionSharpEnabled.IsOn;
        foreach (var control in new Control[] { NrEnabled, Strength, Structure, Tone, NrPreset, PreSr, Cache, Interval })
            control.IsEnabled = nrConnected;
        foreach (var control in new Control[] { Passes, Skin, Detail, Colour, AutoMask, EdgeAware })
            control.IsEnabled = nrConnected && expanded;
        Reduced.IsEnabled = nrConnected && expanded && PreSr.IsOn;
        WorkScale.IsEnabled = nrConnected && expanded && (!PreSr.IsOn || Reduced.IsOn);
        Interval.IsEnabled = nrConnected && Cache.IsOn;
        HigherMultiplier.IsEnabled = connected && Flag(status, "can_mfg");
        foreach (var button in StyleChoices.Children.OfType<ToggleButton>()) button.IsEnabled = nrConnected;
        SavePreset.IsEnabled = connected && !dirty;
        ClearSaved.IsEnabled = connected;
        foreach (var button in MultiplierChoices.Children.OfType<ToggleButton>())
        {
            var count = int.Parse((string)button.Tag);
            button.IsEnabled = connected && Flag(status, "can_mfg") && (count <= 0 || count - 1 <= Int(status, "backend_max"));
        }
        CompatibilityNote.Text = "Update this game's package for model passes, image tuning and resolution controls.";
        CompatibilityNote.Visibility = connected && !expanded ? Visibility.Visible : Visibility.Collapsed;
        Feedback.Visibility = string.IsNullOrEmpty(Feedback.Text) ? Visibility.Collapsed : Visibility.Visible;
        SetChoices(MultiplierChoices, session ? multiplier : int.MinValue);
        SetChoices(StyleChoices, session ? style : int.MinValue);
        if (!session)
        {
            var wasSyncing = syncing;
            syncing = true;
            foreach (var toggle in new[] { NrEnabled, PreSr, Cache, Reduced, EdgeAware, AutoMask, SharpEnabled, SharpOverride, MotionSharpEnabled })
                toggle.IsOn = false;
            Interval.Value = double.NaN;
            NrPreset.SelectedIndex = Passes.SelectedIndex = HigherMultiplier.SelectedIndex = -1;
            SharpFilter.SelectedIndex = -1;
            syncing = wasSyncing;
        }
        UpdateLabels();
    }

    void UpdateLabels()
    {
        string Percent(double value) => value.ToString("0%", CultureInfo.CurrentCulture);
        string Unit(double value) => Classic ? value.ToString("0.00", CultureInfo.CurrentCulture) : Percent(value);
        if (game is null || !Flag(status, "can_edit"))
        {
            foreach (var label in new[] { StrengthText, StructureText, ToneText, DetailText, ColourText, SkinText, ScaleText, SharpnessText, MotionSharpnessText })
                label.Text = "—";
            return;
        }
        StrengthText.Text = Unit(Strength.Value); StructureText.Text = Unit(Structure.Value);
        ToneText.Text = Unit(Tone.Value); DetailText.Text = Unit(Detail.Value); ColourText.Text = Unit(Colour.Value);
        SkinText.Text = Skin.Value < 0 && !Classic ? "Follow structure" : Unit(Skin.Value); ScaleText.Text = Percent(WorkScale.Value);
        SharpnessText.Text = Int(status, "version") >= 4 ? Unit(Sharpness.Value) : "—";
        MotionSharpnessText.Text = Int(status, "version") >= 4 ? Unit(MotionSharpness.Value) : "—";
        foreach (var (slider, text) in new[] { (Strength, StrengthText), (Structure, StructureText), (Tone, ToneText),
            (Detail, DetailText), (Colour, ColourText), (Skin, SkinText), (WorkScale, ScaleText), (Sharpness, SharpnessText), (MotionSharpness, MotionSharpnessText) })
        {
            slider.IsThumbToolTipEnabled = false;
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetHelpText(slider, text.Text);
        }
    }
    static void SetChoices(Grid group, int selected)
    {
        foreach (var button in group.Children.OfType<ToggleButton>())
        {
            button.IsChecked = int.Parse((string)button.Tag) == selected;
        }
    }
    void Edited()
    {
        if (syncing || Feedback is null || !Flag(status, "can_edit")) return;
        dirty = true; UpdateLabels(); SetAvailability(); QueueApply();
    }
    void QueueApply() { if (!dirty || dragging || disposed) return; editTimer.Stop(); editTimer.Start(); }
    void OnEdit(object sender, RoutedEventArgs e) => Edited();
    void OnChoiceEdit(object sender, SelectionChangedEventArgs e) => Edited();
    void OnSliderEdit(object sender, RangeBaseValueChangedEventArgs e) => Edited();
    void OnNumberEdit(NumberBox sender, NumberBoxValueChangedEventArgs e) => Edited();
    void OnMultiplier(object sender, RoutedEventArgs e)
    {
        if (syncing) return;
        multiplier = int.Parse((string)((ToggleButton)sender).Tag);
        syncing = true; HigherMultiplier.SelectedIndex = 0; syncing = false;
        SetChoices(MultiplierChoices, multiplier); Edited();
    }
    void OnStyle(object sender, RoutedEventArgs e)
    {
        if (syncing) return;
        style = int.Parse((string)((ToggleButton)sender).Tag); SetChoices(StyleChoices, style); Edited();
    }
    void OnHigherMultiplier(object sender, SelectionChangedEventArgs e)
    {
        if (syncing || HigherMultiplier.SelectedIndex <= 0) return;
        multiplier = HigherMultiplier.SelectedIndex + 4; SetChoices(MultiplierChoices, multiplier); Edited();
    }

    async Task ApplyEditsAsync()
    {
        if (!dirty || dragging || game is null || requesting || disposed || !IsShown) return;
        var foreground = MainWindow.ForegroundProcessId();
        if (foreground != (uint)Environment.ProcessId && foreground != (uint)pid)
        {
            dirty = false; Feedback.Text = "Focus changed. Reopen the overlay to continue."; SetAvailability(); return;
        }
        requesting = true; var ticket = generation; SetAvailability();
        try
        {
            if (double.IsNaN(Interval.Value) || Interval.Value != Math.Floor(Interval.Value))
                throw new InvalidOperationException("Choose a whole cache interval from 1 to 16.");
            var result = await service.CompanionAsync("apply", game, Values(), pid);
            if (ticket != generation || disposed) return;
            status = result; dirty = false; Feedback.Text = "Applied by game"; RenderStatus();
        }
        catch (Exception error) { if (ticket == generation) { dirty = false; Feedback.Text = error.Message; } }
        finally { requesting = false; SetAvailability(); }
    }

    async void OnSave(object sender, RoutedEventArgs e) => await SaveAsync(false);
    async void OnClear(object sender, RoutedEventArgs e) => await SaveAsync(true);
    async Task SaveAsync(bool clear)
    {
        if (game is null || requesting || (!clear && dirty)) return;
        if (clear) { editTimer.Stop(); dirty = dragging = false; }
        requesting = true; var ticket = generation; SetAvailability();
        try
        {
            var result = await service.CompanionAsync(clear ? "reset" : "save", game, clear ? null : Values(), pid);
            if (ticket == generation) Feedback.Text = clear ? "Reset to this game's installed settings" : "Preset saved · the overlay helper will apply it";
        }
        catch (Exception error) { if (ticket == generation) Feedback.Text = error.Message; }
        finally { requesting = false; SetAvailability(); }
        await RefreshAsync();
    }

    [DllImport("user32.dll")] static extern uint GetDpiForWindow(nint hwnd);
    [DllImport("user32.dll")] static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(nint hwnd, out uint processId);
    [DllImport("user32.dll")] static extern bool IsWindow(nint hwnd);
    [DllImport("user32.dll")] static extern bool IsIconic(nint hwnd);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(nint hwnd);
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(nint hwnd, int attribute, ref int value, int size);
}
