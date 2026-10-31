using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Views;

/// <summary>
/// Extras: tools that work across the library. Per-game tools (NR diagnosis,
/// ReShade and add-ons) live in each game's Details.
/// </summary>
public sealed partial class ExtrasPage : Page
{
    readonly MainWindow shell = App.Main!;

    public ExtrasPage()
    {
        InitializeComponent();
        var page = new StackPanel { Spacing = 8, Padding = new Thickness(36, 12, 36, 48) };
        page.Children.Add(new TextBlock { Text = "Extras", Style = Prefs.GetStyle("ForgePageTitleTextStyle") });
        page.Children.Add(Prefs.Label("Tools for your whole library. Every game change is reviewed before it is applied."));
        var engine = shell.Service as EngineForgeService;

        // The three one-button tools share a row; the two longer tools pair below, so
        // neither row leaves a short card beside a tall one.
        var actions = new PresetColumns(300, 3) { ColumnSpacing = 16, RowSpacing = 16, Margin = new Thickness(0, 12, 0, 0) };
        actions.Children.Add(Card("Update the rtxForge Overlay", "Bring the in-game overlay in your installed games up to date. Your tuning, NR model and restore backups are kept.",
            engine is null ? null : new OverlayUiReviewView(engine, packages: true)));
        actions.Children.Add(Card("Update DLSS files", "Replace older DLSS files across your library. Originals are backed up.",
            Action("Review games", "", () => shell.LaunchAction("update-dlss", shell.Games.Where(g => !g.Blocked).ToList()))));
        actions.Children.Add(Card("Undo previous changes", "Restore the files from an earlier install, update or restore.",
            Action("Show changes", "", shell.ShowPreviousChangesAsync)));
        page.Children.Add(actions);

        var hdr = new PreferencesGroup("RenoDX HDR");
        var chooseHdrGame = Prefs.ActionButton("Choose game", async (_, _) => await ChooseHdrGameAsync());
        chooseHdrGame.IsEnabled = shell.Games.Count > 0;
        hdr.Add(Prefs.Row("Game HDR", "Install matching HDR mods automatically, or use a custom RenoDX package for a game. Required ReShade files are managed with it.", chooseHdrGame, "\uE793"));
        page.Children.Add(hdr);

        var tools = new PresetColumns(420, 2) { ColumnSpacing = 16, RowSpacing = 16, Margin = new Thickness(0, 8, 0, 0) };
        tools.Children.Add(Card("Global Settings", "Turn neural rendering or frame generation on or off, or set the multiplier, in every game with a package installed. Defaults for future installs stay the same.",
            engine is null ? null : new GlobalControlsView(engine, settingsRows: true), pinToBottom: false));
        tools.Children.Add(Card("App storage", "Downloads, backups and caches rtxForge keeps. Clean up what no game needs.",
            engine is null ? null : new AppStorageView(shell, engine), pinToBottom: false));
        page.Children.Add(tools);

        Content = new ScrollViewer { Content = page, HorizontalScrollMode = ScrollMode.Disabled };
        SizeChanged += (_, e) => page.Padding = PageMargins.For(e.NewSize.Width);
    }

    async Task ChooseHdrGameAsync()
    {
        var games = shell.Games.OrderBy(g => g.Name).ToList();
        if (games.Count == 0) return;
        var picker = new ComboBox { ItemsSource = games.Select(g => g.Name).ToList(), SelectedIndex = 0,
            HorizontalAlignment = HorizontalAlignment.Stretch, MinWidth = 280 };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(picker, "Game for RenoDX HDR");
        var dialog = shell.NewDialog();
        dialog.Title = "RenoDX HDR";
        dialog.Content = Prefs.Row("Game", "Open its automatic and custom HDR package controls.", picker, "\uE7FC");
        dialog.PrimaryButtonText = "Open HDR controls";
        dialog.CloseButtonText = "Cancel";
        if (await dialog.ShowAsync() == ContentDialogResult.Primary && picker.SelectedIndex >= 0)
            shell.OpenGame(games[picker.SelectedIndex], "Tools");
    }

    UIElement Action(string text, string glyph, Func<Task> run)
    {
        var button = Prefs.ActionButton(text, async (_, _) => await run(), glyph: glyph);
        button.HorizontalAlignment = HorizontalAlignment.Right;
        button.IsEnabled = !shell.Service.IsPreview;
        return button;
    }

    /// <summary>
    /// A tool card that fills its row. A one-button tool is pinned to the bottom so buttons
    /// line up across a row; a tool with stacked rows stays under its heading. Preview mode
    /// shows it without engine-backed controls.
    /// </summary>
    static Border Card(string title, string description, UIElement? tool, bool pinToBottom = true)
    {
        var content = new Grid { RowSpacing = 12 };
        content.RowDefinitions.Add(new() { Height = pinToBottom ? new GridLength(1, GridUnitType.Star) : GridLength.Auto });
        content.RowDefinitions.Add(new() { Height = pinToBottom ? GridLength.Auto : new GridLength(1, GridUnitType.Star) });
        var heading = new StackPanel { Spacing = 4 };
        heading.Children.Add(Prefs.Label(title, "ForgeHeadingTextStyle"));
        heading.Children.Add(Prefs.Label(description, "ForgeCaptionDimTextStyle"));
        content.Children.Add(heading);
        var body = tool ?? Prefs.Label("Available with the installed engine.", "ForgeCaptionDimTextStyle");
        Grid.SetRow((FrameworkElement)body, 1);
        content.Children.Add(body);
        return new Border { Style = Prefs.GetStyle("ForgeControlPodStyle"), Padding = new Thickness(20, 16, 20, 16), Child = content,
            VerticalAlignment = VerticalAlignment.Stretch };
    }
}
