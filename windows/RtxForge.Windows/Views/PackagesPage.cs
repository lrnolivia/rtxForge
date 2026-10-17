using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Views;

/// <summary>
/// Packages (gui/package_browser.py show_packages): the pinned packages for this system,
/// your own ZIP package inspected without running anything, and community sources.
/// </summary>
public sealed partial class PackagesPage : Page
{
    readonly MainWindow shell = App.Main!;
    readonly StackPanel body = new() { Spacing = 4 };
    readonly TextBlock status = Prefs.Label("Checking your system…");

    public PackagesPage()
    {
        InitializeComponent();
        var page = new StackPanel { Spacing = 8, Padding = new Thickness(36, 12, 36, 48) };
        page.Children.Add(new TextBlock { Text = "Packages", Style = Prefs.GetStyle("ForgePageTitleTextStyle") });
        page.Children.Add(Prefs.Label("Use a supported package or inspect your own. Every game change is reviewed before it is applied."));
        page.Children.Add(status);
        page.Children.Add(body);
        Content = new ScrollViewer { Content = page, HorizontalScrollMode = ScrollMode.Disabled };
        SizeChanged += (_, e) => page.Padding = PageMargins.For(e.NewSize.Width);
        Loaded += async (_, _) => await LoadAsync();
    }

    static string ProviderName(string id) => id switch { "dlss-unlocked" => "DLSS-Unlocked", "skynizz" => "Skynizz NR + Ada MFG bridge", "custom" => "Custom package", "y4my" => "y4my Multipass", _ => id };

    async Task LoadAsync()
    {
        PackageCatalog catalog;
        try { catalog = await shell.Service.PackagesAsync(); }
        catch (InvalidOperationException error) { status.Text = error.Message; return; }
        status.Text = catalog.Status + " · In use: " + (shell.Settings.RuntimeProvider == "custom" && catalog.CustomName is { } name
            ? name : ProviderName(shell.Settings.RuntimeProvider));
        body.Children.Clear();

        var available = new PreferencesGroup("Available packages");
        foreach (var item in catalog.Packages)
        {
            var current = shell.Settings.RuntimeProvider == item.Id;
            var use = Prefs.ActionButton(current ? "In use" : "Use package", (_, _) => { shell.SelectPackage(item.Id); _ = LoadAsync(); },
                accent: item.Recommended && !current);
            use.IsEnabled = item.Available && !current;
            ToolTipService.SetToolTip(use, item.Reason);
            available.Add(Prefs.Row(item.Name, item.Version + " · " + item.Summary, use, ""));
        }
        body.Children.Add(available);
        if (shell.Settings.RuntimeProvider == "skynizz")
        {
            var version = new PreferencesGroup("Skynizz release", "NR + MFG uses the app's compiled Ada bridge and requires native DLSS Frame Generation. NR Only can use stock Skynizz. Both require a compatible local model and D3D12/DLSS; target runtime validation is pending.");
            var (versionRow, choice) = Prefs.EntryRow("Version", "Use latest supported, or pin a release such as v1.2.1. Repair retains the recorded package. Exact source and SHA-256 are reviewed before installation.", shell.Settings.SkynizzVersion);
            choice.LostFocus += (_, _) => { shell.Settings.SkynizzVersion = string.IsNullOrWhiteSpace(choice.Text) ? "latest" : choice.Text.Trim(); shell.SaveSettings(); };
            version.Add(versionRow);
            body.Children.Add(version);
        }

        var custom = new PreferencesGroup("Your own package", "ZIP archives. Files and instructions are inspected without running them.");
        var pick = Prefs.ActionButton("Choose archive", async (_, _) => await InspectAsync(), glyph: "");
        pick.IsEnabled = !shell.Service.IsPreview;
        custom.Add(Prefs.Row("Add custom package", catalog.CustomName is { } saved ? "Reviewed: " + saved : "Detect the layout and review suggested settings", pick, ""));
        body.Children.Add(custom);

        if (catalog.Community.Count > 0)
        {
            var community = new PreferencesGroup("Other community projects",
                "Source discovery only. Other GPUs and layouts remain unvalidated by this app; the current deployment route targets RTX 40.");
            foreach (var source in catalog.Community)
                community.Add(Prefs.Row(source.Name, source.Note, new HyperlinkButton { Content = "View source", NavigateUri = new Uri(source.Url) }, ""));
            body.Children.Add(community);
        }
    }

