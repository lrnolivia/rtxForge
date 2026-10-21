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

        var page = new Grid { RowSpacing = 20, Padding = new Thickness(36, 12, 36, 24) };
        page.RowDefinitions.Add(new() { Height = GridLength.Auto });
        page.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        page.RowDefinitions.Add(new() { Height = GridLength.Auto });
        var heading = new StackPanel { Spacing = 6 };
        heading.Children.Add(new TextBlock { Text = "Presets", Style = Prefs.GetStyle("ForgePageTitleTextStyle") });
        heading.Children.Add(Prefs.Label("Your defaults for new installs. Review games to apply them to existing packages."));
        page.Children.Add(heading);
        var scroll = new ScrollViewer { Content = tuning, HorizontalScrollMode = ScrollMode.Disabled,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Padding = new Thickness(0, 0, 4, 4) };
        Grid.SetRow(scroll, 1); page.Children.Add(scroll);

        var footer = new StackPanel { Spacing = 8 };
        var actions = new PresetColumns(180, 4) { ColumnSpacing = 8, RowSpacing = 8 };
        applyAll = Prefs.ActionButton("Review all games…", async (_, _) => await ApplyAllAsync(), glyph: "");
        actions.Children.Add(Prefs.ActionButton("Save as default", (_, _) => Save(), accent: true, glyph: ""));
        actions.Children.Add(Prefs.ActionButton("Choose games…", (_, _) => { Save(); shell.BeginPresetSelection(); }, glyph: ""));
        actions.Children.Add(applyAll);
        reset = Prefs.ActionButton("Reset changes", (_, _) => { tuning.Value = shell.Settings.Presets; Refresh(); }, glyph: "");
        ToolTipService.SetToolTip(reset, "Discard unsaved preset changes.");
        actions.Children.Add(reset);
        foreach (var action in actions.Children.OfType<Button>()) action.HorizontalAlignment = HorizontalAlignment.Stretch;
        footer.Children.Add(actions); footer.Children.Add(changed);
        Grid.SetRow(footer, 2); page.Children.Add(footer); Content = page;
        // One centered column, as every page (Controls/PageMargins).
        SizeChanged += (_, e) => page.Padding = PageMargins.For(e.NewSize.Width, bottom: 24);
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
        applyAll.Content = Prefs.Content($"Review all games… ({count})", "");
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
