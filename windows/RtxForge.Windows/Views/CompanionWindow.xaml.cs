using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using Windows.Graphics;

namespace RtxForge.Windows.Views;

public sealed partial class CompanionWindow : Window
{
    readonly MainWindow shell;
    readonly EngineForgeService service;
    readonly DispatcherQueueTimer pollTimer, editTimer;
    Game? game;
    JsonObject? status;
    int pid, multiplier = -1, style, generation;
    bool syncing = true, dirty, requesting, polling, disposed, dragging;
    public bool IsShown { get; private set; }

    public CompanionWindow(MainWindow owner, EngineForgeService engine)
    {
        shell = owner; service = engine;
        InitializeComponent();
        SystemBackdrop = new DesktopAcrylicBackdrop();
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
        var rounded = 2;
        DwmSetWindowAttribute(handle, 33, ref rounded, sizeof(int));
        var noBorder = unchecked((int)0xFFFFFFFE);
        DwmSetWindowAttribute(handle, 34, ref noBorder, sizeof(int));
        Root.KeyDown += (_, e) =>
        {
            if (e.Key == global::Windows.System.VirtualKey.Escape) { e.Handled = true; HidePanel(); }
        };
        AppWindow.Closing += (_, e) => { if (!disposed) { e.Cancel = true; HidePanel(); } };
        pollTimer = DispatcherQueue.CreateTimer();
        pollTimer.Interval = TimeSpan.FromSeconds(1);
        pollTimer.Tick += async (_, _) => await RefreshAsync();
        editTimer = DispatcherQueue.CreateTimer();
        editTimer.IsRepeating = false;
        editTimer.Interval = TimeSpan.FromMilliseconds(350);
        editTimer.Tick += async (_, _) => await ApplyEditsAsync();
        foreach (var slider in new[] { Strength, Structure, Tone, Skin, Detail, Colour, WorkScale })
        {
            slider.AddHandler(UIElement.PointerPressedEvent, new PointerEventHandler((_, _) => dragging = true), true);
            slider.AddHandler(UIElement.PointerReleasedEvent, new PointerEventHandler((_, _) => { dragging = false; QueueApply(); }), true);
            slider.AddHandler(UIElement.PointerCanceledEvent, new PointerEventHandler((_, _) => { dragging = false; QueueApply(); }), true);
            slider.AddHandler(UIElement.PointerCaptureLostEvent, new PointerEventHandler((_, _) => { dragging = false; QueueApply(); }), true);
        }
        syncing = false;
        SetAvailability();
    }

    public void Present()
    {
        if (!IsShown)
        {
            var area = DisplayArea.GetFromWindowId(shell.AppWindow.Id, DisplayAreaFallback.Primary).WorkArea;
            var scale = GetDpiForWindow(shell.Handle) / 96.0;
            var edge = (int)Math.Round(24 * scale);
            var width = Math.Min((int)Math.Round(420 * scale), area.Width - 2 * edge);
            AppWindow.MoveAndResize(new RectInt32(area.X + area.Width - width - edge,
                area.Y + edge, width, area.Height - 2 * edge));
        }
        ShortcutHint.Text = shell.CompanionShortcutProblem ?? (shell.Settings.PanelHotkey == "Disabled"
            ? "Esc to return to your game" : $"{shell.Settings.PanelHotkey} · show or hide");
        IsShown = true;
        // Resolve the foreground game before Activate makes the overlay foreground.
        var foreground = MainWindow.ForegroundProcessId();
        Activate(); pollTimer.Start();
        _ = RefreshAsync(foreground);
    }

    public void HidePanel() { editTimer.Stop(); pollTimer.Stop(); dirty = dragging = false; AppWindow.Hide(); IsShown = false; }
    public void Shutdown() { disposed = true; editTimer.Stop(); pollTimer.Stop(); Close(); }
    void OnHide(object sender, RoutedEventArgs e) => HidePanel();
    static int Int(JsonObject? data, string key, int fallback = 0) => data?[key]?.GetValue<int>() ?? fallback;
    static bool Flag(JsonObject? data, string key) => data?[key]?.GetValue<bool>() == true;
    static string Text(JsonObject? data, string key) => data?[key]?.GetValue<string>() ?? "";
    static double Number(JsonObject? data, string key, double fallback = 1) => data?[key]?.GetValue<double>() ?? fallback;