    async Task InspectAsync()
    {
        var path = await shell.PickFileAsync(".zip");
        if (path is null) return;
        status.Text = "Reading package files and configuration…";
        PackageInspection inspection;
        try { inspection = await shell.Service.InspectPackageAsync(path); }
        catch (InvalidOperationException error) { status.Text = error.Message; return; }
        status.Text = "Inspection complete. No game files have changed.";

        var panel = new StackPanel { Spacing = 12, MinWidth = 600 };
        panel.Children.Add(Prefs.Row(inspection.Name, inspection.Confidence + $" · Detected format: {inspection.Family} · {inspection.FileCount} files · {inspection.ExpandedBytes / 1048576.0:0.0} MiB expanded", glyph: ""));
        var fields = new Dictionary<string, Func<string>>();
        var settings = new PreferencesGroup("Package Settings");
        string[] counts = ["auto", "0", "1", "2", "3", "4", "5"];
        foreach (var parameter in inspection.Parameters)
        {
            if (parameter.Key == "OverrideInterpolationCount")
            {
                var (row, combo) = Prefs.ComboRow("MFG multiplier", parameter.Origin, ["Auto", "Off", "2×", "3×", "4×", "5×", "6×"], Math.Max(0, Array.IndexOf(counts, parameter.Value)));
                fields[parameter.Key] = () => counts[Math.Max(0, combo.SelectedIndex)];
                settings.Add(row);
            }
            else
            {
                var (row, entry) = Prefs.EntryRow(parameter.Label, parameter.Origin, parameter.Value);
                entry.MinWidth = 120;
                fields[parameter.Key] = () => entry.Text.Trim();
                settings.Add(row);
            }
        }
        panel.Children.Add(settings);
        if (inspection.Warnings.Count > 0) panel.Children.Add(Prefs.Label(string.Join("\n", inspection.Warnings), "ForgeCaptionDimTextStyle"));
        foreach (var (file, text) in inspection.Instructions)
            panel.Children.Add(new Expander
            {
                Header = file + " · original instructions · commands are never executed", HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                Content = new TextBox { Text = text, IsReadOnly = true, TextWrapping = TextWrapping.Wrap, AcceptsReturn = true, MaxHeight = 220 },
            });
        panel.Children.Add(Prefs.Label("Your editable instructions / review notes (never executed)"));
        var notes = new TextBox
        {
            Text = string.Join("\n\n", inspection.Instructions.Select(i => i.Text)), AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 100, MaxHeight = 200,
        };
        panel.Children.Add(notes);
        if (!inspection.Deployable)
            panel.Children.Add(Prefs.Label("This layout has no verified deployment adapter yet. It can be inspected, but nothing will be installed.", "ForgeCaptionDimTextStyle"));
        var trust = new CheckBox { Content = "I trust the source of this package" };
        panel.Children.Add(trust);

        var dialog = shell.NewDialog();
        dialog.Title = "Review your package";
        dialog.Resources["ContentDialogMaxWidth"] = 820.0;
        dialog.Content = new ScrollViewer { Content = panel, MaxHeight = 620 };
        dialog.PrimaryButtonText = "Use reviewed package";
        dialog.IsPrimaryButtonEnabled = false;
        dialog.CloseButtonText = "Cancel";
        trust.Checked += (_, _) => dialog.IsPrimaryButtonEnabled = inspection.Deployable;
        trust.Unchecked += (_, _) => dialog.IsPrimaryButtonEnabled = false;
        PackageChoice? choice = null;
        dialog.PrimaryButtonClick += async (_, args) =>
        {
            var deferral = args.GetDeferral();
            try
            {
                choice = await shell.Service.UseCustomPackageAsync(inspection, fields.ToDictionary(f => f.Key, f => f.Value()), trust.IsChecked == true, notes.Text);
            }
            catch (InvalidOperationException error)
            {
                args.Cancel = true;
                status.Text = error.Message;
                panel.Children.Add(Prefs.Label(error.Message));
            }
            finally { deferral.Complete(); }
        };
        await dialog.ShowAsync();
        if (choice is null) { shell.Service.DiscardReview(new EngineReview(inspection.Token, "package", "", "", "", [], [])); return; }
        shell.SelectPackage("custom", choice.Presets);
        await LoadAsync();
    }
}

/// <summary>Extras (show_extras): standalone tools and NR diagnostics for each game.</summary>
public sealed partial class ExtrasPage : Page
{
    readonly MainWindow shell = App.Main!;
    readonly StackPanel list = new() { Spacing = 4 };

    public ExtrasPage()
    {
        InitializeComponent();
        var page = new StackPanel { Spacing = 8, Padding = new Thickness(36, 12, 36, 48) };
        page.Children.Add(new TextBlock { Text = "Extras", Style = Prefs.GetStyle("ForgePageTitleTextStyle") });
        page.Children.Add(Prefs.Label("Manage standalone tools and NR diagnostics for each game."));
        page.Children.Add(list);
        Content = new ScrollViewer { Content = page, HorizontalScrollMode = ScrollMode.Disabled };
        SizeChanged += (_, e) => page.Padding = PageMargins.For(e.NewSize.Width);
        Fill();
        shell.GamesChanged += Fill;
        Unloaded += (_, _) => shell.GamesChanged -= Fill;
    }

    void Fill()
    {
        list.Children.Clear();
        if (shell.Games.Count == 0) list.Children.Add(Prefs.Label("Your games appear here after the library scan."));
        foreach (var game in shell.Games)
        {
            var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            var diagnose = Prefs.ActionButton("Diagnose NR", async (_, _) => await shell.DiagnoseAsync(game));
            diagnose.IsEnabled = game.Installed;
            actions.Children.Add(diagnose);
            actions.Children.Add(Prefs.ActionButton("Tools", (_, _) => shell.OpenGame(game, "Tools")));
            var row = Prefs.Row(game.Name, game.Installed ? game.Profile ?? "Configured" : game.Blocked ? game.BlockedReason ?? "Unsupported" : "Not installed", actions);
            if (row.Child is Grid grid) grid.Children.Add(Art(game));
            list.Children.Add(row);
        }
    }

    /// <summary>
    /// The list view's wide capsule (98×46, art corner radius) with the review
    /// screen's 2px bezel in the game's own accent color.
    /// </summary>
    static Grid Art(Game game)
    {
        var art = new Grid
        {
            Width = 98, Height = 46,
            CornerRadius = (CornerRadius)Application.Current.Resources["ForgeArtCornerRadius"],
            Background = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["ControlFillColorSecondaryBrush"],
            BorderThickness = new Thickness(2),
        };
        art.Children.Add(new Image { Source = ViewModels.GameItem.Image(game.CapsulePath ?? game.PosterPath), Stretch = Microsoft.UI.Xaml.Media.Stretch.UniformToFill });
        _ = BezelAsync(art, game);
        return art;
    }

    static async System.Threading.Tasks.Task BezelAsync(Grid art, Game game)
    {
        if (await Services.ArtAccent.ForGameAsync(game) is { } palette) art.BorderBrush = palette.AccentBrush;
    }
}
