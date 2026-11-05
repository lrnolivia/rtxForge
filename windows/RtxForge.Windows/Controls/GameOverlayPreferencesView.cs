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
    readonly TextBlock status = Prefs.Label("Appearance, layout, menus and shortcuts below apply only to this game.");
    readonly Border appearanceCard = new() { Style = Prefs.GetStyle("ForgeSettingsCardStyle") };
    ToggleSwitch? inheritedToggle;
    Expander? menuOptions;
    bool loading;

    public GameOverlayPreferencesView(MainWindow shell, Game game)
    {
        this.shell = shell; this.game = game;
        Spacing = 10;
        Children.Add(status);
        Children.Add(appearanceCard);Children.Add(fields);
        RebuildAppearance();Rebuild();
    }

    void RebuildAppearance()
    {
        var appearance = new OverlayPresentationView(edit =>
        {
            try
            {
                edit();
                var glass = GlassAppearance.Load(GlassAppearance.GameFilePath(game));
                var fresh = ForgeSettings.EditGameOverlay(game, s => { s["overlay_appearance"] = glass.ToJson(); s["overlay_theme"] = glass.Theme; });
                shell.Settings.CopyOverlayFrom(fresh);
                loading=true;if(inheritedToggle is not null)inheritedToggle.IsOn=false;loading=false;
                if(menuOptions is not null)menuOptions.IsEnabled=true;
                status.Text = "Appearance saved for this game.";
            }
            catch (Exception error) { status.Text = error.Message; }
        }, shell.Service as EngineForgeService, game, appliedGlobally: fresh =>
        {
            shell.Settings.CopyOverlayFrom(fresh);
            status.Text = "This style is now your default, and every game's overlay uses it.";
        });
        appearance.SetRendererEnabled(GlassAppearance.OverlayOptions(ForgeSettings.Load(),game)["overlay_renderer"]?.ToString() != "optiscaler");
        appearanceCard.Child=appearance;
    }

    bool Save(Action<JsonObject>? edit)
    {
        if (loading) return false;
        try
        {
            var fresh = ForgeSettings.EditGameOverlay(game, edit);
            OverlayHelper.CacheRenderer(game,fresh);
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
        var values = GlassAppearance.OverlayOptions(settings,game);
        var inherited = !settings.GameOverlaySettings.ContainsKey(game.Id);
        var (defaultsRow, defaults) = Prefs.SwitchRow("Use app overlay settings", "Turn off to choose settings for this game.", inherited, "\uE713");
        inheritedToggle=defaults;fields.Children.Add(defaultsRow);
        defaults.Toggled += (_, _) =>
        {
            if (loading) return;
            if(Save(defaults.IsOn ? null : _ => { })){RebuildAppearance();Rebuild();}
        };
        var options = new StackPanel { Spacing = 8 };
        menuOptions=new Expander { Header = "Menu and welcome settings", Content = options,
            IsEnabled = !inherited,
            HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch };
        fields.Children.Add(menuOptions);
        var (rendererRow,renderer)=Prefs.ComboRow("Overlay","Choose rtxForge to re-enable this game's panel.",["rtxForge","Native"],values["overlay_renderer"]?.ToString()=="optiscaler"?1:0,"\uE7F4");
        renderer.SelectionChanged+=(_,_)=>{if(loading||renderer.SelectedIndex<0)return;if(Save(v=>v["overlay_renderer"]=renderer.SelectedIndex==1?"optiscaler":"game"))RebuildAppearance();};
        fields.Children.Insert(1,rendererRow);
        void Toggle(string title, string key)
        {
            var glyph = key == "overlay_live_stats" ? "\uE9D9" : key.EndsWith("intro") || key == "overlay_welcome" ? "\uE8F2" : "\uE700";
            var (row, control) = Prefs.SwitchRow(title, null, values[key]!.GetValue<bool>(), glyph);
            control.Toggled += (_, _) => Save(v => v[key] = control.IsOn);
            options.Children.Add(row);
        }
        void Choice(string title, string key, string[] keys, string[] captions)
        {
            var (row, control) = Prefs.ComboRow(title, null, captions, Math.Max(0, Array.IndexOf(keys, values[key]!.ToString())), key == "overlay_welcome_position" ? "\uE8B9" : "\uE765");
            control.SelectionChanged += (_, _) => { if (control.SelectedIndex >= 0) Save(v => v[key] = keys[control.SelectedIndex]); };
            options.Children.Add(row);
        }
        Toggle("Welcome message", "overlay_welcome");
        Choice("Welcome position", "overlay_welcome_position", ForgeSettings.WelcomePositions,
            ["Top center", "Top left", "Top right", "Bottom left", "Bottom right"]);
        Toggle("Live feature statistics", "overlay_live_stats");
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
        fields.Children.Add(Prefs.Row("Update overlays", "Review and apply this game's overlay menu and welcome choices.", update, "\uE9D9"));
        loading = false;
    }
}
