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
        var cards = new PresetColumns(420, 2) { ColumnSpacing = 16, RowSpacing = 16, Margin = new Thickness(0, 12, 0, 0) };
        var engine = shell.Service as EngineForgeService;

        cards.Children.Add(Card("One-time changes", "Turn neural rendering or frame generation on or off, or set the multiplier, in every game with a package installed.",
            engine is null ? null : new GlobalControlsView(engine, settingsRows: true)));
        cards.Children.Add(Card("Update the rtxForge Overlay", "Bring the in-game overlay in your installed games up to date. Tuning and restore backups are kept.",
            engine is null ? null : new OverlayUiReviewView(engine, packages: true)));
        cards.Children.Add(Card("Update DLSS files", "Replace older DLSS files across your library. Originals are backed up.",
            Action("Review games", "", () => shell.LaunchAction("update-dlss", shell.Games.Where(g => !g.Blocked).ToList()))));
        cards.Children.Add(Card("Undo previous changes", "Restore the files from an earlier install, update or restore.",
            Action("Show changes", "", shell.ShowPreviousChangesAsync)));
        cards.Children.Add(Card("App storage", "Downloads, backups and caches rtxForge keeps. Clean up what no game needs.",
            engine is null ? null : new AppStorageView(shell, engine)));
        page.Children.Add(cards);

        Content = new ScrollViewer { Content = page, HorizontalScrollMode = ScrollMode.Disabled };
        SizeChanged += (_, e) => page.Padding = PageMargins.For(e.NewSize.Width);
    }

    UIElement Action(string text, string glyph, Func<Task> run)
    {
        var button = Prefs.ActionButton(text, async (_, _) => await run(), glyph: glyph);
        button.HorizontalAlignment = HorizontalAlignment.Right;
        button.IsEnabled = !shell.Service.IsPreview;
        return button;
    }

    /// <summary>A tool card; preview mode shows the tool without its engine-backed controls.</summary>
    static Border Card(string title, string description, UIElement? tool)
    {
        var content = new StackPanel { Spacing = 12 };
        var heading = new StackPanel { Spacing = 4 };
        heading.Children.Add(Prefs.Label(title, "ForgeHeadingTextStyle"));
        heading.Children.Add(Prefs.Label(description, "ForgeCaptionDimTextStyle"));
        content.Children.Add(heading);
        content.Children.Add(tool ?? Prefs.Label("Available with the installed engine.", "ForgeCaptionDimTextStyle"));
        return new Border { Style = Prefs.GetStyle("ForgeControlPodStyle"), Padding = new Thickness(20, 16, 20, 16), Child = content,
            VerticalAlignment = VerticalAlignment.Top };
    }
}
