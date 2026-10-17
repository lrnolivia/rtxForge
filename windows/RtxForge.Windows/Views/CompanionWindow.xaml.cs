using System.Globalization;
using System.Text.Json.Nodes;
using Microsoft.UI;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using Windows.Graphics;
using Color = global::Windows.UI.Color;

namespace RtxForge.Windows.Views;

public sealed partial class CompanionWindow : Window
{
    readonly MainWindow shell;
    readonly EngineForgeService service;
    readonly DispatcherQueueTimer timer;
    Game? game;
    JsonObject? status;
    bool syncing = true, dirty, requesting, polling, disposed;
    int multiplier = -1, generation;
    DateTime feedbackUntil;
    public bool IsShown { get; private set; }

    public CompanionWindow(MainWindow owner, EngineForgeService engine)
    {
        shell = owner;
        service = engine;
        InitializeComponent();
        SystemBackdrop = new DesktopAcrylicBackdrop();
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(DragBar);
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "rtxforge.ico"));
        if (AppWindow.Presenter is OverlappedPresenter presenter)
        {
            presenter.IsAlwaysOnTop = true;
            presenter.IsMaximizable = false;
            presenter.IsMinimizable = false;
            presenter.IsResizable = false;
            presenter.SetBorderAndTitleBar(true, false);
        }
        Root.KeyDown += (_, e) =>
        {
            if (e.Key == global::Windows.System.VirtualKey.Escape) { e.Handled = true; HidePanel(); }
        };
        AppWindow.Closing += (_, e) => { if (!disposed) { e.Cancel = true; HidePanel(); } };
        timer = DispatcherQueue.CreateTimer();
        timer.Interval = TimeSpan.FromSeconds(1);
        timer.Tick += async (_, _) => await RefreshAsync();
        syncing = false;
    }

    public void Present(Game? selected)
    {
        var items = shell.Games.OrderByDescending(g => g.Installed).ThenBy(g => g.Name).ToList();
        if (selected is not null && items.All(g => g.Id != selected.Id)) items.Insert(0, selected);
        var next = selected ?? game ?? items.FirstOrDefault(g => g.Id == shell.Settings.CompanionGame) ?? items.FirstOrDefault();
        var same = game?.Id == next?.Id;
        syncing = true;
        GamePicker.ItemsSource = items;
        GamePicker.SelectedItem = items.FirstOrDefault(g => g.Id == next?.Id);
        syncing = false;
        if (!same || game is null) SelectGame(GamePicker.SelectedItem as Game);
        ShortcutHint.Text = shell.CompanionShortcutProblem ?? (shell.Settings.PanelHotkey == "Disabled"
            ? "Shortcut disabled · open this panel from Game Details"
            : $"{shell.Settings.PanelHotkey} to show or hide · keep rtxForge running");
        if (!IsShown)
        {
            var area = DisplayArea.GetFromWindowId(shell.AppWindow.Id, DisplayAreaFallback.Primary).WorkArea;
            var scale = GetDpiForWindow(shell.Handle) / 96.0;
            var width = (int)Math.Round(460 * scale);
            var height = Math.Min((int)Math.Round(790 * scale), area.Height - (int)(32 * scale));
            AppWindow.MoveAndResize(new RectInt32(area.X + area.Width - width - (int)(24 * scale),
                area.Y + (area.Height - height) / 2, width, height));
        }
        IsShown = true;
        Activate();
        timer.Start();
        _ = RefreshAsync();
    }

    public void HidePanel() { timer.Stop(); AppWindow.Hide(); IsShown = false; }
    public void Shutdown() { disposed = true; timer.Stop(); Close(); }
    void OnHide(object sender, RoutedEventArgs e) => HidePanel();
    void OnGameChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!syncing) SelectGame(GamePicker.SelectedItem as Game);
    }
    void SelectGame(Game? selected)
    {
        game = selected;
        generation++;
        status = null;
        dirty = false;
        Feedback.Text = "";
        if (game is not null) { shell.Settings.CompanionGame = game.Id; shell.Settings.Save(); }
        SetAvailability();
        _ = RefreshAsync();
    }

    static int Int(JsonObject? data, string key, int fallback = 0) => data?[key]?.GetValue<int>() ?? fallback;
    static bool Flag(JsonObject? data, string key) => data?[key]?.GetValue<bool>() == true;
    static string Text(JsonObject? data, string key) => data?[key]?.GetValue<string>() ?? "";

    async Task RefreshAsync()
    {
        if (requesting || polling || disposed || game is null) return;
        polling = true;
        var selected = game;
        var ticket = generation;
        try
        {
            var result = await service.CompanionAsync("status", selected);
            if (ticket != generation || disposed || requesting) return;
            status = result;
            RenderStatus();
            if (!dirty)
            {
                var values = (result["values"] as JsonObject)?.DeepClone() as JsonObject ?? new();
                if (Text(result, "state") == "waiting" && Flag(result, "preset_compatible") && result["saved_values"] is JsonObject saved)
                    foreach (var pair in saved) values[pair.Key] = pair.Value?.DeepClone();
                LoadValues(values);
            }
        }
        catch (Exception error)
        {
            if (ticket == generation)
            {
                status = new JsonObject { ["state"] = "unavailable", ["detail"] = error.Message };
                RenderStatus();
            }
        }
        finally { polling = false; SetAvailability(); }
    }

    void RenderStatus()
    {
        var running = Text(status, "state") == "running";
        ConnectionText.Text = running ? "Connected to game" : Text(status, "state") switch
        {
            "waiting" => "Game is not connected", "stalled" => "Game is not responding", _ => "Controls unavailable"
        };
        ConnectionDot.Fill = new SolidColorBrush(running ? Color.FromArgb(255, 157, 211, 77) : Color.FromArgb(255, 173, 180, 188));
        ConnectionDetail.Text = running ? "Apply live changes now. Saving also applies and reuses them." : Text(status, "detail");
        var fresh = Flag(status, "native_fresh");
        MfgActual.Text = !running ? "Start the game to verify output."
            : !Flag(status, "can_mfg") ? "MFG is managed by the installed package."
            : !fresh ? "Waiting for native frame-generation status."
            : Int(status, "native_status") != 0 ? "The game reported an FG error."
            : Int(status, "native_mode") == 0 ? "Frame Generation is off in the game."
            : Int(status, "native_presented") > 1 ? $"{Int(status, "native_presented")} frames presented · reported by game"
            : "Frame Generation is enabled; waiting for generated output.";
        MfgDetail.Text = "Includes the rendered frame.";
        NrActual.Text = running ? Flag(status, "nr_running") ? "NR is active" : "NR is not currently evaluating" : "Status appears when this game connects.";
        if (running && status?["rendered_fps"] is JsonNode fps)
            NrActual.Text += $" · {fps.GetValue<double>():0.#} rendered FPS";
        TelemetryText.Text = running && status?["nr_ms"] is JsonNode timing
            ? $"NR GPU time: {timing.GetValue<double>():0.00} ms" : "NR GPU timing is unavailable.";
        if (Flag(status, "saved") && !Flag(status, "preset_compatible"))
            Feedback.Text = "The package changed. Review these controls and save a new preset to use it again.";
        else if (Text(status, "preset_error") is { Length: > 0 } error)
            Feedback.Text = "Saved preset could not apply: " + error;
        else if (!dirty && DateTime.UtcNow >= feedbackUntil)
            Feedback.Text = Flag(status, "saved") ? "Saved in rtxForge. Applies while rtxForge is running." : "";
    }

    void LoadValues(JsonObject values)
    {
        syncing = true;
        multiplier = Int(values, "multiplier", -1);
        NrEnabled.IsOn = Int(values, "enabled", 1) == 1;
        Strength.Value = values["intensity"]?.GetValue<double>() ?? 1;
        NrPreset.SelectedIndex = Int(values, "preset");
        PreSr.IsOn = Int(values, "pre_sr", 1) == 1;
        Cache.IsOn = Int(values, "cache") == 1;
        Interval.Value = Int(values, "interval", 1);
        NrStyle.SelectedIndex = Int(values, "style");
        Structure.Value = values["structure"]?.GetValue<double>() ?? 1;
        Tone.Value = values["tone"]?.GetValue<double>() ?? 1;
        HigherMultiplier.SelectedIndex = multiplier > 4 ? multiplier - 4 : 0;
        SetMultiplierVisual();
        StrengthText.Text = Strength.Value.ToString("0%", CultureInfo.CurrentCulture);
        syncing = false;
    }

    JsonObject Values()
    {
        var result = new JsonObject
        {
            ["enabled"] = NrEnabled.IsOn ? 1 : 0, ["intensity"] = Strength.Value,
            ["pre_sr"] = PreSr.IsOn ? 1 : 0, ["cache"] = Cache.IsOn ? 1 : 0,
            ["interval"] = (int)Interval.Value, ["style"] = Math.Max(0, NrStyle.SelectedIndex),
            ["structure"] = Structure.Value, ["tone"] = Tone.Value, ["preset"] = Math.Max(0, NrPreset.SelectedIndex)
        };
        if (Flag(status, "can_mfg")) result["multiplier"] = multiplier;
        return result;
    }

    void SetAvailability()
    {
        if (ApplyLive is null) return;
        var editable = !requesting && Flag(status, "can_save");
        NrEnabled.IsEnabled = Strength.IsEnabled = NrPreset.IsEnabled = Advanced.IsEnabled = editable;
        HigherMultiplier.IsEnabled = editable && Flag(status, "can_mfg");
        foreach (var button in MultiplierChoices.Children.OfType<ToggleButton>())
        {
            var count = int.Parse((string)button.Tag);
            button.IsEnabled = editable && Flag(status, "can_mfg") &&
                (Text(status, "state") != "running" || count <= 0 || count - 1 <= Int(status, "backend_max"));
        }
        ApplyLive.IsEnabled = !requesting && dirty && Flag(status, "can_edit");
        SavePreset.IsEnabled = editable;
        SavePreset.Content = Text(status, "state") == "running" ? "Save + apply" : "Save for game";
        ClearSaved.IsEnabled = !requesting && Flag(status, "saved");
        ClearSaved.Visibility = Flag(status, "saved") ? Visibility.Visible : Visibility.Collapsed;
        Feedback.Visibility = string.IsNullOrEmpty(Feedback.Text) ? Visibility.Collapsed : Visibility.Visible;
    }

    void Edited()
    {
        if (syncing || Feedback is null) return;
        dirty = true;
        Feedback.Visibility = Visibility.Visible;
        Feedback.Text = "Changes are ready. Apply live, or save them for this game.";
        StrengthText.Text = Strength.Value.ToString("0%", CultureInfo.CurrentCulture);
        SetAvailability();
    }
    void OnEdit(object sender, RoutedEventArgs e) => Edited();
    void OnChoiceEdit(object sender, SelectionChangedEventArgs e) => Edited();
    void OnSliderEdit(object sender, RangeBaseValueChangedEventArgs e) => Edited();
    void OnNumberEdit(NumberBox sender, NumberBoxValueChangedEventArgs e) => Edited();
    void OnMultiplier(object sender, RoutedEventArgs e)
    {
        if (syncing) return;
        multiplier = int.Parse((string)((ToggleButton)sender).Tag);
        syncing = true; HigherMultiplier.SelectedIndex = 0; syncing = false;
        SetMultiplierVisual(); Edited();
    }
    void OnHigherMultiplier(object sender, SelectionChangedEventArgs e)
    {
        if (syncing) return;
        multiplier = HigherMultiplier.SelectedIndex <= 0 ? 4 : HigherMultiplier.SelectedIndex + 4;
        SetMultiplierVisual(); Edited();
    }
    void SetMultiplierVisual()
    {
        foreach (var button in MultiplierChoices.Children.OfType<ToggleButton>())
        {
            var chosen = int.Parse((string)button.Tag) == multiplier;
            button.IsChecked = chosen;
            button.Background = new SolidColorBrush(chosen ? Color.FromArgb(255, 86, 130, 29) : Color.FromArgb(255, 65, 70, 76));
            button.Foreground = new SolidColorBrush(Colors.White);
        }
    }

    async void OnApply(object sender, RoutedEventArgs e) => await ExecuteAsync("apply");
    async void OnSave(object sender, RoutedEventArgs e) => await ExecuteAsync("save");
    async void OnClear(object sender, RoutedEventArgs e) => await ExecuteAsync("forget");
    async Task ExecuteAsync(string action)
    {
        if (game is null || requesting) return;
        requesting = true;
        var ticket = generation;
        GamePicker.IsEnabled = false;
        SetAvailability();
        try
        {
            if (action != "forget" && (double.IsNaN(Interval.Value) || Interval.Value != Math.Floor(Interval.Value)))
                throw new InvalidOperationException("Choose a whole cache interval between 1 and 16.");
            var result = await service.CompanionAsync(action, game, action == "forget" ? null : Values());
            if (ticket != generation || disposed) return;
            if (action == "apply") { dirty = false; status = result; RenderStatus(); Feedback.Text = "Applied by the game."; }
            else { Feedback.Text = Text(result, "detail"); }
            feedbackUntil = DateTime.UtcNow.AddSeconds(5);
        }
        catch (Exception error)
        {
            if (ticket == generation) { Feedback.Text = error.Message; feedbackUntil = DateTime.UtcNow.AddSeconds(10); }
        }
        finally { requesting = false; GamePicker.IsEnabled = true; SetAvailability(); }
        await RefreshAsync();
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    static extern uint GetDpiForWindow(nint hwnd);
}
