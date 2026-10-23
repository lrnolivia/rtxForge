using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Controls;

/// <summary>A condensed per-game card; game files change only through the shared review flow.</summary>
public sealed class GameOverlayPreferencesView : StackPanel
{
    readonly MainWindow shell;
    readonly Game game;
    readonly StackPanel fields = new() { Spacing = 8 };
    readonly TextBlock status = Prefs.Label("The primary overlay follows the app setting. Menu and welcome choices can differ for this game.");
    bool loading;

    public GameOverlayPreferencesView(MainWindow shell, Game game)
    {
        this.shell = shell; this.game = game;
        Spacing = 10;
        Children.Add(status);
        Children.Add(fields);
        Rebuild();
    }

    bool Save(Action<JsonObject>? edit)
    {
        if (loading) return false;
        try
        {
            var fresh = ForgeSettings.EditGameOverlay(game, edit);
            shell.Settings.CopyOverlayFrom(fresh);
            shell.ConfigureCompanionShortcut();
            status.Text = "Saved for this game. Review Update Overlays to apply its menu choices; startup changes take effect next launch.";
            return true;
        }
        catch (Exception error) { status.Text = error.Message; return false; }
    }

    void Rebuild()
    {
        loading = true;
        fields.Children.Clear();
        var settings = ForgeSettings.Load();
        var values = settings.GameOverlayOptions(game);
        var inherited = !settings.GameOverlaySettings.ContainsKey(game.Id);
        var (defaultsRow, defaults) = Prefs.SwitchRow("Use app overlay settings", "Turn off to choose settings for this game.", inherited);
        fields.Children.Add(defaultsRow);
        defaults.Toggled += (_, _) =>
        {
            if (loading) return;
            Save(defaults.IsOn ? null : _ => { });
            Rebuild();
        };
        var options = new StackPanel { Spacing = 8 };
        fields.Children.Add(new Expander { Header = "Menu and welcome settings", Content = options,
            IsEnabled = !inherited,
            HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch });
        void Toggle(string title, string key)
        {
            var (row, control) = Prefs.SwitchRow(title, null, values[key]!.GetValue<bool>());
            control.Toggled += (_, _) => Save(v => v[key] = control.IsOn);
            options.Children.Add(row);
        }
        void Choice(string title, string key, string[] keys, string[] captions)
        {
            var (row, control) = Prefs.ComboRow(title, null, captions, Math.Max(0, Array.IndexOf(keys, values[key]!.ToString())));
            control.SelectionChanged += (_, _) => { if (control.SelectedIndex >= 0) Save(v => v[key] = keys[control.SelectedIndex]); };
            options.Children.Add(row);
        }
        Toggle("Welcome message", "overlay_welcome");
        Choice("Welcome position", "overlay_welcome_position", ForgeSettings.WelcomePositions,
            ["Top center", "Top left", "Top right", "Bottom left", "Bottom right"]);
        Toggle("Live feature statistics", "overlay_live_stats");
        Choice("Controls", "overlay_controls", ["unified", "classic"], ["Unified", "Advanced"]);
        var shortcut = new OverlayShortcutPicker(values["panel_hotkey"]!.ToString(), settingsRow: true);
        shortcut.SaveBinding = value => Save(v => v["panel_hotkey"] = value);
        options.Children.Add(shortcut);
        Toggle("OptiScaler menu", "optiscaler_ui");
        Toggle("OptiScaler intro", "optiscaler_intro");
        Choice("OptiScaler shortcut", "optiscaler_hotkey", ["Insert", "F8", "Disabled"], ["Insert", "F8", "Disabled"]);
        Toggle("ReShade menu", "reshade_ui");
        Toggle("ReShade welcome", "reshade_intro");
        Toggle("Native Vulkan MFG menu and hint", "vulkan_mfg_native_menu");
        var update = new Button { Content = "Update Overlays", HorizontalAlignment = HorizontalAlignment.Right,
            IsEnabled = game.Installed && shell.Service is EngineForgeService };
        update.Click += async (_, _) =>
        {
            if (shell.Service is not EngineForgeService engine) return;
            update.IsEnabled = false;
            try { await OperationDialog.ShowPreparedAsync(shell, "update-overlays", progress => engine.ReviewOverlayPackagesAsync(progress, [game.Id])); }
            finally { update.IsEnabled = true; }
        };
        fields.Children.Add(update);
        loading = false;
    }
}
