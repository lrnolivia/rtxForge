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
    readonly StackPanel body = new() { Spacing = 20 };
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

    static string ProviderName(string id) => id switch { "feeder" => "Feeder NR", "dlss-unlocked" => "DLSS-Unlocked", "skynizz" => "Skynizz NR + Ada MFG bridge", "custom" => "Custom package", "y4my" => "y4my Multipass", _ => id };

    async Task LoadAsync()
    {
        PackageCatalog catalog;
        try { catalog = await shell.Service.PackagesAsync(); }
        catch (InvalidOperationException error) { status.Text = error.Message; return; }
        status.Text = catalog.Status + " · In use: " + (shell.Settings.RuntimeProvider == "custom" && catalog.CustomName is { } name
            ? name : ProviderName(shell.Settings.RuntimeProvider));
        body.Children.Clear();

        var curated = new StackPanel { Spacing = 12, Margin = new Thickness(0, 12, 0, 0) };
        curated.Children.Add(Prefs.Label("Curated Packages", "ForgeHeadingTextStyle"));
        var packages = new PresetColumns(360, 2) { ColumnSpacing = 12, RowSpacing = 12 };
        foreach (var item in catalog.Packages.OrderByDescending(p => p.Id == shell.Settings.RuntimeProvider).ThenByDescending(p => p.Recommended))
            packages.Children.Add(PackageCard(item));
        curated.Children.Add(packages);
        body.Children.Add(curated);
        if (catalog.Packages.Any(p => p.Id == "feeder") || shell.Settings.RuntimeProvider == "feeder")
        {
            var feeder = Section("Feeder NR", "Used for compatible DirectX 11 games, including when Skynizz is selected. Choose your local stack once; rtxForge keeps a verified copy, and installation copies ReShade, Feeder, RenoDX and shaders for you. NR only.");
            var paths = new PresetColumns(360, 2) { ColumnSpacing = 16, RowSpacing = 12 };
            paths.Children.Add(FolderField("Local stack folder", "Your ReShade, Feeder, RenoDX and shader files. Only needed until rtxForge keeps a copy.",
                shell.Settings.FeederSource, path => shell.Settings.FeederSource = path));
            paths.Children.Add(FolderField("Original backups folder", "Original manifests and backups used to recognize existing setups. rtxForge keeps verified copies.",
                shell.Settings.FeederBackups, path => shell.Settings.FeederBackups = path));
            feeder.Children.Add(paths);
            var kept = Prefs.Label("Checking stored Feeder files…", "ForgeCaptionDimTextStyle");
            var keep = new Button { Content = "Keep a copy in rtxForge", HorizontalAlignment = HorizontalAlignment.Left };
            ToolTipService.SetToolTip(keep, "Verify both folders and store their files with rtxForge. Game files are not changed.");
            async Task ShowKeptAsync(bool import)
            {
                keep.IsEnabled = false;
                try
                {
                    var storage = await shell.Service.FeederStorageAsync(import ? NonEmpty(shell.Settings.FeederSource) : null,
                        import ? NonEmpty(shell.Settings.FeederBackups) : null);
                    kept.Text = (storage.Recipe is null ? "No stack stored yet" : "Stored stack · " + storage.Recipe
                        + (storage.NrVersion is null ? "" : " · NR model " + storage.NrVersion))
                        + $" · {storage.Backups} original backup{(storage.Backups == 1 ? "" : "s")} kept";
                }
                catch (InvalidOperationException error) { kept.Text = error.Message; }
                finally { keep.IsEnabled = true; }
            }
            static string? NonEmpty(string value) => string.IsNullOrWhiteSpace(value) ? null : value;
            keep.Click += async (_, _) => await ShowKeptAsync(true);
            feeder.Children.Add(kept);
            feeder.Children.Add(keep);
            _ = ShowKeptAsync(false);
            body.Children.Add(shell.Settings.RuntimeProvider == "feeder" ? Card(feeder) : new Expander
            {
                Header = "Feeder setup · DirectX 11 NR", Content = feeder, HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
            });
        }
        if (shell.Settings.RuntimeProvider == "skynizz")
        {
            var components = new PresetColumns(400, 2) { ColumnSpacing = 12, RowSpacing = 12 };
            var nr = Section("NR package", "Skynizz for DirectX 12 games with DLSS. A compatible local NR model is required.");
            var release = catalog.Packages.FirstOrDefault(p => p.Id == "skynizz")?.Version.Split(' ', StringSplitOptions.RemoveEmptyEntries).FirstOrDefault();
            var releases = new List<string> { "latest" };
            var captions = new List<string> { "Latest supported (recommended)" };
            if (release is not null && release.StartsWith('v') && Version.TryParse(release[1..], out _))
            {
                releases.Add(release); captions.Add(release + " · keep this release");
            }
            var saved = shell.Settings.SkynizzVersion;
            var savedOnly = !releases.Contains(saved);
            if (savedOnly) { releases.Add(saved); captions.Add("Saved release · " + saved); }
            nr.Children.Add(Choice("Release", "Repairs keep each game's installed release. New installs use this selection.", captions,
                releases.IndexOf(saved), index => shell.Settings.SkynizzVersion = releases[index], savedOnly ? captions.Count - 1 : -1));
            nr.Children.Add(Choice("NR model preset", "Performance (B) uses preset 2 with compatible 310.9.16 models.",
                ["Automatic", "Legacy (A)", "Performance (B)"], Math.Clamp(shell.Settings.NrPreset ?? 0, 0, 2),
                index => shell.Settings.NrPreset = index));
            components.Children.Add(Card(nr));
            var mfg = Section("MFG package", "For NR + MFG installs in games with native DLSS Frame Generation.");
            mfg.Children.Add(Choice("MFG component", "Applies to new installs. Restore an existing package before switching components.",
                ["Integrated Ada bridge", "MFG Unlock 1.4.4 (preview)"], shell.Settings.MfgProvider == "mfg-unlock" ? 1 : 0,
                index => shell.Settings.MfgProvider = index == 1 ? "mfg-unlock" : "integrated"));
            mfg.Children.Add(Prefs.Label("MFG Unlock uses ReShade and replaces the integrated unlock. The separate component remains a preview.", "ForgeCaptionDimTextStyle"));
            components.Children.Add(Card(mfg));
            body.Children.Add(components);
        }

        var sources = new PresetColumns(400, catalog.Community.Count > 0 ? 2 : 1) { ColumnSpacing = 12, RowSpacing = 12 };
        var custom = Section("Your own package", "Inspect a ZIP archive and review its settings before using it. Instructions are never run.");
        var pick = Prefs.ActionButton("Choose archive", async (_, _) => await InspectAsync(), glyph: "");
        pick.IsEnabled = !shell.Service.IsPreview;
        pick.HorizontalAlignment = HorizontalAlignment.Right;
        if (catalog.CustomName is { } customName) custom.Children.Add(Prefs.Label("Reviewed: " + customName, "ForgeCaptionDimTextStyle"));
        custom.Children.Add(pick);
        sources.Children.Add(Card(custom));

        if (catalog.Community.Count > 0)
        {
            var community = Section("Other community projects", "Explore other projects. These sources aren't curated install options.");
            foreach (var source in catalog.Community)
            {
                var entry = new StackPanel { Spacing = 4 };
                entry.Children.Add(new HyperlinkButton { Content = source.Name, NavigateUri = new Uri(source.Url), Padding = new Thickness(0) });
                entry.Children.Add(Prefs.Label(source.Note, "ForgeCaptionDimTextStyle"));
                community.Children.Add(entry);
            }
            sources.Children.Add(Card(community));
        }
        body.Children.Add(sources);
    }

    Border PackageCard(PackageOption item)
    {
        var current = shell.Settings.RuntimeProvider == item.Id;
        var content = new Grid { RowSpacing = 12 };
        content.RowDefinitions.Add(new() { Height = GridLength.Auto });
        content.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        content.RowDefinitions.Add(new() { Height = GridLength.Auto });
        content.Children.Add(Section(item.Name, item.Version));
        var description = new StackPanel { Spacing = 8 };
        description.Children.Add(Prefs.Label(item.Summary));
        if (!item.Available) description.Children.Add(Prefs.Label(item.Reason, "ForgeCaptionDimTextStyle"));
        Grid.SetRow(description, 1); content.Children.Add(description);
        var use = Prefs.ActionButton(current ? "In use" : "Use package", (_, _) => { shell.SelectPackage(item.Id); _ = LoadAsync(); },
            accent: item.Recommended && !current);
        use.IsEnabled = item.Available && !current && !shell.Busy;
        use.HorizontalAlignment = HorizontalAlignment.Right;
        ToolTipService.SetToolTip(use, item.Reason);
        Grid.SetRow(use, 2); content.Children.Add(use);
        return Card(content);
    }

    static StackPanel Section(string title, string description)
    {
        var section = new StackPanel { Spacing = 10 };
        var heading = new StackPanel { Spacing = 4 };
        heading.Children.Add(Prefs.Label(title, "ForgeHeadingTextStyle"));
        heading.Children.Add(Prefs.Label(description, "ForgeCaptionDimTextStyle"));
        section.Children.Add(heading);
        return section;
    }

    static Border Card(UIElement content) => new()
    {
        Style = Prefs.GetStyle("ForgeControlPodStyle"), Padding = new Thickness(20, 16, 20, 16), Child = content,
    };

    UIElement Choice(string title, string description, IReadOnlyList<string> captions, int selected, Action<int> save, int retainedOnly = -1)
    {
        var field = new StackPanel { Spacing = 6 };
        field.Children.Add(new TextBlock { Text = title, TextWrapping = TextWrapping.Wrap });
        var combo = new ComboBox { HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch };
        for (var i = 0; i < captions.Count; i++) combo.Items.Add(new ComboBoxItem { Content = captions[i], IsEnabled = i != retainedOnly });
        combo.SelectedIndex = selected;
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(combo, title);
        combo.SelectionChanged += (_, _) => { if (combo.SelectedIndex < 0 || combo.SelectedIndex == retainedOnly) return; save(combo.SelectedIndex); shell.SaveSettings(); };
        field.Children.Add(combo);
        field.Children.Add(Prefs.Label(description, "ForgeCaptionDimTextStyle"));
        return field;
    }

    UIElement FolderField(string title, string description, string value, Action<string> save)
    {
        var field = new StackPanel { Spacing = 6 };
        field.Children.Add(new TextBlock { Text = title, TextWrapping = TextWrapping.Wrap });
        var input = new TextBox { Text = value };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(input, title);
        input.LostFocus += (_, _) => { save(input.Text.Trim()); shell.SaveSettings(); };
        field.Children.Add(input);
        field.Children.Add(Prefs.Label(description, "ForgeCaptionDimTextStyle"));
        return field;
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
