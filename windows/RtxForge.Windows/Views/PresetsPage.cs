using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Views;

/// <summary>
/// Presets: the library presets (NR Strength, Sharpening, MFG) on their own page, as in
/// Game Mode. Save defaults separately from reviewed changes to all or chosen configured games.
/// </summary>
public sealed partial class PresetsPage : Page
{
    readonly MainWindow shell = App.Main!;
    readonly PresetControlsView tuning;
    readonly Button applyAll;
    readonly HyperlinkButton reset;
    readonly MenuFlyoutItem allGames;
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
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right };
        applyAll = new Button { Content = Prefs.Content("Apply to games…", "") };
        var menu = new MenuFlyout();
        allGames = new MenuFlyoutItem { Text = "All installed games" };
        allGames.Click += async (_, _) => await ApplyAllAsync();
        var choose = new MenuFlyoutItem { Text = "Choose games…" };
        choose.Click += async (_, _) => await ChooseGamesAsync();
        menu.Items.Add(allGames); menu.Items.Add(choose); applyAll.Flyout = menu;
        actions.Children.Add(Prefs.ActionButton("Save defaults", (_, _) => Save(), accent: true, glyph: ""));
        actions.Children.Add(applyAll);
        reset = new HyperlinkButton { Content = "Discard changes", HorizontalAlignment = HorizontalAlignment.Left,
            VerticalAlignment = VerticalAlignment.Center };
        reset.Click += (_, _) => { tuning.Value = shell.Settings.Presets; Refresh(); };
        ToolTipService.SetToolTip(reset, "Discard unsaved preset changes.");
        foreach (var action in actions.Children.OfType<Button>()) action.Width = 200;
        var actionRow = new Grid { ColumnSpacing = 12 };
        actionRow.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        actionRow.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        actionRow.Children.Add(reset); Grid.SetColumn(actions, 1); actionRow.Children.Add(actions);
        footer.Children.Add(changed); footer.Children.Add(actionRow);
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
        allGames.Text = $"All installed games ({count})";
        applyAll.IsEnabled = count > 0 && !shell.Busy;
        var dirty = tuning.HasChanges(shell.Settings.Presets);
        reset.IsEnabled = dirty;
        reset.Visibility = dirty ? Visibility.Visible : Visibility.Collapsed;
        changed.Text = (dirty ? "Unsaved changes. " : "") + "Save defaults for new installs, or apply these settings to configured games after review.";
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
        await shell.LaunchAction("apply", Configured(), tuning.Value);
        Refresh();
    }

    async Task ChooseGamesAsync()
    {
        var selected = new HashSet<Game>();
        var choices = new StackPanel { Spacing = 8 };
        choices.Children.Add(Prefs.Label("Select games, then review the changes before applying."));
        var dialog = new ContentDialog { Title = "Choose games", PrimaryButtonText = "Review changes", CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Primary, XamlRoot = XamlRoot, RequestedTheme = ActualTheme, IsPrimaryButtonEnabled = false,
            Content = new ScrollViewer { Content = choices, MaxHeight = 360 } };
        foreach (var game in Configured())
        {
            var check = new CheckBox { Content = game.Name };
            check.Checked += (_, _) => { selected.Add(game); dialog.IsPrimaryButtonEnabled = selected.Count > 0; };
            check.Unchecked += (_, _) => { selected.Remove(game); dialog.IsPrimaryButtonEnabled = selected.Count > 0; };
            choices.Children.Add(check);
        }
        if (await dialog.ShowAsync() == ContentDialogResult.Primary)
            await shell.LaunchAction("apply", Configured().Where(selected.Contains).ToList(), tuning.Value);
        Refresh();
    }
}
