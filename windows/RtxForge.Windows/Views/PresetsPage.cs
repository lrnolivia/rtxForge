using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Views;

/// <summary>
/// Presets: the library presets (NR Strength, Sharpening, MFG) on their own page, as in
/// Game Mode. The footer matches Linux: Reset, Select games and Apply to all.
/// </summary>
public sealed partial class PresetsPage : Page
{
    readonly MainWindow shell = App.Main!;
    readonly PresetControlsView tuning;
    readonly Button reset, selectGames, applyAll;
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

        var footer = new Grid { ColumnSpacing = 12 };
        footer.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        footer.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        changed.VerticalAlignment = VerticalAlignment.Center;
        changed.TextWrapping = TextWrapping.WrapWholeWords;
        footer.Children.Add(changed);
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right };
        reset = Prefs.ActionButton("Reset", (_, _) => { tuning.Value = shell.Settings.Presets; Refresh(); }, glyph: "");
        ToolTipService.SetToolTip(reset, "Discard unsaved preset changes.");
        selectGames = Prefs.ActionButton("Select games", (_, _) => SelectGames(), glyph: "");
        ToolTipService.SetToolTip(selectGames, "Choose games in the Library to apply these presets to.");
        applyAll = Prefs.ActionButton("Apply to all", async (_, _) => await ApplyAllAsync(), accent: true, glyph: "");
        ToolTipService.SetToolTip(applyAll, "Review these presets for every configured game, and keep them as your defaults.");
        actions.Children.Add(reset); actions.Children.Add(selectGames); actions.Children.Add(applyAll);
        Grid.SetColumn(actions, 1); footer.Children.Add(actions);
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
        tuning.SetMode(shell.Mode, legacy: shell.Settings.RuntimeProvider != "skynizz", dynamicSupported: shell.Settings.DynamicMfgSupported);
        Refresh();
    }

    List<Game> Configured() => shell.Games.Where(g => g.Installed && !g.Blocked).ToList();

    void Refresh()
    {
        var count = Configured().Count;
        var dirty = tuning.HasChanges(shell.Settings.Presets);
        reset.IsEnabled = dirty && !shell.Busy;
        selectGames.IsEnabled = count > 0 && !shell.Busy;
        applyAll.IsEnabled = !shell.Busy;
        changed.Text = (dirty ? "Unsaved changes. " : "")
            + (count > 0 ? $"Apply to all reviews {count} configured game{(count == 1 ? "" : "s")} and keeps these as your defaults."
                         : "No games have features installed yet. Apply to all saves these as your defaults for new installs.");
    }

    void Save(Tuning value)
    {
        shell.Settings.NrStrength = value.NrStrength;
        shell.Settings.SharpeningStrength = value.SharpeningStrength;
        shell.Settings.MfgMultiplier = value.MfgMultiplier;
        shell.Settings.NrOnLaunch = value.NrOnLaunch == true;
        shell.Settings.FeatureControls = value.FeatureControls;
        shell.Settings.Save();
        Refresh();
    }

    /// <summary>Library presets mode applies the saved defaults, so unsaved edits are kept first.</summary>
    void SelectGames()
    {
        if (tuning.HasChanges(shell.Settings.Presets)) Save(tuning.Value);
        shell.BeginPresetSelection();
    }

    /// <summary>Reviewed apply to every configured game; the presets become the defaults once it completes.</summary>
    async Task ApplyAllAsync()
    {
        var value = tuning.Value;
        var targets = Configured();
        if (targets.Count == 0) { Save(value); shell.ShowToast("Saved as your defaults for new installs."); return; }
        if (await shell.LaunchAction("apply", targets, value)) Save(value);
        Refresh();
    }
}