    async Task RefreshAsync(uint? observedForeground = null)
    {
        if (requesting || polling || disposed) return;
        polling = true;
        try
        {
            var foreground = observedForeground ?? MainWindow.ForegroundProcessId();
            var retained = foreground == (uint)Environment.ProcessId ? pid : 0;
            var active = await service.ActiveCompanionAsync(shell.Games, foreground, retained);
            if (disposed || requesting) return;
            var location = (active["row"] as JsonObject)?["game"]?.GetValue<string>();
            var next = shell.Games.FirstOrDefault(g => string.Equals(g.Id, location, StringComparison.OrdinalIgnoreCase));
            var nextPid = Int(active, "pid");
            if (game?.Id != next?.Id || pid != nextPid)
            {
                generation++; editTimer.Stop(); dirty = dragging = false;
                game = next; pid = nextPid; Feedback.Text = "";
            }
            var ticket = generation;
            var result = game is null ? active : await service.CompanionAsync("status", game);
            if (ticket != generation || disposed || requesting) return;
            status = result;
            GameName.Text = game?.Name ?? "Ready when you are";
            ConnectionText.Text = game is null ? Text(result, "detail")
                : Text(result, "state") == "running" ? "Connected · changes apply live" : Text(result, "detail");
            if (!dirty && result["values"] is JsonObject values) LoadValues(values);
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

    void RenderStatus()
    {
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
        if (Flag(status, "saved") && !Flag(status, "preset_compatible"))
            Feedback.Text = "The package changed. Save this preset again to use it with the new package.";
        else if (Text(status, "preset_error") is { Length: > 0 } error) Feedback.Text = "Preset could not apply: " + error;
    }

    void LoadValues(JsonObject values)
    {
        syncing = true;
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
        return result;
    }

    void SetAvailability()
    {
        if (Controls is null) return;
        var session = game is not null && Flag(status, "can_edit");
        var connected = session && !requesting;
        var expanded = Int(status, "version") >= 3;
        foreach (var control in new Control[] { NrEnabled, Strength, Structure, Tone, NrPreset, PreSr, Cache, Interval })
            control.IsEnabled = connected;
        foreach (var control in new Control[] { Passes, Skin, Detail, Colour, AutoMask, EdgeAware })
            control.IsEnabled = connected && expanded;
        Reduced.IsEnabled = connected && expanded && PreSr.IsOn;
        WorkScale.IsEnabled = connected && expanded && (!PreSr.IsOn || Reduced.IsOn);
        Interval.IsEnabled = connected && Cache.IsOn;
        HigherMultiplier.IsEnabled = connected && Flag(status, "can_mfg");
        foreach (var button in StyleChoices.Children.OfType<ToggleButton>()) button.IsEnabled = connected;
        SavePreset.IsEnabled = connected && !dirty;
        ClearSaved.IsEnabled = connected;
        ClearSaved.Visibility = Flag(status, "saved") ? Visibility.Visible : Visibility.Collapsed;
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
            foreach (var toggle in new[] { NrEnabled, PreSr, Cache, Reduced, EdgeAware, AutoMask })
                toggle.IsOn = false;
            Interval.Value = double.NaN;
            NrPreset.SelectedIndex = Passes.SelectedIndex = HigherMultiplier.SelectedIndex = -1;
            syncing = wasSyncing;
        }
        UpdateLabels();
    }

    void UpdateLabels()
    {
        string Percent(double value) => value.ToString("0%", CultureInfo.CurrentCulture);
        if (game is null || !Flag(status, "can_edit"))
        {
            foreach (var label in new[] { StrengthText, StructureText, ToneText, DetailText, ColourText, SkinText, ScaleText })
                label.Text = "—";
            return;
        }
        StrengthText.Text = Percent(Strength.Value); StructureText.Text = Percent(Structure.Value);
        ToneText.Text = Percent(Tone.Value); DetailText.Text = Percent(Detail.Value); ColourText.Text = Percent(Colour.Value);
        SkinText.Text = Skin.Value < 0 ? "Follow structure" : Percent(Skin.Value); ScaleText.Text = Percent(WorkScale.Value);
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
        if (game is null || requesting || dirty) return;
        requesting = true; var ticket = generation; SetAvailability();
        try
        {
            var result = await service.CompanionAsync(clear ? "forget" : "save", game, clear ? null : Values(), pid);
            if (ticket == generation) Feedback.Text = clear ? "Saved preset cleared · live settings kept" : "Preset saved · used while rtxForge is running";
        }
        catch (Exception error) { if (ticket == generation) Feedback.Text = error.Message; }
        finally { requesting = false; SetAvailability(); }
        await RefreshAsync();
    }

    [DllImport("user32.dll")] static extern uint GetDpiForWindow(nint hwnd);
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(nint hwnd, int attribute, ref int value, int size);
}
