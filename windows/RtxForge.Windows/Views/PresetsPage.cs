using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Views;

/// <summary>
/// Presets: the library presets (NR Strength, Sharpening, MFG) on their own page, as in
/// Game Mode. Apply to every configured game, or choose games in the Library's presets mode.
/// </summary>
public sealed partial class PresetsPage : Page
{
    readonly MainWindow shell = App.Main!;
    readonly PresetControlsView tuning;
    readonly Button applyAll, reset;
    readonly TextBlock changed = Prefs.Label("", "ForgeCaptionDimTextStyle");

    public PresetsPage()
    {
        InitializeComponent();
        tuning = new PresetControlsView(shell.Settings.Presets, shell.Settings.OverlayControls == "classic");
        tuning.Changed += (_, _) => Refresh();

        var page = new StackPanel { Spacing = 8, Padding = new Thickness(36, 12, 36, 48) };
        page.Children.Add(new TextBlock { Text = "Presets", Style = Prefs.GetStyle("ForgePageTitleTextStyle") });
        page.Children.Add(Prefs.Label("The same NR, MFG and image controls as the overlay. Save them for new installs or apply them to configured games."));
        tuning.Margin = new Thickness(0, 24, 0, 0);
        page.Children.Add(tuning);
        page.Children.Add(Prefs.Label("Saved settings take effect on the next game launch. They do not verify the rendered effect.", "ForgeCaptionDimTextStyle"));

        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, Margin = new Thickness(0, 16, 0, 0) };
        applyAll = Prefs.ActionButton("Apply to all configured games", async (_, _) => await ApplyAllAsync(), accent: true, glyph: "");
        actions.Children.Add(applyAll);
        actions.Children.Add(Prefs.ActionButton("Save preset", (_, _) => Save(), accent: true, glyph: ""));
        actions.Children.Add(Prefs.ActionButton("Select games to apply presets", (_, _) => { Save(); shell.BeginPresetSelection(); }, glyph: ""));
        reset = Prefs.ActionButton("Reset", (_, _) => { tuning.Value = shell.Settings.Presets; Refresh(); }, glyph: "");
        ToolTipService.SetToolTip(reset, "Discard unsaved preset changes.");
        actions.Children.Add(reset);
        page.Children.Add(actions);
        page.Children.Add(changed);
        Content = new ScrollViewer { Content = page, HorizontalScrollMode = ScrollMode.Disabled };
        // One centered column, as every page (Controls/PageMargins).
        SizeChanged += (_, e) => page.Padding = PageMargins.For(e.NewSize.Width);
        shell.GamesChanged += Refresh;
        Unloaded += (_, _) => shell.GamesChanged -= Refresh;
    }

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);
        shell.EndPresetSelection();
        tuning.SetMode(shell.Mode, legacy: shell.Settings.RuntimeProvider != "skynizz");
        Refresh();
    }

    List<Game> Configured() => shell.Games.Where(g => g.Installed && !g.Blocked).ToList();

    void Refresh()
    {
        var count = Configured().Count;
        applyAll.Content = Prefs.Content($"Apply to all configured games ({count})", "");
        applyAll.IsEnabled = count > 0 && !shell.Busy;
        var dirty = tuning.HasChanges(shell.Settings.Presets);
        reset.IsEnabled = dirty;
        changed.Text = dirty ? "Unsaved changes · applying saves them as your library presets." : "Saved · " + MainWindow.PresetSummary(shell.Settings.Presets);
    }

    void Save()
    {
        var value = tuning.Value;
        shell.Settings.NrStrength = value.NrStrength;
        shell.Settings.SharpeningStrength = value.SharpeningStrength;
        shell.Settings.MfgMultiplier = value.MfgMultiplier;
        shell.Settings.NrOnLaunch = value.NrOnLaunch == true;
        shell.Settings.FeatureControls = value.FeatureControls;
        shell.Settings.Save();
        Refresh();
    }

    async Task ApplyAllAsync()
    {
        Save();
        await shell.LaunchAction("apply", Configured(), shell.Settings.Presets);
        Refresh();
    }
}
